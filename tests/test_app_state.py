"""Test unit for app status and counters."""

import pytest

import zigpy.state as app_state
import zigpy.types as t
import zigpy.zdo.types as zdo_t

COUNTER_NAMES = ["counter_1", "counter_2", "some random name"]


@pytest.fixture
def counters():
    """Counters fixture."""
    counters = app_state.CounterGroup("ezsp_counters")
    for name in COUNTER_NAMES:
        counters[name]
    return counters


def test_counter():
    """Test basic counter."""

    counter = app_state.Counter("mock_counter")
    assert counter.value == 0

    counter = app_state.Counter("mock_counter", 5)
    assert counter.value == 5
    assert counter.reset_count == 0

    counter.update(5)
    assert counter.value == 5
    assert counter.reset_count == 0

    counter.update(8)
    assert counter.value == 8
    assert counter.reset_count == 0

    counter.update(9)
    assert counter.value == 9
    assert counter.reset_count == 0

    counter.reset()
    assert counter.value == 9
    assert counter._raw_value == 0
    assert counter.reset_count == 1

    # new value after a counter was reset/clear
    counter.update(12)
    assert counter.value == 21
    assert counter.reset_count == 1

    counter.update(15)
    assert counter.value == 24
    assert counter.reset_count == 1

    # new counter value is less than previously reported.
    # assume counter was reset
    counter.update(14)
    assert counter.value == 24 + 14
    assert counter.reset_count == 2

    counter.reset_and_update(14)
    assert counter.value == 38 + 14
    assert counter.reset_count == 3


def test_counter_str():
    """Test counter str representation."""

    counter = app_state.Counter("some_counter", 8)
    assert str(counter) == "some_counter = 8"


def test_counters_init():
    """Test counters initialization."""

    counter_groups = app_state.CounterGroups()
    assert len(counter_groups) == 0
    counters = counter_groups["ezsp_counters"]
    assert len(counter_groups) == 1

    assert len(counters) == 0
    assert counters.name == "ezsp_counters"
    for name in COUNTER_NAMES:
        counters[name]
    assert len(counters) == 3

    cnt_1, cnt_2, cnt_3 = (counter for counter in counters.counters())
    assert cnt_1.name == "counter_1"
    assert cnt_2.name == "counter_2"
    assert cnt_3.name == "some random name"

    assert cnt_1.value == 0
    assert cnt_2.value == 0
    assert cnt_3.value == 0

    counters["some random name"].update(2)
    assert cnt_3.value == 2
    assert counters["some random name"].value == 2
    assert counters["some random name"] == 2
    assert counters["some random name"] == cnt_3
    assert int(cnt_3) == 2

    assert "counter_2" in counters
    assert [counter.name for counter in counters.counters()] == COUNTER_NAMES

    counters.reset()
    for counter in counters.counters():
        assert counter.reset_count == 1


def test_counters_str_and_repr(counters):
    """Test counters str and repr."""

    counters["counter_1"].update(22)
    counters["counter_2"].update(33)

    assert (
        str(counters)
        == "ezsp_counters: [counter_1 = 22, counter_2 = 33, some random name = 0]"
    )

    assert (
        repr(counters)
        == """CounterGroup('ezsp_counters', {Counter('counter_1', 22), """
        """Counter('counter_2', 33), Counter('some random name', 0)})"""
    )


def test_state():
    """Test state structure."""
    state = app_state.State()
    assert state
    assert state.counters == {}

    assert state.counters["new_collection"]["counter_2"] == 0
    assert state.counters["new_collection"]["counter_2"].reset_count == 0
    assert state.counters["new_collection"]["counter_3"].reset_count == 0
    state.counters["new_collection"]["counter_2"] = 2


def test_counters_reset(counters):
    """Test counter resetting."""

    counter = counters["counter_1"]

    assert counter.reset_count == 0
    counters["counter_1"].update(22)
    assert counter.value == 22
    assert counter.reset_count == 0

    counters.reset()
    assert counter.reset_count == 1
    counter.update(22)
    assert counter.value == 44
    assert counter.reset_count == 1


def test_counter_incr():
    """Test counter incement."""

    counter = app_state.Counter("counter_name", 42)
    assert counter == 42

    counter.increment()
    assert counter == 43

    counter.increment(5)
    assert counter == 48
    assert counter.value == 48

    with pytest.raises(AssertionError):
        counter.increment(-1)


def test_counter_nested_groups_increment():
    """Test nested counters."""

    counters = app_state.CounterGroup("device_counters")

    assert len(counters) == 0
    counters.increment("reply", "rx", "zdo", 0x8031)
    counters.increment("total", "rx", 3, 0x0006)
    counters.increment("total", "rx", 3, 0x0008)
    counters.increment("total", "rx", 3, 0x0300)

    tags = {t for t in counters.tags()}
    assert {"rx"} == tags

    tags = {t for t in counters["rx"].tags()}
    assert {"zdo", 3} == tags

    assert counters["rx"]["reply"] == 1
    assert counters["rx"]["zdo"]["reply"] == 1
    assert counters["rx"]["zdo"][0x8031]["reply"] == 1

    assert counters["rx"]["total"] == 3
    assert counters["rx"][3]["total"] == 3
    assert counters["rx"][3][0x0006]["total"] == 1
    assert counters["rx"][3][0x0008]["total"] == 1
    assert counters["rx"][3][0x0300]["total"] == 1


def test_counter_groups():
    """Test CounterGroups."""

    groups = app_state.CounterGroups()
    assert not [group for group in groups]

    counter_group = groups["ezsp_counters"]

    new_groups = [group for group in groups]
    assert new_groups == [counter_group]


@pytest.fixture
def node_info():
    return app_state.NodeInfo(
        nwk=t.NWK(0x0000),
        ieee=t.EUI64.convert("93:2C:A9:34:D9:D0:5D:12"),
        logical_type=zdo_t.LogicalType.Coordinator,
    )


@pytest.fixture
def network_info(node_info):
    return app_state.NetworkInfo(
        extended_pan_id=t.ExtendedPanId.convert("0D:49:91:99:AE:CD:3C:35"),
        pan_id=t.PanId(0x9BB0),
        nwk_update_id=0x12,
        nwk_manager_id=t.NWK(0x0000),
        channel=t.uint8_t(15),
        channel_mask=t.Channels.from_channel_list([15, 20, 25]),
        security_level=t.uint8_t(5),
        network_key=app_state.Key(
            key=t.KeyData.convert("9A:79:D6:9A:DA:EC:45:C6:F2:EF:EB:AF:DA:A3:07:B6"),
            seq=108,
            tx_counter=39009277,
        ),
        tc_link_key=app_state.Key(
            key=t.KeyData(b"ZigBeeAlliance09"),
            partner_ieee=node_info.ieee,
            tx_counter=8712428,
        ),
        key_table=[
            app_state.Key(
                key=t.KeyData.convert(
                    "85:7C:05:00:3E:76:1A:F9:68:9A:49:41:6A:60:5C:76"
                ),
                tx_counter=3792973670,
                rx_counter=1083290572,
                seq=147,
                partner_ieee=t.EUI64.convert("69:0C:07:52:AA:D7:7D:71"),
            ),
            app_state.Key(
                key=t.KeyData.convert(
                    "CA:02:E8:BB:75:7C:94:F8:93:39:D3:9C:B3:CD:A7:BE"
                ),
                tx_counter=2597245184,
                rx_counter=824424412,
                seq=19,
                partner_ieee=t.EUI64.convert("A3:1A:F6:8E:19:95:23:BE"),
            ),
        ],
        children=[
            # Has a key
            t.EUI64.convert("A3:1A:F6:8E:19:95:23:BE"),
            # Does not have a key
            t.EUI64.convert("C6:DF:28:F9:60:33:DB:03"),
        ],
        # If exposed by the stack, NWK addresses of other connected devices on the network
        nwk_addresses={
            # Two children above
            t.EUI64.convert("A3:1A:F6:8E:19:95:23:BE"): t.NWK(0x2C59),
            t.EUI64.convert("C6:DF:28:F9:60:33:DB:03"): t.NWK(0x1CA0),
            # Random devices on the network
            t.EUI64.convert("7A:BF:38:A9:59:21:A0:7A"): t.NWK(0x16B5),
            t.EUI64.convert("10:55:FE:67:24:EA:96:D3"): t.NWK(0xBFB9),
            t.EUI64.convert("9A:0E:10:50:00:1B:1A:5F"): t.NWK(0x1AF6),
        },
        stack_specific={"zstack": {"tclk_seed": "71e31105bb92a2d15747a0d0a042dbfd"}},
        metadata={"zstack": {"version": "20220102"}},
    )


def test_state_backup_restore_unchanged(network_info, node_info):
    obj = app_state.network_state_to_json(
        network_info=network_info, node_info=node_info
    )
    network_info2, node_info2 = app_state.json_to_network_state(obj)

    assert node_info == node_info2
    assert network_info == network_info2
