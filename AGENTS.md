# CogniSight — AI Coding Instructions

## Project Overview

CogniSight is an assistive technology project intended to support people living with dementia through contextual facial recognition, outdoor navigation, indoor navigation, and caregiver support.

The system is intended to run on Raspberry Pi 5 (8 GB), with a Raspberry Pi Camera Module 2 and a GNSS module. Hardware integration and software compatibility must be verified rather than assumed.

## Team Ownership

- **Meghana:** Facial recognition and contextual information.
- **Sharanya:** Outdoor GPS/GNSS navigation.
- **Jahnvi:** Caregiver interface and overall integration coordination.
- **Jahnvi and Archisha:** Indoor navigation.

Module owners are responsible for their implementations, tests, and documentation. Shared architecture and interface changes must be coordinated with Jahnvi.

## Rules for All Coding Agents

1. Read this file, the README, and the relevant GitHub Issue before making changes.
2. Inspect the existing code before proposing a replacement or creating new files.
3. Do not invent APIs, hardware capabilities, test results, or completed features.
4. Do not restructure the repository or change shared interfaces without approval.
5. Work only within the scope of the assigned issue.
6. Preserve existing functionality unless a change is required and documented.
7. Keep dependencies minimal. Explain why any new dependency is necessary.
8. Never commit secrets, API keys, credentials, personal data, or real patient records.
9. Do not present mock data as live hardware or patient data.
10. Add or update tests and setup instructions when relevant.
11. Report assumptions, limitations, failed tests, and unverified behavior honestly.

## Git Workflow

- `main` is the stable branch.
- Create a feature branch for each task.
- Never push directly to `main`.
- Open a pull request targeting `main`.
- Reference the relevant GitHub Issue in the pull request.
- Explain the changes and testing performed.
- Wait for review and approval before merging.

### Explicit authorization for the current release

On 12 November 2026, Jahnvi explicitly authorized completing the remaining
software work, committing as `jahnvik31 <jahnvikotangale@gmail.com>`, and pushing
the finished release directly to `main`. This narrow instruction supersedes the
PR-only steps above for this release. Never force-push, infer successful remote
publication from local commits, or treat this as permission for unrelated future
releases. The normal PR workflow still applies afterward.

Read [NEXT_AGENT_README.md](NEXT_AGENT_README.md), [validation](docs/VALIDATION.md)
and the [Pi runbook](docs/hardware/PI-RUNBOOK.md) before continuing. Indoor issue
#5 remains deferred. Software implementation of #6/#7 is present; #8 covers the
available-module integration. Hardware acceptance still requires real devices.

## Integration Rules

- Do not merge entire existing module repositories blindly.
- Audit and validate each module before integrating it.
- Agree on shared interfaces before implementing cross-module communication.
- Keep hardware-specific code configurable where practical.
- Handle unavailable devices, invalid data, and module failures gracefully.
- Document any change to shared interfaces and notify affected module owners.

## Definition of Done

A task is complete when:
- Its acceptance criteria are met.
- Relevant tests have been run and their results reported.
- Documentation is updated where necessary.
- Changes are limited to the intended scope.
- A pull request is ready for review.

Do not claim that a feature works on Raspberry Pi hardware unless it has actually been tested on the relevant hardware.
