# -*- coding: utf-8 -*-
"""Connection at launch (--connect / connect_on_launch): first attempt, retries
while the mount does not answer, stop at the first success or when the user
takes over, never a dialog.

    xvfb-run -a python -m pytest -q tests/test_auto_connect.py
"""
import os
import socket
import sys
import tempfile
from pathlib import Path

_TMP = tempfile.mkdtemp(prefix='mm-test-auto-')
os.environ.setdefault('QT_QPA_PLATFORM', 'xcb' if os.environ.get('DISPLAY') else 'offscreen')

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pytest  # noqa: E402

pytest.importorskip('PyQt6')
from PyQt6.QtCore import QTimer  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

APP = QApplication.instance() or QApplication([])

import reporting  # noqa: E402

Path(_TMP, 'reglages_rapports.json').write_text('{"envoi_autorise": false}', encoding='utf-8')
reporting.init(_TMP, application='mountmonitor-essais', version='0')


def _closed_port():
    s = socket.socket()
    s.bind(('127.0.0.1', 0))
    port = s.getsockname()[1]
    s.close()                       # nobody listens any more: connection refused
    return port


@pytest.fixture
def settings(monkeypatch):
    from src.config.settings import Settings
    s = Settings()
    before = {k: s.get(k) for k in ('mount_protocol', 'mount_ip', 'mount_port', 'ascom_driver',
                                    'connect_on_launch', 'connect_retry_s', 'serial_port')}
    # Retries go through QTimer.singleShot: record them instead of waiting.
    scheduled = []
    monkeypatch.setattr(QTimer, 'singleShot', staticmethod(lambda ms, f: scheduled.append((ms, f))))
    yield s, scheduled
    for k, v in before.items():
        s.set(k, v)


def _wait_for(win, delay=10.0):
    """The connection is opened in the poller thread: wait for its answer."""
    import time
    end = time.monotonic() + delay
    while win._connecting and time.monotonic() < end:
        APP.processEvents()
        time.sleep(0.01)
    APP.processEvents()
    assert not win._connecting, "no answer from the connection"


def _make_window(**kw):
    from src.gui.main_window import MainWindow
    return MainWindow(**kw)


def test_no_connection_at_launch_by_default(settings):
    s, scheduled = settings
    s.set('connect_on_launch', False)
    win = _make_window()
    assert not win._auto_connect_active
    assert not any(f == win._auto_connect for _, f in scheduled)
    win.hide()


def test_silent_mount_then_retry(settings):
    s, scheduled = settings
    s.set('mount_protocol', 'lx200'); s.set('mount_ip', '127.0.0.1'); s.set('mount_port', _closed_port())
    s.set('connect_retry_s', 30)
    win = _make_window(auto_connect=True)
    assert win._auto_connect_active
    assert (1500, win._auto_connect) in scheduled
    scheduled.clear()
    win._auto_connect()                       # 1st attempt: refused
    _wait_for(win)
    assert not win._connected
    assert win._connect_attempts == 1
    assert (30000, win._auto_connect) in scheduled   # retry in 30 s
    win._auto_connect()                       # 2nd attempt
    _wait_for(win)
    assert win._connect_attempts == 2
    win.hide()


def test_mount_answers_and_retries_stop(settings):
    s, scheduled = settings
    s.set('mount_protocol', 'simulation')
    win = _make_window(auto_connect=True)
    win._auto_connect()
    _wait_for(win)
    assert win._connected
    assert not win._auto_connect_active
    scheduled.clear()
    win._auto_connect()                       # a late retry does nothing
    assert win._connect_attempts == 1 and not scheduled
    win._disconnect()
    win.hide()


def test_connect_on_launch_setting_equals_option(settings):
    s, scheduled = settings
    s.set('connect_on_launch', True)
    win = _make_window()
    assert win._auto_connect_active
    assert (1500, win._auto_connect) in scheduled
    win.hide()


def test_user_click_stops_retries(settings):
    s, scheduled = settings
    s.set('mount_protocol', 'lx200'); s.set('mount_ip', '127.0.0.1'); s.set('mount_port', _closed_port())
    win = _make_window(auto_connect=True)
    win._auto_connect()
    _wait_for(win)
    assert win._auto_connect_active
    win._toggle_connection()                           # he clicks Connect (refused too)
    _wait_for(win)
    assert not win._auto_connect_active
    scheduled.clear()
    win._auto_connect()                       # the already scheduled retry does nothing
    assert win._connect_attempts == 1 and not scheduled
    win.hide()


def test_ascom_without_driver_does_not_open_chooser(settings, monkeypatch):
    s, scheduled = settings
    s.set('mount_protocol', 'ascom'); s.set('ascom_driver', '')
    import src.gui.preferences_dialog as pd
    monkeypatch.setattr(pd, '_ascom_choose', lambda *a: pytest.fail('selecteur ASCOM ouvert'))
    win = _make_window(auto_connect=True)
    win._auto_connect()
    _wait_for(win)
    assert not win._auto_connect_active and not win._connected
    win.hide()


def test_minimum_delay_of_5_s(settings):
    s, scheduled = settings
    s.set('mount_protocol', 'lx200'); s.set('mount_ip', '127.0.0.1'); s.set('mount_port', _closed_port())
    s.set('connect_retry_s', 0)
    win = _make_window(auto_connect=True)
    scheduled.clear()
    win._auto_connect()
    _wait_for(win)
    assert (5000, win._auto_connect) in scheduled
    win.hide()


def test_connect_option_recognised():
    import main
    sys_argv = sys.argv
    try:
        sys.argv = ['main.py', '--connect']
        assert main.parse_args().connect is True
        sys.argv = ['main.py']
        assert main.parse_args().connect is False
    finally:
        sys.argv = sys_argv
