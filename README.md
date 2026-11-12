# CogniSight

**Next coding agent or device contributor:** read [NEXT_AGENT_README.md](NEXT_AGENT_README.md) first. It records the implemented software, hardware corrections and remaining device tests.

CogniSight is an assistive technology project intended to support people living with dementia through contextual recognition, navigation assistance, and caregiver support.

## Project Status

**Phase:** Software validation complete for available modules; target-hardware qualification pending.

Fresh recognition, GNSS positioning, and caregiver-monitoring implementations are present. System contracts, Pi diagnostics, and available-module software integration are implemented. Target Raspberry Pi, receiver, headset, and phone qualification remains pending; software tests do not establish hardware compatibility.

## Modules

### 1. Contextual Facial Recognition
Recognises registered people and uses stored relationship and contextual information to provide meaningful assistance.

### 2. Outdoor Navigation
Acquires verified location/status from local GPSD, distinguishing current fixes from historical locations. Walking-route directions are outside this version.

### 3. Indoor Navigation
Deferred by the user (issue #5); no indoor producer or guidance is implemented.

### 4. Caregiver Support
Authenticated read-only dashboard for a caregiver phone on the same Wi-Fi, with HTTPS, module status, and stale/unavailable-data handling. Enrollment remains local to the Pi.

*Available-module software is implemented. Indoor remains deferred, and physical compatibility/accuracy must still be measured.*

## Development Workflow

- `main` contains the stable, reviewed version.
- Develop new work on feature branches.
- Submit pull requests for review before merging.
- Test changes and document setup instructions.
- Track work and known issues through GitHub Issues.

The user explicitly authorized this completion release directly to main; see the scoped exception in [AGENTS.md](AGENTS.md).

## Setup

Download the [printable next-steps PDF](output/pdf/CogniSight-next-steps.pdf). It contains a short checklist and the full laptop/Pi/phone procedure.

For the physical-device contributor, start with the [simple SSH runbook](docs/hardware/PI-RUNBOOK.md) and [hardware checklist](docs/hardware/README.md). See the [architecture and editable draw.io diagram](docs/architecture.md) and [module contracts](docs/system/CONTRACTS.md).

Then read [recognition and service setup](docs/recognition/README.md), then [GNSS configuration](docs/navigation/README.md) and [same-Wi-Fi phone access](docs/caregiver/README.md). See [software validation and remaining release gates](docs/VALIDATION.md).

## Team

This is a collaborative student project. Module ownership and contributions will be documented as integration progresses.

## Facial recognition module (issue #2)

A fresh offline recognition, verified-context, USB voice, and local enrollment
implementation is available. See [setup and operation](docs/recognition/README.md),
[approved plan](docs/recognition/PLAN.md), and
[hardware qualification gates](docs/recognition/QUALIFICATION.md).

**Hardware qualification is pending.** Local policy tests are not proof of Pi
compatibility, recognition accuracy, or live audio performance. Existing modules
remain independently owned; optional GPSD and caregiver monitoring connect through the documented module contracts.

## Software checks

```sh
PYTHONPATH=src python3 -m unittest discover -s tests -v
node --test tests/dashboard.test.cjs
```

GitHub Actions installs the web/vision test dependencies and rejects skipped
software checks. Local wheel building, real Flask/Waitress integration and OpenCV image-quality checks
have passed; see [validation](docs/VALIDATION.md) for the exact environment and one
sandbox socket skip. Remote CI remains pending until the workflow actually runs. Native Pi and phone acceptance is a separate requirement.
