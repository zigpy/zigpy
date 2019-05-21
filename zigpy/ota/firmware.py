"""OTA Firmware handling."""
import attr

import zigpy.types as t


@attr.s(frozen=True)
class FirmwareKey:
    manufacturer_id = attr.ib(default=None)
    image_type = attr.ib(default=None)


@attr.s
class Firmware:
    key = attr.ib(default=FirmwareKey)
    version = attr.ib(default=t.uint32_t(0))
    size = attr.ib(default=t.uint32_t(0))
    url = attr.ib(default=None)
    data = attr.ib(default=None)

    def upgradeable(self, manufacturer_id, img_type, ver, hw_ver=None) -> bool:
        """Check if it should upgrade"""
        key = FirmwareKey(manufacturer_id, img_type)
        # ToDo check for hardware version
        return all((self.key == key, self.version > ver, self.is_valid))

    @property
    def is_valid(self):
        """Return True if firmware validation passes."""
        # ToDo proper validation
        return self.data is not None
