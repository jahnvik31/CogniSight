# CogniSight product notes

Product discussion only. This file does not authorize code changes.

## Product framing

CogniSight is an offline aid for a person living with dementia. The value to them is not feeling lost when someone they should know appears. That recognition should arrive calmly. Their autonomy matters: the device should support the moment, not take it over.

## Features, in order

1. Contextual facial recognition
2. Outdoor navigation
3. Indoor navigation
4. Caregiver dashboard

## Facial recognition

A caregiver enrolls each person with a name, a relationship, and a note. Three consecutive matches of the same face trigger speech. The wearer can also use "Computer" commands: who is this, tell me more, when did I last see them, repeat, stop, pause, and resume.

The current stack finds a face with YuNet and builds a signature with SFace. Photos are not stored. Matching is against a local gallery. Named speech stays off until the gallery is calibrated on real faces, and a frame older than one second cannot confirm anyone. Listening and speech are offline. This design has not been shown working on the Raspberry Pi.

The three-in-a-row rule is there to avoid false introductions. To the wearer it can read as the device hesitating. The preferred behaviour is to speak immediately when a strong combined confidence is reached from the multi-angle vectors stored for that person, with a single safe word that cuts the speech off.

YuNet and SFace are a narrow pair, and they are unvalidated on this Pi. DeepFace has a proven Raspberry Pi 5 track record and is the stack to weigh against the current pair.

Judges will value human impact over the technology. Lead with fewer repeated introductions and with recognition that stays calm.

Solidify the product before changing code.

## Stack review

Parked for development. None of this is immediate work, and none of it changes the current code.

This section refines the stack note above. The earlier note treated DeepFace as a proven Pi 5 option in general. Here the claim is narrower: the caller has already seen DeepFace perform on a Raspberry Pi 5.

### Matching

Swap YuNet and SFace for DeepFace in `matching.py`. One library would cover detection, embedding, and tracking. Enrollment stays multi-angle, with several vectors per person. Combined confidence across those vectors is the trigger to speak.

### Tracking and stability

DeepFace's face tracking can tag and identify the faces in a frame. Still open: whether a separate YOLO model is needed on top of that.

### Speech

Research lightweight speech-to-text and text-to-speech among Hugging Face audio models. Cactus Labs' small edge models are worth checking for the Pi.

### Setup screen

Password setup and diagnostics arguably belong in the web UI rather than `cli.py`. Keep a headless CLI fallback, because a dementia device may have a broken display.

### Config

Replace the manual try/catch validation with Pydantic models. Open question: why the IP-address checks, the optional-services block, and `validate_config` exist in their current form.

### Shared records

Replace the dataclasses in the shared records with Pydantic models, for stricter type checking.

### Packaging

A plain GitHub clone is enough for the deadline. No Docker for now.

## Outdoor navigation dropped

Outdoor navigation is dropped. The board the team has cannot provide a satellite position, and the online substitutes could not be turned on in time.

The ADIY SIM A7670C is a 4G modem, not a GPS receiver. A satellite fix on that chip needs a separate antenna, and that antenna is not available in time.

Google's Geolocation API can place a device at about 20 metres indoors from nearby Wi-Fi. The free allowance is 10,000 calls a month, or 70,000 on an India-priced account. A billing account is required even for the free allowance. An India address has 30 days to finish an identity check with PAN or Aadhaar. Paying by UPI needs a prepayment of ₹500 to ₹1,000, and that payment does not finish the identity check. The $300 Cloud credit starts only when signup creates the first billing account as a trial.

An auto-created "Google Cloud Platform trial billing account" is already linked to the projects visible, test auth, and replay, all outside an organization. Turning Geolocation on for visible still sent the browser back to billing, and the loop repeated.

Creating another billing account was blocked. The organization menu on that screen was grayed out. This Google account belongs to an organization and does not have permission to create a billing account there. The form offers no way to choose "no organization."

The other location services were not usable. Mozilla Location Service has been closed to outside users since June 2024. An internet-address lookup needs no billing account, and it places the college's shared connection, kilometres from the room. OpenCelliD uses cell towers. The Pi cannot see towers, and Indian coordinates from that service are rounded to about 1 kilometre.

## Indoor navigation

Indoor navigation is three files under `src/cognisight/indoor`. One part saves a room map as a local file. Another walks doorways and corridors to list a route. There is no camera, no sensor, and no floor plan behind it. The live status is a stub that always says unavailable. It is a map a caregiver types in, not guidance for the person wearing the device.

Nothing senses the room. There is no laser scanner, no depth camera, no Bluetooth beacon, and no AirTag-style tag. The map is entered by hand.

For a person with dementia, the confusion that matters is forgetting what a room is for, not finding the door. Using the camera they already have to say "kitchen" when they walk in fits the face-recognition idea better than a route someone clicked.

Without a working location fix, indoor navigation cannot know where the wearer is. OpenHaystack Bluetooth beacons were the missing piece suggested for rough direction and distance inside an apartment.

As it stands, the system is a wearable security camera. A caregiver watches the feed and reacts.

## Overall

Several features do not make sense as designed. The location attempt failed because the SIM card was not bought with the A7670C module. The Pi camera was later confirmed working, on a 22-pin cable. The check script from that confirmation was not kept. `cognisight camera` is the replacement: one frame through Picamera2.

## Caregiver dashboard

Trim the phone page to two panels. Remove outdoor location and indoor navigation entirely. Keep device health, as a check that the Pi is alive, and people in view, from recognition.

A live camera picture is the other idea. Sending that picture over the local network with RTSP is a poor fit for ordinary Wi-Fi. The practical path is a cloud push: the Pi sends the video to a server, and the caregiver watches it from that server on their phone, because they cannot stay on the same Wi-Fi as the Pi. That server is a new dependency.

If the stream works, the dashboard has something to show. Indoor navigation could come back as visual context from that picture, rather than as a map the caregiver typed in.

## Foundation

The previous program was removed. The tests and most of that code were holding a design this project is not going to build: YuNet and SFace, the GPS client, the typed room map, and the four-panel phone page.

What is in `src/` now is a face gallery. One folder of photos per person, matched with DeepFace Facenet512 the same way VISU-X does it. Enroll, identify, and a camera watch are command-line tools. Speech, the phone page, and room recognition are not in this code yet.
