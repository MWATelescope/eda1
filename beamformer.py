
import logging
import sys
import threading
import time

__docformat__ = 'reStructuredText'

# Bitfield constants in control byte
SYN = 128
ACK = 64
FIN = 32
RST = 16
SN = 8
AN = 4
EOR = 2
SO = 1

loglevel = logging.DEBUG

# set up the logging
logger = logging.getLogger()
logger.setLevel(loglevel)


class Beamformer(object):
    """
    This class is used to control the operation one polarisation of a Kaelus beamformer.
    The beamformer is connected using a USB to serial FTDI chip. On the creation of a beamformer object a serial port needs to be provided.

    - **parameters**::

            **pol=None**
                Serial port object generated with the PySerial class.

            **logging=1**
                This attribute controls if the information of packets is printed to the terminal.

            **CombinerLNA=0**
                This attribute is used to store the intended value for the combiner LNA, **0 is Disable**, **1 is Enable**.

            **CombinerLNARead=0**
                This attribute stores the value for the last read setting for the combiner LNA, **0 is Disabled**, **1 is Enabled**

            **CombinerTemperature=0**
                This attribute stores the value for the last read temperature of the combiner LNA in degrees centigrade.

            **CombinerCurrent=0**
                This attribute stores the values for the last read current of the combiner LNA in milliamps.

            **AntennaCurrents=[0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0]**
                This attribute stores the last read values of the antenna currents for all channels in milliamps.

            **LNA1Currents=[0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0]**
                This attribute stores the last read values of the LNA1 currents for all channels in milliamps.

            **LNA2Currents=[0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0]**
                This attribute stores the last read values of the LNA2 currents for all channels in milliamps.

            **DelayBoardTemperatures=[0,0,0,0]**
                This attribute stores the last read values of the temperatures of the 4 delayboards in degrees centigrade.

            **ChannelEnable= [0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0]**
                This attribute stores the *intended* values of the enabled channels of all 16 channels, **0 is Disabled**, **1 is Enabled**. This function uses calibration data.

            **ChannelEnableRead=[]**
                This attribute stores the *last read* values of the enabled channels of all 16 channels, **0 is Disabled**, **1 is Enabled**.

            **ChannelDelay= [255,255,255,255,255,125,255,255,126,255,255,255,255,255,255,255]**
                This attribute stores the *intended* values delay switch value of all 16 channels, **min: 0 - max: 255**. This function uses calibration data.

            **ChannelDelayRead=[]**
                This attribute stores the *last read* values delay switch value of all 16 channels, **min:0 - max: 255**.

            **ChannelEnableDiag=[0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0]**
                This attribute stores the *intended* values of the enabled channels of all 16 channels. This function uses raw data.**0x01 is LNA2**, **0x02 is LNA1**, **0x04 is output**, **0x08 is input**, **0x10 is antenna LNA**.

            **ChannelEnableReadDiag=[]**
                This attribute stores the *last read* values of the enabled channels of all 16 channels. This is the diagnostics version which stores the individual switch values. **0x01 is LNA2**, **0x02 is LNA1**, **0x04 is output**, **0x08 is input**, **0x10 is antenna LNA**.

            **ChannelDelayDiag=[0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0]**
                This attribute stores the *intended* values of the delay switch of all 16 channels. This function uses raw data. **min: 0 - max: 255**.

            **ChannelDelayReadDiag=[]**
                This attribute stores the *last Read* values of the delay switch of all 16 channels. This function uses raw data. **min: 0 - max: 255**.

            **ChannelAttenuators=[0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0]**
                This attribute stores the *intended* values of the attenuator of all 16 channels, **min: 0 - max: 255**.

            **ChannelAttenuatorsRead=[]**
                This attribute stores the *last read* values of the attenuator of all 16 channels, **min: 0 - max: 255**.

            **AlarmStatus=''**
                This string contains the last read alarm status of the beamformer.

            **PollStatus=''**
                This string contains the last read poll status of the beamformer.

            **NumberOfAlarms=0**
                This attribute contains the amount of detected alarms.

            **TimeSinceLastPoll=0**
                This attribute contains the time since the last poll command was called in ms.

            **BeamformerIsReady=1**
                This attribute contains the flag that indicates if the beamformer is ready.

            **SerialNumbers=['','','','']**
                This attribute contains the strings of the serial numbers of the four delay boards.

            **FirmwareVersion=''**
                This attribute contains a string of the version of the firmware of the beamformer.

            **PartNumber=''**
                This attribute contains a string of the part number of the beamformer.

            **BFSerial=''**
                This attribute contains a string of the serial number of the beamformer.

            **CalDate=''**
                This attribute contains a string of the calibration date of the beamformer.

            **ActiveBoards=[0,0,0,0]**
                This attribute contains the boards that are active, **0 is Inactive, 1 is Active**.

            **GainMax=[]**
                This attribute contains the maximum gain of all channels in dB.

            **GainMin=[]**
                This attribute contains the minimum gain of all channels in dB.

            **GainCal=[]**
                This attribute contains the calibrated gain of all channels **min: 0 - max: 255**.

            **control=0**
                This attribute contains the control byte used at the start of a package after the beginflag.

            **state=0**
                This attribute contains ?????.

            **Established=0**
                This attribute contains the flag indicating if the connection is established.

            **AckNumber=0**
                This attribute contains the current Acknowledge Number.

            **SequenceNumber=0**
                This attribute contains the current Sequence Number.

            **ACK=0**
                This attribute contains the current Ack flag.

            **SYN=0**
                This attribute contains the current SYN flag.

            **RST=0**
                This attribute contains the current RST flag.

            **FIN=0**
                This attribute contains the current FIN flag.

            **EOR=0**
                This attribute contains the current FIN flag.

            **SO=0**
                This attribute contains the current FIN flag.

            **Message=[]**
                This attribute contains the stored message ready for sending.

            **LastMessage=[]**
                This attribute contains the last stored message ready for sending.

            **MessageAddendum=[]**
                This attribute contains the addition of a message if the packet to be send is a long one.

            **LastByte=-1**
                This attribute contains the last read byte from the serial receiver buffer.

            **LastCommand=0**
                This attribute contains the last issued command.

            **LastRxCommand=0**
                This attribute contains the last command received.

            **RxLength=0**
                This attribute contains length of the received message.

            **RxMessage=[]**
                This attribute contains last received message.

            **Write**(data)
                This method is used to write a message to the serial port of the beamformer.

                - **Parameters**:
                    -  **data**: datastream of any length. The first element of this array is the first byte sent. The data array element should contain values between 0 and 255.

                - **Returns**:
                    -  **Nothing**

            **ProcessShortPacket**()
                This method is used to process a packet which is received in the buffer. The message is then saved in the attribute RxMessage. This function will automatically read the control flags and will also
                adjust the Ack number and the seq number so the next packet that is sent will heve the correct values for these. It will also run the checksum to see if the packet is correct.

                - **Parameters**:
                    -  **None**

                - **Returns**:
                    -  **Nothing**

            **OpenConnection**()
                This method is used to open a connection with the beamformer. In order to send data and ensure normal operation, a connection has to be setup before operations can be send to the beamformer.
                After a short time period, approximately three seconds the beamformer will timeout and a new connection has to be set up.

                - **Parameters**:
                    -  **None**

                - **Returns**:

                    -  **Nothing**
    """

    def __init__(self, pol, name=None, incapture=None, outcapture=None):
        self.pol = pol
        self.name = name
        self.incapture = incapture    # Either None, or a file-like object that all incoming bytes should be written to for debugging
        self.outcapture = outcapture  # Either None, or a file-like object that all outgoing bytes should be written to for debugging
        self.lock = threading.RLock()
        self.closetime = 0
        self.pol.timeout = 5
        self.CombinerLNA = 0
        self.CombinerLNARead = 0
        self.CombinerTemperature = 0
        self.CombinerCurrent = 0
        self.AntennaCurrents = [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]
        self.LNA1Currents = [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]
        self.LNA2Currents = [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]
        self.DelayBoardTemperatures = [0, 0, 0, 0]
        self.ChannelEnable = [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]
        self.ChannelEnableRead = []
        self.ChannelDelay = [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]
        self.ChannelDelayRead = []
        self.ChannelEnableDiag = [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]
        self.ChannelEnableReadDiag = []
        self.ChannelDelayDiag = [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]
        self.ChannelDelayReadDiag = []
        self.ChannelAttenuators = [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]
        self.ChannelAttenuatorsRead = []
        self.AlarmStatus = ''
        self.PollStatus = ''
        self.NumberOfAlarms = 0
        self.TimeSinceLastPoll = 0
        self.BeamformerIsReady = 1
        self.SerialNumbers = ['', '', '', '']
        self.FirmwareVersion = ''
        self.PartNumber = ''
        self.BFSerial = ''
        self.CalDate = ''
        self.ActiveBoards = [0, 0, 0, 0]
        self.GainMax = []
        self.GainMin = []
        self.GainCal = []
        self.state = 0
        self.Established = 0
        self.AckNumber = 0
        self.SequenceNumber = 0
        self.ACK = 0
        self.SYN = 0
        self.RST = 0
        self.FIN = 0
        self.EOR = 0
        self.SO = 0
        self.Message = []
        self.LastMessage = []
        self.MessageAddendum = []
        self.LastByte = -1
        self.LastCommand = 0
        self.LastRxCommand = 0
        self.RxLength = 0
        self.RxMessage = []
        self.leftovers = ''    # String containing any bytes read from the device after the end of the last packet processed. These will be pre-pended to the next packet.

    def Write(self, data):
        with self.lock:
            if (len(data) > 5):
                self.LastCommand = ord(data[5])
            else:
                self.LastCommand = ord(data[2])
            if data[0] == '\x7e':    # Don't escape the leading 0x7e character if it's at the start of a packet
                data = '\x7e' + data[1:].replace('\x7d', '\x7d\x5d').replace('\x7e', '\x7d\x5e')
            else:
                data = data.replace('\x7d', '\x7d\x5d').replace('\x7e', '\x7d\x5e')
            if sys.version_info.major > 2:
                data = data.encode('latin-1')
            self.pol.write(data)
            logger.debug("(%s) wrote '%s'" % (self.name, ' '.join([hex(ord(c)) for c in data])))
            if self.outcapture:
                self.outcapture.write(data)
                self.outcapture.flush()

    def GetPacket(self):
        with self.lock:
            data = ''
            gotpacket = False
            timeouts = 0
            totlength = 5
            while not gotpacket:
                inchars = ''
                while not inchars:
                    inchars = self.pol.read(totlength - len(data))
                    if sys.version_info.major > 2:
                        inchars = inchars.decode('latin-1')
                    logger.debug("(%s) Got '%s'" % (self.name, ' '.join([hex(ord(c)) for c in inchars])))
                    if not inchars:
                        timeouts += 1
                        if timeouts >= 2:
                            return ''    # Give up after two timouts, equals 10 seconds
                if self.incapture:
                    self.incapture.write(inchars)
                    self.incapture.flush()
                if inchars[-1] == '\x7d':    # If the last byte is an escape character
                    data += (self.leftovers + inchars[:-1])   # Put all but the escape character into 'data'
                    self.leftovers = inchars[-1]              # Save the escape character (0x7d) to add when we get more bytes in
                else:
                    data += self.leftovers + inchars     # Otherwise add the new chars to data
                    self.leftovers = ''                  # and indicate that we aren't waiting on the 2nd byte in an escape pair

                if '\x7e' in data:
                    data = data[data.find('\x7e'):]    # Strip off any characters before the start of the packet
                else:
                    data = ''

                if len(data) < 5:
                    continue     # We definitely don't have enough bytes for even a short packet yet

                RxLength = ord(data[3])            # If 0, this is a short packet (5 bytes). If non zero, the total length is RxLength + 5 (initial short packet) + 2 (final checksum), plus 1 for each 0x7d in the packet
                if RxLength == 0:   # short packet
                    totlength = 5 + data.count('\x7d')   # Add one for each 0x7d escape character, because this is a pair of bytes on the wire representing one byte in the packet
                else:
                    totlength = 7 + RxLength + data.count('\x7d')   # Add one for each 0x7d escape character, because this is a pair of bytes on the wire representing one byte in the packet

                if len(data) >= totlength:
                    gotpacket = True

            self.leftovers = data[totlength:]  # Save any bytes after the packet, to be pre-pended to the next packet read by this function.
            return data[:totlength].replace('\x7d\x5e', '\x7e').replace('\x7d\x5d', '\x7d')   # Return the escaped data. This will be a string of length 5, or length 7 + RxLength.

    def ProcessPacket(self):
        with self.lock:
            self.ACK = False
            self.SYN = False
            self.FIN = False
            self.RST = False
            self.EOR = False
            self.SO = False
            gotreply = False
            self.RxMessage = ''
            data = self.GetPacket()    # Read a complete packet (long or short) and return it as a string with all escape characters processed.
            logger.debug("(%s) Processing new packet: '" % self.name + ' '.join([hex(ord(c)) for c in data]) + "'")
            if len(data) < 5:
                logger.error("(%s) Less than 5 bytes received." % self.name)
                return     # We didn't get a full packet.

            if (self.ComputeChecksum8(data[1:4]) != data[4]):
                logger.error("(%s) Short 3-byte checksum invalid, Error" % self.name)
#                return

            Control = ord(data[1])     # data[0] is the 0x7e packet start, data[1] is the control byte
            self.SYN = (Control & SYN == SYN)
            self.ACK = (Control & ACK == ACK)
            self.FIN = (Control & FIN == FIN)
            self.RST = (Control & RST == RST)
            sn = (Control & SN == SN)
            an = (Control & AN == AN)
            self.EOR = (Control & EOR == EOR)
            self.SO = (Control & SO == SO)
            if sn:
                if an:                        # print 'SN & AN'
                    self.AckNumber = 0
                    self.SequenceNumber = 1
                else:                         # print 'SN'
                    self.AckNumber = 0
                    self.SequenceNumber = 0
            else:
                if an:                        # print 'AN'
                    self.AckNumber = 1
                    self.SequenceNumber = 1
                else:                         # print 'nothing'
                    self.AckNumber = 1
                    self.SequenceNumber = 0

            self.RxLength = ord(data[3])
            if self.RxLength > 0:
                rxmessage = data[5:]
                self.RxMessage = [ord(c) for c in rxmessage]
                assert len(rxmessage) == (self.RxLength + 2)    # Payload length doesn't include 2-byte payload checksum
                csc = self.ComputeChecksum16(rxmessage[:-2])
                if csc != rxmessage[-2:]:
                    logger.error("(%s) Long packet checksum error" % self.name)
#                    return
                self.LastRxCommand = self.RxMessage[0]
            else:
                self.LastRxCommand = ord(data[2])

            if (self.LastCommand == self.LastRxCommand):
                return True     # we got the right packet as a reply
            else:
                logger.error("(%s) Received command %s, last command sent was %s" % (self.name, hex(self.LastRxCommand), hex(self.LastCommand)) )
                return False    # Wrong packet, we need to close and re-open the connection

    def OpenConnection(self):
        with self.lock:
            now = time.time()
            if (now - self.closetime) < 2.0:             # Wait until 2 seconds after the device had it's last CloseConnection() call.
                logger.info("(%s) Waiting until 2 seconds after last CloseConnection()" % self.name)
                time.sleep(2.0 - (now - self.closetime))
            self.pol.flushInput()
            self.pol.flushOutput()
            logger.info('(%s) Opening connection' % self.name)
            self.Write('\xa5\xa5\xa5')     # Send bytes to confirm the version of the serial communication link
            timeouts = 0
            data = ''
            while len(data) < 3:
                inchars = self.pol.read()
                if sys.version_info.major > 2:
                    inchars = inchars.decode('latin-1')
                data += inchars
                if not inchars:
                    timeouts += 1
                    if timeouts >= 2:
                        return ''    # Give up after two timouts, equals 10 seconds

            if self.incapture:
                self.incapture.write(data)
                self.incapture.flush()
            if (chr(0x82) * 3) in data:  # Check for the correct response
                logger.debug('(%s) version OK' % self.name)
            else:
                logger.error('(%s) Invalid Version Response: %s' % (self.name, ' '.join([hex(ord(c)) for c in data]) ))
            control = self.getControlByte(flags=SYN)     # Send a SYN to indicate a set up a connection
            message = self.CompileSmallMessage(control=control)
            logger.debug("(%s) Writing SYN packet" % self.name)
            self.Write(message)

            ok = self.ProcessPacket()        # check for the response
            logger.debug("(%s) Writing ACK packet" % self.name)
            self.SendAck()              # send an acknowlegdement
#            ok = self.ProcessPacket()        # process packet to acquire update the acknumber and seqnumber

    def CloseConnection(self):
        """
    
        This method is used to close the connection with the beamformer. Closing the connection is necessary to make sure that the beamformer does not behave unpredictable if you try to again initiate a connection.
        
        - **Parameters**:
        
            -  **None**
            
        - **Returns**:

            -  **Nothing**
            
        """        
        with self.lock:
            control = self.getControlByte(flags=(ACK + FIN), sn=self.SequenceNumber, an=self.AckNumber)      # send a FIN Packet
            message = self.CompileSmallMessage(control=control)
            logger.debug("(%s) Closing connection" % self.name)
            self.Write(message)
            ok = self.ProcessPacket()              # check the response
            logger.debug("(%s) Writing ACK packet" % self.name)
            self.SendAck()                    # send ACK
#            time.sleep(2)
            self.closetime = time.time()   # Record when this connection was closed, so we don't try to re-open it too soon.
            logger.info('(%s) Closed connection' % self.name)

    def SendAck(self):
        """

        This method will send an ACK package.

        - **Parameters**:

            -  **None**

        - **Returns**:

            -  **Nothing**

        """
        with self.lock:
            control = self.getControlByte(flags=(ACK), sn=self.SequenceNumber, an=self.AckNumber)
            self.Message = self.CompileSmallMessage(control=control, command=0)
            self.Write(self.Message)
#            ok = self.ProcessPacket()
            logger.debug("(%s) Sent Ack" % self.name)
        return True

    def Reconnect(self):
        logger.error("(%s) COMMS ERROR - Disconnecting and reconnecting to fix." % self.name)
        self.CloseConnection()
        time.sleep(3)
        self.OpenConnection()

    def DoCommand(self):
        ok = False
        tries = 0
        with self.lock:
            while (not ok) and (tries < 10):
                tries += 1
                self.Write(self.Message)            # send the poll message
                ok = self.ProcessPacket()                # process received data
                if not ok:
                    self.Reconnect()
        return ok

    def PrintInfo(self, diag):
        """
    
        This method is used to request all the info from the beamformer. The resulting information is the printed, so the user can see the current status of the beamformer.
        THe information printed contains serial numbers, versions, currents, and channel settings. It also contains the alarmstatus. 
        
        - **Parameters**:
        
            -  **diag:** Determine if the diagnostics info has to be printed or the calibrated info. 1 for diagnostics and 0 for calibrated.
            
        - **Returns**:

            -  **Nothing**
            
        """    
        with self.lock:
            Enable = {0:'Disabled', 1:'Enabled'}
            EnableDiag = {0:'', 1:'LNA1', 2:'LNA2', 4:'Output', 8:'Input', 16:'Antenna'}
            self.Poll()                 # poll to get a quick status
            self.ReadAlarms()           # read the alarm status
            self.GetDelayBoardInfo()    # get the info from all the delayboards
            self.GetFirmwareVersion()   # get the firmware version
            self.GetPartNumber()        # get the part number
            self.GetBFSerial()          # get the serial number of the beamformer
            self.GetCalDate()           # get the calibration date
            if (diag):
                self.GetEnabledSwitchesDiag()
                self.GetDelaySwitchesDiag()
                self.GetChannelAttenuators()
            else:
                self.GetEnabledSwitches()       # get all the channel enable switches
                self.GetDelaySwitches()         # get all the values for the delay settings
            self.GetCombinerLNA()
            self.GetCombinerSensorData()
            self.GetSensorData()
            print('\n********************INFO******************************************')         # print everything
            print("Active delay boards: [%s]" % ', '.join([self.SerialNumbers[i] for i in range(0,4) if self.ActiveBoards[i]]))
            print('Firmware version %s, Part number: %s, Serial number: %s' % (self.FirmwareVersion,
                                                                               self.PartNumber,
                                                                               self.BFSerial))
            print('Calibrated on ' + self.CalDate)
            print('*******************ALARMS*****************************************')
            print(self.AlarmStatus)
            print('******************Combiner****************************************')
            print('Combiner LNA: %s   Current=%6.1f mA   Temp=%4.1f degC' % (Enable[self.CombinerLNARead],
                                                                             self.CombinerCurrent,
                                                                             self.CombinerTemperature))
            print('******************CHANNELS****************************************')
            if (diag):
                for i in range(0, 16):
                    print('Channel %2d  Enabled=[%s]  Delay=%3d  Atten=%3d  Currents=(Antenna:%5.1f, LNA1:%5.1f, LNA2:%5.1f) mA' % (i + 1,
                                                                                                                                    ', '.join([EnableDiag[self.ChannelEnableReadDiag[i] & mask] for mask in [1, 2, 4, 8, 16] if self.ChannelEnableReadDiag[i] & mask]),
                                                                                                                                    self.ChannelDelayReadDiag[i],
                                                                                                                                    self.ChannelAttenuators[i],
                                                                                                                                    self.AntennaCurrents[i],
                                                                                                                                    self.LNA1Currents[i],
                                                                                                                                    self.LNA2Currents[i]))
                    if ((i + 1) % 4 == 0):
                        print('Delay board temperature: ' + str(self.DelayBoardTemperatures[i // 4]) + ' degC')
                        print('-----------------')
            else:
                for i in range(0, 16):
                    print('Channel %2d  %8s  Delay=%3d  Currents=(Antenna:%5.1f, LNA1:%5.1f, LNA2:%5.1f) mA' % (i + 1,
                                                                                                                Enable[self.ChannelEnable[i]],
                                                                                                                self.ChannelDelay[i],
                                                                                                                self.AntennaCurrents[i],
                                                                                                                self.LNA1Currents[i],
                                                                                                                self.LNA2Currents[i]))
                    if ((i + 1) % 4 == 0):
                        print('Delay board temperature: ' + str(self.DelayBoardTemperatures[i // 4]) + ' degC')
                        print('-----------------')
        return True

    def ReadAll(self):
        """
    
        This method updates all the setting that can be read.
        
        - **Parameters**:
        
            -  **None**
            
        - **Returns**:

            -  **Nothing**
            
        """   
        with self.lock:
            self.Poll()                        # poll to get a quick status
            self.ReadAlarms()                  # read the alarm status
            self.GetDelayBoardInfo()           # get the info from all the delayboards
            self.GetFirmwareVersion()          # get the firmware version
            self.GetPartNumber()               # get the part number
            self.GetBFSerial()                 # get the serial number of the beamformer
            self.GetCalDate()                  # get the calibration date
            self.GetEnabledSwitchesDiag()
            self.GetDelaySwitchesDiag()
            self.GetChannelAttenuators()
            self.GetEnabledSwitches()          # get all the channel enable switches
            self.GetDelaySwitches()            # get all the values for the delay settings
            self.GetCombinerLNA()
            self.GetCombinerSensorData()
            self.GetSensorData()
        return True

    def Poll(self):
        """
    
        This method executes a poll command, and receives the information from the beamformer. The information that is obtained is stored in the attribute called PollStatus. It contains last reset state, if there are alarms and if the beamformer is ready.
        It also contains a field with the time since the last poll command was executed.
        
        - **Parameters**:
        
            -  **None**
            
        - **Returns**:

            -  **Nothing**
            
        """   
        with self.lock:
            control = self.getControlByte(flags=(ACK + SO), sn=self.SequenceNumber, an=self.AckNumber)            # set control flags
            self.Message = self.CompileSmallMessage(control=control, command=19)                           # command 0x13 command is the poll command
            ok = self.DoCommand()
            if not ok:
                return False
            self.TimeSinceLastPoll = (self.RxMessage[5] +
                                      self.RxMessage[4] << 8 +
                                      self.RxMessage[3] << 16 +
                                      self.RxMessage[2] << 24)      # get the time since last poll fields and interpret them
            self.BeamformerIsReady = self.RxMessage[1]
            state = self.RxMessage[6:10]
            self.PollStatus = self.InterpretPoll(state)           # Use the InterpretPoll function to determine which alarms and reset status is active.
            logger.debug("(%s) Polled" % self.name)
        return True

    def InterpretPoll(self, state):
        """

        This method interprets a given set of 4 bytes in order to determine if there are alarms, and if there are any of which type they are. Furthermore it determines the reset state.

        - **Parameters**:

            -  **state:** this is a bytearray of 4 bytes. It contains the bytes 6 to 10 of the payload from the poll response packet.

        - **Returns**:

            -  **PollMessage:** contains a string with the current alarm status and reset state

        """   
        # Create two dictionaries which describe which bit should give what kind of error
        AlarmChannels = {0:'', 1:'Channel 1 ', 2:'Channel 2 ', 4:'Channel 3 ', 8:'Channel 4 ', 16:'Channel 5 ', 32:'Channel 6 ', 64:'Channel 7 ', 128: 'Channel 8 ',
                         256:'Channel 9 ', 512:'Channel 10 ', 1024:'Channel 11 ', 2048:'Channel 12 ', 4096:'Channel 13 ', 8192:'Channel 14 ', 16384:'Channel 15 ', 32768:'Channel 16 ',
                         15:'Board 1 ', 240:'Board 2 ', 3840:'Board 3 ', 61440:'Board 4 '}
        ResetState = {0:'Reset: power on reset',
                      1:'Reset: Brown out reset',
                      2:'Reset: WDTTimedOUT',
                      4:'Reset: Software Reset',
                      8:'Reset: External Reset',
                      16:'Reset: Illegal OP reset',
                      32:'Reset TrapReset'}
        PollMessage = ''
        if (state[0] & 1):       # determine the alarm source
            PollMessage += 'Antenna LNA, '
        if (state[0] & 2):
            PollMessage += 'LNA 1, '
        if (state[0] & 4):
            PollMessage += 'LNA 2, '
        if (state[0] & 8):
            PollMessage += 'Delay board temperature, '
        if (state[0] & 16):
            PollMessage += 'Combiner LNA, '
        if (state[0] & 32):
            PollMessage += 'Combiner temperature, '
        if (state[0] & 64):
            PollMessage += 'All sources, '

        # TODO - handle aggregation into board1, board2, board3 and board4 if all four bits for that board are set, before/instead-of handling channels individually
        Ac = state[2] + (state[1] << 8)          # determine the alarm channel and compile the PollMessage string
        PollMessage += AlarmChannels[Ac & 1] + AlarmChannels[Ac & 2] + AlarmChannels[Ac & 4] + AlarmChannels[Ac & 8] + AlarmChannels[Ac & 16]
        PollMessage += AlarmChannels[Ac & 32] + AlarmChannels[Ac & 64] + AlarmChannels[Ac & 128] + AlarmChannels[Ac & 256] + AlarmChannels[Ac & 512]
        PollMessage += AlarmChannels[Ac & 1024] + AlarmChannels[Ac & 2048] + AlarmChannels[Ac & 4096] + AlarmChannels[Ac & 8192] + AlarmChannels[Ac & 16384]
        PollMessage += AlarmChannels[Ac & 32768] + ResetState[state[3]]
        return PollMessage
           
    def ReadAlarms(self):
        """
    
        This method reads the alarms from the beamformer. The alarms are then added to an alarmstring called AlarmStatus. This function uses the InterpretAlarms function to determine which alarms are invoked.
        
        - **Parameters**:
        
            -  **None**
            
        - **Returns**:

            -  **Nothing**
            
        """  
        with self.lock:
            self.AlarmStatus = ''            # clear alarmstatus
            control = self.getControlByte(flags=(ACK + SO), sn=self.SequenceNumber, an=self.AckNumber)
            self.Message = self.CompileSmallMessage(control=control, command=23)      # send the read alarms packet
            ok = self.DoCommand()
            if not ok:
                return False
            rxmessage = self.RxMessage[1:]         # remove first byte
            alarms = []
            for i in range(0, 16):
                if rxmessage[i] or rxmessage[i+16] or rxmessage[i+32]:
                    astr = "Channel %2d  Alarms:  " % (i + 1)
                    if rxmessage[i]:
                        astr += "Antenna LNA (%s)  " % self.InterpretAlarm(rxmessage[i])
                    if rxmessage[i + 16]:
                        astr += "LNA 1 (%s)  " % self.InterpretAlarm(rxmessage[i + 16])
                    if rxmessage[i + 32]:
                        astr += "LNA 2 (%s)  " % self.InterpretAlarm(rxmessage[i + 32])
                    alarms.append(astr)
            for dbnum in [1, 2, 3, 4]:
                if rxmessage[47 + dbnum]:
                    alarms.append('Delay board %d (%s)' % (dbnum, self.InterpretAlarm(rxmessage[47 + dbnum])))
            if rxmessage[52]:
                alarms.append('Combiner LNA Alarm (%s)' % self.InterpretAlarm(rxmessage[52]))
            if rxmessage[53]:
                alarms.append('Combiner Temp Alarm (%s)' % self.InterpretAlarm(rxmessage[53]))
            if not alarms:            # if no alarms are detected print 'no Alarms'
                self.AlarmStatus = 'No Alarms'
            else:
                self.AlarmStatus = '\n'.join(alarms)
            logger.debug("(%s) Retrieved alarm status" % self.name)
        return True

    def InterpretAlarm(self, state=0):
        """
    
        This method interprets a given byte so the right alarm can be determined.
        
        - **Parameters**:
        
            -  **state**: Byte of which the alarm status has to be determined.
            
        - **Returns**:

            -  **AlarmMessage**: String containing the alarm status of that byte.
            
        """  
        AlarmMessages = []
        if (state & 1):   # determine the alarm status
            AlarmMessages.append('Minor')
        if (state & 2):
            AlarmMessages.append('Major')
        if (state & 4):
            AlarmMessages.append('High Current')
        if (state & 8):
            AlarmMessages.append('Low Current')
        if (state & 16):
            AlarmMessages.append('High Temp')
        return ','.join(AlarmMessages)         # return the string
    
    def GetDelayBoardInfo(self):
        """
    
        This method requests delay board information of all the four delayboards. The method saves the serial number, maximum gain, minimum gain and calibrated gain in its respective attributes.
        
        - **Parameters**:
        
            -  **None** 
            
        - **Returns**:

            -  **Nothing**
            
        """  
        with self.lock:
            self.GainMax = []
            self.GainMin = []
            self.GainCal = []
            for j in range(0, 4):      # loop through the four delayboards
                control = self.getControlByte(flags=(ACK + EOR), sn=self.SequenceNumber, an=self.AckNumber)
                self.Message = self.CompileSmallMessage(control=control, command=0, length=2)
                self.MessageAddendum = chr(10) + chr(j)
                self.MessageAddendum += self.ComputeChecksum16(self.MessageAddendum)
                self.Message += self.MessageAddendum          # send a delayboardinfo request
                ok = self.DoCommand()
                if not ok:
                    return False
                rxmessage = self.RxMessage[1:]          # remove first byte
                self.ActiveBoards[j] = rxmessage[0]     # determine if board is active
                serialnum = ''.join([chr(x) for x in rxmessage[1:13]])
                self.SerialNumbers[j] = serialnum  # store the serial number in the 'SerialNumbers' attribute

                for i in range(0, 4):             # extract min,max and cal gain from the message.
                    self.GainMin.append((float(rxmessage[15 + (i * 2)]) + float(rxmessage[14 + (i * 2)] << 8)) / 1000)
                    self.GainMax.append((float(rxmessage[23 + (i * 2)]) + float(rxmessage[22 + (i * 2)] << 8)) / 1000)
                    self.GainCal.append(rxmessage[30 + i])
            logger.debug("(%s) Retrieved delay board information" % self.name)
        return True
        
    def GetFirmwareVersion(self):
        """
    
        This method requests the firmare version of the beamformer itself, and store this in the ''FirmwareVersion'' attribute.
        
        - **Parameters**:
        
            -  **None**
            
        - **Returns**:

            -  **Nothing**
            
        """  
        with self.lock:
            self.FirmwareVersion = ''
            control = self.getControlByte(flags=(ACK + SO), sn=self.SequenceNumber, an=self.AckNumber)
            self.Message = self.CompileSmallMessage(control=control, command=16)
            ok = self.DoCommand()
            if not ok:
                return False
            self.FirmwareVersion = ''.join([chr(x) for x in self.RxMessage[1:6]])
            logger.debug("(%s) Retrieved firmare version" % self.name)
        return True
            
    def GetPartNumber(self):
        """
    
        This method requests the part number of the beamformer itself, and store this in the ''PartNumber'' attribute.
        
        - **Parameters**:
        
            -  **None**
            
        - **Returns**:

            -  **Nothing**
            
        """  
        with self.lock:
            control = self.getControlByte(flags=(ACK + SO), sn=self.SequenceNumber, an=self.AckNumber)
            self.Message = self.CompileSmallMessage(control=control, command=17)
            ok = self.DoCommand()
            if not ok:
                return False
            self.PartNumber = ''.join([chr(x) for x in self.RxMessage[1:-2]])
            logger.debug("(%s) Retrieved part number" % self.name)
        return True
        
    def GetBFSerial(self):
        """
    
        This method requests the serial number of the beamformer itself, and store this in the ''BFSerial'' attribute.
        
        - **Parameters**:
        
            -  **None**
            
        - **Returns**:

            -  **Nothing**
            
        """  
        with self.lock:
            control = self.getControlByte(flags=(ACK + SO), sn=self.SequenceNumber, an=self.AckNumber)
            self.Message = self.CompileSmallMessage(control=control, command=18)
            ok = self.DoCommand()
            if not ok:
                return False
            self.BFSerial = ''.join([chr(x) for x in self.RxMessage[1:-2]])
            logger.debug("(%s) Retrieved serial number" % self.name)
        return True
            
    def GetCalDate(self):
        """
    
        This method requests the calibration date of the beamformer itself, and store this in the ''CalDate'' attribute.
        
        - **Parameters**:
        
            -  **None**
            
        - **Returns**:

            -  **Nothing**
            
        """ 
        with self.lock:
            control = self.getControlByte(flags=(ACK + SO), sn=self.SequenceNumber, an=self.AckNumber)
            self.Message = self.CompileSmallMessage(control=control, command=7)
            ok = self.DoCommand()
            if not ok:
                return False
            self.CalDate = '%2d-%2d-%4d' % (self.RxMessage[1], self.RxMessage[2], self.RxMessage[4] + (self.RxMessage[3] << 8))
            logger.debug("(%s) Retrieved calibration date" % self.name)
        return True
        
    def Reset(self):
        """
    
        This method performs a system reset by sending a reset command.
        
        - **Parameters**:
        
            -  **None**
            
        - **Returns**:

            -  **Nothing**
            
        """ 
        with self.lock:
            control = self.getControlByte(flags=(ACK + SO), sn=self.SequenceNumber, an=self.AckNumber)
            self.Message = self.CompileSmallMessage(control=control, command=1)
            ok = self.DoCommand()
            if not ok:
                return False
            logger.debug("(%s) Sent full reset" % self.name)
        return True
      
    def ResetCPLD(self):
        """
    
        This method resets the CPLD controlling the delay switches.
        
        - **Parameters**:
        
            -  **None**
            
        - **Returns**:

            -  **Nothing**
            
        """ 
        with self.lock:
            control = self.getControlByte(flags=(ACK + SO), sn=self.SequenceNumber, an=self.AckNumber)
            self.Message = self.CompileSmallMessage(control=control, command=24)
            ok = self.DoCommand()
            if not ok:
                return False
            logger.debug("(%s) Sent CPLD reset" % self.name)
        return True
    
    def ClearAllAlarms(self):
        """
    
        This method clears all the alarms present on the beamformer from a closed connection state.
        
        - **Parameters**:
        
            -  **None**
            
        - **Returns**:

            -  **Nothing**
            
        """
        with self.lock:
            self.Reset()
            self.ResetCPLD()
            self.Poll()
            self.ClearAlarms()
        return True

    def ClearAlarms(self):
        """
    
        This method clears all the alarms present on the beamformer.
        
        - **Parameters**:
        
            -  **None**
            
        - **Returns**:

            -  **Nothing**
            
        """ 
        with self.lock:
            control = self.getControlByte(flags=(ACK + EOR + SO), sn=self.SequenceNumber, an=self.AckNumber)
            self.Message = self.CompileSmallMessage(control=control, command=2)
            ok = self.DoCommand()
            if not ok:
                return False
            control = self.getControlByte(flags=(ACK + EOR), sn=self.SequenceNumber, an=self.AckNumber)
            self.Message = self.CompileSmallMessage(control=control, command=0, length=4)
            self.MessageAddendum = '\x02\x40\x00\x00'
            self.MessageAddendum += self.ComputeChecksum16(self.MessageAddendum)
            self.Message = self.Message + self.MessageAddendum
            ok = self.DoCommand()
            if not ok:
                return False
            logger.debug("(%s) Cleared alarms" % self.name)
        return True
        
    def UpdateSettings(self):
        """
    
        This method is used to update all the settings concerning the operation of the beamformer. This involves channel enable and delay settings.
        
        - **Parameters**:
        
            -  **None**
            
        - **Returns**:

            -  **Nothing**
            
        """ 
        with self.lock:
            self.Poll()
            self.SetEnabledSwitches()
            self.SetDelaySwitches()
            self.SetCombinerLNA(self.CombinerLNA)
            logger.debug("(%s) Settings Updated" % self.name)
        return True

    def UpdateSettingsDiagnostics(self):
        """
    
        This method is used to update all the settings concerning the operation of the beamformer in diagnostics mode. This involves channel enable and delay settings.
        
        - **Parameters**:
        
            -  **None**
            
        - **Returns**:

            -  **Nothing**
            
        """ 
        with self.lock:
            self.Poll()
            self.SetEnabledSwitchesDiag()
            self.SetDelaySwitchesDiag()
            self.SetChannelAttenuators()
            self.SetCombinerLNA(self.CombinerLNA)
        return True

    def UpdateDelays(self):
        """
    
        This method updates the written delays to the beamformer.
        
        - **Parameters**:
        
            -  **None**
            
        - **Returns**:

            -  **Nothing**
            
        """ 
        with self.lock:
            control = self.getControlByte(flags=(ACK + SO), sn=self.SequenceNumber, an=self.AckNumber)
            self.Message = self.CompileSmallMessage(control=control, command=39)    # send the update delay command
            ok = self.DoCommand()
            if not ok:
                return False
            logger.debug("(%s) Activated the new delay settings" % self.name)
        return True

    def SetCombinerLNA(self, state):
        """
    
        This method will set the combiner LNA with the state that is provided. 1 is enabled and 0 is disabled.
        
        - **Parameters**:
        
            -  **State:** The requested state of the combiner LNA 1 is enabled, 0 is disabled.
            
        - **Returns**:

            -  **Nothing**
            
        """ 
        with self.lock:
            control = self.getControlByte(flags=(ACK + EOR), sn=self.SequenceNumber, an=self.AckNumber)
            self.Message = self.CompileSmallMessage(control=control, command=0, length=2)
            self.MessageAddendum = '\x1f' + chr(state)    # [31,state]
            self.MessageAddendum += self.ComputeChecksum16(self.MessageAddendum)
            self.Message += self.MessageAddendum
            ok = self.DoCommand()
            if not ok:
                return False
            logger.debug("(%s) Enabled the combiner LNA" % self.name)
        return True
        
    def GetCombinerLNA(self):
        """
    
        This method requests the state of the combiner LNA. This state is then stored in the ''CombinerLNARead'' attribute.
        
        - **Parameters**:
        
            -  **None**
            
        - **Returns**:

            -  **Nothing**
            
        """ 
        with self.lock:
            control = self.getControlByte(flags=(ACK + SO), sn=self.SequenceNumber, an=self.AckNumber)
            self.Message = self.CompileSmallMessage(control=control, command=8)
            ok = self.DoCommand()
            if not ok:
                return False
            self.CombinerLNARead = self.RxMessage[1]          # Store the state in the correct attribute
            logger.debug("(%s) Retrieved combiner LNA setting" % self.name)
        return True

    def GetCombinerSensorData(self):
        """
    
        This method requests the temperature and current of the Combiner LNA and stores it in the CombinerTemperature and the CombinerCurrent attributes
        
        - **Parameters**:
        
            -  **None**
            
        - **Returns**:

            -  **Nothing**
            
        """ 
        with self.lock:
            control = self.getControlByte(flags=(ACK + SO), sn=self.SequenceNumber, an=self.AckNumber)
            self.Message = self.CompileSmallMessage(control=control, command=9)
            ok = self.DoCommand()
            if not ok:
                return False
            self.CombinerTemperature = float(self.RxMessage[4] + (self.RxMessage[3] << 8)) / 10.0
            self.CombinerCurrent = float(self.RxMessage[2] + (self.RxMessage[1] << 8)) / 10.0
            logger.debug("(%s) Retrieved combiner sensor data" % self.name)
        return True

    def GetSensorData(self):
        """
    
        This method requests the temperature and current of the 4 delayboards and stores them in the AntennaCurrents, LNA1Currents, LNA2Currents,and the DelayBoardTemperatures attributes
        
        - **Parameters**:
        
            -  **None**
            
        - **Returns**:

            -  **Nothing**
            
        """ 
        with self.lock:
            for j in range(0, 4):         # loop through all the delayboards
                control = self.getControlByte(flags=(ACK + EOR), sn=self.SequenceNumber, an=self.AckNumber)
                self.Message = self.CompileSmallMessage(control=control, command=0, length=2)
                self.MessageAddendum = chr(11) + chr(j)     # [11,j]
                self.MessageAddendum += self.ComputeChecksum16(self.MessageAddendum)
                self.Message += self.MessageAddendum
                ok = self.DoCommand()
                if not ok:
                    return False
                for i in range(0, 4):             # loop through all the delayboard channels and store the information in the correct attributes
                    self.LNA1Currents[i + (j * 4)] = float(self.RxMessage[2 + (i * 6)] + (self.RxMessage[1 + (i * 6)] << 8)) / 10.0
                    self.LNA2Currents[i + (j * 4)] = float(self.RxMessage[4 + (i * 6)] + (self.RxMessage[3 + (i * 6)] << 8)) / 10.0
                    self.AntennaCurrents[i + (j * 4)] = float(self.RxMessage[6 + (i * 6)] + (self.RxMessage[5 + (i * 6)] << 8)) / 10.0
                self.DelayBoardTemperatures[j] = float(self.RxMessage[26] + (self.RxMessage[25] << 8)) / 10.0
            logger.debug("(%s) 'Retrieved delay board sensor data" % self.name)
        return True
        
    def SetDelaySwitches(self):
        """
    
        This method sets the delay switches in calibrated mode, so the delay that is set is the desired delay, and the beamformer will compensate so the delay switches are set to the closest value.
        
        - **Parameters**:
        
            -  **None**
            
        - **Returns**:

            -  **Nothing**
            
        """    
        with self.lock:
            control = self.getControlByte(flags=(ACK + EOR), sn=self.SequenceNumber, an=self.AckNumber)
            self.Message = self.CompileSmallMessage(control=control, command=0, length=19)    # delayswitches command
            self.MessageAddendum = chr(33) + chr(0) + chr(16) + ''.join([chr(x) for x in self.ChannelDelay])     # [33,0,16]+self.ChannelDelay
            self.MessageAddendum += self.ComputeChecksum16(self.MessageAddendum)
            self.Message += self.MessageAddendum
            ok = self.DoCommand()
            if not ok:
                return False
            ok = self.UpdateDelays()
            if not ok:
                return False
            logger.debug("(%s) Sent new delay values to buffer" % self.name)
        return True

    def GetDelaySwitches(self):
        """
    
        This method requests the value of the delay switches. This value is then stored in the attribute: 'ChannelDelayRead'.
        
        - **Parameters**:
        
            -  **None**
            
        - **Returns**:

            -  **Nothing**
            
        """   
        with self.lock:
            control = self.getControlByte(flags=(ACK + SO), sn=self.SequenceNumber, an=self.AckNumber)
            self.Message = self.CompileSmallMessage(control=control, command=12)
            ok = self.DoCommand()
            if not ok:
                return False
            self.ChannelDelayRead = self.RxMessage[3:-2]     # store the values in the correct attribute
            logger.debug("(%s) Retrieved delay switches" % self.name)
        return True
 
    def SetEnabledSwitches(self):
        """
    
        This method sets the enabled switches of the channel. This is in calibrated mode so it will switch on the entire channel at once. A 1 means all LNA's enabled, a 0 means all LNA's disabled. It uses the 'ChannelEnable' attribute to obtain the desired values for the channel enable.
        
        - **Parameters**:
        
            -  **None**
            
        - **Returns**:

            -  **Nothing**
            
        """   
        with self.lock:
            control = self.getControlByte(flags=(ACK + EOR), sn=self.SequenceNumber, an=self.AckNumber)
            self.Message = self.CompileSmallMessage(control=control, command=0, length=19)
            self.MessageAddendum = chr(35) + chr(0) + chr(16) + ''.join([chr(x) for x in self.ChannelEnable])    # [35,0,16]+self.ChannelEnable
            self.MessageAddendum += self.ComputeChecksum16(self.MessageAddendum)
            self.Message += self.MessageAddendum
            ok = self.DoCommand()
            if not ok:
                return False
            logger.debug("(%s) Set channel enable switches" % self.name)
        return True
    
    def GetEnabledSwitches(self):
        """
    
        This method requests the enabled channels of the beamformer and stores them in the ''ChannelEnableRead'' attribute.
        
        - **Parameters**:
        
            -  **None**
            
        - **Returns**:

            -  **Nothing**
            
        """   
        with self.lock:
            control = self.getControlByte(flags=(ACK + SO), sn=self.SequenceNumber, an=self.AckNumber)
            self.Message = self.CompileSmallMessage(control=control, command=14)
            ok = self.DoCommand()
            if not ok:
                return False
            self.ChannelEnableRead = self.RxMessage[3:-2]      # store the enabled channels in ChannelEnableRead
            logger.debug("(%s) Retrieved channel enable switches" % self.name)
        return True

    def SetDelaySwitchesDiag(self):
        """
    
        This method sets the delay switches in uncalibrated mode, the value of the switch that is set will be the actual value of the delayswitches. The attribute that is used is ''ChannelDelayDiag''.
        
        - **Parameters**:
        
            -  **None**
            
        - **Returns**:

            -  **Nothing**
            
        """   
        with self.lock:
            control = self.getControlByte(flags=(ACK + EOR), sn=self.SequenceNumber, an=self.AckNumber)
            self.Message = self.CompileSmallMessage(control=control, command=0, length=19)
            self.MessageAddendum = chr(34) + chr(0) + chr(16) + ''.join([chr(x) for x in self.ChannelDelayDiag])    # [34,0,16]+self.ChannelDelayDiag
            self.MessageAddendum += self.ComputeChecksum16(self.MessageAddendum)
            self.Message += self.MessageAddendum
            ok = self.DoCommand()
            if not ok:
                return False
            logger.debug("(%s) Set channel enable switches in diagnostics mode" % self.name)
        return True
            
    def GetDelaySwitchesDiag(self):
        """
    
        This method requests the uncalibrate delay switch values and stores them in the ''ChannelDelayReadDaig'' attribute.
        
        - **Parameters**:
        
            -  **None**
            
        - **Returns**:

            -  **Nothing**
            
        """ 
        with self.lock:
            control = self.getControlByte(flags=(ACK + SO), sn=self.SequenceNumber, an=self.AckNumber)
            self.Message = self.CompileSmallMessage(control=control, command=13)
            ok = self.DoCommand()
            if not ok:
                return False
            self.ChannelDelayReadDiag = self.RxMessage[3:-2]       # store the values in the Attribute
            logger.debug("(%s) Retrieved delay switches in diagnostics mode" % self.name)
        return True

    def SetChannelAttenuators(self):
        """
    
        This method sets the Channel attenuators in diagnostics mode. The Channel attenuations used are in the attribute ''ChannelAttenuators''.
        
        - **Parameters**:
        
            -  **None**
            
        - **Returns**:

            -  **Nothing**
            
        """ 
        with self.lock:
            control = self.getControlByte(flags=(ACK + EOR), sn=self.SequenceNumber, an=self.AckNumber)
            self.Message = self.CompileSmallMessage(control=control, command=0, length=19)
            self.MessageAddendum = chr(25) + chr(0) + chr(16) + ''.join([chr(x) for x in self.ChannelAttenuators])     # [25,0,16]+self.ChannelAttenuators
            self.MessageAddendum += self.ComputeChecksum16(self.MessageAddendum)
            self.Message += self.MessageAddendum
            ok = self.DoCommand()
            if not ok:
                return False
            logger.debug("(%s) Set channel attenuators" % self.name)
        return True
        
    def GetChannelAttenuators(self):
        """
    
        This method requests the channel attenuations and stores them in the attribute ''ChannelAttenuatorRead''.
        
        - **Parameters**:
        
            -  **None**
            
        - **Returns**:

            -  **Nothing**
            
        """ 
        with self.lock:
            control = self.getControlByte(flags=(ACK + SO), sn=self.SequenceNumber, an=self.AckNumber)
            self.Message = self.CompileSmallMessage(control=control, command=3)
            ok = self.DoCommand()
            if not ok:
                return False
            self.ChannelAttenuatorsRead = self.RxMessage[3:-2]          # store the value of the attenuators
            logger.debug("(%s) Retrieved channel attenuators" % self.name)
        return True

    def SetEnabledSwitchesDiag(self):
        """
    
        This method sets the individual LNA enable switches of the channel as described in the ''ChannelEnableDiag'' attribute.
        
        - **Parameters**:
        
            -  **None**
            
        - **Returns**:

            -  **Nothing**
            
        """ 
        with self.lock:
            control = self.getControlByte(flags=(ACK + EOR), sn=self.SequenceNumber, an=self.AckNumber)
            self.Message = self.CompileSmallMessage(control=control, command=0, length=19)
            self.MessageAddendum = chr(36) + chr(0) + chr(16) + ''.join([chr(x) for x in self.ChannelEnableDiag])   # [36,0,16]+self.ChannelEnableDiag
            self.MessageAddendum += self.ComputeChecksum16(self.MessageAddendum)
            self.Message += self.MessageAddendum
            ok = self.DoCommand()
            if not ok:
                return False
            logger.debug("(%s) Set enabled switches in diagnostics mode" % self.name)
        return True
        
    def GetEnabledSwitchesDiag(self):
        """
    
        This method request the individual enabled switches of a channel and stores them in the ChannelEnableReadDiag attribute.
        
        - **Parameters**:
        
            -  **None**
            
        - **Returns**:

            -  **Nothing**
            
        """ 
        with self.lock:
            control = self.getControlByte(flags=(ACK + SO), sn=self.SequenceNumber, an=self.AckNumber)
            self.Message = self.CompileSmallMessage(control=control, command=15)
            ok = self.DoCommand()
            if not ok:
                return False
            self.ChannelEnableReadDiag = self.RxMessage[3:-2]          # Store the enabled switches in the correct attribute
            logger.debug("(%s) Retrieved enabled switches in diagnostics mode" % self.name)
        return True
      
    def CompileSmallMessage(self, control=0, command=0, length=0):
        """
    
        This method is used to create the small message which is used for short commands, or for the start of long packets. It takes 3 bytes of data, adds the start flag and computes the first checksum. The message is then stored in the Message attribute.
        
        - **Parameters**:
        
            -  **data:** The three middle bytes of a short packet, this holds the control byte, command byte, and the length byte.
            
        - **Returns**:

            -  **Nothing** 
            
        """
        message = '\x7e' + chr(control) + chr(command) + chr(length)
        message += self.ComputeChecksum8(message[1:])     # add the computed checksum.
        return message
        
    def ComputeChecksum8(self, data):
        """
    
        This method comuptes the 8 bit checksum over a small packet (typically 3 bytes). 
        
        - **Parameters**:
        
            -  **Data:** The data over which the checksum has to be computed.
            
        - **Returns**:

            -  **Cs:** The checksum character which is appended at the end of a short message.
            
        """ 
        cs = 0                      # set checksum to 0
        for c in data:  # add all the bytes to get the checksum
            cs += ord(c)
        if cs > 255:                # if there is an overflow, add the overflow to the lower byte
            overflow = cs >> 8
            cs += overflow - (overflow << 8)
        else:
            cs = (~cs & 255)

        return chr(cs)              # return the checksum.
    
    def ComputeChecksum16(self, data):
        """
    
        This method comuptes the 16 bit checksum over a long packet. 
        
        - **Parameters**:
        
            -  **Data:** The data over which the checksum has to be computed.
            
        - **Returns**:

            -  **cs16:** The checksum bytes which are appended at the end of a long message.
            
        """ 
        cs = 0      # set checksum to 0
        for i in range(0, len(data), 2):          # compute the checksum per 16 bytes of data
            if (len(data) % 2 == 1) and (i == len(data) - 1):
                cs += ord(data[i])
            else:
                cs += (ord(data[i + 1]) << 8) + ord(data[i])
        if cs >= 65536:              # if there is an overflow, add the overflow the the lower bytes
            overflow = cs >> 16
            cs += overflow - (overflow << 16)
        cs = ~cs + 65536
        return chr(cs & 0xFF) + chr((cs & 0xFF00) >> 8)

    def getControlByte(self, flags=0, sn=0, an=0):
        """
    
        This method sets the control bits of the control byte. These are set in the control attribute
        
        - **Parameters**:
        
            -  **flags = [SYN] + [ACK] + [FIN] + [RST] + [EOR] + [SO]:** The values for the corresponding control bits
            
        - **Returns**:

            -  **control byte = flags + SN*sn + AN*an**
            
        """ 
        return flags + (SN * sn) + (AN * an)
        

# Xpol=Beamformer(XpolPort)
