#!/usr/bin/env python

"""AAVS station layout model, with APIU

   Command line utility to render 3D visualisations of dipole delays for MWA tile and EDA station
   pointing. Uses the same delay calculation code as the MWA and EDA control systems.

   Written by Andrew Williams (Andrew.Williams@curtin.edu.au)

   Controls - Right-click and drag to spin the camera around the center left/right and up/down.
            - Both-buttons click and drag up and down to change zoom.

   Two data files (locations.txt, gridpoints3.pickle) need to be in the same directory as this script,
       and it also depends on the EDA pointing library (pointing.py).
"""

import pickle
import math
import optparse
import sys

import vpython
from vpython import color
from vpython import vector as v

import pointing

ONLYBFs = None
STRICT = False
CPOS = (0.0, 0.0, 0.0)

EDAOFFSETS = pointing.getOffsets()

TILEDIPSEP = 1.10  # dipole separations in meters for an MWA tile
TILEOFFSETS = [(-1.5, 1.5), (-0.5, 1.5), (0.5, 1.5), (1.5, 1.5),
               (-1.5, 0.5), (-0.5, 0.5), (0.5, 0.5), (1.5, 0.5),
               (-1.5, -0.5), (-0.5, -0.5), (0.5, -0.5), (1.5, -0.5),
               (-1.5, -1.5), (-0.5, -1.5), (0.5, -1.5), (1.5, -1.5)]
TILEDELAYSTEP = 435  # MWA beamformer delay step, in picoseconds

g = open('gridpoints3.pickle', 'rb')
GRID_POINTS = pickle.load(g, encoding='bytes')
g.close()


def getdipole(cpos=None, dlabel=None):
    """Creates and returns a list of 3D objects making up a single MWA dipole. If cpos
       is given, it must be a vpython.vector object used for the center of the dipole (actually
       the point on the ground directly underneath the LNA tube). If dlabel is given, it must
       be a one or two letter label to draw on the top of the LNA tube."""
    width = 0.35  # Center to edge of batwing
    height = 0.4  # Top of batwing corner to ground
    standoff = 0.1  # ground to bottom of batwing triangle
    cylen = 0.15  # length of LNA cylinder
    cydia = 0.15  # diameter of LNA cylinder
    cpoint = v(0, 0, (height / 2.0 + standoff))
    boxw = 0.02  # thickness of dipole arms
    tubeoff = standoff  # gap between bottom of wire tube and the ground
    if cpos is None:
        cpos = v(0, 0, 0)
    elif type(cpos) == tuple:
        cpos = v(cpos)

    xl = vpython.box(pos=v(-width, 0, (height + standoff) / 2) + cpos, axis=v(0, 0, 1), height=boxw, width=boxw,
                     length=height + boxw, color=vpython.color.gray(0.8))
    xlt = vpython.box(pos=v(0, 0, cpoint.z) + cpos, axis=(v(width, 0, standoff) - v(-width, 0, height)), height=boxw,
                      width=boxw, color=vpython.color.gray(0.8))
    xlb = vpython.box(pos=v(0, 0, cpoint.z) + cpos, axis=(v(width, 0, height) - v(-width, 0, standoff)), height=boxw,
                      width=boxw, color=vpython.color.gray(0.8))
    xr = vpython.box(pos=v(width, 0, (height + standoff) / 2) + cpos, axis=v(0, 0, 1), height=boxw, width=boxw,
                     length=height + boxw, color=vpython.color.gray(0.8))

    yl = vpython.box(pos=v(0, -width, (height + standoff) / 2) + cpos, axis=v(0, 0, 1), height=boxw, width=boxw,
                     length=height + boxw, color=vpython.color.gray(0.8))
    ylt = vpython.box(pos=v(0, 0, cpoint.z) + cpos, axis=(v(0, width, standoff) - v(0, -width, height)), height=boxw,
                      width=boxw, color=vpython.color.gray(0.8))
    ylb = vpython.box(pos=v(0, 0, cpoint.z) + cpos, axis=(v(0, width, height) - v(0, -width, standoff)), height=boxw,
                      width=boxw, color=vpython.color.gray(0.8))
    yr = vpython.box(pos=v(0, width, (height + standoff) / 2) + cpos, axis=v(0, 0, 1), height=boxw, width=boxw,
                     length=height + boxw, color=vpython.color.gray(0.8))

    lna = vpython.cylinder(pos=v(0, 0, cpoint.z - cylen / 2) + cpos, axis=v(0, 0, cylen), radius=cydia / 2.0,
                           color=color.white)
    tube = vpython.cylinder(pos=v(0, 0, tubeoff) + cpos, radius=boxw / 2.0, axis=v(0, 0, cpoint.z - standoff),
                            color=color.white)
    olist = [xl, xlt, xlb, xr, yl, ylt, ylb, yr, lna, tube]
    if dlabel and showlabels:
        lnalabel = vpython.text(text=dlabel, pos=lna.pos + lna.axis + v(-0.035 * len(dlabel), -0.035, 0), height=0.07,
                                depth=0.01, color=color.black)
        olist.append(lnalabel)
    return olist


def geteda(offsets=EDAOFFSETS):
    """Create and return a list of 3D objects making up the entire 256 element Engineering
       Development Array, using the dipole locations in locations.txt
    """
    gp = vpython.box(pos=v(0, 0, 0), axis=v(0, 0, 1), height=40.0, width=40.0, length=0.05, color=color.gray(0.5))
    olist = [gp]
    for bfid in pointing.HEXD:
        for dipid in pointing.HEXD:
            dlist = getdipole(cpos=v(*offsets[bfid][dipid]), dlabel=bfid + dipid)
            olist += dlist
    eaxis = vpython.arrow(pos=v(0, 0, 0), axis=v(20, 0, 0), color=color.blue, shaftwidth=0.1, fixedwidth=True,
                          opacity=0.2)
    naxis = vpython.arrow(pos=v(0, 0, 0), axis=v(0, 20, 0), color=color.blue, shaftwidth=0.1, fixedwidth=True,
                          opacity=0.2)
    eaxislabel = vpython.text(text='E', pos=v(20, 0, 0.2), height=0.5, depth=0.1, color=color.blue, opacity=0.2)
    naxislabel = vpython.text(text='N', pos=v(0, 20, 0.2), height=0.5, depth=0.1, color=color.blue, opacity=0.2)
    olist += [eaxis, naxis, eaxislabel, naxislabel]
    return olist


def gettile(offsets=None, cpos=None):
    """Create and return a list of 3D objects making up a single MWA tile. If cpos is given, it's used
       as the center position for the whole tile (if you want to show multiple tiles).
    """
    if offsets is None:
        offsets = TILEOFFSETS

    if cpos is None:
        cpos = v(0, 0, 0)
    elif type(cpos) == tuple:
        cpos = v(cpos)

    eaxis = vpython.arrow(pos=v(0, 0, 0), axis=v(3, 0, 0), color=color.blue, shaftwidth=0.1, fixedwidth=True,
                          opacity=0.2)
    naxis = vpython.arrow(pos=v(0, 0, 0), axis=v(0, 3, 0), color=color.blue, shaftwidth=0.1, fixedwidth=True,
                          opacity=0.2)
    eaxislabel = vpython.text(text='E', pos=v(3, 0, 0.2), height=0.5, depth=0.1, color=color.blue, opacity=0.2)
    naxislabel = vpython.text(text='N', pos=v(0, 3, 0.2), height=0.5, depth=0.1, color=color.blue, opacity=0.2)

    gp = vpython.box(pos=v(0, 0, 0) + cpos, axis=v(0, 0, 1), height=5.0, width=5.0, length=0.05, color=color.gray(0.5))
    olist = [eaxis, naxis, eaxislabel, naxislabel, gp]
    letters = 'ABCDEFGHIJKLMNOP'
    for i in range(16):
        xy = offsets[i]
        p = v(xy[0], xy[1], 0) + cpos
        dlist = getdipole(cpos=p, dlabel=letters[i])
        olist += dlist
    return olist


def getedadelays(offsets=EDAOFFSETS, az=0.0, el=90.0):
    """Create and return 3D objects representing the pointing delays for all 256 EDA dipoles.
       They are represented by arrows for each dipole, with a length equal to that dipoles delay value
       times the speed of light, and all point at the specified az/el direction. Positive delays
       are represented by arrows below the ground plane, negative delays are represented by arrows
       the ground plane.

       Two sets of delays are shown - the ideal gemetric delays are shown in white, and the actual
       integer delays (the sum of the first and second stage delays) are shown in green.

       A tuple of (parrow, ilist, alist) is returned, where 'parrow' is a single, long, yellow arrow
       from the centre of the EDA showing the pointing direction, ilist is the list of 'ideal'
       delay arrows, and 'alist' is the list of 'actual' delay arrows. They are returned
       separately, so the 'visible' attribute on each set of arrows can be set as needed.
       """
    if ONLYBFs is not None:
        clipdelays = False
    else:
        clipdelays = True
    idelays, diagnostics = pointing.calc_delays(offsets=offsets, az=az, el=el, strict=STRICT, verbose=True,
                                                clipdelays=clipdelays, cpos=CPOS)
    if diagnostics is not None:
        delays, delayerrs, sqe, maxerr, offcount = diagnostics
        if offcount > 0:
            print('Elevation low - %d dipoles disabled because delays were too large to reach in hardware.' % offcount)
    else:
        delays, delayerrs, sqe, maxerr, offcount = None, None, None, None, None
    if idelays is None:
        print("Error calculating delays for az=%s, el=%s" % (az, el))
        return []

    if ONLYBFs is None:
        offcount = 0
        for bfid in pointing.HEXD:
            for dipid in pointing.HEXD:
                if idelays[bfid][dipid] == 16:  # disabled
                    offcount += 1
    elif len(
            ONLYBFs) == 1:  # We only have one beamformer enabled, so disable all other dipoles and normalise remaining to the minimum delay on that BF
        offcount = 240
        print(
                    "Only one first stage beamformer enabled (%s) and delays normalised to the minimum value, other 240 dipoles are disabled!" % ONLYBFs)
        for bfid in pointing.HEXD:
            if bfid in ONLYBFs:  # If this is one of the beamformer we want to point:
                mind = min(idelays[bfid].values())  # Find the smallest delay in this BF
                for dipid in pointing.HEXD:
                    idelays[bfid][dipid] -= (
                                mind + 16)  # Subtract the minimum delay from the given delay, then subtract 16
                    if (idelays[bfid][dipid] < -16) or (idelays[bfid][dipid] > 15):
                        idelays[bfid][dipid] = 16  # Disabled
                        offcount += 1
            else:
                for dipid in pointing.HEXD:
                    idelays[bfid][dipid] = 16  # Disable all dipoles on other beamformers
    else:
        offcount = 0
        print("Only some first stage beamformer enabled (%s), other %d dipoles are disabled!" % (ONLYBFs, offcount))
        for bfid in pointing.HEXD:
            for dipid in pointing.HEXD:
                if bfid in ONLYBFs:
                    if (idelays[bfid][dipid] < -16) or (idelays[bfid][dipid] > 15):
                        idelays[bfid][dipid] = 16  # Disabled
                        offcount += 1
                else:
                    idelays[bfid][dipid] = 16  # Disabled
                    offcount += 1

    north = v(0, 1, 0)  # Due north, elevation 0 degrees
    t1 = vpython.rotate(north, angle=(el * math.pi / 180.0),
                        axis=v(1, 0, 0))  # Rotate up (around E/W axis) by 'el' degrees
    pvector = vpython.rotate(t1, angle=(-az * math.pi / 180.0),
                             axis=v(0, 0, 1))  # Rotate clockwise by 'az' degrees around 'up' axis
    parrow = vpython.arrow(pos=v(0, 0, 0), axis=pvector, color=color.yellow, length=20.0, shaftwidth=1.0, visible=True)

    ilist = []
    alist = []
    dlist = []
    for bfid in pointing.HEXD:
        for dipid in pointing.HEXD:
            # Arrow lengths are negative if delays are positive, and vice/versa
            if delays:
                idealdelay = delays[bfid][dipid] * pointing.C
                ilist.append(vpython.arrow(pos=v(*offsets[bfid][dipid]),
                                           axis=pvector,
                                           length=-idealdelay,
                                           color=color.white,
                                           shaftwidth=0.2,
                                           visible=ivis))
                if idelays[bfid][dipid] != 16:  # If this dipole isn't disabled
                    actualdelay = ((idelays[bfid][dipid] * pointing.MSTEP) + (idelays['K'][bfid] * pointing.KSTEP)) * pointing.C
                    alist.append(vpython.arrow(pos=v(*offsets[bfid][dipid]),
                                               axis=pvector,
                                               length=-actualdelay,
                                               color=color.green,
                                               shaftwidth=0.2,
                                               visible=avis))
                    delaydifference = idealdelay - actualdelay
                    dlist.append(vpython.arrow(pos=v(*offsets[bfid][dipid]),
                                               axis=pvector,
                                               length=100 * delaydifference,
                                               color=color.red,
                                               shaftwidth=0.2,
                                               visible=dvis))
    return parrow, ilist, alist, dlist


def get_sweet_delays(az=0.0, el=0.0, maxsigma=None):
    """
    (Written by David Kaplan, copied with minor changes from single_observation.py)

    Returns the grid pointing that is closest to the requested position (az,el) in degrees
    along with the distance to that point.  In addition, filtering can be done on the "sigma" column
    with a maximum allowed value specified.

    :param az: target Az (deg)
    :param el: target El (deg)
    :param maxsigma: maximum sigma or None
    :return: azimuth, elevation, delays
    """

    closest = None
    # in degrees
    closest_distance = 180
    for g in GRID_POINTS:
        number, azimuth, elevation, sigma, delays = g
        if (maxsigma is None or sigma <= maxsigma):
            x1 = math.cos(az * math.pi / 180.0) * math.cos(el * math.pi / 180.0)
            y1 = math.sin(az * math.pi / 180.0) * math.cos(el * math.pi / 180.0)
            z1 = math.sin(el * math.pi / 180.0)
            x2 = math.cos(azimuth * math.pi / 180.0) * math.cos(elevation * math.pi / 180.0)
            y2 = math.sin(azimuth * math.pi / 180.0) * math.cos(elevation * math.pi / 180.0)
            z2 = math.sin(elevation * math.pi / 180.0)
            arg = x1 * x2 + y1 * y2 + z1 * z2
            if (arg > 1):
                arg = 1
            if (arg < -1):
                arg = -1
            theta = math.acos(arg) * 180.0 / math.pi
            if (theta < closest_distance):
                closest_distance = theta
                closest = g
    if (closest is None):
        if (maxsigma is None):
            print('No grid pointings matched')
        else:
            print('No grid pointings matched grid with maxsigma=%.1e' % maxsigma)
        return None, None, None
    number, azimuth, elevation, sigma, delays = closest
    return azimuth, elevation, delays


def gettiledelays(cpos=None, az=0.0, el=90.0):
    """
       Copied from function calc_delays in obssched/pycontroller.py, with
       code to create the actual arrow objects added. If cpos is given, it's
       used as the tile centre position - use this when showing more than one
       tile.

       Algorithm copied from ObsController.java and converted to Python

       This function takes in an azimuth and zenith angle as
       inputs and creates and returns a 16-element byte array for
       delayswitches which have values corresponding to each
       dipole in the tile having a maximal coherent amplitude in the
       desired direction.

       This will return null if the inputs are
       out of physical range (if za is bigger than 90) or
       if the calculated switches for the dipoles are out
       of range of the delaylines in the beamformer.

       azimuth of 0 is north and it increases clockwise
       zenith angle is the angle down from zenith
       These angles should be given in degrees

      Layout of the dipoles on the tile:

                 N

           0   1   2   3

           4   5   6   7
      W                    E
           8   9   10  11

           12  13  14  15

                 S
    """
    if cpos is None:
        cpos = v(0, 0, 0)
    elif type(cpos) == tuple:
        cpos = v(cpos)

    # Find the delay values for the nearest sweetspot, to use for green arrows:
    sweetaz, sweetel, sweetdelays = get_sweet_delays(az=az, el=el)

    # Calculate the geometric delays for the ax/el given, without using sweetspot
    dip_sep = 1.10  # dipole separations in meters
    delaystep = 435.0  # Delay line increment in picoseconds
    maxdelay = 31  # Maximum number of deltastep delays
    c = 0.000299798  # C in meters/picosecond
    dtor = math.pi / 180.0  # convert degrees to radians
    # define zenith angle
    za = 90 - el

    # Define arrays to hold the positional offsets of the dipoles
    xoffsets = [0.0] * 16  # offsets of the dipoles in the W-E 'x' direction
    yoffsets = [0.0] * 16  # offsets of the dipoles in the S-N 'y' direction
    delays = [0.0] * 16  # The calculated delays in picoseconds
    rdelays = [0] * 16  # The rounded delays in units of delaystep

    delaysettings = [0] * 16  # return values

    # Check input sanity
    if (abs(za) > 90):
        return None

        # Offsets of the dipoles are calculated relative to the
        # center of the tile, with positive values being in the north
        # and east directions

    xoffsets[0] = -1.5 * dip_sep
    xoffsets[1] = -0.5 * dip_sep
    xoffsets[2] = 0.5 * dip_sep
    xoffsets[3] = 1.5 * dip_sep
    xoffsets[4] = -1.5 * dip_sep
    xoffsets[5] = -0.5 * dip_sep
    xoffsets[6] = 0.5 * dip_sep
    xoffsets[7] = 1.5 * dip_sep
    xoffsets[8] = -1.5 * dip_sep
    xoffsets[9] = -0.5 * dip_sep
    xoffsets[10] = 0.5 * dip_sep
    xoffsets[11] = 1.5 * dip_sep
    xoffsets[12] = -1.5 * dip_sep
    xoffsets[13] = -0.5 * dip_sep
    xoffsets[14] = 0.5 * dip_sep
    xoffsets[15] = 1.5 * dip_sep

    yoffsets[0] = 1.5 * dip_sep
    yoffsets[1] = 1.5 * dip_sep
    yoffsets[2] = 1.5 * dip_sep
    yoffsets[3] = 1.5 * dip_sep
    yoffsets[4] = 0.5 * dip_sep
    yoffsets[5] = 0.5 * dip_sep
    yoffsets[6] = 0.5 * dip_sep
    yoffsets[7] = 0.5 * dip_sep
    yoffsets[8] = -0.5 * dip_sep
    yoffsets[9] = -0.5 * dip_sep
    yoffsets[10] = -0.5 * dip_sep
    yoffsets[11] = -0.5 * dip_sep
    yoffsets[12] = -1.5 * dip_sep
    yoffsets[13] = -1.5 * dip_sep
    yoffsets[14] = -1.5 * dip_sep
    yoffsets[15] = -1.5 * dip_sep

    # First, figure out the theoretical delays to the dipoles
    # relative to the center of the tile

    # Convert to radians
    azr = az * dtor
    zar = za * dtor

    for i in range(16):
        # calculate exact delays in picoseconds from geometry...
        delays[i] = (xoffsets[i] * math.sin(azr) + yoffsets[i] * math.cos(azr)) * math.sin(zar) / c

    # Find minimum delay
    mindelay = min(delays)

    # Subtract minimum delay so that all delays are positive
    for i in range(16):
        delays[i] -= mindelay

    # Now minimize the sum of the deviations^2 from optimal
    # due to errors introduced when rounding the delays.
    # This is done by stepping through a series of offsets to
    # see how the sum of square deviations changes
    # and then selecting the delays corresponding to the min sq dev.

    # Go through once to get baseline values to compare
    bestoffset = -0.45 * delaystep
    minsqdev = 0

    for i in range(16):
        delay_off = delays[i] + bestoffset
        intdel = int(round(delay_off / delaystep))

        if (intdel > maxdelay):
            intdel = maxdelay

        minsqdev += math.pow((intdel * delaystep - delay_off), 2)

    minsqdev = minsqdev / 16

    offset = (-0.45 * delaystep) + (delaystep / 20.0)
    while offset <= (0.45 * delaystep):
        sqdev = 0
        for i in range(16):
            delay_off = delays[i] + offset
            intdel = int(round(delay_off / delaystep))

            if (intdel > maxdelay):
                intdel = maxdelay
            sqdev = sqdev + math.pow((intdel * delaystep - delay_off), 2)

        sqdev = sqdev / 16
        if (sqdev < minsqdev):
            minsqdev = sqdev
            bestoffset = offset

        offset += delaystep / 20.0

    for i in range(16):
        rdelays[i] = int(round((delays[i] + bestoffset) / delaystep))
        if (rdelays[i] > maxdelay):
            if (rdelays[i] > maxdelay + 1):
                return None  # Trying to steer out of range.
            rdelays[i] = maxdelay

    # Set the actual delays
    for i in range(16):
        delaysettings[i] = int(rdelays[i])

    if mode == 'EDA':
        parrowlen = 20.0
        parrowsw = 1.0
    else:
        parrowlen = 2.5
        parrowsw = 0.2

    north = v(0, 1, 0)  # Due north, elevation 0 degrees
    at1 = vpython.rotate(north, angle=(el * math.pi / 180),
                         axis=v(1, 0, 0))  # Rotate up (around E/W axis) by 'el' degrees
    apvector = vpython.rotate(at1, angle=(-az * math.pi / 180),
                              axis=v(0, 0, 1))  # Rotate clockwise by 'az' degrees around 'up' axis
    aarrow = vpython.arrow(pos=v(0, 0, 0), axis=apvector, color=color.white, length=parrowlen, shaftwidth=parrowsw,
                           visible=avis)

    if (sweetaz is not None) and (sweetel is not None):
        st1 = vpython.rotate(north, angle=(sweetel * math.pi / 180),
                             axis=v(1, 0, 0))  # Rotate up (around E/W axis) by 'el' degrees
        spvector = vpython.rotate(st1, angle=(-sweetaz * math.pi / 180),
                                  axis=v(0, 0, 1))  # Rotate clockwise by 'az' degrees around 'up' axis
        sarrow = vpython.arrow(pos=v(0, 0, 0), axis=spvector, color=color.green, length=parrowlen, shaftwidth=parrowsw,
                               visible=avis)
        alist = [sarrow]
    else:
        alist = []
        spvector = None

    ilist = [aarrow]
    dlist = []
    for i in range(16):
        # Arrow lengths are negative if delays are positive, and vice/versa
        idealdelay = delaysettings[i] * TILEDELAYSTEP * pointing.C
        dposx, dposy = TILEOFFSETS[i]
        dpos = v(dposx, dposy, 0) + cpos
        if sweetdelays:
            sweetdelay = sweetdelays[i] * TILEDELAYSTEP * pointing.C
            alist.append(vpython.arrow(pos=dpos, axis=spvector, length=-sweetdelay, color=color.green, shaftwidth=0.2,
                                       visible=avis))
        ilist.append(vpython.arrow(pos=dpos, axis=apvector, length=-idealdelay, color=color.white, shaftwidth=0.2, visible=avis))

    # Tiles have two pointing arrows, stored in the 'alist' and 'ilist', so return None for the first element.
    return None, ilist, alist, dlist


def processClick(event):
    """If the mouse is clicked or a key is pressed, process the results
    """
    global ilist, alist, dlist, az, el, ivis, avis, dvis
    try:  # Key pressed:
        s = event.key
        print(s)
        if (s == 'a') or (s == 's'):  # Toggle the visibility of the 'actual' delays
            avis = not avis
            for ob in alist:
                ob.visible = avis
        elif s == 'i':  # Toggle the visibility of the 'ideal' delays
            ivis = not ivis
            for ob in ilist:
                ob.visible = ivis
        elif s == 'd':
            dvis = not dvis
            for ob in dlist:
                ob.visible = dvis
        elif s == 'up':
            el += 5
            if el > 90:
                el = 90
            redraw_arrows()
        elif s == 'down':
            el -= 5
            if el < 0:
                el = 0
            redraw_arrows()
        elif s == 'left':
            az -= 10
            if az < 0:
                az += 360
            redraw_arrows()
        elif s == 'right':
            az += 10
            if az >= 360:
                az -= 360
            redraw_arrows()
        elif s == 'r':
            redraw_arrows()

    except AttributeError:  # Mouse clicked:
        pass


def redraw_arrows():
    global parrow, ilist, alist, dlist, az, el

    if mode == 'EDA':
        parrow.visible = False
    for ob in ilist:
        ob.visible = False
    for ob in alist:
        ob.visible = False
    for ob in dlist:
        ob.visible = False

    del ilist
    del alist
    del dlist
    del parrow

    if mode == 'EDA':
        result = getedadelays(az=az, el=el)
        if result is not None:
            parrow, ilist, alist, dlist = result
        else:
            parrow, ilist, alist, dlist = None, [], [], []
    else:
        result = gettiledelays(az=az, el=el)
        if result is not None:
            parrow, ilist, alist, dlist = result
        else:
            parrow, ilist, alist, dlist = None, [], [], []

    for ob in ilist:
        ob.visible = ivis
    for ob in alist:
        ob.visible = avis
    for ob in dlist:
        ob.visible = dvis

    print(az, el)


def show(sec=10):  # Animate scene for N seconds - use when importing library manually
    vpython.sleep(sec)


if __name__ == '__main__':
    usage = "Usage: %prog <options> \n"
    usage += "        With no arguments, the delay model for az=0, el=90 is shown."
    parser = optparse.OptionParser(usage=usage)
    parser.add_option('--tile', '-t', dest='tile', default=False, action='store_true',
                      help='Model pointing delays for a single MWA tile')
    parser.add_option('--eda', dest='eda', default=False, action='store_true',
                      help='Model pointing delays for the EDA (default)')
    parser.add_option('--labels', '-l', dest='labels', default=False, action='store_true',
                      help='Show dipole label letters on top of each LNA in EDA view (slow)')
    parser.add_option('--az', '-a', dest='az', help="Azimuth in degrees", default=0.0)
    parser.add_option('--el', '-e', dest='el', help="Elevation in degrees", default=90.0)
    parser.add_option('--cx', dest='cx', help="E/W offset for delay center in m, relative to geometric centre of EDA",
                      default=0.0)
    parser.add_option('--cy', dest='cy', help="N/S offset for delay center in m, relative to geometric centre of EDA",
                      default=0.0)
    parser.add_option('--onlybfs', '-o',
                      dest='onlybfs',
                      help="One or more hex digits (0-F) in a single string, meaning turn off " +
                           "all but those MWA beamformer, or ALL to turn them all on. The EDA stays " +
                           "in this state until changed with another 'edacmd --onlybfs=' call",
                      default=None)
    parser.add_option('--diffs', '-d', dest='diffs', default=False, action='store_true',
                      help="Show the differences between the ideal and actual delay values")
    (options, args) = parser.parse_args()

    mode = 'EDA'
    showlabels = False
    if options.tile:
        mode = 'TILE'
        showlabels = True
    elif options.labels:
        showlabels = True

    scene = vpython.canvas(width=1600, height=1000)
    scene.forward = v(0, 1, -1)
    scene.up = v(0, 0, 1)
    if mode == 'EDA':
        scene.range = 25
    else:
        scene.range = 5

    az = el = None
    if (options.az is not None) and (options.el is not None):
        az = float(options.az)
        el = float(options.el)

    if options.onlybfs:
        if options.onlybfs.upper() == 'ALL':
            ONLYBFs = None
        else:
            ONLYBFs = []
            for bfid in options.onlybfs:
                if bfid.upper() in pointing.HEXD:
                    ONLYBFs.append(bfid.upper())
                else:
                    print("Invalid BF id passed to --onebf, must be 'ALL' or a string of one or more hex digits")
                    sys.exit()

    if options.cx or options.cy:
        try:
            CPOS = (float(options.cx), float(options.cy), 0.0)
        except ValueError:
            print("Invalid centre position cx=%s, cy=%s given" % (options.cx, options.cy))
            sys.exit()

    avis, ivis, dvis = True, False, False

    if mode == 'EDA':
        eda = geteda()
        parrow, ilist, alist, dlist = getedadelays(az=az, el=el)
    else:
        tile = gettile()
        parrow, ilist, alist, dlist = gettiledelays(az=az, el=el)

    scene.bind('click keydown', processClick)
    print("Pointing direction is shown by yellow arrow. ")
    print("  Press 'A' to toggle display of actual beamformer delays used (green).")
    print("  Press 'I' to toggle display of ideal, geometric delays calculated (white).")
    print("  Press 'D' to toggle display of the delay errors (ideal - actual) (red).")
    print()
    print("Actual delays (green) are only shown for enabled dipoles.")
    print("Negative delays are shown above the ground plane, positive delays are shown below the ground plane.")
    while True:
        vpython.rate(20)
