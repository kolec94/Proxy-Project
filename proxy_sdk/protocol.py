"""Version 1: HTTPS Upgrade then bounded JSON records, one stream per device."""
import asyncio
import base64
import json
import struct

MAX_FRAME = 24576
CHUNK = 8192
TIMEOUT = 15


class ProtocolError(ValueError):
    pass


class Wire:
    def __init__(self, reader, writer):
        self.reader, self.writer = reader, writer
        self.lock = asyncio.Lock()
        writer.transport.set_write_buffer_limits(high=32768, low=8192)

    async def send(self, kind, **fields):
        raw = json.dumps(dict(type=kind, **fields), separators=(",", ":")).encode()
        if len(raw) > MAX_FRAME:
            raise ProtocolError("frame too large")
        async with self.lock:
            self.writer.write(struct.pack("!I", len(raw)) + raw)
            await asyncio.wait_for(self.writer.drain(), TIMEOUT)

    async def recv(self):
        size = struct.unpack("!I", await self.reader.readexactly(4))[0]
        if not 0 < size <= MAX_FRAME:
            raise ProtocolError("invalid frame size")
        value = json.loads(await self.reader.readexactly(size))
        if not isinstance(value, dict) or not isinstance(value.get("type"), str):
            raise ProtocolError("invalid message")
        return value


def encode(data):
    if len(data) > CHUNK:
        raise ProtocolError("chunk too large")
    return base64.b64encode(data).decode("ascii")


def decode(text):
    if not isinstance(text, str) or len(text) > 4 * ((CHUNK + 2) // 3):
        raise ProtocolError("invalid data")
    data = base64.b64decode(text, validate=True)
    if not data or len(data) > CHUNK:
        raise ProtocolError("invalid data length")
    return data


async def close(writer):
    if writer:
        writer.close()
        try:
            await asyncio.wait_for(writer.wait_closed(), 2)
        except (OSError, asyncio.TimeoutError):
            pass
        except asyncio.CancelledError:
            # A previous cancelled close can cancel StreamWriter's shared
            # close waiter. Preserve actual caller cancellation, but allow
            # subsequent cleanup of the already-closed socket to finish.
            if asyncio.current_task().cancelling():
                raise


async def headers(reader):
    raw = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), TIMEOUT)
    if len(raw) > 16384:
        raise ProtocolError("headers too large")
    lines = raw.decode("ascii").split("\r\n")
    result = {}
    for line in lines[1:]:
        if not line:
            continue
        key, sep, value = line.partition(":")
        key = key.lower()
        if not sep or key in result:
            raise ProtocolError("invalid or duplicate header")
        result[key] = value.strip()
    return lines[0], result
