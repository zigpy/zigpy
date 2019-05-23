import zigpy.types as t
from zigpy.zcl import foundation


def test_typevalue():
    tv = foundation.TypeValue()
    tv.type = 0x20
    tv.value = t.uint8_t(99)
    ser = tv.serialize()
    r = repr(tv)
    assert r.startswith('<') and r.endswith('>')
    assert 'type=uint8_t' in r
    assert 'value=99' in r

    tv2, data = foundation.TypeValue.deserialize(ser)
    assert data == b''
    assert tv2.type == tv.type
    assert tv2.value == tv.value


def test_read_attribute_record():
    orig = b'\x00\x00\x00\x20\x99'
    rar, data = foundation.ReadAttributeRecord.deserialize(orig)
    assert data == b''
    assert rar.status == 0
    assert isinstance(rar.value, foundation.TypeValue)
    assert isinstance(rar.value.value, t.uint8_t)
    assert rar.value.value == 0x99

    r = repr(rar)
    assert len(r) > 5
    assert r.startswith('<') and r.endswith('>')

    ser = rar.serialize()
    assert ser == orig


def test_attribute_reporting_config_0():
    arc = foundation.AttributeReportingConfig()
    arc.direction = 0
    arc.attrid = 99
    arc.datatype = 0x20
    arc.min_interval = 10
    arc.max_interval = 20
    arc.reportable_change = 30
    ser = arc.serialize()

    arc2, data = foundation.AttributeReportingConfig.deserialize(ser)
    assert data == b''
    assert arc2.direction == arc.direction
    assert arc2.attrid == arc.attrid
    assert arc2.datatype == arc.datatype
    assert arc2.min_interval == arc.min_interval
    assert arc2.max_interval == arc.max_interval
    assert arc.reportable_change == arc.reportable_change


def test_attribute_reporting_config_1():
    arc = foundation.AttributeReportingConfig()
    arc.direction = 1
    arc.attrid = 99
    arc.timeout = 0x7e
    ser = arc.serialize()

    arc2, data = foundation.AttributeReportingConfig.deserialize(ser)
    assert data == b''
    assert arc2.direction == arc.direction
    assert arc2.timeout == arc.timeout


def test_typed_collection():
    tc = foundation.TypedCollection()
    tc.type = 0x20
    tc.value = t.LVList(t.uint8_t)([t.uint8_t(i) for i in range(100)])
    ser = tc.serialize()

    assert len(ser) == 1 + 1 + 100  # type, length, values

    tc2, data = foundation.TypedCollection.deserialize(ser)

    assert tc2.type == 0x20
    assert tc2.value == list(range(100))


def test_write_attribute_status_record():
    attr_id = b'\x01\x00'
    extra = b'12da-'
    res, d = foundation.WriteAttributesStatusRecord.deserialize(
        b'\x00' + attr_id + extra)
    assert res.status == foundation.Status.SUCCESS
    assert res.attrid is None
    assert d == attr_id + extra
    r = repr(res)
    assert r.startswith(
        '<' + foundation.WriteAttributesStatusRecord.__name__)
    assert 'status' in r
    assert 'attrid' not in r

    res, d = foundation.WriteAttributesStatusRecord.deserialize(
        b'\x87' + attr_id + extra)
    assert res.status == foundation.Status.INVALID_VALUE
    assert res.attrid == 0x0001
    assert d == extra

    r = repr(res)
    assert 'status' in r
    assert 'attrid' in r

    rec = foundation.WriteAttributesStatusRecord(
        foundation.Status.SUCCESS, 0xaabb
    )
    assert rec.serialize() == b'\x00'
    rec.status = foundation.Status.UNSUPPORTED_ATTRIBUTE
    assert rec.serialize()[0:1] == foundation.Status.UNSUPPORTED_ATTRIBUTE.serialize()
    assert rec.serialize()[1:] == b'\xbb\xaa'


def test_configure_reporting_response_serialization():
    direction_attr_id = b'\x00\x01\x10'
    extra = b'12da-'
    res, d = foundation.ConfigureReportingResponseRecord.deserialize(
        b'\x00' + direction_attr_id + extra)
    assert res.status == foundation.Status.SUCCESS
    assert res.direction is None
    assert res.attrid is None
    assert d == direction_attr_id + extra
    r = repr(res)
    assert r.startswith(
        '<' + foundation.ConfigureReportingResponseRecord.__name__)
    assert 'status' in r
    assert 'direction' not in r
    assert 'attrid' not in r

    res, d = foundation.ConfigureReportingResponseRecord.deserialize(
        b'\x8c' + direction_attr_id + extra)
    assert res.status == foundation.Status.UNREPORTABLE_ATTRIBUTE
    assert res.direction is not None
    assert res.attrid == 0x1001
    assert d == extra

    r = repr(res)
    assert 'status' in r
    assert 'direction' in r
    assert 'attrid' in r

    rec = foundation.ConfigureReportingResponseRecord(
        foundation.Status.SUCCESS, 0x00, 0xaabb
    )
    assert rec.serialize() == b'\x00'
    rec.status = foundation.Status.UNREPORTABLE_ATTRIBUTE
    assert rec.serialize()[0:1] == foundation.Status.UNREPORTABLE_ATTRIBUTE.serialize()
    assert rec.serialize()[1:] == b'\x00\xbb\xaa'
