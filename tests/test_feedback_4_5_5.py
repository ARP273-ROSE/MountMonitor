"""Remarks of the MM3 author on 4.5.4 (24/11/2026)."""
from pathlib import Path
import pytest

from tests.test_feedback_4_x import window  # noqa: F401  (fixture)


def test_axial_off_in_pure_ascom(window):
    w = window
    s = w._settings
    s.set("axial_mode", "velocity")
    s.set("mount_protocol", "lx200")
    assert w._axial_mode() == "velocity"
    s.set("mount_protocol", "ascom")
    s.set("ascom_10micron_commands", False)
    assert w._axial_mode() == "off"            # chosen before switching: ignored
    s.set("ascom_10micron_commands", True)
    assert w._axial_mode() == "velocity"


def test_preferences_grey_axial_and_reopen_last_tab(window):
    from src.gui.preferences_dialog import PreferencesDialog
    s = window._settings
    s.set("mount_protocol", "lx200")
    s.set("preferences_tab", 2)
    d = PreferencesDialog(s)
    assert d._tabs.currentIndex() == 2
    assert d._axial_mode.isEnabled()
    d._protocol.setCurrentIndex(2)               # ASCOM
    d._ascom_10micron.setChecked(False)
    assert not d._axial_mode.isEnabled()
    d._ascom_10micron.setChecked(True)
    assert d._axial_mode.isEnabled()
    d._tabs.setCurrentIndex(1)
    assert s.get("preferences_tab") == 1
    d.close()


def test_graphs_ignore_wheel_and_dumps_keep_colours(window, tmp_path):
    w = window
    vb = w._ra_graph._plot.getViewBox()
    assert vb.state["mouseEnabled"] == [False, False]
    g = w._ra_graph
    g.set_tracking(False)
    seen = []
    import pyqtgraph.exporters as ex
    orig = ex.ImageExporter.export
    try:
        ex.ImageExporter.export = lambda self, f=None: seen.append(g._tracking)
        g.export_to_image(str(tmp_path))
    finally:
        ex.ImageExporter.export = orig
    assert seen == [True] and g._tracking is False


def test_update_offer_is_modeless_and_ownerless():
    """24/11/2026: a modal update dialog owned by the window, hidden at an
    unattended start, left the window unusable."""
    src = (Path(__file__).resolve().parent.parent / 'src' / 'gui' / 'main_window.py').read_text(encoding='utf-8')
    body = src.split('def _show_update_dialog', 1)[1].split('\n    def ', 1)[0]
    assert 'QDialog(None)' in body and 'dlg.exec()' not in body and 'dlg.show()' in body
    close = src.split('def closeEvent', 1)[1].split('\n    def ', 1)[0]
    assert '_update_offer' in close


def test_unattended_second_instance_shows_no_box():
    src = (Path(__file__).resolve().parent.parent / 'main.py').read_text(encoding='utf-8')
    block = src.split('if not _lock_file.tryLock(_wait_ms):', 1)[1].split('app._instance_lock', 1)[0]
    assert block.index('args.connect') < block.index('QMessageBox')


def test_update_offer_returns_at_once(window):
    window._show_update_dialog({"version": "9.9.9", "notes": "x", "size": 0})
    dlg = window._update_offer
    assert dlg is not None and dlg.isVisible() and not dlg.isModal()
    assert dlg.parent() is None and window.isEnabled()
    dlg.reject()
    assert window._update_offer is None
