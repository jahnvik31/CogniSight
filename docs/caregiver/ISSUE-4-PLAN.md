# Issue #4 — Caregiver dashboard implementation specification

**Owner:** Jahnvi. **Scope:** one wearer/Pi, one caregiver credential, read-only monitoring from a caregiver's phone on the same Wi-Fi. This records the user's confirmed scope and the implementation boundaries; target-device acceptance remains pending. It replaces the earlier planning alternatives rather than leaving local-versus-phone access unresolved.

[Issue #4](https://github.com/jahnvik31/CogniSight/issues/4) calls for recognition/context, outdoor location/time, separate indoor status, honest missing/stale/mock states, tests and setup documentation. Cross-module integration remains coordinated through #6. The source issue snapshot consulted on 12 November 2026 was approximately two weeks old; the current repository is the implementation source of truth.

## 1. Resulting behavior and boundaries

The dashboard contains four clearly separated cards: recognized people and verified context, outdoor GPS fix/status, indoor integration status, and device health. A successful page refresh means only that the dashboard backend responded; it is not proof that the camera or receiver progressed, that a location is accurate, or that the wearer is safe.

Recognition names, relationships and notes come only from caregiver-maintained profiles. The page exposes the current eligible recognition snapshot; it does not claim to provide a complete event log, all missed encounters, a camera stream, or continuous identity verification. It displays source age and source status. Profile enrollment/editing remains in the existing Pi-local tool and is not accessible through the phone service.

Outdoor navigation v1 provides verified location/status only, as confirmed by the user. Current coordinates require a valid, finite, fresh fix; unknown/no-fix, disconnected, invalid and stale are different states. Preserved `last_known` data is labelled historical and retains its original time/age. `(0,0)` can be an actual valid fix and is never a missing-data default. No map tiles, route computation, walking instructions, heading inference or external geolocation service are added. Receiver model, real GNSS accuracy and transport compatibility remain unverified until tested on the actual hardware.

Indoor navigation is explicitly unavailable/not integrated. The dashboard neither invents indoor progress nor uses outdoor coordinates as an indoor position. A later real indoor adapter must have its own reviewed localization, map/version and expiry contract.

All personal context is read-only on the phone. No remote enrollment, wearer-control command, camera/audio capture, conversation memory, emergency notification, longitudinal location history, multiple wearers, or cloud service is in scope.

## 2. Composition and contracts

### Process and web boundaries

A single recognition runtime remains the camera owner. Its read-only `dashboard_snapshot()` composes actual source status and age. The caregiver provider callback is read by a separate Flask application, created with `create_dashboard_app(provider, state_dir, allowed_hosts)`. The backend listens only on 127.0.0.1, port 8766 by default. The existing enrollment application remains separately bound to loopback port 8765. The caregiver application has no enrollment, profile mutation or recognition-control routes.

The phone reaches HTTPS on the Pi's selected LAN interface through Caddy. Caddy forwards only to the caregiver backend. It must never forward to the enrollment app. Use existing Flask/Jinja/Waitress dependencies plus locally packaged JavaScript/CSS, avoiding an additional frontend toolchain or network asset dependency. Flask's deployed application needs a production server; Waitress provides a single-process threaded WSGI deployment. [Flask deployment guidance](https://flask.palletsprojects.com/en/stable/deploying/), [Waitress documentation](https://flask.palletsprojects.com/en/stable/deploying/waitress/)

### Snapshot contract

The provider returns schema version 1 and recognition/outdoor/indoor/health sections. A pure allowlisted projection accepts only intended fields; images, embeddings, raw GPS sentences, credentials, serials, transcripts, unknown fields and arbitrary health keys never enter the response.

| Section | Values shown |
|---|---|
| Recognition | status; explicit `data_source`; optional observed UTC; monotonic-derived age and producer expiry; up to four approved person records (`person_id`, name, relationship, note) |
| Outdoor | status; source/mode; optional valid latitude/longitude and speed; optional observed UTC; monotonic-derived age/expiry; optional historical `last_known` fix |
| Indoor | `unavailable`, `not_integrated`; no invented destination/checkpoint |
| Health | allowlisted camera, microphone, playback, model, storage, clock, runtime and navigation component state codes |

Recognition observed UTC is numeric or absent. GPS observed time may be timezone-qualified ISO 8601; the projection converts it to a finite bounded Unix timestamp. Naive/malformed/oversized timestamps are omitted. Observation UTC and freshness are separate: receipt time must not be substituted for an old GNSS observation to make it current.

Source mode is independent of operational status. `live` means the underlying source is real and currently eligible, `mock` means explicitly simulated, and `unavailable` means no eligible current data. Preserve the operational explanation even when current data is unavailable: `paused`, `uncalibrated`, `no_fix`, `disconnected`, `invalid` and `stale` remain visible. Unsupported schema, missing producer or unusable coordinates fail closed. A real outage never automatically switches to a mock provider.

The projection does not persist a new history store. It reads the current provider snapshot only. The recognition module's encounter history and biometric data remain owned by that module. This avoids implying that its bounded in-process event queue is a durable or complete monitoring log.

## 3. Freshness, failures and phone behavior

The page fetches `/dashboard/state` every half second while connected (five-second retries after failure), at most one request at a time, with a four-second request timeout. It checks HTTP success, JSON type and schema; an HTTP error does not automatically reject a Fetch promise. Browser update handling uses safe DOM text operations rather than injecting profile HTML. [MDN Fetch behavior](https://developer.mozilla.org/en-US/docs/Web/API/Fetch_API/Using_Fetch)

The backend supplies age from actual producer progress, not from the HTTP refresh. Recognition frame presence expires at one second by default; GPS expires at its configured maximum age, ten seconds by default. The projection accepts a finite positive producer `max_age_seconds` capped at 300 seconds and rejects currentness at the expiry boundary. The browser advances age using `performance.now()` between polls so a stopped poll cannot freeze “live.” It never compares the phone's wall clock with a Pi timestamp to determine freshness.

Recognition people/context disappear when the source becomes stale or unavailable. Invalid/no-fix/stale GPS does not retain current coordinates. Historical `last_known` remains explicitly separate and its age continues increasing. The UI does not reinterpret speed/course as a stationary person's facing direction or an error estimate as guaranteed accuracy.

A failed, malformed, timed-out or disconnected fetch clears personal/current values and shows reconnecting. A 401/403 or unexpected authentication redirect clears sensitive DOM data and stops polling until sign-in. Polling pauses while the tab is hidden and resumes when visible; age rendering must still expire stored observations. No overlapping polls, browser geolocation, CDN, analytics, external map calls, browser notification or automatic speech is added.

Explicit mock input produces both a persistent DEMO banner and source labels. Clearing a snapshot clears the demo banner as well. Live failures show unavailable, not invented demonstration values.

## 4. Same-Wi-Fi access and privacy

Use a separate cookie name and an HMAC-derived signing key based on the existing local session secret. The caregiver password hash is shared with Pi-local setup; signed sessions are not shared across applications. Configure Secure, HttpOnly, SameSite=Strict cookies, CSRF-protected login/logout, password throttling (five failed attempts per minute), bounded requests, no-store responses, escaped templates and restrictive security headers. Use `Referrer-Policy: same-origin` so HTTPS login/logout retain the same-origin Referer required by Flask-WTF strict SSL CSRF validation; missing or cross-origin Referer is rejected even with a valid token. Do not disable that strict check. Keep personal fields out of session cookies and logs. Disable per-request session refresh so half-second polling with five-second failure retries does not keep a fifteen-minute signed session alive indefinitely. [Flask security/configuration](https://flask.palletsprojects.com/en/stable/web-security/), [session configuration](https://flask.palletsprojects.com/en/stable/config/)

The application requires an explicit hostname/IP allowlist, HTTPS, same-origin requests and a loopback proxy peer. Wildcards and unspecified allowlists are rejected. Waitress trusts only the local proxy's protocol header; do not trust client-supplied host/prefix or arbitrary proxy chains. Backend ports remain loopback-only. The app's proxy middleware is configured for that one verified protocol hop, not for changing client identity. [Werkzeug proxy trust](https://werkzeug.palletsprojects.com/en/stable/middleware/proxy_fix/)

The supplied Caddy example binds the selected LAN IP, rejects non-private source addresses and forwards only to 127.0.0.1:8766. It disables implicit HTTP redirects; the caregiver navigates directly to HTTPS. Keep WAN/router port forwarding disabled. Choose one actual reachable LAN hostname or reserved IP, matching application allowlist, Caddy site address and phone URL. Guest Wi-Fi client isolation may prevent connectivity and requires network configuration rather than weakening authentication.

Caddy `tls internal` uses a local CA. The phone must trust the public root certificate after its fingerprint is verified through a trusted channel; never copy the CA private key or bypass certificate warnings. Certificate storage is service-account-specific. [Caddy TLS](https://caddyserver.com/docs/caddyfile/directives/tls), [local HTTPS/client trust](https://caddyserver.com/docs/automatic-https), [LAN bind](https://caddyserver.com/docs/caddyfile/directives/bind), [proxy behavior](https://caddyserver.com/docs/caddyfile/directives/reverse_proxy)

The dashboard does not open internet access, configure the router, install a phone trust root, or provision Caddy automatically. Deployment steps remain concrete documented work on the actual Pi/phone. Remote access away from the same Wi-Fi requires a new reviewed transport/security scope.

## 5. Implementation milestones and local checks

1. **Projection and status policy:** pure functions validate source mode, finite/ranged coordinates, timestamps, age, expiry, current people and historical location. Missing integration remains explicit. Regression cases cover the real `(0,0)` case, invalid values, no-fix with historical data, mock labels, unknown schema and producer-specific expiry.
2. **Read-only phone surface:** independent caregiver app, login/logout, `/dashboard`, `/dashboard/state`, self-hosted responsive cards and status/age updates. It cannot expose enrollment even when the broader runtime runs on the same Pi.
3. **Secure optional startup:** compose the provider and second loopback server only when caregiver configuration is explicitly enabled and allowed hosts exist. Reuse private state and independent session signing; retain local enrollment unchanged. Root startup owns server lifecycle and handles failed startup/shutdown rather than creating another camera owner.
4. **Verified source integration:** recognition snapshot derives from actual runtime progress and approved profiles. GPSD location/status snapshot retains real-source mode and `last_known`; unconfigured receiver means disconnected/unavailable rather than a mock fix. Indoor remains not integrated. Coordinate external contracts through #6; do not claim receiver compatibility from parser tests.
5. **Pi/phone qualification:** production-server proxy path, trusted certificates, real browser behavior, actual GNSS and camera integration, failure isolation and combined resource/latency measurements must be executed before declaring issue #4 complete.

Implementation and tests exist for these software surfaces. Flask integration checks are currently dependency-gated on the development host; no phone, TLS proxy, Pi-native or hardware acceptance result has been claimed. Each verified change is intended for a separate local commit by the primary agent; publishing and merge require working GitHub connectivity and the user's authorized workflow.

## 6. Release acceptance matrix

| Area | Required evidence |
|---|---|
| Authentication | Unauthenticated state returns 401; login/logout reject missing CSRF; secure distinct cookie; automatic polls do not renew fifteen-minute expiry; expired session clears phone content |
| Proxy/TLS | Real Waitress header middleware plus local Caddy path; nonlocal backend peer, wrong Host, cross-origin Origin and plain HTTP rejected; phone trusts correct certificate without warning |
| Data validity | Unknown schema/unintegrated producers unavailable; invalid/ranged/nonfinite GPS rejected; `(0,0)` valid when source fix is valid; observed timestamp cannot drive freshness |
| Recency | Recognition frame age and configured GPS expiry respected; phone wall-clock changes do not affect monotonic expiry; no-fix after valid fix yields historical last-known only |
| Recognition/privacy | Only approved profile fields; stale source clears names/context; no vectors, frames, raw notes outside allowlist, credentials or raw exception messages in HTTP/logs/cookies |
| Failures | Camera/GPSD removal, producer stall/restart, storage failure, malformed provider response and connection timeout remain honest and isolated; other sections can still display their own state |
| Mock separation | Simulated source produces DEMO label; no silent fallback or mixed-source claim; disconnect clears mock indicator with content |
| Browser/accessibility | Real phone viewport, keyboard focus, 200% zoom, narrow reflow, text status labels, contrast and screen-reader status checks; no auto-playing speech |
| Resource/load | Two-hour combined run, five open dashboard tabs, no crashes/unbounded DOM/queue growth; total relevant-process memory remains under existing 4 GB budget; recognition/audio latency gates still pass |
| Presentation latency | Proposed dashboard p95 accepted-update-to-render <=2 seconds during connected half-second polling; measure source receipt, HTTP and render delay separately, not only server response time |
| Offline | No third-party requests after installation; same-Wi-Fi browser works with internet disconnected; no default map/CDN dependence |
| Documentation | Clean setup reproduces qualified versions, explicit configuration/host/certificate procedure, limitations and incomplete indoor integration documented |

Aim for relevant WCAG 2.2 AA behaviors through automated and manual checks; do not assert blanket accessibility conformance without evaluation. [W3C WCAG reference](https://www.w3.org/WAI/WCAG22/quickref/)

The dashboard is disabled by default until explicitly configured. Rollback disables only its optional service and proxy; recognition/enrollment and private profiles remain usable. There is no new location-history database migration. Issue #4 completion requires real available-module-to-phone evidence and documented unavailable integrations, not just successful fixture rendering.
