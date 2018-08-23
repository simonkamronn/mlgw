# vim: set encoding=utf-8 tabstop=4 softtabstop=4 shiftwidth=4 expandtab
#
# ########################################################################
# Copyright (C) 2015 Martin Sinn
#########################################################################
# mlgw plugin is to be used with smarthome.py (http://mknx.github.io/smarthome/)
#
#  Version 0.5 beta
#
#
# masterlink-gateway plugin for smarthome.py is free software: you can 
# redistribute it and/or modify it under the terms of the GNU General 
# Public License as published by the Free Software Foundation, either 
# version 3 of the License, or (at your option) any later version.
# 

import logging
import socket
import threading
#import struct
import time
import ast
import sys


_LOGGER = logging.getLogger(' ')
log_telegrams = 4
loglevel_keepalivetelegrams = logging.DEBUG      # DEBUG
loglevel_receivedtelegrams = logging.INFO        # INFO
loglevel_unhandledtelegrams = logging.INFO
loglevel_senttelegrams = logging.INFO            # INFO

DEFAULT_SOURCE = 'DVD'

def _hexbyte( byte ):
    resultstr = hex( byte )
    if byte < 16:
        resultstr = resultstr[:2] + "0" + resultstr[2]
    return resultstr

def _hexword( byte1, byte2 ):
    resultstr = _hexbyte( byte2 )
    resultstr = _hexbyte( byte1 ) + resultstr[2:]
    return resultstr


# Dictionary for items to listen for
# { listenerkey: item }, listenerkey = 256 * room + cmd
listenerlightdict = {}
listenercontroldict = {}
listenersourcestatusdict = {}
listenerspeakermodedict = {}


#########################################################################################
###### Installation-specific data

# Dictionary to lookup room names, filled from plugin.conf
roomdict = dict( [] )
reverse_roomdict = {}

# Dictionary to lookup MLN names, filled from plugin.conf
mlndict = dict( [] )
reverse_mlndict = {}


#########################################################################################
###### Dictionaries with MLGW Protokoll Data

payloadtypedict = dict( [
    (0x01, "Beo4 Command"), (0x02, "Source Status"), (0x03, "Pict&Snd Status"),
    (0x04, "Light and Control command"), (0x05, "All standby notification"), 
    (0x06, "BeoRemote One control command"), (0x07, "BeoRemote One source selection"),
    (0x20, "MLGW virtual button event"), (0x30, "Login request"), (0x31, "Login status"),
    (0x32, "Change password request"), (0x33, "Change password response"), 
    (0x34, "Secure login request"), (0x36, "Ping"), (0x37, "Pong"), 
    (0x38, "Configuration change notification"), (0x39, "Request Serial Number"), 
    (0x3a, "Serial Number"), (0x40, "Location based event")
    ] )

#payloaddirectiondict = dict( [
#    (0x01, "-> Beolink"), (0x02, "Beolink ->"), (0x03, "Beolink ->"),
#    (0x04, "Beolink ->"), (0x05, "MLGW ->"), 
#    (0x06, "-> Beolink"), (0x07, "-> Beolink"),
#    (0x20, "bidirectional"), (0x30, "-> MLGW"), (0x31, "MLGW ->"),
#    (0x32, "-> MLGW"), (0x33, "MLGW ->"), 
#    (0x34, "-> MLGW"), (0x36, "-> MLGW"), (0x37, "MLGW ->"), 
#    (0x38, "MLGW ->"), (0x39, "-> MLGW"), 
#    (0x3a, "MLGW ->"), (0x40, "-> MLGW")
#    ] )

beo4commanddict = dict( [
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
    # Sound and picture control:
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
    ] )

BEO4_CMDS = {v.upper(): k for k, v in beo4commanddict.items()}

### for '0x02: Source Status'

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

soundstatusdict = dict( [
    (0x00, "Not muted"), (0x01, "Muted")
    ] )

speakermodedict = dict( [
    (0x01, "Center channel"), (0x02, "2ch stereo"), (0x03, "Front surround"),
    (0x04, "4ch stereo"), (0x05, "Full surround"),
    #  Dummy for 'Listen for all modes'
    (0xfd, "<all>")
    ] )

reverse_speakermodedict = {v.upper(): k for k, v in speakermodedict.items()}

screenmutedict = dict( [
    (0x00, "not muted"), (0x01, "muted")
    ] )

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
# ##### Decode MLGW Protokoll packet to readable string

## Get decoded string for mlgw packet's payload type
#
def _getpayloadtypestr( payloadtype ):
        result = payloadtypedict.get( payloadtype )
        if result == None:
            result = "UNKNOWN (type=" + _hexbyte( payloadtype ) + ")"
        return result

def _getraumstr( raum ):
    result = roomdict.get( raum )
    if result == None:
        result = "Room=" + str( raum )
    return result

def _getmlnstr( mln ):
    result = mlndict.get( mln )
    if result == None:
        result = "MLN=" + str( mln )
    return result
    
def _getbeo4commandstr( command ):
        result = beo4commanddict.get( command )
        if result == None:
            result = "Cmd=" + _hexbyte( command )
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
        resultstr = _getraumstr( message[4] ) + " " + _getdictstr( lctypedict, message[5] ) + " " + _getbeo4commandstr( message[6] )

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


class MLGateway(object):
    def __init__(self, name, host='mlgw.local', user='admin', password='admin', port=9000, logging=False):
        self._name = name
        self._host = host
        self._user = user
        self._password = password
        self._port = port
        self._tcpip = None
        self.buffersize = 1024
        self._socket = None
        self.telegramlogging = logging
        self._mln = None
        self.connected = False

    ## Open tcp connection to mlgw
    def OpenConnection(self):
        self.connected = False

        # get ip address for hostname
        try:
            self._tcpip = socket.gethostbyname(self._host)
        except Exception as e:
            _LOGGER.error("mlgw: Error resolving '%s': %s" % (self._host, e))
            return

        # open socket to masterlink gateway
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
             self._socket.connect((self._tcpip, self._port))
        except Exception as e:
            _LOGGER.error("mlgw: Error opening connection to %s: %s" % (self._tcpip, e))
            return
        if self._tcpip != self._host:
            _LOGGER.info("mlgw: Opened connection to ML Gateway '" + self._host + "' on IP " + self._tcpip + ":" + str(self._port))
        else:
            _LOGGER.info("mlgw: Opened connection to ML Gateway on IP " + self._tcpip + ":" + str(self._port))
        self.connected = True
        return

    ## Close connection to mlgw
    def CloseConnection(self):
        if self.connected:
            self.connected = False
            self._socket.shutdown(socket.SHUT_RDWR)
            self._socket.close()
            _LOGGER.info("mlgw: Closed connection to ML Gateway")
        return

    ## Send command to mlgw
    def SendCommand(self, msg_type, payload):
        if self.connected:
            self._telegram = bytearray()
            self._telegram.append(0x01)             # byte[0] SOH
            self._telegram.append(msg_type)         # byte[1] msg_type
            self._telegram.append(len(payload))     # byte[2] Length
            self._telegram.append(0x00)             # byte[3] Spare
            for p in payload:
                self._telegram.append(p)
            self._socket.send(self._telegram)

            # Sleep to allow msg to arrive
            time.sleep(1)

            if self.telegramlogging:
                if msg_type == 0x36:
                    loglevel = loglevel_keepalivetelegrams
                else:
                    loglevel = loglevel_senttelegrams
                _LOGGER.log(loglevel, "mlgw: >SENT: " + _getpayloadtypestr(msg_type) + ": " + _getpayloadstr(self._telegram))  # debug

    ## Send Beo4 command to mlgw
    def beo4_cmd(self, mln, dest, cmd):
        self._payload = bytearray()
        self._payload.append(mln)              # byte[0] MLN
        self._payload.append(dest)             # byte[1] Dest-Sel (0x00, 0x01, 0x05, 0x0f)
        self._payload.append(cmd)              # byte[2] Beo4 Command
#        self._payload.append(0x00)             # byte[3] Sec-Source
#        self._payload.append(0x00)             # byte[3] Link
        self.SendCommand(0x01, self._payload)

    def virtual_btn_press(self, btn):
        self.SendCommand(0x20, [btn])

    def all_standby(self):
        self.virtual_btn_press(2)
        # self.beo4_cmd(0x01, 0x0F, BEO4_CMDS.get('STANDBY'))

    ## Receive message from mlgw
    def ReceiveCommand(self):
        if self.connected:
            try:
                self._mlgwdata = self._socket.recv(self.buffersize)
            except KeyboardInterrupt:
                _LOGGER.error("mlgw: KeyboardInterrupt, terminating...")
                self.CloseConnection()
                sys.exit(1)

            self._payloadstr = _getpayloadstr(self._mlgwdata)
            if self._mlgwdata[0] != 0x01:
                _LOGGER.error("mlgw: Received telegram with SOH byte <> 0x01")
            if self._mlgwdata[3] != 0x00:
                _LOGGER.error("mlgw: Received telegram with spare byte <> 0x00")
            if self.telegramlogging:
                loglevel = loglevel_receivedtelegrams
                if self._mlgwdata[1] == 0x37:
                    loglevel = loglevel_keepalivetelegrams
                _LOGGER.log(loglevel, "mlgw: <RCVD: '" + _getpayloadtypestr(self._mlgwdata[1]) + "': " + str(self._payloadstr))  # debug
            return (self._mlgwdata[1], str(self._payloadstr))

    ## Get serial number of mlgw
    def GetSerial(self):
        if self.connected:
            # Request serial number
            self.SendCommand(0x39, '')
            (result, self._serial) = self.ReceiveCommand()
            _LOGGER.warning("mlgw: Serial number of ML Gateway is " + self._serial)  # info
        return

    ## Test and login if necessary
    def Login(self):
        if not self.connected:
            return

        # send Ping
        (result, self._wrkstr) = self.ping()
        if result == 0x31:
            _LOGGER.info("mlgw: Login required for this ML Gateway")
            self._wrkstr = self._user + chr(0x00) + self._password
            self._payload = bytearray()
            for i in range(0, len(self._wrkstr)):
                self._payload.append(ord(self._wrkstr[i]))
            self.SendCommand(0x30, self._payload)   # Login Request
            (result, self._wrkstr) = self.ReceiveCommand()
            if self._wrkstr == 'FAIL':
                _LOGGER.error("mlgw: Login not successful, user / password combination is not valid!")
                self.CloseConnection()
            else:
              _LOGGER.info("mlgw: Login successful, connection established")
        else:
            _LOGGER.info("mlgw: Connection established")
        return

    def ping(self):
        self.SendCommand(0x36, '')
        return self.ReceiveCommand()

    def get_device(self, mln):
        self._mln = mln
        return self

    @property
    def name(self):
        return self._name + self._mln

    def turn_on(self):
        self.select_source(DEFAULT_SOURCE)

    def turn_off(self):
        self.beo4_cmd(self._mln, 0x01, BEO4_CMDS.get('STANDBY'))

    def select_source(self, source):
        self.beo4_cmd(self._mln, 0x01, BEO4_CMDS.get(source))

    def turn_vol_up(self):
        self.beo4_cmd(self._mln, 0x01, BEO4_CMDS.get('VOLUME UP'))

    def turn_vol_down(self):
        self.beo4_cmd(self._mln, 0x01, BEO4_CMDS.get('VOLUME DOWN'))


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    rooms = [
        (0x01, "Living_room"), (0x02, "Outdoor"), (0x03, "Bedroom"), (0x04, "Toilet"), (0x05, "Kitchen")
    ]
    mlns = [
        (0x01,"Dining room"), (0x02,"Main terrace"), (0x03,"Side terrace")
    ]
    

    _LOGGER.debug("mlgw: mlgw.__init__()")
    mlgw = MLGateway('name', logging=True)
    mlgw.OpenConnection()
    if mlgw.connected:
        # mlgw.GetSerial()
        mlgw.Login()
    try:
        dining_speaker = mlgw.get_device(0x01)
        dining_speaker.turn_on()
        dining_speaker.turn_vol_up()
        dining_speaker.turn_vol_up()

        # main_terrace = mlgw.get_device(0x02)
        # main_terrace.turn_vol_up()
        # main_terrace.turn_vol_up()
        # main_terrace.turn_on()
        # time.sleep(1)
        
        # mlgw.virtual_btn_press(1)

        # mlgw.all_standby()
        # time.sleep(1)
    finally:
        mlgw.CloseConnection()
        time.sleep(2)