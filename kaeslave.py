#!/usr/bin/env python

"""
Runs on the Raspberry Pi connected to the Kaelus beamformer via USB, to send pointing commands, etc.
"""

import os
import logging
from logging import handlers
import random
import sys
import time

import astropy
import astropy.time
import astropy.units
from astropy.time import Time
from astropy.coordinates import SkyCoord, EarthLocation

import serial
from serial import Serial
import threading

if sys.version_info.major == 2:
    # noinspection PyUnresolvedReferences
    STR_CLASS = basestring
else:
    STR_CLASS = str

# set up the logging

LOGLEVEL_CONSOLE = logging.INFO  # Logging level for console messages (INFO, DEBUG, ERROR, CRITICAL, etc)
LOGLEVEL_LOGFILE = logging.INFO  # Logging level for logfile
LOGLEVEL_REMOTE = logging.INFO
LOGFILE = "/tmp/kaeslave.log"


class MWALogFormatter(logging.Formatter):
    def format(self, record):
        return "%s: time %10.6f - %s" % (record.levelname, time.time(), record.getMessage())


mwalf = MWALogFormatter()

logger = logging.getLogger()
logger.setLevel(logging.DEBUG)

fh = handlers.RotatingFileHandler(LOGFILE, maxBytes=1000000000,
                                  backupCount=5)  # 1 Gb per file, max of five old log files
fh.setLevel(LOGLEVEL_LOGFILE)
fh.setFormatter(mwalf)

ch = logging.StreamHandler()
ch.setLevel(LOGLEVEL_CONSOLE)
ch.setFormatter(mwalf)

# add the handlers to the logger
logger.addHandler(fh)
logger.addHandler(ch)

import Pyro4

sys.excepthook = Pyro4.util.excepthook
Pyro4.config.DETAILED_TRACEBACK = True
Pyro4.config.SERIALIZERS_ACCEPTED.add('pickle')

import pyslave
import beamformer
import pointing

TILEID = 99
CLIENTNAME = 'Kaelus'

SIMULATE = False  # Set to False to control a real Kaelus beamformer
TEST = False

STRICT = False

ONLYBFs = None
# ONLYBFs = ['E']

CPOS = (0.0, 0.0, 0.0)  # Offset from geometric centre, in metres, to use as delay centre for pointing calculations

SLAVEPORT = 19987
DEVICE0 = '/dev/ttyUSB0'
DEVICE1 = '/dev/ttyUSB1'

DEFATTEN = 0  # Default channel attenuation, 0-255
DIPOLEFILE = None  # Filename containing dipole offsets from the centre in metres, or None to use MWA tile spacings

MWAPOS = EarthLocation.from_geodetic(lon="116:40:14.93", lat="-26:42:11.95", height=377.8)

# Timeout for PyController comms to the PointingSlave instance
PS_TIMEOUT = 60


class KaelusBeamformer(object):
    """Represents a single Kaelus beamformer. Two attributes (.X and .Y) contain
       instances of the 'Beamformer' class from beamformer.py, to handle serial
       communications.
    """

    def __init__(self, simulate=False, dipolefile=DIPOLEFILE):
        """
        Create an instance of a Kaelus beamformer.

        :param simulate: If True, don't talk to the actual hardware, just simulate a physical box
        :param dipolefile: File name to read dipole physical locations from.
        """
        self.simulate = simulate
        if not self.simulate:
            try:
                serial0 = Serial(DEVICE0)  # serial port for X pol board
                serial1 = Serial(DEVICE1)  # serial port for Y pol board
            except serial.serialutil.SerialException:
                logger.critical("Error opening serial port, exiting")
                sys.exit()
            A = beamformer.Beamformer(serial0, name=DEVICE0)
            B = beamformer.Beamformer(serial1, name=DEVICE1)

            # Create two threads to initialise the X and Y beamformer boxes in parallel. Wait until both
            # have finished before we exit. We don't know which is X and which is Y until after the initialisation,
            # when we can read the serial numbers.
            athread = threading.Thread(target=self._init_pol, args=(A,))
            bthread = threading.Thread(target=self._init_pol, args=(B,))
            athread.start()
            bthread.start()
            athread.join()
            bthread.join()

            if 'TX2150200007' in A.BFSerial:
                self.X = A
                self.Y = B
            elif 'TX2150200008' in A.BFSerial:
                self.X = B
                self.Y = A
            else:
                logger.critical('Unable to find a valid BFSerial value, X/Y polarisations could be wrong: %s, %s' % (A.BFSerial, B.BFSerial))
                self.X = A
                self.Y = B

            logger.info('Assigned delay board TX2150200007 as X, TX2150200008 as Y')
            self.X.name = 'X'
            self.Y.name = 'Y'

            self.channels = [self.X, self.Y]
        else:
            logger.critical("Running in simulation mode, not controlling the actual Kaelus hardware!")
            self.X = None
            self.Y = None
            self.channels = []

        self.offsets = pointing.getOffsets(dipolefile=dipolefile)  # Read dipole offsets in from file

    def _init_pol(self, pol):
        """
        Initialise one physical Kaelus component (X or Y)

        :param pol: An instance of beamformer.Beamformer, either self.X or self.Y
        """
        logger.info("Initialising %s" % pol.name)
        with pol.lock:
            pol.OpenConnection()
            pol.ClearAlarms()
            pol.CombinerLNA = 1
            pol.ChannelEnableDiag = [
                                        15] * 16  # 0x01 is LNA2, 0x02 is LNA1, 0x04 is output, 0x08 is input, 0x10 is antenna LNA
            pol.ChannelDelay = [128] * 16
            pol.ChannelAttenuators = [DEFATTEN] * 16
            pol.UpdateSettingsDiagnostics()
            pol.ReadAll()
            pol.PrintInfo(diag=1)
            pol.CloseConnection()
        logger.info("%s initialisation finished." % pol.name)

    def onlybfs(self, bfids=None):
        """Set which of the MWA beamformers contribute to the EDA output. Unused inputs
           are disabled to avoid adding in noise.

           If called with bfids=None, enables all first stage inputs to the Kaelus beamformer. If bfids
           is a list or string of single hex digits, disable all Kaelus inputs except the ones specified.

           The state is stored in a global variable, and returned by the get_status call in the PointingSlave
           class.

           Result is True if the call suceeded, False if there was a problem with the bfids parameter.

           :param bfids: A list or a string of hex digits specifying imputs to use, or None to use all of them.
        """
        enables = [15] * 16
        global ONLYBFs
        onlybfs = None
        if bfids is None:
            logger.info('Enabling all channels')
            enables = [15] * 16
        elif (type(bfids) == list) or (isinstance(bfids, STR_CLASS)):
            enables = [0] * 16
            onlybfs = []
            for bfid in bfids:
                if (isinstance(bfid, STR_CLASS)) and (len(bfid) == 1):
                    if bfid.upper() in pointing.HEXD:
                        onlybfs.append(bfid.upper())
                        enables[pointing.HEXD.index(bfid.upper())] = 15
                    else:
                        logger.error("Invalid BFID code: %s" % bfid)
                        return False
                else:
                    logger.error("Invalid BFID: %s" % bfid)
                    return False

        logger.info('Enabling only beamformers: %s' % bfids)
        for pol in [self.X, self.Y]:
            with pol.lock:
                pol.ChannelEnableDiag = enables
                pol.OpenConnection()
                pol.UpdateSettingsDiagnostics()
                pol.ReadAll()
                pol.PrintInfo(diag=1)
                pol.CloseConnection()
        logger.info('Finished KaelusBeamformer.only1bf(bfids=%s) --> %s, %s' % (bfids, onlybfs, enables))
        ONLYBFs = onlybfs
        return True

    def MarcinHack(self):
        """Enable a couple of specific Kaelus inputs for testing, and disable the rest.
        """
        logger.info('MarcinHack: Enabling input 2 in X, and 5 in Y (both indexed from 1)')
        for pol in [self.X, self.Y]:
            with pol.lock:
                enables = [0] * 16  # All channels disabled
                if pol is self.X:
                    enables[4] = 1
                elif pol is self.Y:
                    enables[1] = 1
                pol.ChannelEnableDiag = enables
                pol.OpenConnection()
                pol.UpdateSettingsDiagnostics()
                pol.ReadAll()
                pol.PrintInfo(diag=1)
                pol.CloseConnection()
        logger.info('Finished KaelusBeamformer.MarcinHack with 2Y and 5X enabled.')
        return True

    def doPointing(self, starttime=0, xaz=0.0, xel=90.0, xdelays=None):
        """Given coordinates or delay settings, repoint the tile.

           NOTE that yaz and yel are ignored - only xaz and xel parameters are used to point BOTH polarisations. This is to
           save time, as the delay calculations can significant length of time on a Raspberry Pi.

           The X and Y polarisations are pointed in independent threads in parallel, to save time.

           Result is True for pointed OK, False for below 'horizon', None for simulated.

           :param starttime: If supplied, wait until this unix timetamp before actually pointing the tile, then return
           :param xaz: azimuth (in degrees) to point to
           :param xel: elevation (in degrees) to point to
           :param xdelays: raw delays - either None (to use az/el), or a dict (full EDA delays, as returned by pointing.calc_delays()
           :return: True on success, False if there was a problem with the parameters
        """
        if xdelays and (type(xdelays) == dict):  # If delays is a dict, they are EDA delays, so use them. If a list, they are normal MWA tile delays
            logger.info("Received raw delays to send to beamformers")
            ydelays = xdelays
        else:
            xdelays, diagnostics = pointing.calc_delays(offsets=self.offsets, az=xaz, el=xel, verbose=True,
                                                        strict=STRICT, cpos=CPOS)
            if diagnostics is not None:
                delays, delayerrs, sqe, maxerr, offcount = diagnostics
                if offcount > 0:
                    logger.warning(
                        'Elevation low - %d dipoles disabled because delays were too large to reach in hardware.' % offcount)
            ydelays = xdelays
        if (xdelays is None) or (ydelays is None):
            return False

        if self.simulate:
            return None
        else:
            self.X.ChannelDelay = [xdelays['K'][bfid] + 128 for bfid in
                                   pointing.HEXD]  # Add 128 to rescale from signed (-128 to +127) values
            self.Y.ChannelDelay = [ydelays['K'][bfid] + 128 for bfid in pointing.HEXD]
            now = time.time()
            if starttime > now:
                time.sleep(starttime - now)
            xthread = threading.Thread(target=self._point_pol, args=(self.X,))
            ythread = threading.Thread(target=self._point_pol, args=(self.Y,))
            xthread.start()
            ythread.start()
            xthread.join()
            ythread.join()
            #      self.LogAlarms()    # TODO - Comms errors when reading alarms, since the lightning strike in Jan 2017. Re-enable after repairs?
            return True

    def PrintInfo(self, diag=1):
        """
        Get status and version details from the Kaelus hardware, and print it to standard out.

        :param diag: 1 (the default) to print diagnostic values, 0 to print calibrated values.
        :return: None
        """
        print("Beamformer status for X-pol:")
        with self.X.lock:
            self.X.OpenConnection()
            self.X.PrintInfo(diag)
            self.X.CloseConnection()
        print("\n\nBeamformer status for Y-pol:")
        with self.Y.lock:
            self.Y.OpenConnection()
            self.Y.PrintInfo(diag)
            self.Y.CloseConnection()
        print('\n')

    def LogAlarms(self):
        """
        Write current hardware alarm status to the log file.

        :return: None
        """
        with self.X.lock:
            self.X.OpenConnection()
            self.X.ReadAlarms()
            self.X.CloseConnection()
        logger.info("Alarm status for X-pol: %s" % self.X.AlarmStatus)
        with self.Y.lock:
            self.Y.OpenConnection()
            self.Y.ReadAlarms()
            self.Y.CloseConnection()
        logger.info("Alarm status for Y-pol: %s" % self.Y.AlarmStatus)

    def _point_pol(self, pol):
        """
        Point the given polarisation (self.X or self.Y) using the previously supplied delay switch settings

        :param pol: An instance of beamformer.Beamformer, either self.X or self.Y
        :return:
        """
        logger.debug("Pointing %s" % pol.name)
        with pol.lock:
            pol.OpenConnection()
            pol.SetDelaySwitches()
            pol.UpdateDelays()
            pol.CloseConnection()
        logger.info("Pointed %s" % pol.name)


def calc_azel(ra=0.0, dec=0.0, calctime=None):
    """Takes RA and DEC in degrees, calculates Az/El of target at the specified time in unix epoch seconds.
       If the time is not specified, calculate for 'now'.

       :param ra: Right Ascension (J2000) in degrees
       :param dec: Declination (J2000) in degrees
       :param calctime: Time (as a unix time stamp) for the conversion, or None to calculate for the current time.
       :return: A tuple of (azimuth, elevation) in degrees
    """
    # noinspection PyUnresolvedReferences
    coords = SkyCoord(ra=ra, dec=dec, equinox='J2000', unit=(astropy.units.deg, astropy.units.deg))
    if calctime is None:
        azeltime = Time.now()
    else:
        azeltime = Time(calctime, format='unix', scale='utc')
    coords.location = MWAPOS
    coords.obstime = azeltime
    cpos = coords.transform_to('altaz')
    return cpos.az.deg, cpos.alt.deg


class PointingSlave(pyslave.Slave):
    """Subclass the pycontroller slave class so we can override the notify() method to point the EDA.

       The notify() method (to point the EDA) is the only remote method called by pycontroller, at the start of each
       MWA observation. The other methods defined here (stop_tracking, get_status, etc) are called by
       EDA client code (edacmd tool, ploteda, etc). The EDA client code can also call notify() to
       point the EDA.
    """

    def __init__(self, bf=None, tileid=0, clientid=None, port=None):
        self.bf = bf
        self.tileid = tileid
        self.orig_tileid = tileid  # Save the 'real' tile ID here, so we can change the 'current' one
        self.lastpointing = (None, None, None, None, None, None, None, None, None)
        pyslave.Slave.__init__(self, clientid=clientid, rclass='pointing', port=port)

    @Pyro4.expose
    def stop_tracking(self):
        """Change the tileid that we recognise for notify() calls, so that we ignore any notify() calls
           from pycontroller in response to MWA observations. EDA client code calls to notify() use a
           tileid of 0, and are always recognised
        """
        self.tileid = None
        logger.warning('Tracking disable, current tile ID set to None')
        return True

    @Pyro4.expose
    def start_tracking(self):
        """Change the tileid that we recognise for notify() calls, so that we react to any notify() calls
          from pycontroller in response to MWA observations. EDA client code calls to notify() use a
          tileid of 0, and are always recognised
       """
        self.tileid = self.orig_tileid
        logger.warning('Tracking enabled, current tile ID restored to %d' % self.tileid)
        return True

    @Pyro4.expose
    def onlybfs(self, bfids=None):
        """If called with bfids=None, enables all first stage inputs to the Kaelus beamformer. If bfids
           is a list or string of single hex digits, disable all Kaelus inputs except the ones specified.

           The state is saved in a global variable, and lasts until the next call to onlybfs().

           :param bfids: A list of hex digits (eg ['0', '4', 'A']), or a string of hex digits (eg '04A')
           :return: False if there was an error parsing the bfids argument, True if successful.
        """
        return self.bf.onlybfs(bfids=bfids)

    @Pyro4.expose
    def set_cpos(self, cpos=None):
        """Sets the position of the EDA centre used for delay calculations, relative to the geometric centre.

           If cpos is not None, it must be a tuple of three floats, used as an offset from the geometrical
           EDA centre (0,0,0) in the units used in the locations file), in metres.

           The state is saved in a global variable, and lasts until the next call to set_cpos().

           :param cpos: A tuple of three floats (offsets E/W, N/S and up/down), or None.
           :return: False if there was an error parsing the cpos argument, True if successful.
        """
        global CPOS
        if cpos is None:
            CPOS = (0.0, 0.0, 0.0)
        else:
            if (type(cpos) == tuple) and (len(cpos) == 3):
                ok = True
                for element in cpos:
                    if (type(element) != float) and (type(element) != int):
                        ok = False
                if ok:
                    CPOS = cpos
                    return True
                else:
                    logger.error('Invalid item in argument for set_cpos(%s) call' % cpos)
                    return False
            else:
                logger.error('Invalid argument to set_cpos(%s)' % cpos)
                return False

    @Pyro4.expose
    def is_tracking(self):
        """Returns True if we are tracking MWA observations, False otherwise."""
        return self.tileid == self.orig_tileid

    @Pyro4.expose
    def get_status(self):
        """Returns a status object. This is a tuple of:
          istracking (True or False),
          ONLYBFs (global variable, None for all beamformers enabled, or a list of hex digit if only some are enabled)
          CPOS (global flag containing offset centre for delay calculations)
          self.tileid (None if not tracking, otherwise the MWA tile ID that the EDA is mirroring,
          self.lastpointing - the last pointing status.

        The 'lastpointing' status is itself a tuple, of:
          starttime (in GPS seconds or unix timestamp) - when the pointing took place
          obsid (in GPS seconds) for this observation
          xra
          xdec
          xaz
          xel
          xdelays (a list of 16 raw delay values, overriding az/el/ra/dec)
          offcount (how many dipoles were disabled, using onlybfs or because the required delay values couldn't be met)
          ok (True or False) - whether the pointing was successful
     """
        return (self.is_tracking(), ONLYBFs, CPOS, self.tileid, self.lastpointing)

    @Pyro4.expose
    def notify(self, obsid=None, starttime=None, stoptime=None, clientid=None, rclass=None, values=None):
        """Called remotely by the master object when registered tile properties change.

           This takes the az/el pointing direction, converts to a list of 256 tuples for
           the 256 AAVS antennae (x,y), and calls the SetDelays() function on the
           Kaelus beamformer to send these delay settings. The Kaelus beamformer
           blocks until the specified time, and returns True or False, and this value
           is returned to Pycontroller.

           :param obsid:     The MWA observation ID (time in GPS seconds) for the new observation.
           :param starttime: The time the new observation should start, either in GPS seconds or
                              seconds since the Unix epoch (defined when the client is registered).
           :param stoptime:  The time the new observation should stop, in the same timescale (GPS seconds
                              or Unix epoch seconds) as the starttime parameter.
           :param clientid:  Arbitrary client name string, should match this client's ID.
           :param rclass:    Registration class - either 'pointing', 'freq', 'atten', or 'obs'. Defines
                              what sort of notification messages we should be sent. Should match registrion
                              class of this client.
           :param values:    The actual data for the new observation, as a dictionary where
                              tile_id is the key. The value is a dictionary with polarisation ('X' or 'Y') as
                              the key, and a tuple of (ra, dec, az, el, rawdelays) as value.
                              Eg:  values={0:{'X':(12.0, -26.0, None, None, None), 'Y':(12.0, -26.0, None, None, None)}}

           :return:          A tuple of (clientid, obsid, starttime, resdict) where 'resdict' is a dictionary with tileid
                             as a key, and tuples of (BFtemperature,ok) as a value, and the other items are defined above.
        """
        assert rclass == 'pointing'
        assert clientid == self.clientid
        if self.tileid in values.keys():
            xra, xdec, xaz, xel, xdelays = values[self.tileid]['X']
            yra, ydec, yaz, yel, ydelays = values[self.tileid]['Y']
        elif 0 in values.keys():
            logger.info('Manual pointing command received - tile 0 information')
            xra, xdec, xaz, xel, xdelays = values[0]['X']
            yra, ydec, yaz, yel, ydelays = values[0]['Y']
        elif self.tileid is None:
            logger.info('Not pointing - MWA tracking disabled, will only point when given tileid=0')
            return self.clientid, obsid, starttime, {self.tileid:(999, False)}  # Tuple of clientid, tileid, starttime, temperature in deg C, and a 'pointing OK' boolean
        else:
            logger.warning('Not pointing - tileid of %s not in tileset: %s' % (self.tileid, values.keys()))
            return self.clientid, obsid, starttime, {self.tileid:(999, False)}  # Tuple of clientid, tileid, starttime, temperature in deg C, and a 'pointing OK' boolean

        if xdelays and (type(xdelays) == dict):
            logger.info("Received raw delays to send to beamformers for obsid=%s, time=%s" % (obsid, starttime))
        elif (xra is not None) and (xdec is not None):
            logger.info("Received RA/Dec=%s/%s for target at obsid=%s, time=%s, calculating Az/El" % (xra, xdec, obsid, starttime))
            az, el = calc_azel(ra=xra, dec=xdec, calctime=(starttime + ((starttime - stoptime) / 2)))
            xaz = yaz = az
            xel = yel = el
        else:
            logger.info("Received Az/el for obsid=%s, time %s: az=%s, el=%s" % (obsid, starttime, xaz, xel))
        ok = self.bf.doPointing(starttime=starttime,
                                xaz=xaz, xel=xel,
                                yaz=yaz, yel=yel,
                                xdelays=xdelays, ydelays=ydelays)  # Result is True for pointed OK, False for below 'horizon', None for simulated
        self.lastpointing = (starttime, obsid, xra, xdec, xaz, xel, xdelays, -1, ok)  # Note that the offcount value isn't returned from the Kaelus BF, so set it to -1
        logger.info("Pointed: ok=%s for obsid=%s, time %s: ra=%s,  dec=%s, az=%s, el=%s" % (ok, obsid, starttime, xra, xdec, xaz, xel))
        return self.clientid, obsid, starttime, {self.tileid:(-999, ok)}


if __name__ == '__main__':
    if len(sys.argv) > 1:
        TILEID = int(sys.argv[1])
    if len(sys.argv) > 2:
        CLIENTNAME = sys.argv[2]

    logger.info("Forcing low-latency mode OFF for USB serial devices.")
    os.system('setserial %s ^low_latency' % DEVICE0)
    os.system('setserial %s ^low_latency' % DEVICE1)

    calc_azel(ra=0.0, dec=-26.0)  # Run the astropy function once on startup, to preload all the ephemeris data and save time later

    KBF = KaelusBeamformer(simulate=SIMULATE)

    # Point the BF at the zenith when the daemon starts up:
    KBF.doPointing()

    if TEST:
        while True:
            az = random.random() * 360
            el = 82.0 + random.random() * 18.0
            KBF.doPointing(xaz=az, xel=el)
            time.sleep(5)
    else:
        pcs = PointingSlave(bf=KBF, tileid=TILEID, clientid=CLIENTNAME, port=SLAVEPORT)
        pcs.startup()
        time.sleep(1)

        # We don't want to register with the MWA observation controller to shadow MWA observations:
        # pcs.register(tiles=[TILEID], gpstime=False, control=True)

        # KBF.MarcinHack()   # Enable just 2Y and 8X

        # while True:
        #   try:
        #     while True:
        #       logger.debug('Now %8.1f, last heartbeat %8.1f' % (time.time(), pcs.heartbeat_time))
        #       if (time.time() - pcs.heartbeat_time) > PS_TIMEOUT:
        #         logger.error('Timeout hearing from PyController, reregistering now')
        #         try:
        #           pcs.register(tiles=[TILEID], gpstime=False, control=True)
        #           logger.info('Re-registered')
        #         except:
        #           logger.exception('Failed to re-register with ObsController')
        #       time.sleep(10)
        #   finally:
        #     # cleanup
        #     pcs.deregister()
        #     pcs.exiting = True
        #     pcs.pyro_daemon.shutdown()
        #   time.sleep(10)

        try:
            while True:
                time.sleep(10)
        finally:
            # cleanup
            pcs.deregister()
            pcs.exiting = True
            pcs.pyro_daemon.shutdown()
