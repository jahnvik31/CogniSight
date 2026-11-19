# The caregiver dashboard

The caregiver dashboard is a web application, served by the device itself,
that family members and carers open on a phone or computer on the same Wi-Fi
network, or on a monitor attached to the Pi. It shows the live camera picture
with names drawn on faces, subtitles of exactly what the wearer just heard, who
is with them, which room they are in, and a timeline of the day; and it is
where the caregiver adds people, puts up and links talking signs, draws the
floor plan, checks the device's approximate location, and checks that every
part of the device is working.

The source is in `web/` (SolidJS). The device's HTTP API, which the dashboard
uses for everything, is described in [docs/API.md](../API.md) and summarised in
[ARCHITECTURE.md](../ARCHITECTURE.md).

> **Hardware status.** The dashboard has not been used against the Raspberry
> Pi. It was used against the program running on a Windows laptop with a USB
> webcam.

---

## 1. Technology and build

| Part | Choice (from `web/package.json`) |
|---|---|
| UI library | SolidJS `^1.9.9` (chosen, according to the project overview, because it is fast on phones; it updates only the parts of the page whose data changed, without a virtual DOM) |
| Routing | `@solidjs/router` `^0.15.3` |
| Build tool | Vite `^6.3.5` with `vite-plugin-solid` |
| Maps | Leaflet `^1.9.4`, with OpenStreetMap tiles (Place page only) |
| Font | `@fontsource-variable/atkinson-hyperlegible-next` `^5.3.0`, bundled into the build |

### 1.1 The built app is committed

`npm run build` writes the finished app to `web/dist/`: one `index.html`, one
JavaScript bundle, one CSS file, and the two font files (Latin and Latin
Extended, as WOFF2). **`web/dist` is committed to the repository on purpose**
(the `.gitignore` explicitly re-includes it), so the Raspberry Pi needs no
Node.js, npm, or build step: `cognisight start` serves the files directly.
If `web/dist/index.html` is missing, the program prints "The dashboard is not
built (web/dist is missing). The API still runs." and serves only the API.

After changing the dashboard source, a developer runs `cd web && npm install
&& npm run build` and commits `web/dist`. During development, `npm run dev`
starts Vite on port 5173 and forwards `/api` and `/stream.mjpg` to the device
program on `http://127.0.0.1:8765`. The automated check on GitHub
(`.github/workflows/software-checks.yml`) builds the dashboard with Node 22 to
confirm the source builds; it does not check that the committed `web/dist`
matches the source.

### 1.2 How the device serves it

Flask serves any file that exists under `web/dist` (after checking that the
resolved path is inside that folder). Every other path that does not start
with `/api/` returns `index.html` with `Cache-Control: no-cache`, so a deep
link such as `/people/Priya` loads the app, which then shows the right page.
Unknown `/api/...` paths return the JSON error "No such API route." (404).

The font is served from the device, so the dashboard makes no requests to font
services. The only third-party requests the browser makes are for map tiles on
the Place page (section 4.7).

---

## 2. Routes

| Path | Page | Tab |
|---|---|---|
| `/` | Live | Live |
| `/people` | People (`?add=1` opens "Add a person") | People |
| `/people/:name` | Person | People |
| `/home` | Home: signs and floor plan (`?add=1` opens "Add a sign") | Home |
| `/home/signs/:id` | Sign | Home |
| `/home/print` | Print signs (`?ids=1,3` limits it to those signs) | Home |
| `/place` | Place: room at home and the map | Place |
| `/device` | Device status and controls | Device |
| anything else | "There's no page here" with a link back to Live | — |

Each page sets the browser tab title to "<Page> – CogniSight" (for example
"Priya – CogniSight").

---

## 3. The application shell

`web/src/App.jsx` wraps every page:

- **Navigation.** Five tabs: Live, People, Home, Place, Device, each with an
  icon and a label. On wide screens they form a left-hand rail under the
  "CogniSight" wordmark; on phones they move to the bottom (section 9). The
  current tab is marked with `aria-current` ("page" for the exact page, "true"
  for a page inside that section, such as a person's page under People) and a
  soft green background.
- **Device state.** Under the wordmark, a dot and a word summarise the device:
  green "Camera on", marigold "Camera off", "Connecting…" before the first
  answer, or "Not connected" when the device cannot be reached. It comes from
  the shared `/api/status` poll (every 3 seconds), which the Live and Device
  pages also use.
- **Offline banner.** A sticky slot at the top of the content (section 8).
- **Skip link** and **focus management** (section 10).

---

## 4. Pages

### 4.1 Live (`/`)

The page a caregiver leaves open. Heading "Live", with the line "What
CogniSight sees and says, as it happens." and, when anyone is recognised, "2
people recognised right now."

**Left column**

- **The camera picture** (section 7), with "Live" and a pulsing dot in the
  corner while frames arrive. The device draws the boxes and names: green for
  known people, orange "Unknown" for others, and blue outlines for signs.
- **The subtitle strip** over the bottom edge of the picture (section 6).
- **Sign chip**: "Sign in view: Hallway" while a saved sign is in the picture.
- **"Speech to the earphones"**: the current state ("On. CogniSight says who
  it sees into their earphones." / "Off. CogniSight stays quiet until you turn
  speech back on." / "Speech isn't available. …"), a **Turn speech off/on**
  button, and **Test speech**. See
  [speech-and-voice.md](speech-and-voice.md#9-dashboard-controls).

**Right column**

- **"With them now"**:
  - the room line, "In the hallway", or after 120 seconds without a sign,
    "Last seen in the hallway, 4 min ago";
  - each recognised person with their first photo (or initial), their name as
    a link to their page, and their relationship (or "Recognised");
  - "Someone they don't know" (or "2 people they don't know") with "Should
    CogniSight know them? Add a person";
  - "No one in view" when there are no faces, or "The camera is off, so
    CogniSight can't see who is there.";
  - a warning "Recognition last updated 20 sec ago. If this continues, check
    the Device page." when the camera is on but the last recognition pass is
    more than 15 seconds old.
- **The guide card**: "Guide them to a room" with a room selector and **Start
  guiding** (needs at least two signs; otherwise "Put up at least two signs,
  with directions between them, to guide them from room to room. Go to
  Home"). During a trip it shows the route as steps (reached / next / to do),
  "They've reached the bathroom." on arrival, "Last said: “…”", "Started 1 min
  ago", and **Stop guiding**. See [signposts.md](signposts.md#9-what-the-caregiver-sees).
- **"Today"**: the timeline of events from `/api/events` (the newest 50),
  newest first, split into today (after local midnight, converted to the
  device's clock) and "Earlier". Each row has a marker, the text, and a
  relative time ("3 min ago") with the exact time as a tooltip. Event kinds are
  labelled for screen readers as "Recognised", "Unknown face", "Said to them",
  "Heard a command", "Moved room", "Guiding", and "Device". With no events:
  "Nothing yet today. When CogniSight recognises someone, reads a sign, or
  speaks to them, it shows up here."

### 4.2 People (`/people`)

"Everyone CogniSight can introduce. 3 people saved." A grid of tiles, one per
person: first photo (or a large initial), name, relationship (or "No
relationship added"), and "Last seen 5 min ago" or "Not seen yet". With nobody
saved, an empty state invites "Add the first person they should recognise"
("Start with the people they see most: family, carers, close neighbours. One
clear photo is enough to begin.").

**Add a person** (opened with the button or `?add=1`):

- **Name** (required, up to 80 characters): "The name CogniSight says, such as
  Priya." Leaving it empty shows "Enter their name. It's what CogniSight will
  say when it sees them."
- **Relationship** (optional, up to 80): "Who they are to them: daughter,
  neighbour, carer."
- **Note** (optional, up to 500): "Anything worth remembering, such as “Visits
  on Sundays.”"
- **Photo**: either **Take photo with the device camera** ("They look at
  CogniSight while you press the button."), which shows a small live camera
  picture for lining up, or **Upload a photo** ("A clear, recent photo where
  their face fills most of the picture."), with **Take photo with this phone**
  (touch screens only; opens the phone's front camera) and **Choose a photo**,
  and a preview.
- While saving: "Hold still. The device is taking a photo and checking for a
  face…" or "Saving and checking the photo for a face…". The request is given
  60 seconds, because capturing and checking for a face can be slow on the Pi.
- On success the browser goes to the new person's page, which shows "Priya is
  saved. CogniSight will introduce them when they come into view." On a
  duplicate name the error is followed by a link "Open Priya". A photo with no
  face shows the device's message, "No face was found in that photo. Use a
  clear, well-lit photo facing the camera."

How the device stores and checks photos is in
[face-recognition.md](face-recognition.md#2-enrolment-adding-a-person-or-a-photo).

### 4.3 Person (`/people/:name`)

- A back link "All people"; the person's photo, name, relationship, and "Last
  seen 2 min ago" or "Not seen by the camera yet".
- **Photos**: "3–5 photos from slightly different angles make recognition
  steadier.", with a warning when there are fewer than three, a grid of photos
  each with **Delete photo** (asking "Delete their only photo? CogniSight
  won't recognise them until you add another." for the last one), and **Add a
  photo**: open the device camera and **Take photo**, **Take photo with this
  phone**, or **Upload a photo**.
- **Details**: relationship and note, with **Save changes** enabled only when
  something has changed.
- **Remove Priya**: "CogniSight will stop recognising them." **Delete Priya**
  asks "Delete Priya and 3 photos? This can't be undone." in place before
  deleting, then returns to the People page.
- If the name does not exist: "No one called Priya is saved".

### 4.4 Home (`/home`)

"Talking signs beside the doors. When the camera reads one, they hear which
room they're in." followed by the current room.

- **Add a sign**: room name (up to 40 characters, the device's limit), other
  names separated by commas ("toilet, washroom"),
  and a note ("Something to remind them here, such as “Your room is the blue
  door.”"). After saving: "Kitchen is sign 3. Print it, then tap the plan
  beside its door to place it.", and the floor plan switches to placing that
  sign.
- **Print signs** opens the print page for all signs.
- **Floor plan**: the editor described in
  [signposts.md](signposts.md#11-the-floor-plan-editor).
- **Signs**: each sign with its marker, a link to its page, "In view now" /
  "Last seen …" / "Not seen yet", and "2 ways out" / "No ways out yet". The
  sign in view and the sign of the current room are highlighted.

### 4.5 Sign (`/home/signs/:id`)

- The marker and name, "Sign 3 · Last seen 4 min ago".
- **Details**: name, a preview "Said on arrival: “This is the kitchen. Tea is
  by the window.”" that updates as the caregiver types, the note, the checkbox
  **Say the note when they arrive**, and other names.
- **Ways from this sign**: one row per direction ("To" and "Directions", up to
  240 characters; the name box on this page takes up to 40, matching the
  device), with
  the way back shown under each, **Add a way**, and **Save directions**. See
  [signposts.md](signposts.md#4-links-one-sentence-for-someone-standing-at-the-sign).
- **The printed sign**: a 200-pixel preview of the marker and **Print this
  sign**.
- **Remove this sign**: "Its directions and its place on the floor plan are
  removed too."

### 4.6 Print signs (`/home/print`)

One A4 sheet per sign, previewed on screen, with **Print**. Instructions: print
at 100 % size, not "fit to page", on plain white paper, without glossy
lamination. The sheet format is in
[signposts.md](signposts.md#10-the-printed-sign).

### 4.7 Place (`/place`)

"Where they are: the room at home, and the device's position on the map."

- **At home**: "In the kitchen since 2:14 pm", a note when the last sign was
  read more than 120 seconds ago, and up to eight of today's room changes with
  their times. With no sign seen: "No sign seen yet. Put up signs from the Home
  page."
- **On the map**: a Leaflet map with OpenStreetMap tiles, a dot at the
  estimated position, and a shaded circle whose radius is the reported
  accuracy; a sentence saying how the position was found (from Wi-Fi, or only
  from the internet connection, "a rough area, about 5.4 km wide", with a
  different explanation depending on whether Google was sent too few access
  points or could not match the ones it was sent); the
  coordinates to five decimal places, the accuracy, when it was checked, a
  link "Open in OpenStreetMap", and **Check again**. When location is not set
  up, the page shows three steps to add the key. Details are in
  [location.md](location.md#6-the-place-page).

### 4.8 Device (`/device`)

- A one-line summary: "Everything CogniSight needs is running." or "Needs
  attention: the camera, recognition and speech."
- **Open this dashboard on a phone**: the addresses reported by the device,
  for example `cognisight.local:8765` and `192.168.1.20:8765`.
- Status cards:

| Card | Shows |
|---|---|
| Camera | "Running" / "Not running", the camera name and type (for example "imx219 using picamera2"), and the error, or "Check the ribbon cable and restart CogniSight." |
| Recognition | "Running" / "Not running", model, face detector, match cutoff (0.30), seconds per check, and any error. |
| Speech | "On" / "Off" / "Not available", any error, and a toggle. |
| Listening | "On" / "Off" / "Not available", "Last heard: “who is this”, 2 min ago", any error, and a toggle. The toggle is enabled even when listening is "Not available" (it is disabled only while offline or while a change is in progress), so a microphone plugged in later can be tried again without restarting. |
| People | Number of people saved, with "Manage people". |
| Running for | Uptime ("2 hr 14 min") and the device name. |

The status API also reports the signs subsystem (`signs.ok`, `count`,
`error`), but the Device page does not show it.

---

## 5. Polling and pausing

The dashboard does not use WebSockets. Every page keeps its data fresh by
polling the API with `usePoll(fetcher, interval)` (in `web/src/lib.js`):

| Page | What is polled | Interval |
|---|---|---|
| Every page (shell) | `/api/status` | 3 s |
| Live | `/api/live` | 1 s |
| Live | `/api/events?limit=50` | 2 s |
| Live | `/api/home` (signs for the guide card) | 10 s |
| Live | `/api/people` (photos for avatars) | 30 s |
| People, Person | `/api/people` | 10 s |
| Home | `/api/home` | 4 s |
| Home | `/api/live` (signs in view, room, trip) | 1.5 s |
| Sign | `/api/home` | 5 s |
| Print signs | `/api/home` | 30 s |
| Place | `/api/location` | 60 s |
| Place ("At home") | `/api/home` | 5 s |
| Place ("At home") | `/api/events?limit=200` | 15 s |
| Device | uses the shell's `/api/status` poll | 3 s |

`usePoll` has four properties:

- **No overlapping requests.** The next request is scheduled only after the
  previous one has finished; if a refresh is requested while one is in flight,
  it runs once straight after.
- **Paused while the tab is hidden.** When the browser reports the page as
  hidden (another tab, a locked phone), the timer is cleared and no requests
  are made. When the page becomes visible again, it fetches immediately. This
  saves the phone's battery and the Pi's CPU.
- **Keeps the last good data** when a request fails, and exposes the error
  separately, so a brief network drop does not blank the page.
- **Optimistic updates.** After an action, the page replaces its copy of the
  data with the device's reply (`mutate`) and then refreshes.

Relative times ("2 min ago") are recomputed by a separate clock that ticks
every 1–15 seconds depending on the page.

### 5.1 Clock correction

All times from the device are Unix seconds on the device's clock. If the
phone's clock is wrong, "2 min ago" would be wrong too. Every API response
carries an HTTP `Date` header; the dashboard compares it with the browser's
clock and, if they differ by more than 2 seconds, adds that difference to all
"now" calculations (`deviceNow()` in `web/src/api.js`). Differences of 2
seconds or less are ignored because the header has only whole seconds.

---

## 6. The subtitle strip

The strip under the camera picture shows **exactly what the wearer last
heard**, so a caregiver watching remotely knows what the device said. It
reads the `said` field of `/api/live` (`{"text", "at"}`), which the device sets
only when a sentence was actually handed to a working speaker.

- The sentence is shown in quotation marks in large type (1.125–1.5 rem,
  scaling with the screen), with "Said to them just now" underneath.
- It stays for **20 seconds** (`CAPTION_SECONDS`) after the sentence was said,
  then fades out over 0.6 seconds instead of vanishing. The last sentence is
  remembered so it can fade.
- It is hidden while the device is offline.
- The strip is dark on light (`--caption-bg` `#1F2A2E`, text `#F3F5F2`) in the
  light theme and inverted in the dark theme, with a 5-pixel ring of page
  colour so it stands out over the picture.
- The visual strip is hidden from screen readers; a separate visually hidden
  `aria-live="polite"` region announces "Said to them: …" instead.

---

## 7. The camera stream

### 7.1 MJPEG

`GET /stream.mjpg` is a Motion-JPEG stream: one HTTP response of type
`multipart/x-mixed-replace; boundary=frame` in which each part is one JPEG
image (quality 80) with the boxes and names already drawn by the device. The
browser shows it with an ordinary `<img>` element, so no video player or
JavaScript decoder is needed and it works on every phone browser. The device
sends a frame each time the camera produces a new one (the Pi camera is
configured for 15 frames per second at 640 × 480); a client that is slower
simply misses frames. The response has `Cache-Control: no-store`. If the
camera is not running, the request returns 503.

### 7.2 Connection and retry (`web/src/Camera.jsx`)

- The image URL is `/stream.mjpg?t=<timestamp>`; changing the timestamp forces
  a fresh connection.
- The component tracks three states: **loading** (waiting for the first
  frame), **ok**, and **error**. Because some browsers never fire a `load`
  event for MJPEG, it also checks every second whether a frame has been
  decoded (`naturalWidth > 0`).
- On **error**, it retries **every 5 seconds** and shows "The camera isn't
  running. Check the ribbon cable and restart CogniSight. Trying again every 5
  seconds."
- It reconnects at once when the device reports the camera has come back,
  when the device becomes reachable again after being offline, and when the
  tab becomes visible again.
- While the tab is hidden, the `<img>` is removed from the page, which closes
  the stream, so a phone in a pocket does not keep downloading frames.
- The frame keeps the camera's aspect ratio (from `/api/live`'s `frame` width
  and height, or 4:3 until known). Messages for each state: "Connecting to the
  camera…", "Waiting for the device. The picture comes back on its own when
  the device can be reached again.", and the camera message above.

The same component, in a compact size, is used to line up enrolment photos.

---

## 8. Error handling and the offline banner

All requests go through one function, `request()` in `web/src/api.js`:

| Situation | What the dashboard does |
|---|---|
| Normal reply | Returns the JSON; clears the offline state. |
| `204 No Content` | Returns nothing; clears the offline state. |
| The device answers with `{"error": "…"}` | Shows the device's own sentence (for example "There is already a sign called Kitchen."). |
| No network, connection refused, or a GET request timed out | Marks the device **offline** and reports "Can't reach the device. Check that it is switched on and on the same Wi-Fi as this phone or computer." |
| A change (POST, PATCH, PUT, DELETE) timed out | "The device took too long to answer. Check the Live page, then try again." (not marked offline, because the change may have happened). |
| 502, 504, or another 5xx without a JSON body | Treated as offline (a proxy answering for a device that is down). |
| Other errors without a sentence | 404: "That wasn't found on the device. It may have just been deleted. Reload the page to see the latest."; 413: "That photo is too large for the device. Try a smaller one."; 5xx: "The device ran into a problem (error 500). Try again in a moment."; otherwise "The device couldn't do that (error 400)." |
| A successful reply that is not JSON | "The device sent a reply this page doesn't understand. Make sure the dashboard and the device software are the same version." |

Timeouts: 10 seconds by default; 20 seconds for **Test speech**; 30 seconds
for reading the location and for **Check again** on the Place page (a fresh
lookup takes at most about 20 seconds on the device); 60 seconds for adding a
person or a photo.

**The offline banner.** While the device is offline, one banner appears at the
top of every page: "Can't reach the device. Retrying…", in a sticky slot with
`role="status"` so screen readers announce it. Polling continues in the
background; the first successful reply removes the banner. While offline,
buttons that would change something are disabled, pages show "Waiting for the
device.", and the camera shows its waiting message. Individual pages do not
repeat the offline error.

Errors from actions are shown next to the control that caused them, in a
paragraph with `role="alert"`, prefixed with what failed ("Couldn't save the
plan. …", "Couldn't start guiding. …").

---

## 9. Phone layout

The layout changes below a width of **760 pixels** (`max-width: 759.98px`):

- The left rail becomes a top bar with the wordmark and the device state.
- The five tabs become a **bottom tab bar** fixed to the bottom of the screen,
  each tab an equal fifth of the width with the icon above the label and a
  minimum height of 60 pixels. The current tab's icon sits in a soft green
  pill. Below 420 pixels the icon padding shrinks so all five tabs still fit
  side by side on a 360-pixel phone.
- **Safe areas**: the page sets `viewport-fit=cover`, the top bar is padded by
  at least `env(safe-area-inset-top)`, the tab bar by
  `env(safe-area-inset-bottom)`, and the content has bottom padding of 96
  pixels plus the safe area, so nothing is hidden under a notch, the home
  indicator, or the tab bar.
- The floor plan canvas becomes 320–560 pixels tall (58 % of the viewport
  height).

Touch-related rules across the app:

- **Touch targets of at least 44 pixels**: buttons, text links, checkboxes,
  plan tools (44 × 44), and map zoom buttons have a minimum height of 44
  pixels; text inputs and selects are 48 pixels; desktop navigation tabs are
  46 pixels.
- Form text is 17 pixels (the body size), above the 16 pixels at which some
  phone browsers zoom into a field.
- "Take photo with this phone" buttons and the "Two fingers move and zoom the
  plan" hint appear only on touch screens (`pointer: coarse`).
- Hover effects apply only on devices that can hover.
- On the map, one-finger drags scroll the page instead of panning the map on
  phones, and the scroll wheel does not zoom it.
- The plan editor uses pointer events: one finger edits, two fingers pan and
  zoom.

---

## 10. Accessibility

| Measure | Where |
|---|---|
| A **"Skip to content"** link appears when focused with the keyboard. | Shell |
| After every page change, focus moves to the new page's `<h1>`, so keyboard and screen-reader users start at the new content. | Shell |
| Visible focus: a 3-pixel outline in the ink colour on every focusable element (`:focus-visible`). | Global |
| Navigation is a labelled `<nav>`, with `aria-current` on the current tab. | Shell |
| Live regions: the offline banner (`role="status"`), the subtitle (`aria-live="polite"`), success messages (`role="status"`), and errors (`role="alert"`). | Throughout |
| Form fields have visible labels, hints linked with `aria-describedby`, `aria-required`, and `aria-invalid` on errors; on a failed submit, focus returns to the name field. | Forms |
| Destructive actions ask for confirmation **in place** (no pop-up); focus moves to "Cancel" when the question appears and back to the button afterwards. | `ConfirmAction` |
| Event kinds are shown by colour **and** shape (filled dot, ring, diamond, square), and each row has a hidden text label. | Timeline |
| Route steps announce ", reached" and ", next"; the current step has `aria-current="step"`. | Guide card |
| The floor plan is keyboard-operable (arrow keys, R, Delete, +/−, Ctrl/Cmd + Z), has a spoken summary of its contents and of the keys, and placed signs are focusable buttons named "Kitchen sign, where they are now". | Plan editor |
| Markers have text alternatives ("Marker for sign 3, Kitchen") where they carry meaning, and are hidden from screen readers where they are decorative. | Markers |
| The map is a labelled region: "Map of the device's estimated position. The circle shows the area it is likely within." | Place |
| Animations (the room pulse, caption fades, the live dot) are switched off when the system asks for reduced motion. | Global |
| A dark theme follows the system setting (`prefers-color-scheme`). | Global |
| `lang="en-GB"`, and browser text scaling is not overridden. | `index.html` |
| A legible typeface designed for low-vision readers (section 11.2). | Global |

No formal accessibility audit (automated or with assistive-technology users)
has been carried out.

---

## 11. Design system

### 11.1 Colour palette

Colours are CSS custom properties in `web/src/styles.css`, with separate values
for the light and dark themes. Each colour has one meaning across the app, and
the device draws its camera overlays in the same moss and marigold.

| Token | Light | Dark | Meaning and use |
|---|---|---|---|
| `--paper` | `#F3F5F2` | `#121819` | Page background (a soft off-white in the light theme). |
| `--surface` | `#FFFFFF` | `#1A2224` | Cards, panels, inputs. |
| `--ink` | `#1F2A2E` | `#E6ECE8` | Main text; focus outline. |
| `--muted` | `#5D6B6E` | `#A2B0B1` | Secondary text, hints, ordinary plan links. |
| `--line` / `--line-strong` | `#D9DFDB` / `#B4BFBA` | `#2D383A` / `#46555A` | Borders and dividers. |
| `--moss` | `#2F6B4F` | `#6DBE93` | **Known and OK**: recognised faces (also the green box on the camera picture), "running" states, primary buttons, signs in view, the reading-zone wedge, the location circle. |
| `--moss-soft` | `#E2EEE7` | `#1B3327` | Selected tab, success backgrounds. |
| `--marigold` | `#C98A16` | `#E2A93F` | **Unknown or needs attention**: unknown faces (also the orange box on the camera picture), the offline banner, "Camera off", warnings. `--marigold-text` `#855800` is used for text on light backgrounds. |
| `--danger` | `#A3362A` | `#F08A7E` | Destructive actions (delete). |
| `--route` | `#2F5F8A` | `#8AB8E6` | **Guidance and moving between rooms**: route steps, highlighted route arrows, room-change events, the current-room ring. |
| `--stage` | `#11181A` | `#0A0F10` | Background behind the camera picture. |
| `--caption-bg` / `--caption-ink` | `#1F2A2E` / `#F3F5F2` | `#E6ECE8` / `#121819` | The subtitle strip. |

The browser's theme colour matches the paper colour (`#F3F5F2` light,
`#121819` dark), and the favicon is a moss-green rounded square with a ring.
Corners are 22 pixels on the camera frame and 10 pixels on controls.

### 11.2 Typography: Atkinson Hyperlegible Next

The whole interface uses **Atkinson Hyperlegible Next** (variable weight),
with system sans-serif fonts as fallbacks. Atkinson Hyperlegible was designed
by the Braille Institute for readers with low vision: letters that are often
confused (such as capital I, lower-case l, and the digit 1, or O and 0) are
given distinct shapes, and the letterforms are open and generously spaced.
The typeface was chosen for that reason: the dashboard is meant to be easy to
read for caregivers whose eyesight may not be perfect, often on a small phone
screen. The "Next" version is a variable font, so one pair of files (Latin and
Latin Extended) covers every weight used.

Sizes: body text 17 px (1.0625 rem) with line height 1.5; small text 14 px;
headings 18 px (h3), 22 px (h2), and 28–38 px (h1, scaling with the screen).
Headings are bold (weights 700–760).

### 11.3 Copy conventions

The interface text follows consistent conventions, visible throughout the
source:

- **The wearer is "they"; the caregiver is "you".** "With them now", "Guide
  them to…", "Said to them", "They hear one step at each sign on the way."
- **Plain, complete sentences** in everyday words; no technical terms where an
  ordinary word works ("Match cutoff" and "Face detector" appear only on the
  Device page).
- **Buttons say what will happen**: "Take photo and save person", "Save
  directions", "Turn speech off", "Delete Priya".
- **Errors say what failed and what to do next**: "Couldn't save the plan. …",
  "The camera isn't running. Check the ribbon cable and restart CogniSight."
- **Progress ends with an ellipsis**: "Saving…", "Checking…", "Taking photo…".
- **Honest states**: "Not running", "Not available", and a location from the
  internet address is called "a rough area", never a position.
- **Destructive actions name what will be lost**: "Delete Priya and 3 photos?
  This can't be undone."
- **Relative times** ("just now", "40 sec ago", "2 hr ago", "yesterday") with
  the exact time as a tooltip.
- Quoted speech uses curly quotation marks (“…”); spelling is British English;
  there are no exclamation marks.

---

## 12. Limitations

- **No login.** Anyone on the same network can open the dashboard, watch the
  camera, and add or delete people (see
  [ARCHITECTURE.md](../ARCHITECTURE.md#11-security-and-privacy)).
- **Same network only.** A caregiver away from home cannot reach it; there is
  no cloud relay.
- **Polling, not push.** Updates arrive up to one polling interval late (1 s
  on the Live page), and each open dashboard adds requests and, while visible,
  one MJPEG stream to the Pi's load. The effect on the Pi has not been
  measured.
- **Committed build can drift.** If the source is changed without rebuilding
  and committing `web/dist`, the Pi serves the old dashboard.
