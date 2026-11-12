# Implementation ledger — docs/recognition/PLAN.md

- Branch: feat/2-contextual-recognition; source checkout initially clean.
- User explicitly withdrew commit identity. NO COMMITS until new author supplied.
- Network DNS blocks pip installs; local Python 3.9.6 lacks numpy/Flask/pytest.
- Ruling: use unittest-compatible tests, also discoverable by pytest. Real
  dependency integration checks are explicit skips when unavailable; no fake
  hardware successes. Cost: integration acceptance requires execution on Pi.
- Ruling: work on feature branch in existing checkout; no extra worktree needed
  for this empty project and user-authorized implementation.
- Preflight: enrollment/storage -> gallery snapshots; tracker -> context/history;
  recognition -> expiring speech; runtime -> localhost control. Shared contracts
  are module-local only. A single runtime owns the CSI camera.

## Implemented

- Transactional profiles/embeddings, normalized gallery matching, conservative
  spatial tracking, enrollment guard, context/encounter lifecycle and expiry.
- Picamera2 single-owner adapter, OpenCV model/quality gates, latest-frame slot.
- USB Vosk/Piper pipeline, bounded speech/microphone queues, cancel/reconnect.
- Local authenticated CSRF-protected browser setup and additional samples.
- Model manifest/downloader, held-out calibration evaluator, qualification
  recorder, CLI, service template and Pi setup/acceptance documentation.

## Rulings

- Ruling: stock speech prefix is `computer`, configurable; custom `cogni` needs a
  lexicon containing it. Missing vocabulary fails closed. Cost: wearer command
  phrasing differs from the illustrative original plan; documented in setup.
- Ruling: clock timestamps require systemd-timesyncd synchronization marker and
  a sane date. Cost: alternative clock-sync setups show unavailable history until
  supported; do not invent encounter dates from an unverified clock.
- Ruling: exact dependency lock and hardware acceptance remain pending the Pi;
  never claim a lock generated on this Mac qualifies the native camera stack.

## Independent review and fixes

Fresh reviewer examined source and reproduced foreground-target and delayed-audio
failures. Fixed all five Important findings with failing-then-passing regressions:
unknown foreground blocks background identification; audio-readiness recovery
announces visible identity; old microphone stream closes before reconnect;
storage failure during presence reset cannot kill runtime; password state inside
checkout rejected. Also covered queued profile-edit invalidation and cooldown
preservation. UI uses slightly shorter relationship/pronunciation input limits
than storage (100 vs150); this only constrains input and is deferred UI polish.

## Validation boundary

No assets downloaded, no hardware tests, no Flask/native image integration ran
on the development machine because required dependencies could not be installed.
Available tests explicitly report these dependency skips. Qualification helper
ran metadata-only and correctly retained release_qualified=false. Issue update
prepared locally; publishing/PR requires a valid GitHub login and network access.

## Phase 2 — qualification hardening

- User authorized fresh #3 and #4 implementation in parallel, sequential local
  commits under jahnvik31, and a final push to main after completion.
- Qualification gates now enforce every stop trial within one second and correct;
  command accuracy must pass for every speaker, intent, and speaker/intent pair.
- Failed headset smoke checks exit nonzero. Qualification reports are atomic,
  private, and cannot clobber input files or symlink targets.
- Validation: 87 tests run, 80 pass, seven dependency skips. All new acceptance
  regressions were observed failing before the fix. No target hardware claims.

- Temporal regressions reproduced and fixed: frame gaps cannot complete a
  three-observation identity confirmation; expired tracks retire before spatial
  reassociation; returning people start new encounters after ten seconds.
- Speech validity now checks elapsed monotonic time even without another camera
  frame. Added read-only dashboard projection with separate recognition, outdoor,
  indoor and health status; no second camera owner or invented indoor data.
- Pre-commit full suite: 128 tests, 116 pass, 12 explicit environment/dependency
  skips. New temporal and bridge cases pass against real storage/state logic.

## Issues #3 and #4 implemented in parallel

- User confirmed every module is fresh, has a GNSS board, selected verified
  location/status first, and selected a caregiver phone on the same Wi-Fi.
- GPSD and caregiver software, comprehensive plans, deployment guidance and
  lifecycle wiring are committed separately. Exact board wiring is not guessed.
- Independent review corrected Waitress proxy filtering, session auto-renewal,
  keepalive/request-worker cleanup, inference-lock blocking, and HTTPS CSRF
  Referer compatibility. Native-dependency checks remain visibly skipped locally.
- Real shipped UI rendered at phone width with clearly simulated intercepted data;
  four shipped-JavaScript behavior tests pass. CI rejects dependency skips and
  checks wheel assets once it can run. See docs/VALIDATION.md for release boundaries.

- User approved the redesigned phone UI. Actual shipped markup/styles/script
  were inspected at 320/390/1440 widths with simulated inputs and no overflow.
  Connected refresh now precedes one-second recognition expiry; failure retries
  stay five seconds. No stale-data retention or new data claims were introduced.

- Latest user instruction: keep commits local; defer any push to main until all
  issues have been looked after. No remote push performed in this phase.
