# SDK and Windows participant client

Version 0.1.0 implements a restricted, consent-based pilot: a shared Python networking library, a visible Windows application, and a matching authenticated TLS gateway. It is not yet a general-purpose proxy distribution SDK for third-party apps.

## What works

- Explicit enrollment consent; one-time enrollment grants expire after 24 hours.
- Unique device credentials, protected with user-scoped DPAPI on Windows.
- Verified gateway TLS; no certificate-verification bypass in the client.
- Persistent participant daily caps and persistent gateway customer quotas.
- Exact participant and operator hostname allowlists; destination TCP port 443 only.
- Endpoint-side DNS validation and a connection to the validated numeric IPv4 address.
- Rejection of private, loopback, link-local, shared address space and other nonglobal DNS answers.
- One active CONNECT session per device; no direct VPS fallback.
- Pause, consent withdrawal, stop on window close, and paused state on every launch.
- A local TLS integration harness covering forwarding, caps, credentials and revocation.

## Platform support

| Platform | Current implementation | Next work |
| --- | --- | --- |
| Windows x64 | Tkinter participant UI, DPAPI credential storage, per-user installer build | Real-machine installation and network smoke test; code signing |
| Linux | Shared SDK and gateway; automated integration tests | No participant distribution package; token storage is test-only plaintext |
| Android phones | Not implemented | Native consent UI, secure storage, lifecycle and foreground-execution integration |
| Android TV | Not implemented | Android core plus remote-control UI, TV lifecycle and distribution review |

Each device family needs its own package. Android phones and TV can share much of an Android module, but need different interfaces and lifecycle testing. The protocol can remain common across Windows and Android. This Python prototype is not directly embeddable as an Android AAR; an Android implementation would likely port the small networking core or replace it with a shared native library.

## Install the Windows participant

1. Open the repository's **Actions** tab and select a successful **Test SDK and build Windows participant** run for the current commit.
2. Download the `ProxyProject-Windows-0.1.0` artifact. It contains `ProxyProject-Setup-0.1.0.exe` and its SHA-256 checksum.
3. Verify the downloaded file using `Get-FileHash` in PowerShell and compare it with `SHA256SUMS.txt`.
4. Run the per-user installer and launch **Proxy Project** from the Start menu.
5. Enter the operator's HTTPS gateway origin, one-time enrollment code, exact permitted domains, and daily cap.
6. Read the disclosure, select consent, and choose **Enroll paused**. Choose **Start** separately when ready.

The installer is unsigned. Do not disable antivirus or bypass a security block; signed distribution is a separate release requirement. CI packaging does not substitute for testing installation on an actual Windows desktop. No service, scheduled task, startup entry, remote shell, or unattended sharing is installed.

**Pause** closes active connections. **Withdraw consent** pauses immediately and asks the gateway to revoke the token. If offline, local consent remains withdrawn and revocation stays pending; retry Withdraw after reconnecting. The app will not resume while consent is withdrawn.

To change the enrolled gateway, domains, or cap, withdraw and re-enroll with a new grant. Editing fields alone does not change active limits. A re-enrollment does not clear the same-day byte count. Uninstall via Windows Apps settings; local usage and enrollment state is intentionally retained. Withdraw first when possible. The uninstaller does not need or expose gateway credentials.

## Run from source

Python 3.12 or newer is required. Runtime code uses the Python standard library. Windows Python installations should include Tcl/Tk.

From the repository root:

```bash
python -m pip install -e .
python -m unittest discover -s tests -v
python apps/windows/main.py
```

Tests require the `openssl` executable to generate an ephemeral test certificate. They use a controlled local echo server and explicit test-only DNS/dial substitutions; no public proxy traffic is generated. There is no runtime private-destination override.

Do not ship the Linux participant state to real users: its non-Windows credential encoding is only for development. Windows builds require DPAPI-protected tokens.

## Run the pilot gateway

Use a VPS with a trusted certificate whose hostname matches the client origin. Provision and renew the certificate separately. The executable does not obtain certificates automatically. Restrict private key and database permissions; run under an unprivileged service account. Choose port 8443 initially to avoid root requirements.

```bash
python -m gateway.server --db /var/lib/proxy-project/gateway.sqlite \
  --cert /etc/proxy-project/fullchain.pem \
  --key /etc/proxy-project/privkey.pem \
  --bind 0.0.0.0 --port 8443 \
  --allow-host example.com
```

Replace `example.com` with the exact approved pilot destination. Add `--allow-host` once per domain. Both the gateway and participant must permit that hostname. The client uses `https://your-gateway-hostname:8443` as its origin.

To issue a one-time grant or a customer credential, run the following **locally on the gateway host**, with access to the same database:

```bash
python -m gateway.server --db /var/lib/proxy-project/gateway.sqlite --issue-grant
python -m gateway.server --db /var/lib/proxy-project/gateway.sqlite --issue-customer 10000000
```

These commands print newly issued secrets. Deliver them privately; do not paste them into GitHub, logs, or issue comments. The second command grants a total 10 MB logical payload quota, not a recurring allowance. There is no public administrative API in this version. Stop the gateway process to stop all routing.

A proxy customer must support an **HTTPS proxy**, meaning TLS to the proxy itself, and HTTP/1.1 CONNECT. Use proxy username `pilot` and the issued customer token as the password. Customer-to-destination TLS remains inside CONNECT. Never put customer credentials in documentation or URLs committed to this repository.

## Implemented transport versus earlier blueprint

The earlier VPS guide describes a future WebSocket transport. This version uses **HTTP/1.1 Upgrade: proxy-project-v1 over verified TLS**, followed by length-prefixed JSON frames. It is **not WebSocket-compatible**. Connect the client directly to this gateway listener; an ordinary Caddy HTTP reverse proxy configuration is not a drop-in frontend for it.

All enrollment, revocation, device and CONNECT requests share the configured TLS port. Version one uses one stream per tunnel generation. When a stream completes or fails, the tunnel closes; the SDK reconnects with backoff. Consequently the device may be briefly unavailable between customer sessions. Persistent multiple-stream multiplexing is deferred.

Frames have a 4-byte unsigned big-endian length followed by UTF-8 JSON, at most 24,576 bytes. DATA carries strict Base64, at most 8,192 decoded bytes. Implemented messages are HELLO, PING/PONG, OPEN, OPEN_OK/OPEN_ERROR, DATA, EOF and CLOSE. One reader task owns each transport; writes are serialized. Bounded stream buffers and drain timeouts apply TCP backpressure. This version does not implement WINDOW_UPDATE.

HTTPS routes:

| Route | Authentication | Behavior |
| --- | --- | --- |
| POST `/v1/devices/enroll` | Bearer one-time grant | Requires current consent disclosure; returns device ID and token |
| POST `/v1/devices/revoke` | Bearer device token | Revokes token and disconnects the device |
| GET `/v1/devices/tunnel` | Bearer device token plus Upgrade | Opens authenticated framed tunnel |
| CONNECT `hostname:443` | Proxy-Authorization Basic | Assigns one idle approved device or returns an error |

Never implement remote execution, file operations, or downloaded tasks in the relay protocol.

## Accounting and limits

The participant counts request and response payload bytes, persisted before forwarding, against a UTC-day cap of 1 to 1000 decimal MB. The quota does not count Base64, TLS or network framing. A household usually downloads a response from the destination and uploads it again to the gateway, so actual ISP transfer can be roughly twice the logical payload plus overhead.

Customer byte counts are also persisted before forwarding. They are conservative quota reservations: a failed send may consume quota even though the destination did not receive it. These counters are **not invoice-ready billing**. Refund/reconciliation logic remains necessary before selling a metered product.

The gateway has at most 64 post-handshake connections and one session per device. Default limits include 15-second I/O drain timeouts, a 60-second idle read timeout, and a nominal 300-second customer session wait (an EOF completion wait can add up to 60 seconds). Tune only after testing. Handshake-rate protection still requires upstream/network controls. SQLite commits per chunk favor correctness over throughput.

## Before paid distribution

- Sign the executable and installer; test install, pause, uninstall and restart on real Windows machines.
- Run a restricted external-network pilot with devices you are authorized to use.
- Add production rate limits, controlled data retention, backups and recovery checks.
- Add stronger operational visibility and invoice reconciliation before charging by GB.
- Evaluate proxy request compatibility, throughput, gateway restart behavior and reconnect delay.
- Provide actual participant compensation terms outside the software if compensation is offered.

Do not buy installs solely because the unit tests or installer build pass. Use the gates in the [30-day plan](30-day-plan.md).

## References

- [Python 3.12 TLS documentation](https://docs.python.org/3.12/library/ssl.html)
- [Microsoft user-scoped DPAPI](https://learn.microsoft.com/en-us/windows/win32/api/dpapi/nf-dpapi-cryptprotectdata)
- [PyInstaller platform-specific builds](https://pyinstaller.org/en/stable/)
