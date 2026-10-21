"""Money tab: your Robux, what is pending, totals for a period, and your transaction history."""
import re

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QCheckBox, QComboBox, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

import rbx
from tab_account import pending_rows
from ui_common import button, export_csv, fill_table, hint, make_table

PERIODS = [("Day", "Today"), ("Week", "This week"), ("Month", "This month"), ("Year", "This year")]
KINDS = [("Sale", "Sales"), ("Purchase", "Purchases"), ("GroupPayout", "Group payouts"), ("EngagementPayout", "Premium payouts"),
         ("GroupEngagementPayout", "Group premium payouts"), ("AffiliateSale", "Affiliate sales"), ("AdImpressionPayout", "Ad payouts"),
         ("PremiumStipend", "Premium stipends"), ("CurrencyPurchase", "Robux bought"), ("TradeSystem", "Trades")]
TOTAL_NAMES = {"salesTotal": "Sales", "purchasesTotal": "Purchases", "affiliateSalesTotal": "Affiliate sales",
               "groupPayoutsTotal": "Group payouts", "currencyPurchasesTotal": "Robux bought", "premiumStipendsTotal": "Premium stipends",
               "tradeSystemEarningsTotal": "Trade earnings", "tradeSystemCostsTotal": "Trade costs", "pendingRobuxTotal": "Pending Robux",
               "incomingRobuxTotal": "Incoming", "outgoingRobuxTotal": "Outgoing", "engagementPayoutTotal": "Premium payouts",
               "adImpressionPayoutsTotal": "Ad payouts", "groupPremiumPayoutsTotal": "Group premium payouts"}


def total_label(key):
    if key in TOTAL_NAMES:
        return TOTAL_NAMES[key]
    return re.sub(r"(?<!^)(?=[A-Z])", " ", key.removesuffix("Total")).capitalize()


def total_rows(totals):
    """[(label, amount)] for every non-zero '...Total' field Roblox returns."""
    return [(total_label(k), int(v)) for k, v in sorted((totals or {}).items()) if k.endswith("Total") and isinstance(v, (int, float)) and v]


class MoneyTab(QWidget):
    def __init__(self, ctx, show_pending=None):
        super().__init__()
        self.ctx, self.loaded = ctx, False
        self.items = []
        lay = QVBoxLayout(self)
        top = QHBoxLayout()
        self.balance = QLabel("Robux: -")
        self.balance.setProperty("role", "title")
        self.pending = QLabel("Pending: -")
        self.pending.setProperty("role", "title")
        top.addWidget(self.balance)
        top.addSpacing(24)
        top.addWidget(self.pending)
        top.addStretch()
        if show_pending:
            top.addWidget(button("Pending details...", show_pending, "Where your pending Robux comes from, sale by sale"))
        top.addWidget(button("Refresh", self.load))
        lay.addLayout(top)

        row = QHBoxLayout()
        row.addWidget(QLabel("Totals for:"))
        self.period = QComboBox()
        for key, text in PERIODS:
            self.period.addItem(text, key)
        self.period.setCurrentIndex(2)
        self.period.currentIndexChanged.connect(self.load_totals)
        row.addWidget(self.period)
        row.addStretch()
        lay.addLayout(row)
        self.totals = make_table(["What", "Robux"], [260, 120], empty="No money moved in this period.")
        self.totals.setProperty("export_name", "robux-totals")
        self.totals.setMaximumHeight(210)
        lay.addWidget(self.totals)

        row = QHBoxLayout()
        row.addWidget(QLabel("Transactions:"))
        self.kind = QComboBox()
        for key, text in KINDS:
            self.kind.addItem(text, key)
        row.addWidget(self.kind)
        self.only_pending = QCheckBox("Only pending")
        row.addWidget(self.only_pending)
        row.addWidget(button("Load", self.load_transactions, "Your newest transactions of this kind (up to 300)"))
        row.addStretch()
        row.addWidget(button("Export CSV...", lambda: export_csv(self.table, self, name="robux-transactions"), "Save the list below as a spreadsheet file"))
        lay.addLayout(row)
        self.table = make_table(["Date", "Robux", "Type", "Item", "Game", "From / to"], [130, 80, 150, 260, 200, 160], empty="No transactions of this kind.")
        self.table.setProperty("export_name", "robux-transactions")
        lay.addWidget(self.table, 1)
        self.info = hint("Sign in on the Home tab to see your Robux.")
        lay.addWidget(self.info)
        ctx.signed_out.connect(self.clear)

    def clear(self):
        self.loaded = False
        self.balance.setText("Robux: -")
        self.pending.setText("Pending: -")
        for t in (self.totals, self.table):
            fill_table(t, [])
        self.info.setText("Sign in on the Home tab to see your Robux.")

    def ensure_loaded(self):
        if not self.loaded and self.ctx.logged_in:
            self.load()

    def load(self):
        c = self.ctx
        if not c.logged_in:
            return
        self.loaded = True
        c.async_.run(c.client.robux, lambda r: self.balance.setText(f"Robux: {r:,}" if r is not None else "Robux: -"), lambda e: self.balance.setText("Robux: (not available)"))
        c.async_.run(c.client.pending_total, lambda r: self.pending.setText(f"Pending: {r:,}"), lambda e: self.pending.setText("Pending: (not available)"))
        self.load_totals()
        self.load_transactions()

    def load_totals(self):
        c = self.ctx
        if not c.logged_in:
            return
        frame = self.period.currentData()

        def got(d):
            rows = total_rows(d)
            fill_table(self.totals, [[k, v] for k, v in rows], {(i, 1): ("#3ba55d" if v > 0 else "#e5534b") for i, (k, v) in enumerate(rows)})
            if not rows:
                self.info.setText("No money moved in this period.")
        c.async_.run(lambda: c.client.transaction_totals(frame), got, lambda e: self.info.setText(f"Could not load the totals: {e}"))

    def load_transactions(self):
        c = self.ctx
        if not c.logged_in:
            return
        kind, only = self.kind.currentData(), self.only_pending.isChecked()
        self.info.setText("Loading transactions...")

        def work():
            items = c.client.transactions(kind, max_pages=3)
            return [i for i in items if i.get("isPending")] if only else items

        def got(items):
            self.items = items
            rows = pending_rows(items)
            fill_table(self.table, rows)
            self.table.sortByColumn(0, Qt.SortOrder.DescendingOrder)
            robux = sum(r[1] for r in rows)
            self.info.setText(f"{len(rows)} transaction(s), {robux:,} Robux in total." if rows else "No transactions of this kind.")
        c.async_.run(work, got, lambda e: self.info.setText(f"Could not load: {e}"))
