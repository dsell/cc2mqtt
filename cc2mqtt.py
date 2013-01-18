#!/usr/bin/python
# -*- coding: utf-8 -*-
# vim tabstop=4 expandtab shiftwidth=4 softtabstop=4

#
# cc2mqtt
#	reads power data from the cc128 and posts the full message to mqtt
#


__author__ = "Dennis Sell"
__copyright__ = "Copyright (C) Dennis Sell"



import os
import sys
import mosquitto
import socket
import time
import logging
import signal
import threading
import serial
from config import Config
import pycurrentcost
import commands


CLIENT_VERSION = "0.6"
CLIENT_NAME = "cc2mqtt"
MQTT_TIMEOUT = 60	#seconds


#TODO might want to add a lock file
#TODO  need to deal with no config file existing!!!
#TODO move config file to home dir


#read in configuration file
homedir = os.path.expanduser("~")
f = file(homedir + '/.cc2mqtt.conf')
cfg = Config(f)
MQTT_HOST = cfg.MQTT_HOST
MQTT_PORT = cfg.MQTT_PORT
CLIENT_TOPIC = cfg.CLIENT_TOPIC
BASE_TOPIC = cfg.BASE_TOPIC
INTERVAL = cfg.INTERVAL
SERIAL_PORT = cfg.SERIAL_PORT


mqtt_connected = 0


#define what happens after connection
def on_connect(self, obj, rc):
	global mqtt_connected
	global running

	mqtt_connected = True
	print "MQTT Connected"
	mqttc.publish( CLIENT_TOPIC + "status" , "online", 1, 1 )
	mqttc.publish( CLIENT_TOPIC + "version", CLIENT_VERSION, 1, 1 )
	ip = commands.getoutput("/sbin/ifconfig").split("\n")[1].split()[1][5:]
	mqttc.publish( CLIENT_TOPIC + "ip", ip, 1, 1 )
	mqttc.publish( CLIENT_TOPIC + "pid", os.getpid(), 1, 1 )
	mqttc.subscribe( CLIENT_TOPIC + "ping", 2)


def on_message(self, obj, msg):
	if (( msg.topic == CLIENT_TOPIC + "ping" ) and ( msg.payload == "request" )):
		mqttc.publish( CLIENT_TOPIC + "ping", "response", qos = 1, retain = 0 )


def do_cc128_loop():
	global running
	global mqttc
#	global usb
	global cc

	while running:
		try:
			reading = cc.get_reading()
			xml = reading.xml_str
			print xml
			mqttc.publish( BASE_TOPIC + "xml", xml, qos = 2 )
			mqttc.publish( BASE_TOPIC + "version", str(reading.version), 2 , 1 )
			mqttc.publish( BASE_TOPIC + "sensor_num", str(reading.sensor_num), 2 , 1 )
			mqttc.publish( BASE_TOPIC + "radio_id", str(reading.radio_id), 2 , 1 )
			mqttc.publish( BASE_TOPIC + "poll_time", str(reading.poll_time), 2 , 1 )
			mqttc.publish( BASE_TOPIC + "temperature", str(reading.temperature), 2 , 1 )
			try:
				for i in range( 1, 9 ):
					mqttc.publish( BASE_TOPIC + "channel-" + str(i), str(reading.channels[i]['watts']), 2, 1 )
			except:
				mqttc.publish( BASE_TOPIC + "number-channels", i-1 , 2, 1 )
		except:
			pass


def do_disconnect():
       global mqtt_connected
       mqttc.disconnect()
       mqtt_connected = False
       print "Disconnected"


def mqtt_disconnect():
	global mqtt_connected
	print "Disconnecting..."
	mqttc.disconnect()
	if ( mqtt_connected ):
		mqtt_connected = False 
		print "MQTT Disconnected"
		mqttc.publish ( "/clients/" + CLIENT_NAME + "/status" , "offline", 1, 1 )


def mqtt_connect():
	rc = 1
	while ( rc ):
		print "Attempting connection..."
		mqttc.will_set(CLIENT_TOPIC + "status", "disconnected", 1, 1)

		#define the mqtt callbacks
		mqttc.on_message = on_message
		mqttc.on_connect = on_connect
#		mqttc.on_disconnect = on_disconnect

		#connect
		rc = mqttc.connect( MQTT_HOST, MQTT_PORT, MQTT_TIMEOUT )
		if rc != 0:
			logging.info( "Connection failed with error code $s, Retrying in 30 seconds.", rc )
			print "Connection failed with error code ", rc, ", Retrying in 30 seconds." 
			time.sleep(30)
		else:
			print "Connect initiated OK"


def cleanup(signum, frame):
	mqtt_disconnect()
	sys.exit(signum)


#create a client
mqttc = mosquitto.Mosquitto( CLIENT_NAME, clean_session=False, obj=None ) 

#trap kill signals including control-c
signal.signal(signal.SIGTERM, cleanup)
signal.signal(signal.SIGINT, cleanup)

#usb = serial.Serial(port=SERIAL_PORT, baudrate=57600)
cc = pycurrentcost.CurrentCostReader(port=SERIAL_PORT)

running = True

t = threading.Thread(target=do_cc128_loop)
t.start()


def main_loop():
	global mqtt_connected
	mqttc.loop(10)
	while running:
		if ( mqtt_connected ):
			rc = mqttc.loop(10)
			if rc != 0:	
				mqtt_disconnect()
				print rc
				print "Stalling for 20 seconds to allow broker connection to time out."
				time.sleep(20)
				mqtt_connect()
				mqttc.loop(10)
		pass


mqtt_connect()
main_loop()

