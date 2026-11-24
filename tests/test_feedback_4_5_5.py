"""Remarks of the MM3 author on 4.5.4 (24/11/2026)."""
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
