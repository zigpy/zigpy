from typing import Iterable, Tuple, Union

from . import basic
from .struct import Struct


class BroadcastAddress(basic.enum16):
    ALL_DEVICES = 0xFFFF
    RESERVED_FFFE = 0xFFFE
    RX_ON_WHEN_IDLE = 0xFFFD
    ALL_ROUTERS_AND_COORDINATOR = 0xFFFC
    LOW_POWER_ROUTER = 0xFFFB
    RESERVED_FFFA = 0xFFFA
    RESERVED_FFF9 = 0xFFF9
    RESERVED_FFF8 = 0xFFF8


class EUI64(basic.FixedList, item_type=basic.uint8_t, length=8):
    # EUI 64-bit ID (an IEEE address).
    def __repr__(self):
        return ":".join("%02x" % i for i in self[::-1])

    def __hash__(self):
        return hash(repr(self))

    @classmethod
    def convert(cls, ieee: str):
        if ieee is None:
            return None
        ieee = [basic.uint8_t(p, base=16) for p in ieee.split(":")[::-1]]
        assert len(ieee) == cls._length
        return cls(ieee)


class KeyData(basic.FixedList, item_type=basic.uint8_t, length=16):
    pass


class Bool(basic.enum8):
    false = 0
    true = 1


class AttributeId(basic.uint16_t, hex_repr=True):
    pass


class BACNetOid(basic.uint32_t):
    pass


class Channels(basic.bitmap32):
    """Zigbee Channels."""

    NO_CHANNELS = 0x00000000
    ALL_CHANNELS = 0x07FFF800
    CHANNEL_11 = 0x00000800
    CHANNEL_12 = 0x00001000
    CHANNEL_13 = 0x00002000
    CHANNEL_14 = 0x00004000
    CHANNEL_15 = 0x00008000
    CHANNEL_16 = 0x00010000
    CHANNEL_17 = 0x00020000
    CHANNEL_18 = 0x00040000
    CHANNEL_19 = 0x00080000
    CHANNEL_20 = 0x00100000
    CHANNEL_21 = 0x00200000
    CHANNEL_22 = 0x00400000
    CHANNEL_23 = 0x00800000
    CHANNEL_24 = 0x01000000
    CHANNEL_25 = 0x02000000
    CHANNEL_26 = 0x04000000

    @classmethod
    def from_channel_list(cls, channels: Iterable[int]) -> "Channels":
        mask = cls.NO_CHANNELS

        for channel in channels:
            if not 11 <= channel <= 26:
                raise ValueError(
                    f"Invalid channel number {channel}. Must be between 11 and 26."
                )

            mask |= cls[f"CHANNEL_{channel}"]

        return mask


class ClusterId(basic.uint16_t):
    pass


class Date(Struct):
    years_since_1900: basic.uint8_t
    month: basic.uint8_t
    day: basic.uint8_t
    day_of_week: basic.uint8_t

    @property
    def year(self):
        if self.years_since_1900 is None:
            return None

        return 1900 + self.years_since_1900

    @year.setter
    def year(self, years):
        assert 1900 <= years <= 2155
        self.years_since_1900 = years - 1900


class NWK(basic.uint16_t, hex_repr=True):
    pass


class PanId(NWK):
    pass


class ExtendedPanId(EUI64):
    pass


class Group(basic.uint16_t, hex_repr=True):
    pass


class NoData:
    @classmethod
    def deserialize(cls, data):
        return cls(), data

    def serialize(self):
        return b""


class TimeOfDay(Struct):
    hours: basic.uint8_t
    minutes: basic.uint8_t
    seconds: basic.uint8_t
    hundredths: basic.uint8_t


class _Time(basic.uint32_t):
    pass


class UTCTime(_Time):
    pass


class StandardTime(_Time):
    """Adjusted for TimeZone but not for daylight saving."""

    pass


class LocalTime(_Time):
    """Standard time adjusted for daylight saving."""

    pass


class Relays(basic.LVList, item_type=NWK, length_type=basic.uint8_t):
    """Relay list for static routing."""

    pass


class APSStatus(basic.enum8):
    # A request has been executed successfully
    APS_SUCCESS = 0x00

    # A transmit request failed since the ASDU is too large and fragmentation
    # is not supported
    APS_ASDU_TOO_LONG = 0xA0

    # A received fragmented frame could not be defragmented at the current time
    APS_DEFRAG_DEFERRED = 0xA1

    # A received fragmented frame could not be defragmented since the device
    # does not support fragmentation
    APS_DEFRAG_UNSUPPORTED = 0xA2

    # A parameter value was out of range
    APS_ILLEGAL_REQUEST = 0xA3

    # An APSME-UNBIND.request failed due to the requested binding link not
    # existing in the binding table
    APS_INVALID_BINDING = 0xA4

    # An APSME-REMOVE-GROUP.request has been issued with a group identifier
    # that does not appear in the group table
    APS_INVALID_GROUP = 0xA5

    # A parameter value was invalid or out of range
    APS_INVALID_PARAMETER = 0xA6

    # An APSDE-DATA.request requesting acknowledged transmission failed due to
    # no acknowledgement being received
    APS_NO_ACK = 0xA7

    # An APSDE-DATA.request with a destination addressing mode set to 0x00
    # failed due to there being no devices bound to this device
    APS_NO_BOUND_DEVICE = 0xA8

    # An APSDE-DATA.request with a destination addressing mode set to 0x03
    # failed due to no corresponding short address found in the address map
    # table
    APS_NO_SHORT_ADDRESS = 0xA9

    # An APSDE-DATA.request with a destination addressing mode set to 0x00
    # failed due to a binding table not being supported on the device
    APS_NOT_SUPPORTED = 0xAA

    # An ASDU was received that was secured using a link key
    APS_SECURED_LINK_KEY = 0xAB

    # An ASDU was received that was secured using a network key
    APS_SECURED_NWK_KEY = 0xAC

    #  An APSDE-DATA.request requesting security has resulted in an error
    #  during the corresponding security processing
    APS_SECURITY_FAIL = 0xAD

    # An APSME-BIND.request or APSME.ADDGROUP.request issued when the binding
    # or group tables, respectively, were full
    APS_TABLE_FULL = 0xAE

    # An ASDU was received without any security
    APS_UNSECURED = 0xAF

    # An APSME-GET.request or APSMESET.request has been issued with an unknown
    # attribute identifier
    APS_UNSUPPORTED_ATTRIBUTE = 0xB0

    @classmethod
    def _missing_(cls, value):
        chained = NWKStatus(value)
        status = cls._member_type_.__new__(cls, chained.value)
        status._name_ = chained.name
        status._value_ = value
        return status


class MACStatus(basic.enum8):
    # Operation was successful
    MAC_SUCCESS = 0x00

    # Association Status field
    MAC_PAN_AT_CAPACITY = 0x01
    MAC_PAN_ACCESS_DENIED = 0x02

    # The frame counter purportedly applied by the originator of the received
    # frame is invalid
    MAC_COUNTER_ERROR = 0xDB

    # The key purportedly applied by the originator of the received frame is
    # not allowed to be used with that frame type according to the key usage
    # policy of the recipient
    MAC_IMPROPER_KEY_TYPE = 0xDC

    # The security level purportedly applied # by the originator of the
    # received frame does not meet the minimum security level
    # required/expected by the recipient for that frame type
    MAC_IMPROPER_SECURITY_LEVEL = 0xDD

    # The received frame was purportedly secured using security based on IEEE
    # Std 802.15.4-2003, and such security is not supported by this standard
    MAC_UNSUPPORTED_LEGACY = 0xDE

    # The security purportedly applied by the originator of the received frame
    # is not supported
    MAC_UNSUPPORTED_SECURITY = 0xDF

    # The beacon was lost following a synchronization request
    MAC_BEACON_LOSS = 0xE0

    # A transmission could not take place due to activity on the channel, i.e.
    # the CSMA-CA mechanism has failed
    MAC_CHANNEL_ACCESS_FAILURE = 0xE1

    # The GTS request has been denied by the PAN coordinator
    MAC_DENIED = 0xE2

    # The attempt to disable the transceiver has failed
    MAC_DISABLE_TRX_FAILURE = 0xE3

    # Cryptographic processing of the received secured frame failed
    MAC_SECURITY_ERROR = 0xE4

    # Either a frame resulting from processing has a length that is greater
    # than aMaxPHYPacketSize or a requested transaction is too large to fit in
    # the CAP or GTS
    MAC_FRAME_TOO_LONG = 0xE5

    # The requested GTS transmission failed because the specified GTS either
    # did not have a transmit GTS direction or was not defined
    MAC_INVALID_GTS = 0xE6

    # A request to purge an MSDU from the transaction queue was made using an
    # MSDU handle that was not found in the transaction table
    MAC_INVALID_HANDLE = 0xE7

    # A parameter in the primitive is either not supported or is out of the
    # valid range
    MAC_INVALID_PARAMETER = 0xE8

    # No acknowledgment was received after macMaxFrameRetries
    MAC_NO_ACK = 0xE9

    # A scan operation failed to find any network beacons
    MAC_NO_BEACON = 0xEA

    # No response data was available following a request
    MAC_NO_DATA = 0xEB

    # The operation failed because a 16-bit short address was not allocated
    MAC_NO_SHORT_ADDRESS = 0xEC

    # A receiver enable request was unsuccessful because it could not be
    # completed within the CAP. @note The enumeration description is not used
    # in this standard, and it is included only to meet the backwards
    # compatibility requirements for IEEE Std 802.15.4-2003
    MAC_OUT_OF_CAP = 0xED

    # A PAN identifier conflict has been detected and communicated to the PAN
    # coordinator
    MAC_PAN_ID_CONFLICT = 0xEE

    # A coordinator realignment command has been received
    MAC_REALIGNMENT = 0xEF

    # The transaction has expired and its information was discarded
    MAC_TRANSACTION_EXPIRED = 0xF0

    # There is no capacity to store the transaction
    MAC_TRANSACTION_OVERFLOW = 0xF1

    # The transceiver was in the transmitter enabled state when the receiver
    # was requested to be enabled. @note The enumeration description is not
    # used in this standard, and it is included only to meet the backwards
    # compatibility requirements for IEEE Std 802.15.4-2003
    MAC_TX_ACTIVE = 0xF2

    # The key purportedly used by the originator of the received frame is not
    # available or, if available, the originating device is not known or is
    # blacklisted with that particular key
    MAC_UNAVAILABLE_KEY = 0xF3

    # A SET/GET request was issued with the identifier of a PIB attribute that
    # is not supported
    MAC_UNSUPPORTED_ATTRIBUTE = 0xF4

    # A request to send data was unsuccessful because neither the source
    # address parameters nor the destination address parameters were present
    MAC_INVALID_ADDRESS = 0xF5

    # A receiver enable request was unsuccessful because it specified a number
    # of symbols that was longer than the beacon interval
    MAC_ON_TIME_TOO_LONG = 0xF6

    # A receiver enable request was unsuccessful because it could not be
    # completed within the current superframe and was not permitted to be
    # deferred until the next superframe
    MAC_PAST_TIME = 0xF7

    # The device was instructed to start sending beacons based on the timing
    # of the beacon transmissions of its coordinator, but the device is not
    # currently tracking the beacon of its coordinator
    MAC_TRACKING_OFF = 0xF8

    # An attempt to write to a MAC PIB attribute that is in a table failed
    # because the specified table index was out of range
    MAC_INVALID_INDEX = 0xF9

    # A scan operation terminated prematurely because the number of PAN
    # descriptors stored reached an implementation specified maximum
    MAC_LIMIT_REACHED = 0xFA

    # A SET/GET request was issued with the identifier of an attribute that is
    # read only
    MAC_READ_ONLY = 0xFB

    # A request to perform a scan operation failed because the MLME was in the
    # process of performing a previously initiated scan operation
    MAC_SCAN_IN_PROGRESS = 0xFC

    # The device was instructed to start sending beacons based on the timing
    # of the beacon transmissions of its coordinator, but the instructed start
    # time overlapped the transmission time of the beacon of its coordinator
    MAC_SUPERFRAME_OVERLAP = 0xFD


class NWKStatus(basic.enum8):
    # A request has been executed successfully
    NWK_SUCCESS = 0x00

    # An invalid or out-of-range parameter has been passed to a primitive from
    # the next higher layer
    NWK_INVALID_PARAMETER = 0xC1

    # The next higher layer has issued a request that is invalid or cannot be
    # executed given the current state of the NWK layer
    NWK_INVALID_REQUEST = 0xC2

    # An NLME-JOIN.request has been disallowed
    NWK_NOT_PERMITTED = 0xC3

    # An NLME-NETWORK-FORMATION.request has failed to start a network
    NWK_STARTUP_FAILURE = 0xC4

    # A device with the address supplied to the NLMEDIRECT-JOIN.request is
    # already present in the neighbor table of the device on which the
    # NLMEDIRECT-JOIN.request was issued
    NWK_ALREADY_PRESENT = 0xC5

    # Used to indicate that an NLME-SYNC.request has failed at the MAC layer
    NWK_SYNC_FAILURE = 0xC6

    # An NLME-JOIN-DIRECTLY.request has failed because there is no more room
    # in the neighbor table
    NWK_NEIGHBOR_TABLE_FULL = 0xC7

    # An NLME-LEAVE.request has failed because the device addressed in the
    # parameter list is not in the neighbor table of the issuing device
    NWK_UNKNOWN_DEVICE = 0xC8

    # An NLME-GET.request or NLME-SET.request has been issued with an unknown
    # attribute identifier
    NWK_UNSUPPORTED_ATTRIBUTE = 0xC9

    # An NLME-JOIN.request has been issued in an environment where no networks
    # are detectable
    NWK_NO_NETWORKS = 0xCA

    NWK_RESERVED_0xCB = 0xCB

    # Security processing has been attempted on an outgoing frame, and has
    # failed because the frame counter has reached its maximum value
    NWK_NWK_MAX_FRM_COUNTER = 0xCC

    # Security processing has been attempted on an outgoing frame, and has
    # failed because no key was available with which to process it
    NWK_NO_KEY = 0xCD

    # Security processing has been attempted on an outgoing frame, and has
    # failed because the security engine produced erroneous output
    NWK_BAD_CCM_OUTPUT = 0xCE

    NWK_RESERVED_0xCF = 0xCF

    # An attempt to discover a route has failed due to a reason other than a
    # lack of routing capacity
    NWK_ROUTE_DISCOVERY_FAILED = 0xD0

    # An NLDE-DATA.request has failed due to a routing failure on the sending
    # device or an NLMEROUTE-DISCOVERY.request has failed due to the cause
    # cited in the accompanying NetworkStatusCode
    NWK_ROUTE_ERROR = 0xD1

    # An attempt to send a broadcast frame or member mode multicast has failed
    # due to the fact that there is no room in the BTT
    NWK_BT_TABLE_FULL = 0xD2

    # An NLDE-DATA.request has failed due to insufficient buffering available.
    # A non-member mode multicast frame was discarded pending route discovery
    NWK_FRAME_NOT_BUFFERED = 0xD3

    @classmethod
    def _missing_(cls, value):
        chained = MACStatus(value)
        status = cls._member_type_.__new__(cls, chained.value)
        status._name_ = chained.name
        status._value_ = value
        return status


class AddrMode(basic.enum8):
    """Addressing mode."""

    Group = 0x01
    NWK = 0x02
    IEEE = 0x03


class _AddressingIEEE(Struct):
    """Addressing mode is IEEE."""

    addr_mode: AddrMode
    addr: EUI64
    endpoint: basic.uint8_t


class _AddressingGroup(Struct):
    """Addressing mode is Group."""

    addr_mode: AddrMode
    addr: Group


class _AddressingNWK(Struct):
    """Addressing mode is Group."""

    addr_mode: AddrMode
    addr: NWK
    endpoint: basic.uint8_t


class Addressing:
    """Addr mode, address (group, node id or ieee) and optionally endpoint id."""

    AddrMode = AddrMode
    IEEE = _AddressingIEEE
    Group = _AddressingGroup
    NWK = _AddressingNWK

    @classmethod
    def ieee(cls, ieee: EUI64, endpoint: Union[basic.uint8_t, int]) -> _AddressingIEEE:
        """Return IEEE addressing mode."""

        return cls.IEEE(AddrMode.IEEE, ieee, endpoint)

    @classmethod
    def group(cls, group: Group) -> _AddressingGroup:
        """Return Group addressing mode."""

        return cls.Group(AddrMode.Group, group)

    @classmethod
    def nwk(cls, nwk: NWK, endpoint: Union[basic.uint8_t, int]) -> _AddressingNWK:
        """Return NWK addressing mode."""

        return cls.NWK(AddrMode.NWK, nwk, endpoint)

    @classmethod
    def deserialize(
        cls, data: bytes
    ) -> Tuple[Union[_AddressingGroup, _AddressingIEEE, _AddressingNWK], bytes]:
        """Deserialize data."""

        if data[0] == AddrMode.IEEE:
            return cls.IEEE.deserialize(data)
        elif data[0] == AddrMode.Group:
            return cls.Group.deserialize(data)
        elif data[0] == AddrMode.NWK:
            return cls.NWK.deserialize(data)

        raise ValueError(f"Invalid '0x{data[0]:02x}' addressing mode")
