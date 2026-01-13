"""OTA Firmware handling."""

from __future__ import annotations

import hashlib
import logging
from typing import Self

import attrs

import zigpy.types as t

LOGGER = logging.getLogger(__name__)


def format_bytes(data: bytes) -> str:
    """Format bytes for representation."""
    if len(data) > 32:
        return f"{len(data)}:{data[:25].hex()}...{data[-7:].hex()}"
    else:
        return f"{len(data)}:{data.hex()}"


class HWVersion(t.uint16_t):
    @property
    def version(self):
        return self >> 8

    @property
    def revision(self):
        return self & 0x00FF

    def __repr__(self):
        return f"<{self.__class__.__name__} version={self.version} revision={self.revision}>"


class HeaderString(bytes):
    _size = 32

    def __new__(cls, value: str | bytes):
        if isinstance(value, str):
            value = value.encode("utf-8").ljust(cls._size, b"\x00")

        if len(value) != cls._size:
            raise ValueError(f"HeaderString must be exactly {cls._size} bytes long")

        return super().__new__(cls, value)

    @classmethod
    def deserialize(cls, data: bytes) -> tuple[HeaderString, bytes]:
        if len(data) < cls._size:
            raise ValueError(f"Data is too short. Should be at least {cls._size}")

        raw = data[: cls._size]
        return cls(raw), data[cls._size :]

    def serialize(self) -> bytes:
        return self

    def __str__(self) -> str:
        return repr(self)

    def __repr__(self) -> str:
        try:
            text = repr(self.rstrip(b"\x00").decode("utf-8"))
        except UnicodeDecodeError:
            text = f"{len(self)}:{self.hex()}"

        return f"<{text}>"


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
        requires=lambda s: s.field_control is not None
        and FieldControl.SECURITY_CREDENTIAL_VERSION_PRESENT in s.field_control
    )
    upgrade_file_destination: t.EUI64 = t.StructField(
        requires=lambda s: s.field_control is not None
        and FieldControl.DEVICE_SPECIFIC_FILE_PRESENT in s.field_control
    )
    minimum_hardware_version: HWVersion = t.StructField(
        requires=lambda s: s.field_control is not None
        and FieldControl.HARDWARE_VERSIONS_PRESENT in s.field_control
    )
    maximum_hardware_version: HWVersion = t.StructField(
        requires=lambda s: s.field_control is not None
        and FieldControl.HARDWARE_VERSIONS_PRESENT in s.field_control
    )

    @property
    def security_credential_version_present(self) -> bool | None:
        if self.field_control is None:
            return None
        return bool(
            self.field_control & FieldControl.SECURITY_CREDENTIAL_VERSION_PRESENT
        )

    @property
    def device_specific_file(self) -> bool | None:
        if self.field_control is None:
            return None
        return bool(self.field_control & FieldControl.DEVICE_SPECIFIC_FILE_PRESENT)

    @property
    def hardware_versions_present(self) -> bool | None:
        if self.field_control is None:
            return None
        return bool(self.field_control & FieldControl.HARDWARE_VERSIONS_PRESENT)

    @classmethod
    def deserialize(cls, data: bytes) -> tuple[OTAImageHeader, bytes]:
        hdr, data = super().deserialize(data)
        if hdr.upgrade_file_id != cls.MAGIC_VALUE:
            raise ValueError(
                f"Wrong magic number for OTA Image: {hdr.upgrade_file_id!r}"
            )

        return hdr, data


class ElementTagId(t.enum16):
    UPGRADE_IMAGE = 0x0000
    ECDSA_SIGNATURE_CRYPTO_SUITE_1 = 0x0001
    ECDSA_SIGNING_CERTIFICATE_CRYPTO_SUITE_1 = 0x0002
    IMAGE_INTEGRITY_CODE = 0x0003
    PICTURE_DATA = 0x0004
    ECDSA_SIGNATURE_CRYPTO_SUITE_2 = 0x0005
    ECDSA_SIGNING_CERTIFICATE_CRYPTO_SUITE_2 = 0x0006


class LVBytes32(t.LVBytes):
    _prefix_length = 4


class SubElement(t.Struct):
    tag_id: ElementTagId
    data: LVBytes32

    def __repr__(self) -> str:
        return (
            f"<{self.__class__.__name__}(tag_id={self.tag_id!r},"
            f" data=[{format_bytes(self.data)}])>"
        )


class BaseOTAImage:
    """Base OTA image container type. Not all images are valid Zigbee OTA images but are
    nonetheless accepted by devices. Only requirement is that the image contains a valid
    OTAImageHeader property and can be serialized/deserialized.
    """

    header: OTAImageHeader

    @classmethod
    def deserialize(cls, data) -> tuple[BaseOTAImage, bytes]:
        raise NotImplementedError  # pragma: no cover

    def serialize(self):
        raise NotImplementedError  # pragma: no cover


class OTAImage(t.Struct, BaseOTAImage):
    """Zigbee OTA image according to 11.4 of the ZCL specification."""

    header: OTAImageHeader
    subelements: t.List[SubElement]

    @classmethod
    def deserialize(cls, data: bytes) -> tuple[OTAImage, bytes]:
        hdr, data = OTAImageHeader.deserialize(data)
        elements_len = hdr.image_size - hdr.header_length

        if elements_len > len(data):
            raise ValueError(
                f"Data is too short for {cls}: expected at least {hdr.image_size} -"
                f" {hdr.header_length} = {elements_len} bytes, got {len(data)}"
            )

        image = cls(header=hdr, subelements=[])
        element_data, data = data[:elements_len], data[elements_len:]

        while element_data:
            element, element_data = SubElement.deserialize(element_data)
            image.subelements.append(element)

        return image, data

    def serialize(self) -> bytes:
        res = super().serialize()

        if self.header.image_size != len(res):
            raise ValueError(
                f"Image size in header ({self.header.image_size} bytes)"
                f" does not match actual image size ({len(res)} bytes)"
            )

        return res


@attrs.define(kw_only=True)
class HueSBLOTAImage(BaseOTAImage, t.BaseDataclassMixin):
    """Unique OTA image format for certain Hue devices. Starts with a valid header but does
    not contain any valid subelements beyond that point.
    """

    SUBELEMENTS_MAGIC = b"\x2a\x00\x01"

    header: OTAImageHeader = None
    data: bytes = None

    def serialize(self) -> bytes:
        return self.header.serialize() + self.data

    @classmethod
    def deserialize(cls, data: bytes) -> tuple[Self, bytes]:
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


@attrs.define(kw_only=True, repr=False)
class TelinkEncryptedSubElement(t.BaseDataclassMixin):
    TELINK_ENCRYPTED_TAG_ID = ElementTagId(0xF000)

    tag_id: ElementTagId = attrs.field(default=None, converter=ElementTagId)
    tag_info: t.uint16_t = None
    data: bytes = None

    def __repr__(self) -> str:
        return (
            f"<{self.__class__.__name__}(tag_id={self.tag_id!r}"
            f", tag_info={self.tag_info!r}, data=[{format_bytes(self.data)}])>"
        )

    @classmethod
    def deserialize(cls, data: bytes) -> tuple[Self, bytes]:
        if len(data) < 8:
            raise ValueError("Data too short to contain encrypted Telink subelement")

        tag_id, data = ElementTagId.deserialize(data)

        if tag_id != cls.TELINK_ENCRYPTED_TAG_ID:
            raise ValueError(
                f"Not a Telink encrypted subelement: unexpected tag ID {tag_id!r}"
            )

        tag_length, data = t.uint32_t.deserialize(data)

        if len(data) < tag_length + 2:
            raise ValueError(
                f"Data too short to contain Telink subelement data: expected"
                f" {tag_length + 2} bytes, got {len(data)}"
            )

        tag_info, data = t.uint16_t.deserialize(data)
        tag_data, data = data[:tag_length], data[tag_length:]

        return cls(tag_id=tag_id, tag_info=tag_info, data=tag_data), data

    def serialize(self) -> bytes:
        result = ElementTagId(self.tag_id).serialize()
        result += t.uint32_t(len(self.data)).serialize()
        result += t.uint16_t(self.tag_info).serialize()
        result += self.data

        return result


@attrs.define(kw_only=True)
class TelinkOTAImage(BaseOTAImage, t.BaseDataclassMixin):
    """Telink OTA image. Includes a proprietary "tag info" after the tag length."""

    header: OTAImageHeader = None
    subelements: t.List[SubElement | TelinkEncryptedSubElement] = None

    @classmethod
    def deserialize(cls, data: bytes) -> tuple[Self, bytes]:
        hdr, data = OTAImageHeader.deserialize(data)
        elements_len = hdr.image_size - hdr.header_length

        if elements_len > len(data):
            raise ValueError(
                f"Data is too short for {cls}: expected at least {hdr.image_size} -"
                f" {hdr.header_length} = {elements_len} bytes, got {len(data)}"
            )

        image = cls(header=hdr, subelements=[])
        element_data, data = data[:elements_len], data[elements_len:]

        while element_data:
            tag_id, _ = ElementTagId.deserialize(element_data)

            if tag_id == TelinkEncryptedSubElement.TELINK_ENCRYPTED_TAG_ID:
                element, element_data = TelinkEncryptedSubElement.deserialize(
                    element_data
                )
            else:
                element, element_data = SubElement.deserialize(element_data)

            image.subelements.append(element)

        return image, data

    def serialize(self) -> bytes:
        res = self.header.serialize()

        for subelement in self.subelements:
            res += subelement.serialize()

        if self.header.image_size != len(res):
            raise ValueError(
                f"Image size in header ({self.header.image_size} bytes)"
                f" does not match actual image size ({len(res)} bytes)"
            )

        return res


def parse_ota_image(data: bytes) -> tuple[BaseOTAImage, bytes]:
    """Attempts to extract any known OTA image type from data. Does not validate firmware."""

    if len(data) > 4 and int.from_bytes(data[0:4], "little") + 21 == len(data):
        # Legrand OTA images are prefixed with their unwrapped size and include a 1 + 16
        # byte suffix
        return OTAImage.deserialize(data[4:-17])
    elif (
        len(data) > 152
        # Avoid the SHA512 hash until we're pretty sure this is a Third Reality image
        and int.from_bytes(data[68:72], "little") + 64 == len(data)
        and data.startswith(hashlib.sha512(data[64:]).digest())
    ):
        # Third Reality OTA images contain a 152 byte header with multiple SHA512 hashes
        # and the image length
        return OTAImage.deserialize(data[152:])
    elif data.startswith(b"NGIS"):
        # IKEA container needs to be unwrapped
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
        pass

    try:
        # Otherwise, try parsing as a spec-compliant OTA image
        return OTAImage.deserialize(data)
    except ValueError:
        pass

    # Finally, try the Telink proprietary format
    return TelinkOTAImage.deserialize(data)
