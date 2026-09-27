"""TLS gateway with optional loopback SOCKS5 listener for an allowlisted pilot; no public admin API."""
import argparse
import asyncio
import base64
import contextlib
import json
from pathlib import Path
import secrets
import ssl
import time
from .store import Store
from proxy_sdk.policy import Policy
from proxy_sdk.protocol import Wire, headers, close, CHUNK, TIMEOUT, encode, decode
from proxy_sdk.storage import DISCLOSURE_VERSION


class Device:
    def __init__(self, ident, wire):
        self.id, self.wire = ident, wire
        self.busy = False
        self.session = None
        self.ready = False


class Session:
    def __init__(self, writer, token):
        self.id = secrets.token_hex(16)
        self.writer, self.token = writer, token
        self.opened = asyncio.get_running_loop().create_future()
        self.done = asyncio.Event()
        self.accepted = asyncio.Event()


class Gateway:
    def __init__(self, store, policy):
        self.store, self.policy = store, policy
        self.devices = {}
        self.server = None
        self.socks_server = None
        self.connections = set()
        self.tasks = set()

    async def start(self, context, host="127.0.0.1", port=0):
        self.server = await asyncio.start_server(self.handle, host, port, ssl=context,
                                                ssl_handshake_timeout=5, limit=32768)
        return self.server.sockets[0].getsockname()[1]

    async def start_socks(self, port=1080):
        # RFC 1929 credentials are plaintext: expose only through SSH forwarding.
        self.socks_server = await asyncio.start_server(
            self.handle_socks, "127.0.0.1", port, limit=32768)
        return self.socks_server.sockets[0].getsockname()[1]

    async def stop(self):
        for server in (self.server, self.socks_server):
            if server:
                server.close()
                await server.wait_closed()
        for writer in list(self.connections):
            writer.close()
        for task in list(self.tasks):
            task.cancel()
        await asyncio.gather(*list(self.tasks), return_exceptions=True)

    async def response(self, writer, code, body=None):
        data = json.dumps(body or {}).encode()
        writer.write((f"HTTP/1.1 {code}\r\nContent-Type: application/json\r\n"
                      f"Content-Length: {len(data)}\r\nConnection: close\r\n\r\n").encode() + data)
        await asyncio.wait_for(writer.drain(), TIMEOUT)

    async def handle(self, reader, writer):
        task = asyncio.current_task()
        if len(self.connections) >= 64:
            await close(writer)
            return
        self.connections.add(writer)
        self.tasks.add(task)
        try:
            line, head = await headers(reader)
            method, target, version = line.split()
            if version != "HTTP/1.1" or "transfer-encoding" in head:
                raise ValueError("unsupported HTTP framing")
            if method == "CONNECT":
                await self.proxy(reader, writer, target, head)
            elif method == "POST" and target in ("/v1/devices/enroll", "/v1/devices/revoke"):
                token = head.get("authorization", "").removeprefix("Bearer ")
                n = int(head.get("content-length", "0"))
                if not 0 < n <= 2048:
                    raise ValueError("invalid body size")
                body = json.loads(await asyncio.wait_for(reader.readexactly(n), TIMEOUT))
                if target.endswith("enroll"):
                    if body.get("consent") is not True or body.get("consent_version") != DISCLOSURE_VERSION:
                        raise ValueError("consent required")
                    result = self.store.enroll(token, DISCLOSURE_VERSION)
                else:
                    ident = self.store.revoke(token)
                    if not ident:
                        raise ValueError("invalid device")
                    old = self.devices.get(ident)
                    if old:
                        old.wire.writer.close()
                    result = {"revoked": True}
                await self.response(writer, "200 OK", result)
            elif method == "GET" and target == "/v1/devices/tunnel":
                await self.tunnel(reader, writer, head)
            else:
                await self.response(writer, "404 Not Found")
        except (ValueError, KeyError, TypeError, OSError, asyncio.TimeoutError,
                asyncio.IncompleteReadError, asyncio.LimitOverrunError):
            # No exceptions, credentials or destination payloads go into logs.
            pass
        finally:
            self.connections.discard(writer)
            self.tasks.discard(task)
            await close(writer)

    async def tunnel(self, reader, writer, head):
        ident = self.store.device(head.get("authorization", "").removeprefix("Bearer "))
        if not ident or head.get("upgrade") != "proxy-project-v1" or head.get("connection", "").lower() != "upgrade":
            await self.response(writer, "401 Unauthorized")
            return
        if ident in self.devices:
            await self.response(writer, "409 Conflict")
            return
        device = Device(ident, Wire(reader, writer))
        self.devices[ident] = device
        heartbeat = None
        try:
            writer.write(b"HTTP/1.1 101 Switching Protocols\r\nConnection: Upgrade\r\nUpgrade: proxy-project-v1\r\n\r\n")
            await writer.drain()
            hello = await asyncio.wait_for(device.wire.recv(), 10)
            if hello != {"type": "HELLO", "version": 1}:
                raise ValueError("unsupported protocol")
            device.ready = True
            async def ping():
                while True:
                    await asyncio.sleep(20)
                    await device.wire.send("PING")
            heartbeat = asyncio.create_task(ping())
            while True:
                msg = await asyncio.wait_for(device.wire.recv(), 75)
                kind = msg["type"]
                if kind == "PONG":
                    continue
                session = device.session
                if not session or msg.get("id") != session.id:
                    raise ValueError("unexpected stream")
                if kind in ("OPEN_OK", "OPEN_ERROR") and not session.opened.done():
                    session.opened.set_result(kind == "OPEN_OK")
                elif kind == "DATA" and session.opened.done() and session.opened.result():
                    # Do not write payload before the customer success response.
                    await asyncio.wait_for(session.accepted.wait(), TIMEOUT)
                    data = decode(msg.get("data"))
                    self.store.consume(session.token, len(data))
                    session.writer.write(data)
                    await asyncio.wait_for(session.writer.drain(), TIMEOUT)
                elif kind == "CLOSE":
                    session.done.set()
                    # Exit closes the device tunnel; reconnect creates a clean
                    # generation so late frames cannot affect a future stream.
                    break
                else:
                    raise ValueError("unexpected frame")
        finally:
            self.devices.pop(ident, None)
            if device.session:
                if not device.session.opened.done():
                    device.session.opened.set_result(False)
                device.session.done.set()
            if heartbeat:
                heartbeat.cancel()
                await asyncio.gather(heartbeat, return_exceptions=True)

    async def socks_reply(self, writer, code):
        # Relay protocol does not expose the endpoint's bound socket address.
        writer.write(bytes([5, code, 0, 1]) + b"\x00" * 6)
        await asyncio.wait_for(writer.drain(), TIMEOUT)

    async def handle_socks(self, reader, writer):
        task = asyncio.current_task()
        if len(self.connections) >= 64:
            await close(writer)
            return
        self.connections.add(writer)
        self.tasks.add(task)
        try:
            # Total negotiation deadline prevents slow clients occupying slots.
            async with asyncio.timeout(TIMEOUT):
                version, count = await reader.readexactly(2)
                if version != 5 or count == 0:
                    return
                methods = await reader.readexactly(count)
                writer.write(b"\x05\x02" if 2 in methods else b"\x05\xff")
                await writer.drain()
                if 2 not in methods:
                    return
                version, length = await reader.readexactly(2)
                if version != 1 or length == 0:
                    writer.write(b"\x01\x01")
                    await writer.drain()
                    return
                username = await reader.readexactly(length)
                length = (await reader.readexactly(1))[0]
                password = await reader.readexactly(length)
                try:
                    token = password.decode("ascii")
                except UnicodeDecodeError:
                    token = ""
                valid = username == b"pilot" and length > 0 and self.store.valid_customer(token)
                writer.write(b"\x01\x00" if valid else b"\x01\x01")
                await writer.drain()
                if not valid:
                    return
                version, command, reserved, kind = await reader.readexactly(4)
                if version != 5 or reserved != 0:
                    await self.socks_reply(writer, 1)
                    return
                if command != 1:  # No BIND or UDP ASSOCIATE.
                    await self.socks_reply(writer, 7)
                    return
                if kind != 3:  # Domain-only to preserve exact hostname policy.
                    await self.socks_reply(writer, 8)
                    return
                length = (await reader.readexactly(1))[0]
                raw_host = await reader.readexactly(length)
                port = int.from_bytes(await reader.readexactly(2), "big")
                try:
                    host = self.policy.check(raw_host.decode("ascii"), port)
                except ValueError:
                    await self.socks_reply(writer, 2)
                    return
            await self.relay(reader, writer, token, host, port, socks=True)
        except (ValueError, OSError, asyncio.TimeoutError, asyncio.IncompleteReadError):
            pass
        finally:
            self.connections.discard(writer)
            self.tasks.discard(task)
            await close(writer)

    async def proxy(self, reader, writer, target, head):
        raw = head.get("proxy-authorization", "")
        try:
            if not raw.startswith("Basic "):
                raise ValueError("missing proxy auth")
            _, token = base64.b64decode(raw[6:], validate=True).decode().split(":", 1)
            if not self.store.valid_customer(token):
                raise ValueError("invalid customer")
        except ValueError:
            await self.response(writer, "407 Proxy Authentication Required")
            return
        if "content-length" in head:
            await self.response(writer, "400 Bad Request")
            return
        try:
            host, port_s = target.rsplit(":", 1)
            port = int(port_s)
            host = self.policy.check(host, port)
        except ValueError:
            await self.response(writer, "403 Forbidden")
            return
        await self.relay(reader, writer, token, host, port)

    async def relay(self, reader, writer, token, host, port, socks=False):
        async def reply(code):
            if socks:
                await self.socks_reply(writer, {200: 0, 503: 3, 502: 4}[code])
            elif code == 200:
                writer.write(b"HTTP/1.1 200 Connection Established\r\n\r\n")
                await asyncio.wait_for(writer.drain(), TIMEOUT)
            else:
                await self.response(writer, {503: "503 Service Unavailable", 502: "502 Bad Gateway"}[code])
        device = next((d for d in self.devices.values() if d.ready and not d.busy), None)
        if device is None:
            await reply(503)
            return
        device.busy = True
        session = device.session = Session(writer, token)
        send_task = done_task = None
        try:
            await device.wire.send("OPEN", id=session.id, host=host, port=port)
            if not await asyncio.wait_for(session.opened, 15):
                await reply(502)
                return
            await reply(200)
            session.accepted.set()
            async def forward():
                while not session.done.is_set():
                    data = await asyncio.wait_for(reader.read(CHUNK), 60)
                    if not data:
                        await device.wire.send("EOF", id=session.id)
                        return
                    self.store.consume(token, len(data))
                    await device.wire.send("DATA", id=session.id, data=encode(data))
            send_task = asyncio.create_task(forward())
            done_task = asyncio.create_task(session.done.wait())
            done, _ = await asyncio.wait([send_task, done_task], timeout=300,
                                         return_when=asyncio.FIRST_COMPLETED)
            if send_task in done:
                await send_task
                await asyncio.wait_for(session.done.wait(), 60)
        finally:
            for task in (send_task, done_task):
                if task:
                    task.cancel()
            await asyncio.gather(*[t for t in (send_task, done_task) if t], return_exceptions=True)
            device.wire.writer.close()  # One stream per tunnel generation.
            session.done.set()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", required=True)
    parser.add_argument("--issue-grant", action="store_true")
    parser.add_argument("--issue-customer", type=int, metavar="QUOTA_BYTES")
    parser.add_argument("--cert")
    parser.add_argument("--key")
    parser.add_argument("--bind", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8443)
    parser.add_argument("--allow-host", action="append")
    parser.add_argument("--socks-port", type=int, help="Enable loopback-only SOCKS5 on this port; use SSH forwarding")
    args = parser.parse_args()
    if args.socks_port is not None and not 1 <= args.socks_port <= 65535:
        parser.error("--socks-port must be between 1 and 65535")
    Path(args.db).parent.mkdir(parents=True, exist_ok=True)
    store = Store(args.db)
    if args.issue_grant:
        print(store.grant())
        return
    if args.issue_customer is not None:
        print(store.customer(args.issue_customer))
        return
    if not args.cert or not args.key or not args.allow_host:
        parser.error("serving requires --cert, --key and at least one --allow-host")
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    ctx.set_alpn_protocols(["http/1.1"])
    ctx.load_cert_chain(args.cert, args.key)
    gateway = Gateway(store, Policy(args.allow_host))
    async def run():
        await gateway.start(ctx, args.bind, args.port)
        if args.socks_port is not None:
            await gateway.start_socks(args.socks_port)
            print(f"SOCKS5 listening on 127.0.0.1:{args.socks_port}; SSH forwarding required for remote clients")
        print(f"Pilot gateway listening on {args.bind}:{args.port}; max 64 connections")
        try:
            await asyncio.Event().wait()
        finally:
            await gateway.stop()
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
