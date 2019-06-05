"""OTA Firmware handling."""
import attr
import enum

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


class HWVersion(t.uint16_t):
    @property
    def version(self):
        return self >> 8

    @property
    def revision(self):
        return self & 0x00ff

    def __repr__(self):
        return "<{} version={} revision={}>".format(self.__class__.__name__,
                                                    self.version,
                                                    self.revision)


class HeaderString(str):
    _size = 32

    @classmethod
    def deserialize(cls, data):
        if len(data) < cls._size:
            raise ValueError("Data is too short. Should be at least %s",
                             cls._size)
        raw = data[:cls._size].split(b'\x00')[0]
        return cls(raw.decode('utf8', errors='replace')), data[cls._size:]

    def serialize(self):
        return self.encode('utf8').ljust(self._size, b'\x00')


class OTAImageHeader(t.Struct):
    MAGIC_VALUE = 0x0beef11e
    _fields = [
        ('upgrade_file_id', t.uint32_t),
        ('header_version', t.uint16_t),
        ('header_length', t.uint16_t),
        ('field_control', t.uint16_t),
        ('manufacturer_id', t.uint16_t),
        ('image_type', t.uint16_t),
        ('file_version', t.uint32_t),
        ('stack_version', t.uint16_t),
        ('header_string', HeaderString),
        ('image_size', t.uint32_t)
    ]

    @property
    def security_credential_version_present(self) -> bool:
        if self.field_control is None:
            return None
        return bool(self.field_control & 0x01)

    @property
    def device_specific_file(self) -> bool:
        if self.field_control is None:
            return None
        return bool(self.field_control & 0x02)

    @property
    def hardware_versions_present(self) -> bool:
        if self.field_control is None:
            return None
        return bool(self.field_control & 0x04)

    @classmethod
    def deserialize(cls, data) -> tuple:
        hdr, data = super().deserialize(data)
        if hdr.upgrade_file_id != cls.MAGIC_VALUE:
            raise ValueError("Wrong magic number for OTA Image: %s" %
                             (hdr.upgrade_file_id, ))

        if hdr.security_credential_version_present:
            hdr.security_credential_version, data = t.uint8_t.deserialize(data)
        else:
            hdr.security_credential_version = None

        if hdr.device_specific_file:
            hdr.upgrade_file_destination, data = t.EUI64.deserialize(data)
        else:
            hdr.upgrade_file_destination = None

        if hdr.hardware_versions_present:
            hdr.minimum_hardware_version, data = HWVersion.deserialize(data)
            hdr.maximum_hardware_version, data = HWVersion.deserialize(data)
        else:
            hdr.minimum_hardware_version = None
            hdr.maximum_hardware_version = None

        return hdr, data

    def serialize(self) -> bytes:
        data = super().serialize()
        if self.security_credential_version_present:
            data += self.security_credential_version.serialize()
        if self.device_specific_file:
            data += self.upgrade_file_destination.serialize()
        if self.hardware_versions_present:
            data += self.minimum_hardware_version.serialize()
            data += self.maximum_hardware_version.serialize()
        return data


class ElementTagId(t.uint16_t, enum.Enum):
    UPGRADE_IMAGE = 0x0000
    ECDSA_SIGNATURE = 0x0001
    ECDSA_SIGNING_CERTIFICATE = 0x0002
    IMAGE_INTEGRITY_CODE = 0x0003


class SubElement(bytes):
    @property
    def data(self):
        return self

    @property
    def length(self):
        return t.uint32_t(len(self))

    @classmethod
    def deserialize(cls, data) -> tuple:
        if len(data) < 6:
            raise ValueError("Data is too short for {}".format(cls.__name__))

        try:
            tag_id, rest = ElementTagId.deserialize(data)
        except ValueError:
            tag_id, rest = t.uint16_t.deserialize(data)

        length, rest = t.uint32_t.deserialize(rest)
        if length > len(rest):
            raise ValueError("Data is too short for {}".format(cls.__name__))

        r = cls(rest[:length])
        r.tag_id = tag_id
        return r, rest[length:]

    def serialize(self):
        return self.tag_id.serialize() + self.length.serialize() + self
