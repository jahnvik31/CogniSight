# CogniSight module contracts (schema 1)

Implemented boundaries for issues #2, #3, #4 and #6. These describe the software,
not successful Pi/device qualification. Indoor issue #5 is deferred. The user
approved implementation of #6/#7 on 12 November 2026; this records user approval,
not separate sign-off from every module owner.

## Ownership and process boundaries

| Owner | Module | Inputs | Outputs / failure |
| --- | --- | --- | --- |
| Meghana | `recognition/` | One camera, enrolled verified profiles, explicit audio routes | Recognition/context, best-effort events, camera/model/storage health |
| Sharanya | `navigation/` | Local GPSD complete TPV messages | Verified location/status or explicit no-fix/disconnected/invalid/stale |
| Jahnvi | `caregiver/` and integration | Runtime snapshots, authenticated same-origin requests | Read-only allowlisted schema-1 dashboard |
| Jahnvi and Archisha | Indoor, deferred | No producer | Always unavailable / not_integrated |

One Runtime owns Vision, AudioEngine and optional NavigationService. Vision owns
one Picamera2 instance/capture thread. Runtime serializes model calls and enrollment;
there is no second camera for enrollment. The single-slot latest-frame mailbox has
one consuming cursor; another module must not independently consume it. It drops
backlog, retains an owned BGR array, and writes no camera images to disk. Requested
640×480/15 fps, four faces/iteration and OpenCV's two-thread cap are work limits,
not measured performance. Hardware/native calls can hang or crash this process;
threads do not provide process crash isolation.

The navigation worker owns its GPSD socket and reconnect loop independently of
recognition. Recognition failure does not stop receiving GPS, and recognition
lock contention returns an unavailable recognition section while retaining the
independent outdoor snapshot. Audio route loss clears work and retries only an
explicit matching USB input/output. There is no default speaker or network fallback.

## Capture and time

`FramePacket` is a frozen module-local dataclass, not a public JSON envelope:

| Field | Type / rule |
| --- | --- |
| `frame_id` | Integer observation identity; Vision counter increases for this Vision instance, including camera retries; a new process/instance can reset it |
| `captured_at` | Pi process monotonic seconds when the captured array is received; not sensor exposure time |
| `utc` | Nullable UTC epoch seconds, supplied only when the system synchronization marker is present and calendar time passes the sanity floor |
| `image` | Owned three-channel BGR image; never exported in events/dashboard |

Monotonic time determines freshness, independently of UTC. Inference completion,
HTTP fetch time and phone render time never replace source observation time.
Runtime feeds frame `captured_at` and original `utc` to recognition, drops identity
results that are already one second old after inference, and rejects duplicate or
out-of-order observation timestamps. Observation monotonic values must be finite,
nonnegative numeric values. Process restarts construct fresh trackers/projections;
no persisted monotonic timestamp or sequence is reused across reboot. No global
source-session record is introduced because no cross-process consumer needs it.

A current monotonic observation can exist without trusted UTC; calendar/history
claims then remain unavailable. GPSD receiver-reported UTC is timezone-qualified
ISO input, converted to epoch seconds by caregiver projection. It does not prove
the Pi system clock was synchronized. `data_source` expresses evidence availability,
not proof of clock trust. Raw monotonic values never cross to the phone.

## Recognition events

`RecognitionEvent` is frozen. Its `to_dict()` returns these required keys:

| Field | Type / constraint |
| --- | --- |
| `schema_version` | Integer 1, boolean rejected |
| `event_id` | Nonempty string ≤100; generated UUID once on construction when omitted; stable on every serialization |
| `kind` | `confirmed` or `lost` |
| `track_id` | Positive integer, boolean rejected; local tracker identity |
| `person_id` | Nonempty string ≤100; actual enrolled opaque profile ID |
| `timestamp` | Null or finite UTC epoch seconds in [0, 253402300799], boolean rejected |
| `model_version` | Nonempty string ≤100 identifying configured model pair |

Runtime allocates an event once then copies its scalar-only dictionary into each
subscriber queue. Mutation by one reader cannot alter another reader's event.
Maximum eight subscribers, 64 events per subscriber; overflow drops the oldest.
Unsubscribe releases its slot. Delivery is lossy best effort, with no durable log,
acknowledgements or replay. Snapshots are authoritative for current monitoring.
Never use these subscriptions for commands with side effects. No images,
embeddings, raw audio/transcripts or device paths appear in an event.

Synthetic example (not live patient data):

```json
{"schema_version":1,"event_id":"synthetic-example","kind":"confirmed","track_id":1,"person_id":"synthetic-person","timestamp":null,"model_version":"example-model"}
```

## Runtime and caregiver snapshots

`Runtime.dashboard_snapshot()` returns required top-level `schema_version: 1`,
`recognition`, `outdoor`, `indoor`, `health`. The caregiver adapter
`collect_snapshot()` validates/allowlists these and adds required boolean
`has_mock_data`. Unknown schema or malformed input fails closed. Public output is
always schema 1; no internal camera, model, storage or audio object is exposed.

Common section fields (all present after caregiver projection):

| Field | Type / rule |
| --- | --- |
| `status` | `live`, `unavailable`, `stale`, `paused`, `uncalibrated`, `no_fix`, `disconnected`, `invalid`, `mock`, `starting`; unknown becomes unavailable |
| `data_source` | `live`, `mock`, `unavailable`; invalid becomes unavailable; mock always forces visible mock state |
| `reason` | Machine code matching `[a-zA-Z0-9_:-]{1,64}`; invalid/missing uses bounded fallback |
| `observed_at` | Null or finite epoch seconds in [0, 253402300799]; timezone-qualified ISO input is accepted and normalized |
| `age_seconds` | Null or finite nonnegative numeric seconds; booleans rejected |
| `max_age_seconds` | Positive finite seconds ≤300; invalid/missing uses section default |

Live requires available evidence and known age strictly less than its expiry.
Age ≥expiry clears current personal data. Invalid/null/negative/nonfinite age
cannot be current. `ready` health means a component is available, not that a person
or location is currently known. Historical location is separately labeled.

Recognition adds `people`: list with at most four entries, each with required
strings `person_id` (≤100), `name` (≤100), `relationship` (≤150), `note` (≤500).
Entries require nonempty identity and name; invalid entries are dropped. Strings
are truncated at the allowlist boundary. Non-live/non-mock output has no people.
Runtime uses fixed one-second expiry. It confirms after three distinct consecutive
known observations, tracks explicit person recency up to ten seconds, and uses a
60-second automatic announcement cooldown. The public projection and automatic
speech enforce strict one-second expiry, even though tracker helpers internally
permit the endpoint. Tracker identity can remain recent for explicit requests
without becoming current on the caregiver screen.

Profile reads occur only in the recognition producer. It publishes at most four
verified field copies with their evidence times and Store revision. HTTP readers
attempt the runtime lock for at most 50ms, then copy this cache without SQLite,
camera, inference or speech calls. A changed Store revision invalidates cached
names until the next observation. Store failure/lock contention/paused enrollment
returns explicit unavailable/paused state; none invents live data. Each returned
person dictionary is a fresh copy.

Outdoor adds `latitude` (null or finite [-90,90]), `longitude` (null or finite
[-180,180]), `speed_mps` (null or finite nonnegative), `source` (bounded machine
code; GPSD producer uses `gpsd`), and `last_known` (null or historical fix).
Coordinates/speed are populated only for a valid live/mock fix. A malformed fix
sets invalid and clears current coordinates. `last_known` has `latitude`,
`longitude`, nullable `observed_at`/`age_seconds`, and fixed label
`Last known location`. Its existence does not make current status live.
Default GPS expiry is ten seconds, configurable positive up to 300. GPSD producer
also emits internal `schema_version`, `data_kind`, and unavailable `navigation`
route state; caregiver drops these internal extras. Complete TPV validity,
receiver/epoch consistency and duplicate/out-of-order handling belong to
NavigationService. Partial or repeated epochs do not renew current evidence.

Indoor only emits common fields. Its `status`, `reason` and `data_source` are
always overwritten to unavailable / not_integrated / unavailable by caregiver
projection. No destination, marker, route or guidance is inferred.

`health` is a dictionary of bounded machine codes, limited to `camera`,
`microphone`, `playback`, `model`, `storage`, `clock`, `runtime`, `gpsd`,
`navigation`. No raw exception messages are exposed.

Synthetic minimal producer example (not live hardware data):

```json
{"schema_version":1,"recognition":{"status":"live","reason":"current_observation","data_source":"live","observed_at":null,"age_seconds":0.2,"max_age_seconds":1,"people":[{"person_id":"synthetic-person","name":"Example person","relationship":"Example relationship","note":"Synthetic demonstration"}]},"outdoor":{"status":"unavailable","reason":"not_configured","data_source":"unavailable"},"indoor":{"status":"unavailable","reason":"not_integrated","data_source":"unavailable"},"health":{"camera":"ready"}}
```

## Speech and commands

Existing `AudioEngine.say(text, valid, priority)` returns accepted boolean. There
is one bounded queue of eight items, automatic priority 0, explicit response 1,
FIFO within equal priority and text deduplication. Higher priority queued work can
evict lower priority work; it does not preempt native synthesis. Microphone sample
queue capacity is 16. `valid()` is checked before enqueue, before synthesis and
on each playback block. Person-dependent speech rechecks active profile/version,
visibility (automatic) or existing ten-second recency (explicit), pause/enrollment
and cancellation generation. Profile edit/delete invalidates queued context.

Stop bypasses queue capacity, aborts output, increments generation and clears
pending work. During playback only stop commands are dispatched. Parser default
prefix is `Computer`, subject to selected Vosk vocabulary validation. Recognition
pause/resume/identify/context/history/repeat retain existing policies. There are
no route, emergency or indoor commands. Playback block size is approximately
50ms, not a measured end-to-end stop-latency guarantee.

AUX earphones require a suitable USB adapter; physical microphone and plug
compatibility are pending. The reported SIMA7670C/RS232 board has unverified
positioning capability. Navigation stays disabled until exact hardware and data
path are verified. Do not guess wiring, voltage, baud rate or AT commands.

## HTTP, lifecycle and privacy

Enrollment is loopback 127.0.0.1:8765. Dashboard backend is separate loopback
127.0.0.1:8766. GPSD defaults to local port 2947. Caddy exposes only dashboard
HTTPS 443 on the private LAN; enrollment is never proxied. Explicit host/origin
checks, loopback proxy peer, secure HttpOnly SameSite cookie, CSRF, CSP, no-store
responses and a fixed 15-minute session apply. Polling does not extend sessions.
Only proxy TLS scheme is trusted, not arbitrary forwarded host/IP. Waitress bounds
are set in `create_http_server`; inspect shipped configuration and version during
Pi qualification rather than assuming package defaults.

Connected browser polling is 500ms; failure retries are 5s, fetch abort is 4s,
requests do not overlap, rendering advances evidence age with the browser clock.
Authentication/network failures clear current personal data; successful HTTP does
not renew source evidence. Monitoring exposes no enrollment, audio, image or
control endpoint. SQLite, models, private configuration and secrets stay local;
state directory 0700, secret files 0600, service umask 0077.

Startup validates state/configuration and takes one state-directory process lock,
opens SQLite, binds all localhost servers, then starts runtime/device workers.
Core worker death stops the service group. Normal shutdown requests stop/cancels
speech, attempts each device owner even if another close fails, closes HTTP
channels/workers, joins workers and closes SQLite last. Remaining owners/requests
are failure, not clean shutdown; process supervision owns recovery. A stuck camera
reader cannot be replaced with a second owner. No native library changes occur
under a running process. Actual Pi shutdown timing remains an acceptance gate.

## Operator handoff

The [simple Pi runbook](../hardware/PI-RUNBOOK.md) is the ordered setup procedure.
[Validation](../VALIDATION.md) records software results and the remaining hardware
checks. #8 integration tests exercise available-module flows with labelled
synthetic inputs; they do not make those inputs real camera or receiver evidence.

## Evidence and extension rules

`tests/test_contracts.py` exercises stable/validated identity, subscriber isolation
and bounds, exact expiry, profile cache/revision invalidation, duplicate evidence,
slow inference, blocked producer with independent outdoor reads and failed-owner
cleanup. Existing runtime/audio/navigation/caregiver/CLI/Node suites cover policy
and lifecycle regressions. Software tests do not establish recognition accuracy,
Pi compatibility, live voice response or phone TLS trust. See
[validation](../VALIDATION.md) and [hardware plan](../hardware/ISSUE-7-PLAN.md).

Future indoor work needs approved shared-frame fan-out, evidence/expiry contracts,
caregiver schema handling and speech validity rules inside the existing output
owner. Do not add a second camera reader or speech arbitrator. Any cross-module
schema/interface change requires coordinated owner review; never claim owner
sign-off merely because this document exists.
