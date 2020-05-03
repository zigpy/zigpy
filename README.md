# zigpy

[![Build Status](https://travis-ci.org/zigpy/zigpy.svg?branch=master)](https://travis-ci.org/zigpy/zigpy)
[![Coverage](https://coveralls.io/repos/github/zigpy/zigpy/badge.svg?branch=master)](https://coveralls.io/github/zigpy/zigpy?branch=master)

**[zigpy](https://github.com/zigpy/zigpy)** is **[Zigbee protocol stack](https://en.wikipedia.org/wiki/Zigbee)** integration project to implement the **[Zigbee Home Automation](https://www.zigbee.org/)** standard as a Python 3 library. 

Zigbee Home Automation integration with zigpy allows you to connect one of many off-the-shelf Zigbee adapters using one of the available Zigbee radio library modules compatible with zigpy to control Zigbee based devices. There is currently support for controlling Zigbee device types such as binary sensors (e.g., motion and door sensors), sensors (e.g., temperature sensors), lightbulbs, switches, and fans.

zigpy contains common code implementing Zigbee ZCL, ZDO and application state management which is being used by various radio libraries implementing the actual interface with the radio modules from different manufacturers. The separate radio libraries interface with radio hardware adapters/modules over USB and GPIO using different native UART serial protocols.

Reference implementation of the zigpy library exist in **[Home Assistant](https://www.home-assistant.io)** (Python based open source home automation software) as part of its **[ZHA integration component](https://www.home-assistant.io/integrations/zha/)**.

## Compatible hardware

Radio libraries for zigpy include **[bellows](https://github.com/zigpy/bellows)** (which communicates with EZSP/EmberZNet based radios), **[zigpy-xbee](https://github.com/zigpy/zigpy-xbee)** (which communicates with XBee based Zigbee radios), and as **[zigpy-deconz](https://github.com/zigpy/zigpy-deconz)** for deCONZ serial protocol (for communicating with ConBee and RaspBee USB and GPIO radios from Dresden-Elektronik). There are also experimental radio libraries called **[zigpy-zigate](https://github.com/zigpy/zigpy-zigate)** for communicating with ZiGate based radios and **[zigpy-cc](https://github.com/zigpy/zigpy-cc)** for communicating with Texas Instruments based radios based radios that have custom Z-Stack coordinator firmware.

### Known working Zigbee radio modules

- **EmberZNet based radios** using the EZSP protocol (via the [bellows](https://github.com/zigpy/bellows) library for zigpy)
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
  - [ConBee II (a.k.a. ConBee 2) USB adapter from Dresden-Elektronik](https://shop.dresden-elektronik.de/conbee-2.html)
  - [ConBee](https://www.dresden-elektronik.de/conbee/) USB radio adapter from [Dresden-Elektronik](https://www.dresden-elektronik.de)
  - [RaspBee](https://www.dresden-elektronik.de/raspbee/) GPIO radio adapter from [Dresden-Elektronik](https://www.dresden-elektronik.de)
  
### Experimental support for additional Zigbee radio modules

- **[ZiGate open source ZigBee adapter hardware](https://zigate.fr/)** (via the [zigpy-zigate](https://github.com/zigpy/zigpy-zigate) library for zigpy)
  - [ZiGate USB-TTL](https://zigate.fr/produit/zigate-ttl/) (Note! Requires ZiGate firmware 3.1a or later)
  - [ZiGate USB-DIN](https://zigate.fr/produit/zigate-usb-din/) (Note! Requires ZiGate firmware 3.1a or later)
  - [PiZiGate (ZiGate module for Raspberry Pi GPIO)](https://zigate.fr/produit/pizigate-v1-0/) (Note! Requires ZiGate firmware 3.1a or later)
  - [ZiGate Pack WiFi](https://zigate.fr/produit/zigate-pack-wifi-v1-3/) (Note! Requires ZiGate firmware 3.1a or later)
- **Texas Instruments CC253x, CC26x2R, and CC13x2 based radios** (via the [zigpy-cc](https://github.com/zigpy/zigpy-cc) library for zigpy)
  - [CC2531 USB stick hardware flashed with custom Z-Stack coordinator firmware from the Zigbee2mqtt project](https://www.zigbee2mqtt.io/getting_started/what_do_i_need.html)
  - [CC2530 + CC2591 USB stick hardware flashed with custom Z-Stack coordinator firmware from the Zigbee2mqtt project](https://www.zigbee2mqtt.io/getting_started/what_do_i_need.html)
  - [CC2530 + CC2592 dev board hardware flashed with custom Z-Stack coordinator firmware from the Zigbee2mqtt project](https://www.zigbee2mqtt.io/getting_started/what_do_i_need.html)
  - [CC2652R dev board hardware flashed with custom Z-Stack coordinator firmware from the Zigbee2mqtt project](https://www.zigbee2mqtt.io/getting_started/what_do_i_need.html)
  - [CC1352P-2 dev board hardware flashed with custom Z-Stack coordinator firmware from the Zigbee2mqtt project](https://www.zigbee2mqtt.io/getting_started/what_do_i_need.html)
  - [CC2538 + CC2592 dev board hardware flashed with custom Z-Stack coordinator firmware from the Zigbee2mqtt project](https://www.zigbee2mqtt.io/getting_started/what_do_i_need.html)  

## Testing new releases

Testing a new release of the zigpy library before it is released in Home Assistant.

If you are using Supervised Home Assistant (formerly known as the Hassio/Hass.io distro):
- Add https://github.com/home-assistant/hassio-addons-development as "add-on" repository
- Install "Custom deps deployment" addon
- Update config like: 
  ```
  pypi:
    - zigpy==0.20.0
  apk: []
  ```
  where 0.20.0 is the new version
- Start the addon

If you are instead using some custom python installation of Home Assistant then do this:
- Activate your python virtual env
- Update package with ``pip``
  ```
  pip install zigpy==0.20.0

## Release packages available via PyPI

New packages of tagged versions are also released via the "zigpy" project on PyPI
  - https://pypi.org/project/zigpy/
    - https://pypi.org/project/zigpy/#history
    - https://pypi.org/project/zigpy/#files

Older packages of tagged versions are still available on the "zigpy-homeassistant" project on PyPI
  - https://pypi.org/project/zigpy-homeassistant/

Packages of tagged versions of the radio libraries are released via seperate projects on PyPI
- https://pypi.org/project/zigpy/
  - https://pypi.org/project/bellows/
  - https://pypi.org/project/zigpy-xbee/
  - https://pypi.org/project/zigpy-deconz/
  - https://pypi.org/project/zigpy-zigate/
  - https://pypi.org/project/zigpy-cc/

## How to contribute 

You can contribute to this project either as a end-user, a tester (advanced user contributing constructive issue/bug-reports) or as a developer contibuting code.

### How to contribute as an end-user

If you think that you are having problems due to a bug then please see the section below on reporting issues as a tester, but be aware that reporting issues put higher responsibility on your active involment on your part as a tester.

Some developers might be also interested in receiving donations in the form of money or hardware such as Zigbee modules and devices, and even if such donations are most often donated with no strings attached it could in many cases help the developers motivation and indirect improve the development of this project. 

Sometimes it might just be simpler to just donate money earmarked to specifically let an willing developer buy the exact same type Zigbee device that you are having issues with to be able to replicate the issue themselves in order to troubleshoot and hopefully also solve the problem.

Consider submitting a post on GitHub projects issues tracker about willingness to making a donation (please see section bellow on posing issues).

### How to report issues or bugs as a tester

Issues or bugs are normally first be submitted upstream to the software/project that it utilizing zigpy and its radio libraries, (like for example Home Assistant), however if and when the issue is determened to be in the zigpy or underlying radio library then you should continue by submitting a detailed issue/bug report via the GitHub projects issues tracker.

Always be sure to first check if there is not already an existing issue posted with the same description before posting a new issue.

- https://help.github.com/en/github/managing-your-work-on-github/creating-an-issue
  - https://guides.github.com/features/issues/

### How to contribute as a developer

If you are looking to make a contribution as a developer to this project we suggest that you follow the steps in these guides:

- https://github.com/firstcontributions/first-contributions/blob/master/README.md
  - https://github.com/firstcontributions/first-contributions/blob/master/github-desktop-tutorial.md

Code changes or additions can then be submitted to this project on GitHub via pull requests:

- https://help.github.com/en/github/collaborating-with-issues-and-pull-requests/about-pull-requests
  - https://help.github.com/en/github/collaborating-with-issues-and-pull-requests/creating-a-pull-request

## Developer references

Silicon Labs video playlist of ZigBee Concepts: Architecture basics, MAC/PHY, node types, and application profiles
- https://www.youtube.com/playlist?list=PL-awFRrdECXvAs1mN2t2xaI0_bQRh2AqD

## Related projects

### ZHA Device Handlers
ZHA deviation handling in Home Assistant relies on on the third-party [ZHA Device Handlers](https://github.com/zigpy/zha-device-handlers) project. Zigbee devices that deviate from or do not fully conform to the standard specifications set by the [Zigbee Alliance](https://www.zigbee.org) may require the development of custom [ZHA Device Handlers](https://github.com/zigpy/zha-device-handlers) (ZHA custom quirks handler implementation) to for all their functions to work properly with the ZHA component in Home Assistant. These ZHA Device Handlers for Home Assistant can thus be used to parse custom messages to and from non-compliant Zigbee devices. The custom quirks implementations for zigpy implemented as ZHA Device Handlers for Home Assistant are a similar concept to that of [Hub-connected Device Handlers for the SmartThings platform](https://docs.smartthings.com/en/latest/device-type-developers-guide/) as well as that of [zigbee-herdsman converters as used by Zigbee2mqtt](https://www.zigbee2mqtt.io/how_tos/how_to_support_new_devices.html), meaning they are each virtual representations of a physical device that expose additional functionality that is not provided out-of-the-box by the existing integration between these platforms.
