# Caregiver dashboard — issue #4

The caregiver dashboard is a separate, read-only HTTPS application for a phone
on the same Wi-Fi as the Pi. It shows recognition/context, outdoor GPS fix/status,
indoor integration status, and module health. It does not provide remote enrollment,
walking routes, an emergency service, or proof that the wearer is safe.

Implementation exists; **Pi, GNSS receiver, phone browser, certificates, native
recognition/audio and combined-load qualification have not been performed here**.
Latest executed software checks and any dependency skips are recorded in
[validation](../VALIDATION.md). Start with the [Pi runbook](../hardware/PI-RUNBOOK.md).
See ISSUE-4-PLAN.md for the full
specification and acceptance gates. Local setup/enrollment stays on port 8765;
the dashboard backend stays on loopback port 8766. Do not proxy 8765.

## Configure the application

Use the ordinary recognition installation and run `cognisight password` on the Pi.
The dashboard uses that caregiver password but a distinct secure session cookie
and signing key. One wearer/Pi and one caregiver credential are supported.

Add the following section to the private runtime config (outside this example,
replace hosts with actual reachable values):

```json
{
  "caregiver": {
    "enabled": true,
    "allowed_hosts": ["cognisight.local"],
    "backend_port": 8766
  }
}
```

The hostname must resolve to this Pi on the phone. mDNS support varies with the
phone/router; a reserved LAN IP may be used instead. The exact same chosen host
must be in `allowed_hosts`, the Caddy site address, and the URL used on the phone.
No wildcard hosts, automatic LAN binding, cross-origin access, or plain-HTTP
phone login is enabled. Without an explicit allowlist the service fails closed.
This version configures the standard HTTPS port 443 only; allowed hosts are exact
hostnames or literal IP addresses without a port.

## HTTPS on the same Wi-Fi

Use a Caddy installation appropriate for the actual Raspberry Pi OS and architecture.
Follow the official [Caddy install instructions](https://caddyserver.com/docs/install).
Inspect `deploy/Caddyfile.example`, set `COGNISIGHT_HOST` and `COGNISIGHT_LAN_IP`
for the actual Pi, and validate it with `caddy validate --config <Caddyfile>` before
running the proxy. Keep Caddy's standard TLS settings. This template binds the
selected Pi LAN IP, refuses non-private source addresses, forwards only to
127.0.0.1:8766 and disables implicit HTTP redirects. It must never proxy the
recognition enrollment application. No router port forwarding is required or
supported; leave WAN access disabled.

The template uses Caddy's internal certificate authority. A phone does not
implicitly trust the Pi's CA: install the **public root certificate only** into
the phone's trusted certificate store using that phone OS's supported process.
Verify its SHA-256 fingerprint against the certificate on the Pi through a trusted
channel. Do not distribute the CA private key or bypass certificate warnings.
Remove the CA from the phone if this installation is retired. Local HTTPS and
client trust behavior are described in the official
[Caddy HTTPS documentation](https://caddyserver.com/docs/automatic-https) and
[`tls internal` documentation](https://caddyserver.com/docs/caddyfile/directives/tls).
Certificate storage paths depend on the service account; inspect the actual Caddy
service environment rather than assuming a root/home directory.

Open `https://cognisight.local/dashboard` (substitute the chosen host) on the phone
while it is on the same Wi-Fi. A properly trusted certificate must produce no
browser warning. Sign in with the caregiver password. If the network uses guest
client isolation, devices may be unable to reach one another; resolve that network
configuration without exposing the backend to the internet. Recheck the allowlist
and certificate names after an IP/hostname change.

The caregiver app uses `Referrer-Policy: same-origin`: HTTPS forms retain the
same-origin Referer required by Flask-WTF strict CSRF validation without disclosing
referrers to other origins. Missing or cross-origin Referer is rejected even with
a valid CSRF token. Strict SSL CSRF checks remain enabled.

The app trusts exactly one proxy's HTTPS protocol forwarding information only
from a loopback peer. The deployment must keep its WSGI backend loopback-only and
must not add a second proxy without reviewing that trust configuration.
[Caddy reverse proxy](https://caddyserver.com/docs/caddyfile/directives/reverse_proxy),
[Werkzeug proxy trust](https://werkzeug.palletsprojects.com/en/stable/middleware/proxy_fix/).

## What the statuses mean

The page polls every half second while connected (five-second retries after failure). Source age advances independently between
polls. Producer-supplied expiry is enforced: recognition observations default to
one second; GPS fixes default to ten seconds (configurable by the GPS module). A successful page
refresh is not proof that a camera/GPS source progressed. Read-only runtime
snapshots supply actual source age. On a failed fetch the UI removes personal
context/current coordinates and shows disconnected; on an expired session it
clears the data and requires sign-in.

Recognition names, relationships and notes come only from enrolled caregiver
profiles. No confidence-percentage or clinical inference is shown. Outdoor
coordinates require a finite valid current fix. No fix, disconnected, invalid,
and stale states are distinct; any preserved **Last known location** is explicitly
historical. GNSS time can be unavailable. Indoor status says **not integrated**
until an actual module is connected; GPS is not used as a substitute indoor fix.
No map provider, CDN, analytics, camera stream, raw biometric vector, microphone
recording or browser geolocation is used.

If test code supplies `data_source: mock`, the dashboard shows a permanent DEMO
banner and mock labels. Live-data failures never automatically switch to mock data.

## Validate before use

```sh
PYTHONPATH=src python3 -m unittest discover -s tests -p 'test_caregiver*.py' -v
```

Run the complete suite with Flask/Flask-WTF/Waitress installed; software web
checks must not remain skipped for release. Flask test-client checks exercise
authentication/projection, not a physical phone or TLS handshake. On the real Pi/phone, verify trusted TLS,
login/logout/session expiry, invalid Host/Origin rejection, no enrollment URLs,
no external requests, keyboard/zoom/reflow, and source disconnection/recovery.
Measure dashboard render delay and total system load with recognition/audio
running. Review actual GNSS data validity and freshness; synthetic fixtures do not
establish positional accuracy or receiver compatibility.
