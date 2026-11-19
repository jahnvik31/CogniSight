# Demonstration script

A 5 to 7 minute demonstration of every CogniSight feature for examiners.
Examiners cannot hear the wearer's earphones, so every step is also visible
on the dashboard. Show the dashboard on a monitor attached to the Pi, or on a
laptop or phone on the same Wi-Fi.

## Before the session (the day before)

- [ ] `./setup.sh` has been run and finished without errors.
- [ ] Bluetooth earphones are paired and chosen as the Pi's audio output.
      **Test speech** on the Live page plays in them.
- [ ] Optional: a USB microphone is plugged in, for voice commands.
- [ ] Two or three people are enrolled, each with a relationship and 3 to 5
      photos (People page). One team member stays un-enrolled, to show
      "Unknown".
- [ ] Four signs exist on the Home page (Bedroom, Hallway, Bathroom, Kitchen),
      with directions written between them, and a floor plan drawn with the
      signs placed.
- [ ] The signs are printed on A4 at 100% scale.
- [ ] The Google Geolocation key is in `.env`, if location is to be shown.
- [ ] The Pi has a cooler and a proper power supply (5 V, 5 A for a Pi 5).

## Setting up in the room (5 minutes)

1. Tape the Bedroom, Hallway and Bathroom signs at chest height on three walls
   or desks, a few metres apart, so a person can walk from one to the next.
2. Start CogniSight: `./start.sh`. Wait until the Live page shows the camera
   and the timeline says "Face recognition ready" and "Speech ready".
3. Open the Place page and press **Check again**, so the location is fresh.
   The demonstration room may have more Wi-Fi access points than the hostel,
   which gives a closer fix.

## The demonstration

### 1. The problem (30 seconds)

"A person living with dementia often can't recognise a familiar face, or
forgets what a room is for. CogniSight is a camera worn on the body that names
the people and the places around them, quietly, in their earphones."

### 2. Recognising people (2 minutes)

1. The wearer (a team member with the earphones) faces the camera at the
   enrolled person.
2. On the Live page, a green box with the name appears, and the subtitle shows
   **"This is Priya, your daughter."** That is exactly what the wearer heard.
   "With them now" shows the name and relationship.
3. The un-enrolled team member steps in. They get an orange **Unknown** box,
   and nothing is said. Point out that the device would rather say nothing
   than name the wrong person (the 0.30 cutoff).
4. The enrolled person steps out and back in. Nothing is repeated: a person is
   introduced again only after being out of view for two minutes, so the
   wearer is not interrupted.
5. With a microphone, the wearer says "who is this?" and hears the name again,
   then "tell me more" to hear the caregiver's note.
6. Show **People**: add someone live with **Take photo with the device
   camera**, then show that they are recognised straight away.

### 3. Signposts (2 to 3 minutes)

1. Show the **Home** page. Point out the floor plan with walls and doors, the
   placed signs, the shaded zones where each sign can be read from, and the
   arrows for the written directions.
2. Open a sign and show one direction, written for someone standing in front
   of that sign.
3. The wearer stands at the Bedroom sign. The subtitle shows **"This is the
   bedroom."** and the Live page shows "In the bedroom".
4. On the Live page, choose **Guide them to… Bathroom** and press **Start
   guiding**. The wearer hears "Go out of this door and turn left." The guide
   card shows the route: Bedroom, Hallway, Bathroom.
5. The wearer walks to the Hallway sign: "The bathroom is the second door on
   your right." The step ticks off on the card.
6. The wearer reaches the Bathroom sign: "You're at the bathroom." The card
   shows the arrival.
7. Explain the key idea: the Pi has no compass, but when the camera reads a
   sign the wearer must be facing it, so "left" and "right" are always correct
   at that moment.
8. Optional: walk to the wrong sign during a trip to show the route being
   planned again.

### 4. Where they are (1 minute)

1. Show **Place**: "At home: in the hallway since 3:12 pm", with the list of
   room changes. This lets a caregiver check on someone without watching a
   camera feed.
2. Show the outdoor estimate on the map. Explain honestly whether it came from
   Wi-Fi or only the internet connection, and why GPS was not possible with
   the available board.

### 5. Device health (30 seconds)

Show **Device**: camera, face recognition (model, cutoff and seconds per
check), speech, listening, and the addresses a phone can open.

## If something goes wrong

| Problem | What to do |
|---|---|
| No sound in the earphones | Use the subtitles on the Live page: they show every sentence. Re-select the earphones as the audio output. |
| A voice command is not heard | Use the dashboard: **Guide them to…** and the speech buttons do the same things. |
| A face is not recognised | Face the camera directly in good light. Add another photo from the People page. |
| A sign is not read | Move closer (within about 2.5 m), face it squarely, and make sure it is lit and not glossy. |
| The picture is upside down or faces look blue | Restart with `./start.sh --flip` or `./start.sh --swap-colors`. |
| The dashboard does not open on a phone | The phone must be on the same Wi-Fi. Use the numeric address on the Device page, or use the Pi's own screen. |
| Location shows a wide area | Explain the two-access-point rule (see `docs/features/location.md`). This is the honest result. |
