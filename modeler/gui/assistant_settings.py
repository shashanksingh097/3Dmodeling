"""The Assistant's settings: GitHub Copilot or your own key, the model, the
service's address and the key (kept on this computer only when asked)."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QVBoxLayout,
    QWidget,
)

from ..ai import providers as pv


class AssistantSettingsDialog(QDialog):
    def __init__(self, parent: QWidget | None, setting: pv.ProviderSetting, *,
                 copilot_models: list[str] | None = None, key_kept: bool = False) -> None:
        super().__init__(parent)
        self.setWindowTitle("Assistant settings")
        self.setMinimumWidth(480)
        self.copilot_models = list(copilot_models or [])
        self._keys = {setting.kind: setting.api_key} if setting.api_key else {}
        self._models = {setting.kind: setting.model}
        self._urls = {setting.kind: setting.base_url}
        self._vision = {setting.kind: setting.sees_pictures()}

        lay = QVBoxLayout(self)
        form = QFormLayout()
        self.kind = QComboBox()
        for k in pv.KINDS.values():
            self.kind.addItem(k.label, k.key)
        form.addRow("Answers from", self.kind)
        self.model = QComboBox()
        self.model.setEditable(True)
        form.addRow("Model", self.model)
        self.url = QLineEdit()
        form.addRow("Address", self.url)
        self.key = QLineEdit()
        self.key.setEchoMode(QLineEdit.Password)
        self.key.setPlaceholderText("paste the API key")
        form.addRow("API key", self.key)
        self.remember = QCheckBox("Keep the key on this computer (in a file only your user account can read)")
        self.remember.setChecked(key_kept)
        form.addRow("", self.remember)
        self.vision = QCheckBox("The model can see pictures (the assistant may then look at the 3D view)")
        form.addRow("", self.vision)
        lay.addLayout(form)
        self.help = QLabel()
        self.help.setWordWrap(True)
        self.help.setOpenExternalLinks(True)
        lay.addWidget(self.help)
        self.problem = QLabel()
        self.problem.setStyleSheet("color: #c0392b")
        lay.addWidget(self.problem)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        self.ok_button = buttons.button(QDialogButtonBox.Ok)
        lay.addWidget(buttons)

        self._kind = setting.kind
        self.kind.setCurrentIndex(max(0, self.kind.findData(setting.kind)))
        self._show_kind()
        self.kind.currentIndexChanged.connect(self._kind_changed)
        for sig in (self.model.currentTextChanged, self.url.textChanged, self.key.textChanged):
            sig.connect(self._check)

    def _remember_fields(self) -> None:
        self._models[self._kind] = self.model.currentText().strip()
        self._urls[self._kind] = self.url.text().strip()
        if self.key.text():
            self._keys[self._kind] = self.key.text()
        self._vision[self._kind] = self.vision.isChecked()

    def _kind_changed(self) -> None:
        self._remember_fields()
        self._kind = self.kind.currentData()
        self._show_kind()

    def _show_kind(self) -> None:
        info = pv.KINDS[self._kind]
        self.model.blockSignals(True)
        self.model.clear()
        if info.key == "copilot":
            self.model.addItem("")
            self.model.addItems(self.copilot_models)
        self.model.setEditText(self._models.get(self._kind, ""))
        self.model.lineEdit().setPlaceholderText(info.model_hint)
        self.model.blockSignals(False)
        self.url.setText(self._urls.get(self._kind, "") or info.base_url)
        self.url.setEnabled(info.url_editable)
        self.url.setPlaceholderText("https://..." if info.url_editable else "")
        own = info.key != "copilot"
        self.key.setText(self._keys.get(self._kind, ""))
        self.key.setEnabled(own)
        self.key.setPlaceholderText("paste the API key" if info.needs_key else
                                    ("not needed" if info.key == "ollama" else "optional"))
        self.remember.setEnabled(own)
        self.vision.setChecked(self._vision.get(self._kind, info.vision))
        self.vision.setEnabled(own)
        self.vision.setVisible(own)
        text = info.help
        if info.key == "copilot" and not self.copilot_models:
            text += " Sign in to see the models your plan offers."
        self.help.setText(text)
        self._check()

    def setting(self) -> pv.ProviderSetting:
        info = pv.KINDS[self.kind.currentData()]
        url = self.url.text().strip()
        return pv.ProviderSetting(info.key, self.model.currentText().strip(),
                                  "" if url == info.base_url else url,
                                  self.key.text().strip() if info.key != "copilot" else "",
                                  vision=None if info.key == "copilot" else self.vision.isChecked())

    def _check(self) -> None:
        problem = self.setting().problem()
        self.problem.setText(f"To use it: {problem}." if problem else "")
        self.ok_button.setEnabled(not problem)
