#!/usr/bin/env python

"""Command line utility to control EDA, via Pyro4 remote procedure calls to the two
   Raspberry Pi computers doing MWA beamformer control (with 8 beamformers each) and
   one Raspberry Pi controlling the Kaelus beamformer.

   This code needs to know:
      -The telescope coordinates (latitude/longitude/height), defined in the MWAPOS global variable below.
      -The IP addresses of the two Raspberry Pi's inside the first-stage beamformer control boxes (eda1com and eda2com),
        defined in the BURLS global variable below.
      -The IP address of the Raspberry Pi that controls the Kaelus beamformer, defined in the KURL global variable below.
"""

import datetime
import glob
import optparse
import os
import subprocess
import sys
import time
import warnings

warnings.simplefilter(action='ignore')

from astropy.io import fits

import numpy

import Pyro4

import astropy
import astropy.time
import astropy.units
from astropy.time import Time
from astropy.coordinates import SkyCoord, EarthLocation

# Telescope coordinates
MWAPOS = EarthLocation.from_geodetic(lon="116:40:14.93", lat="-26:42:11.95", height=377.8)

kproxy = None
bfproxies = {}

sys.excepthook = Pyro4.util.excepthook
Pyro4.config.DETAILED_TRACEBACK = True

"""
  Tests EDA by pointing it around the zenith, without the need for scheduled MWA observations
"""

HEXD = ['0', '1', '2', '3', '4', '5', '6', '7', '8', '9', 'A', 'B', 'C', 'D', 'E', 'F']

MAXAGE = 60

# Change the IP addresses in these URLs to the right ones on the local network.
KURL = 'PYRO:Kaelus@10.128.2.51:19987'
BURLS = {'eda1com':'PYRO:eda1com@10.128.2.63:19987', 'eda2com':'PYRO:eda2com@10.128.2.65:19987'}

# NUMLOOPS = 80    # 12 hours worth of pointings
ELS = [-19, -15, -10, -5, 0, 5, 10, 15, 19]

NUMLOOPS = 5  # 12 hours worth of pointings
AZELS = [(0.0, 71.0), (0.0, 72.0), (0.0, 73.0), (0.0, 74.0), (0.0, 75.0), (0.0, 76.0), (0.0, 77.0), (0.0, 78.0),
         (0.0, 79.0), (0.0, 80.0),
         (0.0, 81.0), (0.0, 82.0), (0.0, 83.0), (0.0, 84.0), (0.0, 85.0), (0.0, 86.0), (0.0, 87.0), (0.0, 88.0),
         (0.0, 89.0), (0.0, 90.0),
         (180.0, 89.0), (180.0, 88.0), (180.0, 87.0), (180.0, 86.0), (180.0, 85.0), (180.0, 84.0), (180.0, 83.0),
         (180.0, 82.0), (180.0, 81.0), (180.0, 80.0),
         (180.0, 79.0), (180.0, 78.0), (180.0, 77.0), (180.0, 76.0), (180.0, 75.0), (180.0, 74.0), (180.0, 73.0),
         (180.0, 72.0), (180.0, 71.0), (180.0, 70.0)]

TILEID = 0

if sys.version_info.major == 2:
    HOSTNAME = subprocess.check_output(['hostname', '-A'], shell=False).split('.')[0].strip()
else:
    HOSTNAME = subprocess.check_output(['hostname', '-A'], shell=False).decode('UTF-8').split('.')[0].strip()

BIGDAS = 'bigdas' in HOSTNAME  # True if we are running on bigdas


def point_azel(az=0.0, el=0.0, delay=3):
    """
    Given an az/el and a delay in seconds, send network commands to point the EDA at the given az/el.

    :param az: Azimuth in degrees
    :param el: Elevation in degrees
    :param delay: Delay in seconds, for the remote client to wait before sending the new pointing to the beamformers.
    """
    print("Time %10.4f Pointing at az/el: %6.2f, %6.2f" % (time.time(), az, el))
    stime = int(time.time() + delay)
    values = {TILEID:{'X':(None, None, az, el, None),
                      'Y':(None, None, az, el, None)
                      }
              }
    kproxy.notify(obsid=0, starttime=stime, stoptime=stime + 8, clientid='Kaelus', rclass='pointing', values=values)
    for clientid, proxy in bfproxies.items():
        proxy.notify(obsid=0, starttime=stime, stoptime=stime + 8, clientid=clientid, rclass='pointing', values=values)


def calc_azel(ra=0.0, dec=0.0):
    """
    Takes RA and DEC in degrees, and calculates Az/El of target at the current time

    :param ra: Right Ascension (J2000) in degrees
    :param dec: Declination (J2000) in degrees
    :return: A tuple of (azimuth, elevation) in degrees
    """
    coords = SkyCoord(ra=ra, dec=dec, equinox='J2000', unit=(astropy.units.deg, astropy.units.deg))
    now = Time.now()
    coords.location = MWAPOS
    coords.obstime = now
    cpos = coords.transform_to('altaz')
    return cpos.az.deg, cpos.alt.deg


def calc_radec(az=0.0, el=90.0):
    """
    Takes Azimuth and Elevation in degrees, and calculates RA/Dec of target at the current time

    :param az: Azimuth in degrees
    :param el: Elevation in degrees
    :return: A tuple of (ra, dec) in degrees (J2000)
    """
    coords = SkyCoord(alt=el, az=az, unit=(astropy.units.deg, astropy.units.deg), frame='altaz', location=MWAPOS,
                      obstime=Time.now())
    return coords.icrs.ra.deg, coords.icrs.dec.deg


def point_radec(ra=0.0, dec=0.0):
    """
    Given RA and DEC (J2000) in degrees, send commands the point the EDA at that position
    :param ra: Right Ascension (J2000) in degrees
    :param dec: Declination (J2000) in degrees
    """
    az, el = calc_azel(ra=ra, dec=dec)
    point_azel(az=az, el=el)


def track_radec(ra=0.0, dec=0.0, interval=120, total_track_time=31536000):
    """
    Given an RA/Dec, a tracking time, and a re-pointing interval, sesnd repeated pointing commands to follow
    that RA/Dec until the end of the desired tracking time, then return.

    :param ra: Right Ascension (J2000) in degrees
    :param dec: Declination (J2000) in degrees
    :param interval: Number of seconds to wait between re-pointing the telescope.
    :param total_track_time: How many seconds to track for before the function returns.
    """
    start_ux = time.time()
    end_ux = start_ux + total_track_time

    while time.time() <= end_ux:
        az, el = calc_azel(ra=ra, dec=dec)
        point_azel(az=az, el=el)
        time.sleep(interval)


def dopoint(az=0.0, el=90.0, ra=None, dec=None):
    """Jump to the coordinates given. Calculate az/el if given ra/dec,
       if both given then use az/el.

       :param ra: Right Ascension (J2000) in degrees, or None
       :param dec: Declination (J2000) in degrees, or None
       :param az: Azimuth in degrees, or None
       :param el: Elevation in degrees, or None
    """
    if az is None or el is None:
        if ra is not None and dec is not None:
            print("Time %10.4f pointing at calculated ra=%6.2f, dec=%6.2f" % (time.time(), ra, dec))
            point_radec(ra=ra, dec=dec)
        else:
            print("No valid coordinates, not pointing!")
            return
    else:
        print("Time %10.4f pointing at az=%6.2f, el=%6.2f" % (time.time(), az, el))
        point_azel(az=az, el=el)


def start_tracking():
    """
       Start following the MWA observations.
    """
    kproxy.start_tracking()
    for clientid, proxy in bfproxies.items():
        proxy.start_tracking()


def stop_tracking():
    """
       Stop following the MWA observations.
    """
    kproxy.stop_tracking()
    for clientid, proxy in bfproxies.items():
        proxy.stop_tracking()


def is_tracking():
    """
       Returns True if we are following MWA observations, False otherwise.
    """
    kstat = kproxy.get_status()
    istracking, onlybfs, cpos, tileid, lastpointing = kstat
    return istracking


def print_status():
    sdict = {}
    sdict['kaelus'] = kproxy.get_status()
    for clientid, proxy in bfproxies.items():
        sdict[clientid] = proxy.get_status()

    clients = list(sdict.keys())
    clients.sort()
    cdata = []
    for clientid in clients:
        status = sdict[clientid]
        istracking, onlybfs, cpos, tileid, lastpointing = status
        starttime, obsid, ra, dec, az, el, delays, offcount, ok = lastpointing
        cdata.append((starttime, obsid, onlybfs, cpos, tileid))
        if offcount is not None:
            numdipoles = 256 - offcount
        else:
            numdipoles = 0
        if onlybfs is not None:
            withstring = 'with only MWA beamformers: %s ' % onlybfs
        else:
            withstring = ''
        if cpos != (0.0, 0.0, 0.0):
            withstring += 'with delay centre of %s' % str(cpos)
        print(clientid)
        print("  Tracking MWA: %s %s" % (istracking, withstring))
        if starttime is None:
            print("No pointing since startup.")
        else:
            if clientid != 'kaelus':
                print("  Last pointing at time %s (obsid=%d): ra=%s, dec=%s, az=%s, el=%s, with %d working dipoles" % (time.ctime(starttime), obsid, ra, dec, az, el, numdipoles))
            else:
                print("  Last pointing at time %s (obsid=%d): ra=%s, dec=%s, az=%s, el=%s" % (time.ctime(starttime), obsid, ra, dec, az, el))


def getdata():
    """Returns a numpy array containing the most recently written EDA spectrum.
       Return None,None if the most recent file is older than MAXAGE seconds.

       NOTE - this will only work when run on 'bigdas', where live spectrum data is written to /tmp every second.
    """
    if not BIGDAS:
        return None, None  # Can only access live spectra on bigdas
    flist = glob.glob('/tmp/livespec_??.fits')
    fdict = {}
    for fname in flist:
        fdict[os.path.getmtime(fname)] = fname
    tlist = list(fdict.keys())
    tlist.sort()
    dtime = tlist[-1]
    fname = fdict[dtime]
    if (time.time() - dtime) > MAXAGE:
        return None, None  # All files are too old

    tries = 0
    done = False
    data = None
    while tries < 10 and not done:
        try:
            f = fits.open(fname)
            data = f[0].data
            done = True
        except:
            tries += 1
            time.sleep(0.1)
    if done:
        return data, dtime
    else:
        return None, None


def dostripes():
    """
    NOTE - this will only work when run on 'bigdas', where live spectrum data is written to /tmp every second.
    :return:
    """
    xarray = []
    yarray = []
    for elindex in range(len(ELS)):
        xarray[elindex] = numpy.zeros(shape=(NUMLOOPS * 8, 32768))
        yarray[elindex] = numpy.zeros(shape=(NUMLOOPS * 8, 32768))

    allxarray = numpy.zeros(shape=(NUMLOOPS * len(ELS) * 8, 32768))
    # Loop over all the dipoles to test, one by one:
    for loopnum in range(NUMLOOPS):
        for elindex in range(len(ELS)):
            print("loop %d, Testing dipole elevation %d" % (loopnum + 1, ELS[elindex]))
            point_azel(az=0.0, el=ELS[elindex])

            time.sleep(60)
            if BIGDAS:
                data, dtime = getdata()
                if (time.time() - dtime) > 4:
                    print("Stale data found - %5.2f seconds." % (time.time() - dtime))

                xarray[elindex][loopnum * 8:loopnum * 8 + 7] = data[0]
                yarray[elindex][loopnum * 8:loopnum * 8 + 7] = data[1]

                index = (loopnum * len(ELS) + elindex) * 8
                allxarray[index:index + 7] = data[0]

    if BIGDAS:
        for elindex in range(len(ELS)):
            now = time.ctime()
            hdu = fits.PrimaryHDU()
            hdu.data = xarray[elindex]
            hdu.header['TELESCOP'] = "EDA dipole test"
            hdu.header['DATE'] = now
            hdu.writeto('/tmp/edatest%02d_X.fits' % ELS[elindex], clobber=True)

            hdu = fits.PrimaryHDU()
            hdu.data = yarray[elindex]
            hdu.header['TELESCOP'] = "EDA dipole test"
            hdu.header['DATE'] = now
            hdu.writeto('/tmp/edatest%02d_Y.fits' % ELS[elindex], clobber=True)

        now = time.ctime()
        hdu = fits.PrimaryHDU()
        hdu.data = allxarray
        hdu.header['TELESCOP'] = "EDA dipole test"
        hdu.header['DATE'] = now
        hdu.writeto('/tmp/edatest_AllX.fits', clobber=True)


def freqbin(indat=None):
    """Takes a numpy array (shape=(32768,)) and sums groups of 128 channels to
       produce an output array of shape (256,)
    """
    odat = numpy.zeros(shape=(256,), dtype=numpy.float32)
    for i in range(256):
        odat[i] = indat[(i * 128):(i * 128 + 128)].sum()
    odat.shape = (256, 1, 1)
    return odat


def doimage(redfreq=95, greenfreq=160, bluefreq=200, bw=10, rdelay=1, cube=False):
    """Produce an image in three bands (called 'red', 'green' and 'blue') centred on the
       frequencies given in MHz. Each band is 'bw' MHz wide.

       The image is formed by sweeping over all the azimith/elevation values in the AZEL
       global, forming a line at the meridian from 71 degrees elevation due North to
       70 degrees elevation due South. These 40 pointings (1 degree apart) are timed to
       take exactly 4 minutes to complete, in which time the sky moves West by 1 degree,
       so each pointing represents a 1-degree square on the sky.

       For each pointing, a full-spectrum capture from the signatec card is recorded, and
       three chunks (centred on redfreq, greenfreq and bluefred MHz, with a width of 'bw'
       MHz) are averaged and recorded as single pixel values in separate red, green, and
       blue output arrays.

       The rdelay value specifies how many pointings behind the actual telescope position
       the last data values are, when read.

       NOTE - this will only work when run on 'bigdas', where live spectrum data is written to /tmp every second.
    """
    if not BIGDAS:
        print("Needs to run on 'bigdas' host, exiting")
        return
    if cube:
        cubearray = numpy.zeros(shape=(256, len(AZELS) * 8, NUMLOOPS * 8))
    else:
        redarray = numpy.zeros(shape=(len(AZELS) * 8, NUMLOOPS * 8))
        greenarray = numpy.zeros(shape=(len(AZELS) * 8, NUMLOOPS * 8))
        bluearray = numpy.zeros(shape=(len(AZELS) * 8, NUMLOOPS * 8))
        redind, greenind, blueind = redfreq * 100, greenfreq * 100, bluefreq * 100  # Convert frequencies in MHz to channel numbers
        bw2 = bw * 100 / 2  # Convert bandwidth in MHz to half-bandwidth in channels
    exiting = False
    looptime = time.time()
    starttime = looptime
    coordlist = [(0, 0)] * 3  # Initialise a list of pixel coords, with a few dummy values
    ras = {}
    decs = {}
    for loopnum in range(NUMLOOPS):
        ras[loopnum] = []
        now = time.time()
        print("Starting loop %d at %d after %6.2f seconds" % (loopnum + 1, now, now - looptime))
        looptime = now
        for pindex in range(len(AZELS)):
            decs[pindex] = []
            az, el = AZELS[pindex]
            print("  loop %d, testing az/el %d,%d" % (loopnum + 1, az, el))
            point_azel(az=az, el=el, delay=1)
            ra, dec = calc_radec(az=az, el=el)
            ras[loopnum].append(ra)
            decs[pindex].append(dec)

            time.sleep(
                4.075)  # Hand-tuned to result in a 4-minute time to complete 40 az/el pointings one degree apart in dec.
            data, dtime = getdata()  # 4 seconds isn't enough time to wait, use this data read for some previous coordinate's data value.
            if data is None:
                print("Can't get data file, exiting loop")
                exiting = True
                break

            if (time.time() - dtime) > 4:
                print("Stale data found - %5.2f seconds." % (time.time() - dtime))
                exiting = True
                break

            coordlist.append((loopnum, pindex))  # Push the current pointing coords onto the end of the list
            lln, lpin = coordlist[-rdelay]  # The last data value we read corresponds to the last pointing, not this one
            if cube:
                cubearray[:, lpin * 8:lpin * 8 + 8, lln * 8:lln * 8 + 8] = freqbin(data[0])
            else:
                redarray[lpin * 8:lpin * 8 + 8, lln * 8:lln * 8 + 8] = data[0][redind - bw2: redind + bw2].sum()
                greenarray[lpin * 8:lpin * 8 + 8, lln * 8:lln * 8 + 8] = data[0][greenind - bw2: greenind + bw2].sum()
                bluearray[lpin * 8:lpin * 8 + 8, lln * 8:lln * 8 + 8] = data[0][blueind - bw2: blueind + bw2].sum()

        tstart = datetime.datetime.fromtimestamp(starttime).isoformat()
        tend = datetime.datetime.fromtimestamp(time.time()).isoformat()
        hdu = fits.PrimaryHDU()
        hdu.header['TELESCOP'] = "EDA dipole test"
        hdu.header['TSTART'] = tstart
        hdu.header['TEND'] = tend

        rastartmean = sum(ras[0]) / len(ras[0])
        rastartmax = max(ras[0])
        rastartmin = min(ras[0])
        raendmean = sum(ras[max(ras.keys())]) / len(ras[max(ras.keys())])
        raendmax = max(ras[max(ras.keys())])
        raendmin = min(ras[max(ras.keys())])
        if raendmean > rastartmean:
            raem = raendmean
        else:
            raem = raendmean + 360.0
        racenter = (rastartmean + raem) / 2
        if racenter > 360:
            racenter -= 360

        decstartmean = sum(decs[0]) / len(decs[0])
        decstartmax = max(decs[0])
        decstartmin = min(decs[0])
        decendmean = sum(decs[max(decs.keys())]) / len(decs[max(decs.keys())])
        decendmax = max(decs[max(decs.keys())])
        decendmin = min(decs[max(decs.keys())])

        hdu.header['RASTART'] = rastartmean
        hdu.header['RASSPAN'] = rastartmax - rastartmin
        hdu.header['RAESPAN'] = raendmax - raendmin
        hdu.header['RAEND'] = raendmean
        hdu.header['DECSTART'] = decstartmean
        hdu.header['DECSSPAN'] = decstartmax - decstartmin
        hdu.header['DECESPAN'] = decendmax - decendmin
        hdu.header['DECEND'] = decendmean

        hdu.header['EQUINOX'] = 2000
        hdu.header['CRPIX2'] = int(8 * len(AZELS) / 2)
        hdu.header['CRVAL2'] = (decstartmean + decendmean) / 2  # Centre DEC value
        hdu.header['CRPIX1'] = int(8 * (loopnum + 1) / 2)
        hdu.header['CRVAL1'] = racenter  # Centre RA value, allowing for 0/360 wrap during drift scan
        hdu.header[
            'CDELT2'] = -0.125  # (decstartmean - decendmean) / int(8 * len(AZELS))    # Each degree is an 8x8 pixel square, so each pixel is ~ 1/8th of a degree
        hdu.header['CDELT1'] = 0.125  # (rastartmean - raendmean) / int(8 * (loopnum + 1))
        hdu.header['CTYPE2'] = 'DEC'
        hdu.header['CUNIT2'] = 'deg'
        hdu.header['CTYPE1'] = 'RA'
        hdu.header['CUNIT1'] = 'deg'
        hdu.header['RADESYS'] = 'ICRS'

        if cube:
            hdu.header['CRPIX3'] = 128
            hdu.header['CRVAL3'] = 163.84
            hdu.header['CDELT3'] = 1.28
            hdu.header['CTYPE3'] = 'FREQ'
            hdu.header['CUNIT3'] = 'MHz'
            hdu.data = cubearray
            hdu.writeto('/tmp/eda_cube.fits', clobber=True)
        else:
            hdu.data = redarray
            hdu.header['FREQS'] = "%5.1fMHz - %5.1fMHz" % (redfreq - bw / 2.0, redfreq + bw / 2.0)
            hdu.writeto('/tmp/eda_image_R.fits', clobber=True)

            hdu.data = greenarray
            hdu.header['FREQS'] = "%5.1fMHz - %5.1fMHz" % (greenfreq - bw / 2.0, greenfreq + bw / 2.0)
            hdu.writeto('/tmp/eda_image_G.fits', clobber=True)

            hdu.data = bluearray
            hdu.header['FREQS'] = "%5.1fMHz - %5.1fMHz" % (bluefreq - bw / 2.0, bluefreq + bw / 2.0)
            hdu.writeto('/tmp/eda_image_B.fits', clobber=True)

        if exiting:
            break

    for coordindex in range(rdelay + 1,
                            0):  # Keep in going until we've written data into the array for every pointing we did
        time.sleep(6)
        data, dtime = getdata()
        if data is None:
            print("Can't get data file")
            return

        if (time.time() - dtime) > 4:
            print("Stale data - %5.2f seconds." % (time.time() - dtime))
            return

        lln, lpin = coordlist[coordindex]
        if cube:
            cubearray[:, lpin * 8:lpin * 8 + 8, lln * 8:lln * 8 + 8] = freqbin(data[0])
        else:
            redarray[lpin * 8:lpin * 8 + 8, lln * 8:lln * 8 + 8] = data[0][redind - bw2: redind + bw2].sum()
            greenarray[lpin * 8:lpin * 8 + 8, lln * 8:lln * 8 + 8] = data[0][greenind - bw2: greenind + bw2].sum()
            bluearray[lpin * 8:lpin * 8 + 8, lln * 8:lln * 8 + 8] = data[0][blueind - bw2: blueind + bw2].sum()

    tstart = datetime.datetime.fromtimestamp(starttime).isoformat()
    tend = datetime.datetime.fromtimestamp(time.time()).isoformat()
    hdu = fits.PrimaryHDU()
    hdu.header['TELESCOP'] = "EDA dipole test"
    hdu.header['TSTART'] = tstart
    hdu.header['TEND'] = tend

    rastartmean = sum(ras[0]) / len(ras[0])
    rastartmax = max(ras[0])
    rastartmin = min(ras[0])
    raendmean = sum(ras[max(ras.keys())]) / len(ras[max(ras.keys())])
    raendmax = max(ras[max(ras.keys())])
    raendmin = min(ras[max(ras.keys())])
    if raendmean > rastartmean:
        raem = raendmean
    else:
        raem = raendmean + 360.0
    racenter = (rastartmean + raem) / 2
    if racenter > 360:
        racenter -= 360

    decstartmean = sum(decs[0]) / len(decs[0])
    decstartmax = max(decs[0])
    decstartmin = min(decs[0])
    decendmean = sum(decs[max(decs.keys())]) / len(decs[max(decs.keys())])
    decendmax = max(decs[max(decs.keys())])
    decendmin = min(decs[max(decs.keys())])

    hdu.header['RASTART'] = rastartmean
    hdu.header['RASSPAN'] = rastartmax - rastartmin
    hdu.header['RAESPAN'] = raendmax - raendmin
    hdu.header['RAEND'] = raendmean
    hdu.header['DECSTART'] = decstartmean
    hdu.header['DECSSPAN'] = decstartmax - decstartmin
    hdu.header['DECESPAN'] = decendmax - decendmin
    hdu.header['DECEND'] = decendmean

    hdu.header['EQUINOX'] = 2000
    hdu.header['CRPIX2'] = int(8 * len(AZELS) / 2)
    hdu.header['CRVAL2'] = (decstartmean + decendmean) / 2  # Centre DEC value
    hdu.header['CRPIX1'] = int(8 * NUMLOOPS / 2)
    hdu.header['CRVAL1'] = racenter  # Centre RA value, allowing for 0/360 wrap during drift scan
    hdu.header[
        'CDELT2'] = -0.125  # (decstartmean - decendmean) / int(8 * len(AZELS))  # Each degree is an 8x8 pixel square, so each pixel is ~ 1/8th of a degree
    hdu.header['CDELT1'] = 0.125  # (rastartmean - raendmean) / int(8 * (NUMLOOPS + 1))
    hdu.header['CTYPE2'] = 'DEC'
    hdu.header['CUNIT2'] = 'deg'
    hdu.header['CTYPE1'] = 'RA'
    hdu.header['CUNIT1'] = 'deg'
    hdu.header['RADESYS'] = 'ICRS'

    if cube:
        hdu.header['CRPIX3'] = 128
        hdu.header['CRVAL3'] = 163.84
        hdu.header['CDELT3'] = 1.28
        hdu.header['CTYPE3'] = 'FREQ'
        hdu.header['CUNIT3'] = 'MHz'
        hdu.data = cubearray
        hdu.writeto('/tmp/eda_cube.fits', clobber=True)
    else:
        hdu.data = redarray
        hdu.header['FREQS'] = "%5.1fMHz - %5.1fMHz" % (redfreq - bw / 2.0, redfreq + bw / 2.0)
        hdu.writeto('/tmp/eda_image_R.fits', clobber=True)

        hdu.data = greenarray
        hdu.header['FREQS'] = "%5.1fMHz - %5.1fMHz" % (greenfreq - bw / 2.0, greenfreq + bw / 2.0)
        hdu.writeto('/tmp/eda_image_G.fits', clobber=True)

        hdu.data = bluearray
        hdu.header['FREQS'] = "%5.1fMHz - %5.1fMHz" % (bluefreq - bw / 2.0, bluefreq + bw / 2.0)
        hdu.writeto('/tmp/eda_image_B.fits', clobber=True)


def zenith_sweep():
    print("Zenith sweep, looping forever, ^C to exit")
    while True:
        for pindex in range(len(AZELS)):
            starttime = time.time()
            az, el = AZELS[pindex]
            print("  Testing az/el %d,%d" % (az, el))
            point_azel(az=az, el=el)
            time.sleep(starttime + 6.0 - time.time())


def domwagaintest():
    """Sweep the MWA (1st stage) BF's through delays of 0,1,2,4,8,16 and collect power data to see the
       relation between MWA BF delay line used, and output power. Keep the Kaelus delays the same.

       Note that edacom.py adds 16 to the delays it receives, so we need to send -16, -15, -14, -12, -8, and 0

       NOTE - this will only work when run on 'bigdas', where live spectrum data is written to /tmp every second.
    """
    HEXD = ['0', '1', '2', '3', '4', '5', '6', '7', '8', '9', 'A', 'B', 'C', 'D', 'E', 'F']
    RAWDELAYS = [0, 1, 2, 4, 8, 16]

    if BIGDAS:
        gainarrayx = numpy.zeros(shape=(NUMLOOPS, 6, 32768))
        gainarrayy = numpy.zeros(shape=(NUMLOOPS, 6, 32768))
        zarray = numpy.zeros(shape=(2, 32768))

    delays = {}
    for b in HEXD:
        delays[b] = {}
        for d in HEXD:
            delays[b][d] = -16  # An offset of 16 is added to all delays, so this will become 0 (disabled)
    delays['K'] = {}  # An extra beamformer delay dict is added for the Kaelus beamformer (2nd stage)
    for d in HEXD:
        delays['K'][d] = -128  # An offset of 128 is added to all delays, so this will become 0

    print("Setting raw Kaelus delays to 0")
    stime = int(time.time() + 1)
    values = {253:{'X':(None, None, 0.0, 0.0, delays),
                   'Y':(None, None, 0.0, 0.0, delays)
                   }
              }
    try:
        kproxy.notify(obsid=0, starttime=stime, stoptime=stime + 8, clientid='Kaelus', rclass='pointing', values=values)
    except AssertionError:
        print("Pointing error - aborting")
        return

    print("Starting run of %d loops." % NUMLOOPS)
    for loop in range(NUMLOOPS):
        print("  %10.4f: Starting loop %d" % (time.time(), loop))
        for bit in range(6):
            for b in HEXD:
                for d in HEXD:
                    delays[b][d] = RAWDELAYS[bit] - 16  # An offset of 16 is added to all delays in edacom.py
            print("    %10.4f: Setting MWA raw delays to %d" % (time.time(), RAWDELAYS[bit]))
            stime = int(time.time() + 1)
            values = {253:{'X':(None, None, 0.0, 0.0, delays),
                           'Y':(None, None, 0.0, 0.0, delays)
                           }
                      }
            try:
                for clientid, proxy in bfproxies.items():
                    proxy.notify(obsid=0, starttime=stime, stoptime=stime + 8, clientid=clientid, rclass='pointing',
                                 values=values)
            except AssertionError:
                print("Pointing error - aborting")
                return

            time.sleep(8)

            if BIGDAS:
                data, dtime = getdata()
                if data is None:
                    print("No data - aborting")
                    return
                if (time.time() - dtime) > 4:
                    print("Stale data - aborting")
                    return
                if bit == 0:
                    zarray = data
                gainarrayx[loop][bit] = data[0] / zarray[0]
                gainarrayy[loop][bit] = data[1] / zarray[1]

    if BIGDAS:
        gainx = numpy.median(gainarrayx, axis=0)
        gainy = numpy.median(gainarrayy, axis=0)  # Median across all the loops, to get rid of RFI

        now = time.ctime()
        hdu = fits.PrimaryHDU()
        hdu.data = gainx
        hdu.header['TELESCOP'] = "EDA MWA BF delay vs gain test"
        hdu.header['DATE'] = now
        hdu.writeto('/tmp/eda_gain_stg1_x.fits', clobber=True)
        hdu.data = gainy
        hdu.writeto('/tmp/eda_gain_stg1_y.fits', clobber=True)


def dokaelusgaintest():
    """Sweep the Kaelus (2nd stage) BF through delays of 0,1,2,4,8,16,32,64 and collect power data to see the
       relation between Kaelus delay line used, and output power. Keep the MWA delays the same.

       Note that kaeslave.py adds 128 to the delays it receives, so we need to send -128, -127, -126, -124, -120, etc

       NOTE - this will only work when run on 'bigdas', where live spectrum data is written to /tmp every second.
    """
    HEXD = ['0', '1', '2', '3', '4', '5', '6', '7', '8', '9', 'A', 'B', 'C', 'D', 'E', 'F']
    RAWDELAYS = [0, 1, 2, 4, 8, 16, 32, 64]

    if BIGDAS:
        gainarrayx = numpy.zeros(shape=(NUMLOOPS, 8, 32768))
        gainarrayy = numpy.zeros(shape=(NUMLOOPS, 8, 32768))
        zarray = numpy.zeros(shape=(2, 32768))

    delays = {}
    for b in HEXD:
        delays[b] = {}
        for d in HEXD:
            delays[b][d] = -16  # An offset of 16 is added to all delays, so this will become 0 (disabled)
    delays['K'] = {}  # An extra beamformer delay dict is added for the Kaelus beamformer (2nd stage)
    for d in HEXD:
        delays['K'][d] = -128  # An offset of 128 is added to all delays, so this will become 0

    print("Setting raw MWA delays to 0")
    stime = int(time.time() + 1)
    values = {253:{'X':(None, None, 0.0, 0.0, delays),
                   'Y':(None, None, 0.0, 0.0, delays)
                   }
              }
    try:
        for clientid, proxy in bfproxies.items():
            proxy.notify(obsid=0, starttime=stime, stoptime=stime + 8, clientid=clientid, rclass='pointing',
                         values=values)
    except AssertionError:
        print("Pointing error - aborting")
        return

    print("Starting run of %d loops." % NUMLOOPS)
    for loop in range(NUMLOOPS):
        print("  %10.4f: Starting loop %d" % (time.time(), loop))
        for bit in range(6):
            for d in HEXD:
                delays['K'][d] = RAWDELAYS[bit] - 128  # An offset of 128 is added to all delays in kaeslave.py
            print("    %10.4f: Setting Kaelus raw delays to %d" % (time.time(), RAWDELAYS[bit]))
            stime = int(time.time() + 1)
            values = {253:{'X':(None, None, 0.0, 0.0, delays),
                           'Y':(None, None, 0.0, 0.0, delays)
                           }
                      }
            try:
                kproxy.notify(obsid=0, starttime=stime, stoptime=stime + 8, clientid='Kaelus', rclass='pointing', values=values)
            except AssertionError:
                print("Pointing error - aborting")
                return

            time.sleep(8)

            if BIGDAS:
                data, dtime = getdata()
                if data is None:
                    print("No data - aborting")
                    return
                if (time.time() - dtime) > 4:
                    print("Stale data - aborting")
                    return
                if bit == 0:
                    zarray = data
                gainarrayx[loop][bit] = data[0] / zarray[0]
                gainarrayy[loop][bit] = data[1] / zarray[1]

    if BIGDAS:
        gainx = numpy.median(gainarrayx, axis=0)
        gainy = numpy.median(gainarrayy, axis=0)  # Median across all the loops, to get rid of RFI

        now = time.ctime()
        hdu = fits.PrimaryHDU()
        hdu.data = gainx
        hdu.header['TELESCOP'] = "EDA Kaelus BF delay vs gain test"
        hdu.header['DATE'] = now
        hdu.writeto('/tmp/eda_gain_stg2_x.fits', clobber=True)
        hdu.data = gainy
        hdu.writeto('/tmp/eda_gain_stg2_y.fits', clobber=True)


def dohyda():
    track_radec(ra=(9 + 18.0 / 60 + 6.0 / 3600) * 15,
                dec=(-12 - 5.0 / 60 - 44.0 / 3600),
                interval=options.track_interval,
                total_track_time=options.total_track_time)


def do3c444():
    track_radec(ra=(22.0 + 14.0 / 60 + 26.0 / 3600) * 15,
                dec=(-17.0 - 1.0 / 60 - 36.0 / 3600),
                interval=options.track_interval,
                total_track_time=options.total_track_time)


def docena():
    track_radec(ra=(13.0 + 25.0 / 60 + 28.0 / 3600) * 15,
                dec=(-43.0 - 1.0 / 60 - 9.0 / 3600),
                interval=options.track_interval,
                total_track_time=options.total_track_time)


def dopowertest(az=0.0, el=90.0, ra=None, dec=None):
    """Find the ratio between power at the given coordinates and power at the zenith

       NOTE - this will only work when run on 'bigdas', where live spectrum data is written to /tmp every second.
    """
    if not BIGDAS:
        print("Needs to run on 'bigdas' host, exiting.")
        return
    gainarrayx = numpy.zeros(shape=(NUMLOOPS, 32768))
    gainarrayy = numpy.zeros(shape=(NUMLOOPS, 32768))
    zarray = numpy.zeros(shape=(2, 32768))
    print("Starting run of %d loops." % NUMLOOPS)
    for loop in range(NUMLOOPS):
        print("  %10.4f: Starting loop %d" % (time.time(), loop))

        point_azel(az=0, el=90)  # Point to zenith
        time.sleep(8)

        data, dtime = getdata()
        if data is None:
            print("No data - aborting")
            return
        if (time.time() - dtime) > 4:
            print("Stale data - aborting")
            return

        zarray = data

        dopoint(az=az, el=el, ra=ra, dec=dec)
        time.sleep(8)

        data, dtime = getdata()
        if data is None:
            print("No data - aborting")
            return
        if (time.time() - dtime) > 4:
            print("Stale data - aborting")
            return

        gainarrayx[loop] = data[0] / zarray[0]
        gainarrayy[loop] = data[1] / zarray[1]

    print("Pointing back at zenith.")
    point_azel(az=0, el=90)
    gainx = numpy.median(gainarrayx, axis=0)
    gainy = numpy.median(gainarrayy, axis=0)  # Median across all the loops, to get rid of RFI

    outx = []
    outy = []
    for chan in range(0, 32768, 3277):
        outx.append(float(gainx[chan:chan + 3277].sum() / 3277.0))
        outy.append(float(gainy[chan:chan + 3277].sum() / 3277.0))
    print("Freq:\t" + '\t'.join(['%5.1f' % ((chan + 1638.0) / 100.0) for chan in range(0, 32768, 3277)]))
    print("Xpol:\t" + '\t'.join(['%6.5g' % v for v in outx]))
    print("Ypol:\t" + '\t'.join(['%6.5g' % v for v in outy]))


def set_onlybfs(onlybfs):
    print("Setting onlybfs global to %s" % onlybfs)
    kproxy.onlybfs(bfids=onlybfs)
    for proxy in bfproxies.values():
        proxy.onlybfs(bfids=onlybfs)


def init():
    """
       Create Pyro4 proxy objects for the PointingSlave objects on eda1com, eda2com, and the kaelus controller.
    """
    global kproxy, bfproxies
    kproxy = Pyro4.Proxy(KURL)
    bfproxies = {}
    for clientid, url in BURLS.items():
        bfproxies[clientid] = Pyro4.Proxy(url)


if __name__ == '__main__':
    init()
    usage = "Usage: %prog <options> <coords> where <coords> are either an az/el or an ra/dec\n"
    usage += "        With no arguments, the status and last pointing data is returned from each client."
    parser = optparse.OptionParser(usage=usage)
    parser.add_option('--image', dest='image', action='store_true', default=False,
                      help='Take drifscan image from 20d north to 20d south. East west ' +
                           'span is given by the loops argument. All other arguments ignored.')
    parser.add_option('--cube', dest='cube', action='store_true', default=False,
                      help='Like "--image", but instead of splitting into three bands, save ' +
                           'a FITS cube, with a full 327.68MHz of bandwidth. The output ' +
                           'file will be very large...')
    parser.add_option('--az', '-a', dest='az', help="Azimuth in degrees", default=None)
    parser.add_option('--el', '-e', dest='el', help="Elevation in degrees", default=None)
    parser.add_option('--ra', '-r', dest='ra', help="RA in degrees", default=None)
    parser.add_option('--dec', '-d', dest='dec', help="Dec in degrees", default=None)
    parser.add_option('--cx', dest='cx', help="E/W offset for delay center in m, relative to geometric centre of EDA",
                      default=0.0)
    parser.add_option('--cy', dest='cy', help="N/S offset for delay center in m, relative to geometric centre of EDA",
                      default=0.0)
    parser.add_option('--track_interval', '-i', dest='track_interval',
                      help="Tracking interval [default %default seconds]", default=120)
    parser.add_option('--track_time', '-t', '--total_track_time', dest='total_track_time',
                      help="Total tracking time in seconds default should be infinity [default one year = %default seconds]",
                      default=31536000)
    parser.add_option('--onlybfs', '-o',
                      dest='onlybfs',
                      help="One or more hex digits (0-F) in a single string, meaning turn off " +
                           "all but those MWA beamformer, or ALL to turn them all on. The EDA stays " +
                           "in this state until changed with another 'edacmd --onlybfs=' call",
                      default=None)
    parser.add_option('--loops', '-l', dest='loops', help="number of loops to run", default=NUMLOOPS)
    parser.add_option('--zsweep', '-z', dest='zsweep',
                      help="Run zenith sweep forever",
                      default=False,
                      action='store_true')
    parser.add_option('--ptest', '-p', dest='ptest',
                      help="Find power ratio between this position and the zenith",
                      default=False,
                      action='store_true')
    parser.add_option('--follow', '-f', dest='start_tracking',
                      help="Start following the MWA pointings",
                      default=False,
                      action='store_true')
    parser.add_option('--nofollow', '-n', dest='stop_tracking',
                      help="Stop following the MWA pointings",
                      default=False,
                      action='store_true')

    (options, args) = parser.parse_args()
    NUMLOOPS = int(options.loops)
    az = el = ra = dec = None
    if options.az and options.el:
        az = float(options.az)
        el = float(options.el)
    elif options.ra and options.dec:
        ra = float(options.ra)
        dec = float(options.dec)

    if options.image or options.cube:
        print("Collecting drift scan image for %d seconds, all other arguments ignored:" % (NUMLOOPS * 240))
        if options.cube:
            print("Saving image as FITS cube in /tmp/eda_cube.fits")
        else:
            print("Saving three fits images as /tmp/eda_image_[R,G,B].fits")
        tstate = is_tracking()
        if tstate:
            stop_tracking()
            time.sleep(5)
        doimage(cube=options.cube)
        if tstate:
            start_tracking()
        sys.exit()

    if options.onlybfs:
        if options.onlybfs.upper() == 'ALL':
            onlybfs = None
        else:
            onlybfs = []
            for bfid in options.onlybfs:
                if bfid.upper() in HEXD:
                    onlybfs.append(bfid.upper())
                else:
                    print("Invalid BF id passed to --onebf, must be 'ALL' or a string of one or more hex digits")
                    sys.exit()
        set_onlybfs(onlybfs)

    if options.cx or options.cy:
        try:
            cpos = (float(options.cx), float(options.cy), 0.0)
        except ValueError:
            cpos = None
            print("Invalid centre position cx=%s, cy=%s given" % (options.cx, options.cy))
            sys.exit()
        if cpos is not None:
            print("Setting centre position global to %s" % str(cpos))
            kproxy.set_cpos(cpos=cpos)
            for proxy in bfproxies.values():
                proxy.set_cpos(cpos=cpos)

    if options.start_tracking:
        start_tracking()

    if options.stop_tracking:
        stop_tracking()

    if options.ptest and ((az is not None) or (ra is not None)):  # Asked for a power test, and we have coordinates
        dopowertest(az=az, el=el, ra=ra, dec=dec)
    elif options.zsweep:
        zenith_sweep()
    elif ra is not None:
        track_radec(ra=ra, dec=dec, interval=options.track_interval, total_track_time=options.total_track_time)
    elif az is not None:
        point_azel(az=az, el=el)

    print_status()
