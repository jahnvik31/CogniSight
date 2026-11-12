# Draft update for issue #2: Build offline facial recognition with verified context

Supersedes the audit-only implementation scope following the approved fresh-build
plan. Owner remains Meghana; shared-interface coordination remains with Jahnvi.
This draft has not been published to GitHub. Current software and acceptance
status are recorded in [validation](../VALIDATION.md); publishing source code does
not close this issue or certify hardware.

## Deliverable

A fresh Raspberry Pi 5 (8 GB) / Camera Module 2 recognition module with offline
English USB-headset interaction and a local caregiver enrollment tool. Support
100 profiles, caregiver-entered relationships/notes, and previous recognition
history. Do not reuse reverted implementations.

## Implementation milestones

- [ ] Qualify camera, USB input/output, model pair and locked runtime on the Pi.
- [ ] Enroll/update/disable/delete profiles and versioned embeddings locally.
- [ ] Recognize with unknown rejection, tracking, confirmation and cooldowns.
- [ ] Add automatic speech and prefixed commands with cancellable output.
- [ ] Add context/history, bounded events, health, service operation and tests.
- [ ] Complete actual held-out recognition, headset and two-hour soak evaluation.

Software for these milestones is implemented in the release tree; checkboxes require
review and actual acceptance evidence, not merely source-file existence.

## Acceptance

Use docs/recognition/QUALIFICATION.md for measured release gates. All tests must
be rerun with real dependencies on the Pi. Record skips/blockers, privacy and
clock behavior, known/unknown cohort coverage and actual performance. Keep raw
biometric data out of the repository. The current release has explicit user authorization to push to main. Future
changes follow the normal PR workflow unless instructed otherwise; never close
this issue before hardware acceptance.

## Integration boundary

The implemented recognition/event, snapshot and speech boundaries are documented
in [system contracts](../system/CONTRACTS.md). #8 validates available-module
software integration; physical Pi/phone behavior still needs device evidence.
