# The JV-1010 envelope graphs: the pure maths (it must invert the drawing) and dragging them through the patch editor.

import pytest
from PySide6.QtCore import QPointF, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from jv_studio.core import patch
from jv_studio.ui import envelope_graph as eg
from jv_studio.ui.patch_editor import PatchEditor


@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication([])


W, H = 284, 94


def test_a_handle_drag_inverts_the_drawing():
    times, levels = (30, 50, 70, 90), (100, 20, 60, 10)
    points = eg.jv_points(times, levels, 0, W, H)
    for index, point_index in enumerate((1, 2, 3, 5)):
        x, y = points[point_index]
        got_times, got_levels = eg.jv_values_for_handle(index, x, y, times, levels, W, H)
        assert all(abs(a - b) <= 1 for a, b in zip(got_times, times)) and all(abs(a - b) <= 1 for a, b in zip(got_levels, levels))


def test_a_stage_width_depends_only_on_its_own_time():
    a = eg.jv_points((10, 50, 50, 50), (0, 0, 0, 0), 0, W, H)
    b = eg.jv_points((10, 100, 50, 50), (0, 0, 0, 0), 0, W, H)
    assert a[1] == b[1] and (b[2][0] - b[1][0]) > (a[2][0] - a[1][0])  # moving time 2 left stage 1 alone and widened stage 2
    assert (b[3][0] - b[2][0]) == pytest.approx(a[3][0] - a[2][0])  # and did not resize stage 3


def test_the_level_envelope_never_changes_level_four():
    times, levels = (10, 10, 10, 10), (50, 50, 50, 0)
    _, got = eg.jv_values_for_handle(3, 250, 10, times, levels, W, H, free_last_level=False)
    assert got[3] == 0


def test_the_sustain_line_changes_only_level_three():
    times, levels = (10, 20, 30, 40), (50, 60, 70, 80)
    t, l = eg.jv_values_for_sustain(H / 2, times, levels, H)
    assert t == times and l[:2] == (50, 60) and l[3] == 80 and abs(l[2] - 64) <= 1


def test_the_graph_for_each_card_names_the_right_parameters(qapp):
    pitch, filt, level = eg.PitchEnvelopeGraph(), eg.FilterEnvelopeGraph(), eg.LevelEnvelopeGraph()
    assert pitch.NAMES[:2] == ("pitch_envelope_time_1", "pitch_envelope_time_2") and len(pitch.NAMES) == 8
    assert filt.NAMES[4] == "filter_envelope_level_1" and len(level.NAMES) == 7  # no level 4 on the level envelope


@pytest.fixture
def editor(qapp):
    e = PatchEditor()
    e.working = patch.Patch.minimum()
    for tone in range(4):
        for n in range(1, 5):
            e.working.set(patch.TONE, f"filter_envelope_time_{n}", 40, tone=tone)
            e.working.set(patch.TONE, f"filter_envelope_level_{n}", 60, tone=tone)
    e.set_patch(e.working)
    e.tabs.setCurrentIndex(1)
    e.resize(800, 700)
    e.show()
    qapp.processEvents()
    e.seen = []
    e.param_committed.connect(lambda *a: e.seen.append(a))
    yield e
    e.close()


def _filter_graph(editor, tone=0):
    return next(g for t, g in editor._graphs if t == tone and isinstance(g, eg.FilterEnvelopeGraph))


def test_the_graph_shows_the_patch_and_is_live_only_with_a_patch(editor, qapp):
    graph = _filter_graph(editor)
    assert graph.is_editable() and graph.values()["filter_envelope_time_2"] == 40
    editor.set_patch(None)
    assert not graph.is_editable()


def test_a_box_edit_moves_the_graph(editor):
    editor.widget_for(patch.TONE, "filter_envelope_level_2", 0).setValue(111)
    assert _filter_graph(editor).values()["filter_envelope_level_2"] == 111


def _drag(graph, handle, dx, dy, release=True):
    centre = graph.handle_positions()[handle]
    QTest.mousePress(graph, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, centre.toPoint())
    QTest.mouseMove(graph, (centre + QPointF(dx, dy)).toPoint())
    if release:
        QTest.mouseRelease(graph, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, (centre + QPointF(dx, dy)).toPoint())
    return centre


def test_a_drag_moves_the_boxes_live_and_changes_the_patch_only_on_release(editor):
    graph = _filter_graph(editor)
    box = editor.widget_for(patch.TONE, "filter_envelope_level_2", 0)
    before = editor.working.get(patch.TONE, "filter_envelope_level_2", tone=0)
    _drag(graph, 1, 0, -30, release=False)
    assert box.value() > before and editor.working.get(patch.TONE, "filter_envelope_level_2", tone=0) == before and editor.seen == []
    centre = graph.handle_positions()[1]
    QTest.mouseRelease(graph, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, centre.toPoint())
    assert editor.working.get(patch.TONE, "filter_envelope_level_2", tone=0) == box.value() > before
    assert editor.seen and {s[1] for s in editor.seen} <= {"filter_envelope_time_2", "filter_envelope_level_2"} and all(s[2] == 0 for s in editor.seen)


def test_escape_cancels_a_drag_and_puts_everything_back(editor):
    graph = _filter_graph(editor)
    box = editor.widget_for(patch.TONE, "filter_envelope_level_2", 0)
    before = box.value()
    _drag(graph, 1, 20, -30, release=False)
    assert box.value() != before
    QTest.keyClick(graph, Qt.Key.Key_Escape)
    assert box.value() == before and editor.working.get(patch.TONE, "filter_envelope_level_2", tone=0) == before and editor.seen == []


def test_double_click_resets_what_a_handle_controls(editor):
    graph = _filter_graph(editor)
    centre = graph.handle_positions()[0]
    QTest.mouseDClick(graph, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, centre.toPoint())
    assert editor.working.get(patch.TONE, "filter_envelope_time_1", tone=0) == 0 and editor.working.get(patch.TONE, "filter_envelope_level_1", tone=0) == 0
    assert editor.seen
