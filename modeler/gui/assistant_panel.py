"""The Assistant panel: chat with GitHub Copilot, signed in with the user's own GitHub account.

The panel is a dock beside the history. It shows who is signed in and how
much of their Copilot allowance is left, the conversation, and the latest
proposal: a script Copilot tried in the sandbox, with a Run button. Running a
proposal goes through the normal command line, so it lands in the history
like anything the user types, and Undo takes it back.

Copilot runs on a background thread (:class:`modeler.ai.copilot.AssistantThread`);
its tools read the model on the GUI thread, through :class:`_ModelCalls`.
"""

from __future__ import annotations

import html
import os
import threading
from concurrent.futures import Future
from typing import TYPE_CHECKING, Any, Callable

from PySide6.QtCore import QObject, Qt, QUrl, Signal, Slot
from PySide6.QtGui import QActionGroup, QDesktopServices, QFontDatabase, QGuiApplication, QTextCursor
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QTabWidget,
    QTextBrowser,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ..ai import copilot as cp
from ..ai import providers as pv

if TYPE_CHECKING:
    from .main_window import MainWindow


SMALL_PROMPT = "assistant/small_prompt"  # Help > Assistant skills…: names only in the first message


class _ModelCalls(QObject):
    """Runs a function on the GUI thread for the assistant's thread, and waits for it."""

    call = Signal(object, object)

    def __init__(self) -> None:
        super().__init__()
        self.call.connect(self._run, Qt.QueuedConnection)

    @Slot(object, object)
    def _run(self, fn, fut: Future) -> None:
        try:
            fut.set_result(fn())
        except BaseException as exc:  # noqa: BLE001 - handed back to the caller
            fut.set_exception(exc)

    def run(self, fn: Callable[[], Any]) -> Any:
        if threading.current_thread() is threading.main_thread():
            return fn()
        fut: Future = Future()
        self.call.emit(fn, fut)
        return fut.result(120)


class AssistantPanel(QWidget):
    event = Signal(str, object)  # from the assistant's thread
    done = Signal(object, object)  # (callback, future) back on the GUI thread

    def __init__(self, win: "MainWindow") -> None:
        super().__init__(win)
        self.win = win
        self.thread: cp.AssistantThread | None = None
        self.calls = _ModelCalls()
        self.proposal: cp.Proposal | None = None
        self._busy = False
        self._streaming = False
        self._checked = False  # asked Copilot whether someone is signed in
        self._unsaved_keys: dict[str, str] = {}  # keys the user did not want kept: this session only
        self._copilot_models: list[str] = []
        self._pick: tuple[str, Callable, str] | None = None  # (kind, done, pick mode before) while asking

        lay = QVBoxLayout(self)
        lay.setContentsMargins(4, 4, 4, 4)
        top = QHBoxLayout()
        self.status_label = QLabel("Assistant: GitHub Copilot")
        self.status_label.setWordWrap(True)
        top.addWidget(self.status_label, 1)
        self.new_chat_button = QPushButton("New chat")
        self.new_chat_button.setToolTip("Start over: Copilot forgets this conversation (the sign-in stays)")
        self.new_chat_button.clicked.connect(self.new_chat)
        top.addWidget(self.new_chat_button)
        self.settings_button = QPushButton("Model…")
        self.settings_button.setToolTip("GitHub Copilot or your own key (OpenAI, Anthropic, Azure, Ollama...), "
                                        "and the model")
        self.settings_button.clicked.connect(self.open_settings)
        top.addWidget(self.settings_button)
        self.sign_in_button = QPushButton("Sign in with GitHub")
        self.sign_in_button.setToolTip("Sign in with your own GitHub account; Copilot Free works too")
        self.sign_in_button.clicked.connect(self.sign_in)
        top.addWidget(self.sign_in_button)
        lay.addLayout(top)

        # the working folder: a temporary one unless the user picks one, or the project's folder
        row = QHBoxLayout()
        self.folder_label = QLabel()
        self.folder_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        row.addWidget(self.folder_label, 1)
        self.folder_button = QToolButton()
        self.folder_button.setText("Folder")
        self.folder_button.setToolTip("The folder Copilot works in: where it saves and looks for files")
        self.folder_button.setPopupMode(QToolButton.InstantPopup)
        menu = QMenu(self.folder_button)
        group = QActionGroup(menu)
        self.folder_actions = {}
        for mode, text in (("temp", "A temporary folder"), ("project", "The project's folder"),
                           ("custom", "Choose a folder…")):
            act = menu.addAction(text)
            act.setCheckable(True)
            group.addAction(act)
            act.triggered.connect(lambda _=False, m=mode: self.choose_folder(m))
            self.folder_actions[mode] = act
        menu.addSeparator()
        menu.addAction("Open the folder", lambda: QDesktopServices.openUrl(
            QUrl.fromLocalFile(self.working_folder()[0])))
        self.folder_button.setMenu(menu)
        row.addWidget(self.folder_button)
        lay.addLayout(row)

        self.transcript = QTextBrowser()
        self.transcript.setOpenExternalLinks(True)
        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self.tabs.addTab(self.transcript, "Chat")
        self.tabs.addTab(self._debug_tab(), "Debug")
        lay.addWidget(self.tabs, 1)

        # Copilot asked the user to click something in the 3D view
        self.pick_box = QWidget()
        pk = QHBoxLayout(self.pick_box)
        pk.setContentsMargins(6, 4, 6, 4)
        self.pick_box.setStyleSheet("QWidget { background: #fff1e0; } QLabel { color: #5a3200; }")
        self.pick_label = QLabel()
        self.pick_label.setWordWrap(True)
        pk.addWidget(self.pick_label, 1)
        cancel = QPushButton("Cancel")
        cancel.setToolTip("Tell Copilot you do not want to pick anything")
        cancel.clicked.connect(lambda: self.finish_pick(None))
        pk.addWidget(cancel)
        self.pick_box.hide()
        lay.addWidget(self.pick_box)

        self.proposal_box = QWidget()
        pl = QVBoxLayout(self.proposal_box)
        pl.setContentsMargins(0, 0, 0, 0)
        self.proposal_label = QLabel()
        self.proposal_label.setWordWrap(True)
        pl.addWidget(self.proposal_label)
        self.proposal_text = QPlainTextEdit()
        self.proposal_text.setReadOnly(True)
        self.proposal_text.setMaximumHeight(120)
        pl.addWidget(self.proposal_text)
        row = QHBoxLayout()
        self.run_button = QPushButton("Run")
        self.run_button.setToolTip("Run these commands; they go into the history and Undo takes them back")
        self.run_button.clicked.connect(self.run_proposal)
        dismiss = QPushButton("Dismiss")
        dismiss.clicked.connect(self.clear_proposal)
        row.addStretch(1)
        row.addWidget(dismiss)
        row.addWidget(self.run_button)
        pl.addLayout(row)
        self.proposal_box.hide()
        lay.addWidget(self.proposal_box)

        row = QHBoxLayout()
        self.input = QLineEdit()
        self.input.setPlaceholderText("Ask Copilot: \"add a 6 mm hole through the middle of the plate\"")
        self.input.returnPressed.connect(self.send)
        row.addWidget(self.input, 1)
        self.send_button = QPushButton("Send")
        self.send_button.clicked.connect(self.send)
        row.addWidget(self.send_button)
        self.stop_button = QPushButton("Stop")
        self.stop_button.setToolTip("Stop this answer; what is written so far stays")
        self.stop_button.clicked.connect(self.stop)
        self.stop_button.hide()
        row.addWidget(self.stop_button)
        lay.addLayout(row)

        self.event.connect(self._on_event)
        self.done.connect(self._on_done)
        self._stream_start = -1  # where the answer being written starts in the transcript (-1: none)
        self._stream_text = ""
        self._kept = ""  # an answer kept as written (a tool started before it was complete)
        win.processor.listeners.append(self._on_result)
        view = getattr(win, "viewport", None)
        if view is not None and hasattr(view, "command"):
            view.command.connect(self._view_command)
        self.show_folder()
        self._show_provider()

        if not cp.sdk_available():
            self.status_label.setText("The assistant is not installed.")
            self._say("system", html.escape(cp.SDK_HINT))
            for w in (self.sign_in_button, self.send_button, self.input, self.new_chat_button,
                      self.settings_button):
                w.setEnabled(False)
        else:
            self._say("system", "Ask about commands, errors or your model. Copilot tries its scripts in a "
                                "sandbox first and shows them here with a <b>Run</b> button; it never changes "
                                "your model by itself. Requests count against your own Copilot plan.")

    # ---- the working folder --------------------------------------------------------------
    def _settings(self):
        shell = getattr(self.win, "shell", None)
        return shell.settings if shell is not None else None

    def folder_mode(self) -> tuple[str, str]:
        """(``temp`` | ``project`` | ``custom``, the chosen folder for ``custom``), from the settings."""
        st = self._settings()
        if st is None:
            return "temp", ""
        return str(st.value("assistant/folder_mode", "temp")), str(st.value("assistant/folder", "") or "")

    def working_folder(self) -> tuple[str, str]:
        """(the folder Copilot works in now, a note when it is not the one chosen)."""
        mode, chosen = self.folder_mode()
        if mode == "project":
            path = getattr(self.win.processor, "project_path", "")
            if path:
                return os.path.dirname(os.path.abspath(path)), ""
            return cp.default_home(), "the project is not saved yet, so a temporary folder for now"
        if mode == "custom":
            if chosen and os.path.isdir(chosen):
                return chosen, ""
            return cp.default_home(), "the chosen folder is gone, so a temporary folder for now"
        return cp.default_home(), ""

    def show_folder(self) -> None:
        mode, _ = self.folder_mode()
        path, note = self.working_folder()
        what = {"temp": "Temporary folder", "project": "Project folder", "custom": "Folder"}.get(mode, "Folder")
        self.folder_label.setText(f"{what}: {path}" + (f" ({note})" if note else ""))
        self.folder_label.setToolTip(path)
        act = self.folder_actions.get(mode)
        if act is not None:
            act.setChecked(True)

    def choose_folder(self, mode: str, path: str | None = None) -> None:
        """Set where Copilot works; ``custom`` asks for the folder unless ``path`` is given."""
        st = self._settings()
        if mode == "custom" and path is None:
            start = self.folder_mode()[1] or self.working_folder()[0]
            path = QFileDialog.getExistingDirectory(self, "The assistant's working folder", start)
            if not path:
                self.show_folder()  # cancelled: keep what was there
                return
        if st is not None:
            st.setValue("assistant/folder_mode", mode)
            if path:
                st.setValue("assistant/folder", path)
        self.show_folder()
        if self.thread is not None and self.thread.assistant.home != self.working_folder()[0]:
            self.shutdown()
            self._say("system", f"Working folder: {html.escape(self.working_folder()[0])}. "
                                "Copilot starts again in it with your next question.")

    def _debug_tab(self) -> QWidget:
        """Everything sent to Copilot and back: the system message, prompts, tool calls with
        their arguments, results and times, replies, permissions and errors."""
        box = QWidget()
        lay = QVBoxLayout(box)
        lay.setContentsMargins(0, 4, 0, 0)
        self.debug_text = QPlainTextEdit()
        self.debug_text.setReadOnly(True)
        self.debug_text.setFont(QFontDatabase.systemFont(QFontDatabase.FixedFont))
        self.debug_text.setPlaceholderText("Nothing sent yet. The first question shows the full system message here, "
                                           "then every prompt, tool call (with its arguments, result and time) and "
                                           "reply.")
        lay.addWidget(self.debug_text, 1)
        row = QHBoxLayout()
        self.debug_count = QLabel()
        row.addWidget(self.debug_count, 1)
        for text, tip, fn in (("Copy", "Copy the whole log", self.copy_debug),
                              ("Save…", "Save the log to a text file", self.save_debug),
                              ("Clear", "Clear the log (the conversation goes on)", self.clear_debug)):
            b = QPushButton(text)
            b.setToolTip(tip)
            b.clicked.connect(fn)
            row.addWidget(b)
        lay.addLayout(row)
        self._debug_entries: list[dict] = []
        self._show_debug_count()
        return box

    def _show_debug_count(self) -> None:
        calls = sum(1 for e in self._debug_entries if e.get("kind") == "tool_call")
        prompts = sum(1 for e in self._debug_entries if e.get("kind") == "prompt")
        self.debug_count.setText(f"{prompts} prompt(s), {calls} tool call(s)")

    def debug_log(self) -> str:
        return cp.format_log(self._debug_entries)

    def add_debug(self, entry: dict) -> None:
        self._debug_entries.append(entry)
        self.debug_text.appendPlainText(cp.format_log([entry]))
        self._show_debug_count()

    def copy_debug(self) -> None:
        QGuiApplication.clipboard().setText(self.debug_log())

    def save_debug(self, path: str | None = None) -> None:
        if not path:
            path, _ = QFileDialog.getSaveFileName(self, "Save the assistant log",
                                                  os.path.join(self.working_folder()[0], "assistant-log.txt"),
                                                  "Text (*.txt)")
        if path:
            with open(path, "w", encoding="utf-8") as f:
                f.write(self.debug_log())

    def clear_debug(self) -> None:
        self._debug_entries.clear()
        self.debug_text.clear()
        self._show_debug_count()

    def new_chat(self) -> None:
        """Forget the conversation; the next question sends the full first prompt again."""
        if self._busy:
            return
        self.clear_proposal()
        self.finish_pick(None, tell=False)
        self.clear_marks()
        self.transcript.clear()
        self.win.processor.chat.clear()
        self._say("system", "New chat. Copilot has forgotten the earlier conversation.")
        if self.thread is not None:
            self.thread.new_chat()

    def ask_read(self, what: str, path: str) -> str:
        """May Copilot read this? Asked on the GUI thread; "once", "chat" or "deny"."""
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Question)
        box.setWindowTitle("Copilot wants to read a file")
        box.setText(f"Copilot asks to {what}:\n\n{path}")
        box.setInformativeText("It can only read inside the working folder, and only text.")
        once = box.addButton("Allow once", QMessageBox.AcceptRole)
        chat = box.addButton("Allow for this chat", QMessageBox.AcceptRole)
        deny = box.addButton("Deny", QMessageBox.RejectRole)
        box.setDefaultButton(deny)
        box.exec()
        clicked = box.clickedButton()
        answer = "once" if clicked is once else "chat" if clicked is chat else "deny"
        self._say("system", f"{'Allowed' if answer != 'deny' else 'Declined'}: {html.escape(what)} "
                            f"<code>{html.escape(os.path.basename(path) or path)}</code>"
                            + (" (for this chat)" if answer == "chat" else ""))
        return answer

    # ---- pointing: the user clicks for Copilot, Copilot marks for the user ------------------
    def pick_request(self, kind: str | None, prompt: str, done: Callable | None) -> None:
        """Copilot's ask_pick, on the GUI thread: show the request and let the next click answer it."""
        if kind is None:
            self.finish_pick(None, tell=False)
            return
        if self._pick is not None:
            self.finish_pick(None)
        view = getattr(self.win, "viewport", None)
        if view is None or not getattr(view, "_initialized", False):
            done(None)
            return
        before = getattr(view, "pick_mode", "FACE")
        self._pick = (kind, done, before)
        if before != kind:
            self.win.execute(f"PICKMODE, {kind}")
        self.pick_label.setText(f"<b>Copilot asks:</b> {html.escape(prompt)}<br>Click a {kind.lower()} in the "
                                "3D view.")
        self.pick_box.show()
        self._say("system", f"Copilot asks you to click a {kind.lower()}: {html.escape(prompt)}")
        self.tabs.setCurrentIndex(0)

    def _view_command(self, text: str) -> None:
        if self._pick is None or not text.startswith("PICK, "):
            return
        parts = [x.strip() for x in text.split(",")]
        if len(parts) >= 3 and parts[1] == self._pick[0]:
            self.finish_pick((parts[1], int(parts[2])))

    def finish_pick(self, result: tuple[str, int] | None, tell: bool = True) -> None:
        if self._pick is None:
            return
        kind, done, before = self._pick
        self._pick = None
        self.pick_box.hide()
        if before != kind:
            self.win.execute(f"PICKMODE, {before}")
        if done is not None:
            done(result)
        if tell:
            self._say("system", f"You picked {result[0].lower()} {result[1]}." if result else "No pick.")

    def show_marks(self, kind: str, ids: list[int], note: str) -> bool:
        """Copilot's highlight, on the GUI thread."""
        view = getattr(self.win, "viewport", None)
        if view is None or not getattr(view, "_initialized", False):
            return False
        m = self.win.processor.model
        view.set_marks([m.entity_shape(kind, i) for i in ids] if kind else [])
        if kind:
            self._say("system", f"Marked in orange: {kind.lower()} {', '.join(map(str, ids))}"
                                + (f" ({html.escape(note)})" if note else ""))
        return True

    def render_view(self, view: str, width: int, height: int, kind: str, ids: list[int], focus: bool = False,
                    shapes=None) -> bytes | None:
        """Copilot's render tools, on the GUI thread: a PNG of the 3D view (the user's camera is kept);
        focus frames it on the marked entities, shapes are marked instead of entities."""
        vp = getattr(self.win, "viewport", None)
        if vp is None or not hasattr(vp, "snapshot"):
            return None
        m = self.win.processor.model
        marks = list(shapes) if shapes else ([m.entity_shape(kind, i) for i in ids] if kind and ids else None)
        target = None
        if focus and marks:
            from OCP.BRep import BRep_Builder
            from OCP.TopoDS import TopoDS_Compound

            target = TopoDS_Compound()
            bld = BRep_Builder()
            bld.MakeCompound(target)
            for sh in marks:
                bld.Add(target, sh)
        return vp.snapshot(width, height, view, marks, focus=target)

    def show_picture(self, png: bytes) -> None:
        """Show the picture Copilot looked at, small, in the chat."""
        from PySide6.QtGui import QImage, QTextDocument

        img = QImage.fromData(png, "PNG")
        if img.isNull():
            return
        self._pictures = getattr(self, "_pictures", 0) + 1
        url = QUrl(f"picture://{self._pictures}.png")
        self.transcript.document().addResource(QTextDocument.ImageResource, url, img)
        w = min(img.width(), 320)
        self.transcript.append(f"<p style='color:gray'>&nbsp;&nbsp;looked at a picture of the view:<br>"
                               f"<img src='{url.toString()}' width='{w}'></p>")

    def clear_marks(self) -> None:
        view = getattr(self.win, "viewport", None)
        if view is not None and getattr(view, "_mark_ais", None):
            view.set_marks([])

    # ---- where the answers come from ----------------------------------------------------
    def provider_setting(self) -> pv.ProviderSetting:
        st = self._settings()
        values = {} if st is None else {k: st.value(f"assistant/provider_{k}", "") or ""
                                        for k in ("kind", "model", "base_url", "vision")}
        s = pv.from_settings(values)
        if not s.is_copilot and not s.api_key:
            s.api_key = self._unsaved_keys.get(s.kind, "")
        return s

    def set_provider(self, setting: pv.ProviderSetting, keep_key: bool) -> None:
        st = self._settings()
        if st is not None:
            for k, v in setting.to_settings().items():
                st.setValue(f"assistant/provider_{k}", v)
        if not setting.is_copilot:
            if keep_key:
                pv.save_key(setting.kind, setting.api_key)
                self._unsaved_keys.pop(setting.kind, None)
            else:
                if pv.load_key(setting.kind):
                    pv.save_key(setting.kind, "")  # the user no longer wants it kept
                self._unsaved_keys[setting.kind] = setting.api_key
        self.shutdown()  # the next question starts with the new choice
        self._checked = False
        self._show_provider()
        self._say("system", f"Answers now come from <b>{html.escape(setting.label())}</b>.")
        if not setting.is_copilot:
            self.refresh_status()

    def open_settings(self) -> None:
        from .assistant_settings import AssistantSettingsDialog

        current = self.provider_setting()
        dlg = AssistantSettingsDialog(self, current, copilot_models=self._copilot_models,
                                      key_kept=bool(not current.is_copilot and pv.load_key(current.kind)))
        if dlg.exec():
            self.set_provider(dlg.setting(), dlg.remember.isChecked())

    def _show_provider(self) -> None:
        s = self.provider_setting()
        self.sign_in_button.setVisible(s.is_copilot)
        name = "Copilot" if s.is_copilot else s.info.label.split(" (")[0].split(" on ")[0]
        self.input.setPlaceholderText(f"Ask {name}: \"add a 6 mm hole through the middle of the plate\"")
        if not s.is_copilot:
            problem = s.problem()
            self.status_label.setText(f"Your own key: <b>{html.escape(s.label())}</b>"
                                      + (f" · {html.escape(problem)} (Model…)" if problem else ""))
        elif not self._checked:
            self.status_label.setText("Assistant: GitHub Copilot"
                                      + (f" ({html.escape(s.model)})" if s.model else ""))

    # ---- the assistant's thread ----------------------------------------------------------
    def _assistant(self) -> cp.AssistantThread:
        home, _ = self.working_folder()
        if self.thread is not None and self.thread.assistant.home != home:
            self.shutdown()  # the project was saved somewhere else: follow it
        self.show_folder()
        if self.thread is None:
            asst = cp.CopilotAssistant(self.win.processor, run_on_model=self.calls.run,
                                       on_event=lambda kind, data: self.event.emit(kind, data), home=home,
                                       provider=self.provider_setting())
            asst.ask_read = self.ask_read  # these run on the GUI thread (run_on_model)
            asst.pick_request = self.pick_request
            asst.show_marks = self.show_marks
            asst.render_view = self.render_view
            st = self._settings()
            asst.small_prompt = bool(st is not None and str(st.value(SMALL_PROMPT, "false")).lower() == "true")
            self.thread = cp.AssistantThread(asst)
        return self.thread

    def _then(self, fut: Future, callback: Callable[[Future], None]) -> None:
        fut.add_done_callback(lambda f: self.done.emit(callback, f))

    @Slot(object, object)
    def _on_done(self, callback, fut: Future) -> None:
        callback(fut)

    def shutdown(self) -> None:
        """Stop Copilot (when the app closes)."""
        self.finish_pick(None, tell=False)
        if self.thread is not None:
            self.thread.close()
            self.thread = None

    # ---- account -------------------------------------------------------------------------
    def _show_status(self, fut: Future) -> None:
        try:
            st = fut.result()
        except Exception as exc:  # noqa: BLE001
            self.status_label.setText(f"Copilot is not available: {exc}")
            return
        if st.get("own_key"):
            self._show_provider()
        elif st["signed_in"]:
            self.status_label.setText(f"Signed in as <b>{html.escape(st['login'])}</b>")
            self.sign_in_button.setText("Switch account")
            self._then(self._assistant().quota(), self._show_quota)
            self._then(self._assistant().models(), self._got_models)
        else:
            self.status_label.setText("Not signed in")
            self.sign_in_button.setText("Sign in with GitHub")

    def _got_models(self, fut: Future) -> None:
        try:
            self._copilot_models = [m["id"] for m in fut.result()]
        except Exception:  # noqa: BLE001 - the list only fills the Model… box
            pass

    def _show_quota(self, fut: Future) -> None:
        try:
            q = fut.result()
        except Exception:  # noqa: BLE001 - the allowance is a nice-to-have
            return
        chat = q.get("chat") or q.get("premium_interactions") or next(iter(q.values()), None)
        if chat and not chat["unlimited"]:
            self.status_label.setText(self.status_label.text() + f" · {chat['left_percent']:g}% of this month's "
                                                                 "allowance left")

    def sign_in(self) -> None:
        """First press: maybe already signed in (Copilot on this computer); else sign in with a code."""
        self.sign_in_button.setEnabled(False)
        if not self._checked:
            self.status_label.setText("Starting Copilot… (the first start downloads it, about 190 MB)")
            self._then(self._assistant().status(), self._checked_then_sign_in)
            return
        self._say("system", "Starting GitHub sign-in…")

        def show_code(url: str, code: str, seconds: int) -> None:
            self.event.emit("code", (url, code, seconds))

        self._then(self._assistant().sign_in(show_code, self._ask_plaintext), self._signed_in)

    def _checked_then_sign_in(self, fut: Future) -> None:
        self._checked = True
        self._show_status(fut)
        try:
            signed_in = fut.result()["signed_in"]
        except Exception:  # noqa: BLE001 - _show_status said why
            self.sign_in_button.setEnabled(True)
            return
        if signed_in:
            self.sign_in_button.setEnabled(True)
        else:
            self.sign_in()

    def _ask_plaintext(self) -> bool:
        return bool(self.calls.run(lambda: QMessageBox.question(
            self, "Store the GitHub sign-in",
            "The assistant keeps your GitHub sign-in in a file in your own app-data folder, which only "
            f"your user account can read:\n\n{cp.runtime_dir()}\n\nKeep it there? Without it you cannot "
            "sign in. Sign out later by deleting that folder.") == QMessageBox.Yes))

    def _signed_in(self, fut: Future) -> None:
        self.sign_in_button.setEnabled(True)
        try:
            login = fut.result()
        except Exception as exc:  # noqa: BLE001
            self._say("error", html.escape(str(exc)))
            return
        self._say("system", f"Signed in as <b>{html.escape(login)}</b>.")
        self.refresh_status()

    def refresh_status(self) -> None:
        self._checked = True
        self._then(self._assistant().status(), self._show_status)

    # ---- chat ----------------------------------------------------------------------------
    def send(self) -> None:
        text = self.input.text().strip()
        if not text or self._busy:
            return
        self.input.clear()
        self.clear_marks()
        self._say("you", html.escape(text))
        chat = self.win.processor.chat
        thread = self._assistant()
        thread.assistant.earlier = cp.earlier_text(chat)  # used only if this starts a fresh chat
        chat.append({"who": "you", "text": text})
        self._set_busy(True)
        self._streaming = False
        self._then(thread.ask(text), self._answered)

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        self.send_button.setVisible(not busy)
        self.send_button.setEnabled(not busy)
        self.stop_button.setVisible(busy)
        self.stop_button.setEnabled(busy)

    def stop(self) -> None:
        """Stop the answer being written: what came so far stays in the chat."""
        if not self._busy or self.thread is None:
            return
        self.stop_button.setEnabled(False)
        self.thread.stop_answer()

    def _answered(self, fut: Future) -> None:
        self._set_busy(False)
        try:
            reply: cp.Reply = fut.result()
        except Exception as exc:  # noqa: BLE001
            self._end_stream(keep=True)
            self._say("error", html.escape(str(exc)))
            return
        if reply.stopped:
            self._end_stream(keep=True)
            self._say("system", "Stopped.")
        if reply.error:
            self._say("error", html.escape(reply.error))
        if not self._checked:
            self.refresh_status()

    @Slot(str, object)
    def _on_event(self, kind: str, data) -> None:
        if kind == "code":
            url, code, seconds = data
            if code:
                self._say("system", f"Open <a href='{html.escape(url)}'>{html.escape(url)}</a> and enter the code "
                                    f"<b style='font-size:14pt'>{html.escape(code)}</b> (valid for "
                                    f"{seconds // 60} minutes). Waiting for GitHub…")
                QDesktopServices.openUrl(QUrl(url))
            else:
                self._say("system", f"Finish signing in in your browser: <a href='{html.escape(url)}'>"
                                    f"{html.escape(url)}</a>")
                QDesktopServices.openUrl(QUrl(url))
        elif kind == "tool":
            self._end_stream(keep=True)
            self._say("tool", html.escape(str(data)))
        elif kind == "delta":
            self._stream(str(data))
        elif kind == "message":
            self._end_stream(keep=False)
            if str(data).strip() == self._kept:  # already shown as it was written
                self._kept = ""
                return
            self._kept = ""
            self._say("copilot", _markdownish(str(data)))
            self.win.processor.chat.append({"who": "assistant", "text": str(data)})
        elif kind == "proposal":
            self.show_proposal(data)
        elif kind == "debug":
            self.add_debug(data)
        elif kind == "picture":
            self.show_picture(data)

    def show_proposal(self, prop: cp.Proposal) -> None:
        self.proposal = prop
        if prop.edits:
            n = len(prop.edits)
            what = f"{n} change{'s' if n != 1 else ''} to the history"
            lines = []
            for e in prop.edits:
                if e["action"] == "edit":
                    lines += [f"Step {e['entry']}, was:  {e['old']}", f"         now:  {e['text']}"]
                elif e["action"] == "insert":
                    lines.append(f"New step {e['entry']}:  {e['text']}")
                else:
                    lines.append(f"Remove step {e['entry']}:  {e['old']}")
            self.proposal_text.setPlainText("\n".join(lines))
            self.run_button.setToolTip("Change these steps; the model rebuilds. To go back, edit the steps back "
                                       "(the old text is shown here and stays in the conversation).")
        else:
            n = len(prop.script.splitlines())
            what = f"{n} command{'s' if n != 1 else ''}"
            self.proposal_text.setPlainText(prop.script)
            self.run_button.setToolTip("Run these commands; they go into the history and Undo takes them back")
        self.proposal_label.setText(f"<b>Proposal</b> ({what}): {html.escape(prop.summary or 'run these commands')}")
        self.proposal_box.show()

    def clear_proposal(self) -> None:
        self.proposal = None
        self.proposal_box.hide()

    def run_proposal(self) -> None:
        if self.proposal is None:
            return
        prop = self.proposal
        res = None
        for line in prop.commands():
            res = self.win.execute(line)
            if not res.ok:
                break
        if res is not None and res.ok:
            self._say("system", "Ran the proposal.")
        elif res is not None:
            self._say("error", "The proposal stopped with an error: " + html.escape(res.message.splitlines()[-1]))
        if prop.edits:
            self._say("system", "Changed: " + "; ".join(
                html.escape(f"step {e['entry']} was “{e['old']}”") for e in prop.edits if e["old"]))
        self.clear_proposal()

    # ---- the answer as it is written ---------------------------------------------------
    def _stream(self, piece: str) -> None:
        """Show a piece of the answer being written, as plain text; the whole
        answer replaces it (formatted) when it is complete."""
        if not piece:
            return
        cur = QTextCursor(self.transcript.document())
        cur.movePosition(QTextCursor.End)
        if self._stream_start < 0:
            self._say("copilot", "")
            cur.movePosition(QTextCursor.End)
            self._stream_start = cur.position()
            self._stream_text = ""
        self._stream_text += piece
        cur.insertText(piece)
        bar = self.transcript.verticalScrollBar()
        if bar.value() >= bar.maximum() - 40:  # follow the end unless the user scrolled up
            bar.setValue(bar.maximum())

    def _end_stream(self, keep: bool) -> None:
        """Finish the answer being written: keep it as it stands (a tool started,
        or Stop), or take it out because the whole answer follows."""
        if self._stream_start < 0:
            return
        if not keep:
            cur = QTextCursor(self.transcript.document())
            cur.setPosition(self._stream_start)
            cur.movePosition(QTextCursor.StartOfBlock)  # with its "Copilot:" label
            cur.movePosition(QTextCursor.End, QTextCursor.KeepAnchor)
            cur.removeSelectedText()
            cur.deletePreviousChar()  # the empty paragraph left behind
        elif self._stream_text.strip():
            self.win.processor.chat.append({"who": "assistant", "text": self._stream_text})
            self._kept = self._stream_text.strip()
        self._stream_start = -1
        self._stream_text = ""

    # ---- the conversation kept with the project ------------------------------------------
    def _on_result(self, res) -> None:
        word = (res.line or "").split(",")[0].strip().upper()
        if res.ok and word in ("OPEN", "NEW"):
            self.show_kept_chat()

    def show_kept_chat(self) -> None:
        """After a project is opened (or a new one started): show its conversation, and
        start a fresh chat that is given that conversation with the first question."""
        if self._busy:
            self.stop()
        self.clear_proposal()
        self.finish_pick(None, tell=False)
        self.clear_marks()
        if self.thread is not None:
            self.thread.new_chat()
        self.transcript.clear()
        chat = self.win.processor.chat
        if not chat:
            self._say("system", "Ask about commands, errors or your model. The conversation is saved with "
                                "the project.")
            return
        self._say("system", f"The conversation saved with this project ({len(chat)} messages). Copilot "
                            "is given it with your next question.")
        for e in chat:
            if e.get("who") == "you":
                self._say("you", html.escape(e.get("text", "")))
            else:
                self._say("copilot", _markdownish(e.get("text", "")))

    def _say(self, who: str, body_html: str) -> None:
        label = {"you": "You", "copilot": "Copilot", "tool": "·", "system": "", "error": "Problem"}[who]
        if who == "tool":
            self.transcript.append(f"<span style='color:gray'>&nbsp;&nbsp;looked with {body_html}</span>")
            return
        colour = {"error": "#b00020", "system": "gray"}.get(who, "")
        style = f" style='color:{colour}'" if colour else ""
        head = f"<b>{label}:</b> " if label else ""
        self.transcript.append(f"<p{style}>{head}{body_html}</p>")


def _markdownish(text: str) -> str:
    """Enough Markdown for chat answers: code blocks and inline code, paragraphs."""
    out, code = [], False
    for line in text.splitlines():
        if line.strip().startswith("```"):
            out.append("</pre>" if code else "<pre>")
            code = not code
            continue
        esc = html.escape(line)
        if code:
            out.append(esc)
        else:
            parts = esc.split("`")
            esc = "".join(f"<code>{p}</code>" if i % 2 else p for i, p in enumerate(parts))
            out.append(esc + "<br>")
    if code:
        out.append("</pre>")
    return "\n".join(out)
