# Run CogniSight on your Pi using SSH — draft

**For review only.** Use the final guide after the build and local commits are approved. These steps have not been tested on your Pi; no hardware test is being claimed.

Your Pi is already set up with Raspberry Pi OS 64-bit, user **jahnvi**, and hostname **cognisight**. Keep its existing OS and files. Keep your laptop and Pi on the same Wi-Fi. Commands below use a Mac/Linux terminal; Windows commands need to be adapted first.

You have an **AUX headset**; audio setup is for later. Pi 5 has no headset jack, so the current app needs a suitable **USB sound adapter**, including microphone input if your headset has a mic. Camera checks can proceed first; headset tests and app startup wait for valid audio settings.

SSH lets your laptop open a terminal on the Pi. **On your laptop** means a local terminal; **On your Pi** means the terminal opened through SSH. Keep passwords and private files on your devices, out of chat and Git. Replace any `REPLACE_...` text with your own value.

## 1. Connect to the Pi

**On your laptop:**

```sh
ssh jahnvi@cognisight.local
```

On the first connection, verify the displayed key fingerprint against the Pi's local screen or a trusted saved record before accepting it; see the appendix if needed.

**Expected:** You reach a terminal for `jahnvi` on the Pi.
**If it fails:** Check power, Wi-Fi and SSH; if the name is not found, use the IP fallback in the appendix.

## 2. Check the Pi before installing anything

**On your Pi:**

```sh
cat /etc/os-release
uname -m
python3 --version
df -h .
```

The planned starting point is **Bookworm, Python 3.11, aarch64**; it has not yet been tested on your Pi. The installed camera libraries and Python packages must match.

**Expected:** You can identify the OS, Python version and free space.
**If it differs or is unclear:** Stop before installing anything; review a matching setup for that OS, without erasing the card or downgrading Python.

## 3. Fit the camera with power off

**On your Pi:** Stop CogniSight if it is running, then shut down.

```sh
sudo shutdown -h now
```

Wait for shutdown and unplug power. Pi 5 uses a **22-pin camera connector**; the intended Camera Module 2 uses a **15-pin connector**. Your photos show **Camera V2.0**, cable **HBV-Raspberry15DFPC** and 22 visible contacts at the free end; the camera end is hidden, so confirm the cable's fit before connecting it. The labels do not prove an official camera or its sensor. Follow the [official cable instructions](https://www.raspberrypi.com/documentation/computers/camera_software.html). Check the power supply and cooling, reconnect power, then repeat Step 1. Do not wire the SIM A7670C/RS232 board yet.

**Expected:** The camera is connected and the Pi boots again.
**If it fails:** Check the cable and power with the Pi unplugged; never move the camera ribbon while powered.

## 4. Copy the approved local code

**On your laptop, in another terminal:** Use your actual checkout path; the path below is the known workspace example.

```sh
cd /Users/acctest/cognisight/CogniSight
git status --short
git rev-parse HEAD > /tmp/cognisight-commit.txt
git archive --format=tar.gz --output=/tmp/cognisight-code.tar.gz HEAD
scp /tmp/cognisight-code.tar.gz /tmp/cognisight-commit.txt jahnvi@cognisight.local:/tmp/
```

Run this only after the approved changes are committed locally and committed files have been checked for private data. The new code is **not pushed**: cloning GitHub main will miss it. This archive copies committed files without old Git history, ignored models or private state; uncommitted edits are excluded.

**Expected:** Both files reach the Pi; the text file records which commit was copied.
**If it fails:** Check the checkout path and SSH connection; finish intended local changes before transfer, without pushing.

## 5. Unpack into a new folder

**On your Pi:**

```sh
COGNI_REV=$(cat /tmp/cognisight-commit.txt)
COGNI_BUILD="$HOME/cognisight-builds/$COGNI_REV"
mkdir -p "$HOME/cognisight-builds"
mkdir "$COGNI_BUILD" &&
tar -xzf /tmp/cognisight-code.tar.gz -C "$COGNI_BUILD" &&
cp /tmp/cognisight-commit.txt "$COGNI_BUILD/.source-commit" &&
cd "$COGNI_BUILD" &&
cat .source-commit
```

**Expected:** A new folder contains the copied code and its commit number, leaving existing installs and state untouched.
**If it says the folder exists or extraction fails:** Stop and inspect it; do not unpack over an existing install.

## 6. Prepare Python

**On your Pi:** Continue only after Step 2's OS check and the matching package setup are approved; internet is needed for installation and model downloads.

```sh
sudo apt update
sudo apt install python3-venv python3-picamera2 libportaudio2
python3 -m venv --system-site-packages .venv
. .venv/bin/activate
python -m pip install --dry-run -e '.[vision,audio,dev]'
```

**Expected:** The camera packages install, and pip shows a package list without conflicts for review before the real install.
**If it fails or proposes building camera/numerical libraries from source:** Stop and review the package versions; do not use sudo pip or install libcamera through pip.

## 7. Install and check the Python packages

**On your Pi:** After reviewing Step 6's package list:

```sh
python -m pip install -e '.[vision,audio,dev]'
python -m pip check
cognisight doctor
python -c 'import numpy, cv2; from picamera2 import Picamera2; import libcamera; print("NumPy", numpy.__version__); print("OpenCV", cv2.__version__)'
cognisight devices
```

**Expected:** The Python checks finish without errors; audio remains pending until your USB sound adapter is connected and listed.
**If it fails:** Check matching camera/Python packages, and leave missing audio pending without switching to a default speaker.

## 8. Take a camera test picture

**On your Pi:** Stop CogniSight and other camera programs first; point at a scene without people.

```sh
rpicam-hello --list-cameras
umask 077
COGNI_CAMERA_DIR=$(mktemp -d /tmp/cognisight-camera.XXXXXX)
rpicam-still --nopreview --timeout 2000 -o "$COGNI_CAMERA_DIR/check.jpg"
printf '%s\n' "$COGNI_CAMERA_DIR"
```

**Expected:** The actual camera sensor is listed, a picture is saved, and its folder path is printed.
**If it fails:** Check whether another program owns the camera; if no camera is found, shut down and unplug power before checking the cable.

## 9. Look at the picture

**On your laptop:** Replace `REPLACE_CAMERA_DIR` with the full folder path printed in Step 8, then open the copied picture in your usual image viewer.

```sh
scp jahnvi@cognisight.local:REPLACE_CAMERA_DIR/check.jpg /tmp/cognisight-check.jpg
```

**Expected:** You see a clear picture of the test scene.
**If it is missing or unusable:** Fix capture, lighting or focus before moving on.

## 10. Delete the test picture

**On your Pi, in the same SSH terminal as Step 8:** Also delete `/tmp/cognisight-check.jpg` on your laptop using its file manager.

```sh
rm "$COGNI_CAMERA_DIR/check.jpg"
rmdir "$COGNI_CAMERA_DIR"
```

**Expected:** The private test picture is removed from both devices.
**If it fails:** Check the exact path and remove only the test file; do not use broad delete commands.

## 11. Check visible camera preview

**On your Pi, in its own desktop terminal with a monitor attached:**

```sh
rpicam-hello --timeout 5000
```

**Expected:** You see a live preview for five seconds.
**If no monitor is available:** Record preview as pending; an SSH capture with no preview does not prove this step passed.

## 12. Download models; set audio later

**On your Pi, in the copied build folder with `.venv` active:**

```sh
python scripts/fetch_models.py --destination models
cp -n config.example.json config.json
chmod 600 config.json
cognisight devices
sha256sum models/face_recognition_sface_2021dec.onnx
nano config.json
```

Set `model_version` to `sface:` followed by the printed hash, matching `models/manifest.json`. Keep `calibrated: false`, navigation disabled and caregiver access disabled for now. `cp -n` preserves an existing config. When your sound adapter is ready, enter its exact USB input/output names; until then, leave audio unconfigured and skip Steps 13–15.

**Expected:** Models download successfully and the real hash is recorded, with audio settings completed only after the adapter is ready.
**If downloads, hashes or later audio checks fail:** Stop and fix them; do not turn off model checks or use speaker fallback.

## 13. Run a short camera and headset check

**On your Pi, after the USB sound adapter and microphone are configured:** Keep CogniSight stopped; wear the headset, answer the playback prompt and speak “Computer, who is this?” when asked.

```sh
mkdir -p qualification-private
chmod 700 qualification-private
python scripts/qualify.py --output qualification-private/inventory.json
python scripts/qualify.py --config config.json --seconds 10 --interactive --output qualification-private/smoke.json
```

**Expected:** A private report records real camera frames, measured processing time and your actual headset check.
**If it fails:** Read the report's failed step and fix that device/model problem; ten seconds passing is not proof of recognition accuracy.

The first command saves inventory separately. The ten seconds is a sample period, not protection from a stuck camera library: if native code hangs or crashes, the smoke report may not be written, while the earlier inventory remains.

## 14. Start CogniSight

**On your Pi:** Set the caregiver password privately at the prompts, then start one app.

```sh
cognisight password
cognisight run --config config.json
```

**Expected:** One app runs; Ctrl-C stops it and releases the devices.
**If it fails:** Check config, models and headset; do not start another copy or run the app as root.

## 15. Open local enrollment from your laptop

**On your laptop, in another terminal:** Keep this connection open, then visit `http://127.0.0.1:8875` in your laptop browser.

```sh
ssh -N -L 127.0.0.1:8875:127.0.0.1:8765 jahnvi@cognisight.local
```

Sign in using the password from Step 14. This private connection keeps enrollment off the Wi-Fi network. Close it with Ctrl-C when finished. Follow the [recognition guide](../recognition/README.md) before enrolling consenting people or enabling named announcements; do not change `calibrated` just to force a demo.

**Expected:** The local enrollment page opens and accepts your login.
**If local port 8875 is busy:** Choose another free local port in both the command and browser URL.

## Advanced checks / later

These checks belong after the basic setup works. Anything untested stays **pending**.

### Connection help

**On your laptop:** If `cognisight.local` is not found, get the Pi's IP from your router's device list, or run `hostname -I` on the Pi's local screen; then connect with `ssh jahnvi@REPLACE_PI_IP`. Replace `cognisight.local` with that verified IP in later ssh/scp commands too.

For a first-connection fingerprint, **on the Pi's local screen** run `ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub` and compare it with SSH's prompt. If a previously saved key changes, stop and explain the change before updating it. See [official remote-access help](https://www.raspberrypi.com/documentation/computers/remote-access.html).

### Package checks and software tests

The project starts with Bookworm/Python 3.11; latest Raspberry Pi OS downloads use Trixie, which needs its own check. The project currently uses NumPy below 2 and OpenCV 4.10 or newer/below 5. Camera libraries installed by apt and Python packages must work together. Use one intended OpenCV pip package; do not replace OS camera libraries or bypass OS Python protections. Plain doctor finds packages; it does not prove they load or the devices work. The planned native doctor option is not available yet.

**On your Pi:** Run `PYTHONPATH=src python -m unittest discover -s tests -v`; if Node is already installed, also run `node --test tests/dashboard.test.cjs`. Keep every skipped or failing test visible. `scripts/qualify.py` exit 1 means a requested check failed; exit 2 means command/output trouble. An inventory-only report or empty camera scene does not prove face recognition ran successfully.

Save actual OS/image, Python, apt/pip versions, camera sensor, headset/rates, power/cooling and model hashes. Keep package lists private and review them before sharing: they may contain local paths or private download addresses. The model downloader records hashes; Vosk's first download still relies on trusting its official HTTPS source.

### GNSS and caregiver phone

Your board is described as **SIM A7670C MODULE WITH RS232**. Its exact board manual, GNSS support and connection levels are still unverified; an RS232 connection must not be wired directly to Pi GPIO. The 19:54:15 photo shows Imager settings, not the board. Follow the [GNSS guide](../navigation/README.md) only after identifying the hardware, without guessed pins or modem commands. GPSD alone owns the receiver and stays local to the Pi. No fix means unavailable, not invented coordinates; there are no route directions.

Follow the [caregiver HTTPS guide](../caregiver/README.md) for Caddy and the actual phone OS. Use the same exact hostname/IP in app settings, Caddy and the phone URL. The phone must trust Caddy's **public root certificate**, with its fingerprint verified through a trusted channel; never copy the CA private key or bypass a browser warning. Only dashboard backend `127.0.0.1:8766` is proxied. Enrollment `127.0.0.1:8765` stays local. Keep both devices on the same Wi-Fi; do not expose ports to the internet.

### Start after reboot

Adapt `deploy/cognisight.service` to this build's real folder; its example `%h/CogniSight` path differs. Use an ordinary user and only the device permissions needed. Headless audio and user-service startup need testing after logout/reboot; follow the [service guidance](../recognition/README.md) before enabling it. Stop the foreground copy first, and check exactly one app starts. Do not grant root or world-writable device access to fix failures.

App state lives in `~/.local/share/cognisight`, outside the build folder. Preserve it during updates, along with your private config/models. After checking the transfer, delete the temporary archive and commit-number file from `/tmp` on each device.

### Measure before declaring the system ready

Follow the [existing test requirements](../recognition/QUALIFICATION.md) for held-out recognition accuracy, unknown faces, response/stop timing, real voice commands, gallery size, two-hour use, memory, offline use and device recovery. A short camera test proves none of these by itself. Keep local Wi-Fi for SSH/phone when checking operation without internet. Never unplug the camera ribbon while powered. Record failed tests, limits and missing measurements honestly.
