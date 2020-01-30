#!/usr/bin/env python

import datetime
import glob
import os
import sys
import time
import warnings

from astropy.io import fits

import numpy

warnings.simplefilter(action='ignore')
import Pyro4

import matplotlib

matplotlib.use('Agg')
from matplotlib import pyplot as plt

import pointing

"""
  Tests all EDA dipoles by stepping through all 256 dipoles one by one.
"""

TILEID = 0

MAXAGE = 60
HEXD = ['0', '1', '2', '3', '4', '5', '6', '7', '8', '9', 'A', 'B', 'C', 'D', 'E', 'F']

KURL = 'PYRO:Kaelus@10.128.2.51:19987'
BURLS = {'eda1com':'PYRO:eda1com@10.128.2.63:19987', 'eda2com':'PYRO:eda2com@10.128.2.65:19987'}

XTICKS = [5000, 10000, 15000, 20000, 25000, 30000]
XLABELS = ['50', '100', '150', '200', '250', '300']

YTICKS = [10, 20, 30, 40, 50, 60]
YLABELS = ['10', '20', '30', '40', '50', '60']


def getdata():
    """Returns a numpy array containing the most recently written EDA spectrum.
       Return None if the most recent file is older than MAXAGE seconds.
    """
    flist = glob.glob('/tmp/livespec_??.fits')
    fdict = {}
    for fname in flist:
        fdict[os.path.getmtime(fname)] = fname
    tlist = list(fdict.keys())
    tlist.sort()
    dtime = tlist[-2]  # Pick the second last one, in case the latest one is still being written.
    fname = fdict[dtime]
    if (time.time() - dtime) > MAXAGE:
        return None  # All files are too old

    f = fits.open(fname)
    return f[0].data, dtime


def freqbin(indat=None):
    """Takes a numpy array (shape=(32768,)) and sums groups of 128 channels to
       produce an output array of shape (256,)
    """
    odat = numpy.zeros(shape=(256,), dtype=numpy.float32)
    for i in range(256):
        odat[i] = indat[(i * 128):(i * 128 + 128)].sum()
    odat.shape = (256, 1, 1)
    return odat


def set_onlybfs(onlybfs):
    print("Setting onlybfs global to %s" % onlybfs)
    kproxy.onlybfs(bfids=onlybfs)
    for proxy in bfproxies.values():
        proxy.onlybfs(bfids=onlybfs)


if __name__ == '__main__':
    az, el, offsets, idelays, errors = None, None, None, None, None
    if len(sys.argv) == 3:  # If given an az/el, use incremental mode, adding one dipole at a time.
        az = float(sys.argv[1])
        el = float(sys.argv[2])
        offsets = pointing.getOffsets(dipolefile='/usr/local/etc/locations.txt')
        idelays, errors = pointing.calc_delays(offsets=offsets, az=az, el=el, strict=False, verbose=True,
                                               clipdelays=True,
                                               cpos=(0.0, 0.0, 0.0))
    kproxy = Pyro4.Proxy(KURL)
    bfproxies = {}
    for clientid, url in BURLS.items():
        bfproxies[clientid] = Pyro4.Proxy(url)

    xarray = numpy.zeros(shape=(16, 16, 32768))
    yarray = numpy.zeros(shape=(16, 16, 32768))
    starttime = time.time()
    # Loop over all the dipoles to test, one by one:
    for bfid in HEXD:
        if (az is None) or (el is None):
            set_onlybfs([bfid])
        else:
            set_onlybfs(HEXD[:HEXD.index(bfid) + 1])
        for dipid in HEXD:
            delays = {}
            if (az is None) or (el is None):
                print("Testing dipole %s" % bfid + dipid)
                # Create an empty delays structure
                for b in HEXD:
                    delays[b] = {}
                    for d in HEXD:
                        delays[b][d] = 16  # An offset of 16 is added to all delays, so this will become 32 (disabled)
                delays['K'] = {}  # An extra beamformer delay dict is added for the Kaelus beamformer (2nd stage)
                for d in HEXD:
                    delays['K'][d] = 0  # An offset of 128 is added to all delays, so this will become 128

                delays[bfid][dipid] = 0  # Flag exactly one dipole as active, the one we are testing this time
            else:
                print("Adding dipole %s" % bfid + dipid)
                for b in HEXD:
                    delays[b] = {}
                    for d in HEXD:
                        if (b < bfid) or ((b == bfid) and (d <= dipid)):
                            delays[b][d] = idelays[b][d]
                        else:
                            delays[b][
                                d] = 16  # An offset of 16 is added to all delays, so this will become 32 (disabled)
                delays['K'] = idelays['K']

            stime = int(time.time() + 2)
            values = {TILEID:{'X':(None, None, 0.0, 0.0, delays),
                              'Y':(None, None, 0.0, 0.0, delays)
                              }
                      }
            kproxy.notify(obsid=0, starttime=stime, stoptime=stime + 8, clientid='Kaelus', rclass='pointing',
                          values=values)
            for clientid, proxy in bfproxies.items():
                proxy.notify(obsid=0, starttime=stime, stoptime=stime + 8, clientid=clientid, rclass='pointing',
                             values=values)

            time.sleep(8)
            data, dtime = getdata()
            if (time.time() - dtime) > 4:
                print("Stale data found - %5.2f seconds." % (time.time() - dtime))
            bfindex = int(bfid, 16)
            dipindex = int(dipid, 16)

            xarray[bfindex, dipindex] = data[0]
            yarray[bfindex, dipindex] = data[1]

    xrange = numpy.arange(32768, dtype=numpy.float32)
    for bfid in HEXD:
        bfindex = int(bfid, 16)
        f, axarr = plt.subplots(4, 4, sharex='col', sharey='row', figsize=(9, 9), dpi=150)
        for dipid in HEXD:
            dipindex = int(dipid, 16)
            x, y = divmod(dipindex, 4)
            ax = axarr[x, y]
            ax.set_ylim(bottom=10, top=70)
            ax.set_xticks(XTICKS)
            ax.set_xticklabels(XLABELS, fontsize='xx-small')
            ax.set_yticks(YTICKS)
            ax.set_yticklabels(YLABELS, fontsize='xx-small')
            ax.set_title("BF %s Dip %s" % (bfid, dipid), fontsize='small')
            ax.plot(xrange, numpy.log10(xarray[bfindex, dipindex] + 1) * 10, 'b', label='X')
            ax.plot(xrange, numpy.log10(yarray[bfindex, dipindex] + 1) * 10, 'g', label='Y')
            ax.legend(fontsize='xx-small')
        plt.savefig('BF-%s.png' % bfid, dpi=f.dpi)

    outx = numpy.zeros(shape=(256, 256))
    outy = numpy.zeros(shape=(256, 256))
    for bfindex in range(16):
        for dipindex in range(16):
            outx[bfindex * 16 + dipindex, :] = freqbin(xarray[bfindex, dipindex])[:, 0, 0]
            outy[bfindex * 16 + dipindex, :] = freqbin(yarray[bfindex, dipindex])[:, 0, 0]
    tstart = datetime.datetime.fromtimestamp(starttime).isoformat()
    tend = datetime.datetime.fromtimestamp(time.time()).isoformat()
    hdu = fits.PrimaryHDU()
    hdu.header['TELESCOP'] = "EDA dipole test"
    hdu.header['TSTART'] = tstart
    hdu.header['TEND'] = tend
    if (az is not None) and (el is not None):
        hdu.header['AZ'] = az
        hdu.header['EL'] = el
    hdu.header['CRPIX1'] = 128
    hdu.header['CRVAL1'] = 128
    hdu.header['CDELT1'] = 1
    hdu.header['CTYPE1'] = 'Dipole'
    hdu.header['CUNIT1'] = 'Dipole'
    hdu.header['CRPIX2'] = 128
    hdu.header['CRVAL2'] = 163.84
    hdu.header['CDELT2'] = 1.28
    hdu.header['CTYPE2'] = 'FREQ'
    hdu.header['CUNIT2'] = 'MHz'

    hdu.data = outx
    hdu.writeto('diptest_X.fits', clobber=True)
    hdu.data = outy
    hdu.writeto('diptest_Y.fits', clobber=True)

    # We've finished the test, so point the EDA back at the zenith
    for b in HEXD:  # An extra beamformer 'K' to hold Kaelus delays
        delays[b] = {}
        for d in HEXD:
            delays[b][d] = 0  # An offset of 16 is added to all delays, so this will become 16
    for d in HEXD:
        delays['K'][d] = 0  # An offset of 128 is added to all delays, so this will become 128

    stime = int(time.time() + 1)
    values = {TILEID:{'X':(None, None, 0.0, 0.0, delays),
                      'Y':(None, None, 0.0, 0.0, delays)
                      }
              }
    kproxy.notify(obsid=0, starttime=stime, clientid='Kaelus', rclass='pointing', values=values)
    for clientid, proxy in bfproxies.items():
        proxy.notify(obsid=0, starttime=stime, clientid=clientid, rclass='pointing', values=values)

    print("Test finished, EDA pointed to zenith.")
