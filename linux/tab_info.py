"""Settings page: the settings, and the updates (controls plus the update log that says what changed in each version)."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QLabel, QScrollArea, QTabWidget, QVBoxLayout, QWidget

import changelog
from tab_settings import SettingsTab


class UpdatesPage(QWidget):
    """The update controls on top, the update log below."""

    def __init__(self, settings_tab):
        super().__init__()
        self.settings_tab = settings_tab
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        outer.addWidget(scroll)
        body = QWidget()
        scroll.setWidget(body)
        lay = QVBoxLayout(body)
        lay.addWidget(settings_tab.update_box)
        title = QLabel("<b>Update log</b>")
        lay.addWidget(title)
        self.log = QLabel()
        self.log.setTextFormat(Qt.TextFormat.RichText)
        self.log.setWordWrap(True)
        self.log.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.log.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        lay.addWidget(self.log)
        lay.addStretch()
        self.refresh()

    def refresh(self):
        import updater
        self.log.setText(changelog.html(changelog.load(), updater.version()))


class InfoTab(QTabWidget):
    def __init__(self, ctx, on_cleared=None):
        super().__init__()
        self.setProperty("sub", True)
        self.settings_tab = SettingsTab(ctx, on_cleared=on_cleared)
        self.updates = UpdatesPage(self.settings_tab)
        self.addTab(self.settings_tab, "Preferences")
        self.addTab(self.updates, "Updates")
