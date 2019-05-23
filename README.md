# zigpy

[![Build Status](https://travis-ci.org/zigpy/zigpy.svg?branch=master)](https://travis-ci.org/zigpy/zigpy)
[![Coverage](https://coveralls.io/repos/github/zigpy/zigpy/badge.svg?branch=master)](https://coveralls.io/github/zigpy/zigpy?branch=master)

**[zigpy](https://github.com/zigpy/zigpy)** is **[Zigbee protocol stack](https://en.wikipedia.org/wiki/Zigbee)** integration project to implement the **[Zigbee Home Automation](https://www.zigbee.org/)** standard as a Python 3 library. 

Zigbee Home Automation integration with zigpy allows you to connect one of many off-the-shelf Zigbee adapters using one of the available Zigbee radio library modules compatible with zigpy to control Zigbee based devices. There is currently support for controlling Zigbee device types such as binary sensors (e.g., motion and door sensors), sensors (e.g., temperature sensors), lightbulbs, switches, and fans. A working implementation of zigbe exist in **[Home Assistant](https://www.home-assistant.io)** (Python based open source home automation software) as part of its **[ZHA component](https://www.home-assistant.io/components/zha/)**

zigpy works with separate radio libraries which can each interface with multiple USB and GPIO radio adapters/modules over different native UART serial protocols. Such radio libraries includes **[bellows](https://github.com/zigpy/bellows)** (which communicates with EZSP/EmberZNet based radios) and **[zigpy-xbee](https://github.com/zigpy/zigpy-xbee)** (which communicates with XBee based Zigbee radios). There are also experimental radio libraries called **[zigpy-deconz](https://github.com/zigpy/zigpy-deconz)** and **[pyconz](https://github.com/Equidamoid/pyconz/)** available for deCONZ serial protocol (for communicating with ConBee and RaspBee USB and GPIO radios from Dresden-Elektronik).

**Known working Zigbee radio modules:**
- EmberZNet based radios using the EZSP protocol (via the [bellows](https://github.com/zigpy/bellows) library for zigpy)
  - [Nortek GoControl QuickStick Combo Model HUSBZB-1 (Z-Wave & Zigbee USB Adapter)](https://www.nortekcontrol.com/products/2gig/husbzb-1-gocontrol-quickstick-combo/)
  - [Elelabs Zigbee USB Adapter](https://elelabs.com/products/elelabs_usb_adapter.html)
  - [Elelabs Zigbee Raspberry Pi Shield](https://elelabs.com/products/elelabs_zigbee_shield.html)
- XBee Zigbee based radios (via the [zigpy-xbee](https://github.com/zigpy/zigpy-xbee) library for zigpy)
  - Digi XBee Series 2C (S2C) modules
  - Digi XBee Series 2 (S2) modules. Note: These will need to be manually flashed with the Zigbee Coordinator API firmware via XCTU.
  - Digi XBee Series 3 (xbee3-24) modules
- deCONZ based radios (via the [zigpy-deconz](https://github.com/zigpy/zigpy-deconz) library for zigpy)
  - [ConBee II (a.k.a. ConBee 2) USB adapter from Dresden-Elektronik](https://shop.dresden-elektronik.de/conbee-2.html)
  - [ConBee](https://www.dresden-elektronik.de/conbee/) USB adio adapter from [Dresden-Elektronik](https://www.dresden-elektronik.de)
  - [RaspBee](https://www.dresden-elektronik.de/raspbee/) GPIO radio adapter from [Dresden-Elektronik](https://www.dresden-elektronik.de)
  
  **Related projects:**
  ZHA deviation handling in Home Assistant relies on on the third-party [ZHA Device Handlers](https://github.com/dmulcahey/zha-device-handlers) project. Zigbee devices that deviate from or do not fully conform to the standard specifications set by the [Zigbee Alliance](https://www.zigbee.org) may require the development of custom [ZHA Device Handlers](https://github.com/dmulcahey/zha-device-handlers) (ZHA custom quirks handler implementation) to for all their functions to work properly with the ZHA component in Home Assistant. These ZHA Device Handlers for Home Assistant can thus be used to parse custom messages to and from non-compliant Zigbee devices. The custom quirks implementations for zigpy implemented as ZHA Device Handlers for Home Assistant are a similar concept to that of [Hub-connected Device Handlers for the SmartThings Classics platform](https://docs.smartthings.com/en/latest/device-type-developers-guide/) as well as that of [Zigbee-Shepherd Converters as used by Zigbee2mqtt](https://www.zigbee2mqtt.io/how_tos/how_to_support_new_devices.html), meaning they are each virtual representations of a physical device that expose additional functionality that is not provided out-of-the-box by the existing integration between these platforms.
