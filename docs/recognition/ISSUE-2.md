# Draft update for issue #2: Build offline facial recognition with verified context

Supersedes the audit-only implementation scope following the approved fresh-build
plan. Owner remains Meghana; shared-interface coordination remains with Jahnvi.
This draft has not been published to GitHub.

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

Software for these milestones exists on the feature branch; checkboxes require
review and actual acceptance evidence, not merely source-file existence.

## Acceptance

Use docs/recognition/QUALIFICATION.md for measured release gates. All tests must
be rerun with real dependencies on the Pi. Record skips/blockers, privacy and
clock behavior, known/unknown cohort coverage and actual performance. Keep raw
biometric data out of the repository. Open reviewed PRs against main; do not
merge directly or close this issue before hardware acceptance.

## Integration boundary

Only module-local contracts are included here. Confirm external recognition
and speech coordination interfaces through #6 before broader integration in #8.
