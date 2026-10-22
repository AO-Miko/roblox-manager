"""Home: your account, and Discover (games) as a second page inside it."""
from PySide6.QtWidgets import QTabWidget, QVBoxLayout, QWidget


class HomePage(QWidget):
    def __init__(self, account, discover):
        super().__init__()
        self.account, self.discover = account, discover
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.tabs = QTabWidget()
        self.tabs.setProperty("sub", True)
        self.tabs.addTab(account, "Account")
        self.tabs.addTab(discover, "Discover")
        lay.addWidget(self.tabs)
        self.tabs.currentChanged.connect(lambda _=0: self.ensure_loaded())

    def ensure_loaded(self):
        if self.tabs.currentWidget() is self.discover:
            self.discover.ensure_loaded()
