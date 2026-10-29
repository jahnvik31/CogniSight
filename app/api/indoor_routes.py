import cv2
from fastapi import APIRouter, File, HTTPException, UploadFile, status
import numpy as np

from app.api.schemas import (
    IndoorMapResponse,
    IndoorRouteRequest,
    IndoorRouteResponse,
    MarkerRouteRequest,
)
from app.camera.camera import Camera
from app.navigation.indoor_navigation import (
    INDOOR_MAP,
    find_indoor_route,
)
from app.navigation.landmark_detector import (
    MARKER_LOCATIONS,
    IndoorLandmarkDetector,
)

router = APIRouter(tags=["Indoor Navigation"])
detector = IndoorLandmarkDetector()


@router.get(
    "/indoor/map",
    response_model=IndoorMapResponse,
    summary="Get Indoor Landmarks Map",
    description="Returns configured indoor landmarks, marker ID mappings, and structural connections.",
)
def get_indoor_map():
    return {
        "locations": {
            key: value["name"] for key, value in INDOOR_MAP.items()
        },
        "marker_locations": {
            marker_id: location
            for marker_id, location in MARKER_LOCATIONS.items()
        },
        "connections": {
            key: list(value.get("neighbors", []))
            for key, value in INDOOR_MAP.items()
        },
        "note": "Sample development map, not a real building map.",
    }


@router.post(
    "/indoor/route",
    response_model=IndoorRouteResponse,
    summary="Calculate Route Between Locations",
    description="Calculates shortest indoor path and sequential directions between start and destination.",
)
def calculate_indoor_route(payload: IndoorRouteRequest):
    try:
        return find_indoor_route(payload.start, payload.destination)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc


@router.post(
    "/indoor/route-from-marker",
    response_model=IndoorRouteResponse,
    summary="Calculate Route from ArUco Marker ID",
    description="Resolves marker ID to starting landmark, then computes route to destination.",
)
def calculate_route_from_marker(payload: MarkerRouteRequest):
    start = MARKER_LOCATIONS.get(payload.marker_id)

    if start is None:
        valid_markers = sorted(list(MARKER_LOCATIONS.keys()))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown indoor marker ID: {payload.marker_id}. Configured markers: {valid_markers}",
        )

    try:
        route = find_indoor_route(start, payload.destination)
        route["start_marker_id"] = payload.marker_id
        route["location_source"] = "ArUco landmark mapping"
        return route
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc


@router.get(
    "/indoor/scan-current-location",
    summary="Scan Current Location from Live Camera",
    description="Inspects active webcam frame to detect printed ArUco landmark markers.",
)
def scan_current_location():
    """Scans the active camera feed to detect which ArUco landmark is currently visible."""
    frame = Camera.get_latest_frame()

    if frame is None or getattr(frame, "size", 0) == 0:
        return {
            "detected": False,
            "marker_id": None,
            "location": None,
            "display_name": None,
            "message": "Webcam frame unavailable. Ensure camera stream is active.",
        }

    detections = detector.detect(frame, include_unknown=True)
    if not detections:
        return {
            "detected": False,
            "marker_id": None,
            "location": None,
            "display_name": None,
            "message": "No marker visible in camera frame. Show an ArUco marker (IDs 10, 20, 30, 40).",
        }

    first = detections[0]
    mid = first["marker_id"]
    if first.get("known"):
        loc_key = first["location"]
        loc_name = INDOOR_MAP.get(loc_key, {}).get("name", loc_key.replace("_", " ").title())
        return {
            "detected": True,
            "marker_id": mid,
            "location": loc_key,
            "display_name": loc_name,
            "message": f"Detected Marker {mid}: {loc_name}",
        }

    return {
        "detected": False,
        "marker_id": mid,
        "location": None,
        "display_name": None,
        "message": f"Detected unknown marker ID {mid}. Configured markers: {sorted(list(MARKER_LOCATIONS.keys()))}",
    }


@router.post(
    "/indoor/scan-image",
    summary="Detect Landmark from Image File",
    description="Scans an uploaded image frame for ArUco markers.",
)
async def scan_marker_image(file: UploadFile = File(...)):
    contents = await file.read()
    nparr = np.frombuffer(contents, np.uint8)
    frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

    if frame is None:
        raise HTTPException(status_code=400, detail="Could not decode image.")

    detections = detector.detect(frame, include_unknown=True)
    if not detections:
        return {
            "detected": False,
            "marker_id": None,
            "location": None,
            "display_name": None,
            "message": "No marker detected in image.",
        }

    first = detections[0]
    mid = first["marker_id"]
    if first.get("known"):
        loc_key = first["location"]
        loc_name = INDOOR_MAP.get(loc_key, {}).get("name", loc_key.replace("_", " ").title())
        return {
            "detected": True,
            "marker_id": mid,
            "location": loc_key,
            "display_name": loc_name,
            "message": f"Detected Marker {mid}: {loc_name}",
        }

    return {
        "detected": False,
        "marker_id": mid,
        "location": None,
        "display_name": None,
        "message": f"Unknown marker ID {mid}.",
    }
