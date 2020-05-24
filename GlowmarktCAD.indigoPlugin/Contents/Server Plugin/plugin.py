#! /usr/bin/env python
# -*- coding: utf-8 -*-
####################
# Copyright (c) 2020 neilk
#
# Based on the sample dimmer plugin

################################################################################
# Imports
################################################################################
import indigo
import requests
import json
import time
import datetime

################################################################################
# Globals
################################################################################



################################################################################
class Plugin(indigo.PluginBase):
    ########################################
    # Class properties
    ########################################

    ########################################
    def __init__(self, pluginId, pluginDisplayName, pluginVersion, pluginPrefs):
        super(Plugin, self).__init__(pluginId, pluginDisplayName, pluginVersion, pluginPrefs)
        self.debug = pluginPrefs.get("showDebugInfo", False)
        self.deviceList = []


    ########################################
    def deviceStartComm(self, device):
        self.debugLog("Starting device: " + device.name)
        self.debugLog(str(device.id)+ " " + device.name)
        device.stateListOrDisplayStateIdChanged()
        if device.id not in self.deviceList:
            self.update(device)
            self.deviceList.append(device.id)



    ########################################
    def deviceStopComm(self, device):
        self.debugLog("Stopping device: " + device.name)
        if device.id in self.deviceList:
            self.deviceList.remove(device.id)

    ########################################
    def runConcurrentThread(self):
        self.debugLog("Starting concurrent thread")
        try:
        	pollingFreq = int(self.pluginPrefs['pollingFrequency'])
        except:
        	pollingFreq = 15

        try:
            while True:
                # we will check if we have crossed into a new 30 minute period every 30s (so worst case the update could be 30s late)
                # this is currently configurable (it may be lower as a default the check can be quick without hitting the API so that the rate change happens close to minute 00 and minute 30)
                # At present the polling frequency will determine the max number of seconds in a given period the tariff could be out of date
                self.sleep(1 * pollingFreq )
                for deviceId in self.deviceList:
                    # call the update method with the device instance
                    self.update(indigo.devices[deviceId])
                    self.debugLog("Checking the Message Queue")
        except self.StopThread:
            pass



    ########################################
    def update(self,device):
    	#device.stateListOrDisplayStateIdChanged()
    	mqttPlugin = indigo.server.getPlugin("com.flyingdiver.indigoplugin.mqtt")
    	if mqttPlugin.isEnabled():
			props = {
				'message_type':"##GlowmarktCAD##"
			}
			while True:
				message_data = mqttPlugin.executeAction("fetchQueuedMessage", deviceId=634573472, props=props, waitUntilDone=True)
				if message_data == None: 
					return
				payload_json = json.loads(message_data["payload"])
				self.debugLog("Queue Fetch, Meter Data = {}".format(payload_json))
				device_states = []
				try:
					elec_instantaneous = int(payload_json['elecMtr']['0702']['04']['00'],16)
					elec_month_consumption = float((int(payload_json['elecMtr']['0702']['04']['40'], 16))/1000)
					elec_daily_consumption = float((int(payload_json['elecMtr']['0702']['04']['01'], 16))/1000)
					elec_week_consumption = float((int(payload_json['elecMtr']['0702']['04']['30'], 16))/1000)
					electricity_supplier = payload_json['elecMtr']['0708']['01']['01']
					mpan = payload_json['elecMtr']['0702']['03']['07']
					electricity_meter = float((int(payload_json['elecMtr']['0702']['00']['00'], 16))/1000)
					gas_meter = float((int(payload_json['gasMtr']['0702']['00']['00'], 16))/1000)
					gas_week_consumption = float((int(payload_json['gasMtr']['0702']['0C']['30'], 16))/1000)
					gas_month_consumption = float((int(payload_json['gasMtr']['0702']['0C']['40'], 16))/1000)
					gas_daily_consumption = float((int(payload_json['gasMtr']['0702']['0C']['01'], 16))/1000)
					agile_cost= indigo.devices[84950009].states['Current_Electricity_Rate']
					agile_cost_hour = (agile_cost * elec_instantaneous)/1000

					
					
					device_states.append({ 'key' : 'agile_cost_hour', 'value' : agile_cost_hour, 'uiValue' : str(agile_cost_hour)+ " p" }) 
					device_states.append({ 'key' : 'elec_month_consumption', 'value' : elec_month_consumption }) 
					device_states.append({ 'key' : 'elec_week_consumption', 'value' : elec_week_consumption })
					device_states.append({ 'key' : 'elec_daily_consumption', 'value' : elec_daily_consumption }) 
					device_states.append({ 'key' : 'gas_month_consumption', 'value' : gas_month_consumption }) 
					device_states.append({ 'key' : 'gas_week_consumption', 'value' : gas_week_consumption })
					device_states.append({ 'key' : 'gas_daily_consumption', 'value' : gas_daily_consumption })
				
					device_states.append({ 'key' : 'gas_meter', 'value' : gas_meter })
					device_states.append({ 'key' : 'electricity_meter', 'value' : electricity_meter })
					device_states.append({ 'key' : 'electricity_supplier', 'value' : electricity_supplier })

					device_states.append({ 'key': 'elec_instantaneous', 'value' : elec_instantaneous , 'uiValue' :str(elec_instantaneous)+" W", 'clearErrorState':True })
				
					device.updateStatesOnServer(device_states)
					device.updateStateImageOnServer(indigo.kStateImageSel.EnergyMeterOn)
				except Exception as e:
					self.debugLog("Oops!", e.__class__, "occurred.")

        return

    ########################################
    # UI Validate, Plugin Preferences
    ########################################
    def validatePrefsConfigUi(self, valuesDict):
        
        return (True, valuesDict)

    ########################################
    # Provide list of MQTT Brokers for device Config (Credit to FlyingDiver)
    ########################################


    def getBrokerDevices(self, filter="", valuesDict=None, typeId="", targetId=0):

        retList = []
        devicePlugin = valuesDict.get("devicePlugin", None)
        for dev in indigo.devices.iter():
            if dev.protocol == indigo.kProtocol.Plugin and \
                dev.pluginId == "com.flyingdiver.indigoplugin.mqtt" and \
                dev.deviceTypeId != 'aggregator' :
                retList.append((dev.id, dev.name))

        retList.sort(key=lambda tup: tup[1])
        return retList
        
        
    def getAgileDevices(self, filter="", valuesDict=None, typeId="", targetId=0):

        retList = []
        devicePlugin = valuesDict.get("devicePlugin", None)
        for dev in indigo.devices.iter():
            if dev.protocol == indigo.kProtocol.Plugin and \
                dev.pluginId == "com.barn.indigoplugin.OctopusEnergy":
                retList.append((dev.id, dev.name))

        retList.sort(key=lambda tup: tup[1])
        return retList
