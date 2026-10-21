"""The update log: what changed in each version. CHANGELOG.json ships next to the app, so it always describes the installed version."""
import json
from pathlib import Path

FILE = Path(__file__).resolve().parent / "CHANGELOG.json"


def load(path=None):
    """[{'version', 'date', 'changes': [text, ...]}], newest first. A missing or damaged file gives an empty list."""
    try:
        data = json.loads(Path(path or FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    out = []
    for e in data if isinstance(data, list) else []:
        if isinstance(e, dict) and e.get("version"):
            out.append({"version": str(e["version"]), "date": str(e.get("date") or ""),
                        "changes": [str(c) for c in e.get("changes") or [] if str(c).strip()]})
    return out


def html(entries, current):
    """The log as rich text for a label: the installed version is marked, and every change is a bullet."""
    from html import escape
    if not entries:
        return "<p>No update log is available.</p>"
    parts = []
    for e in entries:
        mark = " &nbsp;<span style='color:#35c27a'>&#9679; installed</span>" if e["version"] == current else ""
        parts.append(f"<h3 style='margin-bottom:2px'>Version {escape(e['version'])}"
                     f" <span style='color:#8d96a7;font-weight:normal'>&nbsp;{escape(e['date'])}</span>{mark}</h3><ul style='margin-top:2px'>")
        parts += [f"<li>{escape(c)}</li>" for c in e["changes"]]
        parts.append("</ul>")
    return "".join(parts)
