from contextlib import asynccontextmanager
from pathlib import Path
import cv2
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, StreamingResponse

from app.api.routes import router as api_router
from app.api.indoor_routes import router as indoor_router
from app.camera.camera import Camera
from app.config.settings import settings
from app.database.database import SessionLocal, init_db
from app.services.cognisight_pipeline import CogniSightPipeline
from app.utils.logging_config import logger

STATIC_DIR = Path(__file__).parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan handler for FastAPI application startup and shutdown events."""
    logger.info("Initializing CogniSight database on startup...")
    init_db()
    logger.info("CogniSight API & Web Prototype Server successfully initialized.")
    yield
    logger.info("Shutting down CogniSight API server...")


app = FastAPI(
    title="CogniSight Web Prototype & API",
    description=(
        "CogniSight Visual Understanding & Personalized Memory System. "
        "Provides interactive Web Dashboard, live camera MJPEG feed, and REST API."
    ),
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount API v1 router
app.include_router(api_router, prefix="/api/v1")
app.include_router(indoor_router, prefix="/api/v1")


def generate_video_stream():
    """Generator streaming live camera frames annotated with CogniSight pipeline overlays."""
    logger.info("Starting live camera video stream generator for web feed...")
    pipeline = CogniSightPipeline()
    camera = Camera()

    if not camera.start():
        logger.error("Could not open camera stream for MJPEG video feed.")
        return

    db = SessionLocal()
    try:
        while True:
            ret, frame = camera.read_frame()
            if not ret or frame is None:
                break

            output_frame, context = pipeline.process_frame_full_pipeline(
                frame=frame, db=db, speak_voice=True
            )

            ret_enc, buffer = cv2.imencode(".jpg", output_frame)
            if not ret_enc:
                continue

            frame_bytes = buffer.tobytes()
            yield (
                b"--frame\r\n"
                b"Content-Type: image/jpeg\r\n\r\n" + frame_bytes + b"\r\n"
            )
    finally:
        camera.release()
        pipeline.shutdown()
        db.close()


@app.get("/", response_class=HTMLResponse)
def index_dashboard():
    """Serves CogniSight Interactive Web Prototype Dashboard."""
    html_file = STATIC_DIR / "index.html"
    if html_file.exists():
        return HTMLResponse(content=html_file.read_text(encoding="utf-8"))
    return HTMLResponse("<h2>CogniSight Web UI template file not found.</h2>")


@app.get("/video_feed")
def video_feed():
    """Serves live MJPEG camera video stream annotated with face recognition & context."""
    return StreamingResponse(
        generate_video_stream(),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )
