"""OTA Firmware handling."""

from __future__ import annotations

import logging
import typing

import attr

import zigpy.types as t

LOGGER = logging.getLogger(__name__)


@attr.s(frozen=True)
class ImageKey:
    manufacturer_id = attr.ib(default=None)
    image_type = attr.ib(default=None)


class HWVersion(t.uint16_t):
    @property
    def version(self):
        return self >> 8

    @property
    def revision(self):
        return self & 0x00FF

    def __repr__(self):
        return "<{} version={} revision={}>".format(
            self.__class__.__name__, self.version, self.revision
        )


class HeaderString(str):
    _size = 32

    @classmethod
    def deserialize(cls, data):
        if len(data) < cls._size:
            raise ValueError(f"Data is too short. Should be at least {cls._size}")
        raw = data[: cls._size].split(b"\x00")[0]
        return cls(raw.decode("utf8", errors="replace")), data[cls._size :]

    def serialize(self):
        return self.encode("utf8").ljust(self._size, b"\x00")


class FieldControl(t.bitmap16):
    SECURITY_CREDENTIAL_VERSION_PRESENT = 0b001
    DEVICE_SPECIFIC_FILE_PRESENT = 0b010
    HARDWARE_VERSIONS_PRESENT = 0b100


class OTAImageHeader(t.Struct):
    MAGIC_VALUE = 0x0BEEF11E
    OTA_HEADER = MAGIC_VALUE.to_bytes(4, "little")

    upgrade_file_id: t.uint32_t
    header_version: t.uint16_t
    header_length: t.uint16_t
    field_control: FieldControl
    manufacturer_id: t.uint16_t
    image_type: t.uint16_t
    file_version: t.uint32_t
    stack_version: t.uint16_t
    header_string: HeaderString
    image_size: t.uint32_t

    security_credential_version: t.uint8_t = t.StructField(
        requires=lambda s: s.security_credential_version_present
    )
    upgrade_file_destination: t.EUI64 = t.StructField(
        requires=lambda s: s.device_specific_file
    )
    minimum_hardware_version: HWVersion = t.StructField(
        requires=lambda s: s.hardware_versions_present
    )
    maximum_hardware_version: HWVersion = t.StructField(
        requires=lambda s: s.hardware_versions_present
    )

    @property
    def security_credential_version_present(self) -> bool:
        if self.field_control is None:
            return None
        return bool(
            self.field_control & FieldControl.SECURITY_CREDENTIAL_VERSION_PRESENT
        )

    @property
    def device_specific_file(self) -> bool:
        if self.field_control is None:
            return None
        return bool(self.field_control & FieldControl.DEVICE_SPECIFIC_FILE_PRESENT)

    @property
    def hardware_versions_present(self) -> bool:
        if self.field_control is None:
            return None
        return bool(self.field_control & FieldControl.HARDWARE_VERSIONS_PRESENT)

    @property
    def key(self):
        return ImageKey(self.manufacturer_id, self.image_type)

    @classmethod
    def deserialize(cls, data) -> tuple:
        hdr, data = super().deserialize(data)
        if hdr.upgrade_file_id != cls.MAGIC_VALUE:
            raise ValueError(
                f"Wrong magic number for OTA Image: {hdr.upgrade_file_id!r}"
            )

        return hdr, data


class ElementTagId(t.enum16):
    UPGRADE_IMAGE = 0x0000
    ECDSA_SIGNATURE = 0x0001
    ECDSA_SIGNING_CERTIFICATE = 0x0002
    IMAGE_INTEGRITY_CODE = 0x0003


class LVBytes32(t.LVBytes):
    _prefix_length = 4


class SubElement(t.Struct):
    tag_id: ElementTagId
    data: LVBytes32


class BaseOTAImage:
    """
    Base OTA image container type. Not all images are valid Zigbee OTA images but are
    nonetheless accepted by devices. Only requirement is that the image contains a valid
    OTAImageHeader property and can be serialized/deserialized.
    """

    header: OTAImageHeader

    @classmethod
    def deserialize(cls, data):
        raise NotImplementedError()  # pragma: no cover

    def serialize(self):
        raise NotImplementedError()  # pragma: no cover


class OTAImage(t.Struct, BaseOTAImage):
    """
    Zigbee OTA image according to 11.4 of the ZCL specification.
    """

    header: OTAImageHeader
    subelements: t.List[SubElement]

    @classmethod
    def deserialize(cls, data):
        hdr, data = OTAImageHeader.deserialize(data)
        elements_len = hdr.image_size - hdr.header_length

        if elements_len > len(data):
            raise ValueError(f"Data is too short for {cls}")

        image = cls(header=hdr, subelements=[])
        element_data, data = data[:elements_len], data[elements_len:]

        while element_data:
            element, element_data = SubElement.deserialize(element_data)
            image.subelements.append(element)

        return image, data

    def serialize(self):
        res = super().serialize()
        assert len(res) == self.header.image_size

        return res


@attr.s
class HueSBLOTAImage(BaseOTAImage):
    """
    Unique OTA image format for certain Hue devices. Starts with a valid header but does
    not contain any valid subelements beyond that point.
    """

    SUBELEMENTS_MAGIC = b"\x2A\x00\x01"

    header = attr.ib(default=None)
    data = attr.ib(default=None)

    def serialize(self) -> bytes:
        return self.header.serialize() + self.data

    @classmethod
    def deserialize(cls, data) -> typing.Tuple["HueSBLOTAImage", bytes]:
        header, remaining_data = OTAImageHeader.deserialize(data)
        firmware = remaining_data[: header.image_size - len(header.serialize())]

        if len(data) < header.image_size:
            raise ValueError(
                f"Data is too short to contain image: {len(data)} < {header.image_size}"
            )

        if not firmware.startswith(cls.SUBELEMENTS_MAGIC):
            raise ValueError(
                f"Firmware does not start with expected magic bytes: {firmware[:10]!r}"
            )

        if header.manufacturer_id != 4107:
            raise ValueError(
                f"Only Hue images are expected. Got: {header.manufacturer_id}"
            )

        return cls(header=header, data=firmware), data[header.image_size :]


def parse_ota_image(data: bytes) -> typing.Tuple[BaseOTAImage, bytes]:
    """
    Attempts to extract any known OTA image type from data. Does not validate firmware.
    """

    # IKEA container needs to be unwrapped
    if data.startswith(b"NGIS"):
        if len(data) <= 24:
            raise ValueError(
                f"Data too short to contain IKEA container header: {len(data)}"
            )

        offset = int.from_bytes(data[16:20], "little")
        size = int.from_bytes(data[20:24], "little")

        if len(data) <= offset + size:
            raise ValueError(f"Data too short to be IKEA container: {len(data)}")

        wrapped_data = data[offset : offset + size]
        image, rest = OTAImage.deserialize(wrapped_data)

        if rest:
            LOGGER.warning(
                "Fixing IKEA OTA image with trailing data (%s bytes)",
                size - image.header.image_size,
            )
            image.header.image_size += len(rest)

            # No other structure has been observed
            assert len(image.subelements) == 1
            assert image.subelements[0].tag_id == ElementTagId.UPGRADE_IMAGE

            image.subelements[0].data += rest
            rest = b""

        return image, rest

    try:
        # Hue sbl-ota images start with a Zigbee OTA header but contain no valid
        # subelements after that. Try it first.
        return HueSBLOTAImage.deserialize(data)
    except ValueError:
        return OTAImage.deserialize(data)
