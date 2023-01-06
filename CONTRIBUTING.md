# Contribute to the zigpy project

This file contains information for end-users, testers and developers on how-to contribute to the zigpy project. It will include guides on how to how to install, use, troubleshoot, debug, code and more.

You can contribute to this project either as an normal end-user, a tester (advanced user contributing constructive issue/bug-reports) or as a developer contributing enhancing code.

## How to contribute as an end-user

If you think that you are having problems due to a bug then please see the section below on reporting issues as a tester, but be aware that reporting issues put higher responsibility on your active involvement on your part as a tester.

Some developers might be also interested in receiving donations in the form of money or hardware such as Zigbee modules and devices, and even if such donations are most often donated with no strings attached it could in many cases help the developers motivation and indirectly improve the development of this project. 

Sometimes it might just be simpler to just donate money earmarked to specifically let a willing developer buy the exact same type Zigbee device that you are having issues with to be able to replicate the issue themselves in order to troubleshoot and hopefully also solve the problem.

Consider submitting a post on GitHub projects issues tracker about willingness to making a donation (please see section below on posing issues).

### How to report issues or bugs as a tester

Issues or bugs are normally first to be submitted upstream to the software/project that is utilizing zigpy and its radio libraries, (like for example Home Assistant), however if and when the issue is determined to be in the zigpy or underlying radio library then you should continue by submitting a detailed issue/bug report via the GitHub projects issues tracker.

Always be sure to first check if there is not already an existing issue posted with the same description before posting a new issue.

- https://help.github.com/en/github/managing-your-work-on-github/creating-an-issue
  - https://guides.github.com/features/issues/
  
### Testing new releases

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

### Troubleshooting 

For troubleshooting with Home Assistant, the general recommendation is to first only enable DEBUG logging for homeassistant.core and homeassistant.components.zha in Home Assistant, then look in the home-assistant.log file and try to get the Home Assistant community to exhausted their combined troubleshooting knowledge of the ZHA component before posting issue directly to a radio library, like example zigpy-deconz or zigpy-xbee.

That is, begin with checking debug logs for Home Assistant core and the ZHA component first, (troubleshooting/debugging from the top down instead of from the bottom up), trying to getting help via Home Assistant community forum before moving on to posting debug logs to zigpy and radio libraries. This is a general suggestion to help filter away common problems and not flood the zigpy-cc developer(s) with too many logs.

Please also try the very latest versions of zigpy and the radio library, (see the section above about "Testing new releases"), and only if you still have the same issues with the latest versions then enable debug logging for zigpy and the radio libraries in Home Assistant in addition to core and zha. Once enabled debug logging for all those libraries in Home Assistant you should try to reproduce the problem and then raise an issue to the zigpy repo (or to a specific radio library) repo with a copy of those logs.

To enable debugging in Home Assistant to get debug logs, either update logger configuration section in configuration.yaml or call logger.set_default_level service with {"level": "debug"} data. Check logger component configuration where you want something this in your configuration.yaml

  logger:
  default: info
  logs:
  asyncio: debug
  homeassistant.core: debug
  homeassistant.components.zha: debug
  zigpy: debug
  bellows: debug
  zigpy_znp: debug
  zigpy_xbee: debug
  zigpy_deconz: debug
  zigpy_zigate: debug

## How to contribute as a developer

If you are looking to make a contribution as a developer to this project we suggest that you follow the steps in these guides:

- https://github.com/firstcontributions/first-contributions/blob/master/README.md
  - https://github.com/firstcontributions/first-contributions/blob/master/github-desktop-tutorial.md

Code changes or additions can then be submitted to this project on GitHub via pull requests:

- https://help.github.com/en/github/collaborating-with-issues-and-pull-requests/about-pull-requests
  - https://help.github.com/en/github/collaborating-with-issues-and-pull-requests/creating-a-pull-request

In general when contributing code to this project it is encouraged that you try to follow the coding standards:

- First [raise issues on GitHub](https://github.com/zigpy/zigpy/issues) before working on an enhancement to provide coordination with other contributors.
- Try to keep each pull request short and only a single PR per enhancement as this makes tracking and reviewing easier.
- All code is formatted with black. The check format script that runs in CI will ensure that code meets this requirement and that it is correctly formatted with black. Instructions for installing black in many editors can be found here: https://github.com/psf/black#editor-integration
- Ideally, you should aim to achieve full coverage of any code changes with tests.
- Recommend read and follow [Google Python Style Guide](https://google.github.io/styleguide/pyguide.html).
- Recommend read and follow [Clifford Programming Style](http://www.clifford.at/style.html).
- Recommend code style use [standard naming conventions for Python](https://medium.com/@dasagrivamanu/python-naming-conventions-the-10-points-you-should-know-149a9aa9f8c7).
- Recommend use [Semantic Versioning](http://semver.org/) for libraries and dependencies if possible.
- Contributions must be your own and you must agree with the license.
- All code for this project should aim to be licensed under [GNU GENERAL PUBLIC LICENSE Version 3](https://raw.githubusercontent.com/zigpy/zigpy/dev/LICENSE).

### Installation for use in a new project

#### Prerequicites

It is recommended that code is formatted with `black` and sorted with `isort`. The check format script that runs in CI will ensure that code meets this requirement and that it is correctly formatted with black. Instructions for installing black in many editors can be found here: https://github.com/psf/black#editor-integration

- https://github.com/psf/black
- https://github.com/PyCQA/isort

#### Setup

To setup a development environment, fork the repository and create a virtual environment:

```shell
$ git clone git@github.com:youruser/zigpy.git
$ cd zigpy
$ virtualenv -p python3.8 venv
$ source venv/bin/activate
(venv) $ pip install --upgrade pip pre-commit tox
(venv) $ pre-commit install            # install pre-commit as a Git hook
(venv) $ pip install -e '.[testing]'   # installs zigpy+testing deps into the venv in dev mode
```

At this point `black` and `isort` will be run by the pre-commit hook, reformatting your code automatically to match the rest of the project.
 
### Unit testing

Run `pytest -lv`, which will show you a stack trace and all the local variables when something breaks. It is recommended that you install Python 3.8, 3.9, 3.10 and 3.11 so that you can run `tox` from the root project folder and see exactly what the CI system will tell you without having to wait for Github Actions or Coveralls. Code coverage information will be written by tox to `htmlcov/index.html`.

### The zigpy API

This section is meant to describe the zigpy API (Application Programming Interface) and how-to to use it.

#### Application 

* raw_device_initialized
* device_initialized
* device_removed
* device_joined
* device_left

#### Device

* node_descriptor_updated
* device_init_failure
* device_relays_updated

#### Endpoint

* unknown_cluster_message
* member_added
* member_removed

#### Group

* group_added
* group_member_added
* group_removed
* group_removed

#### ZCL Commands

* cluster_command
* general_command
* attribute_updated
* device_announce
* permit_duration

### Developer references

Reference collections for different hardware specific Zigbee Stack and related manufacturer documentation.
- https://github.com/zigpy/zigpy/discussions/595

Silicon Labs video playlist of ZigBee Concepts: Architecture basics, MAC/PHY, node types, and application profiles
- https://www.youtube.com/playlist?list=PL-awFRrdECXvAs1mN2t2xaI0_bQRh2AqD

### zigpy wiki and communication channels

- https://github.com/zigpy/zigpy/wiki
- https://github.com/zigpy/zigpy/discussions
- https://github.com/zigpy/zigpy/issues

### Zigbee specifications

- [Zigbee PRO 2017 (R22) Protocol Specification](https://zigbeealliance.org/wp-content/uploads/2019/11/docs-05-3474-21-0csg-zigbee-specification.pdf)
- [Zigbee Cluster Library (R8)](https://zigbeealliance.org/wp-content/uploads/2021/10/07-5123-08-Zigbee-Cluster-Library.pdf)
- [Zigbee Base Device Behavior Specification (V1.0)](https://zigbeealliance.org/wp-content/uploads/zip/zigbee-base-device-behavior-bdb-v1-0.zip)
- [Zigbee Lighting & Occupancy Device Specification (V1.0)](https://zigbeealliance.org/wp-content/uploads/2019/11/docs-15-0014-05-0plo-Lighting-OccupancyDevice-Specification-V1.0.pdf)
- [Zigbee Primer](https://docs.smartthings.com/en/latest/device-type-developers-guide/zigbee-primer.html)

## Official release packages available via PyPI

New packages of tagged versions are also released via the "zigpy" project on PyPI
  - https://pypi.org/project/zigpy/
    - https://pypi.org/project/zigpy/#history
    - https://pypi.org/project/zigpy/#files

Older packages of tagged versions are still available on the "zigpy-homeassistant" project on PyPI
  - https://pypi.org/project/zigpy-homeassistant/

Packages of tagged versions of the radio libraries are released via separate projects on PyPI
- https://pypi.org/project/zigpy/
  - https://pypi.org/project/zha-quirks/
  - https://pypi.org/project/bellows/
  - https://pypi.org/project/zigpy-znp/
  - https://pypi.org/project/zigpy-deconz/
  - https://pypi.org/project/zigpy-xbee/
  - https://pypi.org/project/zigpy-zigate/
  - https://pypi.org/project/zigpy-cc/ (obsolete as replaced by zigpy-znp)

## Related projects

### zigpy-cli (zigpy command line interface)
[zigpy-cli](https://github.com/zigpy/zigpy-cli) is a unified command line interface for zigpy radios. The goal of this project is to allow low-level network management from an intuitive command line interface and to group useful Zigbee tools into a single binary.

### ZHA Device Handlers
ZHA deviation handling in Home Assistant relies on the third-party [ZHA Device Handlers](https://github.com/zigpy/zha-device-handlers) project (also known unders zha-quirks package name on PyPI). Zigbee devices that deviate from or do not fully conform to the standard specifications set by the [Zigbee Alliance](https://www.zigbee.org) may require the development of custom [ZHA Device Handlers](https://github.com/zigpy/zha-device-handlers) (ZHA custom quirks handler implementation) to for all their functions to work properly with the ZHA component in Home Assistant. These ZHA Device Handlers for Home Assistant can thus be used to parse custom messages to and from non-compliant Zigbee devices. The custom quirks implementations for zigpy implemented as ZHA Device Handlers for Home Assistant are a similar concept to that of [Hub-connected Device Handlers for the SmartThings platform](https://docs.smartthings.com/en/latest/device-type-developers-guide/) as well as that of [zigbee-herdsman converters as used by Zigbee2mqtt](https://www.zigbee2mqtt.io/how_tos/how_to_support_new_devices.html), meaning they are each virtual representations of a physical device that expose additional functionality that is not provided out-of-the-box by the existing integration between these platforms.

### ZHA integration component for Home Assistant
[ZHA integration component for Home Assistant](https://www.home-assistant.io/integrations/zha/) is a reference implementation of the zigpy library as integrated into the core of **[Home Assistant](https://www.home-assistant.io)** (a Python based open source home automation software). There are also other GUI and non-GUI projects for Home Assistant's ZHA components which builds on or depends on its features and functions to enhance or improve its user-experience, some of those are listed and linked below.

#### ZHA Toolkit

[ZHA Toolkit](https://github.com/mdeweerd/zha-toolkit) is a custom service for "rare" Zigbee operations using the [ZHA integration component](https://www.home-assistant.io/integrations/zha) in [Home Assistant](https://www.home-assistant.io/). The purpose of ZHA Toolkit and its Home Assistant 'Services' feature, is to provide direct control over low level zigbee commands provided in ZHA or zigpy that are not otherwise available or too limited for some use cases. ZHA Toolkit can also; serve as a framework to do local low level coding (the modules are reloaded on each call), provide access to some higher level commands such as ZNP backup (and restore), make it easier to perform one-time operations where (some) Zigbee knowledge is sufficient and avoiding the need to understand the inner workings of ZHA or Zigpy (methods, quirks, etc).

#### ZHA Custom
[zha_custom](https://github.com/Adminiuga/zha_custom) (unmaintained project) is a custom component package for Home Assistant (with its ZHA component for zigpy integration) that acts as zigpy commands service wrapper, when installed it allows you to enter custom commands via to zigy to example change advanced configuration and settings that are not available in the UI.

#### ZHA Map
[zha-map](https://github.com/zha-ng/zha-map) for Home Assistant's ZHA component can build a Zigbee network topology map.

#### ZHA Network Visualization Card
[zha-network-visualization-card](https://github.com/dmulcahey/zha-network-visualization-card) was a custom Lovelace element for Home Assistant which visualize the Zigbee network for the ZHA component.

#### ZHA Network Card
[zha-network-card](https://github.com/dmulcahey/zha-network-card) was a custom Lovelace card for Home Assistant that displays ZHA component Zigbee network and device information in Home Assistant

#### Zigzag
[Zigzag](https://github.com/Samantha-uk/zigzag-v1) was a custom card/panel for [Home Assistant](https://www.home-assistant.io/) that displays a graphical layout of Zigbee devices and the connections between them. Zigzag could be installed as a panel or a custom card and relies on the data provided by the [zha-map](https://github.com/zha-ng/zha-map) integration component.

#### ZHA Device Exporter
[zha-device-exporter](https://github.com/dmulcahey/zha-device-exporter) is a custom component for Home Assistant to allow the ZHA component to export lists of Zigbee devices.

#### ZHA Custom Radios
[zha-custom-radios](https://github.com/zha-ng/zha-custom-radios) A now obsolete custom component package for Home Assistant (with its ZHA component for zigpy integration) that allows users to test out new zigpy radio libraries and hardware modules before they have officially been integrated into ZHA. This enables developers and testers to test new or updated zigpy radio modules without having to modify the Home Assistant source code.

#### Zigpy Deconz Parser
[zigpy-deconz-parser](https://github.com/zha-ng/zigpy-deconz-parser) allow you to parse Home Assistant's ZHA component debug log using `zigpy-deconz` library if you are using a deCONZ based adapter like ConBee or RaspBee.

### Zigbee for Domoticz Plugin
[Zigbee for Domoticz Plugin](https://www.domoticz.com/wiki/ZigbeeForDomoticz) is and addon for [Domoticz home automation software](https://www.domoticz.com/) with hardware independent Zigbee Coordinator support achieved via dependency on [zigpy], with the exception of Zigate (which it still continues to manage and handle in native mode as this plugin was originally the mature "Zigate plugin" for Domoticz). Domoticz-Zigbee project available at https://github.com/zigbeefordomoticz/Domoticz-Zigbee and wiki at https://zigbeefordomoticz.github.io/wiki/

### Zigbee for Jeedom
[Zigbee plugin for Jeedom](https://doc.jeedom.com/en_US/plugins/automation%20protocol/zigbee/) is and official addon for [Jeedom home automation software]([https://www.domoticz.com/](https://jeedom.com/en/)) which depends on [zigpy] for hardware independent Zigbee Coordinator support. While free and open source licensed the source code for this Zigbee plugin is currently not available for direct download on a public website, as instead independent developers and users of Jeedom can only download the code by installing Jeedom and [purchasing the plugin from their Jeedom online marketplace for around €6](https://market.jeedom.com/index.php?v=d&p=market_display&id=4050) (at least as it stands in May in 2022).

### ZigCoHTTP
[ZigCoHTTP](https://github.com/daniel17903/ZigCoHTTP) (unmaintained and now abandoned) was a stand-alone python application project that creates a ZigBee network using zigpy and bellows. ZigBee devices joining this network can be controlled via a HTTP API. It was developed for a Raspberry Pi using a [Matrix Creator Board](https://www.matrix.one/products/creator) but should also work with other computers with Silicon Labs Zigbee hardware, or with other Zigbee hardware if replace bellows with other radio library for zigpy.
