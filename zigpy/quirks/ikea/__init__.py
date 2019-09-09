from zigpy.quirks import CustomDevice


class TradfriPlug(CustomDevice):
    signature = {
        "endpoints": {
            # <SimpleDescriptor endpoint=1 profile=260 device_type=266
            # device_version=0
            # input_clusters=[0, 3, 4, 5, 6, 8, 64636] output_clusters=[5, 25, 32]>
            1: {
                "profile_id": 0x0104,
                "device_type": 0x010A,
                "input_clusters": [0, 3, 4, 5, 6, 8, 64636],
                "output_clusters": [5, 25, 32],
            },
            # <SimpleDescriptor endpoint=2 profile=49246 device_type=16
            # device_version=0
            # input_clusters=[4096] output_clusters=[4096]>
            2: {
                "profile_id": 0xC05E,
                "device_type": 0x0010,
                "input_clusters": [4096],
                "output_clusters": [4096],
            },
            # <SimpleDescriptor endpoint=242 profile=41440 device_type=97
            # device_version=0
            # input_clusters=[33] output_clusters=[33]>
            242: {
                "profile_id": 0xA1E0,
                "device_type": 0x0061,
                "input_clusters": [33],
                "output_clusters": [33],
            },
        },
        "manufacturer": "IKEA of Sweden",
    }

    replacement = {
        "endpoints": {
            1: {
                "profile_id": 0x0104,
                "device_type": 0x010A,
                "input_clusters": [0, 3, 4, 5, 6, 64636],
                "output_clusters": [5, 25, 32],
            }
        }
    }
