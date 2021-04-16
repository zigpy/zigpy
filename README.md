# zigpy

[![Build](https://github.com/zigpy/zigpy/workflows/CI/badge.svg?branch=dev)](https://github.com/zigpy/zigpy/workflows/CI/badge.svg?branch=dev)
[![Coverage](https://coveralls.io/repos/github/zigpy/zigpy/badge.svg?branch=dev)](https://coveralls.io/github/zigpy/zigpy?branch=dev)

**[zigpy](https://github.com/zigpy/zigpy)** is **[Zigbee protocol stack](https://en.wikipedia.org/wiki/Zigbee)** integration project to implement the **[Zigbee Home Automation](https://www.zigbee.org/)** standard as a Python 3 library. 

Zigbee Home Automation integration with zigpy allows you to connect one of many off-the-shelf Zigbee adapters using one of the available Zigbee radio library modules compatible with zigpy to control Zigbee based devices. There is currently support for controlling Zigbee device types such as binary sensors (e.g., motion and door sensors), sensors (e.g., temperature sensors), lightbulbs, switches, and fans.

Zigbee coordinator hardware from many different hardware manufacturers are supported via radio libraries which translate their proprietary communication protocol into a common API which is shared among all radio libraries for zigpy. If some Zigbee coordinator hardware for other manufacturers is not supported by yet zigpy it is possible for any independent developer to step-up and develop a new radio library for zigpy which translates its proprietary communication protocol into the common API that zigpy can understand.

zigpy contains common code implementing Zigbee ZCL, ZDO and application state management which is being used by various radio libraries implementing the actual interface with the radio modules from different manufacturers. The separate radio libraries interface with radio hardware adapters/modules over USB and GPIO using different native UART serial protocols.

Reference implementation of the zigpy library exist in **[Home Assistant](https://www.home-assistant.io)** (Python based open source home automation software) as part of its **[ZHA integration component](https://www.home-assistant.io/integrations/zha/)**.

### Zigbee device OTA updates

zigpy have code to automatically download and perform OTA (Over-The-Air) firmware updates of Zigbee devices if the OTA firmware image provider source URL for updates is known. The OTA update directory is optional and it can also be used for any offline firmware files that you provide yourself.

Online OTA providers for firmware updates are currently only available for IKEA and LEDVANCE devices. OTA updates for device of other manufactures could possible also be supported by zigpy in the future, if these manufacturers publish their device OTA firmware images publicly.

## How to install and test, report bugs, or contribute to this project

For specific instructions on how-to install and test zigpy or contribute bug-reports and code to this project please see the guidelines in the CONTRIBUTING.md file:

- [Guidelines in CONTRIBUTING.md](./CONTRIBUTING.md)

This CONTRIBUTING.md file will contain information about using zigpy, testing new releases, troubleshooting and bug-reporting as, as well as library + code instructions for developers and more.

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
  - https://pypi.org/project/zigpy-deconz/
  - https://pypi.org/project/zigpy-cc/
  - https://pypi.org/project/zigpy-xbee/
  - https://pypi.org/project/zigpy-zigate/
  - https://pypi.org/project/zigpy-znp/

## Related projects

### ZHA Device Handlers
ZHA deviation handling in Home Assistant relies on the third-party [ZHA Device Handlers](https://github.com/zigpy/zha-device-handlers) project. Zigbee devices that deviate from or do not fully conform to the standard specifications set by the [Zigbee Alliance](https://www.zigbee.org) may require the development of custom [ZHA Device Handlers](https://github.com/zigpy/zha-device-handlers) (ZHA custom quirks handler implementation) to for all their functions to work properly with the ZHA component in Home Assistant. These ZHA Device Handlers for Home Assistant can thus be used to parse custom messages to and from non-compliant Zigbee devices. The custom quirks implementations for zigpy implemented as ZHA Device Handlers for Home Assistant are a similar concept to that of [Hub-connected Device Handlers for the SmartThings platform](https://docs.smartthings.com/en/latest/device-type-developers-guide/) as well as that of [zigbee-herdsman converters as used by Zigbee2mqtt](https://www.zigbee2mqtt.io/how_tos/how_to_support_new_devices.html), meaning they are each virtual representations of a physical device that expose additional functionality that is not provided out-of-the-box by the existing integration between these platforms.

### ZHA integration component for Home Assistant
[ZHA integration component for Home Assistant](https://www.home-assistant.io/integrations/zha/) is a reference implementation of the zigpy library as integrated into the core of **[Home Assistant](https://www.home-assistant.io)** (a Python based open source home automation software). There are also other GUI and non-GUI projects for Home Assistant's ZHA components which builds on or depends on its features and functions to enhance or improve its user-experience, some of those are listed and linked below.

#### ZHA Custom
[zha_custom](https://github.com/Adminiuga/zha_custom) is a custom component package for Home Assistant (with its ZHA component for zigpy integration) that acts as zigpy commands service wrapper, when installed it allows you to enter custom commands via to zigy to example change advanced configuration and settings that are not available in the UI.

#### ZHA Map
[zha-map](https://github.com/zha-ng/zha-map) for Home Assistant's ZHA component can build a Zigbee network topology map.

#### ZHA Network Visualization Card
[zha-network-visualization-card](https://github.com/dmulcahey/zha-network-visualization-card) is a custom Lovelace element for Home Assistant which visualize the Zigbee network for the ZHA component.

#### ZHA Network Card
[zha-network-card](https://github.com/dmulcahey/zha-network-card) is a custom Lovelace card for Home Assistant that displays ZHA component Zigbee network and device information in Home Assistant

#### Zigzag
[Zigzag](https://github.com/Samantha-uk/zigzag-v1) is a custom card/panel for [Home Assistant](https://www.home-assistant.io/) that displays a graphical layout of Zigbee devices and the connections between them. Zigzag can be installed as a panel or a custom card and relies on the data provided by the [zha-map](https://github.com/zha-ng/zha-map) integration component.

#### ZHA Device Exporter
[zha-device-exporter](https://github.com/dmulcahey/zha-device-exporter) is a custom component for Home Assistant to allow the ZHA component to export lists of Zigbee devices.

#### ZHA Custom Radios
[zha-custom-radios](https://github.com/zha-ng/zha-custom-radios) A now obsolete custom component package for Home Assistant (with its ZHA component for zigpy integration) that allows users to test out new zigpy radio libraries and hardware modules before they have officially been integrated into ZHA. This enables developers and testers to test new or updated zigpy radio modules without having to modify the Home Assistant source code.

#### Zigpy Deconz Parser
[zigpy-deconz-parser](https://github.com/zha-ng/zigpy-deconz-parser) allow you to parse Home Assistant's ZHA component debug log using `zigpy-deconz` library if you are using a deCONZ based adapter like ConBee or RaspBee.

### ZigCoHTTP
[ZigCoHTTP](https://github.com/daniel17903/ZigCoHTTP) is a stand-alone python application project that creates a ZigBee network using zigpy and bellows. ZigBee devices joining this network can be controlled via a HTTP API. It was developed for a Raspberry Pi using a [Matrix Creator Board](https://www.matrix.one/products/creator) but should also work with other computers with Silicon Labs Zigbee hardware, or with other Zigbee hardware if replace bellows with other radio library for zigpy.
