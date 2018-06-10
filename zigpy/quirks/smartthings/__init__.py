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
