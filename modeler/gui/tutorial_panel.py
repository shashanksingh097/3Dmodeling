"""The Tutorial panel (PLAN item 94): a lesson beside the model, checked as you go.

With no lesson running it lists the tutorials, each with a Start button. During
a lesson it shows the step's text, its checks (✓ when the model has it), and
Show me (runs the step for you), Back, Next and Stop. Every button is a
TUTORIAL command (commands/tutorial_handlers.py), so it shows in the output
and works the same typed. The checks run again after every change to the
model, so Next lights up the moment the step is done, whether it was done by
clicking, typing or the assistant.
"""

from __future__ import annotations

import html
import re

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from .. import i18n
from ..commands import tutorial_handlers as th


def md_html(text: str) -> str:
    """The little Markdown a tutorial uses: paragraphs, **bold**, `code`."""
    out = []
    for para in re.split(r"\n\s*\n", text.strip()):
        t = html.escape(" ".join(line.strip() for line in para.splitlines()))
        t = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", t)
        t = re.sub(r"`(.+?)`", r"<code style='background:#eef1f6'>\1</code>", t)
        out.append(f"<p>{t}</p>")
    return "".join(out)


class TutorialPanel(QWidget):
    def __init__(self, win) -> None:
        super().__init__()
        self.win = win
        self.setObjectName("tutorial_panel")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(6, 4, 6, 4)
        lay.setSpacing(4)
        self.heading = QLabel()
        self.heading.setObjectName("tutorial_heading")
        self.heading.setWordWrap(True)
        lay.addWidget(self.heading)
        self.progress = QProgressBar()
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(6)
        lay.addWidget(self.progress)
        self.body = QTextBrowser()
        self.body.setObjectName("tutorial_text")
        self.body.setOpenLinks(False)
        self.body.anchorClicked.connect(self._link)
        lay.addWidget(self.body, 1)
        self.checks = QLabel()
        self.checks.setObjectName("tutorial_checks")
        self.checks.setWordWrap(True)
        self.checks.setTextFormat(Qt.RichText)
        lay.addWidget(self.checks)
        row = QHBoxLayout()
        self.show_me = QPushButton("Show me")
        self.show_me.setToolTip("Do this step for me, so I can see how (TUTORIAL, SHOW)")
        self.show_me.clicked.connect(lambda: self.win.execute("TUTORIAL, SHOW"))
        self.back = QPushButton("Back")
        self.back.setToolTip("The step before (TUTORIAL, BACK)")
        self.back.clicked.connect(lambda: self.win.execute("TUTORIAL, BACK"))
        self.next = QPushButton("Next")
        self.next.setToolTip("The next step, once this one is done (TUTORIAL, NEXT)")
        self.next.setDefault(True)
        self.next.clicked.connect(lambda: self.win.execute("TUTORIAL, NEXT"))
        self.stop = QPushButton("Stop")
        self.stop.setToolTip("End the tutorial; the model stays as it is (TUTORIAL, STOP)")
        self.stop.clicked.connect(lambda: self.win.execute("TUTORIAL, STOP"))
        for b in (self.show_me, self.back, self.next, self.stop):
            row.addWidget(b)
        lay.addLayout(row)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(150)
        self._timer.timeout.connect(self.recheck)
        win.processor.history_listeners.append(self._timer.start)
        self.refresh()

    # ---- what shows --------------------------------------------------------------------------
    def refresh(self) -> None:
        lesson = self.win.processor.tutorial
        running = lesson is not None
        for b in (self.show_me, self.back, self.next, self.stop):
            b.setVisible(running)
        self.progress.setVisible(running)
        self.checks.setVisible(running)
        if not running:
            self._show_list()
            return
        s = lesson.step
        n, total = lesson.index + 1, len(lesson.tut.steps)
        self.heading.setText(f"<b>{html.escape(lesson.tut.title)}</b><br>step {n} of {total}: "
                             f"<b>{html.escape(s.title)}</b>")
        self.progress.setRange(0, total)
        self.progress.setValue(n - 1 + (1 if th._passed(lesson) else 0))
        self.body.setHtml(md_html(s.text))
        self.checks.setText(self._checks_html(lesson))
        self.show_me.setEnabled(bool(s.hints))
        self.back.setEnabled(lesson.index > 0)
        done = th._passed(lesson)
        self.next.setEnabled(done)
        self.next.setText(i18n.tr("Finish") if lesson.last else i18n.tr("Next"))

    def _checks_html(self, lesson) -> str:
        if not lesson.step.checks:
            return "<span style='color:#555'>Read this, then press <b>Next</b>.</span>"
        rows = []
        for r in lesson.results:
            if r["pass"]:
                rows.append(f"<span style='color:#2e7d32'>✓ {html.escape(_short(r))}</span>")
            else:
                rows.append(f"<span style='color:#777'>○ {html.escape(_short(r))}</span>")
        if th._passed(lesson):
            rows.append("<b style='color:#2e7d32'>Done! Press " + ("Finish" if lesson.last else "Next") + ".</b>")
        return "<br>".join(rows)

    def _show_list(self) -> None:
        self.heading.setText(i18n.tr("<b>Tutorials</b><br>Short lessons that check your model as you go."))
        parts = []
        for t in th.available():
            parts.append(f"<p><a href='start:{html.escape(t.name)}'><b>{html.escape(t.title)}</b></a><br>"
                         f"{html.escape(t.about)}</p>")
        parts.append("<p style='color:#555'>Each one starts a new project. Click a title to start.</p>")
        self.body.setHtml("".join(parts))

    def _link(self, url) -> None:
        text = url.toString()
        if text.startswith("start:"):
            self.start(text[6:])

    # ---- doing ---------------------------------------------------------------------------------
    def start(self, name: str):
        p = self.win.processor
        how = ""
        if th._unsaved(p):
            ans = QMessageBox.question(
                self.win, "Start a tutorial",
                "A tutorial starts a new project, and this one has changes that are not saved.\n\n"
                "Start the tutorial anyway (the changes are lost)?",
                QMessageBox.Yes | QMessageBox.Cancel, QMessageBox.Cancel)
            if ans != QMessageBox.Yes:
                return None
            how = ", NEW"
        return self.win.execute(f"TUTORIAL, {name}{how}")

    def recheck(self) -> None:
        """Check the step again (after the model changed), quietly."""
        lesson = self.win.processor.tutorial
        if lesson is None:
            return
        before = th._passed(lesson) and bool(lesson.results or not lesson.step.checks)
        th.check_step(self.win.processor, lesson)
        self.refresh()
        if th._passed(lesson) and not before and lesson.step.checks:
            self.win.statusBar().showMessage(f"Tutorial: step {lesson.index + 1} done. Press Next", 6000)


def _short(r: dict) -> str:
    return th.r_text(r)
