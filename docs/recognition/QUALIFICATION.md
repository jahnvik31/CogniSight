# Hardware acceptance record

Status: **NOT RUN on target hardware**. Read [validation](../VALIDATION.md) for
current software-test/build evidence; earlier development-host limitations are
not hardware results. Hardware ownership does not establish remote access or
prove compatibility. No Pi camera, microphone, GNSS or TTS pass is claimed.
Use the [Pi runbook](../hardware/PI-RUNBOOK.md) and save a separate inventory before
configured smoke; a native hang can prevent smoke reporting. Empty-scene capture
is not SFace feature execution, and feature execution is not identity accuracy.

## Release gates

Record setup identity, model hashes, locked dependencies and command results.
Measure on the Pi with networking disabled after installation:

| Test | Required result |
|---|---|
| Recognition appearance -> audible start | p95 <=3 s |
| Command end -> audible response | p95 <=2 s |
| Recognized stop -> silence | <=1 s |
| Commands | >=95% intents, >=20 trials per command per intended test speaker |
| Held-out known encounters | >=95% correct accepted identities; report rejects/wrong identities |
| Independent unknown encounters | >=300; zero named false accepts |
| Gallery | 100 entries; report number of real distinct identities evaluated |
| Continuous operation | 2 hours; no crashes, queue growth, sustained throttling |
| Combined module memory | peak <4 GB |
| Offline | no runtime downloads or network dependency |
| Faults | disconnect/reconnect camera+headset; no stale identity or redirected speech |

Use separate calibration and held-out evaluation sessions. Adjacent video frames
are not independent encounters. Report participant/session counts, lighting,
distance, head pose, glasses, motion, multiple faces, uncertainty and exclusions.
Test baseline distance 0.75–2 metres, then restrict the documented operating range
to actual passing conditions. Include unknown people who are not in enrollment.

Do not use enrollment captures as held-out tests. Obtain consent and avoid patient
records. A small known-person test does not certify a 100-person gallery. Zero
false accepts among 300 independent trials still permits roughly a 1% upper bound
at 95% confidence under an independent binomial model; real encounters may be
correlated. No liveness/authentication claim is made.

## Manual failure scenarios

1. Dark/bright/backlit scene, blurred motion, partial face, similar relatives.
2. Person changes at same image position; crosses another person; exits while
   speech is queued; returns during cooldown; remains motionless for minutes.
3. Spoken requests with intended wearer's accent, pauses and background speech.
   Play unrelated conversation and speech leaking from headset; no unintended
   identity request or self-loop may occur.
4. Stop while synthesizing and while playing; only stop actionable during output.
5. Remove microphone/output USB connection, reconnect with different enumeration.
6. Disable/edit/delete profile while a response is queued or playing.
7. Camera busy, disconnected, restart; malformed/missing/hash-mismatched model.
8. Storage unavailable/full; clock unsynchronized or moved backward; service reboot.
9. Concurrent enrollment clicks, cancellation, session expiration, browser close.
10. Full software suite with required dependencies, and actual phone login,
    logout, trusted TLS, expiry and source recovery; enrollment stays loopback.

Before marking #2 complete, attach the actual report and limitations, link
implementation PRs, and coordinate the updated fresh-implementation scope. Do not
close the issue based solely on unit tests.
