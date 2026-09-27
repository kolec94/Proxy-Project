"""Participant-controlled SDK. The host owns the event loop and consent UI."""
import asyncio
import json
import random
import re
import ssl
from urllib.parse import urlsplit
from .policy import Policy
from .protocol import Wire, CHUNK, TIMEOUT, headers, close, encode, decode
from .storage import DISCLOSURE_VERSION


def endpoint(url):
    parsed = urlsplit(url)
    if (parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password
            or parsed.path not in ("", "/") or parsed.query or parsed.fragment):
        raise ValueError("use an HTTPS gateway origin without a path or credentials")
    # Strict authority to avoid request-line or header injection.
    if not re.fullmatch(r"[A-Za-z0-9.-]+(?::[0-9]{1,5})?", parsed.netloc):
        raise ValueError("invalid gateway authority")
    return parsed.hostname, parsed.port or 443, parsed.netloc


class Client:
    def __init__(self, state, *, cafile=None, status=None):
        self.state = state
        self.context = ssl.create_default_context(cafile=cafile)
        self.context.minimum_version = ssl.TLSVersion.TLSv1_2
        self.context.set_alpn_protocols(["http/1.1"])
        self.status = status or (lambda value: None)
        self.task = None
        self.writer = None
        self.dest = None
        self.dest_task = None
        self.stream = None
        self.lock = asyncio.Lock()

    async def _connect(self):
        host, port, _ = endpoint(self.state.data["gateway"])
        return await asyncio.wait_for(asyncio.open_connection(
            host, port, ssl=self.context, server_hostname=host, limit=32768), TIMEOUT)

    async def _request(self, path, token, payload):
        if not re.fullmatch(r"[A-Za-z0-9_-]{20,128}", token):
            raise ValueError("invalid credential format")
        reader, writer = await self._connect()
        _, _, authority = endpoint(self.state.data["gateway"])
        body = json.dumps(payload).encode()
        try:
            writer.write((f"POST {path} HTTP/1.1\r\nHost: {authority}\r\n"
                          f"Authorization: Bearer {token}\r\nContent-Type: application/json\r\n"
                          f"Content-Length: {len(body)}\r\nConnection: close\r\n\r\n").encode() + body)
            await asyncio.wait_for(writer.drain(), TIMEOUT)
            line, head = await headers(reader)
            n = int(head.get("content-length", "0"))
            if not 0 <= n <= 8192:
                raise ValueError("invalid gateway response")
            value = json.loads(await asyncio.wait_for(reader.readexactly(n), TIMEOUT))
            if line.split()[1] != "200":
                raise ValueError("gateway denied request")
            return value
        finally:
            await close(writer)

    async def enroll(self, gateway, grant, allowed_hosts, daily_cap):
        async with self.lock:
            await self._pause()
            if self.state.data.get("token"):
                raise ValueError("withdraw the existing enrollment first")
            endpoint(gateway)
            policy = Policy(allowed_hosts)
            if type(daily_cap) is not int or not 1_000_000 <= daily_cap <= 1_000_000_000:
                raise ValueError("daily cap must be 1 to 1000 MB")
            self.state.data["gateway"] = gateway
            value = await self._request("/v1/devices/enroll", grant, {
                "consent_version": DISCLOSURE_VERSION, "consent": True})
            self.state.data.update(device_id=value["device_id"], hosts=sorted(policy.hosts),
                                   cap=daily_cap, consented=True, paused=True,
                                   consent_version=DISCLOSURE_VERSION)
            self.state.set_token(value["token"])
            self.status("Enrolled and paused. Select Start to share.")

    async def start(self):
        async with self.lock:
            if self.task and not self.task.done():
                return
            d = self.state.data
            if not d.get("consented") or d.get("consent_version") != DISCLOSURE_VERSION:
                raise ValueError("current disclosure consent required")
            self.state.token()
            self.policy = Policy(d["hosts"])
            d["paused"] = False
            self.state.save()
            self.task = asyncio.create_task(self._run())

    async def _pause(self):
        self.state.data["paused"] = True
        # Close connections even if local storage has become unwritable.
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
            self.task = None
        await self._close_dest()
        await close(self.writer)
        self.writer = None
        self.state.save()
        self.status("Paused. No traffic is being shared.")

    async def pause(self):
        async with self.lock:
            await self._pause()

    async def withdraw(self):
        async with self.lock:
            await self._pause()
            self.state.data["consented"] = False
            self.state.save()
            if self.state.data.get("token"):
                try:
                    await self._request("/v1/devices/revoke", self.state.token(), {})
                except Exception:
                    self.status("Sharing stopped. Gateway revocation pending; retry Withdraw when online.")
                    return False
            self.state.data.pop("token", None)
            self.state.save()
            self.status("Consent withdrawn and credential revoked.")
            return True

    async def _close_dest(self):
        self.stream = None
        if self.dest_task:
            self.dest_task.cancel()
            await asyncio.gather(self.dest_task, return_exceptions=True)
            self.dest_task = None
        await close(self.dest)
        self.dest = None

    async def _responses(self, reader, wire, sid):
        try:
            while self.stream == sid:
                data = await asyncio.wait_for(reader.read(CHUNK), 60)
                if not data:
                    break
                self.state.consume(len(data))
                await wire.send("DATA", id=sid, data=encode(data))
        except (OSError, ValueError, asyncio.TimeoutError):
            pass
        finally:
            if self.stream == sid:
                await wire.send("CLOSE", id=sid)

    async def _session(self):
        reader, self.writer = await self._connect()
        token = self.state.token()
        if not re.fullmatch(r"[A-Za-z0-9_-]{20,128}", token):
            raise ValueError("invalid device token")
        _, _, authority = endpoint(self.state.data["gateway"])
        self.writer.write((f"GET /v1/devices/tunnel HTTP/1.1\r\nHost: {authority}\r\n"
                           f"Authorization: Bearer {token}\r\nConnection: Upgrade\r\n"
                           "Upgrade: proxy-project-v1\r\n\r\n").encode())
        await self.writer.drain()
        line, _ = await headers(reader)
        if line.split()[1] != "101":
            raise ValueError("gateway denied device connection")
        wire = Wire(reader, self.writer)
        await wire.send("HELLO", version=1)
        self.status("Sharing enabled. One connection maximum; daily cap enforced.")
        while not self.state.data["paused"]:
            msg = await asyncio.wait_for(wire.recv(), 90)
            kind, sid = msg["type"], msg.get("id")
            if kind == "PING":
                await wire.send("PONG")
            elif kind == "OPEN":
                if self.stream is not None or not isinstance(sid, str) or len(sid) > 64:
                    raise ValueError("unexpected stream")
                try:
                    self.state.consume(0)
                    ip = await self.policy.resolve(msg.get("host"), msg.get("port"))
                    dest_reader, self.dest = await asyncio.wait_for(
                        asyncio.open_connection(ip, msg["port"], limit=32768), 10)
                    self.dest.transport.set_write_buffer_limits(high=32768, low=8192)
                    self.stream = sid
                    await wire.send("OPEN_OK", id=sid)
                    self.dest_task = asyncio.create_task(self._responses(dest_reader, wire, sid))
                except (OSError, ValueError, asyncio.TimeoutError):
                    await self._close_dest()
                    await wire.send("OPEN_ERROR", id=sid)
            elif kind == "DATA" and sid == self.stream and self.dest:
                data = decode(msg.get("data"))
                self.state.consume(len(data))
                self.dest.write(data)
                await asyncio.wait_for(self.dest.drain(), TIMEOUT)
            elif kind == "EOF" and sid == self.stream and self.dest:
                if self.dest.can_write_eof():
                    self.dest.write_eof()
            elif kind == "CLOSE" and sid == self.stream:
                await self._close_dest()
            else:
                raise ValueError("unexpected protocol message")

    async def _run(self):
        delay = 1
        try:
            while not self.state.data["paused"]:
                try:
                    await self._session()
                except (OSError, ValueError, asyncio.TimeoutError, asyncio.IncompleteReadError,
                        asyncio.LimitOverrunError):
                    self.status("Disconnected. Retrying with verified TLS; Pause stops retries.")
                finally:
                    await self._close_dest()
                    await close(self.writer)
                    self.writer = None
                await asyncio.sleep(delay + random.random())
                delay = min(delay * 2, 60)
        finally:
            await self._close_dest()
            await close(self.writer)
            self.writer = None
