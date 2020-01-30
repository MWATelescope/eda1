

import sys
import time
import warnings

warnings.simplefilter(action='ignore')

import Pyro4

import pointing

"""
EDA test library

Example usage

$ python
>>> import edatest as et
>>> idelays = et.getDelays(az=180.0, el=80.0)             # Calculate delays for az=180, el=10
BF 0: Naive KD=-90, tried range from -96 - -84, settled on KD=-96
BF 1: Naive KD=-52, tried range from -58 - -46, settled on KD=-47
BF 2: Naive KD=-80, tried range from -86 - -74, settled on KD=-78
BF 3: Naive KD=-3, tried range from -9 - 3, settled on KD=1
BF 4: Naive KD=95, tried range from 89 - 101, settled on KD=89
BF 5: Naive KD=-46, tried range from -52 - -40, settled on KD=-48
BF 6: Naive KD=67, tried range from 61 - 73, settled on KD=63
BF 7: Naive KD=9, tried range from 3 - 15, settled on KD=8
BF 8: Naive KD=69, tried range from 63 - 75, settled on KD=68
BF 9: Naive KD=26, tried range from 20 - 32, settled on KD=29
BF A: Naive KD=63, tried range from 57 - 69, settled on KD=57
BF B: Naive KD=-51, tried range from -57 - -45, settled on KD=-48
BF C: Naive KD=27, tried range from 21 - 33, settled on KD=32
BF D: Naive KD=-23, tried range from -29 - -17, settled on KD=-26
BF E: Naive KD=24, tried range from 18 - 30, settled on KD=26
BF F: Naive KD=-26, tried range from -32 - -20, settled on KD=-25
>>> idelays
{'A': {'A': -2, 'C': 3, 'B': -2, 'E': -4, 'D': -2, 'F': -3, '1': 5, '0': 8, '3': 5, '2': 7, '5': 3, '4': 3, '7': 0, '6': 0, '9': 0, '8': 1}, 'C': {'A': -3, 'C': 2, 'B': 0, 'E': 4, 'D': -5, 'F': -9, '1': 3, '0': 3, '3': -2, '2': 2, '5': -3, '4': -1, '7': -6, '6': 1, '9': -6, '8': 4}, 'B': {'A': 3, 'C': 4, 'B': -1, 'E': -3, 'D': 3, 'F': 6, '1': -5, '0': -7, '3': -2, '2': -4, '5': -1, '4': -4, '7': -1, '6': -2, '9': 1, '8': 2}, 'E': {'A': -5, 'C': 1, 'B': -3, 'E': -4, 'D': -5, 'F': -1, '1': 4, '0': 6, '3': 2, '2': 2, '5': 0, '4': 0, '7': -2, '6': 1, '9': -1, '8': -2}, 'D': {'A': -1, 'C': -6, 'B': 6, 'E': -3, 'D': 8, 'F': 3, '1': -1, '0': 1, '3': -1, '2': 4, '5': -4, '4': 4, '7': 4, '6': -3, '9': -2, '8': 1}, 'F': {'A': 4, 'C': 1, 'B': -6, 'E': 6, 'D': 0, 'F': -7, '1': -3, '0': -2, '3': -6, '2': -3, '5': 3, '4': 5, '7': 0, '6': 1, '9': 2, '8': 2}, 'K': {'A': 57, 'C': 32, 'B': -48, 'E': 26, 'D': -26, 'F': -25, '1': -47, '0': -96, '3': 1, '2': -78, '5': -48, '4': 89, '7': 8, '6': 63, '9': 29, '8': 68}, '1': {'A': -2, 'C': 2, 'B': 4, 'E': -4, 'D': 5, 'F': 0, '1': -3, '0': -3, '3': 1, '2': -5, '5': -1, '4': 1, '7': -3, '6': -7, '9': 3, '8': -5}, '0': {'A': 0, 'C': 2, 'B': 4, 'E': 4, 'D': 0, 'F': 6, '1': 0, '0': -3, '3': -1, '2': -1, '5': 2, '4': 1, '7': -2, '6': 3, '9': 2, '8': 4}, '3': {'A': 2, 'C': 4, 'B': 1, 'E': -4, 'D': -2, 'F': 4, '1': -4, '0': -4, '3': -2, '2': -2, '5': 0, '4': 0, '7': -1, '6': -4, '9': -5, '8': 2}, '2': {'A': 3, 'C': 2, 'B': 3, 'E': -1, 'D': 0, 'F': 4, '1': -3, '0': -6, '3': -5, '2': -3, '5': 0, '4': -1, '7': 1, '6': -2, '9': 0, '8': 2}, '5': {'A': 4, 'C': 4, 'B': 4, 'E': 3, 'D': 1, 'F': 6, '1': -6, '0': -4, '3': -1, '2': -1, '5': -4, '4': -2, '7': 1, '6': 2, '9': 1, '8': -2}, '4': {'A': 2, 'C': -1, 'B': 0, 'E': -3, 'D': 3, 'F': -4, '1': 4, '0': 5, '3': 2, '2': 2, '5': 4, '4': 4, '7': 0, '6': 0, '9': 2, '8': -1}, '7': {'A': 5, 'C': 4, 'B': 7, 'E': -3, 'D': -5, 'F': 1, '1': -3, '0': 0, '3': 3, '2': 1, '5': 3, '4': -1, '7': -6, '6': -3, '9': -2, '8': 1}, '6': {'A': -1, 'C': -4, 'B': 6, 'E': 2, 'D': -3, 'F': 0, '1': 1, '0': 3, '3': 1, '2': 2, '5': 4, '4': 5, '7': -2, '6': -1, '9': -1, '8': 1}, '9': {'A': -4, 'C': 1, 'B': -1, 'E': -5, 'D': -7, 'F': -4, '1': 0, '0': 2, '3': 0, '2': 2, '5': 3, '4': 1, '7': -1, '6': -3, '9': 1, '8': 4}, '8': {'A': -2, 'C': -3, 'B': 1, 'E': -1, 'D': -2, 'F': -4, '1': 2, '0': 5, '3': 2, '2': 5, '5': 0, '4': 3, '7': 0, '6': 1, '9': -1, '8': -1}}
>>>
>>> for dip in '012345679ABCDEF':    # Loop over every dipole except '8' (the 9th dipole)
...   for bfid in et.HEXD:           # Loop over every first-stage beamformer
...     idelays[bfid][dip] = 16      # Disable that dipole (when 16 is added before sending it to the BF, it will become 32)
...
>>> idelays
{'A': {'A': 16, 'C': 16, 'B': 16, 'E': 16, 'D': 16, 'F': 16, '1': 16, '0': 16, '3': 16, '2': 16, '5': 16, '4': 16, '7': 16, '6': 16, '9': 16, '8': 1}, 'C': {'A': 16, 'C': 16, 'B': 16, 'E': 16, 'D': 16, 'F': 16, '1': 16, '0': 16, '3': 16, '2': 16, '5': 16, '4': 16, '7': 16, '6': 16, '9': 16, '8': 4}, 'B': {'A': 16, 'C': 16, 'B': 16, 'E': 16, 'D': 16, 'F': 16, '1': 16, '0': 16, '3': 16, '2': 16, '5': 16, '4': 16, '7': 16, '6': 16, '9': 16, '8': 2}, 'E': {'A': 16, 'C': 16, 'B': 16, 'E': 16, 'D': 16, 'F': 16, '1': 16, '0': 16, '3': 16, '2': 16, '5': 16, '4': 16, '7': 16, '6': 16, '9': 16, '8': -2}, 'D': {'A': 16, 'C': 16, 'B': 16, 'E': 16, 'D': 16, 'F': 16, '1': 16, '0': 16, '3': 16, '2': 16, '5': 16, '4': 16, '7': 16, '6': 16, '9': 16, '8': 1}, 'F': {'A': 16, 'C': 16, 'B': 16, 'E': 16, 'D': 16, 'F': 16, '1': 16, '0': 16, '3': 16, '2': 16, '5': 16, '4': 16, '7': 16, '6': 16, '9': 16, '8': 2}, 'K': {'A': 57, 'C': 32, 'B': -48, 'E': 26, 'D': -26, 'F': -25, '1': -47, '0': -96, '3': 1, '2': -78, '5': -48, '4': 89, '7': 8, '6': 63, '9': 29, '8': 68}, '1': {'A': 16, 'C': 16, 'B': 16, 'E': 16, 'D': 16, 'F': 16, '1': 16, '0': 16, '3': 16, '2': 16, '5': 16, '4': 16, '7': 16, '6': 16, '9': 16, '8': -5}, '0': {'A': 16, 'C': 16, 'B': 16, 'E': 16, 'D': 16, 'F': 16, '1': 16, '0': 16, '3': 16, '2': 16, '5': 16, '4': 16, '7': 16, '6': 16, '9': 16, '8': 4}, '3': {'A': 16, 'C': 16, 'B': 16, 'E': 16, 'D': 16, 'F': 16, '1': 16, '0': 16, '3': 16, '2': 16, '5': 16, '4': 16, '7': 16, '6': 16, '9': 16, '8': 2}, '2': {'A': 16, 'C': 16, 'B': 16, 'E': 16, 'D': 16, 'F': 16, '1': 16, '0': 16, '3': 16, '2': 16, '5': 16, '4': 16, '7': 16, '6': 16, '9': 16, '8': 2}, '5': {'A': 16, 'C': 16, 'B': 16, 'E': 16, 'D': 16, 'F': 16, '1': 16, '0': 16, '3': 16, '2': 16, '5': 16, '4': 16, '7': 16, '6': 16, '9': 16, '8': -2}, '4': {'A': 16, 'C': 16, 'B': 16, 'E': 16, 'D': 16, 'F': 16, '1': 16, '0': 16, '3': 16, '2': 16, '5': 16, '4': 16, '7': 16, '6': 16, '9': 16, '8': -1}, '7': {'A': 16, 'C': 16, 'B': 16, 'E': 16, 'D': 16, 'F': 16, '1': 16, '0': 16, '3': 16, '2': 16, '5': 16, '4': 16, '7': 16, '6': 16, '9': 16, '8': 1}, '6': {'A': 16, 'C': 16, 'B': 16, 'E': 16, 'D': 16, 'F': 16, '1': 16, '0': 16, '3': 16, '2': 16, '5': 16, '4': 16, '7': 16, '6': 16, '9': 16, '8': 1}, '9': {'A': 16, 'C': 16, 'B': 16, 'E': 16, 'D': 16, 'F': 16, '1': 16, '0': 16, '3': 16, '2': 16, '5': 16, '4': 16, '7': 16, '6': 16, '9': 16, '8': 4}, '8': {'A': 16, 'C': 16, 'B': 16, 'E': 16, 'D': 16, 'F': 16, '1': 16, '0': 16, '3': 16, '2': 16, '5': 16, '4': 16, '7': 16, '6': 16, '9': 16, '8': -1}}
>>> et.sendDelays(idelays=idelays)
>>>
"""

sys.excepthook = Pyro4.util.excepthook
Pyro4.config.DETAILED_TRACEBACK = True

OFFSETS = pointing.getOffsets()

HEXD = ['0', '1', '2', '3', '4', '5', '6', '7', '8', '9', 'A', 'B', 'C', 'D', 'E', 'F']

KURL = 'PYRO:Kaelus@10.128.2.51:19987'
BURLS = {'eda1com':'PYRO:eda1com@10.128.2.63:19987', 'eda2com':'PYRO:eda2com@10.128.2.65:19987'}
TILEID = 0

kproxy = Pyro4.Proxy(KURL)
bfproxies = {}
for clientid, url in BURLS.items():
  bfproxies[clientid] = Pyro4.Proxy(url)


def getDelays(az=0, el=90):
  """Call pointing.calc_delays to return the delays and associated error structures, then
     return just the integer delay values.

     Here, idelays is a dict, with key values ranging from '0' to 'F', plus 'K'.

     idelays['0'] contains all 16 dipole delays for the first of the first stage beamformers, and is in itself,
     a dict with keys ranging from '0' to 'F', for the 16 dipoles.

     idelays['1'] is another dict containing the 16 dipole delays for the SECOND first stage beamformer, etc.

     idelays['K'] is a dict containing the second stage delays for the Kaelus beamformer, and is also a dict,
     with keys ranging from '0' (containing the Kaelus input delay for first-stage beamformer '0') to 'F'.

     So, the total delay in picoseconds for dipole 'E' on beamformer '3' (the 15th dipole on the 4th MWA beamformer)
     would be given by:

     delay = idelays['K']['3'] * 92.0 + idelays['3']['E'] * 435.0

     Note that these delay values are signed - both positive and negative values. First stage delays can range from
     -16 to +15, and second stage delays can range from -128 to +126. Before they are actually sent to the
     beamformers, 16 is added to the first-stage delay values, and 128 is added to the second stage delay values.

     This means that if you set a first stage delay value of 16, when it is actually send to the beamformer, it will
     become a delay of 32, which means that dipole will be disabled. The Kaelus delays do NOT work like that - use
     'edacmd --onlybfs=...' to enable and disable Kaelus beamformer inputs.

  """
  idelays, estruct = pointing.calc_delays(offsets=OFFSETS, az=az, el=el, strict=False, verbose=True, clipdelays=True, cpos=(0.0, 0.0, 0.0))
  return idelays


def sendDelays(idelays=None):
  stime = int(time.time() + 2)
  values = {TILEID: {'X': (None, None, 0.0, 0.0, idelays),
                     'Y': (None, None, 0.0, 0.0, idelays)
                     }
            }
  kproxy.notify(obsid=0, starttime=stime, stoptime=stime + 8, clientid='Kaelus', rclass='pointing', values=values)
  for clientid, proxy in bfproxies.items():
    proxy.notify(obsid=0, starttime=stime, stoptime=stime + 8, clientid=clientid, rclass='pointing', values=values)
