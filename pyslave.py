import logging
import socket
import threading
import time
import traceback

import Pyro4
import Pyro4.socketutil

loglevel = logging.DEBUG

# set up the logging
logger = logging.getLogger()
logger.setLevel(loglevel)

# Details for the MWA observation controller that we should register clients with
MASTERPORT = 19999
MASTERHOST = 'helios.mwa128t.org'

REFERENCEIP = '8.8.8.8'  # A host guaranteed to be visible on the network interface that we want the Pyro server to bind to


class Slave(object):
    """An instance of this class is the client that attaches to a pycontroller 'Master' object.
    """

    def __init__(self, clientid=None, rclass=None, port=None):
        """
        Creates a Slave object that will be registered with a PyController daemon to receive updates about the
        upcoming scheduled observations.

        :param clientid: The name of this client.
        :param rclass: A string, eg 'pointing' - defines the format of the 'values' argument passed to notify() calls by PyController.
        :param port: Network port to listen on when the request handler is running.
        """
        if port:
            self.uri = ''
            self.port = port
        else:
            self.uri = None
            self.port = None
        self.pyro_daemon = None
        self.exiting = False
        self.rclass = rclass
        self.sthread = None
        self.clientid = clientid
        self.master = Pyro4.Proxy(uri='PYRO:pycontroller@%s:%s' % (MASTERHOST, MASTERPORT))
        self.started = False  # Has the Pyroserver 'startup()' function been called?
        self.running = False  # Is the Pyroserver startup completed, so the server is running now?
        self.registered = False  # Is the slave connected to a PyController instance?
        self.heartbeat_time = time.time()  # Timestamp of last method call

    @Pyro4.expose
    def ping(self):
        """
        Called remotely over the network.

        Returns immediately. Called to verify (to the controller) that the slave is alive.
        :return: True
        """
        logger.debug('ping() called on pyslave.Slave()')
        return True

    @Pyro4.expose
    def heartbeat(self):
        """
           Called remotely over the network.

           Returns immediately. Called to verify (to the slave) that the controller is alive.
           :return: None
        """
        logger.debug('heartbeat() called on pyslave.Slave()')
        self.heartbeat_time = time.time()
        return

    def startup(self):
        """Start the Pyro4 request loop running in a background thread, for the slave object.
        """
        self.sthread = threading.Thread(target=self._ServePyroRequests, name='SlavePyroDaemon:%s' % self.clientid)
        self.sthread.daemon = True
        self.sthread.start()
        self.started = True

    def register(self, tiles=None, gpstime=True, uri=None, control=False):
        """
        Called locally, to register this slave with a remote PyController process somewhere else on the network.

        :param tiles: A list of integers - the tile number/s that this slave process is physically controlling.
        :param gpstime: Boolean - True if starttime values passed to notify should be in GPS seconds, False for unix timestamps.
        :param uri: The Pyro4 URI string that the controller should use to talk to this slave process.
        :param control: True if this process is to be considered 'in control' of the tile number/s specified.
        :return: None
        """
        if tiles is None or self.rclass is None:
            logger.error('rclass and tiles must both be defined to register for notifications')
            return False
        if not self.started:
            logger.error('Slave object must have startup() called before registering for notifications')
            return False

        if uri is None:
            self.master.register(clientid=self.clientid, rclass=self.rclass, tiles=tiles, uri=self.uri, gpstime=gpstime,
                                 control=control)
        else:  # Pass an altered URI to the master, eg for use when port forwarding
            self.master.register(clientid=self.clientid, rclass=self.rclass, tiles=tiles, uri=uri, gpstime=gpstime,
                                 control=control)
            self.uri = uri
        self.registered = True

    def deregister(self):
        """
        Called locally, to de-register this slave from the remote PyController, so we don't receive notify() calls.
        """
        if (not self.registered):
            logger.error("Can't deregister %s" % self.uri)
            return False
        self.master.deregister(uri=self.uri)
        self.registered = False

    def deregall(self):
        """De-register any clients with the same clientid as this client, in case previous incarnations
           had different URIs (eg, same client ID but different port number).
        """
        return self.master.deregbyname(self.clientid)

    @Pyro4.expose
    def notify(self, obsid=None, starttime=None, stoptime=None, clientid=None, rclass=None, values=None):
        """Called remotely by the master object when registered tile properties change.

           This is a stub, to be overriden by sub-classes.

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
                              the key, and a value whose contents depends on the registration class ('pointing', etc).

           :return:          A tuple of (clientid, obsid, starttime, result) where 'result' depends on the registration
                              class ('pointing', etc)., and the other items are defined above.
        """
        logger.info("Notify called on slave at %s" % self.uri)
        logger.info("obsid=%s, starttime=%s, clientid=%s, rclass=%s, values=%s" % (obsid, starttime, clientid, rclass, values))
        if starttime != obsid:  # It's a unix time stamp, not gpstime
            now = time.time()
        else:
            now = time.time() - 315964783  # Hack conversion to gpsseconds - this method will be overridden anyway
        if starttime > now:
            logger.debug('Sleeping for %d seconds' % (starttime - now))
            time.sleep(starttime - now)
        else:
            logger.critical('ERROR! Notification arrived after nominal start time: %s > %s' % (now, starttime))
        logger.info("Notify finished.")
        return self.clientid, obsid, starttime, True

    def _ServePyroRequests(self):
        """When called, start serving Pyro requests. Method will not ever exit.
        """
        iface = None
        logger.info('Getting interface address for pycontroller Pyro server')
        while (iface is None) and not self.exiting:
            try:
                iface = Pyro4.socketutil.getInterfaceAddress(REFERENCEIP)  # What is the network IP of this receiver?
            except socket.error:
                logger.info("Network down, can't start pycontroller slave Pyro server, sleeping for 10 seconds")
                if not self.exiting:
                    time.sleep(10)

        while not self.exiting:
            logger.info("Starting pycontroller slave Pyro4 server")
            try:
                if (self.uri is None) or (self.port is None):
                    # just start a new daemon on a random port
                    self.pyro_daemon = Pyro4.Daemon(host=iface)
                    self.port = int(self.pyro_daemon.locationStr.split(':')[1])
                    # register the object in the daemon
                    self.uri = str(self.pyro_daemon.register(self, objectId=self.clientid))
                else:
                    # Use the same port number, so we guarantee the URI stays the same
                    self.pyro_daemon = Pyro4.Daemon(host=iface, port=self.port)
                    # register the object in the daemon
                    self.uri = self.pyro_daemon.register(self, objectId=self.clientid)
                logger.info('pycontroller slave daemon registered as %s' % self.uri)
            except:
                if not self.exiting:
                    logger.error("Exception in pycontroller slave Pyro4 startup. Retrying in 10 sec: %s" % (traceback.format_exc(),))
                    time.sleep(10)
                else:
                    logger.info("Pyro4 slave server is exiting.")
                continue

            try:
                self.running = True
                self.pyro_daemon.requestLoop()
            except:
                self.running = False
                if not self.exiting:
                    logger.error("Exception in pycontroller slave Pyro4 server. Restarting in 10 sec: %s" % (traceback.format_exc(),))
                    time.sleep(10)
                else:
                    logger.info("Pyro4 slave server exiting.")


def clientidbit(uri=''):
    return str(uri).split(':')[1].split('@')[0]
