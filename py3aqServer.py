import json
import logging
import os
import shutil
import datetime
import time
import socket
import ctypes
import struct
import random

import snap7
from snap7.types import S7DataItem, S7AreaDB, S7WLByte
from snap7.common import check_error

from progress.bar import Bar

import FileUtils
from kbhit import *
import TimeUtils
import PrgUtils

class aqServer:
    
    lvariables = []
    lformats = []
    lnames = []
    lgains = []
    loffsets = []
    
    attempts = 0
    cntcalls = 0
    cntitems = 0
    formats  = []
    names    = []
    gains    = []
    offsets  = []
    units    = []
    
    def __init__( self, ConfigPath ):
        self.getConfig( ConfigPath ) 
        
        self.setDebugLevel()
        self.initLogging()
        
        self.setValidatedIP()
        self.setTrigger()
            
        self.connectToPLC()
        self.setValueSettings()
        
        self.getArea()
        self.setHeader()
        
        self.runScanLoop()
        # Waits for KeyInput to Interrupt

    def getConfig( self, ConfigPath ):
        # Ermittelt die benötigte ConfigFile und Pfade
        #  - ConfigFile in 'json' und 'cfg'
        #  - Pfade abhängig von Speicherort des Servers
        
        if os.path.isfile( ConfigPath ):
            self.CurrentDir = __file__.replace('\\', '/').replace( '/py3aqServer.py', '' )
            
            self.DataDir = self.CurrentDir + '/data'
            if not os.path.exists( self.DataDir ):
                os.mkdir( self.DataDir )
                    
            self.LogDir  = self.CurrentDir + '/log'
            if not os.path.exists( self.LogDir ):
                os.mkdir( self.LogDir )
        else:
            print( "Config does not exist or is not in JSON-format" )
            exit()
        
        if ConfigPath.split('.')[-1] == 'json':
            self.Config = json.load( open( ConfigPath, 'r' ) )
            
            self.ConfigAqdata        = self.Config['aqdata']
            self.ConfigCommunication = self.Config['communication']
            self.ConfigMsic          = self.Config['misc']
            self.ConfigTrigger       = self.Config['trigger']
            self.ConfigDebug         = self.Config['debug']
            self.ConfigValues        = self.Config['values']
        
        elif ConfigPath.split('.')[-1] == 'cfg':
            self.ConfigAqdata, self.ConfigCommunication, self.ConfigMsic, self.ConfigValues, self.ConfigTrigger, self.ConfigDebug, self.Config = PrgUtils.get_config( ConfigPath )
        
        self.ConfigFile     = ConfigPath
        self.ConfigScantime = int(self.ConfigMsic['scantime'])
        
        self.Datapath = self.ConfigMsic['datapath'].replace( '\\', '/' )
        
        self.fName = f'{ self.DataDir }/{ self.ConfigMsic["datafile"] }.csv'
        self.hName = f'{ self.DataDir }/{ self.ConfigMsic["datafile"] }_header.csv'
        
        self.hFile = f'{ self.ConfigMsic["datafileprefix"] }_hdr.csv' 
            
        self.Demo     = True if self.ConfigCommunication['demo'] else False
        self.UseDir   = True if self.ConfigMsic['usedir'] else False
        self.Autostart= True if self.ConfigMsic['autostart'] else False
        self.scantime = 0.02 if int(self.ConfigMsic['scantime'])/1000 < 0.02 else int(self.ConfigMsic['scantime'])/1000
        
        # self.Booloof  = True if self.ConfigMsic['booloffset'] else False

        self.ConfigIP        = self.ConfigCommunication['ip']
        self.Rack            = self.ConfigCommunication['rack']
        self.Slot            = self.ConfigCommunication['slot']
        self.ConnectAttempts = int(self.ConfigCommunication['maxattempts'])
        
        self.MaxRecords      = int(self.ConfigMsic['maxrecords'])
        self.delimiter       = self.ConfigMsic['delimiter']
        self.DatafilePrefix  = self.ConfigMsic['datafileprefix']
        
        self.TriggerSignal   = self.ConfigTrigger['trgsignal']
        self.TriggerCondition= self.ConfigTrigger['trgcondition']
        self.TriggerValue    = self.ConfigTrigger['trgvalue']
        self.TriggerPre      = int(self.ConfigTrigger['pretrg'])
        self.TrigerPost      = int(self.ConfigTrigger['posttrg'])
        
        self.DebugLevel      = int(self.ConfigDebug['dbglevel'])
        self.Logts           = self.ConfigDebug['logts']

    def setDebugLevel( self ):
        self.doInfo     = True if 0 < self.DebugLevel < 2 else False
        self.doWarning  = True if 0 < self.DebugLevel < 3 else False
        self.doDebug    = True if 0 < self.DebugLevel < 4 else False
        self.doError    = True if 0 < self.DebugLevel < 5 else False
        self.doCritical = True if 0 < self.DebugLevel < 6 else False
        
        if self.Logts:
            self.logFile    = f'{ self.LogDir }/{ self.DatafilePrefix }{ self.getTimestamp() }.log'
        else:
            self.logFile    = f'{ self.LogDir }/{ self.DatafilePrefix }.log' #! Hier wurde der Fallback im Orginal vergessen... (Sollte Unique sein)

    def initLogging( self ):
        self.clearFolder( self.LogDir )
        
        logging.basicConfig( filename=self.logFile )
        
        self.logger = logging.getLogger(__name__)
        self.logger.setLevel( logging.INFO )
        
        self.Log( 'info', "################## Program Started ###########################" )
        
        self.logger.setLevel( self.DebugLevel )
        
        # write settings also to logfile, if debug is set
        if self.doDebug:
            for settings in self.Config:
                self.Log( 'debug', f'{ settings }: { self.Config[ settings ] }' )
            self.Log( 'debug', f'scantime in [s]: { self.scantime }' )

    def setValidatedIP( self ):
        if self.validIPv4( self.ConfigIP ):
            self.IP = self.ConfigIP
            
            if self.doDebug:
                self.Log( 'debug', f'successfully checked IP address: { self.IP }' )
        else:
            print( f'IP address not valid: { self.ConfigIP }, program exits!' )
            
            if self.doError:
                self.Log( 'error', f'wrong IP address: { self.ConfigIP }, program stopped' )
                
            exit()

    def setTrigger( self ):
        if self.TriggerSignal != 0:
            self.doTrigger = True
            self.TriggerExpression = f"trgsignal{ self.TriggerCondition }{ self.TriggerValue }"
            
            self.preRecord = self.TriggerPre / self.scantime
            self.postRecord = self.TrigerPost / self.scantime
            
            if self.doDebug:
                self.Log( 'debug', f'TriggerExpression: { self.TriggerExpression }' )
                self.Log( 'debug', f'PreRecord: { self.preRecord }' )
                self.Log( 'debug', f'PostRecord { self.postRecord }' )
            
            self.CopyRecords = self.preRecord + self.postRecord
            
        else:
            self.doTrigger         = True
            self.TriggerExpression = "False"
            self.CopyRecords       = 0
               
        self.triggered = False
  
    def connectToPLC( self ):
        self.attempt = 0
        if not self.Demo:
            
            self.Client = snap7.client.Client()
            self.connected   = False
            
            while not self.connected:
                self.attempt += 1
                self.Client.connect( self.IP, self.Rack, self.Slot )
                
                if self.Client.get_connected():
                    self.connected = True 
                    print( f'Successfully Connected to: { self.IP }' )
                    if self.doDebug:
                        self.Log( 'debug', f'Client Connected' )
                    
                elif self.attempt >= self.ConnectAttempts and self.ConnectAttempts != 0:
                    if self.doError:
                        self.Log( 'error', f'error when trying to connect, program will end!' )
                    print( "error when trying to connect, program will end!" )
                    exit()
                    
                else:
                    print( f'Failed to connect #{ self.attempt }.' )
                    pass 
  
    def setValueSettings( self ):
        # only 20 values per multiread
        self.Calls  = ( len(self.ConfigValues) // 20 ) + 1  
        self.Remain = len(self.ConfigValues) % 20
            
        for call in range( self.Calls ):
            if call < self.Calls - 1:
                self.lvariables.append( ( S7DataItem * 20 )() )    
            else:
                self.lvariables.append( ( S7DataItem * self.Remain )() )
        
        if self.doDebug:
            self.Log( 'debug', f'Calls: { self.Calls }, Remain: { self.Remain }, Complete: { len(self.ConfigValues) }' )
            self.Log( 'debug', f'lvariables: { self.lvariables }' )
      
    def getArea( self ):
        # preset S7 area
        self.Area = 0x84
        
        self.data_items = self.lvariables[0]
        
        self.header = f'number{ self.delimiter }timestamp{ self.delimiter }'
        
        values = self.ConfigValues
        for value in values:
            try: # Json like objekt
                temp = ','.join( str(e) for e in value[ list(value)[0] ] )
                parts = value[ list(value)[0] ]
            except:
                temp = ','.join( str(e) for e in values[ value ] )
                parts = values[ value ].split( ',' )
            
            mem = parts[0]
            
            if self.doDebug:
                self.logger.debug( f' { self.getTimestamp() }: { mem }' )
                
            name = list(value)[0]
            self.names.append( name )
            
            # get the gain, defaults to 1
            gain = str( parts[1] )
            self.gains.append( gain )
            
            # get the offset, defaults to 0
            offset = str( parts[2] )
            self.offsets.append( offset )
        
            self.Area = self.get_S7_area(mem)
            dbnum, length, start, Format, hdr = self.get_data_item(
                self.Area,
                mem, 
                name, 
                self.delimiter
            )
            self.formats.append( Format )
            
            self.header = self.header + hdr

            # get the unit, which is a string (empty for booleans)
            if Format == '>B':
                if self.doDebug:
                    self.logger.debug( f' { self.getTimestamp() }: Boolean Names: { hdr }' )
                # split header to get number of boolean values
                hdrs = hdr.split( self.delimiter )
                # write delimiter to unit string for all configured bools
                unit = ( ( len( hdrs ) - 1 ) * self.delimiter )
                self.units.append(unit)
            else:
                unit = parts[3] + self.delimiter
                self.units.append( unit )
                
            if self.doDebug:
                self.logger.debug( f' { self.getTimestamp() }: Value:  { temp }' )
                self.logger.debug( f' { self.getTimestamp() }: Name:   { name }' )
                self.logger.debug( f' { self.getTimestamp() }: Gain:   { gain }' )
                self.logger.debug( f' { self.getTimestamp() }: Offset: { offset }' )
                self.logger.debug( f' { self.getTimestamp() }: Units:  { unit }' )
                
            lenName   = len( name.split(',') )
            lenGain   = len( gain.split('-') )
            lenOffset = len( offset.split('-') )
            lenUnit   = len( unit.split(';') ) - 1
            
            if ( lenName != lenGain ) or (lenName != lenOffset) or (lenName != lenUnit):
                if self.doError:
                    self.logger.error( f' { self.getTimestamp() }: Check your value declaration line for  { name }\n. Number of Names = { lenName }, Gains = { lenGain }, Offsets = { lenOffset } or units = { lenUnit }' )
                exit()
            
        ###################################################################
            # now we check every single item by reading it once from PLC  #
            # if we have a problem we exit because of wrong congiguration #
            ###################################################################
            
            self.configOK = True
            
            if not self.Demo:   
                try:
                    self.result = self.Client.read_area( snap7.types.Areas.DB, dbnum, start, length ) 
                except Exception as e:
                    if self.doError:
                        errorMsg = f' { self.getTimestamp() }: Item { mem } does NOT exist in PLC. Area: { self.Area }, dbnum: { dbnum }, Start: { start }, Length: { length }\n'
                        self.Log( 'error', errorMsg )
                        print( e )
                        print( errorMsg )
                    self.configOK = False
                    pass
                else:
                    if self.doDebug:
                        self.logger.debug( f' { self.getTimestamp() }: Item { mem } does exist in PLC\n' )
            
            # finally write results in our items as C-type variables for snap7.DLL
            self.data_items[self.cntitems].Area     = ctypes.c_int32( self.Area )
            self.data_items[self.cntitems].WordLen  = ctypes.c_int32( S7WLByte )
            self.data_items[self.cntitems].Result   = ctypes.c_int32( 0 )
            self.data_items[self.cntitems].DBNumber = ctypes.c_int32( dbnum )
            self.data_items[self.cntitems].Start    = ctypes.c_int32( start )
            self.data_items[self.cntitems].Amount   = ctypes.c_int32( length )
            
            self.cntitems += 1
            
            if self.doDebug:
                f'Number of Names = { lenName }, Gains = { lenGain }, Offsets = { lenOffset } or units = { lenUnit }'
                self.logger.debug( f' { self.getTimestamp() }: Area: { self.Area }' )
                self.logger.debug( f' { self.getTimestamp() }: dbnum: { dbnum }' )
                self.logger.debug( f' { self.getTimestamp() }: Start: { start }' )
                self.logger.debug( f' { self.getTimestamp() }: Length: { length }' )
                self.logger.debug( f' { self.getTimestamp() }: Number of Names = { lenName }, Gains = { lenGain }, Offsets = { lenOffset } or units = { lenUnit }' )

            if self.cntitems >= 20:
                self.cntitems = 0
                self.cntcalls += 1
                self.lvariables.append(self.data_items)
                self.lformats.append(self.formats)
                self.lnames.append(self.names)
                self.lgains.append(self.gains)
                self.loffsets.append(self.offsets)
                self.data_items = self.lvariables[self.cntcalls]  
            
        if self.cntitems < 20:
            self.lvariables.append(self.data_items)
            self.lformats.append(self.formats)
            self.lnames.append(self.names)
            self.lgains.append(self.gains)
            self.loffsets.append(self.offsets)
            
            if self.doDebug:
                self.logger.debug( f' { self.getTimestamp() }: Formats: { self.formats }' )
                
            self.formats = []
            self.names = []
            self.gains = []
            self.offsets = []   
        
        if not self.configOK:
            print( f'configuration fault, check most recent logfile: { self.logFile } ')
            exit()  
        
    def setHeader( self ):
        infoStr = len( self.header ) * '#' + '\n'
        infoStr = infoStr + '[aqdata]\n'
        infoStr = infoStr + f'#date\t:\t\t{ self.getTimestamp() }\n'
        
        for info in self.ConfigAqdata:
            infoStr = infoStr + f'{ info }\t\t\t{ self.ConfigAqdata[info] }\n'
        infoStr = infoStr + f'({ len(self.header) }#)\n\n[communication]\n'
        for info in self.ConfigCommunication:
            infoStr = infoStr + f'{ info }: { self.ConfigCommunication[info] }\n'
        infoStr = infoStr + f'({ len(self.header) }#)\n\n[misc]\n'
        for info in self.ConfigMsic:
            infoStr = infoStr + f'{ info }: { self.ConfigMsic[info] }\n'
        infoStr = infoStr + f'({ len(self.header) }#)\n\n[trigger]\n'
        for info in self.ConfigTrigger:
            infoStr = infoStr + f'{ info }: { self.ConfigTrigger[info] }\n'
        infoStr = infoStr + f'({ len(self.header) }#)\n\n[debug]\n'
        for info in self.ConfigDebug:
            infoStr = infoStr + f'{ info }: { self.ConfigDebug[info] }\n'
        infoStr = infoStr + f'({ len(self.header) }#)\n\n[values]\n'
        for info in self.ConfigValues:
            try:
                infoStr = infoStr + f'{ info }: { ",".join( str(e) for e in info[ list(info)[0] ] ) }\n'
            except:
                infoStr = infoStr + f'{ info }: { ",".join( str(e) for e in self.ConfigValues[info] ) }\n'
        
        unitStr = ';;'
        self.hdrNames = self.header.split(';')
        
        for unit in self.units:
            unitStr = unitStr + unit
        unitStr = unitStr[:-1]
        
        if self.doDebug:
            self.Log( 'debug', f'unitStr: { unitStr }' )
        
        infoStr = infoStr +  f'({ len(self.header) * "#" })\n\n'
        
        self.HeaderFile = FileUtils.ASCIIDataWrite()
        self.HeaderFile.openOutput( '', self.hName, 1 )
        self.HeaderFile.writeStr( infoStr, 0, 0 )
        self.HeaderFile.closeOutput()
        
        self.OutputFile = FileUtils.ASCIIDataWrite()
        self.OutputFile.openOutput( '', self.fName, 1 )
        self.OutputFile.writeStr( self.header, 0, 0 )
        self.OutputFile.writeStr( unitStr, 0, 0 )
        self.OutputFile.closeOutput()

        self.SmlHeaderFile = FileUtils.ASCIIDataWrite()
        self.SmlHeaderFile.openOutput( '', self.hFile, 1 )
        self.SmlHeaderFile.writeStr( self.header, 0, 0 )
        self.SmlHeaderFile.writeStr( unitStr, 0, 0 )
        self.SmlHeaderFile.closeOutput()
            
        self.OutputFile.openOutput( '', self.fName, 0 )
                           
    def runScanLoop( self ):
        self.exitPrg = False
        
        self.Keyboard = KBHit()
        
        numFile = 0 
        trgFile = numFile
        
        runTime   = TimeUtils.Timer()
        totalTime = TimeUtils.Timer()
        
        os.system( 'cls' )
        
        if not self.Demo:
            print( '\n***************** Aqserver running using config file: *****************' ) 
            print( f'\n{ self.ConfigFile }\n\n' )
            print( 'ESC - Exit program\nP - Pause\nS - Start\nT - Trigger new file\n\nNumber of scans:\n' )
        
        else: 
            print( '\n*********** Aqserver running in DEMO mode using config file: ***********' )
            print( f'\n{ self.ConfigFile }\n\n' )
            print( 'ESC - Exit program\nP - Pause\nS - Start\nT - Trigger new file\n\nNumber of scans:\n' )
            
        while not self.exitPrg:
            
            numRecord = 0
            numPostTriggerRecord = numRecord + 5
            
            MainRuntime = runTime.Reset()
            
            manTrigger = True
    
            BarSnippet = " files: " + str(numFile + 1) + " | scans: "
            self.bar = Bar( BarSnippet, suffix = '%(index)d/%(max)d  - %(elapsed)ds', max = self.MaxRecords )
    
            while ( not self.triggered or ( numRecord < numPostTriggerRecord ) or ( not self.doTrigger and not manTrigger ) or ( trgFile != numFile)) and not self.exitPrg and ( numRecord < self.MaxRecords ):
                
                if self.ConfigScantime > 0 or self.Demo:
                    time.sleep( self.scantime )
                
                if not self.Autostart:
                    
                    numRecord += 1
                    self.bar.next()
                    fNum = ''
                    
                    for call in range( self.Calls ):
                        self.data_items      = self.lvariables[ call ]
                        self.formats    = self.lformats[ call ]
                        self.names      = self.lnames[ call ]
                        self.gains      = self.lgains[ call ]
                        self.offsets    = self.loffsets[ call ]   
                        
                        for item in  self.data_items:
                            buffer  = ctypes.create_string_buffer( item.Amount )
                            pBuffer = ctypes.cast( ctypes.pointer( buffer ), ctypes.POINTER( ctypes.c_uint8 ) )
                            
                            item.pData = pBuffer 
                            
                        if not self.Demo:
                            if self.Client.get_connected():
                                self.attempts = 0
                        
                        else:
                            self.attempts = 0
                                
                        try:
                            if not self.Demo:
                                if not self.Client.get_connected():
                                    print( f'Not Connected, { self.attempts } attempts' )
                                    
                                    if self.doError:
                                        self.Log( 'error', f'Reconnecting Client' )

                                    self.Client.connect(  self.IP, self.Rack, self.Slot  )
                                    self.connected = True
                                    
                                result, self.data_items = self.Client.read_multi_vars( self.data_items )
                                
                                for var in self.lvariables[ call ]:
                                    check_error( var.Result )
                        
                        except BaseException:
                            self.attempts += 1
                            
                            if self.Client.get_connected():
                                
                                if self.doError:
                                    self.Log( 'error', f'Disconnecting Client, because of raised Exception' )
                                    
                                self.Client.disconnect()
                                self.connected = False
                                
                                numRecord -= 1
                                pass
                        
                        else:
                            for i in range( 0, len( self.data_items ) ):

                                di  = self.data_items[ i ]
                                fmt = self.formats[ i ]
                                nm  = self.names[ i ]
                                gn  = self.gains[ i ]
                                of  = self.offsets[ i ]
                                
                                ByteString = ""
                                
                                if not self.Demo:
                                    Byte = bytearray( [  di.pData[ num ]  for num in range( 0, di.Amount ) ] )
                                    
                                else:
                                    if fmt == '>B':
                                        Byte = struct.pack( fmt, random.randint( 0, 255 ) )
                                    elif fmt == '>b':
                                        Byte = struct.pack( fmt, random.randint( -128, 127 ) )
                                    elif fmt == '>h':
                                        Byte = struct.pack( fmt, random.randint( -32767, 32767 ) )
                                    elif fmt == '>i':
                                        Byte = struct.pack( fmt, random.randint( -16777216, 16777216 ) )
                                    elif fmt == '>f':
                                        Byte = struct.pack( fmt, random.uniform( -16777216, 16777216 ) )
                            
                                if fmt == '>B':
                                    bit = int( struct.unpack( fmt, Byte )[0] )
                                    
                                    bitname = nm.split(',')
                                    gain    = gn.split('-')
                                    ofs     = of.split('-')
                                    
                                    if self.doDebug:
                                        self.Log( 'debug', f'Lenghts: { nm } { gn } { of }' )
                                    
                                    for b in range( len( bitname ) ):
                                        if bool( bit & 1 ):
                                            if bitname[ b ] != "":
                                                
                                                if self.doDebug:
                                                    self.Log( 'debug', f'Lenghts: { len( bitname ) } { len( gain ) } { len( ofs ) } counter = { b } bitname: { bitname[b] }, gain: { gain[b] }, offset: { ofs[b] }' )
                                            
                                                bitval = 1* gain[ b ] + ofs[ b ]
                                                ByteString = ByteString + str( bitval ) + self.delimiter
                                        
                                        else:
                                            if bitname[ b ] != "":
                                                
                                                if self.doDebug:
                                                    self.Log( 'debug', f'Lenghts: { len( bitname ) } { len( gain ) } { len( ofs ) } counter = { b } bitname: { bitname[b] }, gain: { gain[b] }, offset: { ofs[b] }' )
                                                    
                                                bitval = int( ofs[b] )
                                                ByteString = ByteString + str( bitval ) + self.delimiter
                                        
                                        bit = bit >> 1
                                        
                                else:                                    
                                    ByteString = str( ( float( struct.unpack( fmt, Byte )[0] ) ) * float( gn ) + float( of )) + self.delimiter
                                
                                fNum = fNum + ByteString
                                
                                if self.doTrigger and nm == str( self.TriggerSignal ) and not self.triggered:
                                    trgsignal = float( str( struct.unpack( fmt, Byte )[0] ) )
                                    
                                    if eval( self.TriggerExpression ):
                                        self.triggered = True

                                        if self.postRecord > 0:
                                            numPostTriggerRecord = numRecord + self.postRecord
                                            
                                            if self.doInfo:
                                                self.Log( 'info', f'value trigger !! Waiting for post-trigger records' )
                                            
                                        else:
                                            numPostTriggerRecord = numRecord
                                            
                                            if self.doInfo:
                                                self.Log( 'info', f'value trigger !! No post-trigger records' )
                                
                                elif ( self.doTrigger and nm == self.TriggerSignal and self.triggered and ( trgFile != numFile ) ) or manTrigger:
                                    trgsignal = float( str( struct.unpack( fmt, Byte )[0] ) )

                                    if not eval( self.TriggerExpression ) and not manTrigger:
                                        self.triggered = False
                                        numPostTriggerRecord = numRecord + 1
                                        trgFile = numFile
                                        
                                if not self.triggered:
                                    numPostTriggerRecord = numRecord + 1
                                    
                        if not self.Demo:
                            if not self.Client.get_connected():
                                break
                            
                    self.OutputFile.writeStr( fNum, self.delimiter, 1, 1 )
                    
                # check for ESC key to end recording and further keys...
                
                if self.Keyboard.kbhit():
                    pressedKey = ord( self.Keyboard.getch() )
                    
                    if pressedKey == 27 or ( self.attempts >= self.ConnectAttempts and self.ConnectAttempts != 0 ):
                        self.exitPrg = True
                        
                    if pressedKey == 112 or pressedKey == 80:
                        self.Autostart = True
                        
                    if pressedKey == 115 or pressedKey == 83:
                        self.Autostart = False
                        
                    if pressedKey == 116 or pressedKey == 84 and not self.triggered:
                        self.triggered = True
                        numPostTriggerRecord = numRecord
                        manTrigger = True
                        
                        if self.doInfo:
                            self.Log( 'info', f'Keyboard Trigger !!' )
                            
            print( '\n' )
            MainRuntime = runTime.GetTotal()
            totalTime   = runTime.GetTotal()
            
            if self.doInfo:
                if numRecord > 0:
                    self.Log( 'info', f'{ numRecord } values, file runtime: { MainRuntime } [s], average: { MainRuntime/numRecord }' )
                    
            self.OutputFile.closeOutput()
            
            if os.path.exists( self.Datapath ):
                if self.UseDir:
                    year, month, day = TimeUtils.getYMD()
                    
                    tempPath = f'{ self.Datapath }/{ year }'
                    if not os.path.exists( tempPath ):
                        os.mkdir( tempPath )
                        
                    tempPath = f'{ tempPath }/{ month }'
                    if not os.path.exists( tempPath ):
                        os.mkdir( tempPath )

                    tempPath = f'{ tempPath }/{ day }'
                    if not os.path.exists( tempPath ):
                        os.mkdir( tempPath )
                
                self.FilenameCompressed = f'{ tempPath }/{ self.DatafilePrefix }'
                
                if self.doDebug:
                    self.Log( 'debug', f'Filename: { self.fName }' )
                    self.Log( 'debug', f'Compressed Filename : { self.FilenameCompressed }' )
                    
            else:
                print( f'path does not exist: { self.Datapath }' )
                print( f'using { self.DataDir }/ instead !' )
                
                if self.doWarning:
                    self.Log( 'warning', f'path does not exist: { self.Datapath }' )
                    
                tempPath = f'{ self.DataDir }/'

                if self.UseDir:
                    year, month, day = TimeUtils.getYMD()
                    
                    tempPath = f'{ self.Datapath }/{ year }'
                    if not os.path.exists( tempPath ):
                        os.mkdir( tempPath )
                        
                    tempPath = f'{ tempPath }/{ month }'
                    if not os.path.exists( tempPath ):
                        os.mkdir( tempPath )

                    tempPath = f'{ tempPath }/{ day }'
                    if not os.path.exists( tempPath ):
                        os.mkdir( tempPath )
                
                self.FilenameCompressed = f'{ tempPath }/{ self.DatafilePrefix }'   
            
            inFile = self.fName
            outFile = self.FilenameCompressed + TimeUtils.getTSfName() + '.csv.gz'
            
            FileUtils.compressFile( inFile, outFile )
            
            if self.doInfo:
                self.Log( 'info', f'created archive: { outFile }' )
                
            if not self.exitPrg and ( self.triggered or numRecord >= self.MaxRecords ):
                tempFile_1 = self.DatafilePrefix + '_temp1.csv' 
                tempFile_2 = self.DatafilePrefix + '_temp2.csv' 
                tempFile_3 = self.DatafilePrefix + '_temp3.csv' 
                
                headerfile = self.hFile
                
                os.system( 'cls' )
                
                if not self.Demo:
                    print( '\n***************** Aqserver running using config file: *****************' )
                    print( f'\n{ self.ConfigFile }\n\n' )
                    print( 'ESC - Exit program\nP - Pause\nS - Start\nT - Trigger new file\n\nNumber of scans:\n' )
                else:
                    print( '\n***************** Aqserver running using config file: *****************' )
                    print( f'\n{ self.ConfigFile }\n\n' )
                    print( 'ESC - Exit program\nP - Pause\nS - Start\nT - Trigger new file\n\nNumber of scans:\n' )
                
                PrgUtils.fileCopyTrgLines( self.fName, tempFile_1, int(self.CopyRecords) )
                PrgUtils.fileReOrder( tempFile_1, tempFile_2, self.delimiter, True )
                PrgUtils.fileAppend( tempFile_3, headerfile, tempFile_2, False, True )
                
                shutil.copy2( tempFile_3, self.fName )
                
                self.OutputFile.openOutput( '', self.fName, 0, self.CopyRecords )
                numFile += 1
                manTrigger = False
                self.triggered = False
                numPostTriggerRecord = numRecord + 1
                trgFile = numFile
                self.bar.finish()
                
        if not self.Demo:
            self.Client.disconnect()
            self.Client.destroy()
            
        tempFile_3 = self.DatafilePrefix + '_temp3.csv'
        headerfile = self.hFile
        if os.path.isfile( headerfile ):
            os.remove( headerfile )
        if os.path.isfile( tempFile_3 ):
            os.remove( tempFile_3 )
            
        headerOutFile = self.Datapath + '/' + self.DatafilePrefix + TimeUtils.getTSfName() + '_header.csv.gz'
        FileUtils.compressFile( self.hName, headerOutFile )
        
        self.logger.setLevel( logging.INFO )
        self.Log( 'info', f'################## program stopped by user ###################' )
        
        print( 'Good bye from AqServer' )              

              
#### Logger ####

    def Log( self, Type, msg ):
        
        LoggingString = f' { self.getTimestamp() }: { msg } '
        
        if Type.lower() == 'info':
            self.logger.info( LoggingString )
        elif Type.lower() == 'warning':
            self.logger.warning( LoggingString )
        elif Type.lower() == 'debug':
            self.logger.debug( LoggingString )
        elif Type.lower() == 'error':
            self.logger.error( LoggingString )
        elif Type.lower() == 'critical':
            self.logger.critical( LoggingString )

################              
      
                                
###### Hilfe #######

    def clearFolder( self, Path ):
        for filename in os.listdir( Path ):
            file_path = os.path.join( Path, filename )
            try:
                if os.path.isfile( file_path ) or os.path.islink( file_path ):
                    os.unlink( file_path )
                elif os.path.isdir( file_path ):
                    shutil.rmtree( file_path )
            except Exception as e:
                print( f'Failed to delete { file_path }. Reason: { e }' )
                
    def getTimestamp( self ):
        return datetime.datetime.fromtimestamp(time.time()).strftime('%Y%m%d_%H%M')
            
    def validIPv4( self, IP ):
        try:
            socket.inet_pton(socket.AF_INET, IP)
        except AttributeError:  # no inet_pton here, sorry
            try:
                socket.inet_aton(IP)
            except socket.error:
                return False
            return IP.count('.') == 3
        except socket.error:  # not a valid address
            return False
        return True

    def get_S7_area( self, varname ):
        # set S7 area from variable name (string)
        # returns area as int
        n = varname[0].lower()
        # flags
        if( n == 'f' ) or ( n == 'm' ):
            vararea=0x83
        # outputs
        elif( n == 'q' ) or ( n == 'a' ):
            vararea=0x82
        # inputs
        elif( n == 'i' ) or ( n == 'e' ):
            vararea=0x81
        # timer
        elif( n == 't' ):
            vararea=0x1D
        # counter
        elif( n == 'z' ) or ( n == 'c' ):
            vararea=0x1C
        # data block
        elif( n == 'd' ):
            vararea=0x84 
        return vararea
    
    def get_data_item( self, area, mem, name, delimiter ):
        if area==0x84:
            # data block
            # format DBn.DXn.x if only a bit (x is 0..7)
            # or DBn.DYn
            # where n is a whole number (pay attention to address ranges of PLC)
            # where y is B for BYTE
            #            W for WORD (integer)
            #            D for DOUBLE WORD integer
            #  			 F for DOUBLE WORD float (real)
            # split data address into DB and operand
            parts = mem.split('.')
            # omit DB, get number
            dbnum = int(parts[0][2:])
            # get operand 
            memformat =  parts[1][1]
            # get address for data bit
            if(memformat.lower()=='x'): #bit
                # only one byte
                length=1
                # format bool
                # byte address
                start = int(parts[1][2:])				
                Format = '>B'
                # split name for bit name
                bitname = name.split(',')
                hdr =""
                for i in range(0,len(bitname)):
                    if bitname[i] != "":
                        hdr = hdr + bitname[i].upper() + delimiter
            
            # get address for data
            if(memformat.lower()=='b'): #byte
                length=1
                start = int(parts[1][2:])
                Format = '>b'
                hdr = name + delimiter
            if(memformat.lower()=='w'): #word
                length=2
                start = int(parts[1][2:])
                Format = '>h'
                hdr = name + delimiter
            if(memformat.lower()=='d'): #dword
                length=4
                start = int(parts[1][2:])
                Format = '>i'
                hdr = name + delimiter
            if(memformat.lower()=='f'): #double word (real numbers)
                length=4
                start = int(parts[1][2:])
                Format = '>f'
                hdr = name + delimiter
                
        else:
            # get address for other bits (I,O,F,T,C)
            memformat =  mem[1]
            # this time dbnum is 0
            dbnum = 0
            
            if(memformat.lower()=='x'): #bit
                length=1
                start = int(mem.split('.')[0][2:])
                Format = '>B'
                # split name for bit name
                bitname = name.split(',')
                hdr =""
                for i in range(0,len(bitname)):
                    if bitname[i] != "":
                        hdr = hdr + bitname[i].upper() + delimiter
            if(memformat.lower()=='b'): #byte
                length=1
                start = int(mem[2:])
                Format = '>b'
                hdr = name + delimiter
            if(memformat.lower()=='w'): #word
                length=2
                start = int(mem[2:])	
                Format = '>h'
                hdr = name + delimiter
            if(memformat.lower()=='d'): #dword
                length=4
                start = int(mem.split('.')[0][2:])
                Format = '>i'
                hdr = name + delimiter
            if(memformat.lower()=='f'): #double word (real numbers)
                length=4
                start = int(mem.split('.')[0][2:])
                Format = '>f'
                hdr = name + delimiter
        return dbnum, length, start, Format, hdr

####################    
        
if __name__ == '__main__':    
    if isinstance(
            PrgUtils.parse_sys_args(),
            list) or isinstance(
                PrgUtils.parse_sys_args(),
            tuple):
        configfile = PrgUtils.parse_sys_args()[0]
    else:
        configfile = PrgUtils.parse_sys_args()
        
    
    #* Example:
    #* python38 C:\Users\USER\Documents\Aqserver\py3aqServer.py -c C:\Users\USER\Documents\Aqserver\aqserver.json

    if os.path.exists( configfile ):
        aqServer( configfile )