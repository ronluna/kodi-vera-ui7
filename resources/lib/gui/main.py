import sys
import re
import time
import threading
import socket
import httplib

import xbmc
import xbmcgui
import xbmcaddon

import vera
import vera.scene
import vera.device 
import vera.device.category

import gui.controlid.main as controlid
import gui.device
import gui.scene

from gui.xbmc import * 

__addon__   = xbmcaddon.Addon('script.verav1')
__cwd__     = __addon__.getAddonInfo('path')

class UpdateThread(threading.Thread):

    def __init__(self, gui_):
        threading.Thread.__init__(self)
        self.gui = gui_

    def run(self):
        while(self.gui.runUpdateThread):
            ok = False
            try:
                self.gui.vera.update()
                self.gui.update()
                self.gui.fromGui     = False
                ok = True
            except socket.error as e:
                if self.gui.runUpdateThread:
                    msg = 'socket: %s' % e.__str__() 
                    error_dialog = xbmcgui.Dialog()
                    error_dialog.ok( 'Network Connection Error', msg )
            except httplib.BadStatusLine:
                if self.gui.runUpdateThread:
                    raise
                else: # socket has been deliberately shutdown
                    pass
            finally:
                if not ok:
                    self.gui.runUpdateThread = False
		
class GUI( xbmcgui.WindowXMLDialog ):

    def __init__(self, *args, **kwargs):
        self.buttonIDToRoom         = {}
        self.buttonIDTo             = {}
        self.buttonType             = {}
        self.setVera()
        self.currentRoom            = None
        self.setUpdateThread()
        self.room                   = 103
        self.scene                  = 105
        self.device                 = 1
        self.onCommit               = False
#        self.fromGui                = True

    def onInit(self):
        self.ControlListRoom        = self.getControl(self.room)
        self.ControlListSceneDevice = self.getControl(self.scene)
        self.fromGui                = True
        self.startUpdateThread()

    def setUpdateThread(self):
        self.runUpdateThread = True
        self.updateThread = UpdateThread(self)

    def startUpdateThread(self):
        if not self.updateThread:
            self.setUpdateThread()
        self.updateThread.start()


   
    def killUpdateThread(self, wait=False):
        self.runUpdateThread = False
        time.sleep(0.2) # dirty
        try:
            # Yeah, this is necessary to 'kill' the awaiting http client
            if self.vera.updateConnection.sock:
                self.vera.updateConnection.sock.shutdown(socket.SHUT_RDWR)
        except AttributeError:
            pass

        if wait and self.updateThread: 
            self.updateThread.join()
        self.updateThread = None

    def exit(self):
        self.killUpdateThread()
        self.close()

    def onAction(self, action):
        if self.getFocusId() == self.scene:
            if action == ACTION_MOVE_LEFT or action == ACTION_MOVE_RIGHT:
               self.setFocusId(103)
               self.ControlListSceneDevice.reset()
               
        if action == ACTION_PREVIOUS_MENU:
            self.exit()

    def onClick(self, controlID):
        while True:
           if not self.updateFillRoom :
              break   
        # Top buttons
        if      controlID == controlid.SETTINGS:
            __addon__.openSettings()
            self.killUpdateThread(wait=True)
            self.setVera()
            self.startUpdateThread()
        elif    controlID == controlid.GET_DATA:
            self.forceRefresh()
        elif    controlID == controlid.EXIT:
            self.exit()

        # Rooms
        elif    controlID == self.room:
            room_ = self.buttonIDToRoom[self.ControlListRoom.getSelectedPosition()]
            self.fromGui = True
            self.fillRoom(room_)
        elif    controlID == controlid.ROOM_NONE:
            self.fromGui = True
            self.fillRoom(None)
        # Scenes
        elif   ( controlID == self.scene and self.buttonType[self.ControlListSceneDevice.getSelectedPosition()] == self.scene) :
            scene = self.buttonIDTo[self.ControlListSceneDevice.getSelectedPosition()]
            try:
                vera.scene.run(scene, vera_controller=self.vera)
            except socket.error as e:
                msg = 'socket: %s' % e.__str__()
                error_dialog = xbmcgui.Dialog()
                error_dialog.ok( 'Network Connection Error', msg )

        # Devices
        elif      (controlID == self.scene and self.buttonType[self.ControlListSceneDevice.getSelectedPosition()] == self.device):
            device = self.buttonIDTo[self.ControlListSceneDevice.getSelectedPosition()]
            if gui.device.simplySwitchable(device):
                try:
                    vera.device.toggle(device, vera_controller=self.vera) 
                except socket.error as e:
                    msg = 'socket: %s' % e.__str__() 
                    error_dialog = xbmcgui.Dialog()
                    error_dialog.ok( 'Network Connection Error', msg )
            else: # requires a new window, has its own exception handling
                gui.device.popup(self, device)
		
    def forceRefresh(self):
        self.killUpdateThread()
        self.vera.getData()
        self.fromGui = True
        self.update()
        self.startUpdateThread()

    def update(self):
        self.updateRooms()
        self.fillRoom(self.currentRoom)

    def updateRooms(self):
        rooms = self.vera.data['rooms']
        savePosition_ = self.ControlListRoom.getSelectedPosition()		
        self.ControlListRoom.reset()
	
        self.ControlListRoom.addItem("(other devices and scenes)") 
        self.buttonIDToRoom[0] = None		

        controlID = 1
        for room in rooms:
            self.ControlListRoom.addItem(room['name'])
            self.buttonIDToRoom[controlID] = room
            controlID += 1
        self.ControlListRoom.selectItem(savePosition_)	
    def showLabel(self, controlID, label):
        control = self.getControl(controlID)
        control.setVisible(True)
        control.setLabel(label)

    def setVera(self):
        self.vera = vera.Controller(__addon__.getSetting('controller_address'))
		
    def fixDevice(self, device):
        try:
           htmlHeat = self.vera.GET('/data_request?id=variableget&DeviceNum=' + str(device['id']) + '&serviceId=urn:upnp-org:serviceId:TemperatureSetpoint1_Heat&Variable=CurrentSetpoint',timeout=5)
#           print   '/data_request?id=variableget&DeviceNum=' + str(device['id']) + '&serviceId=urn:upnp-org:serviceId:TemperatureSetpoint1_Heat&Variable=CurrentSetpoint'		   
#           print htmlHeat
           device['heat'] = htmlHeat
        except :
           device['heat'] = 60
           pass
        try:
           htmlCool = self.vera.GET('/data_request?id=variableget&DeviceNum=' + str(device['id']) + '&serviceId=urn:upnp-org:serviceId:TemperatureSetpoint1_Cool&Variable=CurrentSetpoint',timeout=5)
           device['cool'] = htmlCool
        except :
           device['cool'] = 72		
           pass

        return device


    def fillRoom(self, room):
        self.currentRoom    = room
        buttonID            = 0
        self.updateFillRoom = True

        for scene in self.vera.data['scenes']:
            if \
                    ( room and int(scene['room']) == int(room['id']) ) or \
                    ( not room and not int(scene['room']) )            :
                if not buttonID:
                    if self.fromGui:
                        self.ControlListSceneDevice.reset()
                self.showSceneButton(buttonID, scene)
                self.buttonIDTo[buttonID] = scene
                self.buttonType[buttonID] = self.scene
                if not buttonID:
                    if self.fromGui:
                        self.setFocusId(105)
                buttonID += 1

        for device in self.vera.data['devices']:
            if device['category'] in vera.device.category.DISPLAYABLE:
                if \
                    ( room and int(device['room']) == int(room['id']) ) or \
                    ( not room and not int(device['room']) )            :
                    if not buttonID:
                        if self.fromGui:
                           self.ControlListSceneDevice.reset()
# ******************************************************************************************
# this is the bad patch 
# ******************************************************************************************
                    if (device['category'] == 5) :
                          while  True:
                              if not self.onCommit:
                                   break
                          device = self.fixDevice(device)
# ******************************************************************************************
# this is the bad patch 
# ******************************************************************************************
                    self.showDeviceButton(buttonID, device)
                    self.buttonIDTo[buttonID] = device
                    self.buttonType[buttonID] = self.device
                    if not buttonID: 
                       if self.fromGui:
                          self.setFocusId(105)
                    buttonID += 1

        self.updateFillRoom = False
        
    def showSceneButton(self, buttonID, scene):
        self.itemUpdate     = False
        label2              = self.setButtonComment   (buttonID, scene )
        info                = self.setSceneInfo       (buttonID, scene )
        SceneStateColor     = self.setStateColor      (buttonID, scene )
        if self.fromGui:
           listitem         = xbmcgui.ListItem()
        else:
           listitem         = self.ControlListSceneDevice.getListItem(buttonID)

        listitem.setLabel   (scene['name'])
        listitem.setLabel2	(label2)
        listitem.setProperty("Info",       info)	
        listitem.setProperty("statusIcon", SceneStateColor)
		
        if self.fromGui:
           self.ControlListSceneDevice.addItem(listitem)

    def showDeviceButton(self, buttonID, device):
        label2              = self.setButtonComment(buttonID, device)       
        info                = self.setDeviceInfo   (buttonID, device)
        DeviceStateColor    = self.setStateColor   (buttonID, device)
        if self.fromGui:
           listitem         = xbmcgui.ListItem()
        else:
           listitem         = self.ControlListSceneDevice.getListItem(buttonID)
		   
        listitem.setLabel   (device['name'])
        listitem.setLabel2	(label2)
        listitem.setProperty("Info", info)	
        listitem.setProperty("Icon", gui.device.icon(device))
        listitem.setProperty("statusIcon", DeviceStateColor)

        if self.fromGui:
           self.ControlListSceneDevice.addItem(listitem)
    
    def setButtonComment(self, buttonID, device):
        if 'comment' in device.keys():
            # turn '_Light: My message' into 'My message'
            # with or w/o leading underscore
            text = re.sub(                          \
                    '^_?' + device['name'] + ': ',  \
                    '',                             \
                    device['comment']               \
            )
            textWithTags = '[I][COLOR grey]%s[/COLOR][/I]' % text
        else:
            textWithTags = ''
        return 	textWithTags

    def setStateColor(self, buttonID, device):
        return gui.device.stateBgImage(device)

    def setSceneInfo(self, buttonID, scene):
        if 'active' in scene.keys():
           if scene['active']:
              return 'Active' 
           else:
              return '[COLOR grey][I]Not Active[/I][/COLOR]'
        else:
           return '[COLOR grey][I]Not Active[/I][/COLOR]'
    
    def setDeviceInfo(self, buttonID, device):
        string = gui.device.essentialInfo(
                device,
                temperature_unit=self.vera.data['temperature']
        )
        return string
