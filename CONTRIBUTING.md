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
  zigpy_xbee: debug
  zigpy_deconz: debug
  zigpy_zigate: debug
  zigpy_cc: debug

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
$ virtualenv -p python3.7 venv
$ source venv/bin/activate
(venv) $ pip install --upgrade pip pre-commit tox
(venv) $ pre-commit install            # install pre-commit as a Git hook
(venv) $ pip install -e '.[testing]'   # installs zigpy+testing deps into the venv in dev mode
```

At this point `black` and `isort` will be run by the pre-commit hook, reformatting your code automatically to match the rest of the project.
 
### Unit testing

Run `pytest -lv`, which will show you a stack trace and all the local variables when something breaks. It is recommended that you install both Python 3.7 and 3.8 so that you can run `tox` from the root project folder and see exactly what the CI system will tell you without having to wait for Travis CI or Coveralls. Code coverage information will be written by tox to `htmlcov/index.html`.

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

Silicon Labs video playlist of ZigBee Concepts: Architecture basics, MAC/PHY, node types, and application profiles
- https://www.youtube.com/playlist?list=PL-awFRrdECXvAs1mN2t2xaI0_bQRh2AqD

## Official release packages available via PyPI

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
