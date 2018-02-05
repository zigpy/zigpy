import zigpy.types as t
from zigpy.zcl import foundation


def test_typevalue():
    tv = foundation.TypeValue()
    tv.type = 0x20
    tv.value = t.uint8_t(99)
    ser = tv.serialize()

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
