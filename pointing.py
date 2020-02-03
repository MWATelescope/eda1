__author__ = 'andrew'

"""Library to calculate first and second stage delays to point the Engineering Development Array (EDA).

   Written by Andrew Williams (Andrew.Williams@curtin.edu.au)
"""

import copy
import math

HEXD = ['0', '1', '2', '3', '4', '5', '6', '7', '8', '9', 'A', 'B', 'C', 'D', 'E', 'F']
C = 0.000299798  # Speed of light in meters/picosecond

HEADROOM = 0  # How many Kaelus delay steps do we keep in reserve to account for cable variation in the 1st-2nd stage coax lengths.

MSTEP = 435.0  # MWA BF delay quantisation in picoseconds
KSTEP = 92.0  # Kaelus BF delay quantisation in picoseconds

MINV1 = -16  # Range of possible physical integer MWA beamformer delays
MAXV1 = 15

MINV2 = -128  # Range of possible physical integer Kaelus beamformer delays
MAXV2 = 127

MINDELAY1 = MINV1 * MSTEP  # MWA BF's have 0-31 units of 435ps, or -16 to +15 when treated as a signed value.
MAXDELAY1 = MAXV1 * MSTEP

MINDELAY2 = (MINV2 * KSTEP)  # Kaelus BF has 0-255 units of 92ps delay, or -128 to +127 when treated as a signed value.
MAXDELAY2 = (MAXV2 * KSTEP)

MINDELAY = MINDELAY1 + MINDELAY2  # Minimum (most negative) possible physical delay in picoseconds, not counting rounding up to the nearest integer.
MAXDELAY = MAXDELAY1 + MAXDELAY2  # Maximum (most positive) possible physical delay in picoseconds, not counting rounding down to the nearest integer.

MAXERRORSTRICT = 8.0 / 100 / C  # 8.0cm = 267ps. For 'perfect' pointing, fail the delay calculation if maximum delay error is more than this
MAXERRORLOOSE = 20.0 / 100 / C  # 20.0cm = 667ps. For 'ok' pointing, fail the delay calculation if maximum delay error is more than this

# Correction factors - delay offsets, in picoseconds, to be applied to all dipoles connected to each of the given 1st-stage beamformers.
# These correct for length differences in the cables connecting the outputs of the sixteen first-stage MWA beamformers to the
# inputs of the Kaelus beamformer. Start with all of these equal to zero, then calibrate on the sky to work out what they should be.
BFCORRS = {'0':0.0,  # eg, this offset value in picoseconds is added to all dipoles connected to beamformer '0'
           '1':0.0,
           '2':0.0,
           '3':0.0,
           '4':0.0,
           '5':0.0,
           '6':0.0,
           '7':0.0,
           '8':0.0,
           '9':0.0,
           'A':0.0,
           'B':0.0,
           'C':0.0,
           'D':0.0,
           'E':0.0,
           'F':0.0}


def getOffsets(dipolefile=None):
    """Load the dipole positions for this station from the given text file.

       Format is, for example:

       #Number   EW              NS              UD
       1      -2.865895       17.395070       0.000000
       2      -2.217022       15.314435       0.000000
       3      -4.747859       16.027582       0.000000
       4      -0.316189       16.111557       0.000000

       Here 'Number' is dipole number from 1 to 256. When Number-1 is converted to a two-digit hex number, the first digit is the
       beamformer id ('0' to 'F'), and the second digit is the dipole ID within that beamformer ('0' through 'F').

       Position values are EW (East/West offset from the station centre in metres, East positive)
                           NS (North/South offset from the station centre in metres, North positive)
                           UD (Up/Down offset from the station centre in metres, Up positive). Optional, 0.00 if omitted

       The offsets are returned as a dict, with keys '0' to 'F' for the sixteen 1st stage beamformers,
       each of which contains a dict with keys '0' to 'F' for the sixteen dipoles connected to that beamformer.
       Each of those values is a tuple (x, y, z).
    """

    if dipolefile is None:  # Assume the default EDA layout
        inf = open('locations.txt', 'rt')
    else:
        inf = open(dipolefile, 'rt')

    offsets = {}
    for bfid in HEXD:
        offsets[bfid] = {}
        for dipid in HEXD:
            offsets[bfid][dipid] = (0.0, 0.0, 0.0)

    for line in inf.readlines():
        if line.startswith('#'):
            pass  # Ignore comments
        else:
            try:
                if '#' in line:
                    line = line[:line.find('#')]
                values = line.split()
                if len(values) == 4:
                    number, xs, ys, zs = values
                elif len(values) == 3:
                    number, xs, ys = values
                    zs = 0.00
                else:
                    print("Bad line in file: %s" % line)
                    continue
                name = '%02x' % (int(number) - 1)
                bfid = name[0].upper()
                dipid = name[1].upper()
                x, y, z = float(xs), float(ys), float(zs)
                offsets[bfid][dipid] = (x, y, z)
            except AssertionError:
                print("Problem parsing dipole position file %s in line: %s" % (dipolefile, line))
                return None

    return offsets


def calc_delays(offsets=None,
                az=0.0, el=90.0,
                verbose=True,
                errorlimit=MAXERRORSTRICT,
                strict=True,
                optimise=True,
                clipdelays=True,
                cpos=(0.0, 0.0, 0.0)):
    """Given an azimuth and elevation, return the delay settings for each dipole.

       :param az: azimuth (degrees), where 0 is north and it increases clockwise.
       :param el: elevation (degrees) is the angle up from the horizon.
       :param offsets: a dict containing the 256 dipole positions in metres, relative to the station centre (0, 0, 0)
       :param verbose: Boolean, indicates some text output (when True) or completely silent (when False)
       :param errorlimit: If the maximum pointing error for any dipole exceeds this value in picoseconds, return (None,None).
       :param strict: If False, dipoles exceeding their maximum delay are disabled. If True, this call will fail if any exceed max delay.
       :param optimise: If True, optimise least-squares error for all dipoles by trying alternate Kaelus delay values.
       :param clipdelays: if True (default), means that MWA beamformer idelays are clipped to -16->+15, otherwise they are returned
                     without clipping so that single-beamformer mode works, for example, after normalising delays.
       :param cpos: a tuple of (x, y, z) coordinates for the geometric delay centre, in metres, relative to the coordinates of the
                     dipole offsets. Use this to specify an off-centre geometric delay calculation - for example, if you are
                     only using dipoles in a small cluster near one edge of the EDA, and want to reach lower than 20 degrees
                     away from the zenith. Defaults to (0,0,0).

       Algorith:
          -All 256 dipoles are treated individually, and a geometric delay for each dipole in picoseconds is
              calculated, relative to the station centre (the 0,0,0 coordinate) plus the value of cpos. This delay ranges from
              around -18000ps up to +18000ps for typical pointings that can be achieved.
          -The mean of the total geometric delay is calculated for each group of 16 dipoles connected to a single 1st stage MWA
              MWA beamformer.
          -The Kaelus input delay for the input connected to that 1st stage beamformer is set to that mean delay, divided by the
              Kaelus delay step size (184ps) and rounded to the nearest integer.
          -If that Kaelus integer delay value is too large (positive or negative) for the hardware, the maximum delay value possible
              for that Kaelus input is used instead.
          -The remaining delay for each dipole in that group of 16 (the total delay minus 92ps times the Kaelus delay for that BF)
              is divided by the MWA BF step size (435ps) and rounded to the nearest integer.
          -Rounding errors are optimised using the fact that Kaelus delay steps are much smaller than MWA delay steps - for each
              Kaelus input, a new Kaelus delay value is tried for all values within +/-6 of the value originally chosen, and the
              remaining delay components for each of the 16 MWA beamformers on that Kaelus input are converted to the nearest
              MWA BF delay values. The best Kaelus delay value is chosen by comparing the 'sum of squares' error between
              geometric and quantised/rounded delays for all BF's in that group of 16.
          -Once integer delays have been calculated for all 256 first-stage inputs as well as the 16 Kaelus inputs, a final 'sum of squares'
              error figure is calculated, and the final signed integer delays are returned.

       A tuple is always returned by this function - (None, None) if the pointing is unreachable and strict=True, otherwise
          idelays, (delays, delayerrs, sqe, maxerr) where:

          idelays is a dict, where delays['0'] through to delays['F'] are each dicts containing the delays for the 16 dipoles connected to
              the given first stage beamformer, with keys '0' through 'F' for the 16 dipoles. Each delay is an integer from -16 to +15,
              the allowed range for a (signed) MWA beamformer delay. Add 16 to these values before sending them to the beamformer.

          idelays['K'] is a 17th dict containing delay values, but these ones are for the Kaelus (2nd stage) beamformer. Here the
              key ('0' through 'F') represents the 1st stage beamformer ID for tha input, not an individual dipole. Delay values
              in this dict range from -128 to +127, or a smaller window if HEADROOM has been reserved for cable calibration.
              Add 128 to these values before sending them to the Kaelus beamformer.

          delays has the same structure as 'idelays', but contains only a floating point geometric delay in picoseconds for
              each dipole, from ['0]['0'] to ['F']['F'].

          delayerrs is like delays, but contains the delay errors (geometric minus quantised) in picoseconds for each dipole.

          sqe is a single float: the sum of the squares of the delay errors above.

          maxerr is the absolute value of the largest dipole delay error, in picoseconds.

    """
    dtor = math.pi / 180.0  # convert degrees to radians
    # define zenith angle
    za = 90 - el

    # Initialise the structures to contain geometric and integer delay values.
    delays = {}
    for bfid in HEXD:
        delays[bfid] = {}
        for dipid in HEXD:
            delays[bfid][dipid] = 0.0

    # Initialise the structures to contain the differences between geometric and quantised delay values.
    delayerrs = {}
    for bfid in HEXD:
        delayerrs[bfid] = {}
        for dipid in HEXD:
            delayerrs[bfid][dipid] = 0.0

    idelays = {}
    for bfid in HEXD + ['K']:  # An extra beamformer 'K' to hold Kaelus delays - only necessary for the integer delays
        idelays[bfid] = {}
        for dipid in HEXD:
            idelays[bfid][dipid] = 0.0

    # Check input sanity
    if (abs(za) > 90):
        if verbose:
            print("Elevation must be between 0 and 90 degrees")
        return None, None

    # Convert to radians
    azr = az * dtor
    zar = za * dtor

    for bfid in HEXD:  # Loop over all first-stage beamformers
        for dipid in HEXD:  # Loop over each of the 16 dipoles connected to that first-stage beamformer
            x, y, z = offsets[bfid][dipid]
            x -= cpos[0]  # Find the difference between the dipole coordinate and the geometric delay centre
            y -= cpos[1]
            z -= cpos[2]
            delay = ((x * math.sin(azr) + y * math.cos(azr)) * math.sin(zar) + (z * math.cos(
                zar))) / C  # Calculate geometric delays in picoseconds as a signed float, relative to the station centre
            delay += BFCORRS[bfid]  # Apply a correction factor in picoseconds, unique for each first-stage beamformer
            delays[bfid][
                dipid] = delay  # 'delays' contains 256 _total_ delays in picoseconds, one for each dipole, not split into first/second stages
        # mindelay = min(delays[bfid].values())
        # maxdelay = max(delays[bfid].values())
        meandelay = sum(delays[bfid].values()) / 16.0

        # Allocate as much as possible of the total delay for each dipole to the Kaelus stage 2 delay for that input, by making it equal to the mean total delay for the 16 dipoles on that Kaelus input.
        delay2 = meandelay

        idelays['K'][bfid] = int(round(delay2 / KSTEP))  # First draft at the Kaelus delay for this 1st-stage BF

        # If the Kaelus delay is outside the range of possible Kaelus delay values, make it as large/small as possible, and hope the rest of the total delay can be accomodated by the 1st-stage BF
        if idelays['K'][bfid] > MAXV2 - HEADROOM:
            idelays['K'][bfid] = MAXV2 - HEADROOM
            delay2 = idelays['K'][bfid] * KSTEP
        elif idelays['K'][bfid] < MINV2 + HEADROOM:
            idelays['K'][bfid] = MINV2 + HEADROOM
            delay2 = idelays['K'][bfid] * KSTEP

        if optimise:
            # Now see if we can optimise the 1st-stage pointing residuals by moving +/-6 Kaelus beamformer delay steps from the MWA BF delays (435ps) to the Kaelus input delay (184ps)
            # First, make the window +/- 6 steps if possible, or limit the edges of the window to the minimum or maximum Kaelus integer delay value if we are close to the top or bottom.
            begin = max((MINV2 + HEADROOM), (idelays['K'][bfid] - 6))
            end = min((MAXV2 - HEADROOM), (idelays['K'][bfid] + 6))
            # Now loop over the possible alternative Kaelus delays, calculating the sum of the squares of the differences between the ideal geometric delay, and the quantised integer delays.
            bestkid, bestsqe = idelays['K'][bfid], 9e99
            for kidelay in range(begin, end + 1):
                sqe = 0.0
                for dipid in HEXD:
                    delay1 = delays[bfid][dipid] - (kidelay * KSTEP)
                    idelay1 = int(round(delay1 / MSTEP))
                    if not (MINV1 < idelay1 < MAXV1):  # Optimised dipole delay outside possible value range
                        sqe += 9e99  # Invalidate this choice of kidelay
                    sqe += (delays[bfid][dipid] - ((idelay1 * MSTEP) + (kidelay * KSTEP))) ** 2
                if sqe < bestsqe:
                    bestkid, bestsqe = kidelay, sqe

            # Take the Kaelus delay with the smallest sum-of-squares error and use that
            if verbose:
                print("BF %s: Naive KD=%d, tried range from %d - %d, settled on KD=%d" % (bfid, idelays['K'][bfid], begin, end, bestkid))
            delay2 = bestkid * KSTEP
            idelays['K'][bfid] = bestkid

        # Using that optimised Kaelus delay, calculate the integer 1st stage delay values
        for dipid in HEXD:
            delay1 = delays[bfid][dipid] - delay2
            idelays[bfid][dipid] = int(round(delay1 / MSTEP))
            if clipdelays:
                if idelays[bfid][dipid] < MINV1:
                    idelays[bfid][dipid] = MINV1
                elif idelays[bfid][dipid] > MAXV1:
                    idelays[bfid][dipid] = MAXV1

    # Calculate a final sum-of-squares error for the differences between ideal geometric and actual quantised, rounded delays, as a measure of pointing quality.
    sqe = 0.0
    maxerr = 0.0
    offcount = 0
    for bfid in HEXD:
        for dipid in HEXD:
            err = (delays[bfid][dipid] - ((idelays[bfid][dipid] * MSTEP) + (idelays['K'][bfid] * KSTEP)))
            delayerrs[bfid][dipid] = err
            if abs(err) > maxerr:  # Update the largest error value found in this pointing calculation so far
                maxerr = abs(err)
            if abs(err) > errorlimit:  # If any dipole has an error greater than the maximum allowed error, then either disable it, or just fail
                if strict:
                    if verbose:
                        print("BF %s: Dipole %s exceeds maximum error limit: %5.0f > %5.0f" % (bfid, dipid, maxerr, errorlimit))
                    return None, None
                if clipdelays:  # Don't disable the dipole if we want to use single-beamformer mode, for example, after normalising delays
                    idelays[bfid][dipid] = 16  # This disables the dipole, because 16 is added before sending it to the BF hardware
                offcount += 1  # Add to the count of disabled dipoles
            sqe += err * err

    return idelays, (delays, delayerrs, sqe, maxerr, offcount)


def calc_Kdelays(offsets=None,
                 indelays=None,
                 az=0.0, el=90.0,
                 verbose=True,
                 errorlimit=MAXERRORSTRICT,
                 strict=True,
                 optimise=True,
                 clipdelays=True,
                 cpos=(0.0, 0.0, 0.0)):
    """Given an azimuth and elevation, and a set of existing integer delays, return the delay settings for each dipole
       with the best RMS error by using ONLY Kaelus (2nd stage) delay changes from the input array, keeping
       MWA BF (1st stage) delays the same..

       :param az: azimuth (degrees), where 0 is north and it increases clockwise.
       :param el: elevation (degrees) is the angle up from the horizon.
       :param indelays: a structure in exactly the same format as the output delay structure from this function or calc_delays.
       :param offsets: a dict containing the 256 dipole positions in metres, relative to the station centre (0, 0, 0)
       :param verbose: Boolean, indicates some text output (when True) or completely silent (when False)
       :param errorlimit: If the maximum pointing error for any dipole exceeds this value in picoseconds, return (None,None).
       :param strict: If False, dipoles exceeding their maximum delay are disabled. If True, this call will fail if any exceed max delay.
       :param optimise: If True, optimise least-squares error for all dipoles by trying alternate Kaelus delay values.
       :param clipdelays: if True (default), means that MWA beamformer idelays are clipped to -16->+15, otherwise they are returned
                     without clipping so that single-beamformer mode works, for example, after normalising delays.
       :param cpos: a tuple of (x, y, z) coordinates for the geometric delay centre, in metres, relative to the coordinates of the
                     dipole offsets. Use this to specify an off-centre geometric delay calculation - for example, if you are
                     only using dipoles in a small cluster near one edge of the EDA, and want to reach lower than 20 degrees
                     away from the zenith. Defaults to (0,0,0).

       Algorith:
          -All 256 dipoles are treated individually, and a geometric delay for each dipole in picoseconds is
              calculated, relative to the station centre (the 0,0,0 coordinate). This delay ranges from around -18000ps up to
              +18000ps for typical pointings that can be acheived.
          -The mean of the total geometric delay is calculated for each group of 16 dipoles connected to a single 1st stage MWA
              MWA beamformer.
          -The Kaelus input delay for the input connected to that 1st stage beamformer is set to that mean delay, divided by the
              Kaelus delay step size (184ps) and rounded to the nearest integer.
          -If that Kaelus integer delay value is too large (positive or negative) for the hardware, the maximum delay value possible
              for that Kaelus input is used instead.
          -The remaining delay (the total delay minus 184ps times the Kaelus delay for that BF) is divided by the MWA BF step
              size (435ps) and rounded to the nearest integer.
          -Rounding errors are optimised using the fact that Kaelus delay steps are much smaller than MWA delay steps - a new Kaelus
              delay value is tried for all values within +/-3 of the value originally chosen, and the 'sum of squares' error between
              geometric and quantised/rounded delays is optimised.
          -Once integer delays have been calculated for all 256 first-stage inputs as well as the 16 Kaelus inputs, a final 'sum of squares'
              error figure is calculated, and the final signed integer delays are returned.

       A tuple is always returned by this function - (None, None) if the pointing is unreachable and strict=True, otherwise (delays,(sqe, maxerr)) where:
          idelays, (delays, delayerrs, sqe, maxerr) where:

          idelays is a dict, where delays['0'] through to delays['F'] are each dicts containing the delays for the 16 dipoles connected to
              the given first stage beamformer, with keys '0' through 'F' for the 16 dipoles. Each delay is an integer from -16 to +15,
              the allowed range for a (signed) MWA beamformer delay. Add 16 to these values before sending them to the beamformer.

          idelays['K'] is a 17th dict containing delay values, but these ones are for the Kaelus (2nd stage) beamformer. Here the
              key ('0' through 'F') represents the 1st stage beamformer ID for tha input, not an individual dipole. Delay values
              in this dict range from -128 to +127, or a smaller window if HEADROOM has been reserved for cable calibration.
              Add 128 to these values before sending them to the Kaelus beamformer.

          delays has the same structure as 'idelays', but contains only a floating point geometric delay in picoseconds for
              each dipole, from ['0]['0'] to ['F']['F'].

          delayerrs is like delays, but contains the delay errors (geometric minus quantised) in picoseconds for each dipole.

          sqe is a single float: the sum of the squares of the delay errors above.

          maxerr is the absolute value of the largest dipole delay error, in picoseconds.
    """
    dtor = math.pi / 180.0  # convert degrees to radians
    # define zenith angle
    za = 90 - el

    # Initialise the structures to contain geometric and integer delay values.
    delays = {}
    for bfid in HEXD:
        delays[bfid] = {}
        for dipid in HEXD:
            delays[bfid][dipid] = 0.0

    # Initialise the structures to contain the differences between geometric and quantised delay values.
    delayerrs = {}
    for bfid in HEXD:
        delayerrs[bfid] = {}
        for dipid in HEXD:
            delayerrs[bfid][dipid] = 0.0

    idelays = {}
    for bfid in HEXD + ['K']:  # An extra beamformer 'K' to hold Kaelus delays - only necessary for the integer delays
        idelays[bfid] = {}
        for dipid in HEXD:
            idelays[bfid][dipid] = 0.0

    # Check input sanity
    if (abs(za) > 90):
        if verbose:
            print("Elevation must be between 0 and 90 degrees")
        return None, None

    if indelays is None:
        print(
            "Must pass input delay structure - if you aren't modifying a previously calculated delay set, use calc_delays()")
        return None, None

    # Convert to radians
    azr = az * dtor
    zar = za * dtor

    for bfid in HEXD:  # Loop over all first-stage beamformers
        for dipid in HEXD:  # Loop over each of the 16 dipoles connected to that first-stage beamformer
            x, y, z = offsets[bfid][dipid]
            x -= cpos[0]  # Find the difference between the dipole coordinate and the geometric delay centre
            y -= cpos[1]
            z -= cpos[2]
            delay = ((x * math.sin(azr) + y * math.cos(azr)) * math.sin(zar) + (z * math.cos(
                zar))) / C  # Calculate geometric delays in picoseconds as a signed float, relative to the station centre
            delays[bfid][
                dipid] = delay  # 'delays' contains 256 _total_ delays in picoseconds, one for each dipole, not split into first/second stages
        # mindelay = min(delays[bfid].values())
        # maxdelay = max(delays[bfid].values())
        meandelay = sum(delays[bfid].values()) / 16.0

        inmeandelay = sum(indelays[bfid].values()) * MSTEP / 16.0
        delay2 = meandelay - inmeandelay
        idelays['K'][bfid] = int(round(delay2 / KSTEP))  # First draft at the Kaelus delay for this 1st-stage BF

        # If the Kaelus delay is outside the range of possible Kaelus delay values, make it as large/small as possible, and hope the rest of the total delay can be accomodated by the 1st-stage BF
        if idelays['K'][bfid] > MAXV2 - HEADROOM:
            idelays['K'][bfid] = MAXV2 - HEADROOM
            # delay2 = idelays['K'][bfid] * KSTEP
        elif idelays['K'][bfid] < MINV2 + HEADROOM:
            idelays['K'][bfid] = MINV2 + HEADROOM
            # delay2 = idelays['K'][bfid] * KSTEP

        if optimise:
            # Now see if we can optimise the 1st-stage pointing residuals by moving +/-6 Kaelus beamformer delay steps
            # First, make the window +/- 3 steps if possible, or limit the edges of the window to the minimum or maximum Kaelus interger delay value if we are close to the top or bottom.
            begin = max((MINV2 + HEADROOM), (idelays['K'][bfid] - 6))
            end = min((MAXV2 - HEADROOM), (idelays['K'][bfid] + 6))
            # Now loop over the possible alternative Kaelus delays, calculating the sum of the squares of the differences between the ideal geometric delay, and the quantised integer delays.
            bestkid, bestsqe = idelays['K'][bfid], 9e99
            for kidelay in range(begin, end + 1):
                sqe = 0.0
                for dipid in HEXD:
                    sqe += (delays[bfid][dipid] - ((indelays[bfid][dipid] * MSTEP) + (kidelay * KSTEP))) ** 2
                if sqe < bestsqe:
                    bestkid, bestsqe = kidelay, sqe

            # Take the Kaelus delay with the smallest sum-of-squares error and use that
            if verbose:
                print("BF %s: Naive KD=%d, tried range from %d - %d, settled on KD=%d" % (bfid, idelays['K'][bfid], begin, end, bestkid))
            # delay2 = bestkid * KSTEP
            idelays['K'][bfid] = bestkid

        # Copy the integer 1st stage delay values
        idelays[bfid] = copy.copy(indelays[bfid])

    # Calculate a final sum-of-squares error for the differences between ideal geometric and actual quantised, rounded delays, as a measure of pointing quality.
    sqe = 0.0
    maxerr = 0.0
    offcount = 0
    for bfid in HEXD:
        for dipid in HEXD:
            err = (delays[bfid][dipid] - ((idelays[bfid][dipid] * MSTEP) + (idelays['K'][bfid] * KSTEP)))
            delayerrs[bfid][dipid] = err
            if abs(err) > maxerr:  # Update the largest error value found in this pointing calculation so far
                maxerr = abs(err)
            if abs(
                    err) > errorlimit:  # If any dipole has an error greater than the maximum allowed error, then either disable it, or just fail
                if strict:
                    if verbose:
                        print("BF %s: Dipole %s exceeds maximum error limit: %5.0f > %5.0f" % (bfid, dipid, maxerr, errorlimit))
                    return None, None
                if clipdelays:  # Don't disable the dipole if we want to use single-beamformer mode, for example, after normalising delays
                    idelays[bfid][
                        dipid] = 16  # This disables the dipole, because 16 is added before sending it to the BF hardware
                offcount += 1  # Add to the count of disabled dipoles
            sqe += err * err

    return idelays, (delays, delayerrs, sqe, maxerr, offcount)


def pdelays(delays=None, errors=None):
    """Pretty-print the given delays and calculate and print some statistics about the delay values.
    """
    fstring = "%3d  " * 16
    print("Integer delays for each dipole, and Kaelus BF:")
    print("Dipole:                 0    1    2    3    4    5    6    7    8    9    A    B    C    D    E    F")
    for bfid in HEXD:
        mindelay = min(delays[bfid].values())
        maxdelay = max(delays[bfid].values())
        meandelay = sum(delays[bfid].values()) / 16.0
        print("BF %s: delay = (%3d) +" % (bfid, delays['K'][bfid]),
              fstring % tuple([delays[bfid][dipid] for dipid in HEXD]),
              "   Max=%3d, Min=%3d, Mean=%7.3f" % (maxdelay, mindelay, meandelay))

    print()
    mindelay = min(delays['K'].values())
    maxdelay = max(delays['K'].values())
    meandelay = sum(delays['K'].values()) / 16.0
    print("KB:   Max=%3d, Min=%3d, Mean=%7.3f" % (maxdelay, mindelay, meandelay))

    if errors is not None:
        rdelays, delayerrs, errsum, maxerr, offcount = errors
        print()
        print("%d dipoles disabled because delays exceeded limits" % offcount)
        print("Delay errors per dipole, in cm:")
        fstring = "%3.0f  " * 16
        print("Dipole:                 0    1    2    3    4    5    6    7    8    9    A    B    C    D    E    F")
        for bfid in HEXD:
            minerr = min(delayerrs[bfid].values()) * 100 * C
            maxerr = max(delayerrs[bfid].values()) * 100 * C
            print("BF %s:                " % bfid,
                  fstring % tuple([delayerrs[bfid][dipid] * 100 * C for dipid in HEXD]),
                  "   Max=%3d, Min=%3d" % (maxerr, minerr))


def track(offsets=None, fname='', errorlimit=MAXERRORSTRICT):
    """Given a file containing lines with three values (gpsseconds, az, el), read in the contents
       line by line and print status and flags when the source becomes visible to this station
       (using the provided dipole offsets in 'offsets'), when it is no longer visible, and when the
       MWA and Kaelus dipoles change state.
    """
    f = open(fname, 'rt')
    odelays = None
    fixdelays = None
    lines = f.readlines()
    for line in lines:
        t, az, el = tuple(map(float, line.split()))
        newdelays, newerrors = calc_delays(offsets=offsets, az=az, el=el, verbose=False, errorlimit=errorlimit)
        if newdelays is None:
            print("Oops.", (odelays is None))
        if (odelays is None) and (newdelays is not None):
            fixdelays, fixerrors, = newdelays, newerrors
            print("Time=%d: Rises" % t)
        elif (odelays is not None) and (newdelays is None):
            print("Time=%d: Sets" % t)

        newkdelays, newkerrors = calc_Kdelays(offsets=offsets, indelays=fixdelays, az=az, el=el, verbose=False,
                                              errorlimit=errorlimit)
        if newkdelays is not None:
            newkrdelays, newkdelayerrs, newkerrsum, newkmaxerr, newoffcount = newkerrors
            if newkmaxerr * C * 100 > errorlimit:
                print("Time=%d: MWA BF delays changed, errors outside limits." % t)
                fixdelays, fixerrors = newdelays, newerrors

        odelays = newdelays


def plotErrors(offsets=None, npts=100):
    import numpy
    import random
    from matplotlib.mlab import griddata
    import matplotlib.pyplot as plt
    import numpy as np

    x = numpy.zeros(shape=npts)
    y = numpy.zeros(shape=npts)
    z1 = numpy.zeros(shape=npts)
    z2 = numpy.zeros(shape=npts)
    i = 0
    while i < npts:
        x[i] = random.uniform(0, 360)
        y[i] = random.uniform(70, 90)
        delays, errors = calc_delays(offsets=offsets, az=x[i], el=y[i], verbose=False, strict=True)
        if errors is not None:
            delays, delayerrs, errsum, maxerr = errors
            z1[i] = math.sqrt(errsum / 256)
            z2[i] = maxerr
            i += 1
    # define grid.
    xi = np.linspace(0, 360, 1800)
    yi = np.linspace(70, 90, 100)
    # grid the data.
    z1i = griddata(x, y, z1, xi, yi, interp='linear')
    z2i = griddata(x, y, z2, xi, yi, interp='linear')

    plt.figure(figsize=(24, 12), dpi=300)
    f, axarr = plt.subplots(nrows=2, ncols=1, sharex=True, sharey=False, squeeze=True)
    #  plt.subplots_adjust(left=0.125, bottom=0.1, right=0.9, top=0.9,
    #                wspace=0.0, hspace=0.1)

    rmsf = axarr[0]  # Axes for X pol figure
    maxf = axarr[1]  # Axes for pol difference figure

    # contour the gridded RMS error data, plotting dots at the nonuniform data points.
    rmserror = z1i * C * 100.0
    ECS1 = rmsf.contour(xi, yi, rmserror, 8, linewidths=0.5, colors='k')
    ECS2 = rmsf.contourf(xi, yi, rmserror, 8, cmap=plt.cm.rainbow,
                         vmax=abs(rmserror).max(), vmin=-abs(rmserror).max())
    plt.colorbar(mappable=ECS2, ax=rmsf)  # draw colorbar
    # plot data points.
    rmsf.scatter(x, y, marker='.', c='b', s=0.1, zorder=10)
    rmsf.set_xlim(0, 360)
    rmsf.set_ylim(70, 90)
    rmsf.set_title('Mean EDA pointing errors (cm/dipole) (%d points)' % npts)

    # contour the gridded maximum error data, plotting dots at the nonuniform data points.
    maxerror = z2i * C * 100
    MCS1 = maxf.contour(xi, yi, maxerror, 8, linewidths=0.5, colors='k')
    MCS2 = maxf.contourf(xi, yi, maxerror, 8, cmap=plt.cm.rainbow,
                         vmax=abs(maxerror).max(), vmin=-abs(maxerror).max())
    plt.colorbar(mappable=MCS2, ax=maxf)  # draw colorbar
    # plot data points.
    maxf.scatter(x, y, marker='.', c='b', s=0.1, zorder=10)
    maxf.set_xlim(0, 360)
    maxf.set_ylim(70, 90)
    maxf.set_title('Max EDA pointing errors (cm/dipole) (%d points)' % npts)

    #  plt.colorbar(mappable=MCS2, ax=[rmsf, maxf])
    plt.savefig('/tmp/eda2.png', dpi=300)
