from zigpy.quirks import CustomDevice


class KeenTemperatureHumiditySensor(CustomDevice):
    signature = {
        "endpoints": {
            # <SimpleDescriptor endpoint=1 profile=260 device_type=770 device_version=1
            # input_clusters=[0, 3, 1, 32]
            # output_clusters=[0, 4, 3, 5, 25, 1026, 1029, 1027, 32]>
            1: {
                "profile_id": 0x0104,
                "device_type": 0x0302,
                "input_clusters": [0, 3, 1, 32],
                "output_clusters": [0, 4, 3, 5, 25, 1026, 1029, 1027, 32],
            }
        },
        "manufacturer": "Keen Home Inc",
    }

    replacement = {
        "endpoints": {
            1: {
                "input_clusters": [0x0000, 0x0003, 0x0402, 0x0405],
                "output_clusters": [0x0403],
            }
        }
    }
