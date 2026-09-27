"""Atomic participant state; Windows credentials are protected by user DPAPI."""
import base64
import ctypes
import datetime
import json
import os
from pathlib import Path
import tempfile

DISCLOSURE_VERSION = "2026-09-26-v1"


def _dpapi(data, decrypt=False):
    from ctypes import wintypes
    class Blob(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_ubyte))]
    buffer = (ctypes.c_ubyte * len(data)).from_buffer_copy(data)
    source, target = Blob(len(data), buffer), Blob()
    dll = ctypes.WinDLL("crypt32", use_last_error=True)
    fn = dll.CryptUnprotectData if decrypt else dll.CryptProtectData
    fn.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.c_void_p,
                   ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
    fn.restype = wintypes.BOOL
    if not fn(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(target)):
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        return ctypes.string_at(target.pbData, target.cbData)
    finally:
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.LocalFree.argtypes = [ctypes.c_void_p]
        kernel.LocalFree.restype = ctypes.c_void_p
        kernel.LocalFree(target.pbData)


class State:
    def __init__(self, path):
        self.path = Path(path)
        self.data = json.loads(self.path.read_text()) if self.path.exists() else {
            "consented": False, "paused": True, "used": 0, "day": "", "cap": 100_000_000}
        self.data["paused"] = True  # Explicit Start on every app launch.

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        fd, name = tempfile.mkstemp(dir=self.path.parent)
        try:
            with os.fdopen(fd, "w") as f:
                json.dump(self.data, f)
                f.flush()
                os.fsync(f.fileno())
            os.replace(name, self.path)
        finally:
            if os.path.exists(name):
                os.unlink(name)

    def set_token(self, token):
        raw = token.encode()
        self.data["token"] = base64.b64encode(_dpapi(raw) if os.name == "nt" else raw).decode()
        self.data["token_format"] = "dpapi" if os.name == "nt" else "test-plaintext"
        self.save()

    def token(self):
        raw = base64.b64decode(self.data["token"])
        if self.data["token_format"] == "dpapi":
            raw = _dpapi(raw, decrypt=True)
        elif os.name == "nt":
            raise ValueError("Windows credential must use DPAPI")
        return raw.decode()

    def consume(self, count):
        if type(count) is not int or count < 0:
            raise ValueError("invalid byte count")
        today = datetime.datetime.now(datetime.timezone.utc).date().isoformat()
        if today > self.data.get("day", ""):
            self.data.update(day=today, used=0)
        if self.data["paused"] or not self.data["consented"]:
            raise ValueError("participant is not sharing")
        if self.data["used"] + count > self.data["cap"]:
            raise ValueError("daily participant limit reached")
        self.data["used"] += count
        self.save()  # Persist before forwarding; crash cannot reset accounting.
