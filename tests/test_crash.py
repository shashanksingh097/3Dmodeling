"""Crash guard without a window: error log and the lock left by a crash."""

import sys

from modeler.crash import CrashGuard


def test_errors_are_logged(tmp_path):
    g = CrashGuard(str(tmp_path / "logs"), install=False)
    seen = []
    g.on_error = lambda summary, details: seen.append(summary)
    try:
        raise KeyError("x")
    except KeyError:
        g.excepthook(*sys.exc_info())
    assert seen == ["KeyError: 'x'"]
    assert "KeyError" in open(g.errors_path, encoding="utf-8").read()
    g.clean_exit()


def test_last_session_crash_is_noticed(tmp_path):
    logs = str(tmp_path / "logs")
    first = CrashGuard(logs, install=False)
    assert not first.last_session_crashed
    # no clean_exit: the lock stays, as after a crash
    second = CrashGuard(logs, install=False)
    assert second.last_session_crashed
    second.clean_exit()
    assert not CrashGuard(logs, install=False).last_session_crashed
