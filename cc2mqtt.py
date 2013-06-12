#!/usr/bin/python
# -*- coding: utf-8 -*-
# vim tabstop=4 expandtab shiftwidth=4 softtabstop=4

#
# cc2mqtt
#    reads power data from the cc128 and posts the full message to mqtt
#


__author__ = "Dennis Sell"
__copyright__ = "Copyright (C) Dennis Sell"


APPNAME = "cc2mqtt"
VERSION = "0.10"
WATCHTOPIC = "/raw/" + APPNAME + "/"

import logging
import pycurrentcost
import threading
from daemon import Daemon
from mqttcore import MQTTClientCore
from mqttcore import main


class MyMQTTClientCore(MQTTClientCore):
    def __init__(self, appname, clienttype):
        MQTTClientCore.__init__(self, appname, clienttype)
        self.clientversion = VERSION
        self.watchtopic = WATCHTOPIC
        self.serialport = self.cfg.SERIAL_PORT
    
        t = threading.Thread(target=self.do_thread_loop)
        t.start()

    def do_thread_loop(self):
        cc = pycurrentcost.CurrentCostReader(port=self.serialport)
        while (self.running):
            if (self.mqtt_connected):              
                try:
                    reading = cc.get_reading()
                    xml = reading.xml_str
                    print xml
#QOS values all qrong and broken!!!! TODO
                    self.mqttc.publish(self.watchtopic + "xml", xml, qos=2, retain=True)
                    self.mqttc.publish(self.watchtopic + "version",
                                        str(reading.version), qos=2, retain=True)
                    self.mqttc.publish(self.watchtopic + "sensor_num",
                                        str(reading.sensor_num), qos=2, retain=True)
                    self.mqttc.publish(self.watchtopic + "radio_id",
                                        str(reading.radio_id), qos=2, retain=True)
                    self.mqttc.publish(self.watchtopic + "poll_time",
                                        str(reading.poll_time), qos=2, retain=True)
                    self.mqttc.publish(self.watchtopic + "temperature",
                                        str(reading.temperature), qos=2, retain=True)
                    try:
                        for i in range(1, 9):
                            self.mqttc.publish(self.watchtopic + "channel-" +
                                               str(i),
                                               str(reading.channels[i]['watts']),
                                                        qos=2, retain=True)
                    except:
                        self.mqttc.publish(self.watchtopic +
                                           "number-channels", i - 1, qos=2, retain=True)
                except:
                    pass
            pass

class MyDaemon(Daemon):
    def run(self):
        mqttcore = MyMQTTClientCore(APPNAME, clienttype="single")
        mqttcore.main_loop()


if __name__ == "__main__":
    daemon = MyDaemon('/tmp/' + APPNAME + '.pid')
    main(daemon)
