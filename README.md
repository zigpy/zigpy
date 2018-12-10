# zigpy

[![Build Status](https://travis-ci.org/zigpy/zigpy.svg?branch=master)](https://travis-ci.org/zigpy/zigpy)
[![Coverage](https://coveralls.io/repos/github/zigpy/zigpy/badge.svg?branch=master)](https://coveralls.io/github/zigpy/zigpy?branch=master)

**[zigpy](https://github.com/zigpy/zigpy)** is a Python 3 project to implement **[Zigbee Home Automation](https://www.zigbee.org/)** integration. 

zigpy works with separate radio libraries which can each interface with multiple USB and GPIO radio adapters/modules over different native UART serial UART protocols.

Such radio libraries includes **[bellows](https://github.com/zigpy/bellows)** (which communicates with EZSP/EmberZNet based radios) and **[zigpy-xbee](https://github.com/zigpy/zigpy-xbee)** (which communicates with XBee based Zigbee radios). 

There is also experimental radio libraries called **[pyconz](https://github.com/Equidamoid/pyconz/)** and **[zigpy-deconz](https://github.com/damarco/zigpy-deconz)** available for deCONZ serial protocol (for communicating with ConBee and RaspBee USB and GPIO radios from Dresden-Elektronik).
