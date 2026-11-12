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
