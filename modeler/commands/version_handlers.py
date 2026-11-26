"""VERSION: which version this is, what changed in it, and whether a newer one is out (PLAN item 117)."""

from __future__ import annotations

from .. import __version__, updates
from .processor import Arg, CommandError, Processor, command


@command(
    "VERSION",
    Arg("what", str, "", "NEWS (what changed in this version) or CHECK (ask GitHub for a newer one); "
                         "nothing: the version"),
    Arg("since", str, "", "with NEWS: every change since this version (e.g. 0.5.0)"),
    logged=False,
    help="This app's version: VERSION · what changed in it: VERSION, NEWS (or VERSION, NEWS, 0.5.0: every "
         "change since 0.5.0) · whether a newer version is out: VERSION, CHECK (asks GitHub; nothing about you "
         "or the model is sent). Preferences can check by itself when the app starts.",
)
def version(p: Processor, what, since):
    w = what.strip().upper()
    if not w:
        p.give_report("version", {"version": __version__})
        return f"3Dmodeling {__version__} (VERSION, NEWS: what changed; VERSION, CHECK: is a newer one out?)"
    if w == "NEWS":
        if since:
            try:
                updates.parse(since)
            except updates.UpdateError as exc:
                raise CommandError(f"VERSION: {exc}") from None
        secs = updates.notes(__version__, since.strip())
        p.give_report("version", {"version": __version__, "news": [{"version": v, "text": b} for v, b in secs]})
        if not secs:
            return (f"no notes for {__version__}" + (f" since {since}" if since else "")
                    + " (the changelog is not here, or has no such section)")
        return updates.as_markdown(secs)
    if w == "CHECK":
        try:
            r = updates.check()
        except updates.UpdateError as exc:
            raise CommandError(f"VERSION: {exc}") from None
        p.give_report("version", {"version": __version__, "latest": r["latest"], "newer": r["newer"], "url": r["url"]})
        if r["newer"]:
            return f"version {r['latest']} is out (this is {__version__}): {r['url']}"
        return f"this is the newest version ({__version__}; the newest release is {r['latest']})"
    raise CommandError("VERSION: NEWS, CHECK or nothing")
