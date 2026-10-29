# CogniSight — Complete End-to-End Visual Understanding & Voice Assistance System

CogniSight is an AI-assisted visual understanding and personalized memory system designed for cognitive assistance.

---

## Complete Pipeline Architecture

```text
┌───────────────────────────┐
│     Webcam Live Feed      │
└─────────────┬─────────────┘
              │
              ▼
┌───────────────────────────┐
│     Face Detector         │  <-- InsightFace SCRFD
└─────────────┬─────────────┘
              │
              ▼
┌───────────────────────────┐
│     Face Embedder         │  <-- ArcFace 512-D L2 Vector
└─────────────┬─────────────┘
              │
              ▼
┌───────────────────────────┐
│     Similarity Matcher    │  <-- L2 Cosine Dot Product against SQLite
└─────────────┬─────────────┘
              │
              ▼
┌───────────────────────────┐
│     Person Memory         │  <-- Relationships, Personal Notes & Last Seen
└─────────────┬─────────────┘
              │
              ▼
┌───────────────────────────┐
│     Context Engine        │  <-- Synthesizes perception + memory into state
└─────────────┬─────────────┘
              │
              ▼
┌───────────────────────────┐
│     Voice Assistant       │  <-- Non-blocking Text-To-Speech (pyttsx3)
└───────────────────────────┘
```

---

## Core Features & Modules Built

1. **Face Detection**: Fast SCRFD detection producing bounding boxes `[x1, y1, x2, y2]` and detection confidence scores.
2. **Face Embedding**: ArcFace MobileFaceNet model producing 512-dimensional float32 L2-normalized embeddings.
3. **Person Enrollment**: Automated voice microphone enrollment and quality-checked sample validation ($\ge 80\text{px}$, confidence $\ge 60\%$).
4. **Database Storage**: SQLAlchemy 2.0 ORM over SQLite storing binary-serialized 512-D vectors, Person Profiles, and Interaction Logs.
5. **Similarity Matcher**: Fast dot-product Cosine Similarity with configurable decision thresholding (`FACE_RECOGNITION_THRESHOLD=0.50`).
6. **Real-Time Recognition & Stability**: Multi-face spatial tracking with temporal smoothing (rolling majority voting over $K=5$ frames) and frame-skipping performance optimization (`RECOGNITION_INTERVAL=3`).
7. **Person Memory**: Stores relationships (e.g. "Sister / Caregiver / Friend"), personal memory notes ("Loves tea with 2 sugars"), and automatically updates `last_seen` timestamps.
8. **Context Engine**: Synthesizes real-time perception with memory into structured headlines, subtexts, and spoken announcements.
9. **Voice Assistant**: Non-blocking Text-To-Speech audio output engine & Web Speech API continuous microphone audio enrollment with periodic 30-second memory reminders.
10. **Interactive Web Dashboard**: Full-featured Web UI (`http://127.0.0.1:8000`) with live MJPEG stream, unknown person voice enrollment, memory profile editor, and API Swagger docs.
11. **Indoor Navigation (Module 2)**: ArUco landmark detection (OpenCV DICT_4X4_50), Breadth-First Search (BFS) graph routing, temporal confirmation tracking, and sequential non-blocking voice directions. Detailed in [Indoor Navigation Guide](file:///app/navigation/README.md).

---

## Project Structure

```text
CogniSight/
│
├── app/
│   ├── main.py                     # FastAPI app entrypoint & OpenAPI docs
│   │
│   ├── config/
│   │   ├── __init__.py
│   │   └── settings.py             # App configuration settings
│   │
│   ├── camera/
│   │   ├── __init__.py
│   │   └── camera.py               # OpenCV video capture stream
│   │
│   ├── face/
│   │   ├── __init__.py
│   │   ├── detector.py             # InsightFace SCRFD face detector
│   │   ├── embedding.py            # ArcFace 512-D embedding generator
│   │   ├── matcher.py              # Cosine similarity matching engine
│   │   ├── recognizer.py           # Master recognition engine with temporal smoothing
│   │   ├── enroll.py               # Quality-checked person enrollment CLI & service
│   │   └── schemas.py              # BoundingBox & RecognitionResult data models
│   │
│   ├── memory/
│   │   ├── __init__.py
│   │   └── memory_service.py       # Memory profile, relationship, & notes service
│   │
│   ├── context/
│   │   ├── __init__.py
│   │   └── context_engine.py       # Perception + Memory Context Synthesis Engine
│   │
│   ├── navigation/
│   │   ├── __init__.py
│   │   ├── indoor_navigation.py    # Graph definition, validation, BFS routing & instructions
│   │   ├── landmark_detector.py    # ArUco detector (DICT_4X4_50) & LandmarkTracker debouncer
│   │   ├── generate_markers.py     # Marker image generation script (PNG)
│   │   ├── test_landmarks.py       # Camera landmark test script
│   │   ├── test_live_navigation.py # Interactive live webcam navigation demonstration
│   │   └── README.md               # Dedicated indoor navigation guide
│   │
│   ├── voice/
│   │   ├── __init__.py
│   │   └── voice_assistant.py      # Non-blocking Text-To-Speech engine (speak_sequence & clear_queue)
│   │
│   ├── database/
│   │   ├── __init__.py
│   │   ├── database.py             # SQLAlchemy engine & sessionmaker
│   │   ├── models.py               # Person, FaceEmbedding, PersonProfile, InteractionLog
│   │   └── repository.py           # Database CRUD repository layer
│   │
│   ├── services/
│   │   ├── __init__.py
│   │   ├── recognition_service.py  # Service layer for recognition & enrollment
│   │   └── cognisight_pipeline.py  # Integrated CogniSight Pipeline Orchestrator
│   │
│   ├── api/
│   │   ├── __init__.py
│   │   ├── routes.py               # Face & memory REST endpoints
│   │   ├── indoor_routes.py        # Indoor navigation endpoints
│   │   └── schemas.py              # API Request/Response DTO models
│   │
│   └── utils/
│       ├── __init__.py
│       └── logging_config.py       # Structured logging setup
│
├── markers/                        # Generated ArUco marker PNGs (10, 20, 30, 40)
│
├── data/                           # SQLite database & outputs
│   └── cognisight.db
│
├── scripts/                        # Standalone runner scripts
│   ├── demo_detector.py
│   ├── demo_embedding.py
│   ├── demo_enrollment.py
│   ├── demo_matcher.py
│   ├── run_webcam_detection.py
│   ├── run_realtime_recognition.py
│   └── run_cognisight_full.py      # Complete system launcher
│
├── tests/                          # Automated Pytest test suite (58 tests)
│   ├── conftest.py
│   ├── test_api.py
│   ├── test_database.py
│   ├── test_detector.py
│   ├── test_embedding.py
│   ├── test_enrollment.py
│   ├── test_indoor_api.py          # 12 indoor navigation REST API tests
│   ├── test_indoor_navigation.py   # 20 indoor routing, BFS, & tracker tests
│   ├── test_matcher.py
│   ├── test_memory_context_voice.py
│   └── test_recognizer.py
│
├── .env                            # Active environment settings
├── .env.example                    # Environment template
├── .gitignore                      # Git exclusion rules
├── requirements.txt                # Package dependencies
└── README.md                       # Comprehensive documentation
```

---

## Execution Guide

### 1. Run Complete Integrated System (Webcam + Memory + Voice)
```powershell
.\.venv\Scripts\python.exe -m scripts.run_cognisight_full
```

### 2. Enroll a Person (CLI)
```powershell
.\.venv\Scripts\python.exe -m app.face.enroll --name "John" --samples 10
```

### 3. Run FastAPI Backend Server
```powershell
.\.venv\Scripts\uvicorn.exe app.main:app --reload --host 127.0.0.1 --port 8000
```
Open **`http://127.0.0.1:8000/docs`** to manage profiles, upload images, and trigger voice announcements!

### 4. Run Live Indoor Navigation (Module 2)
```powershell
.\.venv\Scripts\python.exe app\navigation\test_live_navigation.py
```

### 5. Generate Indoor ArUco Markers
```powershell
.\.venv\Scripts\python.exe app\navigation\generate_markers.py
```

### 6. Run Pytest Suite
```powershell
.\.venv\Scripts\pytest.exe tests/ -v
```
**Status:** `58 passed, 1 warning`

---

## REST API Endpoints Summary

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/api/v1/health` | Service health status & model configuration |
| `GET` | `/api/v1/persons` | List all enrolled person profiles with memory |
| `GET` | `/api/v1/persons/{id}` | Get specific person details and memory notes |
| `POST` | `/api/v1/persons` | Create a new person profile |
| `PUT` | `/api/v1/persons/{id}/memory` | Update relationship and memory notes |
| `DELETE` | `/api/v1/persons/{id}` | Delete person profile and associated embeddings |
| `POST` | `/api/v1/recognition/predict` | Face recognition on uploaded image file |
| `POST` | `/api/v1/enrollment/upload` | Batch enrollment from uploaded image files |
| `POST` | `/api/v1/voice/speak` | Trigger Text-To-Speech voice announcement |
| `GET` | `/api/v1/indoor/map` | Get indoor landmark layout & marker mappings |
| `POST` | `/api/v1/indoor/route` | Calculate shortest indoor route between locations |
| `POST` | `/api/v1/indoor/route-from-marker` | Calculate indoor route from scanned ArUco marker ID |
