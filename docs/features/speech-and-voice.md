# Speech and voice commands

CogniSight speaks short sentences into the wearer's earphones (who is in front
of them, which room they are in, and the next step of a guided trip) and
listens for a small set of spoken commands such as "stop", "who is this?", and
"take me to the bathroom". Both directions run offline on the device through
one library, moonshine-voice, with a fallback to the `espeak-ng` voice and,
failing that, silence, so the rest of the system keeps working when audio is
missing.

The code is in `src/cognisight/voice.py` (speakers, the announcer, the listener,
and the command grammar) and `src/cognisight/runtime.py` (start-up, the
handling of heard commands, and the dashboard controls). The tests are in
`tests/test_voice.py` and `tests/test_signs.py`.

> **Hardware status.** Speech, listening, and Bluetooth audio have **not** been
> tested on the Raspberry Pi. The behaviour below is what the code does; audio
> quality, latency, and recognition accuracy on the Pi are unmeasured.

---

## 1. The speech library: moonshine-voice

`pyproject.toml` installs `moonshine-voice>=0.1.6` as the optional `voice`
extra (version 0.1.6 was installed in the development environment). It is one
open-source package that provides both:

- **Text-to-speech (TTS):** neural voices (the library offers Kokoro and Piper
  voices among others).
- **Speech-to-text (STT):** Moonshine streaming recognition from a microphone.

Both run entirely on the device. Models are downloaded once, during setup, by
`cognisight download` (section 1.3), after which no network connection is
needed for speech.

### 1.1 The voice

`MoonshineSpeaker` builds the voice as:

```python
TextToSpeech().language("en_us")      # no voice is named
```

CogniSight does not choose a voice itself; the library's default voice for
`en_us` is used. In the installed library that default is the Kokoro voice
**`af_heart`**: it is the voice file (`kokoro/voices/af_heart.kokorovoice`) that
`cognisight download` placed in the library's cache on the development machine.
`load_speaker()` accepts a `voice` argument, but nothing in the program passes
one, and there is no command-line option for it.

### 1.2 The fallback chain

`load_speaker()` returns the best speaker that works here and **never raises**:

| Order | Speaker | When it is used | What the Device page shows |
|---|---|---|---|
| 1 | `MoonshineSpeaker` | The library imports and the voice loads. | Speech available, no error. |
| 2 | `EspeakSpeaker` | Moonshine failed (missing library, no audio device, download failure) and an `espeak-ng` (or `espeak`) program is on the `PATH`. It runs `espeak-ng -s 150 "<text>"` (150 words per minute) as a separate process. | Speech available, with the note "Using espeak-ng because Moonshine: …". |
| 3 | `NullSpeaker` | Neither of the above works. It accepts sentences and does nothing. | "Speech isn't available. Moonshine: …; espeak-ng: …" |

`setup.sh` installs `espeak-ng` from apt so that step 2 is normally available.

Until speech has loaded, the announcer uses a `NullSpeaker` with the message
"Loading speech…". Speech is loaded only after face recognition (TensorFlow)
has finished loading, or after 180 seconds, whichever comes first, because
importing two large libraries at the same time on the Pi was judged slow and
fragile (see [ARCHITECTURE.md](../ARCHITECTURE.md)).

### 1.3 Model downloads

`cognisight download` (run by `setup.sh`) calls `download_voice_models()`,
which loads the `en_us` TTS voice and the **tiny** streaming STT model once and
closes them, so they are cached for offline use. If this fails, the command
prints "Speech models could not be downloaded: …" and "CogniSight will still
run; speech will use espeak-ng or stay off." The moonshine-voice models are
kept in the library's own per-user cache, not in the repository. Only the tiny
model is pre-downloaded; the `small` and `medium` listening models (section 5)
are not.

---

## 2. The announcer

`Announcer` (in `voice.py`) sits between the rest of the program and the
speaker. Every sentence the device says passes through `Announcer.say()`:

1. If speech is turned off (`enabled` is false), nothing happens.
2. The sentence is handed to the speaker. If the speaker raises (for example,
   Bluetooth earphones disconnected), the error is stored as "Could not play
   speech: …" and shown on the dashboard; it is not raised further.
3. If the speaker is a `NullSpeaker`, nothing was heard, so nothing is reported
   as said.
4. Otherwise the sentence is reported: it becomes the `said` value in
   `GET /api/live` (shown as the subtitle under the camera picture) and a
   `said` event on the Live page timeline.

The rule "only report what was actually played" means the subtitles never show
words the wearer did not hear.

---

## 3. Introductions

### 3.1 Wording

`introduction(name, relationship)` builds the sentence. Whitespace in the
relationship is collapsed first.

| Relationship stored | Sentence | Rule |
|---|---|---|
| *(empty)* | "This is Priya." | No relationship: name only. |
| `daughter` | "This is Priya, your daughter." | A bare noun gets "your". |
| `my neighbour` | "This is Ravi, your neighbour." | "my" is changed to "your", because the caregiver writes from their own point of view but the sentence is spoken to the wearer. |
| `your carer` | "This is Asha, your carer." | Already addressed to the wearer: kept. |
| `the family doctor` | "This is Dr Rao, the family doctor." | Starts with "the", "a", or "an": kept as written. |

The prefixes are checked case-insensitively, followed by a space.

### 3.2 When a person is introduced: 120 seconds out of view

The recognition loop calls `Announcer.seen(name, relationship)` for every
recognised face on every pass (at most twice a second). The announcer speaks
**the moment a person is first recognised**, and introduces them again only
after they have been **out of view for `COOLDOWN_SECONDS = 120` seconds**:

- For each person the announcer remembers the time they were last recognised
  while speech could be heard. **Every** sighting updates that time, so the
  120-second timer restarts each time the person is seen.
- A person is introduced when the gap since that previous sighting is 120
  seconds or more (or there was no previous sighting). Someone who stays in
  view, and so is recognised every half second, is introduced **once**, however
  long they stay (tested by `test_someone_who_stays_in_view_is_introduced_once`,
  which simulates ten minutes). Someone who leaves and comes back after two
  minutes or more is introduced again
  (`test_speaks_at_once_and_again_only_after_two_minutes_away`).
- The timer is kept **per person**. Seeing Ravi does not affect Priya.
- It is measured with a monotonic clock, so changes to the system clock do not
  affect it.
- **Nothing is recorded while speech cannot be heard.** `Announcer.can_speak()`
  is false when speech is turned off or when the current speaker is not
  available (for example, the silent placeholder used while speech is still
  loading after start-up). In that case `seen()` returns at once without
  updating the timer. So a person recognised before speech has loaded is
  introduced as soon as it has (`test_not_lost_while_speech_is_still_loading`),
  and a person in view while speech is turned off is introduced when it is
  turned back on (`test_muted_says_nothing_and_introduces_after_unmute`).

"Out of view" here means "not recognised". A person who stays in the room but
is not recognised for two minutes (turned away from the camera, or in poor
light) is introduced again when next recognised.

This replaced an earlier design that waited for three matching frames in a row
before speaking, which made the device seem to hesitate. Speaking on the first
confident match, with a strict distance cutoff (see
[face recognition](face-recognition.md#43-the-cutoff)), is the current
approach. Not repeating introductions while someone stays with the wearer is
the main way the device avoids being intrusive.

---

## 4. Queueing

With moonshine-voice, `say()` **queues** the sentence and returns immediately.
The library splits long text at sentence boundaries, synthesises the next
sentence while the current one plays, and plays them strictly in order. This is
why the code comments "Queued, so a direction never cuts off an introduction":
if the wearer walks up to a sign while being introduced to someone, they hear
the introduction and then the direction.

`Announcer.stop()` calls the library's `stop()`, which halts the sentence being
played and drops everything still queued. It is used by the "stop" command and
when speech is turned off from the dashboard.

The espeak-ng fallback does **not** queue: `EspeakSpeaker.say()` first stops
any sentence still playing and then starts the new one. With the fallback
voice, a new sentence therefore cuts off the previous one.

Several sentences are combined into one `say()` call in two places: "who is
this?" with two known people in view joins both introductions, and "tell me
more" joins every note.

---

## 5. Listening

`Listener` wraps the library's `MicTranscriber`:

```python
MicTranscriber().language("en").model_arch(ModelArch.TINY_STREAMING)
```

- It listens on the system's **default microphone**.
- The model is chosen with `--listen-model`: `tiny` (the default), `small`, or
  `medium`, mapped to the library's streaming model architectures. An
  unrecognised value falls back to tiny. The tiny model is noted in the
  project overview as about 34 million parameters.
- The library calls back **once per finished line** of speech (a
  `LineCompleted` event), not for partial words. CogniSight's handler,
  `Runtime._on_heard(text)`, runs on the library's own thread.
- Listening is started after speech has loaded, unless `--no-listen` was given.
  When it starts, the timeline shows "Listening for “stop” and “who is this”".

Only the recognised text is used. No audio is recorded or stored. Lines that do
not match any command are ignored and are not logged.

---

## 6. The command grammar

### 6.1 Normalisation

`parse_command(text)` lower-cases the line, changes curly apostrophes (’) to
straight ones ('), and collapses whitespace. It then tries four regular
expressions **in this order** and returns the first that matches anywhere in
the line (all patterns are bounded by word boundaries, `\b`):

| Order | Command | Pattern (from `voice.py`) | Example phrases |
|---|---|---|---|
| 1 | `stop` | `stop`, `quiet`, `shush`, `enough`, `silence`, `cancel` | "Stop.", "okay be quiet", "that's enough" |
| 2 | `go` | `take me to`, `where's`, `where is`, `where are`, `how do i get to`, `go to`, `want to go`, `need to go`, `need the`, `find the`, `show me the`, `way to` | "take me to the bathroom", "where's the kitchen?", "I need the toilet" |
| 3 | `more` | `tell me more`, `more about`, `who is he again`, `who is she again`, `who is they again` | "tell me more", "who is she again?" |
| 4 | `who` | `who's this/that/it/here`, `who is this/that/it/here`, `who am i talking to`, `who am i speaking to`, `say that again`, `say it again`, `repeat` | "who is this?", "who's that", "say that again" |

Because the order matters, "stop" wins over everything: "who is this, stop"
is a stop command. Anything else returns `None`. The device's own sentences,
such as "This is Priya, your daughter.", do not match any pattern (tested).

### 6.2 "Where am I?"

"where am i" is not one of the four patterns. `Runtime._on_heard` checks for it
separately (the lower-cased line contains `where am i`) when no pattern
matched. It is answered from the signposts navigator (see
[Talking signposts](signposts.md)):

- If a sign was read within the last **300 seconds** (5 minutes), the device
  says "You're in the kitchen." (using the room-name wording rule in section
  6.4).
- Otherwise it says "I'm not sure. Look around for a sign on the wall."

### 6.3 What each command does

`Runtime._on_heard` first checks whether the device is **talking at that
moment** (the speaker's `is_talking()`; if that check fails, the device is
assumed not to be talking). While it is talking, **every phrase except "stop"
is ignored**, and is not logged. The reason, given in the code comment: over a
loudspeaker, the microphone hears the device itself, and a sentence such as
"Let's go to the bathroom. …" contains "go to" and a room name and would
otherwise sound like a request to start a trip. "stop" is always accepted so
the wearer can still cut speech off. Otherwise the line is dispatched:

| Command | Action |
|---|---|
| `stop` | Stops speech at once (the current sentence and the queue). If a guided trip is in progress, the trip is ended and the timeline records "Stopped guiding when asked". Nothing is said. |
| `who` | Introduces **every** recognised person currently in view, in one sentence each ("This is Priya, your daughter. This is Ravi, your neighbour."). If no one known is in view: "I don't see anyone I know right now." This repeats an introduction regardless of the 120-second rule in section 3.2. |
| `more` | Reads the notes of everyone known who is in view ("Visits on Sundays."). If none of them has a note, it introduces the first of them. If no one known is in view: "I don't see anyone I know right now." |
| `go` | Finds the room named in the line and starts a guided trip there (6.4). |
| "where am I" | Answers as in 6.2. |

After a recognised command, the line is stored as the "last heard" text (shown
on the Device page) and a `heard` event "Heard “take me to the bathroom”" is
added to the timeline.

The "in view" list comes from the most recent recognition pass, so it reflects
the camera picture at most about half a second old (more if recognition is
slow on the Pi).

### 6.4 How "go" finds a room

`SignStore.find_destination(text)` (in `signs.py`) looks for a sign whose
**name or any of its aliases** appears in the line as whole words:

1. The spoken line is lower-cased, curly apostrophes become straight, every
   character other than `a–z`, `0–9`, apostrophe, and space becomes a space,
   and whitespace is collapsed.
2. Each sign's name and each alias is cleaned the same way.
3. A term matches if it appears in the line bounded by spaces or the ends of
   the line, so "hall" does not match inside "hallway".
4. If several terms match, the **longest** one wins. For example, with signs
   "Room" and "TV room", "take me to the TV room" chooses "TV room".

Examples from the tests, with a Bathroom sign whose aliases are "toilet" and
"washroom":

| Heard | Result |
|---|---|
| "take me to the toilet please" | Bathroom (alias match) |
| "Where's the kitchen?" | Kitchen |
| "take me to the garden" | No match |

If a sign is found, a trip is started exactly as when the caregiver presses
"Start guiding" (see [Talking signposts](signposts.md#7-trips)). If none is
found, the device says "I don't know that room. I know Bathroom, Bedroom,
Hallway." listing up to **six** sign names in alphabetical order, or "I don't
know any rooms yet." when there are no signs.

Room names in sentences use the rule in `the()` (in `signs.py`): "Kitchen"
becomes "the kitchen", "TV room" becomes "the TV room" (the capital is kept
because the next letter is also a capital), and names that start with "the",
"my", "your", or a possessive such as "Priya's room" are kept as written.

---

## 7. When audio or the microphone is missing

Nothing about audio can stop the rest of CogniSight from running:

| Situation | What happens |
|---|---|
| moonshine-voice not installed, or its voice fails to load | espeak-ng is used if installed; otherwise speech is silently off. The Device page explains why. |
| No audio output device, or Bluetooth earphones disconnect while speaking | The speaker raises; the announcer stores "Could not play speech: …", which appears on the Live and Device pages. Recognition and guidance continue. |
| No microphone | Starting the listener fails; the Device page shows "Listening unavailable: …" and the Listening card reads "Not available". The **Turn listening on** button stays enabled, so after plugging in a microphone the caregiver can press it to try opening the microphone again, without restarting. |
| `--no-speech` | The device starts with speech turned off; it can be turned on from the dashboard. |
| `--no-listen` | The listener is never created. The Device page shows "Listening is off." |

---

## 8. Bluetooth earphones

CogniSight does not talk to Bluetooth directly. Both moonshine-voice and
espeak-ng play to the **system's default audio output**. Once Bluetooth
earphones are paired and chosen as the output (on Raspberry Pi OS: the
Bluetooth icon to pair, then right-click the speaker icon to choose the
output), every sentence goes to them. Two practical points follow:

- The README warns that microphones in Bluetooth earphones are unreliable on
  the Pi and recommends a USB microphone for voice commands.
- The Raspberry Pi 5 has no 3.5 mm audio socket, so wired earphones would need
  a USB audio adapter or another output; the setup instructions assume
  Bluetooth earphones or a speaker.

None of this has been tested on the Pi. The optional systemd service in
`deploy/cognisight.service` starts after `sound.target` and `pipewire.service`
so that audio is up before CogniSight starts.

---

## 9. Dashboard controls

| Where | Control | Effect |
|---|---|---|
| Live page, "Speech to the earphones" | **Turn speech off / on** | `POST /api/speech`. Turning speech off also stops anything playing. The line under the heading reads "On. CogniSight says who it sees into their earphones." or "Off. CogniSight stays quiet until you turn speech back on." The button is disabled while speech is not available. |
| Live page | **Test speech** | `POST /api/speech/test` with no text. The device says "Hello. CogniSight speech is working." even if speech is turned off (it is turned on only for that sentence). If speech is not available, the API answers 503 with the reason and the page shows "The test didn't play. …". |
| Device page, Speech card | Turn speech on/off | Same as on the Live page; shows "On", "Off", or "Not available", and any error. |
| Device page, Listening card | Turn listening on/off | `POST /api/listening`. Shows "Last heard: “who is this”, 2 min ago". The button is enabled even when listening is "Not available", so pressing it retries opening the microphone. |
| Live page subtitle strip | (display) | Shows the last sentence spoken for 20 seconds; see [Caregiver dashboard](caregiver-dashboard.md#6-the-subtitle-strip). |

The API also accepts a custom test sentence (`{"text": "..."}`, cut to 200
characters), which the dashboard does not use.

---

## 10. Everything the device can say

| Sentence | When |
|---|---|
| "This is Priya." / "This is Priya, your daughter." / "This is Dr Rao, the family doctor." | A known person is recognised for the first time, or after not being recognised for 120 seconds or more (section 3). |
| "This is Priya, your daughter. This is Ravi, your neighbour." | The wearer asks "who is this?" with known people in view. |
| "Visits on Sundays." (the caregiver's note) | The wearer asks "tell me more" and a person in view has a note. |
| "I don't see anyone I know right now." | "who is this?" or "tell me more" with no known person in view. |
| "This is the kitchen." | No trip is in progress and a sign is read for the first time, or after not being read for 120 seconds or more, provided it was not announced in the last 120 seconds. |
| "This is the kitchen. Tea is by the window." | As above, when the sign has a note and "Say the note when they arrive" is ticked. |
| "Let's go to the bathroom. Look around for a sign on the wall." | A trip starts and no sign has been read in the last 120 seconds. |
| *The caregiver's direction*, e.g. "The bathroom is the second door on your right." | During a trip, at each sign on the way; repeated if the wearer is still in front of the same sign after 30 seconds. |
| "You're at the bathroom." | During a trip, when the destination's sign is read. |
| "I don't know the way to the kitchen from here." | During a trip, at a sign with no written route to the destination. |
| "You're in the hallway." | "where am I?" with a sign read in the last 5 minutes. |
| "I'm not sure. Look around for a sign on the wall." | "where am I?" otherwise. |
| "I don't know that room. I know Bathroom, Bedroom, Hallway." | A "go" request naming no known room (up to six names listed). |
| "I don't know any rooms yet." | A "go" request when no signs exist. |
| "Hello. CogniSight speech is working." | The caregiver presses **Test speech**. |

The sign-related sentences are explained in [Talking signposts](signposts.md).

## 11. Everything the device understands

| Phrase (any phrase containing…) | Command |
|---|---|
| stop, quiet, shush, enough, silence, cancel | stop |
| take me to, where's, where is, where are, how do I get to, go to, want to go, need to go, need the, find the, show me the, way to | go (a room name or alias must also be in the phrase) |
| tell me more, more about, who is he/she/they again | more |
| who's / who is + this / that / it / here, who am I talking to, who am I speaking to, say that again, say it again, repeat | who |
| where am I | where am I |

---

## 12. Limitations

- **Untested on the Pi**, including Bluetooth output, microphone input, and the
  speed of the neural voice.
- **Commands are ignored while the device is talking**, except "stop" (section
  6.3). This protects against the device hearing itself through a loudspeaker,
  but the wearer has to wait until a sentence has finished before asking
  something else. The check is made when a line of speech has been
  transcribed; whether transcription of the device's own last words can finish
  after playback has ended (and so slip through) has not been tested.
- **Any "where is …" question is treated as a room request.** "Where is Priya?"
  is answered "I don't know that room. I know …".
- **English only.** Both the STT language (`en`) and the TTS language
  (`en_us`) are fixed. Room names and aliases are matched only on the letters
  a–z and digits, so names written in other scripts cannot be requested by
  voice.
- **"Out of view" means "not recognised".** A person who stays nearby but is
  not recognised for two minutes is introduced again when next recognised
  (section 3.2).
- **The espeak-ng fallback interrupts itself** rather than queueing.
