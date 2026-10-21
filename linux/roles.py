"""Who may administer the app: a signed list of Roblox user ids with a role, published next to the ban list (dist/roles.json + dist/roles.json.sig).

    {"serial": 3, "roles": {"239345228": "owner", "123456": "admin"}}

Two roles, one above the other: owner (2) > admin (1); everybody else has no role (0). The Admin tab only appears for an account that has a role.
The hierarchy: nobody can ban or unban themselves, and nobody can ban someone of the same or a higher role (an owner can ban an admin; an admin
cannot ban an admin or the owner). An unban needs at least the role of whoever placed the ban.

Like the ban list, the file is only believed with a valid signature of the release key, a newer serial replaces an older one, the last good list
is kept on disk, and an unreachable list changes nothing.
"""
import base64
import json

import bans
import plat
import sshsig

NAMESPACE = "roblox-manager-roles"
RANKS = {"admin": 1, "owner": 2}
NAMES = {v: k for k, v in RANKS.items()}


def _cache_file():
    return plat.state_dir() / "roles.cache.json"


def parse(data, sig_text, trusted=None):
    """(serial, {user id: role}) if `data` is a role list signed by the trusted key, else None. Unknown roles are dropped."""
    if sshsig.verify(data, sig_text, trusted if trusted is not None else bans.TRUSTED, NAMESPACE) is None:
        return None
    try:
        d = json.loads(data.decode("utf-8"))
        roles = {int(k): str(v).lower() for k, v in d.get("roles", {}).items()}
        return int(d["serial"]), {k: v for k, v in roles.items() if v in RANKS}
    except (ValueError, KeyError, TypeError, AttributeError):
        return None


def load():
    """The last good list from disk, checked again every time: (serial, {user id: role}); (0, {}) if there is none."""
    try:
        c = json.loads(_cache_file().read_text(encoding="utf-8"))
        got = parse(base64.b64decode(c["data"]), c["sig"])
    except (OSError, ValueError, KeyError, TypeError):
        return 0, {}
    return got or (0, {})


def role_of(user_id):
    """'owner', 'admin' or None."""
    try:
        return load()[1].get(int(user_id))
    except (ValueError, TypeError):
        return None


def rank_of(user_id):
    return RANKS.get(role_of(user_id), 0)


def refresh(get=None, base=None):
    """Download the list; True if it changed, False if not, None if it could not be fetched or was refused. Never raises."""
    get = get or bans._http_get
    base = base or bans.BASE_URL
    try:
        data = get(base + "roles.json")
        sig = get(base + "roles.json.sig", limit=20_000).decode("utf-8", "replace")
    except Exception:                                    # noqa: BLE001 - any network problem just means "could not fetch"
        return None
    got = parse(data, sig)
    if got is None:
        return None
    have_serial, have = load()
    if got[0] < have_serial or (got[0] == have_serial and got[1] == have):
        return False
    try:
        f = _cache_file()
        f.parent.mkdir(parents=True, exist_ok=True)
        tmp = f.with_suffix(".tmp")
        tmp.write_text(json.dumps({"data": base64.b64encode(data).decode(), "sig": sig}), encoding="utf-8")
        tmp.replace(f)
    except OSError:
        return None
    return True


# ---- the hierarchy (the same rules are in tools/ban.sh, which does the publishing)
def may_ban(actor_rank, actor_id, target_id, target_rank):
    """(True, '') or (False, why)."""
    if actor_rank < 1:
        return False, "You are not an admin."
    if int(actor_id) == int(target_id):
        return False, "You cannot ban yourself."
    if target_rank >= actor_rank:
        return False, f"You cannot ban {'the owner' if target_rank >= 2 else 'an admin'}: they have the same role as you or a higher one."
    return True, ""


def may_unban(actor_rank, ban_rank):
    """A ban placed by an owner can only be lifted by an owner; one placed by an admin by an admin or an owner."""
    if actor_rank < 1:
        return False, "You are not an admin."
    if actor_rank < ban_rank:
        return False, "This ban was placed by someone with a higher role than yours."
    return True, ""
