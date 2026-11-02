"""The guard that keeps every test off the real internet (tests/_offline.py). Run: python3 tests/test_offline.py"""
import _offline  # noqa: F401  (this test is about it)
import socket
import sys

import requests

res = []


def check(n, ok, e=""):
    res.append(bool(ok))
    print(("PASS " if ok else "FAIL ") + n + (("  " + str(e)[:200]) if e else ""))


try:
    requests.get("https://users.roblox.com/v1/users/1", timeout=5)
    got = "reached"
except requests.RequestException as e:
    got = str(e)
check("a request to Roblox is refused at once, with the reason", "tests never use the real network" in got, got[:120])
try:
    socket.create_connection(("93.184.216.34", 80), timeout=3)
    refused = False
except OSError as e:
    refused = "tests never use the real network" in str(e)
check("a connection to any other address is refused", refused)
srv = socket.socket()
srv.bind(("127.0.0.1", 0))
srv.listen(1)
try:
    socket.create_connection(("127.0.0.1", srv.getsockname()[1]), timeout=3).close()
    ok = True
except OSError:
    ok = False
srv.close()
check("this computer can still be reached (the tests that run a small local server)", ok)
check("every refused attempt is written down", ("users.roblox.com", None) in _offline.CALLS or any(h == "users.roblox.com" for h, _ in _offline.CALLS), _offline.CALLS[:3])
print(f"{sum(res)}/{len(res)} checks passed")
sys.exit(0 if all(res) else 1)
