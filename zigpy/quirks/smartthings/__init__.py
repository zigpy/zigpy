import zigpy.types as t
from zigpy.quirks import CustomDevice, CustomCluster


class SmartthingsRelativeHumidityCluster(CustomCluster):
    cluster_id = 0xfc45
    name = 'Smartthings Relative Humidity Measurement'
    ep_attribute = 'humidity'
    attributes = {
        # Relative Humidity Measurement Information
        0x0000: ('measured_value', t.int16s),
    }
    server_commands = {}
    client_commands = {}


class SmartthingsTemperatureHumiditySensor(CustomDevice):
    signature = {
        # <SimpleDescriptor endpoint=1 profile=260 device_type=770 device_version=0 input_clusters=[0, 1, 3, 32, 1026, 2821, 64581] output_clusters=[3, 25]>
        1: {
            'profile_id': 0x0104,
            'device_type': 0x0302,
            'input_clusters': [0, 1, 3, 32, 1026, 2821, 64581],
            'output_clusters': [3, 25],
        }
    }

    replacement = {
        'endpoints': {
            1: {
                'input_clusters': [0x0000, 0x0001, 0x0003, 0x0402, 0x0B05,
                                   SmartthingsRelativeHumidityCluster],
            }
        }
    }


class SmartThingsAccelCluster(CustomCluster):
    cluster_id = 0xfc02
    name = "Smartthings Accelerometer"
    ep_attribute = 'accelerometer'
    attributes = {
        0x0000: ('motion_threshold_multiplier', t.uint8_t),
        0x0002: ('motion_threshold', t.uint16_t),
        0x0010: ('acceleration', t.bitmap8),  # acceleration detected
        0x0012: ('x_axis', t.int16s),
        0x0013: ('y_axis', t.int16s),
        0x0014: ('z_axis', t.int16s),
    }

    client_commands = {}
    server_commands = {}


class SmartthingsMultiPurposeSensor(CustomDevice):
    signature = {
        # <SimpleDescriptor endpoint=1 profile=260 device_type=1026
        # device_version=0 input_clusters=[0, 1, 3, 32, 1026, 1280, 64514]
        # output_clusters=[3, 25]>
        1: {
            'profile_id': 0x0104,
            'device_type': 0x0402,
            'input_clusters': [
                0, 1, 3, 32, 1026, 1280, SmartThingsAccelCluster.cluster_id
            ],
            'output_clusters': [3, 25],
        }
    }

    replacement = {
        'endpoints': {
            1: {
                'input_clusters': [0x0000, 0x0001, 0x0003, 0x0020, 0x0402,
                                   0x0500, SmartThingsAccelCluster],
                'output_clusters': [0x0003, 0x0019]
            }
        }
    }
