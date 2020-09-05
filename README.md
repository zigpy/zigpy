# zigpy

[![Build Status](https://travis-ci.org/zigpy/zigpy.svg?branch=master)](https://travis-ci.org/zigpy/zigpy)
[![Coverage](https://coveralls.io/repos/github/zigpy/zigpy/badge.svg?branch=master)](https://coveralls.io/github/zigpy/zigpy?branch=master)

**[zigpy](https://github.com/zigpy/zigpy)** is **[Zigbee protocol stack](https://en.wikipedia.org/wiki/Zigbee)** integration project to implement the **[Zigbee Home Automation](https://www.zigbee.org/)** standard as a Python 3 library. 

Zigbee Home Automation integration with zigpy allows you to connect one of many off-the-shelf Zigbee adapters using one of the available Zigbee radio library modules compatible with zigpy to control Zigbee based devices. There is currently support for controlling Zigbee device types such as binary sensors (e.g., motion and door sensors), sensors (e.g., temperature sensors), lightbulbs, switches, and fans.

zigpy contains common code implementing Zigbee ZCL, ZDO and application state management which is being used by various radio libraries implementing the actual interface with the radio modules from different manufacturers. The separate radio libraries interface with radio hardware adapters/modules over USB and GPIO using different native UART serial protocols.

Reference implementation of the zigpy library exist in **[Home Assistant](https://www.home-assistant.io)** (Python based open source home automation software) as part of its **[ZHA integration component](https://www.home-assistant.io/integrations/zha/)**.

## How to install and test, report bugs, or contribute to this project

For specific instructions on how-to install and test zigpy or contribute bug-reports and code to this project please see the guidelines in the CONTRIBUTING.md file:

- [Guidelines in CONTRIBUTING.md](./CONTRIBUTING.md)

This CONTRIBUTING.md file will contain information about using zigpy, testiing new releases, troubleshooting and bug-reporting as, as well as librar + code instructions for developers and more.

You can contribute to this project either as an end-user, a tester (advanced user contributing constructive issue/bug-reports) or as a developer contributing code.

## Compatible hardware

Radio libraries for zigpy include **[bellows](https://github.com/zigpy/bellows)** (which communicates with EZSP/ZNet based radios), **[zigpy-xbee](https://github.com/zigpy/zigpy-xbee)** (which communicates with XBee based Zigbee radios), and as **[zigpy-deconz](https://github.com/zigpy/zigpy-deconz)** for deCONZ serial protocol (for communicating with ConBee and RaspBee USB and GPIO radios from Dresden-Elektronik). There are also experimental radio libraries called **[zigpy-zigate](https://github.com/zigpy/zigpy-zigate)** for communicating with ZiGate based radios and **[zigpy-cc](https://github.com/zigpy/zigpy-cc)** for communicating with Texas Instruments based radios based radios that have custom Z-Stack coordinator firmware.

### Known working Zigbee radio modules

- **EmberZNet based radios** using the EZSP protocol (via the [bellows](https://github.com/zigpy/bellows) library for zigpy)
  - [ITEAD Sonoff ZBBridge](https://www.itead.cc/smart-home/sonoff-zbbridge.html) (Note! This first have to be flashed with [Tasmota firmware and EmberZNet firmware](https://www.digiblur.com/2020/07/how-to-use-sonoff-zigbee-bridge-with.html))
  - [Nortek GoControl QuickStick Combo Model HUSBZB-1 (Z-Wave & Zigbee USB Adapter)](https://www.nortekcontrol.com/products/2gig/husbzb-1-gocontrol-quickstick-combo/)
  - [Elelabs Zigbee USB Adapter](https://elelabs.com/products/elelabs_usb_adapter.html)
  - [Elelabs Zigbee Raspberry Pi Shield](https://elelabs.com/products/elelabs_zigbee_shield.html)
  - Telegesis ETRX357USB (Note! First have to be flashed with other EmberZNet firmware)
  - Telegesis ETRX357USB-LRS (Note! First have to be flashed with other EmberZNet firmware)
  - Telegesis ETRX357USB-LRS+8M (Note! First have to be flashed with other EmberZNet firmware)
- **XBee Zigbee based radios** (via the [zigpy-xbee](https://github.com/zigpy/zigpy-xbee) library for zigpy)
  - Digi XBee Series 2C (S2C) modules
  - Digi XBee Series 2 (S2) modules. Note: These will need to be manually flashed with the Zigbee Coordinator API firmware via XCTU.
  - Digi XBee Series 3 (xbee3-24) modules
- **deCONZ based radios** (via the [zigpy-deconz](https://github.com/zigpy/zigpy-deconz) library for zigpy)
  - [ConBee II (a.k.a. ConBee 2) USB adapter from dresden dlektronik](https://shop.dresden-elektronik.de/conbee-2.html)
  - [ConBee](https://www.dresden-elektronik.de/conbee/) USB radio adapter from [dresden elektronik](https://www.dresden-elektronik.de)
  - [RaspBee II (a.k.a. RaspBee 2)](https://www.dresden-elektronik.com/product/raspbee-II.html) GPIO radio adapter from [dresden elektronik](https://www.dresden-elektronik.de)
  - [RaspBee](https://www.dresden-elektronik.de/raspbee/) GPIO radio adapter from [dresden elektronik](https://www.dresden-elektronik.de)

### Experimental support for additional Zigbee radio modules

- **[ZiGate open source ZigBee adapter hardware](https://zigate.fr/)** (via the [zigpy-zigate](https://github.com/zigpy/zigpy-zigate) library for zigpy)
  - [ZiGate USB-TTL](https://zigate.fr/produit/zigate-ttl/) (Note! Requires ZiGate firmware 3.1a or later)
  - [ZiGate USB-DIN](https://zigate.fr/produit/zigate-usb-din/) (Note! Requires ZiGate firmware 3.1a or later)
  - [PiZiGate (ZiGate module for Raspberry Pi GPIO)](https://zigate.fr/produit/pizigate-v1-0/) (Note! Requires ZiGate firmware 3.1a or later)
  - [ZiGate Pack WiFi](https://zigate.fr/produit/zigate-pack-wifi-v1-3/) (Note! Requires ZiGate firmware 3.1a or later)
- **Texas Instruments CC253x, CC26x2R, and CC13x2 based radios** (via the [zigpy-cc](https://github.com/zigpy/zigpy-cc) library for zigpy)
  - [CC2531 USB stick hardware flashed with custom Z-Stack coordinator firmware from the Zigbee2mqtt project](https://www.zigbee2mqtt.io/getting_started/what_do_i_need.html)
  - [CC2530 + CC2591/CC2592 USB stick hardware flashed with custom Z-Stack coordinator firmware from the Zigbee2mqtt project](https://www.zigbee2mqtt.io/getting_started/what_do_i_need.html)
  - [CC2538 + CC2592 dev board hardware flashed with custom Z-Stack coordinator firmware from the Zigbee2mqtt project](https://www.zigbee2mqtt.io/getting_started/what_do_i_need.html)  
  - [CC2652P/CC2652R/CC2652RB USB stick and dev board hardware flashed with custom Z-Stack coordinator firmware from the Zigbee2mqtt project](https://www.zigbee2mqtt.io/getting_started/what_do_i_need.html)
  - [CC1352P/CC1352R USB stick and dev board hardware flashed with custom Z-Stack coordinator firmware from the Zigbee2mqtt project](https://www.zigbee2mqtt.io/getting_started/what_do_i_need.html)

## Release packages available via PyPI

New packages of tagged versions are also released via the "zigpy" project on PyPI
  - https://pypi.org/project/zigpy/
    - https://pypi.org/project/zigpy/#history
    - https://pypi.org/project/zigpy/#files

Older packages of tagged versions are still available on the "zigpy-homeassistant" project on PyPI
  - https://pypi.org/project/zigpy-homeassistant/

Packages of tagged versions of the radio libraries are released via separate projects on PyPI
- https://pypi.org/project/zigpy/
  - https://pypi.org/project/bellows/
  - https://pypi.org/project/zigpy-xbee/
  - https://pypi.org/project/zigpy-deconz/
  - https://pypi.org/project/zigpy-zigate/
  - https://pypi.org/project/zigpy-cc/

## Related projects

### ZHA Device Handlers
ZHA deviation handling in Home Assistant relies on the third-party [ZHA Device Handlers](https://github.com/zigpy/zha-device-handlers) project. Zigbee devices that deviate from or do not fully conform to the standard specifications set by the [Zigbee Alliance](https://www.zigbee.org) may require the development of custom [ZHA Device Handlers](https://github.com/zigpy/zha-device-handlers) (ZHA custom quirks handler implementation) to for all their functions to work properly with the ZHA component in Home Assistant. These ZHA Device Handlers for Home Assistant can thus be used to parse custom messages to and from non-compliant Zigbee devices. The custom quirks implementations for zigpy implemented as ZHA Device Handlers for Home Assistant are a similar concept to that of [Hub-connected Device Handlers for the SmartThings platform](https://docs.smartthings.com/en/latest/device-type-developers-guide/) as well as that of [zigbee-herdsman converters as used by Zigbee2mqtt](https://www.zigbee2mqtt.io/how_tos/how_to_support_new_devices.html), meaning they are each virtual representations of a physical device that expose additional functionality that is not provided out-of-the-box by the existing integration between these platforms.

### ZHA integration component for Home Assistant
[ZHA integration component for Home Assistant](https://www.home-assistant.io/integrations/zha/) is a reference implementation of the zigpy library as integrated into the core of **[Home Assistant](https://www.home-assistant.io)** (a Python based open source home automation software). There are also other GUI and non-GUI projects for Home Assistant's ZHA components which builds on or depends on its features and functions to enhance or improve its user-experience, some of those are listed and linked below.

#### ZHA Custom Radios
[zha-custom-radios](https://github.com/zha-ng/zha-custom-radios) adds support for custom radio modules for zigpy to [[Home Assistant's ZHA (Zigbee Home Automation) integration component]](https://www.home-assistant.io/integrations/zha/). This custom component for Home Assistant allows users to test out new modules for zigpy in Home Assistant's ZHA integration component before they are integrated into zigpy ZHA and also helps developers new zigpy radio modules without having to modify the Home Assistant's source code.

#### ZHA Custom
[zha_custom](https://github.com/Adminiuga/zha_custom) is a custom component package for Home Assistant (with its ZHA component for zigpy integration) that acts as zigpy commands service wrapper, when installed it allows you to enter custom commands via to zigy to example change advanced configuration and settings that are not available in the UI.

#### ZHA Map
[zha-map](https://github.com/zha-ng/zha-map) for Home Assistant's ZHA component can build a Zigbee network topology map.

#### ZHA Network Visualization Card
[zha-network-visualization-card](https://github.com/dmulcahey/zha-network-visualization-card) is a custom Lovelace element for Home Assistant which visualize the Zigbee network for the ZHA component.

#### ZHA Network Card
[zha-network-card](https://github.com/dmulcahey/zha-network-card) is a custom Lovelace card for Home Assistant that displays ZHA component Zigbee network and device information in Home Assistant

#### ZHA Device Exporter
[zha-device-exporter](https://github.com/dmulcahey/zha-device-exporter) is a custom component for Home Assistant to allow the ZHA component to export lists of Zigbee devices.

#### ZHA Custom Radios
[zha-custom-radios](https://github.com/zha-ng/zha-custom-radios) A now obsolete custom component package for Home Assistant (with its ZHA component for zigpy integration) that allows users to test out new zigpy radio libraries and hardware modules before they have officially been integrated into ZHA. This enables developers and testers to test new or updated zigpy radio modules without having to modify the Home Assistant source code.

#### Zigpy Deconz Parser
[zigpy-deconz-parser](https://github.com/zha-ng/zigpy-deconz-parser) allow you to parse Home Assistant's ZHA component debug log using `zigpy-deconz` library if you are using a deCONZ based adapter like ConBee or RaspBee.
