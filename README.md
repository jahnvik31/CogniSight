# CogniSight

CogniSight helps a person living with dementia recognise the people around
them. A Raspberry Pi camera sees who is in front of them, and a quiet voice in
their earphones says "This is Priya, your daughter." Family members add people
and watch what the device sees from a dashboard on their phone.

What it does, why, and what was dropped from the original plan:
[docs/PROJECT_OVERVIEW.md](docs/PROJECT_OVERVIEW.md).

## What you need

- Raspberry Pi 5 with Raspberry Pi OS (64-bit, with desktop), connected to Wi-Fi
- Raspberry Pi Camera Module 2 on the 22-pin ribbon cable
- Bluetooth earphones (or any speaker) for the spoken names
- Optional: a monitor, and a USB microphone for voice commands
- About 3 GB of free space and an internet connection for the first setup

## Set it up (once)

Open a Terminal on the Pi and run:

```sh
git clone https://github.com/jahnvik31/CogniSight.git
cd CogniSight
./setup.sh
```

This installs everything, downloads the models, and saves one photo from the
camera as `camera-check.jpg`. It takes 10 to 20 minutes. If the camera check
fails, check that the ribbon cable is pushed in fully at both ends with the
contacts facing the right way, then run `./setup.sh` again.

To have CogniSight start by itself whenever the Pi turns on, run
`./setup.sh --autostart` instead.

### Earphones

Pair the Bluetooth earphones from the Bluetooth icon at the top right of the
Pi's desktop. Then right-click the speaker icon and choose the earphones as
the audio output. Spoken names go to whichever output is selected there.

### Location (optional)

Open the `.env` file in the CogniSight folder and paste the Google
Geolocation key after `GEOLOCATION_API_KEY=`. Restart CogniSight. Google gives
a close position only when the Pi can hear at least two Wi-Fi access points.
With fewer, it gives a rough area of a few kilometres, and the dashboard says so.

## Run it

```sh
cd CogniSight
./start.sh
```

The dashboard opens on the Pi's screen. On a phone connected to the **same
Wi-Fi**, open the address the terminal prints, usually
`http://cognisight.local:8765`. The Device page shows it too.

To stop CogniSight, press `Ctrl+C` in the terminal.

## Demo in five steps

1. Open **People** and press **Add a person**. Type a name and a relationship
   ("daughter"), choose **Take photo with the device camera**, have that person
   face the camera, and press **Take photo and save person**.
2. On their page, add two or three more photos from slightly different angles.
3. Open **Live**. When they step in front of the camera, a green box appears
   with their name, and the earphones say "This is Priya, your daughter." The
   words also appear as subtitles under the picture.
4. Someone who is not saved gets an orange "Unknown" box and no announcement.
5. With a microphone connected, say "who is this?" to hear the name again, or
   "stop" to cut the speech off.

## Signs around the home (indoor guidance)

1. Open **Home** and add a sign for each place that matters: Bedroom, Hallway,
   Bathroom, Kitchen. For each one, write a short direction to the next sign,
   for someone standing in front of it ("The bathroom is the second door on
   your right.").
2. Optionally draw the house on the floor plan: walls, doors, room names, and
   where each sign goes. The shaded wedge in front of a sign shows where the
   wearer has to stand for the camera to read it.
3. Press **Print signs**, print one A4 sheet per sign, and tape each at eye
   level beside its door.
4. When the camera sees a sign, the wearer hears "This is the kitchen." To guide
   them, choose a room under **Guide them to…** on the Live page, or let them
   say "take me to the bathroom". They hear one step at each sign until "You're
   at the bathroom."

Demo with three printed sheets (Bedroom, Hallway, Bathroom) taped around the
room: start at Bedroom, press **Guide them to… Bathroom**, and walk past the
signs while the dashboard ticks off the route.

## If something looks wrong

| Problem | Fix |
|---|---|
| Picture is upside down | `./start.sh --flip` |
| Faces look blue | `./start.sh --swap-colors` |
| "Camera not found" | Check the ribbon cable, then restart. Test with `.venv/bin/cognisight camera` |
| No sound | Choose the earphones as the output (speaker icon). Press **Test speech** on the Live page |
| Voice commands do nothing | Bluetooth earphone mics are unreliable on the Pi. Use a USB microphone |
| Phone can't open the dashboard | Phone and Pi must be on the same Wi-Fi. Try the numeric address on the Device page |
| Someone is not recognised | Add more photos of them, facing the camera, in similar light |
| A sign is not read | Walk closer (about 2.5 m or less), face it, and make sure it is printed at full A4 size and lit |

## Commands

```sh
./start.sh                                   # everything: camera, recognition, speech, dashboard
.venv/bin/cognisight camera                  # save one photo from the camera
.venv/bin/cognisight enroll "Priya" a.jpg --relationship daughter
.venv/bin/cognisight identify photo.jpg      # name the people in a photo
.venv/bin/cognisight start --help            # all options
```

People are stored as folders of photos under `data/faces/`. Nothing leaves
the Pi except the location request to Google.

## For developers

- Python code: `src/cognisight/`. Run the tests with `python -m unittest discover -s tests -v`.
  They need only Flask.
- Dashboard (SolidJS): `web/`. It is served from the committed `web/dist`. After
  changing it, run `cd web && npm install && npm run build` and commit `web/dist`.
  While editing, run `npm run dev` with `cognisight start` running, and open
  http://localhost:5173.
- API: [docs/API.md](docs/API.md).

Recognition settings: DeepFace Facenet512, OpenCV face detector, cosine
distance, cutoff 0.30. The dashboard has no login, so use it only on a trusted
network.
