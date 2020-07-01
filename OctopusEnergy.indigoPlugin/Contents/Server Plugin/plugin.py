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
import csv
import os
import base64
import dateutil.parser
import dateutil.tz

################################################################################
# Globals
################################################################################
# The base URL for the Octopus Energy API
BASE_URL = "https://api.octopus.energy/v1"
# GSP is Grid Supply point, it is generated from a postcode and used to select the correct tariff for the location
# this is the api call to return the GSP when the postcode is entered
GET_GSP = "/industry/grid-supply-points/?postcode="
# This is the product code for the Octopus Energy Agile Tariff which will return the 30 min rates when combined with a GSP
PRODUCT_CODE="AGILE-18-02-21"
state_list = ["From-00-00","From-00-30","From-01-00","From-01-30","From-02-00","From-02-30","From-03-00","From-03-30","From-04-00","From-04-30","From-05-00","From-05-30","From-06-00","From-06-30","From-07-00","From-07-30","From-08-00","From-08-30","From-09-00","From-09-30","From-10-00","From-10-30","From-11-00","From-11-30","From-12-00","From-12-30","From-13-00","From-13-30","From-14-00","From-14-30","From-15-00","From-15-30","From-16-00","From-16-30","From-17-00","From-17-30","From-18-00","From-18-30","From-19-00","From-19-30","From-20-00","From-20-30","From-21-00","From-21-30","From-22-00","From-22-30","From-23-00","From-23-30"]




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
        if device.deviceTypeId == "OctopusEnergy_consumption":
            newProps = device.pluginProps
            if device.pluginProps['meter_type']=='electricity' and device.pluginProps['calc_costs_yest']:
                newProps['address']="Electricity Cost"
            elif device.pluginProps['meter_type']=='electricity' and not (device.pluginProps['calc_costs_yest']):
                newProps['address'] = "Electricity Usage"
            else:
                newProps['address']= "Gas Usage"
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
            pollingFreq = 30

        try:
            while True:
                # we will check if we have crossed into a new 30 minute period every 30s (so worst case the update could be 30s late)
                # this is currently configurable (it may be lower as a default the check can be quick without hitting the API so that the rate change happens close to minute 00 and minute 30)
                # At present the polling frequency will determine the max number of seconds in a given period the tariff could be out of date
                self.sleep(1 * pollingFreq )
                for deviceId in self.deviceList:
                    # call the update method with the device instance
                    self.update(indigo.devices[deviceId])
        except self.StopThread:
            pass

    ########################################
    def update(self,device):

        ########################################################################
        # Complete the update process for consumption devices
        ########################################################################

        if device.deviceTypeId =="OctopusEnergy_consumption":
            local_day = datetime.datetime.now().date()
            local_yesterday = datetime.datetime.now().date() - datetime.timedelta(days=1)

            ########################################################################
            # Check if the API Calls have been made today, if not then re-run
            # The previous day results are not available at a known time after midnight
            # and it varies wildly.  My need to add a mechanism to set them out of range if no update is available
            ########################################################################


            if str(local_day) != device.states["API_Today"]:
                self.debugLog("Need to update consumption - not same day as last update "+device.name)
            else:
                self.debugLog("No Need to update consumption - same day as last update "+device.name)
                return

            ########################################################################
            # Calculate the date to retrieve the usage data (only the previous day is available)
            # The call either the Gas or Electricity Supply urls
            ########################################################################

            local_yesterday = datetime.datetime.now().date()  - datetime.timedelta(days=1)
            if device.pluginProps['meter_type']=='electricity':
                url = "https://api.octopus.energy/v1/electricity-meter-points/"+device.pluginProps['meter_point']+"/meters/"+device.pluginProps['meter_serial']+"/consumption/?period_from="+str(local_yesterday)+"T00:00:00&period_to="+str(local_yesterday)+"T23:59:00"
                self.debugLog("Eleccy "+ url)
            else:
                url = "https://api.octopus.energy/v1/gas-meter-points/"+device.pluginProps['meter_point']+"/meters/"+device.pluginProps['meter_serial']+"/consumption/?period_from="+str(local_yesterday)+"T00:00:00&period_to="+str(local_yesterday)+"T23:59:00"
                self.debugLog("Gas "+url)
            encoded_api_key = base64.b64encode(device.pluginProps['API_key']+":")
            payload = {}
            headers = {
                'Authorization': 'Basic '+encoded_api_key
            }
            api_error = False
            #response = requests.request("GET", url, headers=headers, data=payload)
            try:
                response = requests.get(url, headers=headers, data=payload)
                response.raise_for_status()
            except requests.exceptions.HTTPError as err:
                self.errorLog("Octopus API refresh failure (Consumption), Http Error " + str(err))
                api_error = True
            except Exception as err:
                self.errorLog("Octopus API refresh failure (consumption), Other error " + str(err))
                api_error = True
            response_json=response.json()

            ########################################################################
            # If we have had a valid response, we need to check that the days values have been returned
            # It reports in 30 min periods, so we should have 48  results if the data is available
            ########################################################################

            if not api_error and response_json['count']!=48:
                api_error= True
                self.errorLog('API Error - Meter Data not available, results limited to '+str(response_json['count']))

            ########################################################################
            # Apply the results to the states, and if selected in the props write out a CSV file
            ########################################################################

            device_states = []
            results_csv=[]

            if not api_error:
                half_hourly_consumption = response_json['results']
                sum_consump = 0
                consump_state = 0

                if device.pluginProps['calc_costs_yest'] and device.pluginProps['meter_type'] == 'electricity':
                    tariff_device=indigo.devices[int(device.pluginProps["tariff_device"])]
                    yesterday_rates = json.loads(tariff_device.pluginProps['yesterday_rates'])


                for consumption in reversed(half_hourly_consumption):
                    if device.pluginProps['calc_costs_yest'] and device.pluginProps['meter_type']=='electricity':

                        half_hour_cost = consumption["consumption"] * yesterday_rates[(47-consump_state)]['value_inc_vat']
                        device_states.append({'key': state_list[consump_state], 'value': half_hour_cost, 'decimalPlaces' : 4  })
                        sum_consump = sum_consump + half_hour_cost
                        self.debugLog(consumption['interval_start']+" "+str(half_hour_cost))
                        results_csv.append([consumption['interval_start'], half_hour_cost])
                    else:
                        device_states.append({'key': state_list[consump_state], 'value': consumption["consumption"],'decimalPlaces' : 4 })
                        sum_consump= sum_consump + consumption["consumption"]
                        results_csv.append([consumption['interval_start'], consumption['consumption']])

                    consump_state += 1

                if device.pluginProps['calc_costs_yest'] and device.pluginProps['meter_type'] == 'electricity':
                    device_states.append({'key': 'total_daily_consumption', 'value': sum_consump,'decimalPlaces' : 2, 'uiValue' : str(round(sum_consump,2))+" p"})
                elif device.pluginProps['meter_type'] == 'electricity':
                    device_states.append({'key': 'total_daily_consumption', 'value': sum_consump,'decimalPlaces' : 2 ,'uiValue' : str(round(sum_consump,2))+" kWh"})
                elif device.pluginProps['meter_type'] == 'gas':
                    device_states.append({'key': 'total_daily_consumption', 'value': sum_consump,'decimalPlaces' : 2 ,'uiValue' : str(round(sum_consump,2))+" M3"})


                if device.pluginProps['Log_Rates']:
                    if self.pluginPrefs['LogFilePath'] == "":
                        self.errorLog("No directory path specified in the Plugin Configuration to save the CSV File")
                        DefaultCSVPath = "{}/Preferences/Plugins/{}".format(indigo.server.getInstallFolderPath(), self.pluginId)
                        self.errorLog("Defaulting to "+DefaultCSVPath)

                        self.pluginPrefs['LogFilePath']= DefaultCSVPath
                        if not os.path.isdir(self.pluginPrefs['LogFilePath']):
                            os.mkdir(self.pluginPrefs['LogFilePath'])
                    filepath = self.pluginPrefs['LogFilePath']+"/"+str(local_day)+"-"+device.name+"-History.csv"
                    with open(filepath, 'w') as file:
                        writer = csv.writer(file)
                        writer.writerow(["Period", "Tariff"])
                        for results in results_csv:
                            writer.writerow(results)




                device_states.append({'key': 'API_Today', 'value': str(local_day)})
            if api_error:
                device_states.append({'key': 'API_Today', 'value': "Meter Data Not Available"})
            device.updateStatesOnServer(device_states)
            if api_error:
                device.setErrorStateOnServer('Meter Data Not Available')
            ########################################################################
            # Consumption device updates complete
            ########################################################################

            return

        ########################################################################
        # Now if it is not a consumption device, it is a rate device so update that
        ########################################################################


        device.stateListOrDisplayStateIdChanged()


        # The Tariff code is built from the Grid Supply Point (gsp) and the product code.  For the purposes of the plugin this is hardcoded to the agile offering
        # No need to vary this for the current version, but I will review in the future as it may be other tariffs than Agile may be of interest (even if they do not change every 30 mins)
        TARIFF_CODE="E-1R-"+PRODUCT_CODE+"-"+device.pluginProps['device_gsp']
        GET_STANDING_CHARGES = BASE_URL + "/products/" + PRODUCT_CODE + "/electricity-tariffs/" + TARIFF_CODE + "/standing-charges/"
        # Due to the way they API publishes the daily rates, I will force a refresh at 17:00 utc, as not all of the rates would have been available at midnight the previous day)

        ########################################################################
        # Reset Flags used to test the need to make half hour, daily and evening updates
        ########################################################################


        # Calculate 'now' using UTC as this will collect the correct tariff regardless of Daylight Savings, as the periods are reported in UTC (Z).  This will be the same baseline as the consumption data
        now = datetime.datetime.utcnow()
        # But calculate the applicable day using local time and the API will automatically adjust if it is BST and will ensure max, min and average align to the local time
        local_day = datetime.datetime.now().date()
        # Also calculate yesterday as this will be used to get yesterdays rates
        local_yesterday = datetime.datetime.now().date()  - datetime.timedelta(days=1)
        # Flag used to see if the rate needs to be updated
        update_rate = False
        # Flag used to see if the daily rate needs to be updates
        update_daily_rate = False
        # Flag used to determine if this is the 17:00Z update cycle
        update_afternoon_refresh = False
        #Flag used to mark API errors for the todays rate call
        api_error = False
        #Flag used to mark API error getting yesterdays rates
        api_error_yest = False


        ########################################################################
        # Check if the device state for the current tariff matches the "current period", if so no updates required
        ########################################################################


        # Rates are published from minute 00 to 30 and 30 to 00, work out which period we are in (0-29 mins first half, 30-59 second half)
        # We will use this to match to the results for the current period for the response
        if int(now.strftime("%M")) > 29:
            current_tariff_valid_period = (now.strftime("%Y-%m-%dT%H:30:00Z"))
        else:
            current_tariff_valid_period = (now.strftime("%Y-%m-%dT%H:00:00Z"))
        # Compare the current_tariff_valid_period with the one stored on the device to see if we need to update (we have crossed a half hour boundary)
        # If they match we can skip all of the updates and return, otherwise we update the period (and potentially the daily figures)
        if current_tariff_valid_period == device.states["Current_From_Period"]:
            self.debugLog("No need to update Current "+current_tariff_valid_period+" Stored "+device.states["Current_From_Period"]+" for "+device.name)
        else:
            self.debugLog("Need to Update Current "+current_tariff_valid_period+" Stored "+device.states["Current_From_Period"]+" for "+device.name)
            update_rate = True

        if update_rate:
            ########################################################################
            # If "update_rate is true" this will be the first run after either minute 00 or minute 30
            # We will then check if the API data needs to be refreshed, or other daily actions are Required
            # Such as the day changing when daily max, min and average need to be calculated
            # Or at 17:00 UTC when all of the rates for the current 24hour period will be available
            # Will now check if the daily updates are needed by comparing to the last day stored in the device state "API_Today"
            ########################################################################

            if str(local_day) != device.states["API_Today"]:
                update_daily_rate = True
            else:
                self.debugLog("No Need to update daily - same day as last update "+device.name)
                update_daily_rate = False

            ########################################################################
            # Now check if it is 17:00Z and if the afternoon update has been completed
            # If it is 17:00Z and the update has not been done then set to True
            ########################################################################

            if current_tariff_valid_period == str(local_day)+"T17:00:00Z" and device.states['API_Afternoon_Refresh'] == False:
                indigo.server.log("Applying the Afternoon Daily Rate Update from the Octopus API for Device "+ device.name)
                update_afternoon_refresh = True
            else:
                self.debugLog("No Need for the Afternoon refresh - it is not 17:00Z or it has been done  for "+device.name)
                update_afternoon_refresh = False

            ########################################################################
            # Now start doing the various updates based on the conditions
            ########################################################################

            # Create update list that will be used to minimise Indigo Server calls, will all be applied at the end of update in a single update states on server call
            device_states = []

            ########################################################################
            # The rates should only need to be updated against the API at 00:00 "OR" at 17:00Z
            ########################################################################

            if (update_daily_rate or update_afternoon_refresh):

                ########################################################################
                # Now Make the API calls
                ########################################################################


                indigo.server.log("Refreshing Daily Rate Information from the Octopus API for Device "+ device.name)

                PERIOD="period_from="+str(local_day)+"T00:00&period_to="+str(local_day)+"T23:59"
                GET_LOCAL_TARIFFS = BASE_URL+"/products/"+PRODUCT_CODE+"/electricity-tariffs/"+TARIFF_CODE+"/standard-unit-rates/?"+PERIOD
                try:
                    response = requests.get(GET_LOCAL_TARIFFS, timeout=float(self.pluginPrefs['requeststimeout']))
                    response.raise_for_status()
                except requests.exceptions.HTTPError as err:
                    self.errorLog("Octopus API refresh failure, Http Error "+ str(err))
                    device_states.append({ 'key': 'API_Today', 'value' : "API Refresh Failed"})
                    device.setErrorStateOnServer("No Update")
                    api_error = True
                except Exception as err:
                    self.errorLog("Octopus API refresh failure, Other error "+str(err))
                    device_states.append({ 'key': 'API_Today', 'value' : "API Refresh Failed"})
                    device.setErrorStateOnServer("No Update")
                    api_error = True
                # If API request succeeded, then save the response, and update the "API_Today" device state
                try:
                    if response.status_code ==200:
                        results_json = response.json()
                        #self.debugLog(results_json)
                        half_hourly_rates = results_json['results']
                        # Update the device state to show the API update has run sucessfully
                        device_states.append({ 'key': 'API_Today', 'value' : str(local_day)})
                        self.debugLog("Got the rates OK")
                        if current_tariff_valid_period == str(local_day)+"T17:00:00Z":
                            self.debugLog("Setting Afternoon refresh done to device state")
                            device_states.append({ 'key': 'API_Afternoon_Refresh', 'value' : True })
                # Catch all other possible failures
                except:
                    self.errorLog("Octopus API Refresh, Error in getting current tariffs")
                    device_states.append({ 'key': 'API_Today', 'value' : "API Refresh Failed"})
                    device.setErrorStateOnServer("No Update")

                ########################################################################
                # Iterate through the rate retured and calculate the
                # Max, min and average
                ########################################################################

                if not api_error:
                    sum_rates = 0
                    max_rate = 0
                    rate_state = 0

                    stored_rates=indigo.Dict()
                    # This is the current rate cap for Agile Octopus, min value should always be lower than this, from the plugin config
                    min_rate = str(self.pluginPrefs['Capped_Rate'])

                    # Used to build a matrix to determine the cheapest time to consume energy today
                    costs = []
                    times = []

                    for rates in reversed(half_hourly_rates):
                        sum_rates = sum_rates + rates["value_inc_vat"]
                        device_states.append({'key': state_list[rate_state], 'value': rates["value_inc_vat"], 'decimalPlaces' : 4 })
                        period_str = rates['valid_from']
                        time_ts = dateutil.parser.parse(timestr=period_str).astimezone(dateutil.tz.tzlocal())
                        times.append(time_ts)
                        costs.append(rates['value_inc_vat'])
                        rate_state += 1
                        if rates["value_inc_vat"] >= max_rate:
                            max_rate = rates["value_inc_vat"]
                        if rates["value_inc_vat"] <= min_rate:
                            min_rate = rates["value_inc_vat"]
                    average_rate = sum_rates / results_json['count']
                    # If we only have 46 rates for the day then set the the 2300 and 2230 rates to a known false value of 999
                    if len(half_hourly_rates)==46:
                        device_states.append({'key': 'From-23-00', 'value': 999})
                        device_states.append({'key': 'From-23-30', 'value': 999})
                 #
                # Determine Lowest Cost Usage Periods in current data
                    # Build a matrix of half-hour periods (vertical) and 1-8 averaging periods
                    # (horizontal) (so second column is hour average costs)
                    cost_matrix = []

                    for x in range(len(costs)):
                        cost_row = [costs[x]]
                        for y in range(1, 8):
                            if len(costs) - x < y + 1:
                                # table ends before averaging period
                                cost_row.append(None)
                            else:
                                cost_total = 0
                                for z in range(y + 1):
                                    cost_total = cost_total + costs[x + z]
                                cost_row.append(round(cost_total / (z + 1), 4))
                        cost_matrix.append(cost_row)

                    output = []
                    for x in range(8):
                        # Build column, find minimum
                        cost_col = []
                        for y in range(len(costs)):
                            if cost_matrix[y][x] is not None:
                                cost_col.append(cost_matrix[y][x])



                        mindex = cost_col.index(min(cost_col))

                        output.append({"time": "%s" % times[mindex].strftime("%m/%d/%Y, %H:%M:%S"),
                                       "cost": "%.4f" % cost_col[mindex]})

                        # output a list for cheapest 30m, 1h, 2h. 3h and 4h
                    self.debugLog(json.dumps([output[0], output[1], output[3], output[5], output[7]]))



                    # Update the states to be applied to the server for the todays rates if the API call succeeded

                    device_states.append({ 'key': 'Daily_Average_Rate', 'value' : average_rate , 'decimalPlaces' : 4 })
                    device_states.append({ 'key': 'Daily_Max_Rate', 'value' : max_rate , 'decimalPlaces' : 4 })
                    device_states.append({ 'key': 'Daily_Min_Rate', 'value' : min_rate , 'decimalPlaces' : 4 })
                    device_states.append({ 'key': 'API_Today', 'value' : str(local_day)})
                    device_states.append({'key': 'lowest_30m_cost', 'value': output[0]['cost'], 'decimalPlaces': 4})
                    device_states.append({'key': 'lowest_30m_time', 'value': str(output[0]['time'])})
                    device_states.append({'key': 'lowest_1h_cost', 'value': output[1]['cost'], 'decimalPlaces': 4})
                    device_states.append({'key': 'lowest_1h_time', 'value': str(output[1]['time'])})
                    device_states.append({'key': 'lowest_2h_cost', 'value': output[3]['cost'], 'decimalPlaces': 4})
                    device_states.append({'key': 'lowest_2h_time', 'value': str(output[3]['time'])})
                    device_states.append({'key': 'lowest_3h_cost', 'value': output[5]['cost'], 'decimalPlaces': 4})
                    device_states.append({'key': 'lowest_3h_time', 'value': str(output[5]['time'])})
                    device_states.append({'key': 'lowest_4h_cost', 'value': output[7]['cost'], 'decimalPlaces': 4})
                    device_states.append({'key': 'lowest_4h_time', 'value': str(output[7]['time'])})

                ########################################################################
                # Store the JSON response to the device so that the API doesn't need to be called every 30 mins
                ########################################################################
                updatedProps=device.pluginProps
                if not api_error:
                    updatedProps['today_rates'] = json.dumps(half_hourly_rates)

                ########################################################################
                # Get Yesterdays Rates from the API (rather than copying yesterdays)
                # This is more robust and will provide yesterdays data on the first device update
                # Also it does not matter if this is run at a different time as it is now
                # Does not over-write but recalculates correctly
                ########################################################################


                YESTERDAY_PERIOD="period_from="+str(local_yesterday)+"T00:00&period_to="+str(local_yesterday)+"T23:59"
                GET_YESTERDAY_TARIFFS = BASE_URL+"/products/"+PRODUCT_CODE+"/electricity-tariffs/"+TARIFF_CODE+"/standard-unit-rates/?"+YESTERDAY_PERIOD

                try:
                    yesterday_response = requests.get(GET_YESTERDAY_TARIFFS, timeout=float(self.pluginPrefs['requeststimeout']))
                    yesterday_response.raise_for_status()
                except requests.exceptions.HTTPError as err:
                    self.errorLog("Octopus API refresh failure (Yesterday refresh), Http Error "+ str(err))
                    api_error_yest = True
                except Exception as err:
                    self.errorLog("Octopus API refresh failure (Yesterday refresh), Other error "+str(err))
                    api_error_yest = True
                # If API request succeeded, then save the response, and update the "API_Today" device state
                try:
                    if yesterday_response.status_code ==200:
                        yesterday_results_json = yesterday_response.json()
                        #self.debugLog(results_json)
                        yesterday_half_hourly_rates = yesterday_results_json['results']
                        # If this is the 17:00Z run then update the device state to show it has been completed
                        if update_afternoon_refresh:
                            self.debugLog("Setting Afternoon refresh done to device state")
                            device_states.append({ 'key': 'API_Afternoon_Refresh', 'value' : True })
                # Catch all other possible failures
                except:
                    self.errorLog("Octopus API Refresh, Error in getting yesterday tariffs")


                ########################################################################
                # Iterate through the rate retured and calculate the
                # Max, min and average for yesterday
                ########################################################################

                if not api_error_yest:
                    sum_rates_yest = 0
                    max_rate_yest = 0
                    stored_rates_yest = indigo.Dict()
                    # This is the current rate cap for Agile Octopus, min value should always be lower than this, from the plugin config
                    min_rate_yest = str(self.pluginPrefs['Capped_Rate'])
                    for rates in yesterday_half_hourly_rates:
                        sum_rates_yest = sum_rates_yest + rates["value_inc_vat"]
                        if rates["value_inc_vat"] >= max_rate_yest:
                            max_rate_yest = rates["value_inc_vat"]
                        if rates["value_inc_vat"] <= min_rate_yest:
                            min_rate_yest = rates["value_inc_vat"]
                    average_rate_yest = sum_rates_yest / yesterday_results_json['count']

                ########################################################################
                # Store the JSON response to the device so that the API doesn't need to be called every 30 mins
                ########################################################################

                if not api_error_yest:
                    updatedProps['yesterday_rates'] = json.dumps(yesterday_half_hourly_rates)

                if not api_error and not api_error_yest:
                    device.replacePluginPropsOnServer(updatedProps)
                    device_states.append({ 'key': 'Yesterday_Standing_Charge', 'value' : device.states['Daily_Standing_Charge'] , 'uiValue' :str(device.states['Daily_Standing_Charge'])+"p" })
                    device_states.append({ 'key': 'Yesterday_Average_Rate', 'value' : average_rate_yest , 'decimalPlaces' : 4 })
                    device_states.append({ 'key': 'Yesterday_Max_Rate', 'value' : max_rate_yest , 'decimalPlaces' : 4 })
                    device_states.append({ 'key': 'Yesterday_Min_Rate', 'value' : min_rate_yest , 'decimalPlaces' : 4 })
                if not update_afternoon_refresh:
                    device_states.append({ 'key': 'API_Afternoon_Refresh', 'value' : False })
                    self.debugLog("Resetting Afternoon Refresh to False")
                self.debugLog("Updating yesterday rates")

                ########################################################################
                # Update the standing charge
                # Unlikely to change too often but the overhead is small so twice daily updates not excessive
                ########################################################################

                try:
                    response = requests.get(GET_STANDING_CHARGES, timeout=float(self.pluginPrefs['requeststimeout']))
                    response.raise_for_status()
                except requests.exceptions.HTTPError as err:
                    self.errorLog("Octopus API - Standing Charge Http Error "+ str(err))
                except Exception as err:
                    self.errorLog("Octopus API - Standing Charge Other error"+str(err))
                if response.status_code ==200:
                    standing_charge_json = response.json()
                    standing_charge_inc_vat = float(standing_charge_json["results"][0]["value_inc_vat"])
                    device_states.append({ 'key': 'Daily_Standing_Charge', 'value' : standing_charge_inc_vat , 'uiValue' :str(standing_charge_inc_vat)+"p" })
                    self.debugLog("Standing Charge "+str(standing_charge_inc_vat))
                else:
                    self.errorLog("Octopus API - Standing Charge Error getting Standing Charges")

                # Append the updates to the updated states dict and change the state image

                #Moved into the if response
                #device_states.append({ 'key': 'Daily_Standing_Charge', 'value' : standing_charge_inc_vat , 'uiValue' :str(standing_charge_inc_vat)+"p" })
                device.updateStateImageOnServer(indigo.kStateImageSel.EnergyMeterOn)

                # If this is the first update the yesterday standing charge will be set to zero, this applies todays rate to yesterday
                # as this is better than it appearing as zero.  risk that if the rate changed the day before you created the device the update will be 1 day late
                # but this unlikely risk is better than it appearing to be zero

                if device.states["Yesterday_Standing_Charge"]== 0:
                    device_states.append({ 'key': 'Yesterday_Standing_Charge', 'value' : standing_charge_inc_vat , 'uiValue' :str(standing_charge_inc_vat)+"p" })

                ########################################################################
                # This ends the indented section that only runs
                # if it is 00:00 or 17:00Z
                ########################################################################

                ########################################################################
                # Write the CSV file out at 18:00 UTC and if the checkbox is ticked in the device config
                # File name in the form 2020-04-28-devicename-Rates.csv in the folder from the plugin config
                # Now defaults to the plugin prefs folder if an empty path is specified
                ########################################################################

                if device.pluginProps['Log_Rates'] and current_tariff_valid_period == str(local_day)+"T18:00:00Z":
                    if self.pluginPrefs['LogFilePath'] == "":
                        self.errorLog("No directory path specified in the Plugin Configuration to save the CSV File")
                        DefaultCSVPath = "{}/Preferences/Plugins/{}".format(indigo.server.getInstallFolderPath(), self.pluginId)
                        self.errorLog("Defaulting to "+DefaultCSVPath)

                        self.pluginPrefs['LogFilePath']= DefaultCSVPath
                        if not os.path.isdir(self.pluginPrefs['LogFilePath']):
                            os.mkdir(self.pluginPrefs['LogFilePath'])
                    filepath = self.pluginPrefs['LogFilePath']+"/"+str(local_day)+"-"+device.name+"-Rates.csv"
                    with open(filepath, 'w') as file:
                        writer = csv.writer(file)
                        writer.writerow(["Period", "Tariff"])
                        for rates in json.loads(device.pluginProps['today_rates']):
                            writer.writerow([rates['valid_from'],rates['value_inc_vat']])

            ########################################################################
            # Now parse the stored json in the device to check for the applicable rate
            # in this 30 minute period if an update is needed
            ########################################################################

            for rates in json.loads(device.pluginProps['today_rates']):
                # Find the record with the matching current tariff period in the saved JSON
                if rates['valid_from'] == current_tariff_valid_period:
                    indigo.server.log("Current Rate inc vat is "+str(rates["value_inc_vat"]))
                    current_tariff = float(rates["value_inc_vat"])

            ########################################################################
            # Append the half hourly updates to the update dictionary but not if an API refresh failed (which will force future attempts to refresh)
            ########################################################################

            device_states.append({ 'key': 'Current_Electricity_Rate', 'value' : current_tariff , 'decimalPlaces'  :4, 'uiValue' :str(current_tariff)+"p", 'clearErrorState':True })
            device_states.append({ 'key': 'Current_From_Period', 'value' : current_tariff_valid_period })

            ########################################################################
            # Apply State Updates to Indigo Server
            ########################################################################
            device.updateStatesOnServer(device_states)

            # Update the plugin props with the stored json for today and yeserdays rates


        else:
            self.debugLog("No Updates required for device through update_rate  for "+device.name)
        ########################################################################
        # Nothing else needs to be done for this update, return to runConcurrentThread
        ########################################################################

        self.debugLog("Update cycle complete for "+ device.name )
        return()

    ########################################
    # UI Validate, Plugin Preferences
    ########################################
    def validatePrefsConfigUi(self, valuesDict):
        try:
            timeoutint=float(valuesDict['requeststimeout'])
        except:
            self.errorLog("Invalid entry for  API Timeout - must be a number")
            errorsDict = indigo.Dict()
            errorsDict['requeststimeout'] = "Invalid entry for API Timeout - must be a number"
            return (False, valuesDict, errorsDict)
        try:
            pollingfreq = int(valuesDict['pollingFrequency'])
        except:
            self.errorLog("Invalid entry for Polling Frequency - must be a whole number greater than 0")
            errorsDict = indigo.Dict()
            errorsDict['pollingFrequency'] = "Invalid entry for Polling Frequency - must be a whole number greater than 0"
            return (False, valuesDict, errorsDict)
        if int(valuesDict['pollingFrequency']) == 0:
            self.errorLog("Invalid entry for Polling Frequency - must be greater than 0")
            errorsDict = indigo.Dict()
            errorsDict['pollingFrequency'] = "Invalid entry for Polling Frequency - must be a whole number greater than 0"
            return (False, valuesDict, errorsDict)
        if int(valuesDict['requeststimeout']) == 0:
            self.errorLog("Invalid entry for Requests Timeout - must be greater than 0")
            errorsDict = indigo.Dict()
            errorsDict['requeststimeout'] = "Invalid entry for Requests Timeout - must be greater than 0"
            return (False, valuesDict, errorsDict)
        try:
            timeoutint=float(valuesDict['Capped_Rate'])
        except:
            self.errorLog("Invalid entry for  Capped Rate - must be a number")
            errorsDict = indigo.Dict()
            errorsDict['Capped_Rate'] = "Invalid entry for Capped Rate - must be a number"
            return (False, valuesDict, errorsDict)
        if valuesDict['LogFilePath'] !="":
            if not os.path.isdir(valuesDict['LogFilePath']):
                errorsDict = indigo.Dict()
                errorsDict['LogFilePath'] = "Directory specified does not exist"
                self.errorLog(valuesDict['LogFilePath']+ " directory does not exist")
                return (False, valuesDict, errorsDict)
            if not os.access(valuesDict['LogFilePath'], os.W_OK):
                errorsDict = indigo.Dict()
                errorsDict['LogFilePath'] = "Directory specified is not writable"
                self.errorLog(valuesDict['LogFilePath']+ " directory is not writable")
                return (False, valuesDict, errorsDict)
        return (True, valuesDict)

    ########################################
    # UI Validate, Device Config
    ########################################
    def validateDeviceConfigUi(self, valuesDict, typeId, device):
        if typeId == "OctopusEnergy_consumption":
            return (True, valuesDict)
        if typeId== "OctopusEnergy":
            if not(valuesDict['Device_Postcode']):
                self.errorLog("Postcode Cannot Be Empty")
                errorsDict = indigo.Dict()
                errorsDict['Device_Postcode'] = "Postcode Cannot Be Empty"
                return (False, valuesDict, errorsDict)
            try:
                response = requests.get(BASE_URL+GET_GSP+valuesDict['Device_Postcode'], timeout=float(self.pluginPrefs['requeststimeout']))
                response.raise_for_status()
            except requests.exceptions.HTTPError as err:

                self.debugLog("Http Error "+ str(err))
                errorsDict = indigo.Dict()
                errorsDict['Device_Postcode'] = "API Error validating with Octopus"
                return (False, valuesDict, errorsDict)
            except Exception as err:
                self.debugLog("Other error"+str(err))
                errorsDict = indigo.Dict()
                errorsDict['Device_Postcode'] = "API Error validating with Octopus"
                return (False, valuesDict, errorsDict)
            else:
                self.debugLog("API successfully Connected to Octopus Servers")
            if response.status_code ==200:
                gsp_json =  response.json()
                if gsp_json['count']==0:
                    self.debugLog("GSP Not returned")
                    errorsDict = indigo.Dict()
                    errorsDict['Device_Postcode'] = "GSP Not returned - Check Postcode"
                    return (False, valuesDict, errorsDict)
                else:
                    gsp= gsp_json['results'][0]['group_id'][1]
                    self.debugLog("GSP is "+gsp)
                    valuesDict['device_gsp'] = gsp
            else:
                gsp = "Unknown API Error"
                errorsDict = indigo.Dict()
                errorsDict['Device_Postcode'] = "Unknown Octopus API Error"
                return (False, valuesDict, errorsDict)
            valuesDict['address'] = valuesDict['Device_Postcode']

        return (True, valuesDict)



    ########################################
    # Menu Methods
    ########################################
    def toggleDebugging(self):
        if self.debug:
            indigo.server.log("Turning off debug logging")
            self.pluginPrefs["showDebugInfo"] = False
        else:
            indigo.server.log("Turning on debug logging")
            self.pluginPrefs["showDebugInfo"] = True
        self.debug = not self.debug

    def logDumpRawData(self):
        for deviceId in self.deviceList:
            self.debugLog(indigo.devices[deviceId].pluginProps)

    def logDumpRates(self):
        for deviceId in self.deviceList:
            if indigo.devices[deviceId].deviceTypeId !="OctopusEnergy_consumption":
                indigo.server.log(indigo.devices[deviceId].name+" Today")
                indigo.server.log("Period , Tariff")
                for rates in json.loads(indigo.devices[deviceId].pluginProps['today_rates']):
                    indigo.server.log(rates['valid_from']+" , "+str(rates['value_inc_vat']))
                indigo.server.log("Yesterday")
                indigo.server.log("Period , Tariff")
                for rates in json.loads(indigo.devices[deviceId].pluginProps['yesterday_rates']):
                    indigo.server.log(rates['valid_from']+" , "+str(rates['value_inc_vat']))

    # Force API refresh on all devices at next cycle

    def forceAPIrefresh(self):
            for deviceId in self.deviceList:
                indigo.server.log(indigo.devices[deviceId].name+" Set for refresh on next cycle")
                indigo.devices[deviceId].updateStateOnServer(key='API_Today', value='API Refresh Requested')
                if indigo.devices[deviceId].deviceTypeId != "OctopusEnergy_consumption":
                    indigo.devices[deviceId].updateStateOnServer(key='Current_From_Period', value='API Refresh Requested')

    ########################################
    # Action Methods
    ########################################

    # Write Todays rates to file
    def todayToFile(self,pluginAction, device):
        local_day = datetime.datetime.now().date()
        if self.pluginPrefs['LogFilePath'] == "":
            self.errorLog("No directory path specified in the Plugin Configuration to save the CSV File")
            DefaultCSVPath = "{}/Preferences/Plugins/{}".format(indigo.server.getInstallFolderPath(), self.pluginId)
            self.errorLog("Defaulting to "+DefaultCSVPath)
            self.pluginPrefs['LogFilePath']= DefaultCSVPath
        if not os.path.isdir(self.pluginPrefs['LogFilePath']):
            os.mkdir(self.pluginPrefs['LogFilePath'])
        filepath = self.pluginPrefs['LogFilePath']+"/"+str(local_day)+"-"+device.name+"-Action-Today-Rates.csv"
        if device.pluginProps['CSV_engine']:
            filepath=device.pluginProps['CSV_FilePath']+"agile_today.csv"
        with open(filepath, 'w') as file:
            writer = csv.writer(file)
            writer.writerow(["Period", "Tariff"])

            for rates in reversed(json.loads(device.pluginProps['today_rates'])):
                self.debugLog(rates['valid_from'])
                newdate = dateutil.parser.parse(rates['valid_from'])
                writer.writerow([newdate.strftime("%Y-%m-%d %H:%M:%S.%f"),rates['value_inc_vat']])


        indigo.server.log("Created CSV file "+filepath+" for device "+ device.name)


        return()

    # Write Yesterdays rates to file
    def yesterdayToFile(self,pluginAction, device):
        local_day = datetime.datetime.now().date()
        if self.pluginPrefs['LogFilePath'] == "":
            self.errorLog("No directory path specified in the Plugin Configuration to save the CSV File")
            DefaultCSVPath = "{}/Preferences/Plugins/{}".format(indigo.server.getInstallFolderPath(), self.pluginId)
            self.errorLog("Defaulting to "+DefaultCSVPath)
            self.pluginPrefs['LogFilePath']= DefaultCSVPath
        if not os.path.isdir(self.pluginPrefs['LogFilePath']):
            os.mkdir(self.pluginPrefs['LogFilePath'])
        filepath = self.pluginPrefs['LogFilePath']+"/"+str(local_day)+"-"+device.name+"-Action-Yesterday-Rates.csv"
        with open(filepath, 'w') as file:
            writer = csv.writer(file)
            writer.writerow(["Period", "Tariff"])
            for rates in reversed(json.loads(device.pluginProps['yesterday_rates'])):
                writer.writerow([rates['valid_from'],rates['value_inc_vat']])
        indigo.server.log("Created CSV file "+filepath+" for device "+ device.name)
        return()



    #Was getting strange behaviour as when I wrote the json to the plugin props the device would restart causing a failed update
    #Found this was intended unless this method was defined.  Now will only restart if the address (postcode) changes.

    def didDeviceCommPropertyChange(self, origDev, newDev):
            if origDev.pluginProps['address'] != newDev.pluginProps['address']:
                return True
            return False

    def getTariffDevice(self, filter="", valuesDict=None, typeId="", targetId=0):

        retList = []
        devicePlugin = valuesDict.get("devicePlugin", None)
        for dev in indigo.devices.iter():
            if dev.protocol == indigo.kProtocol.Plugin and \
                    dev.pluginId == "com.barn.indigoplugin.OctopusEnergy" and \
                    dev.deviceTypeId != 'OctopusEnergy_consumption':
                retList.append((dev.id, dev.name))

        retList.sort(key=lambda tup: tup[1])
        return retList
