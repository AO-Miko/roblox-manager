"""What the Admin tab does on this PC: it runs tools/ban.sh in a checkout of the update repository, which signs the new list with the release key
and publishes it. That needs the checkout (branch `release`), git, bash, ssh-keygen and the release key; the tab says what is missing.
The hierarchy is checked here first (so the tab can explain) and again by tools/ban.sh (so the rules hold whatever starts it)."""
import json
import os
import shutil
import subprocess
from pathlib import Path

import plat
import rbx

CONFIG = rbx.CONFIG_DIR / "admin.json"
KEY_DEFAULT = Path.home() / ".config" / "roblox-manager-release" / "signing_key"


def saved_repo():
    env = os.environ.get("ROBLOX_MANAGER_ADMIN_REPO")
    if env:
        return Path(env)
    try:
        p = json.loads(CONFIG.read_text()).get("repo")
        return Path(p) if p else None
    except (OSError, ValueError, AttributeError):
        return None


def save_repo(path):
    CONFIG.parent.mkdir(parents=True, exist_ok=True)
    CONFIG.write_text(json.dumps({"repo": str(path)}))


def find_repo():
    """The saved folder, else the repository this program lives in (when it is run from a checkout)."""
    r = saved_repo()
    if r:
        return r
    here = Path(__file__).resolve().parent
    for p in (here, *here.parents):
        if (p / "tools" / "ban.sh").exists() and (p / ".git").exists():
            return p
    return None


def key_path():
    return Path(os.environ.get("ROBLOX_MANAGER_SIGNING_KEY", KEY_DEFAULT))


def problems(repo=None):
    """What is missing for publishing from this PC (empty list: ready)."""
    out = []
    repo = repo or find_repo()
    if repo is None or not (Path(repo) / "tools" / "ban.sh").exists():
        out.append("Choose the folder of your Roblox Manager repository (the one with tools/ban.sh, on the `release` branch).")
    for tool in ("git", "bash", "ssh-keygen"):
        if shutil.which(tool) is None:
            out.append(f"`{tool}` is not installed on this PC.")
    if not key_path().exists():
        out.append(f"The release key is not on this PC ({key_path()}).")
    return out


def run(args, repo=None, timeout=120):
    """Run tools/ban.sh with args; (ok, text)."""
    repo = Path(repo or find_repo())
    try:
        p = subprocess.run(["bash", str(repo / "tools" / "ban.sh"), *args], cwd=repo, capture_output=True, text=True, timeout=timeout,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except (OSError, subprocess.TimeoutExpired) as e:
        return False, str(e)
    text = (p.stdout + p.stderr).strip()
    return p.returncode == 0, text


def ban(user_id, reason, actor_id, push=True, repo=None):
    args = ["ban", str(int(user_id)), reason[:200], "--by", str(int(actor_id))]
    return run(args + (["--push"] if push else []), repo)


def unban(user_id, actor_id, note="", push=True, repo=None):
    args = ["unban", str(int(user_id)), note[:200], "--by", str(int(actor_id))]
    return run(args + (["--push"] if push else []), repo)


def read_bans(repo=None):
    """The ban entries of the checkout: [{'id', 'reason', 'since', 'by', 'rank'}], newest first."""
    try:
        d = json.loads((Path(repo or find_repo()) / "dist" / "bans.json").read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return []
    return sorted(d.get("bans", []), key=lambda b: b.get("since", ""), reverse=True)
