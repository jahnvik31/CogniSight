# Software validation and release boundaries

## Implemented scope

- #2: offline recognition/context, USB speech adapters, local enrollment and history.
- #3: user-confirmed **verified location/status first**, fresh GPSD implementation.
  No walking directions, maps, cellular support or guessed GNSS vendor commands.
- #4: user-confirmed **caregiver phone on the same Wi-Fi**, read-only authenticated
  HTTPS monitoring; one wearer and credential per Pi. Enrollment stays loopback-only.
- Indoor navigation has no producer and remains explicitly not integrated.

The user authorized incremental local commits by
`jahnvik31 <jahnvikotangale@gmail.com>` and a final push to `main` after this work.
The usual PR/main workflow in AGENTS.md is superseded for that explicit push only.

## Local verification

```sh
PYTHONPATH=src python3 -m unittest discover -s tests -v
node --test tests/dashboard.test.cjs
PYTHONPYCACHEPREFIX=/private/tmp/cognisight-pycache python3 -m compileall -q src scripts tests
```

The development host lacks Flask/Flask-WTF, Waitress, NumPy/OpenCV and Pi/audio
libraries. Dependency installation and Git pushes are blocked by this execution
environment's network restrictions. The Python suite reports exact skipped checks;
those are not successes. It also skips its real TCP loopback test when the sandbox
denies socket binding. Boundary tests still exercise the GPSD parser/worker with
controlled synthetic socket responses.

Node tests execute the **shipped dashboard JavaScript** against a small DOM boundary:
source-age expiry without new polls, expired-session removal of sensitive content,
and network-failure clearing/retry. They are not a substitute for a phone browser.
The actual Jinja templates, styles and script were additionally rendered in
Playwright at a 390-pixel viewport using intercepted, clearly labelled simulated
responses. No horizontal overflow was observed. That preview does not test Flask
login, certificates, real positions or target hardware.

## CI gate

`.github/workflows/software-checks.yml` uses Python 3.11 and Node 24, installs
software-test dependencies, rejects any skipped software tests, executes the
JavaScript tests, builds a wheel and checks that shipped templates/styles/scripts
are present. It uses read-only repository permissions and does not commit/publish.
**The workflow has not run in this session.** Its result must be checked after
network access permits pushing. Hardware acceptance is never inferred from CI.

Reference action usage:
[checkout](https://github.com/actions/checkout),
[setup-python](https://github.com/actions/setup-python),
[setup-node](https://github.com/actions/setup-node).

## Review fixes

Independent review and regression checks addressed:

- Slow recognition no longer blocks the independent GPS dashboard projection.
- Dropped/late frames cannot manufacture consecutive recognition or a continuous
  encounter; queued speech expires using elapsed time.
- Waitress trusts only the local proxy's HTTPS protocol header; forwarded host and
  client-address headers remain untrusted. The backend is still loopback-only.
- Polling does not extend the fifteen-minute caregiver session.
- HTTPS forms retain same-origin Referer so Flask-WTF's strict CSRF checks work;
  missing/cross-origin Referer remains rejected. The real Flask regressions are
  dependency-gated locally and mandatory in CI.
- Listener, keepalive channels and request workers are stopped before closing
  SQLite. A stuck request worker makes shutdown fail rather than closing its DB.
- Stop timing checks every trial; command accuracy checks every speaker/intent;
  private qualification reports cannot overwrite source/configuration files.

## Not yet qualified

1. Exact GNSS board model, connection, antenna, vendor setup, and genuine outdoor fix.
2. Pi camera/model inference, headset speech/interruptions, and the qualified
   Python/apt/model lock on the actual device.
3. Caddy validation, phone CA trust, end-to-end HTTPS login/logout/expiry and LAN
   reachability. No certificate-warning bypass is allowed.
4. Real recognition accuracy, GNSS accuracy/fix behavior, accessibility and two-hour
   combined-load/thermal/memory/latency measurements.
5. A successful GitHub push and successful software CI/package build.

Use module plans/setup guides and docs/recognition/QUALIFICATION.md to record
actual evidence. No GitHub issues are closed or hardware acceptance claimed here.
