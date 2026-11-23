"""No sample while the mount slews, nor during delay_after_slew counted
from the END of the slew (MountMonitor 3 behaviour)."""
from src.core.mount_connection import MountStatus
from src.core.poller import MountPoller


def _poller(delay):
    p = MountPoller(connection=None, processor=None)
    p.set_delay_after_slew(delay)
    settled = []
    p.slew_settled.connect(lambda: settled.append(True))
    return p, settled


def test_dropped_during_slew_and_delay_after_its_end():
    p, settled = _poller(10)
    T, S = MountStatus.TRACKING, MountStatus.SLEWING
    assert p._skip_for_slew(T, now=0) is False
    # A 10 s slew: the old code counted the delay from its start, so
    # recording resumed the moment the slew ended.
    for t in range(1, 11):
        assert p._skip_for_slew(S, now=t) is True
    assert p._skip_for_slew(T, now=11) is True      # slew ended at 11
    assert p._skip_for_slew(T, now=20.9) is True
    assert settled == []
    assert p._skip_for_slew(T, now=21) is False
    assert settled == [True]
    assert p._skip_for_slew(T, now=22) is False
    assert settled == [True]                        # once


def test_no_delay_still_drops_the_slew():
    p, settled = _poller(0)
    assert p._skip_for_slew(MountStatus.SLEWING, now=0) is True
    assert p._skip_for_slew(MountStatus.TRACKING, now=1) is False
    assert settled == [True]


def test_new_slew_during_delay_restarts_it():
    p, settled = _poller(10)
    p._skip_for_slew(MountStatus.SLEWING, now=0)
    assert p._skip_for_slew(MountStatus.TRACKING, now=1) is True
    assert p._skip_for_slew(MountStatus.SLEWING, now=5) is True
    assert p._skip_for_slew(MountStatus.TRACKING, now=6) is True
    assert p._skip_for_slew(MountStatus.TRACKING, now=15) is True
    assert p._skip_for_slew(MountStatus.TRACKING, now=16) is False
    assert settled == [True]
