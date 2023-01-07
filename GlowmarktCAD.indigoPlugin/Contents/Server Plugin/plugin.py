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
# import time
from datetime import datetime, timedelta, date
import pytz

################################################################################
# Globals
################################################################################
state_list = ["From-00-00", "From-00-30", "From-01-00", "From-01-30", "From-02-00", "From-02-30", "From-03-00",
              "From-03-30", "From-04-00", "From-04-30", "From-05-00", "From-05-30", "From-06-00", "From-06-30",
              "From-07-00", "From-07-30", "From-08-00", "From-08-30", "From-09-00", "From-09-30", "From-10-00",
              "From-10-30", "From-11-00", "From-11-30", "From-12-00", "From-12-30", "From-13-00", "From-13-30",
              "From-14-00", "From-14-30", "From-15-00", "From-15-30", "From-16-00", "From-16-30", "From-17-00",
              "From-17-30", "From-18-00", "From-18-30", "From-19-00", "From-19-30", "From-20-00", "From-20-30",
              "From-21-00", "From-21-30", "From-22-00", "From-22-30", "From-23-00", "From-23-30"]


############################
# API Functions
#############################


def refresh_daily_consumption_device(self, device):
    if device.pluginProps['dayList'] == 'today':
        today = str(date.today())
    else:
        today = str(date.today() - timedelta(days=1))
    isdst_now_in = lambda zonename: bool(datetime.now(pytz.timezone(zonename)).dst())
    dst_applies = isdst_now_in("Europe/London")
    if dst_applies:
        offset = "-60"
    else:
        offset = "0"
    if not token_check_valid(self):
        refresh_token(self)
    api_error = False
    resource_type = device.pluginProps['resource_type']
    resource = self.pluginPrefs[resource_type]
    # Refresh resource to request a meter update from the DCC

    url = "https://api.glowmarkt.com/api/v0-1/resource/" + resource + "/catchup"

    payload = {}
    headers = {
        'Content-Type': 'application/json',
        'applicationId': 'b0f1b774-a586-4f72-9edd-27ead8aa7a8d'
    }
    headers['token'] = self.pluginPrefs['token']
    try:
        response = requests.get(url, headers=headers, data=payload)
        response.raise_for_status()
    except requests.exceptions.HTTPError as err:
        indigo.server.log(
            "HTTP Error from Glowmarkt API requesting catchup to collect a new meter read - Will retry next cycle")
        self.debugLog("Error is " + str(err))
        api_error = True
    except Exception as err:
        indigo.server.log(
            "Unknown/Other Error from Glowmarkt API requesting catchup to collect a new meter read - Will retry next cycle")
        self.debugLog("Error is " + str(err))
        api_error = True
    if api_error:
        indigo.server.log("Aborting update cycle")
        return
    self.debugLog("Updated resource " + resource + " of type " + resource_type)
    self.debugLog(response.json())

    # finish updating resource

    url = "https://api.glowmarkt.com/api/v0-1/resource/" + resource + "/readings?from=" + today + "T00:00:00&to=" + today + "T23:59:00&function=sum&period=PT30M&offset=" + offset

    payload = {}
    headers = {
        'Content-Type': 'application/json',
        'applicationId': 'b0f1b774-a586-4f72-9edd-27ead8aa7a8d'
    }
    headers['token'] = self.pluginPrefs['token']
    try:
        response = requests.get(url, headers=headers, data=payload)
        response.raise_for_status()
    except requests.exceptions.HTTPError as err:
        indigo.server.log("HTTP Error from Glowmarkt API refreshing 30 min elec usage - Will retry next cycle")
        self.debugLog("Error is " + str(err))
        api_error = True
    except Exception as err:
        indigo.server.log("Unknown/Other Error from Glowmarkt API refreshing 30 min elec - Will retry next cycle")
        self.debugLog("Error is " + str(err))
        api_error = True
    if api_error:
        indigo.server.log("Aborting update cycle")
        return
    response_json = response.json()

    device_states = []
    state_count = 0
    consumption_sum = 0
    now = datetime.now()
    isdst_now_in = lambda zonename: bool(datetime.now(pytz.timezone(zonename)).dst())
    dst_applies = isdst_now_in("Europe/London")
    if dst_applies:
        now = now + timedelta(hours=1)
    if int(now.strftime("%M")) > 29:
        current_tariff_valid_period = (now.strftime("%Y-%m-%d %H:30:00"))
    else:
        current_tariff_valid_period = (now.strftime("%Y-%m-%d %H:00:00"))
    for rates in response_json['data']:
        device_states.append({'key': state_list[state_count], 'value': rates[1], 'decimalPlaces': 4})
        if str(datetime.fromtimestamp(rates[0])) == current_tariff_valid_period:
            device_states.append({'key': 'consumption_this_period', 'value': rates[1], 'decimalPlaces': 4})

        state_count += 1
        consumption_sum = consumption_sum + rates[1]

    if resource_type == "electricity.consumption.cost":
        if device.pluginProps['Pound_enable']:
            device_states.append({'key': 'consumption_sum', 'value': consumption_sum, 'decimalPlaces': 4,
                                  'uiValue': "£" + str(round((consumption_sum / 100), 2))})
        else:
            device_states.append({'key': 'consumption_sum', 'value': consumption_sum, 'decimalPlaces': 4,
                                  'uiValue': str(round(consumption_sum, 2)) + " p"})
    if resource_type == "electricity.consumption":
        device_states.append({'key': 'consumption_sum', 'value': consumption_sum, 'decimalPlaces': 2,
                              'uiValue': str(round(consumption_sum, 2)) + " kWh"})
    if resource_type == "gas.consumption.cost":
        if device.pluginProps['Pound_enable']:
            device_states.append({'key': 'consumption_sum', 'value': consumption_sum, 'decimalPlaces': 4,
                                  'uiValue': str(round(consumption_sum, 2)) + " p"})
        else:
            device_states.append({'key': 'consumption_sum', 'value': consumption_sum, 'decimalPlaces': 4,
                                  'uiValue': "£" + str(round((consumption_sum / 100), 2))})
    if resource_type == "gas.consumption":
        device_states.append({'key': 'consumption_sum', 'value': consumption_sum, 'decimalPlaces': 2,
                              'uiValue': str(round(consumption_sum, 2)) + " kWh"})

    device_states.append({'key': 'consumption_date', 'value': today})
    device_states.append({'key': 'consumption_type', 'value': resource_type})

    device.updateStatesOnServer(device_states)


def token_check_valid(self):
    time_now = datetime.now() + timedelta(hours=1)
    expiry_time = datetime.fromtimestamp(self.pluginPrefs['token_expires'])
    if expiry_time > time_now:
        self.debugLog("Time remaining on token is " + str(expiry_time - time_now))
        return True
    else:
        self.debugLog("Get new Token - One hour or less remaining valid")
        return False


def refresh_token(self):
    url = "https://api.glowmarkt.com/api/v0-1/auth"

    payload = "{\n\"username\": \"" + self.pluginPrefs['bright_account'] + "\",\n\"password\": \"" + \
              self.pluginPrefs['bright_password'] + "\"\n}"
    headers = {
        'Content-Type': 'application/json',
        'applicationId': "b0f1b774-a586-4f72-9edd-27ead8aa7a8d",
    }
    try:
        response = requests.request("POST", url, headers=headers, data=payload)
        response.raise_for_status()
    except requests.exceptions.HTTPError as err:
        self.debugLog("HTTP Error when refreshing token")
    except Exception as err:
        self.debugLog("Other error when refreshing token")

    response_json = response.json()
    if response.status_code != 200:
        self.errorLog("Failed to Authenticate with Glow Servers, Check Password and Account Name")
        errorsDict = indigo.Dict()
        errorsDict['bright_password'] = "Failed to Authenticate with Glow Servers, Check Password and Account Name"
        return False
    else:
        self.pluginPrefs['token'] = response_json['token']
        self.pluginPrefs['token_expires'] = response_json['exp']
        self.debugLog("Token is " + self.pluginPrefs['token'])
        self.debugLog("Expiry is " + str(self.pluginPrefs['token_expires']))
        return True


def get_resources(self):
    if not token_check_valid(self):
        refresh_token(self)
    url = "https://api.glowmarkt.com/api/v0-1/resource"

    payload = {}
    headers = {
        'Content-Type': 'application/json',
        'applicationId': 'b0f1b774-a586-4f72-9edd-27ead8aa7a8d',
    }
    headers['token'] = self.pluginPrefs['token']
    self.debugLog("Getting Resources")
    try:
        response = requests.request("GET", url, headers=headers, data=payload)
        response.raise_for_status()
    except requests.exceptions.HTTPError as err:
        self.debugLog("HTTP Error when collecting resources")
        return False
    except Exception as err:
        self.debugLog("Other error when collecting resources")
        return False
    response_json = response.json()
    resource_list = []
    if response.status_code == 200:
        for resources in response_json:
            self.debugLog(resources['classifier'])
            resource_list.append(resources['classifier'])
            self.pluginPrefs[resources['classifier']] = resources['resourceId']
            self.debugLog(self.pluginPrefs[resources['classifier']])
        self.pluginPrefs['resource_list'] = resource_list
        return True
    else:
        self.debugLog("Error getting resources")
        return False


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

        device.stateListOrDisplayStateIdChanged()
        if device.deviceTypeId == "daily_Consumption":
            newProps = device.pluginProps
            # only needed to ensure upgraded devices have the new property
            if not "Pound_enable" in newProps:
                newProps["Pound_enable"] = False
            if device.states['consumption_type'] == 'electricity.consumption.cost':
                newProps['address'] = "Electricity Cost"
            elif device.states['consumption_type'] == 'electricity.consumption':
                newProps['address'] = "Electricity Usage"
            elif device.states['consumption_type'] == 'gas.consumption':
                newProps['address'] = "Gas Usage"
            elif device.states['consumption_type'] == 'gas.consumption.cost':
                newProps['address'] = "Gas Cost"
            else:
                newProps['address'] = "-"
            device.replacePluginPropsOnServer(newProps)
        if device.deviceTypeId == "GlowmarktCAD" or device.deviceTypeId == "GlowmarktCAD_local":
            newProps = device.pluginProps
            newProps['address'] = device.states['mpan']
            device.replacePluginPropsOnServer(newProps)
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
        except self.StopThread:
            pass

    ########################################
    def update(self, device):
        # device.stateListOrDisplayStateIdChanged()
        mqttPlugin = indigo.server.getPlugin("com.flyingdiver.indigoplugin.mqtt")
        if mqttPlugin.isEnabled() and self.pluginPrefs[
            'MQTT_enable_local'] and device.deviceTypeId == "GlowmarktCAD_local":
            self.debugLog(device.name)
            self.debugLog(device.lastChanged)
            time_since_update = datetime.now() - device.lastChanged
            if time_since_update.total_seconds() > 60:
                self.debugLog("No update from MQTT for over 60 seconds - maybe CAD is offline")
                device.setErrorStateOnServer('CAD Offline/No Local MQTT Messages')

            props = {
                'message_type': "##GlowmarktCAD_local##"
            }
            while True:
                message_data = mqttPlugin.executeAction("fetchQueuedMessage",
                                                        deviceId=int(device.pluginProps["brokerID"]), props=props,
                                                        waitUntilDone=True)
                if message_data == None:
                    return
                local_payload_json = json.loads(message_data["payload"])
                self.debugLog("Queue Fetch, Local Meter Data = {}".format(local_payload_json))
                device_states = []
                if 'electricitymeter' in local_payload_json:
                    try:
                        self.debugLog("Updating Electricity Meter")
                        elec_instantaneous = local_payload_json['electricitymeter']['power']['value']
                        elec_month_consumption = float(local_payload_json['electricitymeter']['energy']['import']['month'])
                        elec_daily_consumption = float(local_payload_json['electricitymeter']['energy']['import']['day'])
                        electricity_meter_export = float(local_payload_json['electricitymeter']['energy']['export']['cumulative'])

                        elec_week_consumption = float(local_payload_json['electricitymeter']['energy']['import']['week'])
                        electricity_supplier = local_payload_json['electricitymeter']['energy']['import']['supplier']
                        mpan = local_payload_json['electricitymeter']['energy']['import']['mpan']
                        electricity_meter = float(local_payload_json['electricitymeter']['energy']['import']['cumulative'])
                        elec_unit_rate = float(
                            local_payload_json['electricitymeter']['energy']['import']['price']['unitrate'])
                        elec_standing_charge = float(
                            local_payload_json['electricitymeter']['energy']['import']['price']['standingcharge'])

                        device_states.append({'key': 'elec_month_consumption', 'value': elec_month_consumption, 'decimalPlaces': 3,'uiValue': str(elec_month_consumption) + " kWh"})
                        device_states.append({'key': 'elec_week_consumption', 'value': elec_week_consumption, 'decimalPlaces': 3,'uiValue': str(elec_week_consumption) + " kWh"})
                        device_states.append({'key': 'elec_daily_consumption', 'value': elec_daily_consumption, 'decimalPlaces': 3,'uiValue': str(elec_daily_consumption) + " kWh"})

                        device_states.append({'key': 'electricity_meter', 'value': electricity_meter,'uiValue': str(electricity_meter) + " kWh"})
                        device_states.append({'key': 'electricity_meter_export', 'value': electricity_meter_export,'uiValue': str(electricity_meter_export) + " kWh"})

                        device_states.append({'key': 'electricity_supplier', 'value': electricity_supplier})
                        device_states.append({'key': 'mpan', 'value': mpan})
                        device_states.append({'key': 'elec_instantaneous', 'value': elec_instantaneous,'decimalPlaces': 3,'uiValue': str(elec_instantaneous) + " kW", 'clearErrorState': True})
                        device_states.append({'key': 'elec_unit_rate', 'value': elec_unit_rate, 'decimalPlaces': 4,
                                              'uiValue': str(elec_unit_rate) + " £"})
                        device_states.append(
                            {'key': 'elec_standing_charge', 'value': elec_standing_charge, 'decimalPlaces': 4,
                             'uiValue': str(elec_standing_charge) + " £"})

                    except Exception as e:
                            self.errorLog("Failed to complete local updates for Local Glow CAD MQTT electricity " + device.name)
                            self.debugLog(e)
                            self.debugLog(local_payload_json)
                            device.setErrorStateOnServer('Meter Error Local MQTT Electricity')
                if 'gasmeter' in local_payload_json:
                    self.debugLog("Updating Gas Meter")
                    try:
                        mprn = local_payload_json['gasmeter']['energy']['import']['mprn']
                        gas_meter = float(local_payload_json['gasmeter']['energy']['import']['cumulative'])
                        gas_week_consumption = float(local_payload_json['gasmeter']['energy']['import']['week'])
                        gas_month_consumption = float(local_payload_json['gasmeter']['energy']['import']['month'])
                        gas_daily_consumption = float(local_payload_json['gasmeter']['energy']['import']['day'])
                        gas_dayvol = float(local_payload_json['gasmeter']['energy']['import']['dayvol'])
                        gas_weekvol = float(local_payload_json['gasmeter']['energy']['import']['weekvol'])
                        gas_monthvol = float(local_payload_json['gasmeter']['energy']['import']['monthvol'])
                        gas_cumulative_vol = float(local_payload_json['gasmeter']['energy']['import']['cumulativevol'])
                        gas_unit_rate = float(local_payload_json['gasmeter']['energy']['import']['price']['unitrate'])
                        gas_standing_charge = float(local_payload_json['gasmeter']['energy']['import']['price']['standingcharge'])
                        gas_supplier = local_payload_json['gasmeter']['energy']['import']['supplier']
                        device_states.append({'key': 'gas_week_consumption', 'value': gas_week_consumption, 'decimalPlaces': 3,'uiValue': str(gas_week_consumption) + " kWh"})
                        device_states.append({'key': 'gas_month_consumption', 'value': gas_month_consumption, 'decimalPlaces': 3,'uiValue': str(gas_month_consumption) + " kWh"})
                        device_states.append({'key': 'gas_daily_consumption', 'value': gas_daily_consumption, 'decimalPlaces': 3,'uiValue': str(gas_daily_consumption) + " kWh"})
                        device_states.append({'key': 'gas_dayvol', 'value': gas_dayvol, 'decimalPlaces': 3,'uiValue': str(gas_dayvol) + " m3"})
                        device_states.append({'key': 'gas_weekvol', 'value': gas_weekvol, 'decimalPlaces': 3,'uiValue': str(gas_weekvol) + " m3"})
                        device_states.append({'key': 'gas_monthvol', 'value': gas_monthvol, 'decimalPlaces': 3,'uiValue': str(gas_monthvol) + " m3"})
                        device_states.append({'key': 'gas_cumulative_vol', 'value': gas_cumulative_vol, 'decimalPlaces': 3,'uiValue': str(gas_cumulative_vol) + " m3"})
                        device_states.append({'key': 'gas_dayvol', 'value': gas_dayvol, 'decimalPlaces': 3,'uiValue': str(gas_dayvol) + " m3"})
                        device_states.append({'key': 'gas_weekvol', 'value': gas_weekvol, 'decimalPlaces': 3,'uiValue': str(gas_weekvol) + " m3"})
                        device_states.append({'key': 'gas_monthvol', 'value': gas_monthvol, 'decimalPlaces': 3,'uiValue': str(gas_monthvol) + " m3"})
                        device_states.append({'key': 'gas_unit_rate', 'value': gas_unit_rate, 'decimalPlaces': 4,'uiValue': str(gas_unit_rate) + " £"})
                        device_states.append({'key': 'gas_standing_charge', 'value': gas_standing_charge, 'decimalPlaces': 4,'uiValue': str(gas_standing_charge) + " £"})
                        device_states.append({'key': 'gas_meter', 'value': gas_meter, 'decimalPlaces': 3,'uiValue': str(gas_meter) + " kWh"})
                        device_states.append({'key': 'mprn', 'value': mprn})
                        device_states.append({'key': 'gas_supplier', 'value': gas_supplier})

                    except Exception as e:
                        self.errorLog("Failed to complete local updates for Local Glow CAD MQTT Gas " + device.name)
                        self.debugLog(e)
                        self.debugLog(local_payload_json)
                        device.setErrorStateOnServer('Meter Error Local MQTT Gas')
                device.updateStatesOnServer(device_states)
                device.updateStateImageOnServer(indigo.kStateImageSel.EnergyMeterOn)
            return

        if mqttPlugin.isEnabled() and self.pluginPrefs['MQTT_enable'] and device.deviceTypeId == "GlowmarktCAD":
            self.debugLog(device.name)
            self.debugLog(device.lastChanged)
            time_since_update = datetime.now() - device.lastChanged
            if time_since_update.total_seconds() > 60:
                self.debugLog("No update from MQTT for over 60 seconds - maybe CAD is offline")
                device.setErrorStateOnServer('CAD Offline/No MQTT Messages')

            props = {
                'message_type': "##GlowmarktCAD##"
            }
            while True:
                message_data = mqttPlugin.executeAction("fetchQueuedMessage",
                                                        deviceId=int(device.pluginProps["brokerID"]), props=props,
                                                        waitUntilDone=True)
                if message_data == None:
                    return
                payload_json = json.loads(message_data["payload"])
                # self.debugLog("Queue Fetch, Meter Data = {}".format(payload_json))
                device_states = []
                try:
                    elec_instantaneous = int(payload_json['elecMtr']['0702']['04']['00'], 16)
                    elec_month_consumption = float((int(payload_json['elecMtr']['0702']['04']['40'], 16)) / 1000)
                    elec_daily_consumption = float((int(payload_json['elecMtr']['0702']['04']['01'], 16)) / 1000)
                    elec_week_consumption = float((int(payload_json['elecMtr']['0702']['04']['30'], 16)) / 1000)
                    electricity_supplier = payload_json['elecMtr']['0708']['01']['01']
                    mpan = payload_json['elecMtr']['0702']['03']['07']
                    meter_status = payload_json['pan']['status']
                    electricity_meter = float((int(payload_json['elecMtr']['0702']['00']['00'], 16)) / 1000)
                    gas_meter = float((int(payload_json['gasMtr']['0702']['00']['00'], 16)) / 1000)
                    gas_week_consumption = float((int(payload_json['gasMtr']['0702']['0C']['30'], 16)) / 1000)
                    gas_month_consumption = float((int(payload_json['gasMtr']['0702']['0C']['40'], 16)) / 1000)
                    gas_daily_consumption = float((int(payload_json['gasMtr']['0702']['0C']['01'], 16)) / 1000)
                    device_states.append(
                        {'key': 'elec_month_consumption', 'value': elec_month_consumption, 'decimalPlaces': 2,
                         'uiValue': str(elec_month_consumption) + " kWh"})
                    device_states.append(
                        {'key': 'elec_week_consumption', 'value': elec_week_consumption, 'decimalPlaces': 2,
                         'uiValue': str(elec_week_consumption) + " kWh"})
                    device_states.append(
                        {'key': 'elec_daily_consumption', 'value': elec_daily_consumption, 'decimalPlaces': 2,
                         'uiValue': str(elec_daily_consumption) + " kWh"})
                    device_states.append(
                        {'key': 'gas_month_consumption', 'value': gas_month_consumption, 'decimalPlaces': 2,
                         'uiValue': str(gas_month_consumption) + " kWh"})
                    device_states.append(
                        {'key': 'gas_week_consumption', 'value': gas_week_consumption, 'decimalPlaces': 2,
                         'uiValue': str(gas_week_consumption) + " kWh"})
                    device_states.append(
                        {'key': 'gas_daily_consumption', 'value': gas_daily_consumption, 'decimalPlaces': 2,
                         'uiValue': str(gas_daily_consumption) + " kWh"})
                    device_states.append({'key': 'gas_meter', 'value': gas_meter})
                    device_states.append({'key': 'electricity_meter', 'value': electricity_meter})
                    device_states.append({'key': 'electricity_supplier', 'value': electricity_supplier})
                    device_states.append({'key': 'mpan', 'value': mpan})
                    device_states.append({'key': 'meter_status', 'value': meter_status})

                    device_states.append({'key': 'elec_instantaneous', 'value': elec_instantaneous,
                                          'uiValue': str(elec_instantaneous) + " W", 'clearErrorState': True})
                    # If an agile tariff device is configured from the Octopus Energy Plugin then calculate the actual projected cost per hour
                    if device.pluginProps['octopus_enable']:
                        agile_device = device.pluginProps['octopusID']
                        agile_cost = indigo.devices[int(agile_device)].states['Current_Electricity_Rate']
                        agile_cost_hour = (agile_cost * elec_instantaneous) / 1000
                        device_states.append({'key': 'agile_cost_hour', 'value': agile_cost_hour, 'decimalPlaces': 2,
                                              'uiValue': str(round(agile_cost_hour, 2)) + " p"})

                    device.updateStatesOnServer(device_states)
                    device.updateStateImageOnServer(indigo.kStateImageSel.EnergyMeterOn)
                    if meter_status != "joined":
                        device.setErrorStateOnServer('Meter Error Check CAD')

                except Exception as e:
                    self.errorLog("Failed to complete updates for Glow device " + device.name)
                    self.debugLog(e)
                    self.debugLog(payload_json)
                    device.setErrorStateOnServer('Meter Error MQTT')


        else:
            self.debugLog("No update for " + device.name)
        if device.deviceTypeId == "daily_Consumption":
            update_time = device.lastChanged
            now = datetime.now()
            refresh_time = now - update_time

            if refresh_time.total_seconds() > (int(self.pluginPrefs.get('refresh_frequency')) * 60):
                self.debugLog("Updating device")
                refresh_daily_consumption_device(self, device)
        return

    ########################################
    # UI Validate, Device Config
    ########################################
    def validateDeviceConfigUi(self, valuesDict, typeId, device):
        if typeId == "daily_Consumption":
            return (True, valuesDict)
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

            payload = "{\n\"username\": \"" + valuesDict['bright_account'] + "\",\n\"password\": \"" + valuesDict[
                'bright_password'] + "\"\n}"
            headers = {
                'Content-Type': 'application/json',
                'applicationId': "b0f1b774-a586-4f72-9edd-27ead8aa7a8d",
                'Content-Type': 'application/json'
            }
            try:
                response = requests.request("POST", url, headers=headers, data=payload)
                response.raise_for_status()
            except requests.exceptions.HTTPError as err:
                self.debugLog("HTTP Error when authenticating to Glowmarkt")
            except Exception as err:
                self.debugLog("Other error when authenticating to Glowmarkt")
            self.debugLog(response)
            response_json = response.json()
            self.debugLog(response_json)
            self.debugLog(response_json['token'])
            if response.status_code != 200:
                self.errorLog("Failed to Authenticate with Glow Servers, Check Password and Account Name")
                errorsDict = indigo.Dict()
                errorsDict[
                    'bright_password'] = "Failed to Authenticate with Glow Servers, Check Password and Account Name"
                return (False, valuesDict, errorsDict)
            else:
                self.pluginPrefs['token'] = response_json['token']
                self.pluginPrefs['token_expires'] = response_json['exp']
                self.debugLog("Token is " + self.pluginPrefs['token'])
                self.debugLog("Expiry is " + str(self.pluginPrefs['token_expires']))
                get_resources(self)

        except:
            self.debugLog("Unknown error connecting to Glowmarkt")
            errorsDict = indigo.Dict()
            errorsDict['bright_password'] = "Failed to Authenticate with Glow Servers, Check Password and Account Name"
            return (False, valuesDict, errorsDict)

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

    def resourceListGenerator(self, filter="", valuesDict=None, typeId="", targetId=0):
        resource_list = []
        for resource in self.pluginPrefs['resource_list']:
            self.debugLog(resource)
            resource_list.append((resource, resource))
        return resource_list
