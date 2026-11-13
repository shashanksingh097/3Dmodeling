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
import threading
from concurrent.futures import Future
from typing import TYPE_CHECKING, Any, Callable

from PySide6.QtCore import QObject, Qt, QUrl, Signal, Slot
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from ..ai import copilot as cp

if TYPE_CHECKING:
    from .main_window import MainWindow


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

        lay = QVBoxLayout(self)
        lay.setContentsMargins(4, 4, 4, 4)
        top = QHBoxLayout()
        self.status_label = QLabel("Assistant: GitHub Copilot")
        self.status_label.setWordWrap(True)
        top.addWidget(self.status_label, 1)
        self.sign_in_button = QPushButton("Sign in with GitHub")
        self.sign_in_button.setToolTip("Sign in with your own GitHub account; Copilot Free works too")
        self.sign_in_button.clicked.connect(self.sign_in)
        top.addWidget(self.sign_in_button)
        lay.addLayout(top)

        self.transcript = QTextBrowser()
        self.transcript.setOpenExternalLinks(True)
        lay.addWidget(self.transcript, 1)

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
        lay.addLayout(row)

        self.event.connect(self._on_event)
        self.done.connect(self._on_done)

        if not cp.sdk_available():
            self.status_label.setText("The assistant is not installed.")
            self._say("system", html.escape(cp.SDK_HINT))
            for w in (self.sign_in_button, self.send_button, self.input):
                w.setEnabled(False)
        else:
            self._say("system", "Ask about commands, errors or your model. Copilot tries its scripts in a "
                                "sandbox first and shows them here with a <b>Run</b> button; it never changes "
                                "your model by itself. Requests count against your own Copilot plan.")

    # ---- the assistant's thread ----------------------------------------------------------
    def _assistant(self) -> cp.AssistantThread:
        if self.thread is None:
            asst = cp.CopilotAssistant(self.win.processor, run_on_model=self.calls.run,
                                       on_event=lambda kind, data: self.event.emit(kind, data))
            self.thread = cp.AssistantThread(asst)
        return self.thread

    def _then(self, fut: Future, callback: Callable[[Future], None]) -> None:
        fut.add_done_callback(lambda f: self.done.emit(callback, f))

    @Slot(object, object)
    def _on_done(self, callback, fut: Future) -> None:
        callback(fut)

    def shutdown(self) -> None:
        """Stop Copilot (when the app closes)."""
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
        if st["signed_in"]:
            self.status_label.setText(f"Signed in as <b>{html.escape(st['login'])}</b>")
            self.sign_in_button.setText("Switch account")
            self._then(self._assistant().quota(), self._show_quota)
        else:
            self.status_label.setText("Not signed in")
            self.sign_in_button.setText("Sign in with GitHub")

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
            "This computer has no keychain for passwords. Store the GitHub sign-in in a plain file in "
            "your home folder?") == QMessageBox.Yes))

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
        self._say("you", html.escape(text))
        self._busy = True
        self.send_button.setEnabled(False)
        self._streaming = False
        self._then(self._assistant().ask(text), self._answered)

    def _answered(self, fut: Future) -> None:
        self._busy = False
        self.send_button.setEnabled(True)
        try:
            reply: cp.Reply = fut.result()
        except Exception as exc:  # noqa: BLE001
            self._say("error", html.escape(str(exc)))
            return
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
            self._say("tool", html.escape(str(data)))
        elif kind == "message":
            self._say("copilot", _markdownish(str(data)))
        elif kind == "proposal":
            self.show_proposal(data)

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
