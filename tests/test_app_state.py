"""Test unit for app status and counters."""

import pytest

import zigpy.application.state as app_state

COUNTER_NAMES = ["counter_1", "counter_2", "some random name"]


@pytest.fixture
def counters():
    """Counters fixture."""
    return app_state.Counters("ezsp_counters", COUNTER_NAMES)


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


def test_counters_init(counters):
    """Test counters initialization."""

    assert counters.name == "ezsp_counters"
    assert counters.list
    assert len(counters.list) == 3

    cnt_1, cnt_2, cnt_3 = counters.list
    assert cnt_1.name == "counter_1"
    assert cnt_2.name == "counter_2"
    assert cnt_3.name == "some random name"

    assert cnt_1.value == 0
    assert cnt_2.value == 0
    assert cnt_3.value == 0

    with pytest.raises(KeyError):
        counters["no such counter"]

    counters["some random name"] = 2
    assert cnt_3.value == 2
    assert counters["some random name"].value == 2
    assert counters["some random name"] == 2
    assert counters["some random name"] == cnt_3
    assert int(cnt_3) == 2

    assert "counter_2" in counters
    assert [counter.name for counter in counters] == COUNTER_NAMES

    with pytest.raises(KeyError):
        counters["no such counter"] = 2

    counters.reset()
    for counter in counters:
        assert counter.reset_count == 1

    existing = counters.add_counter("some random name")
    assert existing.value == 2
    assert len(counters.list) == 3

    new = counters.add_counter("new_counter", 42)
    assert new.value == 42
    assert len(counters.list) == 4


def test_counters_str_and_repr(counters):
    """Test counters str and repr."""

    counters["counter_1"] = 22
    counters["counter_2"] = 33

    assert (
        str(counters)
        == "ezsp_counters: [counter_1 = 22, counter_2 = 33, some random name = 0]"
    )

    assert (
        repr(counters) == """Counters('ezsp_counters', {Counter('counter_1', 22), """
        """Counter('counter_2', 33), Counter('some random name', 0)})"""
    )


def test_state():
    """Test state structure."""
    state = app_state.State()
    assert state
    assert state.counters == {}

    state.initialize_counters("new_collection", ("counter_2", "counter_3"))
    assert state.counters["new_collection"]["counter_2"] == 0
    assert state.counters["new_collection"]["counter_2"].reset_count == 0
    assert state.counters["new_collection"]["counter_3"].reset_count == 0
    state.counters["new_collection"]["counter_2"] = 2

    state.initialize_counters("new_collection", ("counter_2", "counter_3"))
    assert state.counters["new_collection"]["counter_2"] == 2
    assert state.counters["new_collection"]["counter_2"].reset_count == 1
    assert state.counters["new_collection"]["counter_3"] == 0
    assert state.counters["new_collection"]["counter_3"].reset_count == 1


def test_counters_reset(counters):
    """Test counter resetting."""

    counter = counters["counter_1"]

    assert counter.reset_count == 0
    counters["counter_1"] = 22
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


def test_counters_by_name(counters):
    """Test accessing individual counters by name."""
    counters["counter_2"] = 22
    counter = counters["counter_2"]
    assert counters.counter_2 is counter
    assert counter == 22
    assert counters.counter_2 == 22

    with pytest.raises(AttributeError):
        counters.no_such_counter


class NewCounter(app_state.Counter):
    pass


def test_counters_auto_create():
    """Test auto creation of counters."""

    counters = app_state.Counters(
        "new_counters",
        ("counter_x", "counter_y"),
        counter_class=NewCounter,
        auto_create=True,
    )

    assert "counter_x" in counters
    assert "counter_y" in counters
    assert "not_yet" not in counters
    assert "nor_this_one" not in counters

    counters["not_yet"] = 2
    # auto counter create only works when accessing by index
    with pytest.raises(AttributeError):
        new = counters.nor_this_one
        new.update(3)

    assert "not_yet" in counters
    assert "nor_this_one" not in counters
    assert counters["not_yet"].value == 2
    assert isinstance(counters["not_yet"], NewCounter)
