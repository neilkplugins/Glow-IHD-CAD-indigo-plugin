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
		self.debugLog(str(device.id) + " " + device.name)
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

				self.sleep(1 * pollingFreq)
				for deviceId in self.deviceList:
					# call the update method with the device instance
					self.update(indigo.devices[deviceId])
					self.debugLog("Checking the Message Queue")
		except self.StopThread:
			pass

	########################################
	def update(self, device):
		# device.stateListOrDisplayStateIdChanged()
		mqttPlugin = indigo.server.getPlugin("com.flyingdiver.indigoplugin.mqtt")
		if mqttPlugin.isEnabled() and self.pluginPrefs['MQTT_enable']:
			props = {
				'message_type': "##GlowmarktCAD##"
			}
			while True:
				message_data = mqttPlugin.executeAction("fetchQueuedMessage", deviceId=634573472, props=props,
														waitUntilDone=True)
				if message_data == None:
					return
				payload_json = json.loads(message_data["payload"])
				self.debugLog("Queue Fetch, Meter Data = {}".format(payload_json))
				device_states = []
				try:
					elec_instantaneous = int(payload_json['elecMtr']['0702']['04']['00'], 16)
					elec_month_consumption = float((int(payload_json['elecMtr']['0702']['04']['40'], 16)) / 1000)
					elec_daily_consumption = float((int(payload_json['elecMtr']['0702']['04']['01'], 16)) / 1000)
					elec_week_consumption = float((int(payload_json['elecMtr']['0702']['04']['30'], 16)) / 1000)
					electricity_supplier = payload_json['elecMtr']['0708']['01']['01']
					mpan = payload_json['elecMtr']['0702']['03']['07']
					electricity_meter = float((int(payload_json['elecMtr']['0702']['00']['00'], 16)) / 1000)
					gas_meter = float((int(payload_json['gasMtr']['0702']['00']['00'], 16)) / 1000)
					gas_week_consumption = float((int(payload_json['gasMtr']['0702']['0C']['30'], 16)) / 1000)
					gas_month_consumption = float((int(payload_json['gasMtr']['0702']['0C']['40'], 16)) / 1000)
					gas_daily_consumption = float((int(payload_json['gasMtr']['0702']['0C']['01'], 16)) / 1000)
					device_states.append({'key': 'elec_month_consumption', 'value': elec_month_consumption})
					device_states.append({'key': 'elec_week_consumption', 'value': elec_week_consumption})
					device_states.append({'key': 'elec_daily_consumption', 'value': elec_daily_consumption})
					device_states.append({'key': 'gas_month_consumption', 'value': gas_month_consumption})
					device_states.append({'key': 'gas_week_consumption', 'value': gas_week_consumption})
					device_states.append({'key': 'gas_daily_consumption', 'value': gas_daily_consumption})
					device_states.append({'key': 'gas_meter', 'value': gas_meter})
					device_states.append({'key': 'electricity_meter', 'value': electricity_meter})
					device_states.append({'key': 'electricity_supplier', 'value': electricity_supplier})
					device_states.append({'key': 'mpan', 'value': mpan})

					device_states.append({'key': 'elec_instantaneous', 'value': elec_instantaneous,
										  'uiValue': str(elec_instantaneous) + " W", 'clearErrorState': True})
					# If an agile tariff device is configured from the Octopus Energy Plugin then calculate the actual projected cost per hour
					if device.pluginProps['octopus_enable']:
						agile_device = device.pluginProps['octopusID']
						self.debugLog(agile_device)
						agile_cost = indigo.devices[int(agile_device)].states['Current_Electricity_Rate']
						agile_cost_hour = (agile_cost * elec_instantaneous) / 1000
						device_states.append({'key': 'agile_cost_hour', 'value': agile_cost_hour,
											  'uiValue': str(agile_cost_hour) + " p"})

					device.updateStatesOnServer(device_states)
					device.updateStateImageOnServer(indigo.kStateImageSel.EnergyMeterOn)
				except Exception as e:
					self.debugLog("Failed to complete updates for Glow device " + device.name)
					self.debugLog(e)
		else:
			self.debugLog("MQTT Connector not enabled or MQTT option not configured in Plugin Config - Skipping Message Queue Check")
		return

	########################################
	# UI Validate, Device Config
	########################################
	def validateDeviceConfigUi(self, valuesDict, typeId, device):
		self.debugLog(valuesDict)
		if valuesDict['brokerID'] == "":
			self.errorLog("MQTT Broker Device cannot be empty")
			errorsDict = indigo.Dict()
			errorsDict['brokerID'] = "Broker Device Cannot Be Empty"
			return (False, valuesDict, errorsDict)
		if valuesDict['octopus_enable'] and valuesDict['octopusID'] == "":
			self.errorLog("Octopus Tariff Device cannot be empty")
			errorsDict = indigo.Dict()
			errorsDict['octopusID'] = "Octopus Tariff Device Cannot Be Empty"
			return (False, valuesDict, errorsDict)
		return (True, valuesDict)

	########################################
	# UI Validate, Plugin Preferences
	########################################
	def validatePrefsConfigUi(self, valuesDict):
		if valuesDict['API_enable'] is True:
			if not (valuesDict['bright_account']):
				self.errorLog("Account Email Cannot Be Empty")
				errorsDict = indigo.Dict()
				errorsDict['bright_account'] = "Glow/Bright Account Cannot Be Empty"
				return (False, valuesDict, errorsDict)
			if not (valuesDict['bright_password']):
				self.errorLog("Password Cannot Be Empty")
				errorsDict = indigo.Dict()
				errorsDict['bright_password'] = "Password Cannot Be Empty"
				return (False, valuesDict, errorsDict)
		try:
			url = "https://api.glowmarkt.com/api/v0-1/auth"

			payload = "{\n\"username\": \""+valuesDict['bright_account']+"\",\n\"password\": \""+valuesDict['bright_password']+"\"\n}"
			headers = {
				'Content-Type': 'application/json',
				'applicationId': "b0f1b774-a586-4f72-9edd-27ead8aa7a8d",
				'Content-Type': 'application/json'
			}

			response = requests.request("POST", url, headers=headers, data = payload)
			self.debugLog(response)
			response_json = response.json()
			if response_json['valid'] is not True:
				self.errorLog("Failed to Authenticate with Glow Servers, Check Password and Account Name")
				errorsDict = indigo.Dict()
				errorsDict['bright_password'] = "Failed to Authenticate with Glow Servers, Check Password and Account Name"
				return (False, valuesDict, errorsDict)
			else:
				self.pluginPrefs['token']=response_json['token']
				self.pluginPrefs['token_expires']=response_json['exp']
		except:
			self.debugLog("Unknown error connecting to Glowmarkt")
			errorsDict = indigo.Dict()
			errorsDict['bright_password'] = "Failed to Authenticate with Glow Servers, Check Password and Account Name"
			return (False, valuesDict, errorsDict)

		return(True,valuesDict)



	########################################
	# Provide list of MQTT Brokers for device Config (Credit to FlyingDiver)
	########################################

	def getBrokerDevices(self, filter="", valuesDict=None, typeId="", targetId=0):

		retList = []
		devicePlugin = valuesDict.get("devicePlugin", None)
		for dev in indigo.devices.iter():
			if dev.protocol == indigo.kProtocol.Plugin and \
					dev.pluginId == "com.flyingdiver.indigoplugin.mqtt" and \
					dev.deviceTypeId != 'aggregator':
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
