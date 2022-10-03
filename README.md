# zigpy

[![Build](https://github.com/zigpy/zigpy/workflows/CI/badge.svg?branch=dev)](https://github.com/zigpy/zigpy/workflows/CI/badge.svg?branch=dev)
[![Coverage Status](https://codecov.io/gh/zigpy/zigpy/branch/dev/graph/badge.svg)](https://codecov.io/gh/zigpy/zigpy)

**[zigpy](https://github.com/zigpy/zigpy)** is a hardware independent **[Zigbee protocol stack](https://en.wikipedia.org/wiki/Zigbee)** integration project to implement **[Zigbee](https://www.zigbee.org/)** standard specifications as a Python 3 library. 

Zigbee integration via zigpy allows you to connect one of many off-the-shelf Zigbee Coordinator adapters using one of the available Zigbee radio library modules compatible with zigpy to control Zigbee based devices. There is currently support for controlling Zigbee device types such as binary sensors (e.g., motion and door sensors), sensors (e.g., temperature sensors), lights, switches, buttons, covers, fans, climate control equipment, locks, and intruder alarm system devices.

Zigbee stacks and hardware from many different hardware chip manufacturers are supported via radio libraries which translate their proprietary communication protocol into a common API which is shared among all radio libraries for zigpy. If some Zigbee stack or Zigbee Coordinator hardware for other manufacturers is not supported by yet zigpy it is possible for any independent developer to step-up and develop a new radio library for zigpy which translates its proprietary communication protocol into the common API that zigpy can understand.

zigpy contains common code implementing ZCL (Zigbee Cluster Library) and ZDO (Zigbee Device Object) application state management which is being used by various radio libraries implementing the actual interface with the radio modules from different manufacturers. The separate radio libraries interface with radio hardware adapters/modules over USB and GPIO using different native UART serial protocols.

The **[ZHA integration component for Home Assistant](https://www.home-assistant.io/integrations/zha/)**, the [Zigbee Plugin for Domoticz](https://www.domoticz.com/wiki/ZigbeeForDomoticz), and the [Zigbee Plugin for Jeedom](https://doc.jeedom.com/en_US/plugins/automation%20protocol/zigbee/) (competing open-source home automation software) are all using [zigpy libraries](https://github.com/zigpy/) as dependencies, as such they could be used as references of different implementations if looking to integrate a Zigbee solution into your application.

### Zigbee device OTA updates

zigpy have ability to download and perform Zigbee OTAU (Over-The-Air Updates) of Zigbee devices firmware. The Zigbee OTA update firmware image files should conform to standard Zigbee OTA format and OTA provider source URLs need to be published for public availability. Updates from a local OTA update directory also is also supported and can be used as an option for offline firmware updates if user provide correct Zigbee OTA formatted firmware files themselves.

Support for automatic download from existing online OTA providers in zigpy OTA provider code is currently only available for IKEA, Inovelli, LEDVANCE/OSRAM, SALUS/Computime, and SONOFF/ITEAD devices. Support for additional OTA providers for other manufacturers devices could be added to zigpy in the future, if device manufacturers publish their firmware images publicly and developers contribute the needed download code for them.

## How to install and test, report bugs, or contribute to this project

For specific instructions on how-to install and test zigpy or contribute bug-reports and code to this project please see the guidelines in the CONTRIBUTING.md file:

- [Guidelines in CONTRIBUTING.md](./CONTRIBUTING.md)

This CONTRIBUTING.md file will contain information about using zigpy, testing new releases, troubleshooting and bug-reporting as, as well as library + code instructions for developers and more. This file also contain short summeries and links to other related projects that directly or indirectly depends in zigpy libraries.

You can contribute to this project either as an end-user, a tester (advanced user contributing constructive issue/bug-reports) or as a developer contributing code.

## Compatible Zigbee coordinator hardware

Radio libraries for zigpy are separate projects with their own repositories and include **[bellows](https://github.com/zigpy/bellows)** (for communicating with Silicon Labs EmberZNet based radios), **[zigpy-deconz](https://github.com/zigpy/zigpy-deconz)** (for communicating with deCONZ based radios from Dresden Elektronik), and **[zigpy-xbee](https://github.com/zigpy/zigpy-xbee)** (for communicating with XBee based Zigbee radios), **[zigpy-zigate](https://github.com/zigpy/zigpy-zigate)** for communicating with ZiGate based radios, **[zigpy-znp](https://github.com/zha-ng/zigpy-znp)** or **[zigpy-cc](https://github.com/zigpy/zigpy-cc)** for communicating with Texas Instruments based radios that have Z-Stack ZNP coordinator firmware.

Note! Zigbee 3.0 support or not in zigpy depends primarily on your Zigbee coordinator hardware and its firmware. Some Zigbee coordinator hardware support Zigbee 3.0 but might be shipped with an older firmware which does not, in which case may want to upgrade the firmware manually yourself. Some other Zigbee coordinator hardware may not support a firmware that is capable of Zigbee 3.0 at all but can still be fully functional and feature complete for your needs, (this is very common as many if not most Zigbee devices do not yet Zigbee 3.0 or are backwards-compable with a Zigbee profile that is support by your Zigbee coordinator hardware and its firmware). As a general rule, newer Zigbee coordinator hardware released can normally support Zigbee 3.0 firmware and it is up to its manufacturer to make such firmware available for them.

### Compatible zigpy radio libraries

- **Digi XBee** based Zigbee radios via the [zigpy-xbee](https://github.com/zigpy/zigpy-xbee) library for zigpy.
- **dresden elektronik** deCONZ based Zigbee radios via the [zigpy-deconz](https://github.com/zigpy/zigpy-deconz) library for zigpy.
- **Silicon Labs** (EmberZNet) based Zigbee radios using the EZSP protocol via the [bellows](https://github.com/zigpy/bellows) library for zigpy.
- **Texas Instruments** based Zigbee radios with all compatible Z-Stack firmware via the [zigpy-znp](https://github.com/zha-ng/zigpy-znp) library for zigpy.
- **ZiGate** based ZigBee radios via the [zigpy-zigate](https://github.com/zigpy/zigpy-zigate) library for zigpy.

### Legacy or obsolete zigpy radio libraries

- Texas Instruments with Z-Stack legacy firmware via the [zigpy-cc](https://github.com/zigpy/zigpy-cc) library for zigpy.

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
  - https://pypi.org/project/zigpy-cc/
  - https://pypi.org/project/zigpy-deconz/
  - https://pypi.org/project/zigpy-xbee/
  - https://pypi.org/project/zigpy-zigate/
  - https://pypi.org/project/zigpy-znp/
