#!/usr/bin/env python

import atexit
import logging
import optparse
import signal
import subprocess
import sys
import time

import RPi.GPIO as GPIO
import smbus

# set up the logging

LOGLEVEL_CONSOLE = logging.DEBUG  # Logging level for console messages (INFO, DEBUG, ERROR, CRITICAL, etc)
LOGLEVEL_LOGFILE = logging.DEBUG  # Logging level for logfile
LOGLEVEL_REMOTE = logging.INFO
LOGFILE = "/tmp/edamc.log"


class MWALogFormatter(logging.Formatter):
    def format(self, record):
        return "%s: time %10.6f - %s" % (record.levelname, time.time(), record.getMessage())


mwalf = MWALogFormatter()

logger = logging.getLogger()
logger.setLevel(logging.DEBUG)

fh = logging.FileHandler(LOGFILE)
fh.setLevel(LOGLEVEL_LOGFILE)
fh.setFormatter(mwalf)

ch = logging.StreamHandler()
ch.setLevel(LOGLEVEL_CONSOLE)
ch.setFormatter(mwalf)

# rh = handlers.SysLogHandler(address=('mw-gw'))
# rh.setLevel(LOGLEVEL_REMOTE)
# rh.setFormatter(mwalf)

# add the handlers to the logger
logger.addHandler(fh)
logger.addHandler(ch)
# logger.addHandler(rh)

STATUS = None

# IO pin allocations as (enable, power) for each of the 8 RxDOC cards in this box, numbered 1-8
BFIOPINS = {1:(29, 16), 2:(26, 15), 3:(24, 13), 4:(23, 12), 5:(22, 11), 6:(21, 10), 7:(19, 8), 8:(18, 7)}

POWER12 = 31
POWER48 = 32
ALARMPOWER = 36
ALARM12 = 37
ALARM48 = 38
DIGOUT1 = 33
DIGOUT2 = 35
DIGIN1 = 40

BDICT = {False:'OFF', True:'ON'}

SIGNAL_HANDLERS = {}
CLEANUP_FUNCTION = None


class DOCstatus(object):
    # Device addresses for the eight LTC4151's. Note that these are _seven_ bit addresses,
    # corresponding to D0,D2,D4,...DE when the r/w bit is appended as bit 0 of the address.

    ADDRESSES = {1:0x68, 2:0x69, 3:0x6a, 4:0x6b, 5:0x6c, 6:0x6d, 7:0x6e, 8:0x6f}

    def __init__(self, bus=None, bfnum=0):
        assert (bfnum >= 1) and (bfnum <= 8)
        assert bus is not None
        self.bus = bus
        self.bfnum = bfnum
        self.current = 0.0
        self.voltage = 0.0
        self.enable = bool(GPIO.input(BFIOPINS[bfnum][0]))
        self.power = bool(GPIO.input(BFIOPINS[bfnum][1]))

    def check(self):
        try:
            data = self.bus.read_i2c_block_data(self.ADDRESSES[self.bfnum], 0, 4)
            self.current = ((data[0] * 16) + (data[1] / 16)) * 20e-6 / 0.02  # 20uV per ADU, through a 0.02 Ohm shunt
            self.voltage = ((data[2] * 16) + (data[3] / 16)) * 0.025  # 25mV per ADU
        except IOError:
            self.current = 0.0
            self.voltage = 0.0

    def __repr__(self):
        return "BF# %d: power=%3s, enable=%3s, voltage=%5.2f V, current=%4.0f mA" % (self.bfnum,
                                                                                     BDICT[self.power],
                                                                                     BDICT[self.enable],
                                                                                     self.voltage,
                                                                                     self.current * 1000)


class Status(object):
    def __init__(self):
        self.bfs = {}
        self.power12 = bool(GPIO.input(POWER12))
        self.power48 = bool(GPIO.input(POWER48))
        self.alarmpower = None
        self.alarm12 = None
        self.alarm48 = None
        bus = smbus.SMBus(1)  # Initialise the I2C bus and save the connection object
        for bfnum in range(1, 9):
            self.bfs[bfnum] = DOCstatus(bus=bus, bfnum=bfnum)
        self.check()

    def check(self):
        self.alarmpower = bool(GPIO.input(ALARMPOWER))
        self.alarm12 = bool(GPIO.input(ALARM12))
        self.alarm48 = bool(GPIO.input(ALARM48))

        pled = 1
        eled = 1
        for bfnum in range(1, 9):
            self.bfs[bfnum].check()
            if not GPIO.input(BFIOPINS[bfnum][1]):
                pled = 0
            if not GPIO.input(BFIOPINS[bfnum][0]):
                eled = 0
        GPIO.output(DIGOUT1, pled)
        GPIO.output(DIGOUT2, eled)

    def __repr__(self):
        rets = "EDA Status: 12V=%3s (Alarm=%3s),    48V=%3s (Alarm=%3s)\n" % (BDICT[self.power12], BDICT[self.alarm12],
                                                                              BDICT[self.power48], BDICT[self.alarm48])
        rets += "  Beamformers:\n"
        for bfnum in range(1, 9):
            rets += '    ' + repr(self.bfs[bfnum]) + '\n'
        return rets


def init():
    """Initialise IO pins for power/enable control with all 8 beamformers,
       and create the global STATUS object.
    """
    global STATUS
    GPIO.setmode(GPIO.BOARD)  # Use board connector pin numbers to specify I/O pins
    GPIO.setwarnings(False)
    GPIO.setup(POWER12, GPIO.OUT)
    GPIO.setup(POWER48, GPIO.OUT)
    GPIO.setup(ALARMPOWER, GPIO.IN)
    GPIO.setup(ALARM12, GPIO.IN)
    GPIO.setup(ALARM48, GPIO.IN)
    GPIO.setup(DIGOUT1, GPIO.OUT)
    GPIO.setup(DIGOUT2, GPIO.OUT)
    GPIO.setup(DIGIN1, GPIO.IN)
    for i in range(1, 9):
        enable, power = BFIOPINS[i]
        GPIO.setup(enable, GPIO.OUT)
        GPIO.setup(power, GPIO.OUT)
    STATUS = Status()


def get_hostname():
    if sys.version_info.major == 2:
        fqdn = subprocess.check_output(['hostname', '-A'], shell=False)
    else:
        fqdn = subprocess.check_output(['hostname', '-A'], shell=False).decode('UTF-8')
    return fqdn.split('.')[0]


def turn_on_12():
    GPIO.output(POWER12, 1)
    time.sleep(0.1)
    STATUS.power12 = bool(GPIO.input(POWER12))
    return (STATUS.power12 is True)


def turn_off_12():
    GPIO.output(POWER12, 0)
    time.sleep(0.1)
    STATUS.power12 = bool(GPIO.input(POWER12))
    return (STATUS.power12 is False)


def turn_on_48():
    if True in [x.enable for x in STATUS.bfs.values()]:
        for bfnum in range(1, 9):
            disable_doc(bfnum)
    if True in [x.power for x in STATUS.bfs.values()]:
        for bfnum in range(1, 9):
            turnoff_doc(bfnum)
    time.sleep(0.2)
    GPIO.output(POWER48, 1)
    time.sleep(0.1)
    STATUS.power48 = bool(GPIO.input(POWER48))
    return (STATUS.power48 is True)


def turn_off_48():
    if True in [x.enable for x in STATUS.bfs.values()]:
        for bfnum in range(1, 9):
            disable_doc(bfnum)
        time.sleep(1)  # Wait for a bit after disabling DOC cards, before turning off their power
    if True in [x.power for x in STATUS.bfs.values()]:
        for bfnum in range(1, 9):
            turnoff_doc(bfnum)
    GPIO.output(POWER48, 0)
    time.sleep(0.1)
    STATUS.power48 = bool(GPIO.input(POWER48))
    return (STATUS.power48 is False)


def turnon_doc(bfnum=0):
    if bfnum < 1 or bfnum > 8:
        logger.error("Invalid bfnum - must be 1-8")
        return None
    else:
        if not STATUS.power48:
            logger.error("Must turn on main 48V power before attempting to power up a DOC card")
            return None
        if STATUS.bfs[bfnum].enable:
            disable_doc(bfnum)
            time.sleep(0.1)
        GPIO.output(BFIOPINS[bfnum][1], 1)
        time.sleep(0.1)
        STATUS.bfs[bfnum].power = bool(GPIO.input(BFIOPINS[bfnum][1]))
        STATUS.check()
        return (STATUS.bfs[bfnum].power is True)


def turnoff_doc(bfnum=0):
    if bfnum < 1 or bfnum > 8:
        logger.error("Invalid bfnum - must be 1-8")
        return None
    else:
        disable_doc(bfnum)
        time.sleep(0.1)
        GPIO.output(BFIOPINS[bfnum][1], 0)
        time.sleep(0.1)
        STATUS.bfs[bfnum].power = bool(GPIO.input(BFIOPINS[bfnum][1]))
        STATUS.check()
        return (STATUS.bfs[bfnum].power is False)


def enable_doc(bfnum=0):
    if bfnum < 1 or bfnum > 8:
        logger.error("Invalid bfnum - must be 1-8")
        return None
    else:
        if not STATUS.power48:
            logger.error("Must turn on main 48V power, and power to a DOC card, before it can be enabled")
            return None
        if not STATUS.bfs[bfnum].power:
            logger.error("Must turn on power to a doc before enabling it")
            return None
        GPIO.output(BFIOPINS[bfnum][0], 1)
        time.sleep(0.01)
        STATUS.bfs[bfnum].enable = bool(GPIO.input(BFIOPINS[bfnum][0]))
        STATUS.check()
        return (STATUS.bfs[bfnum].enable is True)


def disable_doc(bfnum=0):
    if bfnum < 1 or bfnum > 8:
        logger.error("Invalid bfnum - must be 1-8")
    else:
        GPIO.output(BFIOPINS[bfnum][0], 0)
        time.sleep(0.01)
        STATUS.bfs[bfnum].enable = bool(GPIO.input(BFIOPINS[bfnum][0]))
        STATUS.check()
        return (STATUS.bfs[bfnum].enable is False)


def turnon():
    turn_on_48()
    time.sleep(0.5)
    for bfnum in range(1, 9):
        turnon_doc(bfnum)
        time.sleep(0.1)
        enable_doc(bfnum)


def turnoff():
    for bfnum in range(1, 9):
        disable_doc(bfnum)
        time.sleep(0.1)
        turnoff_doc(bfnum)
    turn_off_48()


def cleanup():
    logger.info("Turning off all eight beamformers, and 48V supplies")
    turnoff()
    logger.info("Cleaning up GPIO library")
    GPIO.cleanup()


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

    (options, args) = parser.parse_args()

    init()
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
            logger.error(
                "Invalid hostname %s - should be of the form 'edaNmc' or 'edaNcom', where N is an integer" % hostname)
            sys.exit(-1)
        if func != 'mc':
            logger.error(
                "Can't start power/enable/voltage/current monitoring on a comms/pointing device. Run on edaNmc host instead")
            sys.exit(-2)

    logger.info("Turning on 48V supplies and all eight beamformers")
    turnon()

    while True:
        STATUS.check()
        logger.info(str(STATUS))
        time.sleep(10)
