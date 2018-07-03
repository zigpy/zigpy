import threading

from zigpy.zcl.clusters.measurement import OccupancySensing
from zigpy.quirks import CustomDevice, CustomCluster


class TemperatureHumiditySensor(CustomDevice):
    signature = {
        # <SimpleDescriptor endpoint=1 profile=260 device_type=24321 device_version=1 input_clusters=[0, 3, 25, 65535, 18] output_clusters=[0, 4, 3, 5, 25, 65535, 18]>
        1: {
            'profile_id': 0x0104,
            'device_type': 0x5f01,
            'input_clusters': [0, 3, 25, 65535, 18],
            'output_clusters': [0, 4, 3, 5, 25, 65535, 18],
        },
        # <SimpleDescriptor endpoint=2 profile=260 device_type=24322 device_version=1 input_clusters=[3, 18] output_clusters=[4, 3, 5, 18]>
        2: {
            'profile_id': 0x0104,
            'device_type': 0x5f02,
            'input_clusters': [3, 18],
            'output_clusters': [4, 3, 5, 18],
        },
        # <SimpleDescriptor endpoint=3 profile=260 device_type=24323 device_version=1 input_clusters=[3, 12] output_clusters=[4, 3, 5, 12]>
        3: {
            'profile_id': 0x0104,
            'device_type': 0x5f03,
            'input_clusters': [3, 12],
            'output_clusters': [4, 3, 5, 12],
        },
    }

    replacement = {
        'endpoints': {
            1: {
                'input_clusters': [0x0000, 0x0003, 0x0402, 0x0405],
            }
        },
    }


class AqaraTemperatureHumiditySensor(CustomDevice):
    signature = {
        #  <SimpleDescriptor endpoint=1 profile=260 device_type=24321 device_version=1 input_clusters=[0, 3, 65535, 1026, 1027, 1029] output_clusters=[0, 4, 65535]>
        1: {
            'profile_id': 0x0104,
            'device_type': 0x5f01,
            'input_clusters': [0, 3, 65535, 1026, 1027, 1029],
            'output_clusters': [0, 4, 65535],
        },
    }

    replacement = {
        'endpoints': {
            1: {
                'input_clusters': [0x0000, 0x0003, 0x0402, 0x0403, 0x0405],
            }
        },
    }


class AqaraOpenCloseSensor(CustomDevice):
    signature = {
        #  <SimpleDescriptor endpoint=1 profile=260 device_type=24321 device_version=1 input_clusters=[0, 3, 65535, 6] output_clusters=[0, 4, 65535]>
        1: {
            'profile_id': 0x0104,
            'device_type': 0x5f01,
            'input_clusters': [0, 3, 65535, 6],
            'output_clusters': [0, 4, 65535],
        },
    }

    replacement = {
        'endpoints': {
            1: {
                'device_type': 0x0002,
                'input_clusters': [0x0000, 0x0003],
                'output_clusters': [0x0000, 0x0004, 0x0006],
            }
        },
    }


class AqaraBodySensor(CustomDevice):
    class OccupancyCluster(CustomCluster, OccupancySensing):
        cluster_id = 0x0406

        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self._timer_handle = None

        def _update_attribute(self, attrid, value):
            super()._update_attribute(attrid, value)
            if attrid == 0 and value == 1:
                if self._timer_handle:
                    self._timer_handle.cancel()

                self._timer_handle = threading.Timer(60, self._turn_off)
                self._timer_handle.start()

        def _turn_off(self):
            self._timer_handle = None
            self._update_attribute(0, 0)

    signature = {
        #  <SimpleDescriptor endpoint=1 profile=260 device_type=263 device_version=1 input_clusters=[0, 65535, 1030, 1024, 1280, 1, 3] output_clusters=[0, 25]>
        1: {
            'profile_id': 0x0104,
            'device_type': 0x0107,
            'input_clusters': [0, 65535, 1030, 1024, 1280, 1, 3],
            'output_clusters': [0, 25],
        },
    }

    replacement = {
        'endpoints': {
            1: {
                'input_clusters': [0x0000, 0x0001, 0x0003, 0x0400, OccupancyCluster],
            }
        },
    }


class AqaraWaterSensor(CustomDevice):
    signature = {
        #  <SimpleDescriptor endpoint=1 profile=260 device_type=1026 device_version=1 input_clusters=[0, 3, 1] output_clusters=[25]>
        1: {
            'profile_id': 0x0104,
            'device_type': 0x0402,
            'input_clusters': [0, 3, 1],
            'output_clusters': [25],
        },
    }

    replacement = {
        'endpoints': {
            1: {
                'input_clusters': [0x0000, 0x0003, 0x0001, 0x0500],
            }
        },
    }
