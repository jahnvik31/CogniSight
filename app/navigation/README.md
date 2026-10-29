# CogniSight — Module 2: Indoor Navigation Guide

## 1. Module Overview & Assistive Purpose

Module 2 of the CogniSight assistive system provides **marker-referenced graph navigation** designed to help individuals with early-stage Alzheimer's disease or cognitive difficulties navigate familiar indoor environments (e.g., home or care facility).

The module uses visual computer vision landmarks (ArUco markers) positioned at key locations (e.g., entrance, corridor, dining room, bedroom) to identify the user's current landmark and calculates an optimal walkable route to a chosen destination using Breadth-First Search (BFS). Spoken step-by-step instructions are delivered through the `VoiceAssistant` engine.

---

## 2. Architecture & File Structure

```text
CogniSight/
├── app/
│   ├── navigation/
│   │   ├── __init__.py
│   │   ├── indoor_navigation.py     # Graph definition, validation, BFS routing & instruction generation
│   │   ├── landmark_detector.py     # OpenCV ArUco detector (DICT_4X4_50) & LandmarkTracker debouncer
│   │   ├── generate_markers.py      # Script to render print-ready 400x400 PNG marker images
│   │   ├── test_landmarks.py        # Real-time webcam ArUco landmark recognition test
│   │   ├── test_live_navigation.py  # Full live interactive webcam + BFS + sequential voice assistant
│   │   └── README.md                # This comprehensive module guide
│   │
│   ├── api/
│   │   ├── indoor_routes.py         # FastAPI endpoints for indoor mapping and routing
│   │   └── schemas.py               # Pydantic DTOs (IndoorRouteRequest, IndoorRouteResponse, etc.)
│   │
│   └── voice/
│       └── voice_assistant.py       # Non-blocking TTS engine with speak_sequence() and clear_queue()
│
├── markers/                         # Generated ArUco marker PNGs with quiet-zone borders
│   ├── 10_entrance.png
│   ├── 20_corridor.png
│   ├── 30_dining_room.png
│   └── 40_bedroom.png
│
└── tests/
    ├── test_indoor_navigation.py    # 20 automated unit tests (BFS, tracker, markers, speech queues)
    └── test_indoor_api.py           # 12 automated API tests (GET map, POST route, error handling)
```

---

## 3. Marker IDs & Indoor Location Mapping

The system uses the standard OpenCV ArUco `DICT_4X4_50` dictionary:

| ArUco Marker ID | Internal Location Key | Display Name | Role in Layout |
| :--- | :--- | :--- | :--- |
| **10** | `entrance` | Entrance | Main entry point |
| **20** | `corridor` | Main corridor | Central transit junction |
| **30** | `dining_room` | Dining room | Common dining area |
| **40** | `bedroom` | Bedroom | Private living space |

Any marker ID outside this table is reported as an unknown landmark without triggering spurious route announcements or crashing.

---

## 4. Indoor Graph & Routing Algorithm

The indoor environment is modeled as an unweighted undirected graph in `app/navigation/indoor_navigation.py`:

```text
       [10: Entrance]
             │
             ▼
    [20: Main corridor] ◄───► [30: Dining room]
             ▲
             │
             ▼
      [40: Bedroom]
```

- **Algorithm**: Breadth-First Search (BFS) is executed on the adjacency graph to guarantee the shortest walkable path in terms of transit edges.
- **Validation**: `validate_indoor_map()` guarantees graph integrity (no dangling neighbors, bidirectional symmetry).
- **Normalization**: `normalize_location()` normalizes user inputs across casing, spaces, underscores, hyphens, and human-readable display names (e.g., `"Dining Room"` $\rightarrow$ `"dining_room"`).
- **Same Location Handling**: If start and destination match, the system returns a 0-step route and announces `"You are already at your destination: {name}."`

---

## 5. Voice Sequencing & Missing Direction Fix

### The Root Cause of Missing Voice Directions
In the original implementation, `VoiceAssistant.speak()` applied a default 5.0-second rate-limiting cooldown (`settings.SPEECH_COOLDOWN_SECONDS`) intended for face recognition reminders. When route directions were iterated in a fast `for` loop:
1. `voice.speak(starting_location)` locked the cooldown timer.
2. Immediate subsequent calls for `route["instructions"]` occurred within milliseconds.
3. Every subsequent direction evaluated `elapsed < cooldown_seconds`, returned `False`, and was silently dropped.

### The Solution Implemented
1. Added `speak_sequence(utterances: List[str], force: bool = True)` to `VoiceAssistant`. By using `force=True`, each route step is enqueued directly into the background worker thread FIFO queue without being dropped by cooldown timers.
2. Added `clear_queue()` to flush outdated route audio when the user reaches a destination or cancels navigation.
3. Added `LandmarkTracker` with multi-frame temporal confirmation (`confirmation_frames=3`) and debounce logic. A stationary camera viewing the same marker reports `is_new_transition=False`, preventing duplicate speech loops.

---

## 6. How to Run the Module (Windows PowerShell Commands)

All commands should be executed from the project root: `C:\Users\Archisha Goel\OneDrive\Desktop\D\CogniSight`

### A. Generate or Re-generate Marker Images
```powershell
.\.venv\Scripts\python.exe app\navigation\generate_markers.py
```
Generated PNG files are saved to the `markers/` folder with a 50-pixel white border (quiet zone) for easy printing or mobile screen display.

### B. Run Automated Pytest Suite
Run the 32 dedicated indoor navigation and indoor API tests:
```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_indoor_navigation.py tests/test_indoor_api.py -v
```

Run the entire CogniSight test suite (Face Recognition + Memory + Indoor Navigation):
```powershell
.\.venv\Scripts\python.exe -m pytest tests/ -v
```
*Current test suite result: 58 passed, 1 warning.*

### C. Test Landmark Detection with Webcam
```powershell
.\.venv\Scripts\python.exe app\navigation\test_landmarks.py
```
- Hold up any generated marker (IDs 10, 20, 30, or 40) or display it on a phone screen.
- Press `Q` in the window to quit.

### D. Run Live Interactive Navigation Demonstration
```powershell
.\.venv\Scripts\python.exe app\navigation\test_live_navigation.py
```
1. Type the desired destination (e.g., `bedroom`, `dining_room`, or `corridor`).
2. Show a marker to the webcam.
3. Upon 3 consecutive confirmation frames, the system announces:
   - Starting landmark identified.
   - Ordered route transitions.
   - Arrival at destination landmark.
4. Press `C` in the camera window to enter a new destination, or `Q` to exit.

### E. Start FastAPI Backend Server
```powershell
.\.venv\Scripts\uvicorn.exe app.main:app --reload --host 127.0.0.1 --port 8000
```
Interactive Swagger documentation is available at: **`http://127.0.0.1:8000/docs`**

---

## 7. REST API Endpoints & Sample Payloads

### 1. Get Indoor Map
- **Endpoint**: `GET /api/v1/indoor/map`
- **Response**: `200 OK`
```json
{
  "locations": {
    "entrance": "Entrance",
    "corridor": "Main corridor",
    "dining_room": "Dining room",
    "bedroom": "Bedroom"
  },
  "marker_locations": {
    "10": "entrance",
    "20": "corridor",
    "30": "dining_room",
    "40": "bedroom"
  },
  "connections": {
    "entrance": ["corridor"],
    "corridor": ["entrance", "dining_room", "bedroom"],
    "dining_room": ["corridor"],
    "bedroom": ["corridor"]
  },
  "note": "Sample development map, not a real building map."
}
```

### 2. Calculate Route Between Locations
- **Endpoint**: `POST /api/v1/indoor/route`
- **Request Body**:
```json
{
  "start": "entrance",
  "destination": "bedroom"
}
```
- **Response**: `200 OK`
```json
{
  "start": "Entrance",
  "destination": "Bedroom",
  "route": [
    "Entrance",
    "Main corridor",
    "Bedroom"
  ],
  "route_nodes": [
    "entrance",
    "corridor",
    "bedroom"
  ],
  "instructions": [
    "Entrance identified.",
    "Follow the mapped route to Main corridor.",
    "Continue toward Bedroom.",
    "The route has reached the Bedroom landmark."
  ],
  "total_steps": 2,
  "start_marker_id": null,
  "location_source": null,
  "status": "success"
}
```

### 3. Calculate Route From Scanned Marker ID
- **Endpoint**: `POST /api/v1/indoor/route-from-marker`
- **Request Body**:
```json
{
  "marker_id": 10,
  "destination": "bedroom"
}
```
- **Response**: `200 OK`
```json
{
  "start": "Entrance",
  "destination": "Bedroom",
  "route": [
    "Entrance",
    "Main corridor",
    "Bedroom"
  ],
  "route_nodes": [
    "entrance",
    "corridor",
    "bedroom"
  ],
  "instructions": [
    "Entrance identified.",
    "Follow the mapped route to Main corridor.",
    "Continue toward Bedroom.",
    "The route has reached the Bedroom landmark."
  ],
  "total_steps": 2,
  "start_marker_id": 10,
  "location_source": "ArUco landmark mapping",
  "status": "success"
}
```

### 4. Error Responses
- **Unknown marker ID**: Returns `400 Bad Request`
```json
{
  "detail": "Unknown indoor marker ID: 99. Configured markers: [10, 20, 30, 40]"
}
```
- **Unknown destination**: Returns `400 Bad Request`
```json
{
  "detail": "Unknown indoor location: 'garden'. Supported: bedroom, corridor, dining_room, entrance"
}
```

---

## 8. What This Module Does NOT Establish (Limitations & Safety)

For university capstone presentation and clinical assistive honesty:
- **No Continuous Localization**: The system knows position *only* when an ArUco marker is within the camera's field of view. It does not perform dead-reckoning, visual odometry, or SLAM between markers.
- **No Obstacle Detection**: The system does NOT detect furniture, stairs, open doors, or people in the path.
- **No Orientation Guidance**: Because the graph is topological and unweighted without compass or metric turn metadata, instructions use landmark transitions rather than metric turn angles (e.g. "turn 90 degrees left").
- **Assumed Environment**: The map is a predefined configuration representing a known indoor space; it does not automatically map unknown buildings.

---

## 9. Troubleshooting

1. **Webcam Not Detected / Permission Denied**:
   - Verify camera privacy permissions in Windows Settings.
   - Ensure other programs (Teams, Zoom, browser tabs) have closed the camera.
2. **Marker Not Detected**:
   - Check lighting; avoid bright specular glare directly reflecting on the printed marker.
   - Ensure the white border (quiet zone) around the marker is visible.
3. **Voice Audio Missing or Silent**:
   - Check system speaker volume and default output device.
   - If running headless or in test environments without audio drivers, `VoiceAssistant` automatically falls back to structured logging without crashing.
