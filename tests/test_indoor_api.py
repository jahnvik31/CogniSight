from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from app.api.indoor_routes import router as indoor_router

# Create an isolated test FastAPI application mounting the indoor navigation router
app = FastAPI(title="CogniSight Indoor API Test Harness")
app.include_router(indoor_router, prefix="/api/v1")
client = TestClient(app)


# ---------------------------------------------------------------------------
# GET /api/v1/indoor/map
# ---------------------------------------------------------------------------

def test_get_indoor_map():
    """Verify GET /api/v1/indoor/map returns configured landmarks, connections, and markers."""
    response = client.get("/api/v1/indoor/map")
    assert response.status_code == 200

    data = response.json()
    assert "locations" in data
    assert "marker_locations" in data
    assert "connections" in data
    assert "note" in data

    # Verify landmarks
    assert data["locations"]["entrance"] == "Entrance"
    assert data["locations"]["corridor"] == "Main corridor"
    assert data["locations"]["dining_room"] == "Dining room"
    assert data["locations"]["bedroom"] == "Bedroom"

    # Verify marker mappings
    marker_map = data["marker_locations"]
    assert marker_map["10"] == "entrance" or marker_map.get(10) == "entrance"
    assert marker_map["20"] == "corridor" or marker_map.get(20) == "corridor"
    assert marker_map["30"] == "dining_room" or marker_map.get(30) == "dining_room"
    assert marker_map["40"] == "bedroom" or marker_map.get(40) == "bedroom"


# ---------------------------------------------------------------------------
# POST /api/v1/indoor/route
# ---------------------------------------------------------------------------

def test_calculate_route_valid():
    """Test POST /api/v1/indoor/route with valid start and destination."""
    payload = {"start": "entrance", "destination": "bedroom"}
    response = client.post("/api/v1/indoor/route", json=payload)
    assert response.status_code == 200

    data = response.json()
    assert data["start"] == "Entrance"
    assert data["destination"] == "Bedroom"
    assert data["route"] == ["Entrance", "Main corridor", "Bedroom"]
    assert data["route_nodes"] == ["entrance", "corridor", "bedroom"]
    assert data["total_steps"] == 2
    assert data["status"] == "success"
    assert len(data["instructions"]) == 4


def test_calculate_route_with_display_name_and_spaces():
    """Verify route calculation accepts display names with spaces."""
    payload = {"start": "Dining room", "destination": "Bedroom"}
    response = client.post("/api/v1/indoor/route", json=payload)
    assert response.status_code == 200

    data = response.json()
    assert data["start"] == "Dining room"
    assert data["destination"] == "Bedroom"
    assert data["route"] == ["Dining room", "Main corridor", "Bedroom"]


def test_calculate_route_identical_start_and_destination():
    """Test POST /api/v1/indoor/route when start == destination."""
    payload = {"start": "bedroom", "destination": "bedroom"}
    response = client.post("/api/v1/indoor/route", json=payload)
    assert response.status_code == 200

    data = response.json()
    assert data["start"] == "Bedroom"
    assert data["destination"] == "Bedroom"
    assert data["total_steps"] == 0
    assert data["instructions"] == ["You are already at your destination: Bedroom."]


def test_calculate_route_unknown_start():
    """Test POST /api/v1/indoor/route with invalid start returns 400 Bad Request."""
    payload = {"start": "garage", "destination": "bedroom"}
    response = client.post("/api/v1/indoor/route", json=payload)
    assert response.status_code == 400
    assert "Unknown indoor location" in response.json()["detail"]


def test_calculate_route_unknown_destination():
    """Test POST /api/v1/indoor/route with invalid destination returns 400 Bad Request."""
    payload = {"start": "entrance", "destination": "rooftop"}
    response = client.post("/api/v1/indoor/route", json=payload)
    assert response.status_code == 400
    assert "Unknown indoor location" in response.json()["detail"]


def test_calculate_route_malformed_request():
    """Test POST /api/v1/indoor/route with missing fields returns 422 Unprocessable Entity."""
    response = client.post("/api/v1/indoor/route", json={"start": "entrance"})
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# POST /api/v1/indoor/route-from-marker
# ---------------------------------------------------------------------------

def test_route_from_marker_valid():
    """Test POST /api/v1/indoor/route-from-marker with marker 10 (entrance)."""
    payload = {"marker_id": 10, "destination": "bedroom"}
    response = client.post("/api/v1/indoor/route-from-marker", json=payload)
    assert response.status_code == 200

    data = response.json()
    assert data["start"] == "Entrance"
    assert data["destination"] == "Bedroom"
    assert data["start_marker_id"] == 10
    assert data["location_source"] == "ArUco landmark mapping"
    assert data["route"] == ["Entrance", "Main corridor", "Bedroom"]
    assert data["total_steps"] == 2
    assert data["status"] == "success"


def test_route_from_marker_dining_room():
    """Test POST /api/v1/indoor/route-from-marker with marker 30 (dining_room)."""
    payload = {"marker_id": 30, "destination": "corridor"}
    response = client.post("/api/v1/indoor/route-from-marker", json=payload)
    assert response.status_code == 200

    data = response.json()
    assert data["start"] == "Dining room"
    assert data["destination"] == "Main corridor"
    assert data["route"] == ["Dining room", "Main corridor"]
    assert data["total_steps"] == 1


def test_route_from_marker_unknown_id():
    """Test POST /api/v1/indoor/route-from-marker with unmapped marker returns 400 Bad Request."""
    payload = {"marker_id": 999, "destination": "bedroom"}
    response = client.post("/api/v1/indoor/route-from-marker", json=payload)
    assert response.status_code == 400
    assert "Unknown indoor marker ID: 999" in response.json()["detail"]


def test_route_from_marker_invalid_destination():
    """Test POST /api/v1/indoor/route-from-marker with invalid destination returns 400 Bad Request."""
    payload = {"marker_id": 10, "destination": "secret_room"}
    response = client.post("/api/v1/indoor/route-from-marker", json=payload)
    assert response.status_code == 400
    assert "Unknown indoor location" in response.json()["detail"]


def test_route_from_marker_invalid_type():
    """Test POST /api/v1/indoor/route-from-marker with invalid type returns 422."""
    payload = {"marker_id": "not-an-int", "destination": "bedroom"}
    response = client.post("/api/v1/indoor/route-from-marker", json=payload)
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# GET /api/v1/indoor/scan-current-location
# ---------------------------------------------------------------------------

def test_scan_current_location_endpoint():
    """Verify GET /api/v1/indoor/scan-current-location returns valid structured response."""
    response = client.get("/api/v1/indoor/scan-current-location")
    assert response.status_code == 200
    data = response.json()
    assert "detected" in data
    assert "message" in data
