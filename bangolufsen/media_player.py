"""
Support for Bang & Olufsen Master Link Gateway and Beolink Gateway.

For more details about this platform, please refer to the documentation at
https://home-assistant.io/components/media_player.bangolufsen/

This component manages communication To and From the MLGW.

Controlling Devices and Speakers, like Beosound and Beolab, is done simply through a media_player controller in the UI. I use mini_media_player.

This platform also forwards Virtual Buttons and Light/Control commands from the Masterlink to Home Assistant.

There are two ways to enable Light commands to control Hass.io lights.

First is to create a "Custom Strings" device on MLGW with command strings like this:

POST /api/services/scene/turn_on HTTP/1.1\0D\0AAuthorization: Bearer <your token>
\0D\0AContent-Type: application/json\0D\0AContent-Length: 39
\0D\0A\0D\0A{\"entity_id\": \"scene.<your scene>\"}

The second is to listen to Virtual Button and Light events fired by the platform.

Configuration example:

media_player:
  platform: bangolufsen
  host: 192.168.1.10
  username: usr00
  password: usr00
  port: 9000
  default_source: A.MEM
  available_sources:
    - A.MEM
    - CD
    - RADIO
  devices:
    - BeoSound
    - BeoLab3500LR
    - Patio
    - BeoLabStudio
    - TVRoom
    - Bedroom
    - Bathroom

Devices need to be defined in the same order as the MLGW configuration, and MLNs need to be sequential, starting from 1 for the first one.

"""
import logging
import voluptuous as vol
import socket
import time
import threading

#from homeassistant.components.media_player import (SUPPORT_TURN_OFF, SUPPORT_TURN_ON, 
#                                                   PLATFORM_SCHEMA, MediaPlayerDevice, 
#                                                   SUPPORT_SELECT_SOURCE, SUPPORT_VOLUME_STEP)

from homeassistant.const import (CONF_HOST, CONF_NAME, CONF_USERNAME, 
                                 CONF_PASSWORD, CONF_PORT, STATE_OFF,
                                 STATE_ON, STATE_UNKNOWN, CONF_DEVICES,
                                 EVENT_HOMEASSISTANT_STOP)

from homeassistant.components.media_player import (
    MediaPlayerEntity,
    PLATFORM_SCHEMA)

from homeassistant.components.media_player.const import (
    SUPPORT_TURN_ON,
    SUPPORT_TURN_OFF,
    SUPPORT_SELECT_SOURCE,
    SUPPORT_VOLUME_STEP,
    SUPPORT_VOLUME_MUTE
)

import homeassistant.helpers.config_validation as cv

_LOGGER = logging.getLogger(__name__)
# _LOGGER.setLevel(logging.ERROR)

DEFAULT_NAME = 'Beolink'
# A.MEM is the aux port of the Beosound system. For modern uses of Beosound it is typically the most used source 
DEFAULT_SOURCE = 'A.MEM'
AVAILABLE_SOURCES = ['CD', 'RADIO', 'A.MEM'] 
CONF_DEFAULT_SOURCE = 'default_source'
CONF_AVAILABLE_SOURCES = 'available_sources'
SUPPORT_BEO = SUPPORT_TURN_ON | SUPPORT_TURN_OFF | SUPPORT_VOLUME_STEP | SUPPORT_SELECT_SOURCE | SUPPORT_VOLUME_MUTE 

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Optional(CONF_HOST, default='192.168.1.10'): cv.string,
    vol.Required(CONF_DEVICES): cv.ensure_list,
    vol.Optional(CONF_USERNAME, default='admin'): cv.string,
    vol.Optional(CONF_PASSWORD, default='admin'): cv.string,
    vol.Optional(CONF_PORT, default=9000): cv.positive_int,
    vol.Optional(CONF_DEFAULT_SOURCE, default=DEFAULT_SOURCE): cv.string,
    vol.Optional(CONF_AVAILABLE_SOURCES, default=AVAILABLE_SOURCES): cv.ensure_list,
})


def setup_platform(hass, config, add_devices, discovery_info=None):
    host = config.get(CONF_HOST)
    username = config.get(CONF_USERNAME)
    password = config.get(CONF_PASSWORD)
    port = config.get(CONF_PORT)
    devices = config.get(CONF_DEVICES)
    default_source = config.get(CONF_DEFAULT_SOURCE)
    available_sources = config.get(CONF_AVAILABLE_SOURCES)

    gateway = MLGateway(host, port, username, password, default_source, available_sources, hass)
    gateway.connect()

    def _stop_listener(_event):
        gateway.stopped.set()

    hass.bus.listen_once(
        EVENT_HOMEASSISTANT_STOP,
        _stop_listener
    )

    if gateway.connected:
        _LOGGER.info('Adding devices: ' + ', '.join(devices))
        mp_devices = [BeoSpeaker(i + 1, device, gateway) for i, device in enumerate(devices)]
        add_devices(mp_devices)
        gateway.set_devices(mp_devices) # tell the gateway the list of devices connected to it.
    else:
        _LOGGER.error('Not connected')

"""
BeoSpeaker represents a single MasterLink device on the Masterlink bus. E.g., a speaker like BeoSound 3500 or a Masterlink Master device like a receiver or TV (e.g, a Beosound 3000)

Because the Masterlink has only one active source across all the speakers, we maintain the source state in the Gateway class, which manages the relationship with the Masterlink Gateway. It's not very clean, but it works.

"""
class BeoSpeaker(MediaPlayerEntity):
    def __init__(self, mln, name, gateway):
        self._mln = mln
        self._name = name
        self._gateway = gateway
        self._pwon = False
        self._source = self._gateway.beolink_source

    @property
    def name(self):
        return self._name

    @property
    def friendly_name(self):
        return self._name.capwords(sep='_')

    @property
    def supported_features(self):
        # Flag media player features that are supported.
        return SUPPORT_BEO

    @property
    def supported_media_commands(self):
        """Flag of media commands that are supported."""
        return SUPPORT_BEO

    @property
    def source(self):
        # Name of the current input source. Because the source is common across all the speakers connected to the gateway, we just pass through the beolink.
        self._source = self._gateway.beolink_source
        return self._source

    @property
    def source_list(self):
        """List of available input sources."""
        return self._gateway.available_sources

    @property
    def state(self):
        """Return the state of the device."""
        if self._pwon:
            return STATE_ON
        else:
            return STATE_OFF

    def set_state(self, _state):
# to be called by the gateway to set the state to off when there is an event on the ml bus that turns off the device
        if _state == STATE_ON:
            self._pwon = True
        elif _state == STATE_OFF:
            self._pwon = False

    def turn_on(self):
        self.select_source(self._gateway.beolink_source)
# An alternate is to turn on with volume up which for most devices, turns it on without changing source, but it does nothing on the BeoSound system.
#        self._pwon = True
#        self.volume_up()

    def turn_off(self):
        self._pwon = False
        self._gateway.send_beo4_cmd(self._mln, reverse_destselectordict.get('AUDIO SOURCE'), BEO4_CMDS.get('STANDBY'))

    def select_source(self, source):
        self._pwon = True
        self._source = source
        self._gateway.send_beo4_cmd_source(self._mln, reverse_destselectordict.get('AUDIO SOURCE'), self._source)

    def volume_up(self):
        self._gateway.send_beo4_cmd(self._mln, reverse_destselectordict.get('AUDIO SOURCE'), BEO4_CMDS.get('VOLUME UP'))

    def volume_down(self):
        self._gateway.send_beo4_cmd(self._mln, reverse_destselectordict.get('AUDIO SOURCE'), BEO4_CMDS.get('VOLUME DOWN'))

    def mute_volume(self, mute):
        self._gateway.send_beo4_cmd(self._mln, reverse_destselectordict.get('AUDIO SOURCE'), BEO4_CMDS.get('MUTE'))

"""
MLGateway class manages the communication with the Masterlink Gateway. There are two devices that can be controlled this way: The MasterLink Gateway MK2 and the Beolink Gateway. See https://beointegration.com/ for more information about these products.

These integrations allow Home Assistant to control your legacy Bang & Olufsen MasterLink device network.

"""
class MLGateway:
    def __init__(self, host, port, user, password, default_source, available_sources, hass):
        self._host = host
        self._user = user
        self._password = password
        self._port = port
        self._tcpip = host
        self.buffersize = 1024
        self._socket = None
        self.connected = False
        self.telegramlogging = True
        self.stopped = threading.Event()
        self._sourceMLN = 1 
        self._source = default_source
        self._sourceMediumPosition = 0xffff
        self._sourcePosition = 0x00ff
        self._sourceActivity = None
        self._pictureFormat = None
        self._available_sources = available_sources
        self._devices = None
        self._hass = hass

    ## Return last selected source or last source status received from mlgw
    @property
    def beolink_source(self):
        return self._source

    @property
    def available_sources(self):
        return self._available_sources

# populate the list of devices configured on the gateway.
    def set_devices(self, devices):
        self._devices = devices

    ## Open tcp connection to mlgw
    def connect(self):
        _LOGGER.info('Trying to connect')
        self.connected = False

        # get ip address for hostname
        if self._tcpip is None:
          try:
              self._tcpip = socket.gethostbyname(self._host)
          except Exception as e:
              _LOGGER.error("Error resolving '%s': %s" % (self._host, e))
              return

        # open socket to masterlink gateway
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._socket.settimeout(600)
        try:
             self._socket.connect((self._tcpip, self._port))
             threading.Thread(target=self._listen).start()
        except Exception as e:
            self._socket = None
            _LOGGER.error("Error opening connection to %s: %s" % (self._tcpip, e))
            return

        if self._tcpip != self._host:
            _LOGGER.info("Opened connection to ML Gateway '" + self._host + "' on IP " + self._tcpip + ":" + str(self._port))
        else:
            _LOGGER.info("Opened connection to ML Gateway on IP " + self._tcpip + ":" + str(self._port))
        self.connected = True
        self.ping()

    ## Login
    def login(self):
        _LOGGER.info('Trying to login')
        if self.connected:
            wrkstr = self._user + chr(0x00) + self._password
            payload = bytearray()
            for c in wrkstr:
                payload.append(ord(c))
            self.send(0x30, payload)   # login Request

    def ping(self):
        _LOGGER.info('ping')
        self.send(0x36, '')

    ## Close connection to mlgw
    def close(self):
        if self.connected:
            self.connected = False
            self.stopped.set()
            self._socket.shutdown(socket.SHUT_RDWR)
            self._socket.close()
            _LOGGER.info("Closed connection to ML Gateway")

    ## Send command to mlgw
    def send(self, msg_type, payload):
        if self.connected:
            self._telegram = bytearray()
            self._telegram.append(0x01)             # byte[0] SOH
            self._telegram.append(msg_type)         # byte[1] msg_type
            self._telegram.append(len(payload))     # byte[2] Length
            self._telegram.append(0x00)             # byte[3] Spare
            for p in payload:
                self._telegram.append(p)
            self._socket.sendall(self._telegram)

            # Sleep to allow msg to arrive
            time.sleep(1)

            if self.telegramlogging:
                _LOGGER.info("mlgw: >SENT: " + _getpayloadtypestr(msg_type) + ": " + _getpayloadstr(self._telegram))  # debug

    ## Send Beo4 command to mlgw
    def send_beo4_cmd(self, mln, dest, cmd):
        self._payload = bytearray()
        self._payload.append(mln)              # byte[0] MLN
        self._payload.append(dest)             # byte[1] Dest-Sel (0x00, 0x01, 0x05, 0x0f)
        self._payload.append(cmd)              # byte[2] Beo4 Command
        self._payload.append(0x00)             # byte[3] Sec-Source
        self._payload.append(0x00)             # byte[3] Link
        self.send(0x01, self._payload)

    ## Send Beo4 commmand and store the source name
    def send_beo4_cmd_source(self, mln, dest, source):
        self._source = source
        self.send_beo4_cmd(mln, dest, BEO4_CMDS.get(source))

    def send_virtual_btn_press(self, btn):
        self.send(0x20, [btn])

    def _listen(self):
        while not self.stopped.isSet():
            try:
                response = self._socket.recv(self.buffersize)
            except KeyboardInterrupt:
                self.close()
            except socket.timeout:
                # Ping the gateway to test the connection
                self.ping()
                continue

            if response is not None:
                # Decode response. Response[0] is SOH, or 0x01
                msg_byte = response[1]
                msg_type = _getpayloadtypestr(msg_byte)
                msg_payload = _getpayloadstr(response)

                _LOGGER.debug(f'Msg type: {msg_type}. Payload: {msg_payload}')

                if msg_byte == 0x20: # Virtual Button event
                    virtual_btn = response[4]
                    if len(response)<5:
                        virtual_action = _getvirtualactionstr(0x01)
                    else: 
                        virtual_action = _getvirtualactionstr(response[5])
                    _LOGGER.info(f'Virtual button pressed: button {virtual_btn} action {virtual_action}' )
                    self._hass.bus.fire("bangolufsen_virtual_button", {"button": virtual_btn, "action": virtual_action})

                elif msg_byte == 0x31: # Login Status
                    if msg_payload == 'FAIL':
                        _LOGGER.info('Login needed')
                        self.login()
                    elif msg_payload == 'OK':
                        _LOGGER.info('Login successful')
                        self.get_serial()

                elif msg_byte == 0x37: # Pong (Ping response)
                    _LOGGER.info('pong')

                elif msg_byte == 0x02: # Source status
                    _LOGGER.info(f'Msg type: {msg_type}. Payload: {msg_payload}')
                    self._sourceMLN = _getmlnstr( response[4] ) 
                    self._source = _getselectedsourcestr( response[5] ).upper()
                    self._sourceMediumPosition = _hexword( response[6], response[7] )
                    self._sourcePosition = _hexword( response[8], response[9] )
                    self._sourceActivity = _getdictstr( sourceactivitydict, response[10] )
                    self._pictureFormat = _getdictstr( pictureformatdict, response[11] )

                elif msg_byte == 0x05: # All Standby
                    _LOGGER.info(f'Msg type: {msg_type}. Payload: {msg_payload}')
                    if self._devices is not None: # set all connected devices state to off
                        for i in self._devices:
                            i.set_state(STATE_OFF)

                elif msg_byte == 0x04: # Light / Control command
                    lcroom = _getroomstr( response[4] )
                    lctype = _getdictstr( lctypedict, response[5] )
                    lccommand = _getbeo4commandstr( response[6] )
                    _LOGGER.info(f'Light/Control command: room: {lcroom} type: {lctype} command {lccommand}')
                    self._hass.bus.fire("bangolufsen_light_control_event", {"room": response[4], "type": lctype, "command": lccommand})

                else:
                    _LOGGER.info(f'Msg type: {msg_type}. Payload: {msg_payload}')

    ## Receive message from mlgw
    def receive(self):
        if self.connected:
            try:
                self._mlgwdata = self._socket.recv(self.buffersize)
            except socket.timeout:
                pass
            except KeyboardInterrupt:
                _LOGGER.error("mlgw: KeyboardInterrupt, terminating...")
                self.close()

            self._payloadstr = _getpayloadstr(self._mlgwdata)
            if self._mlgwdata[0] != 0x01:
                _LOGGER.error("mlgw: Received telegram with SOH byte <> 0x01")
            if self._mlgwdata[3] != 0x00:
                _LOGGER.error("mlgw: Received telegram with spare byte <> 0x00")
            if self.telegramlogging:
                _LOGGER.info("mlgw: <RCVD: '" + _getpayloadtypestr(self._mlgwdata[1]) + "': " + str(self._payloadstr))  # debug
            return (self._mlgwdata[1], str(self._payloadstr))

    ## Get serial number of mlgw
    def get_serial(self):
        if self.connected:
            # Request serial number
            self.send(0x39, '')
            (result, self._serial) = self.receive()
            _LOGGER.warning("mlgw: Serial number of ML Gateway is " + self._serial)  # info
        return


def _hexbyte(byte):
    resultstr = hex(byte)
    if byte < 16:
        resultstr = resultstr[:2] + "0" + resultstr[2]
    return resultstr

def _hexword(byte1, byte2):
    resultstr = _hexbyte(byte2)
    resultstr = _hexbyte(byte1) + resultstr[2:]
    return resultstr

# ########################################################################################
# ##### MLGW Protocol packet constants

payloadtypedict = dict([
    (0x01, "Beo4 Command"), (0x02, "Source Status"), (0x03, "Pict&Snd Status"),
    (0x04, "Light and Control command"), (0x05, "All standby notification"),
    (0x06, "BeoRemote One control command"), (0x07, "BeoRemote One source selection"),
    (0x20, "MLGW virtual button event"), (0x30, "Login request"), (0x31, "Login status"),
    (0x32, "Change password request"), (0x33, "Change password response"),
    (0x34, "Secure login request"), (0x36, "Ping"), (0x37, "Pong"),
    (0x38, "Configuration change notification"), (0x39, "Request Serial Number"),
    (0x3a, "Serial Number"), (0x40, "Location based event")
    ])

beo4commanddict = dict([
    # Source selection:
    (0x0c, "Standby"), (0x47, "Sleep"), (0x80, "TV"), (0x81, "Radio"), (0x82, "DTV2"),
    (0x83, "Aux_A"), (0x85, "V.Mem"), (0x86, "DVD"), (0x87, "Camera"), (0x88, "Text"),
    (0x8a, "DTV"), (0x8b, "PC"), (0x0d, "Doorcam"), (0x91, "A.Mem"), (0x92, "CD"),
    (0x93, "N.Radio"), (0x94, "N.Music"), (0x97, "CD2"),
    # Digits:
    (0x00, "Digit-0"), (0x01, "Digit-1"), (0x02, "Digit-2"), (0x03, "Digit-3"),
    (0x04, "Digit-4"), (0x05, "Digit-5"), (0x06, "Digit-6"), (0x07, "Digit-7"),
    (0x08, "Digit-8"), (0x09, "Digit-9"),
    # Source control:
    (0x1e, "STEP_UP"), (0x1f, "STEP_DW"), (0x32, "REWIND"), (0x33, "RETURN"),
    (0x34, "WIND"), (0x35, "Go / Play"), (0x36, "Stop"), (0xd4, "Yellow"),
    (0xd5, "Green"), (0xd8, "Blue"), (0xd9, "Red"),
    # Sound and picture control
    (0x0d, "Mute"), (0x1c, "P.Mute"), (0x2a, "Format"), (0x44, "Sound / Speaker"),
    (0x5c, "Menu"), (0x60, "Volume UP"), (0x64, "Volume DOWN"), (0xda, "Cinema_On"),
    (0xdb, "Cinema_Off"),
    # Other controls:
    (0x14, "BACK"), (0x7f, "Exit"),
    # Continue functionality:
    (0x7e, "Key Release"),
    # Functions:
    # Cursor functions:
    (0x13, "SELECT"), (0xca, "Cursor_Up"), (0xcb, "Cursor_Down"), (0xcc, "Cursor_Left"),
    (0xcd, "Cursor_Right"),
    #    
    (0x9b, "Light"),  (0x9c, "Command"),
    #  Dummy for 'Listen for all commands'
    (0xff, "<all>")
    ])

BEO4_CMDS = {v.upper(): k for k, v in beo4commanddict.items()}

destselectordict = dict([
    (0x00, "Video Source"), (0x01, "Audio Source"), (0x05, "V.TAPE/V.MEM"), (0x0f, "All Products")
    ])

reverse_destselectordict = {v.upper(): k for k, v in destselectordict.items()}

virtualactiondict = dict([
    (0x01, "PRESS"), (0x02, "HOLD"), (0x03, "RELEASE")
    ])

selectedsourcedict = dict( [
    (0x0b, "TV"), (0x15, "V.Mem"), (0x1f, "DTV"), (0x29, "DVD"), 
    (0x6f, "Radio"), (0x79, "A.Mem"), (0x8d, "CD"),
    #  Dummy for 'Listen for all sources'
    (0xfe, "<all>")
    ] )
    
reverse_selectedsourcedict = {v.upper(): k for k, v in selectedsourcedict.items()}

sourceactivitydict = dict( [
    (0x00, "Unknown"), (0x01, "Stop"), (0x02, "Playing"), (0x03, "Wind"), 
    (0x04, "Rewind"), (0x05, "Record lock"), (0x06, "Standby")
    ] )

pictureformatdict = dict( [
    (0x00, "Not known"), (0x01, "Known by decoder"), (0x02, "4:3"), (0x03, "16:9"), 
    (0x04, "4:3 Letterbox middle"), (0x05, "4:3 Letterbox top"), 
    (0x06, "4:3 Letterbox bottom"), (0xff, "Blank picture")
    ] )


### for '0x03: Picture and Sound Status'
soundstatusdict = dict([
    (0x00, "Not muted"), (0x01, "Muted")
    ])

speakermodedict = dict([
    (0x01, "Center channel"), (0x02, "2ch stereo"), (0x03, "Front surround"),
    (0x04, "4ch stereo"), (0x05, "Full surround"),
    #  Dummy for 'Listen for all modes'
    (0xfd, "<all>")
    ])

reverse_speakermodedict = {v.upper(): k for k, v in speakermodedict.items()}

screenmutedict = dict([
    (0x00, "not muted"), (0x01, "muted")
    ])

#screenactivedict = dict( [
#    (0x00, "not active"), (0x01, "active")
#    ] )

cinemamodedict = dict( [
    (0x00, "Cinemamode=off"), (0x01, "Cinemamode=on")
    ] )

stereoindicatordict = dict( [
    (0x00, "Mono"), (0x01, "Stereo")
    ] )

### for '0x04: Light and Control command'
lctypedict = dict( [
    (0x01, "LIGHT"), (0x02, "CONTROL")
    ] )

### for '0x31: Login Status
loginstatusdict = dict( [
    (0x00, "OK"), (0x01, "FAIL")
    ] )

# ########################################################################################
# ##### Decode MLGW Protocol packet to readable string

## Get decoded string for mlgw packet's payload type
#
def _getpayloadtypestr( payloadtype ):
        result = payloadtypedict.get( payloadtype )
        if result == None:
            result = "UNKNOWN (type=" + _hexbyte( payloadtype ) + ")"
        return str(result)

def _getroomstr( room ):
    result = "Room=" + str( room )
    return result

def _getmlnstr( mln ):
    result = "MLN=" + str( mln )
    return result
    
def _getbeo4commandstr( command ):
    result = beo4commanddict.get( command )
    if result == None:
        result = "Cmd=" + _hexbyte( command )
    return result

def _getvirtualactionstr( action ):
    result = virtualactiondict.get( action )
    if result == None:
        result = "Action=" + _hexbyte( action )
    return result

def _getselectedsourcestr( source ):
    result = selectedsourcedict.get( source )
    if result == None:
        result = "Src=" + _hexbyte( source )
    return result

def _getspeakermodestr( source ):
    result = speakermodedict.get( source )
    if result == None:
        result = "mode=" + _hexbyte( source )
    return result

def _getdictstr( mydict, mykey ):
    result = mydict.get( mykey )
    if result == None:
        result = _hexbyte( mykey )
    return result


## Get decoded string for a mlgw packet
#
#   The raw message (mlgw packet) is handed to this function. 
#   The result of this function is a human readable string, describing the content
#   of the mlgw packet
#
#  @param message   raw mlgw telegram
#  @returns         telegram as a human readable string
#
def _getpayloadstr( message ):
    if message[2] == 0:            # payload length is 0
        resultstr = "[No payload]"
    elif message[1] == 0x01:       # Beo4 Command
        resultstr = _getmlnstr( message[4] )
        resultstr = resultstr + " " + _hexbyte( message[5] )
        resultstr = resultstr + " " + _getbeo4commandstr(message[6])

    elif message[1] == 0x02:       # Source Status
        resultstr = _getmlnstr( message[4] ) 
        resultstr = resultstr + " " + _getselectedsourcestr( message[5] ) 
        resultstr = resultstr + " " + _hexword( message[6], message[7] )
        resultstr = resultstr + " " + _hexword( message[8], message[9] )
        resultstr = resultstr + " " + _getdictstr( sourceactivitydict, message[10] )
        resultstr = resultstr + " " + _getdictstr( pictureformatdict, message[11] )

    elif message[1] == 0x03:       # Picture and Sound Status
        resultstr = _getmlnstr( message[4] )
        if message[5] != 0x00:
            resultstr = resultstr + " " + _getdictstr( soundstatusdict, message[5] )
        resultstr = resultstr + " " + _getdictstr( speakermodedict, message[6] )
        resultstr = resultstr + " Vol=" + str( message[7] )
        if message[9] != 0x00:
            resultstr = resultstr + " Scrn:" + _getdictstr( screenmutedict, message[8] )
        if message[11] != 0x00:
            resultstr = resultstr + " Scrn2:" + _getdictstr( screenmutedict, message[10] )
        if message[12] != 0x00:
            resultstr = resultstr + " " + _getdictstr( cinemamodedict, message[12] )
        if message[13] != 0x01:
            resultstr = resultstr + " " + _getdictstr( stereoindicatordict, message[13] )

    elif message[1] == 0x04:       # Light and Control command
        resultstr = _getroomstr( message[4] ) + " " + _getdictstr( lctypedict, message[5] ) + " " + _getbeo4commandstr( message[6] )

    elif message[1] == 0x30:       # Login request
        wrk = message[4:4+message[2]]
        for i in range(0, message[2]):
            if wrk[i] == 0: wrk[i] = 0x7f
        wrk = wrk.decode('utf-8')
        resultstr = wrk.split(chr(0x7f))[0] + " / " + wrk.split(chr(0x7f))[1]

    elif message[1] == 0x31:       # Login status
        resultstr = _getdictstr( loginstatusdict, message[4] )

    elif message[1] == 0x3a:       # Serial Number
        resultstr = message[4:4+message[2]].decode('utf-8')

    else:                               # Display raw payload
        resultstr = ""
        for i in range(0, message[2]):
            if i > 0:
                resultstr = resultstr + " "
            resultstr = resultstr + _hexbyte(message[4+i])
    return resultstr


if __name__ == '__main__':
    import sys
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.INFO)
    _LOGGER.addHandler(ch)

    gateway = MLGateway()
    gateway.connect()
    # gateway.login()
    gateway.ping()

    # dining_room = BeoSpeaker(0, 'dining_room', gateway)
    # dining_room.turn_on()

    # gateway.close()
    time.sleep(10)


