"""The detector behind test_text_fit.py: finds text that does not fit (is cut off at the edge) on the pages of the window.
Checks labels, buttons, check boxes, group titles, tab titles, text boxes' hints, drop-downs and table headers.
Used by test_text_fit.py (empty window) and test_gui_full.py (window full of data)."""
import time

from PySide6.QtGui import QFontMetrics, QTextDocument
from PySide6.QtWidgets import (QAbstractButton, QApplication, QComboBox, QGroupBox, QLabel, QLineEdit, QTabBar, QTabWidget, QTableView, QWidget)

import ui_common


def plain(text):
    if "<" in text and ">" in text:
        d = QTextDocument()
        d.setHtml(text)
        return d.toPlainText()
    return text


def adv(w, text):
    return QFontMetrics(w.font()).horizontalAdvance(text)


def where(w):
    names, p = [], w
    while p is not None and len(names) < 3:
        names.append(type(p).__name__)
        p = p.parentWidget()
    return "/".join(names)


def inspect(page, root, problems):
    def report(kind, w, text, detail):
        problems.setdefault((page, kind, text[:60], detail), where(w))

    for w in root.findChildren(QWidget):
        if not w.isVisible() or w.width() <= 0 or w.height() <= 0:
            continue
        if isinstance(w, ui_common.WrapCheck):
            if w.heightForWidth(w.width()) > w.height() + 2:
                report("check box", w, w.text(), f"needs {w.heightForWidth(w.width())} px height, has {w.height()}")
            continue
        if isinstance(w, QLabel) and w.text() and w.pixmap() is None:
            t = plain(w.text())
            if not t.strip():
                continue
            if w.wordWrap():
                if w.heightForWidth(w.width()) > w.height() + 2:
                    report("label", w, t, f"needs {w.heightForWidth(w.width())} px height, has {w.height()}")
            else:
                longest = max((adv(w, line) for line in t.splitlines()), default=0)
                if longest > w.width() + 1 and w.width() < w.sizeHint().width() - 1:
                    report("label", w, t, f"text {longest} px, label {w.width()} px")
        elif isinstance(w, QAbstractButton) and w.text() and not isinstance(w, QTabBar):
            if w.width() < w.sizeHint().width() - 2 and w.width() < adv(w, w.text()) + 16:
                report("button", w, w.text(), f"{w.width()} px, needs {w.sizeHint().width()}")
        elif isinstance(w, QGroupBox) and w.title():
            if adv(w, w.title()) + 24 > w.width():
                report("group title", w, w.title(), f"{w.width()} px")
        elif isinstance(w, QLineEdit) and w.placeholderText() and not w.text():
            if adv(w, w.placeholderText()) + 24 > w.width():
                report("text box hint", w, w.placeholderText(), f"hint {adv(w, w.placeholderText())} px, box {w.width()} px")
        elif isinstance(w, QComboBox) and w.count():
            longest = max(adv(w, w.itemText(i)) for i in range(w.count()))
            if longest + 44 > w.width() and w.width() < w.sizeHint().width() - 2:
                report("drop-down", w, w.itemText(w.currentIndex()), f"widest entry {longest} px, box {w.width()} px")
        elif isinstance(w, QTabBar):
            if w.count() and w.tabRect(w.count() - 1).right() > w.width() + 2:
                report("tab titles", w, ", ".join(w.tabText(i) for i in range(w.count()))[:60], f"tabs reach {w.tabRect(w.count() - 1).right()} px, bar {w.width()} px")
        elif isinstance(w, QTableView) and w.model() is not None:
            h = w.horizontalHeader()
            if h.isVisible():
                for c in range(h.count()):
                    t = str(w.model().headerData(c, h.orientation()) or "")
                    if t and not h.isSectionHidden(c) and adv(h, t) + 16 > h.sectionSize(c):
                        report("table header", w, t, f"column {h.sectionSize(c)} px, text {adv(h, t)} px")


def every_page(win, app=None):
    """(name, widget) for every tab, and every sub-tab inside it, shown one after the other."""
    app = app or QApplication.instance()
    for i in range(win.tabs.count()):
        win.tabs.setCurrentIndex(i)
        app.processEvents()
        top = win.tabs.tabText(i)
        page = win.tabs.widget(i)
        subs = list(page.findChildren(QTabWidget)) + ([page] if isinstance(page, QTabWidget) else [])
        yield top, page
        for s in subs:
            for j in range(s.count()):
                s.setCurrentIndex(j)
                app.processEvents()
                yield f"{top} > {s.tabText(j)}", s.widget(j)


def check_window(win, widths, problems, app=None):
    app = app or QApplication.instance()
    for width in widths:
        win.resize(width, 760)
        for _ in range(5):
            app.processEvents()
            time.sleep(0.02)
        for name, page in every_page(win, app):
            inspect((width, name), page, problems)
        inspect((width, "(side bar)"), win.sidebar, problems)
        inspect((width, "(page header)"), win.header, problems)


def lines(problems):
    return [f"CUT  {page[0]:>4}px  {page[1]:<28} {kind:<12} {text!r}  [{detail}]  in {where_}"
            for (page, kind, text, detail), where_ in sorted(problems.items(), key=lambda kv: (kv[0][0][0], kv[0][0][1], kv[0][1]))]
