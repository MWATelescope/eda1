#!/usr/bin/env python

"""
Runs on one Raspberry Pi inside each of the beamformer control boxes, to send pointing commands to the eight
beamformers connected to that box.

On startup, it:
    -Checks that the hostname (as reported by 'hostname -A') is either 'eda1com or 'eda2com', and exits if not.
    -Uses the integer (1 or 2) in the hostname to determine whether this box is connected to the first
      eight beamformers (0-8), or the second eight beamformers (9-F).
    -Starts a Pyro4 daemon on port 19987 to listen for (and execute) remote procedure calls over the network.

On exit (eg, with a control-C or a 'kill' command), it:
    -Stops the Pyro4 daemon
    -Exits.
"""

import atexit
import logging
from logging import handlers
import optparse
import signal
import subprocess
import sys
import threading
import time
import warnings

# noinspection PyUnresolvedReferences
import RPi.GPIO as GPIO

import astropy
import astropy.time
import astropy.units
from astropy.time import Time
from astropy.coordinates import SkyCoord, EarthLocation
from astropy.utils.exceptions import AstropyWarning, ErfaWarning

warnings.simplefilter('ignore', AstropyWarning)
warnings.simplefilter('ignore', ErfaWarning)


if sys.version_info.major == 2:
    # noinspection PyUnresolvedReferences
    STR_CLASS = basestring
else:
    STR_CLASS = str

# set up the logging

LOGLEVEL_CONSOLE = logging.DEBUG  # Logging level for console messages (INFO, DEBUG, ERROR, CRITICAL, etc)
LOGLEVEL_LOGFILE = logging.DEBUG  # Logging level for logfile
LOGLEVEL_REMOTE = logging.INFO
LOGFILE = "/tmp/edacom.log"


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

# rh = handlers.SysLogHandler(address=('mw-gw', 514))
# rh.setLevel(LOGLEVEL_REMOTE)
# rh.setFormatter(mwalf)

# add the handlers to the logger
logger.addHandler(fh)
logger.addHandler(ch)
# logger.addHandler(rh)

import Pyro4

# noinspection PyUnresolvedReferences
sys.excepthook = Pyro4.util.excepthook
Pyro4.config.DETAILED_TRACEBACK = True
Pyro4.config.SERIALIZERS_ACCEPTED.add('pickle')

import pyslave
import pointing

TILEID = 99  # MWA tile ID for the EDA station

SLAVEPORT = 19987

STRICT = False

ONLYBFs = None
# ONLYBFs = ['E']

CPOS = (0.0, 0.0, 0.0)  # Offset from geometric centre, in metres, to use as delay centre for pointing calculations

# IO pin allocations as (txdata, txclock, rxdata) for each of the 8 RxDOC cards in this box, numbered 1-8
IOPINS = {1:(29, 16, 40), 2:(26, 15, 38), 3:(24, 13, 37), 4:(23, 12, 36), 5:(22, 11, 35), 6:(21, 10, 33), 7:(19, 8, 32),
          8:(18, 7, 31)}

# Timeout for PyController comms to the PointingSlave instance
PS_TIMEOUT = 60

SIGNAL_HANDLERS = {}
CLEANUP_FUNCTION = None

MWAPOS = EarthLocation.from_geodetic(lon="116:40:14.93", lat="-26:42:11.95", height=377.8)


def init():
    """Initialise IO pins for pointing comms with all 8 beamformers
    """
    GPIO.setmode(GPIO.BOARD)  # Use board connector pin numbers to specify I/O pins
    GPIO.setwarnings(False)
    for i in range(1, 9):
        txdata, txclock, rxdata = IOPINS[i]
        GPIO.setup(rxdata, GPIO.IN)
        GPIO.setup(txdata, GPIO.OUT)
        GPIO.setup(txclock, GPIO.OUT)

#
# def get_hostname():
#     """Returns the hostname, with domain stripped off. Used to work out whether this Raspberry Pi controls MWA
#        beamformers 0-8 (eda1com.mwa128t.org) or beamformers 9-F (eda2com.mwa128t.org).
#     """
#     if sys.version_info.major == 2:
#         fqdn = subprocess.check_output(['hostname', '-A'], shell=False)
#     else:
#         fqdn = subprocess.check_output(['hostname', '-A'], shell=False).decode('UTF-8')
#     return fqdn.split('.')[0]


def get_hostname():
    if sys.version_info.major == 2:
        output = subprocess.check_output(['hostname'], shell=False)
    else:
        output = subprocess.check_output(['hostname'], shell=False).decode('UTF-8')
    return output.strip().split('.')[0]


def point(starttime=0, bfnum=0, outstring='', results=None, resultlock=None):
    """
       Called with the start time of the next observation (a unix timestamp), the beamformer number to point, and
       the string containing the delay bits to write.

       Waits until the specified time, then sends the bit string to the beamformer. The results are written to the
       given dictionary, using the lock supplied - this is because 'point' is called in parallel for all eight
       beamformers, using the same results dictionary, so that all eight beamformers are pointed at the same instant.

       :param starttime: start time in seconds past the unix epoch,
       :param bfnum: beamformer output number (1-8),
       :param outstring: bit-string to send,
       :param results: dictionary to store (temp, flag) returned from the beamformer,
       :param resultlock: lock object to avoid conflicts writing to the results dict
       :return:
    """
    now = time.time()
    if now < starttime:
        logger.debug("bf %d is sleeping for %5.2f seconds" % (bfnum, starttime - now))
        time.sleep(starttime - now)
    temp, flags = send_bitstring(bfnum=bfnum, outstring=outstring)
    with resultlock:
        results[bfnum] = (temp, flags)
    logger.info("bf %d bitstring sent." % bfnum)


def calc_azel(ra=0.0, dec=0.0, calctime=None):
    """
       Takes RA and DEC in degrees, and calculates Az/El of target at the specified time

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

       Any methods decorated with '@Pyro4.expose' are called remotely over the network, from the control
       computer.
    """

    def __init__(self, edanum=0, tileid=0, clientid=None, port=None):
        """
        :param edanum: Either 1 or 2, used to determine which set of 8 beamformers we are pointing.
        :param tileid: Which MWA tile number we are (used to ignore notify() calls not meant for us)
        :param clientid: Pyro4 service name - eg eda1com
        :param port: network port to listen on
        """
        self.tileid = tileid
        self.orig_tileid = tileid  # Save the 'real' tile ID here, so we can change the 'current' one
        self.edanum = edanum
        self.offsets = pointing.getOffsets()
        self.lastpointing = (None, None, None, None, None, None, None, None, None)
        pyslave.Slave.__init__(self, clientid=clientid, rclass='pointing', port=port)

    @Pyro4.expose
    def stop_tracking(self):
        """Change the tileid that we recognise for notify() calls, so that we ignore any notify() calls
           from pycontroller in response to MWA observations. EDA client code calls to notify() use a
           tileid of 0, and are always recognised.
        """
        self.tileid = -1
        logger.info('Tracking disable, current tile ID set to None')
        return True

    @Pyro4.expose
    def start_tracking(self):
        """Change the tileid that we recognise for notify() calls, so that we react to any notify() calls
           from pycontroller in response to MWA observations. EDA client code calls to notify() use a
           tileid of 0, and are always recognised.
        """
        self.tileid = self.orig_tileid
        logger.info('Tracking enabled, current tile ID restored to %d' % self.tileid)
        return True

    @Pyro4.expose
    def onlybfs(self, bfids=None):
        """If called with bfids=None, enables all dipoles on all MWA beamformers. If bfids is a list of
           single hex digits, or a string of hex digits, enable all dipoles on those beamformers, and
           disable them on all others.

           The state is saved in a global variable, and lasts until the next call to onlybfs().

           :param bfids: A list of hex digits (eg ['0', '4', 'A']), or a string of hex digits (eg '04A')
           :return: False if there was an error parsing the bfids argument, True if successful.
        """
        global ONLYBFs
        if bfids is None:
            logger.info('Enabling all channels')
            ONLYBFs = None
        elif (type(bfids) == list) or (isinstance(bfids, STR_CLASS)):
            onlybfs = []
            for bfid in bfids:
                if (isinstance(bfid, STR_CLASS)) and (len(bfid) == 1):
                    if bfid.upper() in pointing.HEXD:
                        onlybfs.append(bfid.upper())
                    else:
                        logger.critical("Invalid BFID code: %s" % bfid)
                        return False
                else:
                    logger.critical("Invalid BFID: %s" % bfid)
                    return False
            logger.info("Enabling only beamformers %s" % onlybfs)
            ONLYBFs = onlybfs

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
           the 256 AAVS antennae (x,y), and calls the point() function in parallel in eight
           seperate threads. Each thread waits until the specified observation start time,
           sends the new delays to its MWA beamformer, and returns True or False. If all eight
           tiles point OK, the OK flag returned by this function is True.

           Note that while RA/Dec/Az/El/Delays are passed individually for both X and Y polarisation, the
           current code ignores the Y pol data, and uses the X pol data to set both the X and Y delay values.

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
        elif 0 in values.keys():
            logger.info('Manual pointing command received - tile 0 information')
            xra, xdec, xaz, xel, xdelays = values[0]['X']
        elif self.tileid < 0:
            logger.info('Not pointing - MWA tracking disabled, will only point when given tileid=0')
            return self.clientid, obsid, starttime, {self.tileid:(999, False)}  # Tuple of clientid, tileid, starttime, temperature in deg C, and a 'pointing OK' boolean
        else:
            logger.warning('Not pointing - tileid of %s not in tileset: %s' % (self.tileid, values.keys()))
            return self.clientid, obsid, starttime, {self.tileid:(999, False)}  # Tuple of clientid, tileid, starttime, temperature in deg C, and a 'pointing OK' boolean

        if xdelays and (type(xdelays) == dict):  # If delays is a dict, they are EDA delays, so use them. If a list, they are normal MWA tile delays
            logger.info("Received raw delays to send to beamformers")
            idelays = xdelays
        else:
            if (xra is not None) and (xdec is not None):
                logger.info("Received RA/Dec=%s/%s for target at obsid=%s, time=%s, calculating Az/El" % (xra, xdec, obsid, starttime))
                az, el = calc_azel(ra=xra, dec=xdec, calctime=(starttime + ((starttime - stoptime) / 2)))
                xaz = az
                xel = el
            else:
                logger.info("Received Az/el for obsid=%s, time %s: az=%s, el=%s" % (obsid, starttime, xaz, xel))
            logger.info("New pointing for obsid=%s, time %s: az=%s, el=%s" % (obsid, starttime, xaz, xel))
            if ONLYBFs is not None:
                clipdelays = False
            else:
                clipdelays = True
            idelays, diagnostics = pointing.calc_delays(offsets=self.offsets, az=xaz, el=xel, strict=STRICT,
                                                        verbose=True, clipdelays=clipdelays, cpos=CPOS)
            if diagnostics is not None:
                delays, delayerrs, sqe, maxerr, offcount = diagnostics
                if offcount > 0:
                    logger.warning('Elevation low - %d dipoles disabled because delays were too large to reach in hardware.' % offcount)
            if idelays is None:
                logger.error("Error calculating delays for az=%s, el=%s" % (xaz, xel))
                return self.clientid, obsid, starttime, {self.tileid:(999, False)}

        if ONLYBFs is None:
            offcount = 0
            for bfid in pointing.HEXD:
                for dipid in pointing.HEXD:
                    if idelays[bfid][dipid] == 16:  # disabled
                        offcount += 1
        else:
            offcount = 0
            logger.warning(
                "Only some first stage beamformer enabled (%s), other %d dipoles are disabled!" % (ONLYBFs, offcount))
            for bfid in pointing.HEXD:
                for dipid in pointing.HEXD:
                    if bfid in ONLYBFs:
                        if (idelays[bfid][dipid] < -16) or (idelays[bfid][dipid] > 15):
                            idelays[bfid][dipid] = 16  # Disabled
                            offcount += 1
                    else:
                        idelays[bfid][dipid] = 16  # Disabled
                        offcount += 1

        offset = 0
        if self.edanum == 2:
            offset = 8
        comthreads = []  # Used to store the thread objects that are actually communicating with the beamformers
        results = {}
        resultlock = threading.RLock()
        for bfnum in range(1, 9):
            bfid = hex(bfnum - 1 + offset)[-1].upper()  # Translate input 1-8 on edanum=1 or edanum=2 to a hex bfid in the idelays dict ('0' to 'F')
            tiledelays = [idelays[bfid][hexd] + 16 for hexd in pointing.HEXD]  # raw idelays values range from -16 to +15, so need to add 16 before we send them to the beamformer
            logger.info("bfnum=%d, delays=%s" % (bfnum, tiledelays))
            outstring = gen_bitstring(tiledelays, tiledelays)
            newthread = threading.Thread(target=point,
                                         name='com%s' % bfnum,
                                         kwargs={'starttime':starttime,
                                                 'bfnum':bfnum,
                                                 'outstring':outstring,
                                                 'results':results,
                                                 'resultlock':resultlock})
            newthread.start()
            comthreads.append(newthread)
        for t in comthreads:
            t.join()
        numok = 0
        sumtemp = 0.0
        for bfnum in range(1, 9):
            temp, flags = results[bfnum]
            logger.debug('Port %d: Flags=%d, Temp=%4.1f' % (bfnum, flags, temp))
            if flags == 128:
                numok += 1
                sumtemp += temp
        logger.info(
            "Pointed these tiles without error: %s" % [bfnum for bfnum in range(1, 9) if results[bfnum][1] == 128])
        if numok < 8:
            logger.error("Errors in tiles: %s" % [(bfnum, results[bfnum]) for bfnum in range(1, 9) if results[bfnum][1] != 128])
        self.lastpointing = (starttime, obsid, xra, xdec, xaz, xel, xdelays, offcount, (numok == 8))

        if numok:
            avgtemp = sumtemp / numok
        else:
            avgtemp = 0.0
        return self.clientid, obsid + self.edanum, starttime, {self.tileid:(avgtemp, (numok == 8))}


def gen_bitstring(xdelays, ydelays):
    """Given two arrays of 16 integers, representing the xdelays and ydelays, return
       a string containing 253 characters, each '1' or '0', representing the bit stream
       to be sent to the beamformer.

       Format is:
          8 zeroes
          4 ones
          20 zeroes
          6 blocks of 17 bits, each containing a 16-bit number containing the packed 6-bit
              x delay values, followed by a '1' bit
          6 blocks of 17 bits, each containing a 16-bit number containing the packed 6-bit
              y delay values, followed by a '1' bit
          16 bits of checksum (the twelve 16-bit packed delay words XORed together)
          A '1' bit to mark the end of the 13th 16-bit word

          These 253 bits are returned as a string with 253 '1' and '0' characters.

          After those bits are clocked out, a further 24 clock pulses should be sent, and
          24 bits of data (16 bits containing a 12-bit signed temperature, and 8 bits of
          flags) will be received.
    """
    outlist = ['0' * 8, '1' * 4, '0' * 20]
    dwords = []
    for val in (xdelays + ydelays):
        if (val < 0) or (val > 63):
            return  # Each delay value must fit in 6 bits
        else:
            dwords.append('{0:06b}'.format(val))
    dstring = ''.join(dwords)
    checksum = 0
    for i in range(0, 12 * 16, 16):
        checksum = checksum ^ int(dstring[i:i + 16], 2)
        outlist.append(dstring[i:i + 16] + '1')
    outlist.append('{0:016b}'.format(checksum))
    return ''.join(outlist)  # 253 bits of output data


def send_bitstring(bfnum, outstring, bittime=0.00002):
    """Given a string of 253 '1' or '0' characters, clock them out using the TXDATA and TXCLOCK
       pins, then clock in 24 bits of temp and flag data from the RXDATA pin.

       bittime is the total time to take to send one but, in seconds.
       bfnum is the beamformer number, from 1-8, used to find the correct IO pin numbers
             in the IOPINS dict.
    """
    txdata, txclock, rxdata = IOPINS[bfnum]
    for bit in outstring:
        GPIO.output(txdata, {'1':1, '0':0}[bit])
        time.sleep(bittime / 4)  # wait for data bit to settle
        GPIO.output(txclock, 1)  # Send clock high
        time.sleep(bittime / 2)  # Leave clock high for half the total bit transmit time
        GPIO.output(txclock, 0)  # Send clock low,so data is valid on both rising and falling edge
        time.sleep(bittime / 4)  # Leave data valid until the end of the bit transmit time

    # While the temperature is 16 bits and the checksum is 8 bits, giving 24
    # bits in total, we appear to have to clock an extra bit-time to complete the
    # read-back operation. Once that's done, the checksum is the final (right-
    # most) 8 bits, and the temperature is 13 bits (signed plus 12-bits). Both
    # values are most-significant-bit first (chronologically).

    GPIO.output(txdata, 0)
    inbits = []
    for i in range(25):  # Read in temp data
        time.sleep(bittime / 4)
        GPIO.output(txclock, 1)
        time.sleep(bittime / 4)
        inbits.append({True:'1', False:'0'}[GPIO.input(rxdata)])
        time.sleep(bittime / 4)
        GPIO.output(txclock, 0)
        time.sleep(bittime / 4)

    rawtemp = int(''.join(inbits[:17]), 2)  # Convert the first 16 bits to a temperature
    temp = 0.0625 * (rawtemp & 0xfff)  # 12 bits of value
    if (rawtemp & 0x1000):
        temp -= 256.0
    flags = int(''.join(inbits[17:]), 2)
    return temp, flags


def cleanup():
    """Called on program exit, to clean up GPIO pins and shut down the Pyro server gracefully, without
       leaving hanging network ports.
    """
    global pcs
    logger.info("Cleaning up GPIO library")
    GPIO.cleanup()
    logger.info("Shutting down network Pyro4 daemon")
    try:
        pcs.exiting = True
        pcs.pyro_daemon.shutdown()
    except NameError:
        pass  # In test mode, there's no PySlave instance


# noinspection PyUnusedLocal
def SignalHandler(signum=None, frame=None):
    """Called when a signal is received thay would result in the programme exit, if the
       RegisterCleanup() function has been previously called to set the signal handlers and
       define an exit function using the 'atexit' module.

       Note that exit functions registered by atexit are NOT called when the programme exits due
       to a received signal, so we must trap signals where possible. The cleanup function will NOT
       be called when signal 9 (SIGKILL) is received, as this signal cannot be trapped.
    """
    print("Signal %d received." % signum)
    sys.exit(-signum)  # Called by signal handler, so exit with a return code indicating the signal received


def RegisterCleanup(func):
    """Traps a number of signals that would result in the program exit, to make sure that the
       function 'func' is called before exit. The calling process must define its own cleanup
       function - typically this would delete any facility controller objects, so that any
       processes they have started will be stopped.

       We don't need to trap signal 2 (SIGINT), because this is internally handled by the python
       interpreter, generating a KeyboardInterrupt exception - if this causes the process to exit,
       the function registered by atexit.register() will be called automatically.
    """
    global SIGNAL_HANDLERS, CLEANUP_FUNCTION
    CLEANUP_FUNCTION = func
    for sig in [3, 15]:
        SIGNAL_HANDLERS[sig] = signal.signal(sig, SignalHandler)  # Register a signal handler
    SIGNAL_HANDLERS[1] = signal.signal(1, signal.SIG_IGN)
    # Register the passed CLEANUP_FUNCTION to be called on
    # on normal programme exit, with no arguments.
    atexit.register(CLEANUP_FUNCTION)


if __name__ == '__main__':
    parser = optparse.OptionParser(usage="usage: %prog [options]")
    parser.add_option("-n", "--nohostcheck", default=False, action="store_true", dest="nohostcheck",
                      help="Skip host name check before startup")
    parser.add_option("-t", "--test", default=False, action="store_true", dest="test",
                      help="Test mode - send dummy delays, continuously")

    (options, args) = parser.parse_args()

    init()
    calc_azel(ra=0.0, dec=-26.0)  # Run the astropy function once on startup, to preload all the ephemeris data and save time later
    RegisterCleanup(cleanup)

    if options.nohostcheck:
        edanum = 1
        clientname = 'edaNmc'
    else:
        hostname = get_hostname()
        clientname = hostname
        try:
            eda, edanum, func = hostname[:3], int(hostname[3]), hostname[4:]
            assert eda == 'eda'
            assert (func == 'mc') or (func == 'com')
        except:
            logger.critical("Invalid hostname %s - should be of the form 'edaNmc' or 'edaNcom', where N is an integer" % hostname)
            sys.exit(-1)
        if func != 'com':
            logger.critical("Can't start communications/pointing process on an M&C device. Run on edaNcom host instead")
            sys.exit(-2)

    if options.test:
        xdelays = list(range(0, 32, 2))  # 16 even delay values, [0, 2, 4, ..., 28, 30]
        ydelays = list(range(1, 33, 2))  # 16 even delay values, [1, 3, 5, ..., 29, 31]
        outstring = gen_bitstring(xdelays, ydelays)
        while True:
            for bfnum in range(1, 9):
                temp, flags = send_bitstring(bfnum, outstring)
                logger.info("bf %d bitstring sent, return flags=%d, temp=%4.1f." % (bfnum, flags, temp))
            time.sleep(5)
    else:
        pcs = PointingSlave(edanum=edanum, tileid=TILEID, clientid=clientname, port=SLAVEPORT)
        pcs.startup()
        time.sleep(1)

        while True:
            time.sleep(10)
