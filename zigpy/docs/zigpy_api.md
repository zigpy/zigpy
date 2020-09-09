# Document Zigpy how-to

## Concepts

1. Zigpy principle
   1. the stack
   1. the Zigbee radio lib
   1. the Quirk lib

1. The use of asyncio

1. From device to application (receiving request or attaribute value)

1. From application to device ( sending command or responding to request)

1. ApplicationController Listeners

1. Cluster Event Listeners


## Key steps to make it working

1. Create a Persistent object to store all activities and get connected to a radio hardware.

    You need for that to simply import the Radio ControllerApplication
    Then you need to set at least the path to the Database and the path to access the Radio hardware.
    After that just instantiate the ControllerApplication.

    ```python
    import zigpy.config as conf

    # For zigate you will replace radio by zigpy-radio,
    # For Texas Instruments ZNP (Zigbee Network Processors)  you wioll replace radio by zigpy-znp
    from radio import ControllerApplication

    # Config required to connect to a given device
    device_config = {
        conf.CONF_DEVICE_PATH: "/dev/ttyUSB0",
    }

    # Config required to setup zigpy
    zigpy_config = {
        conf.CONF_DATABASE: "/tmp/zigpy.db",
        conf.CONF_DEVICE: device_config
    }

    # This is unnecessary unless you want to autodetect the radio module that will work
    # with a given port
    #does_radio_work = await ControllerApplication.probe(conf.SCHEMA_DEVICE(device_config))

    zigpyApp = await ControllerApplication.new(
        config=ControllerApplication.SCHEMA(zigpy_config),
        auto_form=True,
        start_radio=True,
    )
    ```

1. Create the Application Controller listner :

    ```python3
    listener = MainListener( zigpyApp )
    self.zigpyApp.add_listener(listener)
    ````

1. Create a listner on each Cluster of each Device
    In order to receive the event from each device, you have to create a listner for each cluster of the device

1. For IAS clusters, it needs to have cluster_command()
    Do not understand that one
    <https://github.com/zigpy/zha-device-handlers/issues/469#issuecomment-685153282>

### Define a class MainListener

This is were you will be able to catch most of the events like:

* When a device joined: def device_joined(self, device)
* When a device is initialized (Called at runtime after a device's information has been queried.): device_initialized(self, device, *, new=True)
* When an object send an update (attribute report or attribute read response): attribute_updated(self, cluster, attribute_id, value)

## Configuration SCHEMA

| Parameter                                    | Description                                                     | Mandatory/Optional |
| --------                                     | -----------                                                     | ------------------ |
| CONF_DATABASE = "database_path"              | path to access the persistent database (sqlite3)               | M |
| CONF_DEVICE = "device"                       | Pointing to a device Configuration. Will for instance have at least CONF_DEVICE_PATH | O |
| CONF_DEVICE_PATH = "path"                    | path to access the device controler (can be a serial line, IP ) | M |
| CONF_NWK = "network"                         | ???                                                            | O |
| CONF_NWK_CHANNEL = "channel"                 | I guess this is the channel to be use                           | O |
| CONF_NWK_CHANNELS = "channels"               | I guess this is a possible list of channel to be selected by the controller ? | O |
| CONF_NWK_EXTENDED_PAN_ID = "extended_pan_id" | allow to specify the extended_pam_id (with Zigate it is only possible after an Erase PDM at Network Setup) | O |
| CONF_NWK_PAN_ID = "pan_id"                   | allow to specify the PANID (in Zigate this is not authorized)   | O |
| CONF_NWK_KEY = "key"                         | ???                                                             | O |
| CONF_NWK_KEY_SEQ = "key_sequence_number"     | ???                                                             | O |
| CONF_NWK_TC_ADDRESS = "tc_address"           | ???                                                             | O |
| CONF_NWK_TC_LINK_KEY = "tc_link_key"         | ???                                                            | O |
| CONF_NWK_UPDATE_ID = "update_id"             | ???                                                            | O |
| CONF_OTA = "ota"                             | Pointing to an OTA configuration ????                          | O |
| CONF_OTA_DIR = "otau_directory"              | Where to find the OTA Firmware                                 | O |
| CONF_OTA_IKEA = "ikea_provider"              | ???                                                            | O |
| CONF_OTA_LEDVANCE = "ledvance_provider"      | ???                                                             | O |

## zigpy APIs

### Application

* raw_device_initialized
* device_initialized

* device_removed
* device_joined
* device_left

### Device

* node_descriptor_updated
* device_init_failure
* device_relays_updated

* get_signature
  Provide as a python Dictionnary , an Ep list and associated cluster In and Out. Unfortunatly do not provide more like Model Name, Manufacturer Code, Manufacturer Name ....
  
### Endpoint

* unknown_cluster_message
* member_added
* member_removed

### Group

* group_added
* group_member_added
* group_removed
* group_removed

### ZCL Commands

* cluster_command
* general_command
* attribute_updated
* device_announce
* permit_duration


## How to deal with errors

