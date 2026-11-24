"""The Assistant panel: proposals with a Run button, and model reads on the GUI thread.
Copilot itself is not started here (that needs a GitHub sign-in)."""

import os
import sys
import threading

import pytest

if os.environ.get("MODELER_GUI_TESTS") == "0":
    pytest.skip("GUI tests disabled", allow_module_level=True)
if sys.platform.startswith("linux") and not os.environ.get("DISPLAY"):
    pytest.skip("no X display (run under xvfb-run)", allow_module_level=True)

from PySide6.QtCore import QSettings  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from modeler.ai import copilot as cp  # noqa: E402
from modeler.gui.main_window import MainWindow  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def pump(app, n=10):
    for _ in range(n):
        app.processEvents()


@pytest.fixture
def win(app, tmp_path):
    w = MainWindow(autosave="off", settings=QSettings(str(tmp_path / "s.ini"), QSettings.IniFormat))
    w.resize(1000, 700)
    w.show()
    pump(app, 20)
    yield w
    w.shell.ask_unsaved = lambda *_: "discard"
    w.close()


def test_panel_is_there_and_starts_nothing(win, app):
    panel = win.assistant_panel
    win.shell.show_assistant()
    pump(app)
    assert win.assistant_dock.isVisible()
    assert panel.thread is None  # Copilot starts only when the user signs in or asks
    labels = [a.text().replace("&", "") for a in win.shell.help_menu.actions()]
    assert "Ask the assistant" in labels
    if not cp.sdk_available():
        assert not panel.send_button.isEnabled()


def test_run_a_proposal(win, app):
    panel = win.assistant_panel
    panel.show_proposal(cp.Proposal("BLOCK, 0,0,0, 10,10,10\nCYL, 5,5,0, 2, 15", "a block and a pin"))
    pump(app)
    assert panel.proposal_box.isVisibleTo(panel)
    assert "2 commands" in panel.proposal_label.text()
    n = len(win.processor.history)
    panel.run_proposal()
    pump(app)
    assert len(win.processor.history) == n + 2
    assert len(win.processor.model.bodies) == 2
    assert not panel.proposal_box.isVisibleTo(panel)
    win.execute("UNDO")  # one Undo takes the whole proposal back
    assert len(win.processor.model.bodies) == 0 and win.processor.cursor == n
    win.execute("REDO")
    assert len(win.processor.model.bodies) == 2 and win.processor.cursor == n + 2


def test_a_proposal_shows_its_effect_and_a_broad_one_needs_a_tick(win, app):
    from modeler.ai import safeguards as sg

    p = win.processor
    for line in ("BLOCK, 0,0,0, 10,10,10", "BLOCK, 20,0,0, 30,10,10", "BLOCK, 40,0,0, 50,10,10"):
        win.execute(line)
    script = "SPHERE, 5,5,5, 2"
    panel = win.assistant_panel
    panel.show_proposal(cp.Proposal(script, "a ball", plan="one sphere in the first block",
                                    effect=sg.plan_script(p, script)))
    pump(app)
    assert "Adds 1 body" in panel.effect_label.toPlainText() and "Plan:" in panel.proposal_label.text()
    assert panel.run_button.isEnabled() and not panel.confirm_box.isVisibleTo(panel)
    panel.clear_proposal()

    script = "DELETE, 1\nDELETE, 2"
    eff = sg.plan_script(p, script)
    assert eff["broad"] and "removes 2 bodies" in eff["broad"][0]
    panel.show_proposal(cp.Proposal(script, "remove two blocks", effect=eff))
    pump(app)
    assert panel.confirm_box.isVisibleTo(panel) and not panel.run_button.isEnabled()
    panel.run_proposal()  # without the tick nothing runs
    assert len(p.model.bodies) == 3
    panel.confirm_box.setChecked(True)
    assert panel.run_button.isEnabled()
    panel.run_proposal()
    pump(app)
    assert len(p.model.bodies) == 1
    win.execute("UNDO")
    assert len(p.model.bodies) == 3


def test_dismiss_a_proposal(win, app):
    panel = win.assistant_panel
    panel.show_proposal(cp.Proposal("SPHERE, 0,0,0, 3", ""))
    panel.clear_proposal()
    assert panel.proposal is None and not win.processor.model.bodies


def test_model_reads_run_on_the_gui_thread(win, app):
    win.execute("BLOCK, 0,0,0, 2,3,4")
    where, answer = [], []

    def read():
        where.append(threading.current_thread() is threading.main_thread())
        return win.processor.evaluate("VOL(1)")

    t = threading.Thread(target=lambda: answer.append(win.assistant_panel.calls.run(read)))
    t.start()
    for _ in range(200):
        pump(app, 1)
        if answer:
            break
        t.join(0.01)
    t.join(5)
    assert answer == [pytest.approx(24.0)] and where == [True]


def test_answers_show_code(win):
    panel = win.assistant_panel
    panel._on_event("message", "Try `BLOCK, 0,0,0, 1,1,1`:\n```\nCYL, 0,0,0, 1, 2\n```")
    html = panel.transcript.toHtml()
    assert "BLOCK, 0,0,0, 1,1,1" in html and "CYL, 0,0,0, 1, 2" in html
    panel._on_event("tool", "describe_body")
    assert "describe_body" in panel.transcript.toPlainText()


def test_run_a_history_edit_proposal(win, app):
    for line in ("W = 10", "BLOCK, 0,0,0, W, 5, 5"):
        win.execute(line)
    panel = win.assistant_panel
    panel.show_proposal(cp.Proposal("", "wider", [{"action": "edit", "entry": 1, "text": "W = 20", "old": "W = 10"}]))
    assert "was:  W = 10" in panel.proposal_text.toPlainText()
    assert "1 change to the history" in panel.proposal_label.text()
    panel.run_proposal()
    pump(app)
    assert win.processor.evaluate("BBOX(1).dx") == pytest.approx(20)
    assert "W = 10" in panel.transcript.toPlainText()


def test_working_folder_choices(win, tmp_path, monkeypatch):
    monkeypatch.setenv("MODELER_COPILOT_HOME", str(tmp_path / "temp"))
    panel = win.assistant_panel
    assert panel.folder_mode()[0] == "temp"
    assert panel.working_folder() == (str(tmp_path / "temp"), "")
    panel.choose_folder("custom", str(tmp_path))
    assert panel.working_folder()[0] == str(tmp_path) and str(tmp_path) in panel.folder_label.text()
    panel.choose_folder("project")
    path, note = panel.working_folder()
    assert path == str(tmp_path / "temp") and "not saved" in note  # unsaved: temporary for now
    (tmp_path / "proj").mkdir()
    win.processor.project_path = str(tmp_path / "proj" / "m.m3d")
    assert panel.working_folder() == (str(tmp_path / "proj"), "")
    assert panel._assistant().assistant.home == str(tmp_path / "proj")  # nothing starts until it is used
    panel.shutdown()


def test_debug_tab_shows_everything(win, app, tmp_path):
    panel = win.assistant_panel
    assert [panel.tabs.tabText(i) for i in range(panel.tabs.count())] == ["Chat", "Debug"]
    panel.clear_debug()
    for e in ({"kind": "system", "time": 0, "text": "You are the assistant", "tools": ["model_summary"],
               "model": "auto"},
              {"kind": "prompt", "time": 0, "text": "holes?"},
              {"kind": "tool_call", "time": 0, "name": "model_summary", "args": {}},
              {"kind": "tool_result", "time": 0, "name": "model_summary", "ok": True, "ms": 12.0,
               "result": '{"bodies":1}'},
              {"kind": "reply", "time": 0, "text": "One body."}):
        panel.event.emit("debug", e)
    pump(app)
    text = panel.debug_text.toPlainText()
    assert "SYSTEM MESSAGE" in text and "TOOL CALL model_summary {}" in text and "12 ms" in text
    assert '"bodies": 1' in text and "One body." in text
    assert panel.debug_count.text() == "1 prompt(s), 1 tool call(s)"
    panel.save_debug(str(tmp_path / "log.txt"))
    assert "TOOL RESULT model_summary" in (tmp_path / "log.txt").read_text()
    panel.copy_debug()
    assert "One body." in QApplication.clipboard().text()
    panel.clear_debug()
    assert panel.debug_text.toPlainText() == ""


def test_new_chat_clears_the_chat(win, app):
    panel = win.assistant_panel
    panel._say("you", "hello")
    panel.show_proposal(cp.Proposal("CYL, 0,0,0, 1, 2", "a pin"))
    panel.new_chat()
    pump(app)
    assert "hello" not in panel.transcript.toPlainText() and "New chat" in panel.transcript.toPlainText()
    assert not panel.proposal_box.isVisibleTo(panel)


@pytest.mark.parametrize("button,answer", [("Allow once", "once"), ("Allow for this chat", "chat"), ("Deny", "deny")])
def test_read_permission_dialog(win, app, button, answer):
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QMessageBox

    panel = win.assistant_panel

    def press():
        box = next(w for w in QApplication.topLevelWidgets() if isinstance(w, QMessageBox) and w.isVisible())
        next(b for b in box.buttons() if b.text() == button).click()

    QTimer.singleShot(100, press)
    assert panel.ask_read("read", "/work/notes.txt") == answer
    assert "notes.txt" in panel.transcript.toPlainText()


def test_own_key_settings(win, app, tmp_path, monkeypatch):
    from modeler.ai import providers as pv
    from modeler.gui.assistant_settings import AssistantSettingsDialog

    monkeypatch.setenv("MODELER_COPILOT_DATA", str(tmp_path / "data"))
    monkeypatch.delenv("MODELER_AI_KEY", raising=False)
    panel = win.assistant_panel
    assert panel.provider_setting().is_copilot and panel.sign_in_button.isVisibleTo(panel)

    dlg = AssistantSettingsDialog(panel, panel.provider_setting(), copilot_models=["gpt-a", "gpt-b"])
    assert dlg.model.count() == 3 and not dlg.key.isEnabled() and dlg.ok_button.isEnabled()
    dlg.kind.setCurrentIndex(dlg.kind.findData("anthropic"))
    assert dlg.key.isEnabled() and not dlg.url.isEnabled() and not dlg.ok_button.isEnabled()
    dlg.model.setEditText("claude-sonnet-5-5")
    assert "API key" in dlg.problem.text()
    dlg.key.setText("sk-ant")
    assert dlg.ok_button.isEnabled()
    s = dlg.setting()
    assert (s.kind, s.model, s.base_url, s.api_key) == ("anthropic", "claude-sonnet-5-5", "", "sk-ant")
    dlg.kind.setCurrentIndex(dlg.kind.findData("ollama"))  # switching back and forth keeps what was typed
    assert dlg.url.text() == "http://localhost:11434/v1" and dlg.url.isEnabled()
    dlg.kind.setCurrentIndex(dlg.kind.findData("anthropic"))
    assert dlg.model.currentText() == "claude-sonnet-5-5" and dlg.key.text() == "sk-ant"

    panel.set_provider(s, keep_key=False)  # not kept: this session only
    pump(app)
    assert pv.load_key("anthropic") == ""
    got = panel.provider_setting()
    assert got.kind == "anthropic" and got.api_key == "sk-ant"
    assert not panel.sign_in_button.isVisibleTo(panel)
    assert "Anthropic Claude: claude-sonnet-5-5" in panel.status_label.text()
    assert panel._assistant().assistant.provider.api_key == "sk-ant"
    panel.set_provider(s, keep_key=True)
    assert pv.load_key("anthropic") == "sk-ant"
    panel.set_provider(pv.ProviderSetting(), keep_key=False)
    assert panel.provider_setting().is_copilot and panel.sign_in_button.isVisibleTo(panel)
    assert panel._assistant().assistant.provider is None
    panel.shutdown()


def test_ask_pick_in_the_view(win, app):
    panel = win.assistant_panel
    win.execute("BLOCK, 0,0,0, 40,30,10")
    win.execute("PICKMODE, BODY")
    pump(app)
    got = []
    panel.pick_request("FACE", "Click the top face", got.append)
    pump(app)
    assert panel.pick_box.isVisibleTo(panel) and "Click the top face" in panel.pick_label.text()
    assert win.viewport.pick_mode == "FACE"
    win.viewport.command.emit("PICK, FACE, 6")  # what a click in the view sends
    pump(app)
    assert got == [("FACE", 6)] and win.processor.model.selection == [6]
    assert not panel.pick_box.isVisibleTo(panel) and win.viewport.pick_mode == "BODY"  # put back
    assert "You picked face 6" in panel.transcript.toPlainText()

    panel.pick_request("EDGE", "Click an edge", got.append)
    panel.finish_pick(None)  # Cancel
    assert got[-1] is None and win.viewport.pick_mode == "BODY"


def test_highlight_marks_in_the_view(win, app):
    panel = win.assistant_panel
    win.execute("BLOCK, 0,0,0, 40,30,10")
    pump(app)
    assert panel.show_marks("FACE", [6], "the top")
    assert len(win.viewport._mark_ais) == 1 and "Marked in orange: face 6" in panel.transcript.toPlainText()
    panel.input.setText("thanks")
    panel._busy = True  # nothing is sent; clearing the marks happens first
    panel.clear_marks()
    assert win.viewport._mark_ais == []
    panel._busy = False


def test_render_takes_a_picture_and_keeps_the_camera(win, app):
    from PySide6.QtGui import QImage

    panel = win.assistant_panel
    win.execute("BLOCK, 0,0,0, 40,30,10")
    win.execute("VIEW, FRONT")
    pump(app)
    vp = win.viewport
    before = vp.view.Camera().Direction()
    before = (before.X(), before.Y(), before.Z())
    png = panel.render_view("TOP", 320, 240, "FACE", [6])
    assert png and png[:8] == b"\x89PNG\r\n\x1a\n"
    img = QImage.fromData(png, "PNG")
    assert (img.width(), img.height()) == (320, 240)
    after = vp.view.Camera().Direction()
    assert (after.X(), after.Y(), after.Z()) == pytest.approx(before)  # the user's view is put back
    assert vp._mark_ais == []  # the marks were for the picture only
    panel.show_picture(png)
    assert "looked at a picture" in panel.transcript.toPlainText()


def test_answer_streams_in_then_is_formatted(win, app):
    panel = win.assistant_panel
    win.processor.chat.clear()
    for piece in ("Use `FIL", "LET`", " with r = 2."):
        panel._on_event("delta", piece)
    assert "Use `FILLET` with r = 2." in panel.transcript.toPlainText()  # as written, unformatted
    panel._on_event("message", "Use `FILLET` with r = 2.")
    text = panel.transcript.toPlainText()
    assert text.count("FILLET") == 1 and "`" not in text  # replaced by the formatted answer
    assert "<code>" in panel.transcript.toHtml() or "FILLET" in text
    assert win.processor.chat[-1] == {"who": "assistant", "text": "Use `FILLET` with r = 2."}
    # a tool starting mid-answer keeps what was written; the same complete answer is not shown twice
    panel._on_event("delta", "Let me look")
    panel._on_event("tool", "describe_body")
    panel._on_event("message", "Let me look")
    assert panel.transcript.toPlainText().count("Let me look") == 1
    assert [e["text"] for e in win.processor.chat].count("Let me look") == 1


def test_stop_button_while_busy(win, app):
    panel = win.assistant_panel
    asked = []

    class FakeThread:
        assistant = type("A", (), {"earlier": "", "home": panel.working_folder()[0]})()

        def stop_answer(self):
            asked.append("stop")

        def close(self):
            pass

        def new_chat(self):
            pass

    panel.thread = FakeThread()
    panel._checked = True  # no status call after the answer
    panel._set_busy(True)
    assert panel.stop_button.isVisibleTo(panel) and not panel.send_button.isVisibleTo(panel)
    panel.stop()
    assert asked == ["stop"] and not panel.stop_button.isEnabled()
    from concurrent.futures import Future

    fut = Future()
    fut.set_result(cp.Reply(text="part", stopped=True))
    panel._on_event("delta", "part")
    panel._answered(fut)
    assert panel.send_button.isVisibleTo(panel) and not panel.stop_button.isVisibleTo(panel)
    assert "part" in panel.transcript.toPlainText() and "Stopped." in panel.transcript.toPlainText()
    panel.thread = None


def test_conversation_is_saved_with_the_project(win, app, tmp_path):
    panel = win.assistant_panel
    win.processor.chat[:] = [{"who": "you", "text": "make a plate"},
                             {"who": "assistant", "text": "Run `BLOCK, 0,0,0, 40,30,5`."}]
    assert win.execute("BLOCK, 0,0,0, 40,30,5").ok
    path = tmp_path / "plate.m3d"
    assert win.execute(f'SAVE, "{path}"').ok
    assert win.execute("NEW").ok
    assert win.processor.chat == [] and "make a plate" not in panel.transcript.toPlainText()
    assert win.execute(f'OPEN, "{path}"').ok
    pump(app)
    assert win.processor.chat[0] == {"who": "you", "text": "make a plate"}
    text = panel.transcript.toPlainText()
    assert "saved with this project (2 messages)" in text and "make a plate" in text
    # the next question gives it to the fresh chat
    assert "make a plate" in cp.earlier_text(win.processor.chat)
    panel.new_chat()
    assert win.processor.chat == []
