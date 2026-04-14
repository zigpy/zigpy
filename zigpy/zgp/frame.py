"""Green Power Data Frame (GPDF) parsing and construction.

Implements parsing of GP frames as delivered by GP Proxy devices via
GP Notification commands on cluster 0x0021, endpoint 242.

Reference: ZGP specification, section A.1.4 (GPDF format).
"""

from __future__ import annotations

import dataclasses
import struct
from typing import ClassVar

from zigpy.zgp.types import (
    ApplicationID,
    DeviceID,
    FrameType,
    GPDCommandID,
    SecurityKeyType,
    SecurityLevel,
)


@dataclasses.dataclass
class GPCommissioningOptions:
    """Options byte from GP Commissioning command (0xE0) payload.

    Bit layout (Table 53, ZGP spec / Wireshark zbee-nwk-gp dissector):
    - Bit 0: MAC Sequence Number Capability
    - Bit 1: RX On Capability
    - Bit 2: Application Information present
    - Bit 3: reserved
    - Bit 4: PAN ID request
    - Bit 5: GP Security Key request
    - Bit 6: Fixed Location
    - Bit 7: Extended Options field present
    """

    RX_ON_CAPABILITY_BIT: ClassVar[int] = 1
    APP_INFO_PRESENT_BIT: ClassVar[int] = 2
    PAN_ID_REQUEST_BIT: ClassVar[int] = 4
    SECURITY_KEY_REQUEST_BIT: ClassVar[int] = 5
    FIXED_LOCATION_BIT: ClassVar[int] = 6
    EXTENDED_OPTIONS_PRESENT_BIT: ClassVar[int] = 7

    raw: int

    @property
    def mac_seq_num_capability(self) -> bool:
        return bool(self.raw & 0x01)

    @property
    def rx_on_capability(self) -> bool:
        return bool(self.raw & (1 << self.RX_ON_CAPABILITY_BIT))

    @property
    def app_info_present(self) -> bool:
        return bool(self.raw & (1 << self.APP_INFO_PRESENT_BIT))

    @property
    def pan_id_request(self) -> bool:
        return bool(self.raw & (1 << self.PAN_ID_REQUEST_BIT))

    @property
    def security_key_request(self) -> bool:
        return bool(self.raw & (1 << self.SECURITY_KEY_REQUEST_BIT))

    @property
    def fixed_location(self) -> bool:
        return bool(self.raw & (1 << self.FIXED_LOCATION_BIT))


@dataclasses.dataclass
class GPCommissioningExtendedOptions:
    """Extended options byte from GP Commissioning command payload.

    Bit layout (Table 54):
    - Bit 0-1: Security Level Capabilities
    - Bit 2-4: Key Type
    - Bit 5: GPD Key present
    - Bit 6: GPD Key Encrypted
    - Bit 7: GPD Outgoing Counter present
    """

    raw: int

    @property
    def security_level(self) -> SecurityLevel:
        return SecurityLevel(self.raw & 0x03)

    @property
    def key_type(self) -> SecurityKeyType:
        return SecurityKeyType((self.raw >> 2) & 0x07)

    @property
    def key_present(self) -> bool:
        return bool(self.raw & (1 << 5))

    @property
    def key_encrypted(self) -> bool:
        return bool(self.raw & (1 << 6))

    @property
    def outgoing_counter_present(self) -> bool:
        return bool(self.raw & (1 << 7))


@dataclasses.dataclass
class GPCommissioningAppInfo:
    """Application Information byte from GP Commissioning command payload.

    Bit layout (Table 55):
    - Bit 0: Manufacturer ID present
    - Bit 1: Model ID present
    - Bit 2: GPD Commands present
    - Bit 3: Cluster List present
    - Bit 4-7: reserved
    """

    raw: int

    @property
    def manufacturer_id_present(self) -> bool:
        return bool(self.raw & 0x01)

    @property
    def model_id_present(self) -> bool:
        return bool(self.raw & (1 << 1))

    @property
    def gpd_commands_present(self) -> bool:
        return bool(self.raw & (1 << 2))

    @property
    def cluster_list_present(self) -> bool:
        return bool(self.raw & (1 << 3))


@dataclasses.dataclass
class GPCommissioningPayload:
    """Parsed GP Commissioning command (0xE0) payload.

    Contains device capabilities, optional security key, and
    application information that the GPD advertises during commissioning.
    """

    device_id: int
    options: GPCommissioningOptions

    # Extended options (present if options bit 7 set)
    extended_options: GPCommissioningExtendedOptions | None = None

    # Security key (present if extended_options.key_present)
    security_key: bytes | None = None

    # Key MIC (present if extended_options.key_encrypted)
    key_mic: int | None = None

    # Outgoing frame counter (present if extended_options.outgoing_counter_present)
    outgoing_counter: int | None = None

    # Application info fields
    app_info: GPCommissioningAppInfo | None = None
    manufacturer_id: int | None = None
    model_id: int | None = None
    gpd_commands: list[int] = dataclasses.field(default_factory=list)
    server_clusters: list[int] = dataclasses.field(default_factory=list)
    client_clusters: list[int] = dataclasses.field(default_factory=list)

    @classmethod
    def from_bytes(cls, data: bytes) -> GPCommissioningPayload:
        """Parse a GP Commissioning command payload.

        Args:
            data: Raw commissioning payload bytes (after command ID).

        Returns:
            Parsed GPCommissioningPayload.
        """
        if len(data) < 2:
            raise ValueError(
                f"Commissioning payload too short: {len(data)} bytes, need at least 2"
            )

        offset = 0

        # Device ID (1 byte)
        device_id = data[offset]
        offset += 1

        # Options (1 byte)
        options = GPCommissioningOptions(data[offset])
        offset += 1

        extended_options = None
        security_key = None
        key_mic = None
        outgoing_counter = None

        # Extended options (1 byte, conditional)
        has_extended = bool(data[offset - 1] & 0x80)  # bit 7 of options
        if has_extended and offset < len(data):
            extended_options = GPCommissioningExtendedOptions(data[offset])
            offset += 1

            # Security key (16 bytes, conditional)
            if extended_options.key_present and offset + 16 <= len(data):
                security_key = bytes(data[offset : offset + 16])
                offset += 16

                # Key MIC (4 bytes, conditional on key_encrypted)
                if extended_options.key_encrypted and offset + 4 <= len(data):
                    (key_mic,) = struct.unpack_from("<I", data, offset)
                    offset += 4

            # Outgoing counter (4 bytes, conditional)
            if extended_options.outgoing_counter_present and offset + 4 <= len(data):
                (outgoing_counter,) = struct.unpack_from("<I", data, offset)
                offset += 4

        # Application information (conditional on options bit 3)
        app_info = None
        manufacturer_id = None
        model_id = None
        gpd_commands: list[int] = []
        server_clusters: list[int] = []
        client_clusters: list[int] = []

        if options.app_info_present and offset < len(data):
            app_info = GPCommissioningAppInfo(data[offset])
            offset += 1

            if app_info.manufacturer_id_present and offset + 2 <= len(data):
                (manufacturer_id,) = struct.unpack_from("<H", data, offset)
                offset += 2

            if app_info.model_id_present and offset + 2 <= len(data):
                (model_id,) = struct.unpack_from("<H", data, offset)
                offset += 2

            if app_info.gpd_commands_present and offset < len(data):
                num_commands = data[offset]
                offset += 1
                gpd_commands = list(data[offset : offset + num_commands])
                offset += num_commands

            if app_info.cluster_list_present and offset < len(data):
                length_byte = data[offset]
                offset += 1
                num_server = length_byte & 0x0F
                num_client = (length_byte >> 4) & 0x0F

                for _ in range(num_server):
                    if offset + 2 <= len(data):
                        (cluster_id,) = struct.unpack_from("<H", data, offset)
                        server_clusters.append(cluster_id)
                        offset += 2

                for _ in range(num_client):
                    if offset + 2 <= len(data):
                        (cluster_id,) = struct.unpack_from("<H", data, offset)
                        client_clusters.append(cluster_id)
                        offset += 2

        return cls(
            device_id=device_id,
            options=options,
            extended_options=extended_options,
            security_key=security_key,
            key_mic=key_mic,
            outgoing_counter=outgoing_counter,
            app_info=app_info,
            manufacturer_id=manufacturer_id,
            model_id=model_id,
            gpd_commands=gpd_commands,
            server_clusters=server_clusters,
            client_clusters=client_clusters,
        )

    def to_bytes(self) -> bytes:
        """Serialize the commissioning payload to bytes."""
        result = bytearray()

        # Device ID
        result.append(self.device_id & 0xFF)

        # Options
        result.append(self.options.raw & 0xFF)

        # Extended options
        if self.extended_options is not None:
            result.append(self.extended_options.raw & 0xFF)

            if self.extended_options.key_present and self.security_key is not None:
                result.extend(self.security_key)

                if self.extended_options.key_encrypted and self.key_mic is not None:
                    result.extend(struct.pack("<I", self.key_mic))

            if (
                self.extended_options.outgoing_counter_present
                and self.outgoing_counter is not None
            ):
                result.extend(struct.pack("<I", self.outgoing_counter))

        # Application info
        if self.app_info is not None:
            result.append(self.app_info.raw & 0xFF)

            if self.app_info.manufacturer_id_present and self.manufacturer_id is not None:
                result.extend(struct.pack("<H", self.manufacturer_id))

            if self.app_info.model_id_present and self.model_id is not None:
                result.extend(struct.pack("<H", self.model_id))

            if self.app_info.gpd_commands_present:
                result.append(len(self.gpd_commands))
                result.extend(self.gpd_commands)

            if self.app_info.cluster_list_present:
                length_byte = (len(self.server_clusters) & 0x0F) | (
                    (len(self.client_clusters) & 0x0F) << 4
                )
                result.append(length_byte)
                for cluster_id in self.server_clusters:
                    result.extend(struct.pack("<H", cluster_id))
                for cluster_id in self.client_clusters:
                    result.extend(struct.pack("<H", cluster_id))

        return bytes(result)


@dataclasses.dataclass
class GPChannelRequestPayload:
    """Parsed GP Channel Request command (0xE3) payload.

    Contains the channel the GPD wants to operate on.
    """

    next_channel: int
    second_next_channel: int

    @classmethod
    def from_bytes(cls, data: bytes) -> GPChannelRequestPayload:
        """Parse channel request payload (1 byte)."""
        if len(data) < 1:
            raise ValueError("Channel request payload requires at least 1 byte")
        byte = data[0]
        return cls(
            next_channel=(byte & 0x0F) + 11,  # Channel offset from 11
            second_next_channel=((byte >> 4) & 0x0F) + 11,
        )
