import typing

import zigpy.types as t


class PowerDescriptor(t.Struct):
    byte_1: t.uint8_t
    byte_2: t.uint8_t

    # TODO: interpret the four 4-bit fields


class SimpleDescriptor(t.Struct):
    endpoint: t.uint8_t
    profile: t.uint16_t
    device_type: t.uint16_t
    device_version: t.uint8_t
    input_clusters: t.LVList[t.uint16_t]
    output_clusters: t.LVList[t.uint16_t]


class SizePrefixedSimpleDescriptor(SimpleDescriptor):
    def serialize(self):
        data = super().serialize()
        return len(data).to_bytes(1, "little") + data

    @classmethod
    def deserialize(cls, data):
        if not data or data[0] == 0:
            return None, data[1:]
        return super().deserialize(data[1:])


class LogicalType(t.enum8):
    Coordinator = 0b000
    Router = 0b001
    EndDevice = 0b010
    Reserved3 = 0b011
    Reserved4 = 0b100
    Reserved5 = 0b101
    Reserved6 = 0b110
    Reserved7 = 0b111


class NodeDescriptor(t.Struct):
    byte1: t.uint8_t
    byte2: t.uint8_t
    mac_capability_flags: t.uint8_t
    manufacturer_code: t.uint16_t
    maximum_buffer_size: t.uint8_t
    maximum_incoming_transfer_size: t.uint16_t
    server_mask: t.uint16_t
    maximum_outgoing_transfer_size: t.uint16_t
    descriptor_capability_field: t.uint8_t

    @property
    def is_valid(self):
        """Return True if all fields were initialized."""
        non_empty_fields = [
            getattr(self, field.name) is not None for field in self.fields
        ]
        return all(non_empty_fields)

    @property
    def logical_type(self):
        """Return logical type of the device"""
        if self.byte1 is None:
            return None
        return LogicalType(self.byte1 & 0x07)

    @property
    def is_coordinator(self):
        """Return True whether this is a coordinator."""
        if self.logical_type is None:
            return None
        return self.logical_type == LogicalType.Coordinator

    @property
    def is_end_device(self):
        """Return True whether this is an end device."""
        if self.logical_type is None:
            return None
        return self.logical_type == LogicalType.EndDevice

    @property
    def is_router(self):
        """Return True whether this is a router."""
        if self.logical_type is None:
            return None
        return self.logical_type == LogicalType.Router

    @property
    def complex_descriptor_available(self):
        if self.byte1 is None:
            return None
        return bool(self.byte1 & 0b00001000)

    @property
    def user_descriptor_available(self):
        if self.byte1 is None:
            return None
        return bool(self.byte1 & 0b00010000)

    @property
    def is_alternate_pan_coordinator(self):
        if self.mac_capability_flags is None:
            return None
        return bool(self.mac_capability_flags & 0b00000001)

    @property
    def is_full_function_device(self):
        if self.mac_capability_flags is None:
            return None
        return bool(self.mac_capability_flags & 0b00000010)

    @property
    def is_mains_powered(self):
        if self.mac_capability_flags is None:
            return None
        return bool(self.mac_capability_flags & 0b00000100)

    @property
    def is_receiver_on_when_idle(self):
        if self.mac_capability_flags is None:
            return None
        return bool(self.mac_capability_flags & 0b00001000)

    @property
    def is_security_capable(self):
        if self.mac_capability_flags is None:
            return None
        return bool(self.mac_capability_flags & 0b01000000)

    @property
    def allocate_address(self):
        if self.mac_capability_flags is None:
            return None
        return bool(self.mac_capability_flags & 0b10000000)


class MultiAddress(t.Struct):
    """Used for binds, represents an IEEE+endpoint or NWK address"""

    addrmode: t.uint8_t
    nwk: t.uint16_t = t.StructField(requires=lambda s: s.addrmode == 0x01)
    ieee: t.EUI64 = t.StructField(requires=lambda s: s.addrmode == 0x03)
    endpoint: t.uint8_t = t.StructField(requires=lambda s: s.addrmode == 0x03)

    @classmethod
    def deserialize(cls, data):
        r, data = super().deserialize(data)

        if r.addrmode not in (0x01, 0x03):
            raise ValueError("Invalid MultiAddress - unknown address mode")

        return r, data

    def serialize(self):
        if self.addrmode not in (0x01, 0x03):
            raise ValueError("Invalid MultiAddress - unknown address mode")

        return super().serialize()


class _NeighborEnums:
    """Types container."""

    class DeviceType(t.enum8):
        Coordinator = 0x0
        Router = 0x1
        EndDevice = 0x2
        Unknown = 0x3

    class RxOnWhenIdle(t.enum8):
        Off = 0x0
        On = 0x1
        Unknown = 0x2

    class Relationship(t.enum8):
        Parent = 0x0
        Child = 0x1
        Sibling = 0x2
        NoneOfTheAbove = 0x3
        PreviousChild = 0x4


class Neighbor(t.Struct):
    """Neighbor Descriptor"""

    DeviceType = _NeighborEnums.DeviceType
    RxOnWhenIdle = _NeighborEnums.RxOnWhenIdle
    RelationShip = _NeighborEnums.Relationship

    class PermitJoins(t.enum8):
        NotAccepting = 0x0
        Accepting = 0x1
        Unknown = 0x2

    extended_pan_id: t.ExtendedPanId
    ieee: t.EUI64
    nwk: t.NWK
    packed: t.uint8_t
    permit_joining: PermitJoins
    depth: t.uint8_t
    lqi: t.uint8_t

    @property
    def device_type(self) -> typing.Optional[_NeighborEnums.DeviceType]:
        """Return neighbor type."""
        if self.packed is None:
            return None
        return _NeighborEnums.DeviceType(self.packed & 0x03)

    @device_type.setter
    def device_type(self, value: _NeighborEnums.DeviceType) -> None:
        """Neighbor type setter."""
        if self.packed is None:
            self.packed = value
        self.packed &= 0b0111_1100
        self.packed |= value & 0x03

    @property
    def rx_on_when_idle(self) -> typing.Optional[_NeighborEnums.RxOnWhenIdle]:
        """Return rx_on."""
        if self.packed is None:
            return None
        return _NeighborEnums.RxOnWhenIdle((self.packed >> 2) & 0x03)

    @rx_on_when_idle.setter
    def rx_on_when_idle(self, value: _NeighborEnums.RxOnWhenIdle) -> None:
        """Rx on when idle setter."""
        if self.packed is None:
            self.packed = value
        self.packed &= 0b0111_0011
        self.packed |= (value & 0x03) << 2

    @property
    def relationship(self) -> typing.Optional[_NeighborEnums.Relationship]:
        """Return relationship."""
        if self.packed is None:
            return None
        return _NeighborEnums.Relationship((self.packed >> 4) & 0x07)

    @relationship.setter
    def relationship(self, value: _NeighborEnums.Relationship) -> None:
        """Relationship setter."""
        if self.packed is None:
            self.packed = value
        self.packed &= 0b0000_1111
        self.packed |= (value & 0x07) << 4


class Neighbors(t.Struct):
    """Mgmt_Lqi_rsp"""

    entries: t.uint8_t
    start_index: t.uint8_t
    neighbor_table_list: t.LVList[Neighbor]


class Route(t.Struct):
    """Route Descriptor"""

    DstNWK: t.NWK
    RouteStatus: t.uint8_t
    NextHop: t.NWK


class Routes(t.Struct):
    Entries: t.uint8_t
    StartIndex: t.uint8_t
    RoutingTableList: t.LVList[Route]


class NwkUpdate(t.Struct):
    CHANNEL_CHANGE_REQ = 0xFE
    CHANNEL_MASK_MANAGER_ADDR_CHANGE_REQ = 0xFF

    ScanChannels: t.Channels
    ScanDuration: t.uint8_t
    ScanCount: t.uint8_t = t.StructField(requires=lambda s: s.ScanDuration <= 0x05)
    nwkUpdateId: t.uint8_t = t.StructField(
        requires=lambda s: s.ScanDuration
        in (s.CHANNEL_CHANGE_REQ, s.CHANNEL_MASK_MANAGER_ADDR_CHANGE_REQ)
    )
    nwkManagerAddr: t.NWK = t.StructField(
        requires=lambda s: s.ScanDuration == s.CHANNEL_MASK_MANAGER_ADDR_CHANGE_REQ
    )


class Status(t.enum8):
    # The requested operation or transmission was completed successfully.
    SUCCESS = 0x00
    # The supplied request type was invalid.
    INV_REQUESTTYPE = 0x80
    # The requested device did not exist on a device following a child
    # descriptor request to a parent.
    DEVICE_NOT_FOUND = 0x81
    # The supplied endpoint was equal to = 0x00 or between 0xf1 and 0xff.
    INVALID_EP = 0x82
    # The requested endpoint is not described by a simple descriptor.
    NOT_ACTIVE = 0x83
    # The requested optional feature is not supported on the target device.
    NOT_SUPPORTED = 0x84
    # A timeout has occurred with the requested operation.
    TIMEOUT = 0x85
    # The end device bind request was unsuccessful due to a failure to match
    # any suitable clusters.
    NO_MATCH = 0x86
    # The unbind request was unsuccessful due to the coordinator or source
    # device not having an entry in its binding table to unbind.
    NO_ENTRY = 0x88
    # A child descriptor was not available following a discovery request to a
    # parent.
    NO_DESCRIPTOR = 0x89
    # The device does not have storage space to support the requested
    # operation.
    INSUFFICIENT_SPACE = 0x8A
    # The device is not in the proper state to support the requested operation.
    NOT_PERMITTED = 0x8B
    # The device does not have table space to support the operation.
    TABLE_FULL = 0x8C
    # The permissions configuration table on the target indicates that the
    # request is not authorized from this device.
    NOT_AUTHORIZED = 0x8D

    @classmethod
    def _missing_(cls, value):
        chained = t.APSStatus(value)
        status = cls._member_type_.__new__(cls, chained.value)
        status._name_ = chained.name
        status._value_ = value
        return status


NWK = ("NWKAddr", t.NWK)
NWKI = ("NWKAddrOfInterest", t.NWK)
IEEE = ("IEEEAddr", t.EUI64)
STATUS = ("Status", Status)


class _CommandID(t.uint16_t, hex_repr=True):
    pass


class ZDOCmd(t.enum_factory(_CommandID)):
    # Device and Service Discovery Server Requests
    NWK_addr_req = 0x0000
    IEEE_addr_req = 0x0001
    Node_Desc_req = 0x0002
    Power_Desc_req = 0x0003
    Simple_Desc_req = 0x0004
    Active_EP_req = 0x0005
    Match_Desc_req = 0x0006
    Complex_Desc_req = 0x0010
    User_Desc_req = 0x0011
    Discovery_Cache_req = 0x0012
    Device_annce = 0x0013
    User_Desc_set = 0x0014
    System_Server_Discovery_req = 0x0015
    Discovery_store_req = 0x0016
    Node_Desc_store_req = 0x0017
    Active_EP_store_req = 0x0019
    Simple_Desc_store_req = 0x001A
    Remove_node_cache_req = 0x001B
    Find_node_cache_req = 0x001C
    Extended_Simple_Desc_req = 0x001D
    Extended_Active_EP_req = 0x001E
    Parent_annce = 0x001F
    #  Bind Management Server Services Responses
    End_Device_Bind_req = 0x0020
    Bind_req = 0x0021
    Unbind_req = 0x0022
    # Network Management Server Services Requests
    # ... TODO optional stuff ...
    Mgmt_Lqi_req = 0x0031
    Mgmt_Rtg_req = 0x0032
    # ... TODO optional stuff ...
    Mgmt_Leave_req = 0x0034
    Mgmt_Permit_Joining_req = 0x0036
    Mgmt_NWK_Update_req = 0x0038
    # ... TODO optional stuff ...

    # Responses
    # Device and Service Discovery Server Responses
    NWK_addr_rsp = 0x8000
    IEEE_addr_rsp = 0x8001
    Node_Desc_rsp = 0x8002
    Power_Desc_rsp = 0x8003
    Simple_Desc_rsp = 0x8004
    Active_EP_rsp = 0x8005
    Match_Desc_rsp = 0x8006
    Complex_Desc_rsp = 0x8010
    User_Desc_rsp = 0x8011
    Discovery_Cache_rsp = 0x8012
    User_Desc_conf = 0x8014
    System_Server_Discovery_rsp = 0x8015
    Discovery_Store_rsp = 0x8016
    Node_Desc_store_rsp = 0x8017
    Power_Desc_store_rsp = 0x8018
    Active_EP_store_rsp = 0x8019
    Simple_Desc_store_rsp = 0x801A
    Remove_node_cache_rsp = 0x801B
    Find_node_cache_rsp = 0x801C
    Extended_Simple_Desc_rsp = 0x801D
    Extended_Active_EP_rsp = 0x801E
    Parent_annce_rsp = 0x801F
    #  Bind Management Server Services Responses
    End_Device_Bind_rsp = 0x8020
    Bind_rsp = 0x8021
    Unbind_rsp = 0x8022
    # ... TODO optional stuff ...
    # Network Management Server Services Responses
    Mgmt_Lqi_rsp = 0x8031
    Mgmt_Rtg_rsp = 0x8032
    # ... TODO optional stuff ...
    Mgmt_Leave_rsp = 0x8034
    Mgmt_Permit_Joining_rsp = 0x8036
    # ... TODO optional stuff ...
    Mgmt_NWK_Update_rsp = 0x8038


CLUSTERS = {
    # Device and Service Discovery Server Requests
    ZDOCmd.NWK_addr_req: (IEEE, ("RequestType", t.uint8_t), ("StartIndex", t.uint8_t)),
    ZDOCmd.IEEE_addr_req: (NWKI, ("RequestType", t.uint8_t), ("StartIndex", t.uint8_t)),
    ZDOCmd.Node_Desc_req: (NWKI,),
    ZDOCmd.Power_Desc_req: (NWKI,),
    ZDOCmd.Simple_Desc_req: (NWKI, ("EndPoint", t.uint8_t)),
    ZDOCmd.Active_EP_req: (NWKI,),
    ZDOCmd.Match_Desc_req: (
        NWKI,
        ("ProfileID", t.uint16_t),
        ("InClusterList", t.LVList[t.uint16_t]),
        ("OutClusterList", t.LVList[t.uint16_t]),
    ),
    # ZDO.Complex_Desc_req: (NWKI, ),
    ZDOCmd.User_Desc_req: (NWKI,),
    ZDOCmd.Discovery_Cache_req: (NWK, IEEE),
    ZDOCmd.Device_annce: (NWK, IEEE, ("Capability", t.uint8_t)),
    ZDOCmd.User_Desc_set: (
        NWKI,
        ("UserDescriptor", t.FixedList[16, t.uint8_t]),
    ),  # Really a string
    ZDOCmd.System_Server_Discovery_req: (("ServerMask", t.uint16_t),),
    ZDOCmd.Discovery_store_req: (
        NWK,
        IEEE,
        ("NodeDescSize", t.uint8_t),
        ("PowerDescSize", t.uint8_t),
        ("ActiveEPSize", t.uint8_t),
        ("SimpleDescSizeList", t.LVList[t.uint8_t]),
    ),
    ZDOCmd.Node_Desc_store_req: (NWK, IEEE, ("NodeDescriptor", NodeDescriptor)),
    ZDOCmd.Active_EP_store_req: (NWK, IEEE, ("ActiveEPList", t.LVList[t.uint8_t])),
    ZDOCmd.Simple_Desc_store_req: (
        NWK,
        IEEE,
        ("SimpleDescriptor", SizePrefixedSimpleDescriptor),
    ),
    ZDOCmd.Remove_node_cache_req: (NWK, IEEE),
    ZDOCmd.Find_node_cache_req: (NWK, IEEE),
    ZDOCmd.Extended_Simple_Desc_req: (
        NWKI,
        ("EndPoint", t.uint8_t),
        ("StartIndex", t.uint8_t),
    ),
    ZDOCmd.Extended_Active_EP_req: (NWKI, ("StartIndex", t.uint8_t)),
    ZDOCmd.Parent_annce: (("Children", t.LVList[t.EUI64]),),
    #  Bind Management Server Services Responses
    ZDOCmd.End_Device_Bind_req: (
        ("BindingTarget", t.uint16_t),
        ("SrcAddress", t.EUI64),
        ("SrcEndpoint", t.uint8_t),
        ("ProfileID", t.uint8_t),
        ("InClusterList", t.LVList[t.uint8_t]),
        ("OutClusterList", t.LVList[t.uint8_t]),
    ),
    ZDOCmd.Bind_req: (
        ("SrcAddress", t.EUI64),
        ("SrcEndpoint", t.uint8_t),
        ("ClusterID", t.uint16_t),
        ("DstAddress", MultiAddress),
    ),
    ZDOCmd.Unbind_req: (
        ("SrcAddress", t.EUI64),
        ("SrcEndpoint", t.uint8_t),
        ("ClusterID", t.uint16_t),
        ("DstAddress", MultiAddress),
    ),
    # Network Management Server Services Requests
    # ... TODO optional stuff ...
    ZDOCmd.Mgmt_Lqi_req: (("StartIndex", t.uint8_t),),
    ZDOCmd.Mgmt_Rtg_req: (("StartIndex", t.uint8_t),),
    # ... TODO optional stuff ...
    ZDOCmd.Mgmt_Leave_req: (("DeviceAddress", t.EUI64), ("Options", t.bitmap8)),
    ZDOCmd.Mgmt_Permit_Joining_req: (
        ("PermitDuration", t.uint8_t),
        ("TC_Significant", t.Bool),
    ),
    ZDOCmd.Mgmt_NWK_Update_req: (("NwkUpdate", NwkUpdate),),
    # ... TODO optional stuff ...
    # Responses
    # Device and Service Discovery Server Responses
    ZDOCmd.NWK_addr_rsp: (
        STATUS,
        IEEE,
        NWK,
        ("NumAssocDev", t.Optional(t.uint8_t)),
        ("StartIndex", t.Optional(t.uint8_t)),
        ("NWKAddressAssocDevList", t.Optional(t.List[t.NWK])),
    ),
    ZDOCmd.IEEE_addr_rsp: (
        STATUS,
        IEEE,
        NWK,
        ("NumAssocDev", t.Optional(t.uint8_t)),
        ("StartIndex", t.Optional(t.uint8_t)),
        ("NWKAddrAssocDevList", t.Optional(t.List[t.NWK])),
    ),
    ZDOCmd.Node_Desc_rsp: (
        STATUS,
        NWKI,
        ("NodeDescriptor", t.Optional(NodeDescriptor)),
    ),
    ZDOCmd.Power_Desc_rsp: (
        STATUS,
        NWKI,
        ("PowerDescriptor", t.Optional(PowerDescriptor)),
    ),
    ZDOCmd.Simple_Desc_rsp: (
        STATUS,
        NWKI,
        ("SimpleDescriptor", t.Optional(SizePrefixedSimpleDescriptor)),
    ),
    ZDOCmd.Active_EP_rsp: (STATUS, NWKI, ("ActiveEPList", t.LVList[t.uint8_t])),
    ZDOCmd.Match_Desc_rsp: (STATUS, NWKI, ("MatchList", t.LVList[t.uint8_t])),
    # ZDO.Complex_Desc_rsp: (
    #     STATUS,
    #     NWKI,
    #     ('Length', t.uint8_t),
    #     ('ComplexDescriptor', t.Optional(ComplexDescriptor)),
    # ),
    ZDOCmd.User_Desc_rsp: (
        STATUS,
        NWKI,
        ("Length", t.uint8_t),
        ("UserDescriptor", t.Optional(t.FixedList[16, t.uint8_t])),
    ),
    ZDOCmd.Discovery_Cache_rsp: (STATUS,),
    ZDOCmd.User_Desc_conf: (STATUS, NWKI),
    ZDOCmd.System_Server_Discovery_rsp: (STATUS, ("ServerMask", t.uint16_t)),
    ZDOCmd.Discovery_Store_rsp: (STATUS,),
    ZDOCmd.Node_Desc_store_rsp: (STATUS,),
    ZDOCmd.Power_Desc_store_rsp: (STATUS, IEEE, ("PowerDescriptor", PowerDescriptor)),
    ZDOCmd.Active_EP_store_rsp: (STATUS,),
    ZDOCmd.Simple_Desc_store_rsp: (STATUS,),
    ZDOCmd.Remove_node_cache_rsp: (STATUS,),
    ZDOCmd.Find_node_cache_rsp: (("CacheNWKAddr", t.EUI64), NWK, IEEE),
    ZDOCmd.Extended_Simple_Desc_rsp: (
        STATUS,
        NWK,
        ("Endpoint", t.uint8_t),
        ("AppInputClusterCount", t.uint8_t),
        ("AppOutputClusterCount", t.uint8_t),
        ("StartIndex", t.uint8_t),
        ("AppClusterList", t.Optional(t.List[t.uint16_t])),
    ),
    ZDOCmd.Extended_Active_EP_rsp: (
        STATUS,
        NWKI,
        ("ActiveEPCount", t.uint8_t),
        ("StartIndex", t.uint8_t),
        ("ActiveEPList", t.List[t.uint8_t]),
    ),
    ZDOCmd.Parent_annce_rsp: (STATUS, ("Children", t.LVList[t.EUI64])),
    #  Bind Management Server Services Responses
    ZDOCmd.End_Device_Bind_rsp: (STATUS,),
    ZDOCmd.Bind_rsp: (STATUS,),
    ZDOCmd.Unbind_rsp: (STATUS,),
    # ... TODO optional stuff ...
    # Network Management Server Services Responses
    ZDOCmd.Mgmt_Lqi_rsp: (STATUS, ("Neighbors", t.Optional(Neighbors))),
    ZDOCmd.Mgmt_Rtg_rsp: (STATUS, ("Routes", t.Optional(Routes))),
    # ... TODO optional stuff ...
    ZDOCmd.Mgmt_Leave_rsp: (STATUS,),
    ZDOCmd.Mgmt_Permit_Joining_rsp: (STATUS,),
    ZDOCmd.Mgmt_NWK_Update_rsp: (
        STATUS,
        ("ScannedChannels", t.Channels),
        ("TotalTransmissions", t.uint16_t),
        ("TransmissionFailures", t.uint16_t),
        ("EnergyValues", t.LVList[t.uint8_t]),
    )
    # ... TODO optional stuff ...
}


# Rewrite to (name, param_names, param_types)
for command_id, schema in CLUSTERS.items():
    param_names = [p[0] for p in schema]
    param_types = [p[1] for p in schema]
    CLUSTERS[command_id] = (param_names, param_types)


class ZDOHeader:
    """Just a wrapper representing ZDO header, similar to ZCL header."""

    def __init__(self, command_id: t.uint16_t = 0x0000, tsn: t.uint8_t = 0) -> None:
        self._command_id = ZDOCmd(command_id)
        self._tsn = t.uint8_t(tsn)

    @property
    def command_id(self) -> ZDOCmd:
        """Return ZDO command."""
        return self._command_id

    @command_id.setter
    def command_id(self, value: t.uint16_t) -> None:
        """Command ID setter."""
        self._command_id = ZDOCmd(value)

    @property
    def is_reply(self) -> bool:
        """Return True if this is a reply."""
        return bool(self._command_id & 0x8000)

    @property
    def tsn(self) -> t.uint8_t:
        """Return transaction seq number."""
        return self._tsn

    @tsn.setter
    def tsn(self, value: t.uint8_t) -> None:
        """Set TSN."""
        self._tsn = t.uint8_t(value)

    @classmethod
    def deserialize(
        cls, command_id: t.uint16_t, data: bytes
    ) -> typing.Tuple["ZDOHeader", bytes]:
        """Deserialize data."""
        tsn, data = t.uint8_t.deserialize(data)
        return cls(command_id, tsn), data

    def serialize(self) -> bytes:
        """Serialize header."""

        return self.tsn.serialize()
