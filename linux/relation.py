"""What you and another person have in common, from Roblox's profile insights: since when you are friends, the friends you share, whether you played together."""
from datetime import datetime, timezone

from PySide6.QtWidgets import QDialog, QHBoxLayout, QPlainTextEdit, QVBoxLayout

import rbx
from ui_common import button


def years_text(ms, now=None):
    """'3 years, 2 months' (or 'under a month') for how long ago a time was."""
    now = datetime.now(timezone.utc) if now is None else now
    then = datetime.fromtimestamp(ms / 1000, tz=timezone.utc)
    months = max(0, (now.year - then.year) * 12 + now.month - then.month - (1 if now.day < then.day else 0))
    y, m = divmod(months, 12)
    parts = ([f"{y} year{'s' if y != 1 else ''}"] if y else []) + ([f"{m} month{'s' if m != 1 else ''}"] if m else [])
    return ", ".join(parts) or "under a month"


def describe(info, name, now=None):
    """The text of the dialog for one person: friends since, played together, the shared friends (names and usernames)."""
    lines = []
    if info and info.get("friends_since_ms"):
        when = datetime.fromtimestamp(info["friends_since_ms"] / 1000, tz=timezone.utc)
        lines.append(f"Friends since {when:%Y-%m-%d} ({years_text(info['friends_since_ms'], now)}).")
    elif info is not None:
        lines.append("Roblox does not say since when you are friends (you may not be).")
    if info and info.get("played_together"):
        lines.append("You have played together.")
    mutual = (info or {}).get("mutual") or []
    if mutual:
        lines.append("")
        lines.append(f"{len(mutual)} mutual friend{'s' if len(mutual) != 1 else ''}:")
        for m in sorted(mutual, key=lambda m: (m["displayName"] or m["username"]).lower()):
            lines.append(f"  {m['displayName'] or m['username']}" + (f"  (@{m['username']})" if m["username"] and m["displayName"] != m["username"] else ""))
    elif info is not None:
        lines.append("No mutual friends.")
    if info is None:
        lines = [f"Roblox gave nothing about you and {name}."]
    return "\n".join(lines)


def show(ctx, user_id, name):
    """Ask Roblox (one request) and show the answer for one person."""
    if ctx.need_login():
        return
    c = ctx
    c.status(f"Looking up what you share with {name}...")

    def done(res):
        c.status("")
        dlg = QDialog(c.window)
        dlg.setWindowTitle(f"You and {name}")
        dlg.resize(460, 420)
        lay = QVBoxLayout(dlg)
        box = QPlainTextEdit()
        box.setReadOnly(True)
        box.setPlainText(describe(res.get(int(user_id)), name))           # (plain text: a name from Roblox is never read as HTML)
        lay.addWidget(box)
        row = QHBoxLayout()
        row.addStretch()
        row.addWidget(button("Close", dlg.accept))
        lay.addLayout(row)
        dlg.exec()

    c.async_.run(lambda: c.client.profile_insights([int(user_id)]), done)
