"""Finding and clearing what the app writes to this PC: logs, activity records, saved pictures and names.

Sign-in data (the encrypted cookies, the list of accounts) and settings are never touched here.
"""

import rbx

CATEGORIES = {
    "logs": {
        "title": "Logs",
        "what": "What the app did and how Roblox answered: manager.log and requests.log, with their older copies.",
    },
    "records": {
        "title": "Activity records",
        "what": "Who you unfriended, unfollowed, unblocked and blocked, and which groups you left, from this app. "
                "(The 'blocked from this app' list is what the Blocked tab shows when Roblox will not give your list.)",
    },
    "caches": {
        "title": "Saved pictures and names",
        "what": "Avatars and user names kept so Roblox is not asked again. They are downloaded again when needed.",
    },
}

RECORD_FILES = ["removed-friends.txt", "left-groups.txt", "unfollowed.txt", "unblocked.txt", "blocked-by-app.json"]
CACHE_FILES = ["names.json", "bad-transaction-types.json"]


def files(category):
    """The files of a category that exist right now."""
    st = rbx.STATE_DIR
    out = []
    if category == "logs":
        for base in ("manager.log", "requests.log"):
            out += [p for p in sorted(st.glob(base + "*")) if p.is_file()]
    elif category == "records":
        out = [st / n for n in RECORD_FILES if (st / n).is_file()]
    elif category == "caches":
        out = [st / n for n in CACHE_FILES if (st / n).is_file()]
        if rbx.AVATAR_DIR.is_dir():
            out += [p for p in rbx.AVATAR_DIR.glob("*") if p.is_file()]
    return [p for p in out if size([p]) > 0]                  # an empty file has nothing to clear


def size(paths):
    total = 0
    for p in paths:
        try:
            total += p.stat().st_size
        except OSError:
            pass
    return total


def human(n):
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024


def summary():
    """{category: (number of files, bytes)}."""
    return {k: (len(f := files(k)), size(f)) for k in CATEGORIES}


def clear(category):
    """Clear a category. The log files that are open right now are emptied (not deleted, so logging simply carries on); older copies and
    everything else are deleted. Returns (files cleared, bytes freed, problems)."""
    n, freed, problems = 0, 0, []
    current = {rbx.STATE_DIR / "manager.log", rbx.STATE_DIR / "requests.log"}
    for p in files(category):
        try:
            s = p.stat().st_size
            if p in current:
                with open(p, "w"):
                    pass                                    # empty it in place
            else:
                p.unlink()
            n += 1
            freed += s
        except OSError as e:
            problems.append(f"{p.name}: {e.strerror or e}")
    if category == "caches":
        rbx.names.data.clear()
        rbx.names.dirty = False
        try:
            rbx.AVATAR_DIR.rmdir()
        except OSError:
            pass
    return n, freed, problems


def describe(category, limit=8):
    """A readable list of what would be cleared, for the confirmation."""
    f = files(category)
    lines = [f"  {p.name}  ({human(size([p]))})" for p in f[:limit]]
    if len(f) > limit:
        lines.append(f"  ... and {len(f) - limit} more ({human(size(f[limit:]))})")
    return "\n".join(lines) if lines else "  (nothing to clear)"
