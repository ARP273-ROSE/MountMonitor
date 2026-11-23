"""Reference "Mount target coordinates": the target is read while tracking,
not only when a slew ends (connecting to a mount already tracking used to
leave the median in place, so both references drew the same graph)."""
from types import SimpleNamespace

from src.core.data_processor import DataProcessor
from src.gui.main_window import MainWindow
from src.models.mount_data import MountStatus


class _Panel:
    def __init__(self):
        self.messages = []

    def add_message(self, text, *a):
        self.messages.append(text)


def _window(mode="target"):
    w = SimpleNamespace(_settings={"reference_mode": mode}, requests=[],
                        _processor=DataProcessor(), _status_panel=_Panel())
    w._processor.set_reference_mode(mode)
    w._mount_request = lambda fn, cb: w.requests.append((fn, cb))
    w.TARGET_REFRESH_S = MainWindow.TARGET_REFRESH_S
    w._receive_target = lambda t: MainWindow._receive_target(w, t)
    return w


def test_read_while_tracking_then_every_30_s(monkeypatch):
    import src.gui.main_window as mw
    clock = [1000.0]
    monkeypatch.setattr(mw.time, "monotonic", lambda: clock[0])
    w = _window()
    MainWindow._refresh_target(w, MountStatus.TRACKING)
    MainWindow._refresh_target(w, MountStatus.TRACKING)
    assert len(w.requests) == 1                      # no flood at every sample
    clock[0] += 31
    MainWindow._refresh_target(w, MountStatus.TRACKING)
    assert len(w.requests) == 2
    MainWindow._refresh_target(w, MountStatus.SLEWING)
    MainWindow._refresh_target(_window("median"), MountStatus.TRACKING)
    assert len(w.requests) == 2


def test_target_used_and_missing_target_said_once():
    w = _window()
    w._receive_target(("22:48:50.17#", "+44*20:56.1#"))
    assert w._processor.target == (22.81393611111111, 44.34891666666667)
    assert any("22:48:50.17" in m for m in w._status_panel.messages)
    w2 = _window()
    w2._receive_target((None, None))
    w2._receive_target((None, None))
    assert len(w2._status_panel.messages) == 1 and w2._processor.target is None
