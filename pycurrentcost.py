#!/usr/bin/env python
"""Python Interface to the Current Cost CC128 Power Meter

This module provides two main classes:

  - CurrentCostReader - the interface object
  - CurrentCostReading - a class to represent a reading from the device.
    - CurrentCostUsageReading

Example usage:

  import pycurrentcost

  cc = pycurrentcost.CurrentCostReader(port='/dev/tty.usbserial')
  reading = cc.get_reading()
  print reading

"""

import os
import serial
import logging
import xml.dom.minidom

# Number of attempts to read a result from the unit before failing.
ATTEMPTS = 5

class CurrentCostReading(object):
  """A base class to represent a single reading from the device."""
  def __init__(self, **kwargs):
    # The device name of the serial port.
    self.port = kwargs.get('port', None)
    # The baud rate of the serial port.
    self.baudrate = kwargs.get('baudrate', None)
    # The serial port file descriptor.
    self.serial = kwargs.get('serial', None)
    # The version of the device, as shown in <src> tag
    self.version = kwargs.get('version', None)
    # The sensor number returned, as shown in <sensor> tag
    self.sensor_num = kwargs.get('version', None)
    # Radio ID returned by the sensor (<id> tag)
    self.radio_id = kwargs.get('radio_id', None)
    # Last poll time (<time> tag)
    self.poll_time = kwargs.get('poll_time', None)
    # The temperature at the display unit
    self.temperature = kwargs.get('temperature', None)
    # The raw XML string this object was built from
    self.xml_str = kwargs.get('xml_str', None)
    # The DOM object for that string
    self.xml_dom = None

  def __str__(self):
    doc_str = '''
Serial port : %s
Serial baud rate : %s
Device Version : %s
Sensor Number : %s
Sensor Radio ID : %s
Poll Time : %s
Temperature : %s
XML Response : %s''' % (self.port, self.baudrate, self.version,
                        self.radio_id, self.sensor, self.poll_time,
                        self.temperature, self.xml_str)
    return doc_str

  def dom(self, xml_str=None):
    """Returns the DOM object for this object. Overwrites the XML for the
    object, if provided"""
    if not xml_str and not self.xml_str:
      raise ValueError, 'cannot generate DOM, no xml present or provided'
    else:
      if not self.xml_str:
        self.xml_str = xml_str

    # passed in value wins over existing value
    if xml_str and xml_str != self.xml_str:
      self.xml_str = xml_str

    try:
      self.xml_dom = xml.dom.minidom.parseString(self.xml_str)
    except xml.parsers.expat.ExpatError, e:
      print 'Error parsing XML Response: %s' % (e)
      print 'XML was : %s' % (xml_str)
      raise (CurrentCostException,
             'Error parsing XML Response: "%s", XML was "%s"' % (e, xml_str))

    return self.xml_dom

  def populate(self):
    """Populates the object attributes from the xml_str attribute"""
    if not self.xml_str:
      raise CurrentCostException, 'populate() called on object with no XML'
    # remove occasional stupidness from the XML the device sends back.
    logging.debug('Populating reading object from XML : %s', self.xml_str)

    try:
      self.xml_dom = self.dom()
      self.version = get_single_tag_contents(self.xml_dom, 'src')
      self.sensor_num = get_single_tag_contents(self.xml_dom, 'sensor')
      self.radio_id = get_single_tag_contents(self.xml_dom, 'id')
      self.poll_time = get_single_tag_contents(self.xml_dom, 'time')
      self.temperature = get_single_tag_contents(self.xml_dom, 'tmprF')
    except ValueError, e:
      logging.debug('Error parsing XML Response : %s' % (e))
      logging.debug('XML was : %s' % (self.xml_str))
      raise


class CurrentCostUsageReading(CurrentCostReading):
  """A Usage reading, the most common kind of reading. 
    This basically consists of the info common to all readings, 
    plus readings from individual channels (usually just watts)"""
  def __init__(self, **kwargs):
    CurrentCostReading.__init__(self, **kwargs)
    # a dict of channel# -> watts
    self.channels = {}

    if self.xml_str is not None:
      self.populate()

  def __str__(self):
    doc_str = CurrentCostReading.__str__(self)
    doc_str = doc_str + 'Channel Readings: \n'
    if len(self.channels) == 0:
      doc_str = doc_str + 'None'
    for i in self.channels.keys():
      doc_str = doc_str + '\t%s = %s' % (i, self.channels[i])
    return doc_str

  def populate(self):
    """Populate the object, inclding data from <ch...> tags"""
    try:
      CurrentCostReading.populate(self)
    except ValueError, e:
      logging.debug('Error parsing XML Response : %s' % (e))
      logging.debug('XML was : %s' % (self.xml_str))
      raise
    # Which sensor is this a reading from?
    if self.sensor_num:
      num = int(self.sensor_num)
    else:
      num = 0
    self.channels.setdefault('sensor_num', num)

    # Get contents of <ch...> tags
    for i in range(1, 9):
      data = get_nested_tag_contents(self.xml_dom, 'ch%d' % (i))
      if data:
        logging.debug('Channel info : ch%s = %s', i, data)
        self.channels.setdefault(i, data)
    
def get_single_tag_contents(node, tag):
  """Given a DOM node object and a tag name, returns the text of what's in 
that tag.
This is only for <src>, <tmpr>, <sensor> tags, etc. Tags with tags 
inside should use get_nested_tag_contents"""

  tags = node.getElementsByTagName(tag)

  if not tags:
    return None

  if len(tags) > 1:
    raise ValueError, 'Number of <%s> tags >1' % (tag)

  element = tags[0]

  for node in element.childNodes:
    if node.nodeType == node.TEXT_NODE:
      return node.data

def get_nested_tag_contents(node, tag):
  """Given a DOM node and a tag name, returns a dict of tags 
and contents from inside it.
i.e. given <bing><dzzt1>1</dzt1><dzzt2>2</dzzt2></bing> 
we would return { 'dzzt1' : 1, 'dzzt2' : 2 }
this is mainly used for the <ch...> tags in usage reports, 
which just have a <watts> tag inside them (for now, I'm assuming)"""

  logging.debug('Looking for contents of %s tags in %s', tag, node.toxml())

  tags = node.getElementsByTagName(tag)

  if not tags:
    return None

  if len(tags) > 1:
    raise ValueError, 'Number of <%s> tags >1' % (tag)

  element = tags[0]

  children = {}
  for node in element.childNodes:
    if node.nodeType == node.TEXT_NODE:
      children.update({ tag : node.data })
    else:
      children.update(
        get_nested_tag_contents(node.parentNode, node.localName))
  return children

class CurrentCostHistoryReading(CurrentCostReading):
  """Placeholder, not implemented"""
  pass

class CurrentCostException(Exception):
  """Generic exception for this module"""
  pass

class CurrentCostReadException(CurrentCostException):
  """Exception for when we have an error reading from the serial port"""
  pass

class CurrentCostReader(object):
  """Interface to the Current Cost CC128 power meter.
  Example usage:

    cc = pycurrentcost.CurrentCostReader(port='/dev/tty.usbserial')
    reading = cc.get_reading()

  """
  def __init__(self, port=None, baudrate=57600):
    if not port:
      raise ValueError, 'serial port device not specified'
    self.port = port
    self.baudrate = baudrate
    if not os.path.exists(port):
      raise ValueError, 'device %s does not exist' % (port, )  
    self.serial = None

  def get_xml(self):
    """Poll the serial port once, until we get a non-empty line of
    text from it. Return the result after fixing it up a little
    and ensuring it is a full string."""

    # If the serial port isn't open yet, open it.
    # We only want to open it once or we leak file descriptors.
    if not self.serial:
      self.serial = serial.Serial(self.port,
                                  self.baudrate,
                                  bytesize=serial.EIGHTBITS,
                                  parity=serial.PARITY_NONE,
                                  stopbits=serial.STOPBITS_ONE,
                                  timeout=10)
    # allow some attempts at getting a response
    read_attempts = 0
    result = None
    while read_attempts < ATTEMPTS:
      read_attempts += 1
      logging.debug('Reading from %s, attempt %d',
                                      self.port, read_attempts)
      result = self.serial.readline()
      orig_result = result

      # The unit likes to output random newlines
      if result == '\n':
        continue

      # history messages are not useful and a different format, skip them
      if result.find('<hist>') != -1:
        logging.debug('Skipping history message: %s', result)
        continue

      # Some simple fixups since the unit likes missing the first
      # character or adding an extra character in front.
      if result.startswith('msg>'):
        result = '<%s' % result

      # Sometimes one message is truncated and another started without
      # a newline inbetween.
      msgs = result.split('<msg><src>')[1:]
      if len(msgs) > 1:
        result = '<msg><src>%s' % msgs[1]
      else:
        # Sometimes there is garbage at the start of the line, drop it.
        result = '<msg><src>%s' % msgs[0]

      # Get rid of any trailing newlines or carrage returns.
      result = result.rstrip('\r\n')

      # We might have connected part way through a line and not
      # received a full XML string, if not then return the result.
      if result.startswith('<msg>') and result.endswith('</msg>'):
        break
      else:
        logging.info('Skipping malformed message: %s', orig_result)
      

    if read_attempts == ATTEMPTS or not result:
      # Failed to read
      raise CurrentCostReadException(
       'could not read from %s after %d attempts' % (self.port, ATTEMPTS))

    return result

  def get_reading(self):
    """Obtain a new reading from the device"""
    xml_str = self.get_xml()
    return CurrentCostUsageReading(port=self.port, xml_str=xml_str)

  def close(self):
    """Close the serial port currently in use for the device
    if it is open."""
    if self.serial:
      self.serial.close()

if __name__ == '__main__':
  import sys

  if len(sys.argv) == 1 or len(sys.argv) > 3:
    sys.stderr.write('Usage: %s <serial port device> [<baud rate>]\n' \
                     % (sys.argv[0]))
    sys.exit(-1)
  elif len(sys.argv) == 2:
    cc = CurrentCostReader(sys.argv[1])
  else:
    cc = CurrentCostReader(sys.argv[1], sys.argv[2])

  reading = cc.get_reading()
  print reading.xml_str
  cc.close()
