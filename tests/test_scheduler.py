import asyncio

import pytest

from zigpy import scheduler
from zigpy.exceptions import (
    DeliveryError,
    FailureScope,
    NetworkBusyError,
    RadioBusyError,
    SendCancelledError,
    SupersededError,
    TransactionExpiredError,
    TransientSendError,
)
import zigpy.types as t

SENT = scheduler.SendStage.SENT
CONFIRMED = scheduler.SendStage.CONFIRMED
REPLIED = scheduler.SendStage.REPLIED


def make_packet(nwk=0x1234, data=b"data", key=None, priority=None, tsn=0x01):
    return t.ZigbeePacket(
        src=t.AddrModeAddress(addr_mode=t.AddrMode.NWK, address=t.NWK(0x0000)),
        src_ep=1,
        dst=t.AddrModeAddress(addr_mode=t.AddrMode.NWK, address=t.NWK(nwk)),
        dst_ep=1,
        tsn=tsn,
        profile_id=0x0104,
        cluster_id=0x0006,
        data=t.SerializableBytes(data),
        priority=priority,
        coalesce_key=key,
    )


class FakeRadio:
    """A radio whose per-send behavior is scripted via `effects`.

    Each send pops the next effect: `None` succeeds, an exception is raised, and an
    async callable is awaited (e.g. to hold a send in flight on `gate`).
    """

    def __init__(self):
        self.sent = []
        self.options = []
        self.times = []
        self.effects = []
        self.gate = asyncio.Event()
        self.in_progress = 0
        self.max_in_progress = 0
        self.cancelled = 0

    async def send_packet(self, packet):
        self.sent.append(packet)
        self.options.append(packet.tx_options)
        self.times.append(asyncio.get_running_loop().time())

        self.in_progress += 1
        self.max_in_progress = max(self.max_in_progress, self.in_progress)

        try:
            effect = self.effects.pop(0) if self.effects else None

            if callable(effect):
                await effect(packet)
            elif effect is not None:
                raise effect
        finally:
            self.in_progress -= 1

    async def hold(self, packet):
        try:
            await self.gate.wait()
        except asyncio.CancelledError:
            # A radio's own cleanup (e.g. a wire-level send cancellation) runs here
            self.cancelled += 1
            raise


@pytest.fixture
async def make_scheduler():
    created = []

    def factory(**kwargs):
        radio = FakeRadio()
        sched = scheduler.SendScheduler(radio.send_packet, **kwargs)
        created.append(sched)
        return sched, radio

    yield factory

    for sched in created:
        sched.stop()


@pytest.mark.parametrize(
    ("final_stage", "resolutions", "expected"),
    [
        # A confirmed success back-fills the sent stage
        (CONFIRMED, [(CONFIRMED, None)], {SENT: None, CONFIRMED: None}),
        # An error at the first stage forward-fills every later stage
        (
            REPLIED,
            [(SENT, DeliveryError("x"))],
            {SENT: DeliveryError, CONFIRMED: DeliveryError, REPLIED: DeliveryError},
        ),
        # The first write to a stage wins, but a late error still fails the rest
        (
            CONFIRMED,
            [(SENT, None), (SENT, DeliveryError("x"))],
            {SENT: None, CONFIRMED: DeliveryError},
        ),
        # A sent success followed by a confirmed error
        (
            CONFIRMED,
            [(SENT, None), (CONFIRMED, DeliveryError("x"))],
            {SENT: None, CONFIRMED: DeliveryError},
        ),
        # A reply value back-fills the earlier stages with success, not the value
        (
            REPLIED,
            [(REPLIED, "reply")],
            {SENT: None, CONFIRMED: None, REPLIED: "reply"},
        ),
    ],
)
async def test_send_slot_write_rules(final_stage, resolutions, expected):
    """Test the slot's write-once staged resolution rules."""
    slot = scheduler.SendSlot(final_stage)

    for stage, result in resolutions:
        slot.resolve(stage, result)

    for stage in scheduler.SendStage:
        if stage > final_stage:
            continue

        if stage not in expected:
            assert not slot.is_resolved(stage)
            continue

        assert slot.is_resolved(stage)
        value = expected[stage]

        if isinstance(value, type) and issubclass(value, BaseException):
            with pytest.raises(value):
                await slot.wait(stage)
        else:
            assert (await slot.wait(stage)) == value


async def test_submit_success(make_scheduler):
    """Test a simple send resolving all stages."""
    sched, radio = make_scheduler()

    handle = sched.submit(make_packet())
    assert handle.state in (scheduler.SendState.QUEUED, scheduler.SendState.IN_FLIGHT)

    await handle
    await handle.sent()
    await handle.confirmed()

    assert handle.state is scheduler.SendState.DONE
    assert handle.park_reason is None
    assert len(radio.sent) == 1
    assert radio.sent[0].data.serialize() == b"data"


async def test_supersession(make_scheduler):
    """Test queued same-key sends superseding one another in place."""
    sched, radio = make_scheduler(max_in_flight=1)
    radio.effects = [radio.hold]

    # Occupy the only in-flight slot so subsequent sends stay queued
    blocker = sched.submit(make_packet(nwk=0x0001))
    await asyncio.sleep(0.01)

    h1 = sched.submit(make_packet(data=b"first", key=("k",)))
    h2 = sched.submit(make_packet(data=b"second", key=("k",)))
    h3 = sched.submit(make_packet(data=b"third", key=("k",)))

    with pytest.raises(SupersededError):
        await h1

    with pytest.raises(SupersededError):
        await h2

    assert h1.state is scheduler.SendState.DONE
    assert h1.park_reason is None

    radio.gate.set()
    await blocker
    await h3

    # Only the blocker and the final version of the coalesced send reached the radio
    assert [p.data.serialize() for p in radio.sent] == [b"data", b"third"]


async def test_supersession_keeps_queue_position(make_scheduler):
    """Test that a trickle of superseding sends cannot starve the coalesced entry."""
    sched, radio = make_scheduler(max_in_flight=1)
    radio.effects = [radio.hold]

    blocker = sched.submit(make_packet(nwk=0x0001))
    await asyncio.sleep(0.01)

    # The coalesced send is submitted first, then unrelated contention piles up
    first = sched.submit(make_packet(nwk=0x000A, data=b"v1", key=("k",)))
    others = [sched.submit(make_packet(nwk=i, tsn=i)) for i in range(0x000B, 0x000F)]

    # A steady trickle of supersessions must not push it back in the queue
    for i in range(2, 5):
        newest = sched.submit(make_packet(nwk=0x000A, data=b"v%d" % i, key=("k",)))

    radio.gate.set()
    await blocker
    await asyncio.gather(newest, *others)

    with pytest.raises(SupersededError):
        await first

    # The coalesced send dispatched at the *first* submission's queue position,
    # ahead of the contention submitted after it, carrying the newest payload
    assert radio.sent[1].data.serialize() == b"v4"
    assert [p.dst.address for p in radio.sent[2:]] == [0x000B, 0x000C, 0x000D, 0x000E]


async def test_supersession_does_not_replace_in_flight(make_scheduler):
    """Test that an in-flight send is never superseded."""
    sched, radio = make_scheduler()
    radio.effects = [radio.hold]

    h1 = sched.submit(make_packet(data=b"first", key=("k",)))
    await asyncio.sleep(0.01)
    assert h1.state is scheduler.SendState.IN_FLIGHT

    h2 = sched.submit(make_packet(data=b"second", key=("k",)))
    radio.gate.set()

    await h1
    await h2

    assert [p.data.serialize() for p in radio.sent] == [b"first", b"second"]


async def test_retry_superseded_while_in_flight(make_scheduler):
    """Test a failed send's retry being superseded by a newer same-key send."""
    sched, radio = make_scheduler(retry_delay=0.01, max_in_flight=1)

    async def gated_fail(packet):
        await radio.gate.wait()
        raise DeliveryError("nope")

    radio.effects = [gated_fail]

    h1 = sched.submit(make_packet(data=b"first", key=("k",)), retries=3)
    await asyncio.sleep(0.01)

    # A newer send with the same key arrives while the first is in flight and stays
    # queued behind it
    h2 = sched.submit(make_packet(data=b"second", key=("k",)))
    radio.gate.set()

    # The first send's retry is abandoned in favor of the newer send
    with pytest.raises(SupersededError):
        await h1

    await h2
    assert [p.data.serialize() for p in radio.sent] == [b"first", b"second"]


async def test_cancel_queued(make_scheduler):
    """Test guaranteed cancellation of a queued send."""
    sched, radio = make_scheduler(max_in_flight=1)
    radio.effects = [radio.hold]

    blocker = sched.submit(make_packet(nwk=0x0001))
    await asyncio.sleep(0.01)

    handle = sched.submit(make_packet())
    assert handle.cancel()
    assert not handle.cancel()

    with pytest.raises(SendCancelledError):
        await handle

    radio.gate.set()
    await blocker
    assert len(radio.sent) == 1


async def test_cancel_in_flight_is_best_effort(make_scheduler):
    """Test that cancelling an in-flight send cancels the attempt for radio cleanup."""
    sched, radio = make_scheduler()
    radio.effects = [radio.hold]

    handle = sched.submit(make_packet())
    await asyncio.sleep(0.01)

    assert handle.state is scheduler.SendState.IN_FLIGHT
    assert handle.cancel()

    with pytest.raises(SendCancelledError):
        await handle

    # The attempt was cancelled inside the radio, triggering its own cleanup
    assert radio.cancelled == 1
    assert not handle.cancel()


async def test_staged_sent_stage(make_scheduler):
    """Test a staged radio resolving the sent stage ahead of the delivery verdict."""
    sched, radio = make_scheduler()

    async def sent_then_gate(packet):
        sched.resolve_sent(packet)
        await radio.gate.wait()

    radio.effects = [sent_then_gate]

    handle = sched.submit(make_packet())
    await asyncio.wait_for(handle.sent(), 1)
    assert handle.state is scheduler.SendState.IN_FLIGHT

    radio.gate.set()
    await handle.confirmed()

    # An unknown packet is ignored
    sched.resolve_sent(make_packet())


async def test_transient_backpressure_consumes_no_attempts(make_scheduler):
    """Test transient rejections re-parking the frame without consuming retries."""
    sched, radio = make_scheduler()
    radio.effects = [
        RadioBusyError("full", retry_in=0.01),
        RadioBusyError("full", retry_in=0.01),
        None,
    ]

    handle = sched.submit(make_packet(), retries=0)
    await handle

    assert len(radio.sent) == 3


async def test_wake_on_confirm(make_scheduler):
    """Test a slot-exhaustion block clearing on the next completion, not the timer."""
    sched, radio = make_scheduler(max_in_flight=2)
    loop = asyncio.get_running_loop()

    radio.effects = [radio.hold, RadioBusyError("full", retry_in=60), None]

    blocker = sched.submit(make_packet(nwk=0x0001))
    rejected = sched.submit(make_packet(nwk=0x0002))
    await asyncio.sleep(0.01)

    start = loop.time()
    radio.gate.set()
    await blocker
    await asyncio.wait_for(rejected, 1)

    # The rejected send retried as soon as the blocker completed, not after 60s
    assert loop.time() - start < 1


async def test_network_busy_backoff_is_timed(make_scheduler):
    """Test channel congestion waiting out its backoff."""
    sched, radio = make_scheduler()
    radio.effects = [NetworkBusyError("busy", retry_in=0.1), None]

    handle = sched.submit(make_packet())
    await handle

    assert len(radio.sent) == 2
    assert radio.times[1] - radio.times[0] >= 0.09


async def test_transient_destination_scope(make_scheduler):
    """Test destination-scoped backpressure only blocking that destination."""
    sched, radio = make_scheduler()
    radio.effects = [
        TransientSendError("hold on", scope=FailureScope.DESTINATION, retry_in=0.1),
        None,
        None,
    ]

    blocked = sched.submit(make_packet(nwk=0x0001))
    await asyncio.sleep(0.01)

    # Liveness from a blocked destination with nothing awaiting wake is a no-op
    sched.destination_seen(
        t.AddrModeAddress(addr_mode=t.AddrMode.NWK, address=t.NWK(0x0001))
    )

    other = sched.submit(make_packet(nwk=0x0002))
    await other

    # The other destination was not affected by the block
    assert blocked.state is not scheduler.SendState.DONE
    assert blocked.park_reason is scheduler.ParkReason.DESTINATION_BLOCKED

    await asyncio.wait_for(blocked, 1)
    assert len(radio.sent) == 3

    # Lane-scoped backpressure says nothing about radio capacity
    assert sched._window == sched.max_in_flight


async def test_broadcast_domain_rate_limit(make_scheduler):
    """Test all broadcast traffic sharing one rate-limited scheduling domain."""
    sched, radio = make_scheduler()
    loop = asyncio.get_running_loop()

    broadcast = make_packet().replace(
        dst=t.AddrModeAddress(
            addr_mode=t.AddrMode.Broadcast,
            address=t.BroadcastAddress.ALL_ROUTERS_AND_COORDINATOR,
        )
    )
    groupcast = make_packet().replace(
        dst=t.AddrModeAddress(addr_mode=t.AddrMode.Group, address=t.Group(0x0002))
    )

    # The firmware's broadcast budget rejects with an exact retry hint
    radio.effects = [
        TransientSendError(
            "rate limited", scope=FailureScope.DESTINATION, retry_in=0.1
        ),
        None,
        None,
        None,
    ]

    start = loop.time()
    h_broadcast = sched.submit(broadcast)
    await asyncio.sleep(0.01)

    # A groupcast contends for the same budget: it defers instead of probing
    h_group = sched.submit(groupcast)
    await asyncio.sleep(0.01)
    assert h_group.park_reason is scheduler.ParkReason.DESTINATION_BLOCKED

    # Unicasts are unaffected by the broadcast domain block
    await sched.submit(make_packet(nwk=0x0001))
    assert len(radio.sent) == 2

    await asyncio.gather(h_broadcast, h_group)

    # The rejected broadcast retried no earlier than the firmware's promise
    assert radio.times[2] - start >= 0.09
    assert sched._window == sched.max_in_flight


async def test_awaiting_wake(make_scheduler):
    """Test frames parking until the sleepy destination is heard from."""
    sched, radio = make_scheduler()
    radio.effects = [TransactionExpiredError("no poll"), None]

    handle = sched.submit(make_packet(nwk=0xABCD))
    await asyncio.sleep(0.01)

    assert handle.park_reason is scheduler.ParkReason.AWAITING_WAKE

    # Liveness from an unrelated destination does nothing
    sched.destination_seen(
        t.AddrModeAddress(addr_mode=t.AddrMode.NWK, address=t.NWK(0x9999))
    )
    await asyncio.sleep(0.01)
    assert handle.park_reason is scheduler.ParkReason.AWAITING_WAKE

    sched.destination_seen(
        t.AddrModeAddress(addr_mode=t.AddrMode.NWK, address=t.NWK(0xABCD))
    )
    await asyncio.wait_for(handle, 1)
    assert len(radio.sent) == 2


@pytest.mark.parametrize("retries", [0, 2])
async def test_delivery_failure_retries(make_scheduler, retries):
    """Test delivery failures consuming attempts and forcing route discovery."""
    sched, radio = make_scheduler(retry_delay=0.01)
    radio.effects = [DeliveryError("nope")] * 10

    # The coalesce key is re-registered across retries
    handle = sched.submit(make_packet(key=("k",)), retries=retries)

    with pytest.raises(DeliveryError):
        await handle

    assert len(radio.sent) == retries + 1

    # Every retry attempt forces route discovery
    for options in radio.options[1:]:
        assert t.TransmitOptions.FORCE_ROUTE_DISCOVERY in options


async def test_priority_ordering(make_scheduler):
    """Test queued sends dispatching in priority order, FIFO within a priority."""
    sched, radio = make_scheduler(max_in_flight=1)
    radio.effects = [radio.hold]

    blocker = sched.submit(make_packet(nwk=0x0001, tsn=0x00))
    await asyncio.sleep(0.01)

    handles = [
        sched.submit(make_packet(tsn=0x10, priority=t.PacketPriority.NORMAL)),
        sched.submit(make_packet(tsn=0x11, priority=t.PacketPriority.LOW)),
        sched.submit(make_packet(tsn=0x12, priority=t.PacketPriority.CRITICAL)),
        sched.submit(make_packet(tsn=0x13, priority=t.PacketPriority.HIGH)),
        sched.submit(make_packet(tsn=0x14, priority=t.PacketPriority.NORMAL)),
    ]

    radio.gate.set()
    await blocker
    await asyncio.gather(*handles)

    assert [p.tsn for p in radio.sent[1:]] == [0x12, 0x13, 0x10, 0x14, 0x11]


async def test_expiry(make_scheduler):
    """Test a queued send expiring before dispatch."""
    sched, radio = make_scheduler(max_in_flight=1)
    radio.effects = [radio.hold]
    loop = asyncio.get_running_loop()

    blocker = sched.submit(make_packet(nwk=0x0001))
    await asyncio.sleep(0.01)

    handle = sched.submit(make_packet(), expires_at=loop.time() - 1)
    radio.gate.set()
    await blocker

    with pytest.raises(SendCancelledError):
        await handle

    assert len(radio.sent) == 1


async def test_window_clamp_and_growth(make_scheduler):
    """Test the adaptive window shrinking on rejection and growing on completion."""
    sched, radio = make_scheduler(max_in_flight=4)
    radio.effects = [RadioBusyError("full", retry_in=0.01), None]

    handle = sched.submit(make_packet())
    await handle

    # Clamped to 1 by the rejection, then grown by the completed attempt
    assert sched._window == 2

    assert sched.max_in_flight == 4
    sched.max_in_flight = 16
    assert sched.max_in_flight == 16
    assert sched._window == 16


async def test_stop_fails_pending_sends(make_scheduler):
    """Test stopping the scheduler failing every unresolved send."""
    sched, radio = make_scheduler(max_in_flight=1)
    radio.effects = [radio.hold]

    in_flight = sched.submit(make_packet(nwk=0x0001))
    await asyncio.sleep(0.01)
    queued = sched.submit(make_packet(nwk=0x0002))

    sched.stop()

    with pytest.raises(SendCancelledError):
        await in_flight

    with pytest.raises(SendCancelledError):
        await queued

    # The scheduler restarts lazily on the next submit
    handle = sched.submit(make_packet(nwk=0x0003))
    await handle
    assert radio.sent[-1].dst.address == 0x0003


async def test_destination_window(make_scheduler):
    """Test the per-destination in-flight window."""
    sched, radio = make_scheduler(destination_window=1)

    async def slow(packet):
        await asyncio.sleep(0.02)

    radio.effects = [slow] * 6

    same = [sched.submit(make_packet(nwk=0x0001, tsn=i)) for i in range(3)]
    await asyncio.gather(*same)
    assert radio.max_in_progress == 1

    radio.max_in_progress = 0
    radio.in_progress = 0
    different = [sched.submit(make_packet(nwk=i, tsn=i)) for i in range(1, 4)]
    await asyncio.gather(*different)
    assert radio.max_in_progress == 3


async def test_unexpected_exception_is_terminal(make_scheduler):
    """Test a non-delivery exception resolving the send instead of stranding it."""
    sched, radio = make_scheduler()
    radio.effects = [RuntimeError("radio exploded")] * 5

    handle = sched.submit(make_packet(), retries=3)

    with pytest.raises(RuntimeError):
        await handle

    # Terminal: no retries were attempted
    assert len(radio.sent) == 1


async def test_replied_stage(make_scheduler):
    """Test the reply stage being resolved by the response-matching layer."""
    sched, radio = make_scheduler()

    handle = sched.submit(make_packet(), expect_reply=True)
    await handle.confirmed()

    assert not handle._slot.is_resolved(REPLIED)
    handle.resolve_reply("the reply")

    assert (await handle) == "the reply"
    assert (await handle.replied()) == "the reply"


async def test_replied_stage_error_propagates(make_scheduler):
    """Test a delivery error resolving the reply stage too."""
    sched, radio = make_scheduler()
    radio.effects = [DeliveryError("nope")]

    handle = sched.submit(make_packet(), expect_reply=True, retries=0)

    with pytest.raises(DeliveryError):
        await handle


async def test_superseded_handle_state(make_scheduler):
    """Test a superseded handle reporting a terminal state."""
    sched, radio = make_scheduler(max_in_flight=1)
    radio.effects = [radio.hold]

    blocker = sched.submit(make_packet(nwk=0x0001))
    await asyncio.sleep(0.01)

    h1 = sched.submit(make_packet(data=b"first", key=("k",)))
    h2 = sched.submit(make_packet(data=b"second", key=("k",)))

    assert h1.state is scheduler.SendState.DONE
    assert h1.park_reason is None
    assert h2.state is scheduler.SendState.QUEUED

    # A superseded handle can no longer cancel the entry
    assert not h1.cancel()

    radio.gate.set()
    await blocker
    await h2


async def test_scheduler_repr(make_scheduler):
    """Test the queue status representation counting live entries."""
    sched, radio = make_scheduler(max_in_flight=1)
    radio.effects = [TransactionExpiredError("no poll"), radio.hold]

    parked = sched.submit(make_packet(nwk=0x0001))
    await asyncio.sleep(0.01)
    assert parked.park_reason is scheduler.ParkReason.AWAITING_WAKE

    in_flight = sched.submit(make_packet(nwk=0x0002))
    await asyncio.sleep(0.01)
    queued = sched.submit(make_packet(nwk=0x0003))

    assert (
        "queued=1 in_flight=1 awaiting_reply=0 retry_backoff=0"
        " destination_blocked=0 awaiting_wake=1 window=1/1" in repr(sched)
    )

    radio.gate.set()
    await in_flight
    await queued


def test_packet_size_sleepy_weighting():
    """Test sleepy destinations weighing heavier against the byte budget."""
    packet = make_packet()
    sleepy = make_packet().replace(extended_timeout=True)

    assert scheduler.packet_size(sleepy) == (
        scheduler.SLEEPY_SIZE_WEIGHT * scheduler.packet_size(packet)
    )
