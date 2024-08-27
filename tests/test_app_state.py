"""Test unit for app status and counters."""

import pytest

import zigpy.state as app_state

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
    """Test counter increment."""

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

    tags = set(counters.tags())
    assert {"rx"} == tags

    tags = set(counters["rx"].tags())
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
    assert not list(groups)

    counter_group = groups["ezsp_counters"]

    new_groups = list(groups)
    assert new_groups == [counter_group]
