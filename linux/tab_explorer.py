"""API Explorer: browse every Roblox web API endpoint, fill it in, send it with your account, read the answer."""
import json
import shlex
import time
from pathlib import Path
from urllib.parse import quote, urlparse

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem, QPlainTextEdit,
    QPushButton, QSplitter, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

import rbx
from ui_common import button, copy_text, hint

CATALOG = Path(__file__).resolve().parent / "catalog"
UPDATABLE = ["groups", "friends", "presence", "users", "inventory", "accountsettings", "privatemessages", "catalog", "badges",
             "trades", "thumbnails", "premiumfeatures", "develop"]
METHOD_COLOUR = {"GET": "#5ab0ff", "POST": "#3ba55d", "PATCH": "#e0a030", "PUT": "#e0a030", "DELETE": "#e5534b"}


# ------------------------------------------------------------------ reading the specs
def skeleton(schema, defs, depth=0):
    """An example JSON value for a Swagger schema."""
    if not isinstance(schema, dict) or depth > 4:
        return None
    if "example" in schema:
        return schema["example"]
    if "$ref" in schema:
        return skeleton(defs.get(schema["$ref"].split("/")[-1], {}), defs, depth + 1)
    t = schema.get("type")
    if t == "object" or "properties" in schema:
        return {k: skeleton(v, defs, depth + 1) for k, v in (schema.get("properties") or {}).items()}
    if t == "array":
        item = skeleton(schema.get("items", {}), defs, depth + 1)
        return [item] if item is not None else []
    return {"integer": 0, "number": 0, "boolean": False, "string": ""}.get(t)


def load_catalog():
    """Returns a list of endpoint dicts from every spec file in the catalog folder."""
    out = []
    for f in sorted(CATALOG.glob("*.json")):
        try:
            spec = json.loads(f.read_text())
        except (OSError, ValueError):
            continue
        host, defs = spec.get("host", f"{f.stem}.roblox.com"), spec.get("definitions", {})
        for path, ops in spec.get("paths", {}).items():
            for method, op in ops.items():
                if method not in ("get", "post", "patch", "put", "delete"):
                    continue
                params, body = [], None
                for p in op.get("parameters", []):
                    if p.get("in") == "body":
                        body = skeleton(p.get("schema", {}), defs)
                    else:
                        params.append({"name": p["name"], "in": p["in"], "required": p.get("required", False), "desc": (p.get("description") or "").replace("\r\n", " ")})
                notes = "\n".join(f"{code}: {r.get('description', '')}".replace("\r\n", "\n    ") for code, r in op.get("responses", {}).items() if code != "200")
                out.append({"service": f.stem, "host": host, "method": method.upper(), "path": path, "summary": op.get("summary") or "",
                            "params": params, "body": body, "notes": notes})
    return out


class ExplorerTab(QWidget):
    def __init__(self, ctx):
        super().__init__()
        self.ctx = ctx
        self.entries = load_catalog()
        self.entry = None
        outer = QHBoxLayout(self)
        split = QSplitter(Qt.Orientation.Horizontal)
        outer.addWidget(split)

        # ---- left: the catalog
        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)
        self.service = QComboBox()
        self.service.addItem("All services")
        for s in sorted({e["service"] for e in self.entries}):
            self.service.addItem(s)
        self.service.activated.connect(lambda _: self.filter())
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search endpoints (words from the path or description)...")
        self.search.textChanged.connect(self.filter)
        self.only_get = QCheckBox("Only read-only (GET)")
        self.only_get.toggled.connect(self.filter)
        ll.addWidget(self.service)
        ll.addWidget(self.search)
        ll.addWidget(self.only_get)
        self.list = QListWidget()
        self.list.currentRowChanged.connect(self.pick)
        ll.addWidget(self.list, 1)
        self.count = hint("")
        ll.addWidget(self.count)
        ll.addWidget(button("Update the catalog from Roblox", self.update_catalog, "Downloads Roblox's current API lists"))
        split.addWidget(left)

        # ---- right: the request and the answer
        right = QWidget()
        rl = QVBoxLayout(right)
        top = QHBoxLayout()
        self.method = QComboBox()
        self.method.addItems(["GET", "POST", "PATCH", "PUT", "DELETE"])
        self.url = QLineEdit()
        self.url.setPlaceholderText("https://groups.roblox.com/v1/groups/{groupId}")
        top.addWidget(self.method)
        top.addWidget(self.url, 1)
        rl.addLayout(top)
        self.summary = QLabel("")
        self.summary.setWordWrap(True)
        self.summary.setStyleSheet("font-weight: bold;")
        rl.addWidget(self.summary)
        rl.addWidget(QLabel("Parameters  (path ones fill the {placeholders}; empty query ones are left out):"))
        self.params = QTableWidget(0, 4)
        self.params.setHorizontalHeaderLabels(["Name", "Where", "Value", "Notes"])
        self.params.horizontalHeader().setStretchLastSection(True)
        self.params.setColumnWidth(0, 130)
        self.params.setColumnWidth(1, 60)
        self.params.setColumnWidth(2, 220)
        self.params.verticalHeader().setVisible(False)
        self.params.setMaximumHeight(170)
        rl.addWidget(self.params)
        row = QHBoxLayout()
        row.addWidget(button("+ query parameter", self.add_param))
        row.addStretch()
        rl.addLayout(row)
        rl.addWidget(QLabel("Body (JSON), for POST / PATCH / PUT / DELETE:"))
        self.body = QPlainTextEdit()
        self.body.setMaximumHeight(120)
        self.body.setStyleSheet("font-family: monospace;")
        rl.addWidget(self.body)
        send = QHBoxLayout()
        self.use_cookie = QCheckBox("Use my account (cookie)")
        self.use_cookie.setChecked(True)
        self.btn_send = button("Send", self.send)
        self.btn_send.setProperty("primary", True)
        send.addWidget(self.use_cookie)
        send.addStretch()
        send.addWidget(button("Copy as curl", self.copy_curl, "A curl command without your cookie in it"))
        send.addWidget(self.btn_send)
        rl.addLayout(send)
        self.result_head = QLabel("")
        self.result_head.setStyleSheet("font-weight: bold;")
        rl.addWidget(self.result_head)
        self.result = QPlainTextEdit()
        self.result.setReadOnly(True)
        self.result.setStyleSheet("font-family: monospace;")
        rl.addWidget(self.result, 1)
        self.notes = hint("")
        rl.addWidget(self.notes)
        split.addWidget(right)
        split.setStretchFactor(1, 3)
        self.visible = []
        self.filter()

    # ============================================================ catalog list
    def filter(self):
        svc = self.service.currentText()
        words = self.search.text().lower().split()
        get_only = self.only_get.isChecked()
        self.visible = []
        self.list.blockSignals(True)
        self.list.clear()
        for e in self.entries:
            if (svc != "All services" and e["service"] != svc) or (get_only and e["method"] != "GET"):
                continue
            hay = f"{e['service']} {e['path']} {e['summary']} {e['method']}".lower()
            if words and not all(w in hay for w in words):
                continue
            self.visible.append(e)
            it = QListWidgetItem(f"{e['method']:6s} {e['service']}{e['path']}" + (f"   - {e['summary'][:60]}" if e["summary"] else ""))
            it.setForeground(QColor(METHOD_COLOUR.get(e["method"], "#ddd")))
            self.list.addItem(it)
        self.list.blockSignals(False)
        self.count.setText(f"{len(self.visible)} of {len(self.entries)} endpoints")

    def pick(self, row):
        if row < 0 or row >= len(self.visible):
            return
        e = self.entry = self.visible[row]
        self.method.setCurrentText(e["method"])
        self.url.setText(f"https://{e['host']}{e['path']}")
        self.summary.setText(e["summary"] or "(no description)")
        self.params.setRowCount(0)
        for p in e["params"]:
            self.add_param(p["name"], p["in"], "", ("required. " if p["required"] else "") + p["desc"])
        self.body.setPlainText(json.dumps(e["body"], indent=2) if e["body"] is not None else "")
        self.notes.setText(("What the error codes mean:\n    " + e["notes"]) if e["notes"] else "")
        mutating = e["method"] != "GET"
        self.btn_send.setText("Send (changes data)" if mutating else "Send")

    def add_param(self, name="", where="query", value="", note=""):
        r = self.params.rowCount()
        self.params.insertRow(r)
        for c, v in enumerate((name, where, value, note)):
            it = QTableWidgetItem(v)
            if c in (1, 3) or (c == 0 and where == "path"):
                it.setFlags(it.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.params.setItem(r, c, it)

    # ============================================================ building and sending the request
    def build(self):
        """(method, url, query params, body or None). Raises ValueError with a readable message."""
        url = self.url.text().strip()
        query, body = {}, None
        for r in range(self.params.rowCount()):
            name, where, value = (self.params.item(r, i).text().strip() if self.params.item(r, i) else "" for i in (0, 1, 2))
            if where == "path":
                if not value:
                    raise ValueError(f"Fill in the value for {{{name}}}.")
                url = url.replace("{" + name + "}", quote(value, safe=""))
            elif name and value:
                query[name] = value
        if "{" in url:
            raise ValueError("The address still has a {placeholder}: fill in its value in the table.")
        method = self.method.currentText()
        text = self.body.toPlainText().strip()
        if text and method != "GET":
            try:
                body = json.loads(text)
            except ValueError as e:
                raise ValueError(f"The body is not valid JSON: {e}")
        host = (urlparse(url).hostname or "").lower()
        if not url.startswith("https://") or not (host == "roblox.com" or host.endswith(".roblox.com")):
            raise ValueError("For your safety only https://...roblox.com addresses can be used here.")
        return method, url, query, body

    def send(self):
        c = self.ctx
        try:
            method, url, query, body = self.build()
        except ValueError as e:
            self.result_head.setText("")
            self.result.setPlainText(str(e))
            return
        auth = self.use_cookie.isChecked()
        if auth and not c.client.has_cookie:
            auth = False
        if method != "GET":
            detail = f"{method} {url}" + (f"\n\nBody:\n{json.dumps(body, indent=2)}" if body is not None else "")
            if not c.confirm("Send a request that changes data", detail + ("\n\nIt will be sent with your account." if auth else "\n\n(without your account)"), danger=True):
                return
        self.result_head.setText("Sending...")
        self.result.clear()
        t0 = time.time()

        def work():
            try:
                status, data, headers = c.client.request(method, url, params=query or None, json_body=body, auth=auth, raw=True, retries=1)
                return status, data, headers, None
            except rbx.RobloxError as e:
                return e.status, e.body, dict(c.client.last_headers), str(e)
        c.async_.run(work, lambda r: self._answer(r, time.time() - t0, auth))

    def _answer(self, res, secs, auth):
        status, data, headers, err = res
        good = 200 <= status < 300
        limit = headers.get("x-ratelimit-remaining") or headers.get("X-RateLimit-Remaining")
        self.result_head.setText(f"HTTP {status}  -  {secs:.2f} s" + (f"  -  rate limit left: {limit}" if limit else "")
                                 + ("  -  with your account" if auth else "  -  anonymous") + (f"  -  {err}" if err and not good else ""))
        self.result_head.setStyleSheet("font-weight: bold; color: " + ("#3ba55d" if good else "#e5534b"))
        self.result.setPlainText(json.dumps(data, indent=2, ensure_ascii=False) if not isinstance(data, str) else data)

    def copy_curl(self):
        try:
            method, url, query, body = self.build()
        except ValueError as e:
            self.ctx.status(str(e))
            return
        from urllib.parse import urlencode
        full = url + ("?" + urlencode(query) if query else "")
        parts = ["curl", "-X", method, shlex.quote(full)]
        if self.use_cookie.isChecked():
            parts += ["-H", '"Cookie: .ROBLOSECURITY=$ROBLOSECURITY"']
        if body is not None:
            parts += ["-H", "'Content-Type: application/json'", "-d", shlex.quote(json.dumps(body))]
        copy_text(" ".join(parts))
        self.ctx.status("curl command copied (your cookie is not in it; it uses $ROBLOSECURITY).")

    # ============================================================ catalog update
    def update_catalog(self):
        c = self.ctx

        def work():
            done = []
            for s in UPDATABLE:
                try:
                    status, data, _ = c.client.request("GET", f"https://{s}.roblox.com/docs/json/v1", auth=False, retries=1)
                    if isinstance(data, dict) and "paths" in data:
                        (CATALOG / f"{s}.json").write_text(json.dumps(data))
                        done.append(s)
                except rbx.RobloxError:
                    pass
            return done

        def finished(done):
            self.entries = load_catalog()
            self.filter()
            c.status(f"Catalog updated for {len(done)} service(s).")
        c.status("Downloading Roblox's API lists...")
        c.async_.run(work, finished)
