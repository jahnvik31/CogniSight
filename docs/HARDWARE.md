# Hardware

What CogniSight runs on, how each part is connected, and what each part can
and cannot do. Specifications are from the manufacturers' published data
unless stated otherwise.

## Parts list

| Part | Role | Notes |
|---|---|---|
| Raspberry Pi 5, 8 GB | Runs everything: camera, face recognition, signs, speech, and the dashboard server | Quad-core Arm Cortex-A76 at 2.4 GHz. All inference runs on the CPU. An active cooler is recommended, because face recognition keeps the CPU busy. Use the official 5 V, 5 A USB-C power supply. |
| Raspberry Pi Camera Module 2 | The only sensor for the surroundings: faces and signs | Sony IMX219, 8 megapixels, 62.2° × 48.8° field of view, fixed focus. It connects to one of the Pi 5's 22-pin camera connectors (the Pi 5 uses the smaller 22-pin connector; the module was confirmed working on a 22-pin cable). CogniSight captures at 640 × 480 at 15 frames per second through Picamera2. |
| Bluetooth earphones | Speech to the wearer | Paired from the Pi desktop and chosen as the default audio output |
| USB microphone (optional) | Voice commands | More reliable than a Bluetooth earphone microphone on Linux, which switches the connection to a low-quality telephone mode |
| Monitor (optional) | Shows the dashboard during a demonstration | `start.sh` opens the dashboard full-screen when a desktop is running |
| microSD card, 32 GB or more | Operating system and models | Raspberry Pi OS 64-bit with desktop. The models and Python packages take about 3 GB. |
| ADIY SIM A7670C board | Not used | See below |

## The A7670C board

The board the team had for outdoor positioning is an ADIY SIM A7670C: a 4G LTE
cellular modem with an RS232 interface and a 1.8 V serial header. It is not a
satellite receiver. Some variants of the A7670C include GNSS, which needs its
own GNSS antenna, but satellite positioning does not need a SIM card. No GNSS
antenna was available, and it was not confirmed whether this variant includes
GNSS, so the board is not used. The exact model printed on the module should
be checked before buying an antenna, if outdoor positioning is attempted
later. See `docs/DESIGN_DECISIONS.md`, section 5.

## Audio

The Raspberry Pi 5 has no 3.5 mm audio jack, so the team's wired AUX headset
cannot be used directly. CogniSight plays speech on the system's default
output:
- Bluetooth earphones paired from the desktop (the intended set-up);
- the speakers of an HDMI monitor;
- a USB sound card, which would also allow the wired headset to be used.

## Wearing the device

The camera faces forward at chest or head height, so what it sees matches
what the wearer is facing. This matters for the signposts: directions are
spoken when a sign is in view, on the basis that the wearer is facing it.
Signs should be placed at about the same height as the camera.

## Camera settings

- Orientation: if the camera is mounted upside down, start with `--flip`.
- Colour order: Picamera2's "RGB888" frames are stored as blue, green, red in
  memory, which is the order OpenCV and DeepFace expect, so no conversion is
  done. If faces look blue on the dashboard, start with `--swap-colors`.
- A USB webcam is used only if no Pi camera is found. This is how the software
  was tested on a laptop.

## Network

The Pi joins Wi-Fi like any computer. The dashboard is served on port 8765
and is reachable from phones on the same network at
`http://<hostname>.local:8765` (the Pi's hostname is `cognisight`) or at its
IP address. For location, the Pi lists nearby Wi-Fi access points with
NetworkManager (`nmcli`). It does not need to connect to them.
