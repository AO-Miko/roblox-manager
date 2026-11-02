"""Imported first by every test: no test talks to the real internet (and so never to the real Roblox).

A test that sends a request to Roblox does not test the app, it tests Roblox, and it can make Roblox refuse the person running it. Any connection to an
address that is not this computer fails at once with an error that says so; connections to this computer (the tests that run a small local server)
and to Unix sockets still work. Tests that need an answer from Roblox replace the client's get/post with a fake one, as they always did.
"""
import ipaddress
import socket

_real_connect = socket.socket.connect
_real_connect_ex = socket.socket.connect_ex
_real_getaddrinfo = socket.getaddrinfo
CALLS = []                 # (host, port) of every refused connection, for a test that wants to look
ALLOW = set()              # host names a test has explicitly opened (never a Roblox host); the addresses they resolve to are allowed too
_allowed_ips = set()


def _local(host):
    if host in ("localhost", ""):
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _refuse(address):
    host = address[0] if isinstance(address, tuple) else None
    if host is None or _local(host) or host in _allowed_ips:       # (a Unix socket, this computer, or a host a test opened: allowed)
        return False
    CALLS.append((host, address[1] if len(address) > 1 else None))
    return True


def _connect(self, address):
    if _refuse(address):
        raise OSError(f"tests never use the real network (tried {address[0]})")
    return _real_connect(self, address)


def _connect_ex(self, address):
    if _refuse(address):
        return 111                                          # (connection refused)
    return _real_connect_ex(self, address)


def _getaddrinfo(host, *args, **kwargs):
    if isinstance(host, str) and host in ALLOW:
        found = _real_getaddrinfo(host, *args, **kwargs)
        _allowed_ips.update(item[4][0] for item in found)
        return found
    if isinstance(host, str) and not _local(host):
        CALLS.append((host, None))
        raise socket.gaierror(f"tests never use the real network (tried to look up {host})")
    return _real_getaddrinfo(host, *args, **kwargs)


socket.socket.connect = _connect
socket.socket.connect_ex = _connect_ex
socket.getaddrinfo = _getaddrinfo


def _report():
    if CALLS:
        print("NOTE this test tried to reach the real network (refused):", sorted({h for h, _ in CALLS}))


import atexit
atexit.register(_report)
