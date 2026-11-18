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
    win.execute("UNDO")
    assert len(win.processor.model.bodies) == 1


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
