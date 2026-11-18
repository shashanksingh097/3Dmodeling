"""Where the assistant's answers come from: GitHub Copilot (the user's own GitHub
account) or "your own key" for a model service the user pays for, or a model
running on their own computer.

The Copilot runtime does the talking either way (the SDK's "bring your own
key" providers), so the tools, the Debug tab and the proposals work the same;
with a key no GitHub account is needed.

Keys are kept only when the user asks: in ``keys.json`` in the per-user
app-data folder (:func:`modeler.ai.copilot.runtime_dir`), readable by the
user only. ``MODELER_AI_KEY`` overrides a stored key.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Kind:
    key: str
    label: str
    sdk_type: str = ""  # the SDK's provider type: openai, anthropic, azure ("" = GitHub Copilot)
    base_url: str = ""  # the usual address; the user may change it
    needs_key: bool = True
    url_editable: bool = False
    model_hint: str = ""
    help: str = ""


KINDS: dict[str, Kind] = {k.key: k for k in (
    Kind("copilot", "GitHub Copilot", needs_key=False,
         model_hint="empty: Copilot picks (Copilot Free always does)",
         help="Sign in with your own GitHub account. Any Copilot plan works, Copilot Free too."),
    Kind("openai", "OpenAI (your own key)", "openai", "https://api.openai.com/v1",
         model_hint="a model name from your OpenAI account",
         help="An API key from platform.openai.com. Requests are billed to your OpenAI account."),
    Kind("anthropic", "Anthropic Claude (your own key)", "anthropic", "https://api.anthropic.com",
         model_hint="for example claude-sonnet-5-5",
         help="An API key from console.anthropic.com. Requests are billed to your Anthropic account."),
    Kind("azure", "Azure OpenAI (your own key)", "azure", "", url_editable=True,
         model_hint="the deployment name",
         help="Your Azure OpenAI resource's address (https://NAME.openai.azure.com) and key."),
    Kind("ollama", "Ollama on this computer (no key)", "openai", "http://localhost:11434/v1",
         needs_key=False, url_editable=True, model_hint="a model you pulled, one that can call tools",
         help="A model running on your own computer with Ollama. Nothing leaves your computer. "
              "Small models often call the tools badly."),
    Kind("custom", "Other OpenAI-compatible service", "openai", "", url_editable=True,
         model_hint="the model name the service expects",
         help="Any service that speaks the OpenAI chat completions API (LM Studio, vLLM, a company "
              "gateway...). The key is optional."),
)}


@dataclass
class ProviderSetting:
    """What the user chose: the kind, the model, the address and the key."""

    kind: str = "copilot"
    model: str = ""
    base_url: str = ""
    api_key: str = field(default="", repr=False)

    @property
    def info(self) -> Kind:
        return KINDS.get(self.kind, KINDS["copilot"])

    @property
    def is_copilot(self) -> bool:
        return self.info.key == "copilot"

    def label(self) -> str:
        if self.is_copilot:
            return "GitHub Copilot" + (f" ({self.model})" if self.model else "")
        name = self.info.label.split(" (")[0]
        return f"{name}: {self.model}" if self.model else name

    def url(self) -> str:
        return (self.base_url or self.info.base_url).strip()

    def problem(self) -> str:
        """What is missing before it can be used ("" when nothing)."""
        if self.is_copilot:
            return ""
        if not self.model.strip():
            return "name the model"
        if not self.url():
            return "give the service's address"
        if self.info.needs_key and not (self.api_key or os.environ.get("MODELER_AI_KEY")):
            return "enter the API key"
        return ""

    def sdk_config(self) -> dict[str, Any] | None:
        """The SDK's ``ProviderConfig`` (None for GitHub Copilot)."""
        if self.is_copilot:
            return None
        cfg: dict[str, Any] = {"type": self.info.sdk_type, "base_url": self.url(),
                               "wire_model": self.model.strip()}
        key = os.environ.get("MODELER_AI_KEY") or self.api_key
        if key:
            cfg["api_key"] = key
        if self.kind == "ollama":
            cfg["model_provider"] = "ollama"
        return cfg

    def to_settings(self) -> dict[str, str]:
        """The parts kept in the app's settings (never the key)."""
        return {"kind": self.kind, "model": self.model, "base_url": self.base_url}


# ---- keys, kept only when the user asks ----------------------------------------------------
def _keys_file() -> str:
    from .copilot import runtime_dir

    return os.path.join(runtime_dir(), "keys.json")


def load_key(kind: str) -> str:
    try:
        with open(_keys_file(), encoding="utf-8") as f:
            return str(json.load(f).get(kind, ""))
    except (OSError, ValueError):
        return ""


def save_key(kind: str, key: str) -> str:
    """Keep (or with an empty key, forget) the key for one kind; returns the file's path."""
    path = _keys_file()
    try:
        with open(path, encoding="utf-8") as f:
            keys = json.load(f)
    except (OSError, ValueError):
        keys = {}
    if key:
        keys[kind] = key
    else:
        keys.pop(kind, None)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(keys, f)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    return path


def from_settings(values: dict[str, Any]) -> ProviderSetting:
    kind = str(values.get("kind") or "copilot")
    if kind not in KINDS:
        kind = "copilot"
    s = ProviderSetting(kind, str(values.get("model") or ""), str(values.get("base_url") or ""))
    if not s.is_copilot:
        s.api_key = load_key(kind)
    return s
