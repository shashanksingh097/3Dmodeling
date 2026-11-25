"""Is there a newer version, and what changed (PLAN item 117).

``latest()`` asks GitHub for the newest published release of the app (only when the user turned the
check on in Preferences, or asks with Help > Check for a new version / ``VERSION, CHECK``); nothing
about the user or the model is sent, only the request itself. ``notes(version)`` reads what changed
in a version from CHANGELOG.md, which ships with the app, for the What's new page shown once after
an update.
"""

from __future__ import annotations

import json
import os
import re
import sys
import urllib.error
import urllib.request

from . import __version__

REPO = "shashanksingh097/3Dmodeling"
API_URL = f"https://api.github.com/repos/{REPO}/releases/latest"
RELEASES_URL = f"https://github.com/{REPO}/releases"
PKG = os.path.dirname(os.path.abspath(__file__))


class UpdateError(RuntimeError):
    pass


def parse(version: str) -> tuple[int, ...]:
    """'v0.6.0' -> (0, 6, 0); the numbers only (a '-beta' tail sorts as the same release)."""
    nums = re.findall(r"\d+", (version or "").split("-")[0].split("+")[0])
    if not nums:
        raise UpdateError(f"{version!r} is not a version")
    return tuple(int(n) for n in nums[:4])


def is_newer(other: str, than: str = __version__) -> bool:
    try:
        a, b = parse(other), parse(than)
    except UpdateError:
        return False
    n = max(len(a), len(b))
    return a + (0,) * (n - len(a)) > b + (0,) * (n - len(b))


def latest(timeout: float = 6.0, opener=None) -> dict:
    """The newest published release: {version, url, name, published, notes}. UpdateError when GitHub
    cannot be reached or answers oddly (no internet, a proxy, too many checks)."""
    req = urllib.request.Request(API_URL, headers={"Accept": "application/vnd.github+json",
                                                   "User-Agent": "3Dmodeling-update-check"})
    try:
        with (opener or urllib.request.urlopen)(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            raise UpdateError("no release has been published yet") from None
        raise UpdateError(f"GitHub answered {exc.code}") from None
    except (urllib.error.URLError, OSError, TimeoutError) as exc:
        raise UpdateError(f"could not reach GitHub ({getattr(exc, 'reason', exc)})") from None
    except ValueError:
        raise UpdateError("GitHub's answer could not be read") from None
    tag = str(data.get("tag_name") or "")
    try:
        parse(tag)
    except UpdateError:
        raise UpdateError(f"the newest release has no version number ({tag!r})") from None
    return {"version": tag.lstrip("vV"), "url": str(data.get("html_url") or RELEASES_URL),
            "name": str(data.get("name") or tag), "published": str(data.get("published_at") or ""),
            "notes": str(data.get("body") or "")}


def check(timeout: float = 6.0, opener=None) -> dict:
    """{current, latest, newer (bool), url, notes}; UpdateError as latest()."""
    rel = latest(timeout, opener)
    return {"current": __version__, "latest": rel["version"], "newer": is_newer(rel["version"]), "url": rel["url"],
            "notes": rel["notes"], "published": rel["published"]}


def changelog_path() -> str | None:
    """CHANGELOG.md: bundled with a built app (modeler/docs), or the repository's."""
    roots = [os.path.join(PKG, "docs"), os.path.dirname(PKG)]
    if getattr(sys, "_MEIPASS", None):
        roots.insert(0, os.path.join(sys._MEIPASS, "modeler", "docs"))
    for d in roots:
        f = os.path.join(d, "CHANGELOG.md")
        if os.path.isfile(f):
            return f
    return None


def sections(text: str) -> list[tuple[str, str]]:
    """CHANGELOG.md's version sections, newest first: [(version or 'Unreleased', body)]."""
    out = []
    parts = re.split(r"^## \[([^\]]+)\][^\n]*\n", text, flags=re.M)
    for k in range(1, len(parts) - 1, 2):
        out.append((parts[k].strip(), parts[k + 1].strip()))
    return out


def notes(version: str = __version__, since: str = "") -> list[tuple[str, str]]:
    """What changed: the section for ``version``, or with ``since`` every version after it up to ``version``
    (newest first). Empty when the changelog is not there or has no such section."""
    path = changelog_path()
    if path is None:
        return []
    with open(path, encoding="utf-8") as fh:
        secs = [(v, b) for v, b in sections(fh.read()) if v.lower() != "unreleased"]
    if since:
        return [(v, b) for v, b in secs if is_newer(v, since) and not is_newer(v, version)]
    try:
        want = parse(version)
    except UpdateError:
        return []
    return [(v, b) for v, b in secs if _same(v, want)]


def _same(v: str, want: tuple[int, ...]) -> bool:
    try:
        got = parse(v)
    except UpdateError:
        return False
    n = max(len(got), len(want))
    return got + (0,) * (n - len(got)) == want + (0,) * (n - len(want))


def as_markdown(secs: list[tuple[str, str]]) -> str:
    return "\n\n".join(f"## {v}\n\n{b}" for v, b in secs)
