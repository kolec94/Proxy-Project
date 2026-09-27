import asyncio
import base64
import datetime
import ipaddress
import json
from pathlib import Path
import socket
import ssl
import struct
import subprocess
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

from gateway.server import Gateway
from gateway.store import Store
from proxy_sdk.client import Client, endpoint
from proxy_sdk.policy import Policy, PolicyError, hostname
from proxy_sdk.protocol import Wire, ProtocolError, decode, headers, close
from proxy_sdk.storage import State, DISCLOSURE_VERSION


class PolicyTests(unittest.IsolatedAsyncioTestCase):
    def test_explicit_policy(self):
        policy = Policy(['example.com'])
        self.assertEqual(policy.check('EXAMPLE.COM.', 443), 'example.com')
        for host, port in [('sub.example.com', 443), ('example.com', 80), ('127.0.0.1', 443),
                           ('localhost', 443), ('example.com\r\n', 443), ('example.com', True)]:
            with self.assertRaises(ValueError):
                policy.check(host, port)

    async def test_private_mixed_dns_rejected(self):
        for address in ['127.0.0.1', '10.0.0.1', '169.254.169.254', '100.64.0.1', '0.0.0.0', '192.168.1.1', '224.0.0.1', '240.0.0.1']:
            rows = [(socket.AF_INET, socket.SOCK_STREAM, 6, '', (a, 443)) for a in ['93.184.216.34', address]]
            with patch.object(asyncio.get_running_loop(), 'getaddrinfo', AsyncMock(return_value=rows)):
                with self.assertRaises(PolicyError):
                    await Policy(['example.com']).resolve('example.com', 443)

    async def test_dns_address_is_pinned(self):
        rows = [(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('93.184.216.34', 443))]
        with patch.object(asyncio.get_running_loop(), 'getaddrinfo', AsyncMock(return_value=rows)) as resolver:
            self.assertEqual(await Policy(['example.com']).resolve('example.com', 443), '93.184.216.34')
            resolver.assert_awaited_once()

    def test_no_insecure_gateway(self):
        for url in ['http://example.com', 'https://user:pass@example.com', 'https://example.com/path',
                    'https://example.com?token=x', 'https://example.com\r\nX: y']:
            with self.assertRaises(ValueError):
                endpoint(url)

    def test_data_limits(self):
        for value in ['', '!', base64.b64encode(b'x' * 8193).decode(), 5]:
            with self.assertRaises(ValueError):
                decode(value)

    async def test_oversize_record_rejected_before_body(self):
        reader = asyncio.StreamReader()
        reader.feed_data(struct.pack('!I', 1_000_000))
        class Writer:
            class Transport:
                def set_write_buffer_limits(self, **kw): pass
            transport = Transport()
        with self.assertRaises(ProtocolError):
            await Wire(reader, Writer()).recv()


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name)/'state.json'

    def tearDown(self):
        self.temp.cleanup()

    def test_starts_paused_and_requires_consent(self):
        state = State(self.path)
        with self.assertRaises(ValueError): state.consume(1)
        state.data.update(consented=True, paused=False)
        state.save()
        self.assertTrue(State(self.path).data['paused'])

    def test_quota_survives_restart(self):
        state = State(self.path)
        state.data.update(consented=True, paused=False, cap=10)
        state.consume(8)
        loaded = State(self.path)
        loaded.data['paused'] = False
        with self.assertRaises(ValueError): loaded.consume(3)
        loaded.consume(2)
        self.assertEqual(loaded.data['used'], 10)

    def test_token_roundtrip(self):
        state = State(self.path)
        state.set_token('test-token-that-is-long-enough')
        self.assertEqual(State(self.path).token(), 'test-token-that-is-long-enough')

    def test_invalid_count(self):
        state = State(self.path)
        with self.assertRaises(ValueError): state.consume(-1)

    def test_enrollment_and_customer_quota_persist(self):
        path = str(Path(self.temp.name)/'db.sqlite')
        store = Store(path)
        grant = store.grant()
        dev = store.enroll(grant, DISCLOSURE_VERSION)
        with self.assertRaises(ValueError): store.enroll(grant, DISCLOSURE_VERSION)
        token = store.customer(100)
        store.consume(token, 90)
        store.db.close()
        store = Store(path)
        with self.assertRaises(ValueError): store.consume(token, 11)
        self.assertEqual(store.device(dev['token']), dev['device_id'])
        store.revoke(dev['token'])
        self.assertIsNone(store.device(dev['token']))
        store.db.close()


class IntegrationTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        cls.certdir = tempfile.TemporaryDirectory()
        cls.cert = str(Path(cls.certdir.name)/'cert.pem')
        cls.key = str(Path(cls.certdir.name)/'key.pem')
        subprocess.run(['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes',
                        '-keyout', cls.key, '-out', cls.cert, '-days', '1', '-subj', '/CN=localhost',
                        '-addext', 'subjectAltName=DNS:localhost'], check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    @classmethod
    def tearDownClass(cls):
        cls.certdir.cleanup()

    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(str(Path(self.temp.name)/'gateway.sqlite'))
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(self.cert, self.key)
        self.gateway = Gateway(self.store, Policy(['example.com']))
        self.port = await self.gateway.start(ctx)
        self.state = State(Path(self.temp.name)/'participant.json')
        self.client = Client(self.state, cafile=self.cert)
        self.origin = f'https://localhost:{self.port}'
        self.context = ssl.create_default_context(cafile=self.cert)
        self.customer = self.store.customer(1_000_000)
        self.echo_connections = set()
        self.echo_tasks = set()
        async def echo(reader, writer):
            task = asyncio.current_task()
            self.echo_tasks.add(task)
            self.echo_connections.add(writer)
            try:
                while data := await reader.read(8192):
                    writer.write(data)
                    await writer.drain()
            finally:
                self.echo_connections.discard(writer)
                self.echo_tasks.discard(task)
                await close(writer)
        self.echo = await asyncio.start_server(echo, '127.0.0.1', 0)
        self.echo_port = self.echo.sockets[0].getsockname()[1]

    async def asyncTearDown(self):
        await self.client.pause()
        await self.gateway.stop()
        self.echo.close()
        await self.echo.wait_closed()
        for writer in list(self.echo_connections): writer.close()
        await asyncio.gather(*list(self.echo_tasks), return_exceptions=True)
        self.store.db.close()
        self.temp.cleanup()

    async def enrolled(self):
        await self.client.enroll(self.origin, self.store.grant(), ['example.com'], 1_000_000)

    async def available(self):
        for _ in range(100):
            if any(d.ready for d in self.gateway.devices.values()): return
            await asyncio.sleep(.02)
        self.fail('device did not become available')

    async def connect(self, token=None, target='example.com:443'):
        reader, writer = await asyncio.open_connection('localhost', self.port, ssl=self.context)
        auth = base64.b64encode(('pilot:' + (token or self.customer)).encode()).decode()
        writer.write((f'CONNECT {target} HTTP/1.1\r\nHost: {target}\r\nProxy-Authorization: Basic {auth}\r\n\r\n').encode())
        await writer.drain()
        status, _ = await headers(reader)
        return status, reader, writer

    def local_destination(self):
        # Test-only substitution: production policy has no private-address bypass.
        # Route the already validated host/port to an in-process echo target.
        original = asyncio.open_connection
        async def dial(host, port, **kw):
            if host == '93.184.216.34' and port == 443:
                return await original('127.0.0.1', self.echo_port, **kw)
            return await original(host, port, **kw)
        return patch('proxy_sdk.client.asyncio.open_connection', side_effect=dial)

    async def socks_login(self, token=None, username=b'pilot'):
        if not self.gateway.socks_server:
            self.socks_port = await self.gateway.start_socks(0)
        reader, writer = await asyncio.open_connection('127.0.0.1', self.socks_port)
        self.addAsyncCleanup(close, writer)
        writer.write(b'\x05\x01\x02')
        await writer.drain()
        self.assertEqual(await reader.readexactly(2), b'\x05\x02')
        password = (token or self.customer).encode()
        writer.write(bytes([1, len(username)]) + username + bytes([len(password)]) + password)
        await writer.drain()
        auth = await reader.readexactly(2)
        return auth, reader, writer

    async def socks_request(self, reader, writer, host=b'example.com', port=443, command=1, kind=3):
        writer.write(bytes([5, command, 0, kind, len(host)]) + host + port.to_bytes(2, 'big'))
        await writer.drain()
        return (await asyncio.wait_for(reader.readexactly(10), 5))[1]

    async def test_socks_auth_and_no_anonymous(self):
        for token in ('invalid', self.store.grant()):
            auth, reader, writer = await self.socks_login(token)
            self.assertEqual(auth, b'\x01\x01')
            self.assertEqual(await reader.read(), b'')
        auth, _, _ = await self.socks_login(username=b'wrong')
        self.assertEqual(auth, b'\x01\x01')
        reader, writer = await asyncio.open_connection('127.0.0.1', self.socks_port)
        self.addAsyncCleanup(close, writer)
        writer.write(b'\x05\x01\x00')
        await writer.drain()
        self.assertEqual(await reader.readexactly(2), b'\x05\xff')
        self.assertEqual(await reader.read(), b'')

    async def test_socks_policy_and_unsupported_requests(self):
        for kw, expected in [({'host': b'forbidden.example'}, 2), ({'port': 80}, 2),
                             ({'command': 2}, 7), ({'command': 3}, 7),
                             ({'kind': 1}, 8), ({'kind': 4}, 8), ({'host': b'\xff'}, 2)]:
            auth, reader, writer = await self.socks_login()
            self.assertEqual(auth, b'\x01\x00')
            self.assertEqual(await self.socks_request(reader, writer, **kw), expected)
        self.assertEqual(self.gateway.devices, {})

    async def test_socks_no_device(self):
        _, reader, writer = await self.socks_login()
        self.assertEqual(await self.socks_request(reader, writer), 3)

    async def test_socks_relay_metering_and_pause(self):
        await self.enrolled()
        with patch.object(Policy, 'resolve', AsyncMock(return_value='93.184.216.34')), self.local_destination():
            await self.client.start()
            await self.available()
            _, reader, writer = await self.socks_login()
            self.assertEqual(await self.socks_request(reader, writer), 0)
            payload = b'socks-relay' * 1000
            writer.write(payload)
            await writer.drain()
            self.assertEqual(await asyncio.wait_for(reader.readexactly(len(payload)), 5), payload)
            self.assertEqual(self.state.data['used'], 2 * len(payload))
            self.assertEqual(self.store.db.execute('SELECT used FROM customers').fetchone()[0], 2 * len(payload))
            # HTTP and SOCKS share the same one-session device reservation.
            status, _, http_writer = await self.connect()
            self.assertIn('503', status)
            await close(http_writer)
            await self.client.pause()
            self.assertEqual(await asyncio.wait_for(reader.read(), 5), b'')

    async def test_socks_private_dns_rejected(self):
        await self.enrolled()
        await self.client.start()
        await self.available()
        with patch.object(Policy, 'resolve', AsyncMock(side_effect=PolicyError('private'))):
            _, reader, writer = await self.socks_login()
            self.assertEqual(await self.socks_request(reader, writer), 4)

    async def test_socks_customer_cap_stops_forwarding(self):
        await self.enrolled()
        token = self.store.customer(3)
        with patch.object(Policy, 'resolve', AsyncMock(return_value='93.184.216.34')), self.local_destination():
            await self.client.start()
            await self.available()
            _, reader, writer = await self.socks_login(token)
            self.assertEqual(await self.socks_request(reader, writer), 0)
            writer.write(b'over-quota')
            await writer.drain()
            self.assertEqual(await asyncio.wait_for(reader.read(), 5), b'')
            self.assertEqual(self.state.data['used'], 0)

    async def test_no_sharing_before_start(self):
        await self.enrolled()
        self.assertEqual(self.gateway.devices, {})
        status, _, writer = await self.connect()
        self.assertIn('503', status)
        await close(writer)

    async def test_auth_and_allowlist(self):
        status, _, writer = await self.connect(token='invalid')
        self.assertIn('407', status)
        await close(writer)
        status, _, writer = await self.connect(target='not-allowed.example:443')
        self.assertIn('403', status)
        await close(writer)

    async def test_full_tls_relay_and_metering(self):
        await self.enrolled()
        with patch.object(Policy, 'resolve', AsyncMock(return_value='93.184.216.34')), self.local_destination():
            await self.client.start()
            await self.available()
            status, reader, writer = await self.connect()
            self.assertIn('200', status)
            payload = b'controlled-echo' * 1000
            writer.write(payload)
            await writer.drain()
            self.assertEqual(await asyncio.wait_for(reader.readexactly(len(payload)), 10), payload)
            self.assertEqual(self.state.data['used'], len(payload) * 2)
            used = self.store.db.execute('SELECT used FROM customers').fetchone()[0]
            self.assertEqual(used, len(payload) * 2)
            await self.client.pause()
            self.assertEqual(await asyncio.wait_for(reader.read(), 5), b'')
            await close(writer)

    async def test_private_destination_blocked_end_to_end(self):
        await self.enrolled()
        # DNS mock only; real Policy.resolve must reject this.
        original = asyncio.get_running_loop().getaddrinfo
        async def resolver(host, port, **kw):
            if host == 'example.com':
                return [(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('127.0.0.1', port))]
            return await original(host, port, **kw)
        with patch.object(asyncio.get_running_loop(), 'getaddrinfo', side_effect=resolver):
            await self.client.start()
            await self.available()
            status, _, writer = await self.connect()
            self.assertIn('502', status)
            await close(writer)

    async def test_participant_cap_stops_forwarding(self):
        await self.enrolled()
        self.state.data['cap'] = 4
        with patch.object(Policy, 'resolve', AsyncMock(return_value='93.184.216.34')), self.local_destination():
            await self.client.start()
            await self.available()
            status, reader, writer = await self.connect()
            self.assertIn('200', status)
            writer.write(b'too many bytes')
            await writer.drain()
            self.assertEqual(await asyncio.wait_for(reader.read(), 5), b'')
            self.assertEqual(self.state.data['used'], 0)
            await close(writer)

    async def test_customer_quota_stops_forwarding(self):
        await self.enrolled()
        self.customer = self.store.customer(4)
        with patch.object(Policy, 'resolve', AsyncMock(return_value='93.184.216.34')), self.local_destination():
            await self.client.start()
            await self.available()
            _, reader, writer = await self.connect()
            writer.write(b'over quota')
            await writer.drain()
            self.assertEqual(await asyncio.wait_for(reader.read(), 5), b'')
            self.assertEqual(self.state.data['used'], 0)
            await close(writer)

    async def test_withdraw_revokes_and_prevents_restart(self):
        await self.enrolled()
        token = self.state.token()
        await self.client.start()
        await self.available()
        self.assertTrue(await self.client.withdraw())
        self.assertIsNone(self.store.device(token))
        with self.assertRaises(ValueError): await self.client.start()

    async def test_enrollment_grant_single_use(self):
        grant = self.store.grant()
        await self.client.enroll(self.origin, grant, ['example.com'], 1_000_000)
        another = Client(State(Path(self.temp.name)/'other.json'), cafile=self.cert)
        with self.assertRaises((ValueError, asyncio.IncompleteReadError)):
            await another.enroll(self.origin, grant, ['example.com'], 1_000_000)

    async def test_untrusted_certificate_rejected(self):
        untrusted = Client(State(Path(self.temp.name)/'bad.json'))
        loop = asyncio.get_running_loop()
        old = loop.get_exception_handler()
        def handler(loop, context):
            if isinstance(context.get('exception'), ConnectionResetError):
                return
            loop.default_exception_handler(context)
        loop.set_exception_handler(handler)
        try:
            with self.assertRaises(ssl.SSLCertVerificationError):
                await untrusted.enroll(self.origin, self.store.grant(), ['example.com'], 1_000_000)
            await asyncio.sleep(.02)
        finally:
            loop.set_exception_handler(old)

    async def test_second_customer_cannot_take_busy_device(self):
        await self.enrolled()
        with patch.object(Policy, 'resolve', AsyncMock(return_value='93.184.216.34')), self.local_destination():
            await self.client.start()
            await self.available()
            status, _, first = await self.connect()
            self.assertIn('200', status)
            status, _, second = await self.connect()
            self.assertIn('503', status)
            await close(second)
            await close(first)

    async def test_concurrent_pause_and_start_finish_paused(self):
        await self.enrolled()
        await asyncio.gather(self.client.start(), self.client.pause())
        self.assertTrue(self.state.data['paused'])
        self.assertIsNone(self.client.task)

    async def test_device_token_cannot_authenticate_customer(self):
        await self.enrolled()
        status, _, writer = await self.connect(token=self.state.token())
        self.assertIn('407', status)
        await close(writer)

    async def test_offline_withdraw_keeps_consent_off(self):
        await self.enrolled()
        with patch.object(self.client, '_request', AsyncMock(side_effect=OSError('offline'))):
            self.assertFalse(await self.client.withdraw())
        self.assertFalse(self.state.data['consented'])
        self.assertTrue(self.state.data['paused'])
        with self.assertRaises(ValueError):
            await self.client.start()
