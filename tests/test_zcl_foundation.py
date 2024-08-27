import logging

import pytest

import zigpy.types as t
from zigpy.zcl import foundation


def test_typevalue():
    tv = foundation.TypeValue()
    tv.type = 0x20
    tv.value = t.uint8_t(99)
    ser = tv.serialize()
    r = repr(tv)
    assert r.startswith("TypeValue(") and r.endswith(")")
    assert "type=uint8_t" in r
    assert "value=99" in r

    tv2, data = foundation.TypeValue.deserialize(ser)
    assert data == b""
    assert tv2.type == tv.type
    assert tv2.value == tv.value

    tv3 = foundation.TypeValue(tv2)
    assert tv3.type == tv.type
    assert tv3.value == tv.value
    assert tv3 == tv2

    tv4 = foundation.TypeValue()
    tv4.type = 0x42
    tv4.value = t.CharacterString("test")
    assert "CharacterString" in str(tv4)
    assert "'test'" in str(tv4)

    tv5 = foundation.TypeValue()
    tv5.type = 0x42
    tv5.value = t.CharacterString("test")

    assert tv5 == tv5  # noqa: PLR0124
    assert tv5 == tv4
    assert tv5 != tv3


def test_read_attribute_record():
    orig = b"\x00\x00\x00\x20\x99"
    rar, data = foundation.ReadAttributeRecord.deserialize(orig)
    assert data == b""
    assert rar.status == 0
    assert isinstance(rar.value, foundation.TypeValue)
    assert isinstance(rar.value.value, t.uint8_t)
    assert rar.value.value == 0x99

    r = repr(rar)
    assert len(r) > 5
    assert repr(foundation.Status.SUCCESS) in r

    ser = rar.serialize()
    assert ser == orig


def test_attribute_reporting_config_0():
    arc = foundation.AttributeReportingConfig()
    arc.direction = foundation.ReportingDirection.SendReports
    arc.attrid = 99
    arc.datatype = 0x20
    arc.min_interval = 10
    arc.max_interval = 20
    arc.reportable_change = 30
    ser = arc.serialize()

    arc2, data = foundation.AttributeReportingConfig.deserialize(ser)
    assert data == b""
    assert arc2.direction == arc.direction
    assert arc2.attrid == arc.attrid
    assert arc2.datatype == arc.datatype
    assert arc2.min_interval == arc.min_interval
    assert arc2.max_interval == arc.max_interval
    assert arc.reportable_change == arc.reportable_change

    assert repr(arc)
    assert repr(arc) == repr(arc2)


def test_attribute_reporting_config_1():
    arc = foundation.AttributeReportingConfig()
    arc.direction = 1
    arc.attrid = 99
    arc.timeout = 0x7E
    ser = arc.serialize()

    arc2, data = foundation.AttributeReportingConfig.deserialize(ser)
    assert data == b""
    assert arc2.direction == arc.direction
    assert arc2.timeout == arc.timeout
    assert repr(arc)


def test_attribute_reporting_config_only_dir_and_attrid():
    arc = foundation.AttributeReportingConfig()
    arc.direction = foundation.ReportingDirection.SendReports
    arc.attrid = 99
    ser = arc.serialize(_only_dir_and_attrid=True)

    arc2, data = foundation.AttributeReportingConfig.deserialize(
        ser, _only_dir_and_attrid=True
    )
    assert data == b""
    assert arc2.direction == arc.direction
    assert arc2.attrid == arc.attrid

    assert repr(arc)
    assert repr(arc) == repr(arc2)


def test_attribute_reporting_config_bad_datatype(caplog):
    arc = foundation.AttributeReportingConfig()
    arc.direction = foundation.ReportingDirection.SendReports
    arc.attrid = 99
    arc.datatype = 0xFE  # unknown
    arc.min_interval = 10
    arc.max_interval = 20
    arc.reportable_change = 30

    with caplog.at_level(logging.WARNING):
        arc.serialize()

    assert "Unknown ZCL type" in caplog.text

    arc2 = foundation.AttributeReportingConfig()
    arc2.direction = foundation.ReportingDirection.SendReports
    arc2.attrid = 99
    arc2.datatype = 0xFE  # unknown
    arc2.min_interval = 10
    arc2.max_interval = 20
    # Missing the reportable change, since it can't be set

    assert arc.serialize() == arc2.serialize()

    caplog.clear()

    with caplog.at_level(logging.WARNING):
        arc3, data = foundation.AttributeReportingConfig.deserialize(arc.serialize())

    assert "Unknown ZCL type" in caplog.text

    assert arc3.serialize() == arc.serialize()


def test_write_attribute_status_record():
    attr_id = b"\x01\x00"
    extra = b"12da-"
    res, d = foundation.WriteAttributesStatusRecord.deserialize(
        b"\x00" + attr_id + extra
    )
    assert res.status == foundation.Status.SUCCESS
    assert res.attrid is None
    assert d == attr_id + extra
    r = repr(res)
    assert r.startswith(foundation.WriteAttributesStatusRecord.__name__)
    assert "status" in r
    assert "attrid" not in r

    res, d = foundation.WriteAttributesStatusRecord.deserialize(
        b"\x87" + attr_id + extra
    )
    assert res.status == foundation.Status.INVALID_VALUE
    assert res.attrid == 0x0001
    assert d == extra

    r = repr(res)
    assert "status" in r
    assert "attrid" in r

    rec = foundation.WriteAttributesStatusRecord(foundation.Status.SUCCESS, 0xAABB)
    assert rec.serialize() == b"\x00"
    rec.status = foundation.Status.UNSUPPORTED_ATTRIBUTE
    assert rec.serialize()[0:1] == foundation.Status.UNSUPPORTED_ATTRIBUTE.serialize()
    assert rec.serialize()[1:] == b"\xbb\xaa"


def test_configure_reporting_response_serialization():
    # success status only
    res, d = foundation.ConfigureReportingResponseRecord.deserialize(b"\x00")
    assert res.status == foundation.Status.SUCCESS
    assert res.direction is None
    assert res.attrid is None
    assert d == b""

    # success + direction and attr id
    direction_attr_id = b"\x00\x01\x10"
    extra = b"12da-"
    res, d = foundation.ConfigureReportingResponseRecord.deserialize(
        b"\x00" + direction_attr_id + extra
    )
    assert res.status == foundation.Status.SUCCESS
    assert res.direction is foundation.ReportingDirection.SendReports
    assert res.attrid == 0x1001
    assert d == extra
    r = repr(res)
    assert r.startswith(foundation.ConfigureReportingResponseRecord.__name__ + "(")
    assert "status" in r
    assert "direction" not in r
    assert "attrid" not in r

    # failure record deserialization
    res, d = foundation.ConfigureReportingResponseRecord.deserialize(
        b"\x8c" + direction_attr_id + extra
    )
    assert res.status == foundation.Status.UNREPORTABLE_ATTRIBUTE
    assert res.direction is not None
    assert res.attrid == 0x1001
    assert d == extra

    r = repr(res)
    assert "status" in r
    assert "direction" in r
    assert "attrid" in r

    # successful record serializes only Status
    rec = foundation.ConfigureReportingResponseRecord(
        foundation.Status.SUCCESS, 0x00, 0xAABB
    )
    assert rec.serialize() == b"\x00"
    rec.status = foundation.Status.UNREPORTABLE_ATTRIBUTE
    assert rec.serialize()[0:1] == foundation.Status.UNREPORTABLE_ATTRIBUTE.serialize()
    assert rec.serialize()[1:] == b"\x00\xbb\xaa"


def test_status_undef():
    data = b"\xff"
    extra = b"extra"

    status, rest = foundation.Status.deserialize(data + extra)
    assert rest == extra
    assert status == 0xFF
    assert status.value == 0xFF
    assert status.name == "undefined_0xff"
    assert isinstance(status, foundation.Status)


def test_frame_control():
    """Test FrameControl frame_type."""
    extra = b"abcd\xaa\x55"
    frc, rest = foundation.FrameControl.deserialize(b"\x00" + extra)
    assert rest == extra
    assert frc.frame_type == foundation.FrameType.GLOBAL_COMMAND

    frc, rest = foundation.FrameControl.deserialize(b"\x01" + extra)
    assert rest == extra
    assert frc.frame_type == foundation.FrameType.CLUSTER_COMMAND

    r = repr(frc)
    assert isinstance(r, str)


def test_frame_control_general():
    frc = foundation.FrameControl.general(
        direction=foundation.Direction.Client_to_Server
    )
    assert frc.is_cluster is False
    assert frc.is_general is True
    data = frc.serialize()

    assert data == b"\x00"
    assert not frc.is_manufacturer_specific
    frc.is_manufacturer_specific = False
    assert frc.serialize() == b"\x00"
    frc.is_manufacturer_specific = True
    assert frc.serialize() == b"\x04"

    frc = foundation.FrameControl.general(
        direction=foundation.Direction.Client_to_Server
    )
    assert frc.direction == foundation.Direction.Client_to_Server
    assert frc.serialize() == b"\x00"
    frc.direction = foundation.Direction.Server_to_Client
    assert frc.serialize() == b"\x08"
    assert (
        foundation.FrameControl.general(
            direction=foundation.Direction.Server_to_Client
        ).serialize()
        == b"\x18"
    )

    frc = foundation.FrameControl.general(
        direction=foundation.Direction.Client_to_Server
    )
    assert not frc.disable_default_response
    assert frc.serialize() == b"\x00"
    frc.disable_default_response = False
    assert frc.serialize() == b"\x00"
    frc.disable_default_response = True
    assert frc.serialize() == b"\x10"


def test_frame_control_cluster():
    frc = foundation.FrameControl.cluster(
        direction=foundation.Direction.Client_to_Server
    )
    assert frc.is_cluster is True
    assert frc.is_general is False
    data = frc.serialize()

    assert data == b"\x01"
    assert not frc.is_manufacturer_specific
    frc.is_manufacturer_specific = False
    assert frc.serialize() == b"\x01"
    frc.is_manufacturer_specific = True
    assert frc.serialize() == b"\x05"

    frc = foundation.FrameControl.cluster(
        direction=foundation.Direction.Client_to_Server
    )
    assert frc.direction == foundation.Direction.Client_to_Server
    assert frc.serialize() == b"\x01"
    frc.direction = foundation.Direction.Client_to_Server
    assert frc.serialize() == b"\x01"
    frc.direction = foundation.Direction.Server_to_Client
    assert frc.serialize() == b"\x09"
    assert (
        foundation.FrameControl.cluster(
            direction=foundation.Direction.Server_to_Client
        ).serialize()
        == b"\x19"
    )

    frc = foundation.FrameControl.cluster(
        direction=foundation.Direction.Client_to_Server
    )
    assert not frc.disable_default_response
    assert frc.serialize() == b"\x01"
    frc.disable_default_response = False
    assert frc.serialize() == b"\x01"
    frc.disable_default_response = True
    assert frc.serialize() == b"\x11"


def test_frame_header():
    """Test frame header deserialization."""
    data = b"\x1c_\x11\xc0\n"
    extra = b"\xaa\xaa\x55\x55"
    hdr, rest = foundation.ZCLHeader.deserialize(data + extra)

    assert rest == extra
    assert hdr.command_id == 0x0A
    assert hdr.direction == foundation.Direction.Server_to_Client
    assert hdr.manufacturer == 0x115F
    assert hdr.tsn == 0xC0

    assert hdr.serialize() == data

    # check no manufacturer
    hdr.frame_control.is_manufacturer_specific = False
    assert hdr.serialize() == b"\x18\xc0\n"

    r = repr(hdr)
    assert isinstance(r, str)


def test_frame_header_general():
    """Test frame header general command."""
    (tsn, cmd_id, manufacturer) = (0x11, 0x15, 0x3344)

    hdr = foundation.ZCLHeader.general(tsn, cmd_id, manufacturer)
    assert hdr.frame_control.frame_type == foundation.FrameType.GLOBAL_COMMAND
    assert hdr.command_id == cmd_id
    assert hdr.tsn == tsn
    assert hdr.manufacturer == manufacturer
    assert hdr.frame_control.is_manufacturer_specific is True

    hdr.manufacturer = None
    assert hdr.manufacturer is None
    assert hdr.frame_control.is_manufacturer_specific is False


def test_frame_header_cluster():
    """Test frame header cluster command."""
    (tsn, cmd_id, manufacturer) = (0x11, 0x16, 0x3344)

    hdr = foundation.ZCLHeader.cluster(
        tsn=tsn, command_id=cmd_id, manufacturer=manufacturer
    )
    assert hdr.frame_control.frame_type == foundation.FrameType.CLUSTER_COMMAND
    assert hdr.command_id == cmd_id
    assert hdr.tsn == tsn
    assert hdr.manufacturer == manufacturer
    assert hdr.frame_control.is_manufacturer_specific is True

    hdr.manufacturer = None
    assert hdr.manufacturer is None
    assert hdr.frame_control.is_manufacturer_specific is False


def test_frame_header_disable_manufacturer_id():
    """Test frame header manufacturer ID can be disabled with NO_MANUFACTURER_ID."""

    hdr = foundation.ZCLHeader.cluster(tsn=123, command_id=0x12, manufacturer=None)
    assert hdr.manufacturer is None
    hdr.manufacturer = 0x1234
    assert hdr.manufacturer == 0x1234

    hdr.manufacturer = foundation.ZCLHeader.NO_MANUFACTURER_ID
    assert hdr.manufacturer is None

    hdr2 = foundation.ZCLHeader.cluster(
        tsn=123, command_id=0x12, manufacturer=foundation.ZCLHeader.NO_MANUFACTURER_ID
    )
    assert hdr2.manufacturer is None


def test_attribute_report():
    a = foundation.AttributeReportingConfig()
    a.direction = 0x01
    a.attrid = 0xAA55
    a.timeout = 900
    b = foundation.AttributeReportingConfig(a)
    assert a.attrid == b.attrid
    assert a.direction == b.direction
    assert a.timeout == b.timeout


def test_pytype_to_datatype_derived_enums():
    """Test pytype_to_datatype_id lookup for derived enums."""

    class e_1(t.enum8):
        pass

    class e_2(t.enum8):
        pass

    class e_3(t.enum16):
        pass

    enum8_id = foundation.DataType.from_python_type(t.enum8)
    enum16_id = foundation.DataType.from_python_type(t.enum16)

    assert foundation.DataType.from_python_type(e_1) == enum8_id
    assert foundation.DataType.from_python_type(e_2) == enum8_id
    assert foundation.DataType.from_python_type(e_3) == enum16_id
    assert foundation.DataType.from_python_type(e_2) == enum8_id
    assert foundation.DataType.from_python_type(e_3) == enum16_id


def test_pytype_to_datatype_derived_bitmaps():
    """Test pytype_to_datatype_id lookup for derived enums."""

    class b_1(t.bitmap8):
        pass

    class b_2(t.bitmap8):
        pass

    class b_3(t.bitmap16):
        pass

    bitmap8_id = foundation.DataType.from_python_type(t.bitmap8)
    bitmap16_id = foundation.DataType.from_python_type(t.bitmap16)

    assert foundation.DataType.from_python_type(b_1) == bitmap8_id
    assert foundation.DataType.from_python_type(b_2) == bitmap8_id
    assert foundation.DataType.from_python_type(b_3) == bitmap16_id
    assert foundation.DataType.from_python_type(b_2) == bitmap8_id
    assert foundation.DataType.from_python_type(b_3) == bitmap16_id


def test_ptype_to_datatype_lvlist():
    """Test pytype for Structure."""

    data = b"L\x06\x00\x10\x00!\xce\x0b!\xa8\x01$\x00\x00\x00\x00\x00!\xbdJ ]"
    extra = b"\xaa\x55extra\x00"

    result, rest = foundation.TypeValue.deserialize(data + extra)
    assert rest == extra
    assert (
        foundation.DataType.from_python_type(result.value.__class__)
        == foundation.DataType.struct
    )
    assert (
        foundation.DataType.from_python_type(foundation.ZCLStructure)
        == foundation.DataType.struct
    )

    class _Similar(t.LVList, item_type=foundation.TypeValue, length_type=t.uint16_t):
        pass

    assert foundation.DataType.from_python_type(_Similar) == foundation.DataType.unk


def test_ptype_to_datatype_notype():
    """Test pytype for NoData."""

    class ZigpyUnknown:
        pass

    assert foundation.DataType.from_python_type(ZigpyUnknown) == foundation.DataType.unk


def test_write_attrs_response_deserialize():
    """Test deserialization."""

    data = b"\x00"
    extra = b"\xaa\x55"
    r, rest = foundation.WriteAttributesResponse.deserialize(data + extra)
    assert len(r) == 1
    assert r[0].status == foundation.Status.SUCCESS
    assert rest == extra

    data = b"\x86\x34\x12\x87\x35\x12"
    r, rest = foundation.WriteAttributesResponse.deserialize(data + extra)
    assert len(r) == 2
    assert rest == extra
    assert r[0].status == foundation.Status.UNSUPPORTED_ATTRIBUTE
    assert r[0].attrid == 0x1234
    assert r[1].status == foundation.Status.INVALID_VALUE
    assert r[1].attrid == 0x1235


@pytest.mark.parametrize(
    ("attributes", "data"),
    [
        ({4: 0, 5: 0, 3: 0}, b"\x00"),
        ({4: 0, 5: 0, 3: 0x86}, b"\x86\x03\x00"),
        ({4: 0x87, 5: 0, 3: 0x86}, b"\x87\x04\x00\x86\x03\x00"),
        ({4: 0x87, 5: 0x86, 3: 0x86}, b"\x87\x04\x00\x86\x05\x00\x86\x03\x00"),
    ],
)
def test_write_attrs_response_serialize(attributes, data):
    """Test WriteAttributes Response serialization."""

    r = foundation.WriteAttributesResponse()
    for attr_id, status in attributes.items():
        rec = foundation.WriteAttributesStatusRecord()
        rec.status = status
        rec.attrid = attr_id
        r.append(rec)

    assert r.serialize() == data


def test_configure_reporting_response_deserialize():
    """Test deserialization."""

    data = b"\x00"
    r, rest = foundation.ConfigureReportingResponse.deserialize(data)
    assert len(r) == 1
    assert r[0].status == foundation.Status.SUCCESS
    assert r[0].direction is None
    assert r[0].attrid is None
    assert rest == b""

    data = b"\x00"
    extra = b"\x01\xaa\x55"
    r, rest = foundation.ConfigureReportingResponse.deserialize(data + extra)
    assert len(r) == 1
    assert r[0].status == foundation.Status.SUCCESS
    assert r[0].direction == foundation.ReportingDirection.ReceiveReports
    assert r[0].attrid == 0x55AA
    assert rest == b""

    data = b"\x86\x01\x34\x12\x87\x01\x35\x12"
    r, rest = foundation.ConfigureReportingResponse.deserialize(data)
    assert len(r) == 2
    assert rest == b""
    assert r[0].status == foundation.Status.UNSUPPORTED_ATTRIBUTE
    assert r[0].attrid == 0x1234
    assert r[1].status == foundation.Status.INVALID_VALUE
    assert r[1].attrid == 0x1235

    with pytest.raises(ValueError):
        foundation.ConfigureReportingResponse.deserialize(data + extra)


def test_configure_reporting_response_serialize_empty():
    r = foundation.ConfigureReportingResponse()

    # An empty configure reporting response doesn't make sense
    with pytest.raises(ValueError):
        r.serialize()


@pytest.mark.parametrize(
    ("attributes", "data"),
    [
        ({4: 0, 5: 0, 3: 0}, b"\x00"),
        ({4: 0, 5: 0, 3: 0x86}, b"\x86\x01\x03\x00"),
        ({4: 0x87, 5: 0, 3: 0x86}, b"\x87\x01\x04\x00\x86\x01\x03\x00"),
        (
            {4: 0x87, 5: 0x86, 3: 0x86},
            b"\x87\x01\x04\x00\x86\x01\x05\x00\x86\x01\x03\x00",
        ),
    ],
)
def test_configure_reporting_response_serialize(attributes, data):
    """Test ConfigureReporting Response serialization."""

    r = foundation.ConfigureReportingResponse()
    for attr_id, status in attributes.items():
        rec = foundation.ConfigureReportingResponseRecord()
        rec.status = status
        rec.direction = 0x01
        rec.attrid = attr_id
        r.append(rec)

    assert r.serialize() == data


def test_status_enum():
    """Test Status enums chaining."""
    status_names = [e.name for e in foundation.Status]
    aps_names = [e.name for e in t.APSStatus]
    nwk_names = [e.name for e in t.NWKStatus]
    mac_names = [e.name for e in t.MACStatus]

    status = foundation.Status(0x98)
    assert status.name in status_names
    assert status.name not in aps_names
    assert status.name not in nwk_names
    assert status.name not in mac_names

    status = foundation.Status(0xAE)
    assert status.name not in status_names
    assert status.name in aps_names
    assert status.name not in nwk_names
    assert status.name not in mac_names

    status = foundation.Status(0xD0)
    assert status.name not in status_names
    assert status.name not in aps_names
    assert status.name in nwk_names
    assert status.name not in mac_names

    status = foundation.Status(0xE9)
    assert status.name not in status_names
    assert status.name not in aps_names
    assert status.name not in nwk_names
    assert status.name in mac_names

    status = foundation.Status(0xFF)
    assert status.name not in status_names
    assert status.name not in aps_names
    assert status.name not in nwk_names
    assert status.name not in mac_names
    assert status.name == "undefined_0xff"


def test_schema():
    """Test schema parameter parsing"""

    bad_s = foundation.ZCLCommandDef(
        id=0x12,
        name="test",
        schema={
            "uh oh": t.uint16_t,
        },
        direction=foundation.Direction.Client_to_Server,
    )

    with pytest.raises(ValueError):
        bad_s.with_compiled_schema()

    s = foundation.ZCLCommandDef(
        id=0x12,
        name="test",
        schema={
            "foo": t.uint8_t,
            "bar?": t.uint16_t,
            "baz?": t.uint8_t,
        },
        direction=foundation.Direction.Client_to_Server,
    )
    s = s.with_compiled_schema()

    str(s)

    assert s.schema.foo.type is t.uint8_t
    assert not s.schema.foo.optional

    assert s.schema.bar.type is t.uint16_t
    assert s.schema.bar.optional

    assert s.schema.baz.type is t.uint8_t
    assert s.schema.baz.optional

    assert "test" in str(s) and "direction=<Direction.Client_to_Server" in str(s)

    for kwargs, value in [
        ({"foo": 1}, b"\x01"),
        ({"foo": 1, "bar": 2}, b"\x01\x02\x00"),
        ({"foo": 1, "bar": 2, "baz": 3}, b"\x01\x02\x00\x03"),
    ]:
        assert s.schema(**kwargs) == s.schema(*kwargs.values())
        assert s.schema(**kwargs).serialize() == value
        assert s.schema.deserialize(value) == (s.schema(**kwargs), b"")

    assert issubclass(s.schema, tuple)


def test_command_schema_error_on_tuple():
    """Test schema throwing an exception when a tuple is passed instead of a dict."""

    cmd_def = foundation.ZCLCommandDef(
        id=0x12,
        name="test",
        schema=(t.uint16_t,),
        direction=foundation.Direction.Client_to_Server,
    )

    with pytest.raises(ValueError):
        cmd_def.with_compiled_schema()


def test_zcl_attribute_definition():
    a = foundation.ZCLAttributeDef(
        id=0x1234,
        name="test",
        type=t.uint16_t,
        access="rw",
    )

    assert "0x1234" in str(a)
    assert "'test'" in str(a)
    assert "uint16_t" in str(a)
    assert not a.is_manufacturer_specific  # default
    assert a.access == (
        foundation.ZCLAttributeAccess.Read | foundation.ZCLAttributeAccess.Write
    )

    with pytest.raises(ValueError):
        a.replace(access="x")

    assert a.replace(access="w").access == foundation.ZCLAttributeAccess.Write


def test_invalid_command_def_name():
    command = foundation.ZCLCommandDef(
        id=0x12,
        name="test",
        schema={
            "foo": t.uint8_t,
        },
        direction=foundation.Direction.Client_to_Server,
    )

    with pytest.raises(ValueError):
        command.replace(name="bad name")

    with pytest.raises(ValueError):
        command.replace(name="123name")


def test_invalid_attribute_def_name():
    attr = foundation.ZCLAttributeDef(
        id=0x1234,
        name="test",
        type=t.uint16_t,
    )

    with pytest.raises(ValueError):
        attr.replace(name="bad name")

    with pytest.raises(ValueError):
        attr.replace(name="123name")


def test_zcl_attribute_access():
    A = foundation.ZCLAttributeAccess

    assert A.from_str("") == (A.NONE)
    assert A.from_str("r") == (A.Read)
    assert A.from_str("r*w") == (A.Read | A.Write_Optional)
    assert A.from_str("r*wp") == (A.Read | A.Write_Optional | A.Report)
    assert A.from_str("rp") == (A.Read | A.Report)
    assert A.from_str("rps") == (A.Read | A.Report | A.Scene)
    assert A.from_str("rs") == (A.Read | A.Scene)
    assert A.from_str("rw") == (A.Read | A.Write)
    assert A.from_str("rwp") == (A.Read | A.Write | A.Report)
    assert A.from_str("rws") == (A.Read | A.Write | A.Scene)

    with pytest.raises(ValueError):
        A.from_str("q")


def test_attribute_command_iteration():
    class Commands1(foundation.BaseCommandDefs):
        command1 = foundation.ZCLCommandDef(
            id=0x12,
            name="test",
            schema={
                "foo": t.uint8_t,
            },
            direction=foundation.Direction.Client_to_Server,
        )

    class Commands2(Commands1):
        command2 = foundation.ZCLCommandDef(
            id=0x12,
            name="test2",
            schema={
                "foo": t.uint8_t,
            },
            direction=foundation.Direction.Client_to_Server,
        )

    assert list(Commands1) == [Commands1.command1]
    assert list(Commands2) == [Commands2.command1, Commands2.command2]


def test_attribute_definition_backwards_compat():
    assert foundation.ZCLAttributeDef(0x1234, t.uint8_t) == foundation.ZCLAttributeDef(
        id=0x1234, type=t.uint8_t
    )
    assert foundation.ZCLAttributeDef("name", t.uint8_t) == foundation.ZCLAttributeDef(
        name="name", type=t.uint8_t
    )


def test_command_definition_backwards_compat():
    assert foundation.ZCLCommandDef(0x12, {}) == foundation.ZCLCommandDef(
        id=0x12, schema={}
    )
    assert foundation.ZCLCommandDef("name", {}) == foundation.ZCLCommandDef(
        name="name", schema={}
    )


def test_array():
    orig_data = data = bytes.fromhex(
        "183c010100004841040006000d0106000206010d0206000206020d0306000206030d04060002"
    )
    hdr, data = foundation.ZCLHeader.deserialize(data)

    command = foundation.GENERAL_COMMANDS[hdr.command_id]
    rsp, rest = command.schema.deserialize(data)

    assert rest == b""

    assert rsp.status_records == [
        foundation.ReadAttributeRecord(
            attrid=0x0001,
            status=foundation.Status.SUCCESS,
            value=foundation.Array(
                type=foundation.DataTypeId.octstr,
                value=t.LVList[t.LVBytes, t.uint16_t](
                    [
                        b"\x00\r\x01\x06\x00\x02",
                        b"\x01\r\x02\x06\x00\x02",
                        b"\x02\r\x03\x06\x00\x02",
                        b"\x03\r\x04\x06\x00\x02",
                    ]
                ),
            ),
        )
    ]

    assert orig_data == hdr.serialize() + rsp.serialize()
