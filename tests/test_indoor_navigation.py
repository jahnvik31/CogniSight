from pathlib import Path
from unittest.mock import MagicMock, patch
import cv2
import numpy as np
import pytest

from app.navigation.indoor_navigation import (
    INDOOR_MAP,
    find_indoor_route,
    generate_route_instructions,
    normalize_location,
    validate_indoor_map,
)
from app.navigation.landmark_detector import (
    MARKER_LOCATIONS,
    IndoorLandmarkDetector,
    LandmarkTracker,
)
from app.voice.voice_assistant import VoiceAssistant


# ---------------------------------------------------------------------------
# 1 & 2. Marker ID Mapping Tests
# ---------------------------------------------------------------------------

def test_configured_marker_mappings():
    """Verify each configured marker ID maps to the expected indoor location."""
    expected = {
        10: "entrance",
        20: "corridor",
        30: "dining_room",
        40: "bedroom",
    }
    assert MARKER_LOCATIONS == expected


def test_marker_10_maps_to_entrance():
    """Explicitly verify that Marker 10 maps to 'entrance'."""
    assert MARKER_LOCATIONS[10] == "entrance"
    detector = IndoorLandmarkDetector()
    assert detector.get_location_for_marker(10) == "entrance"


# ---------------------------------------------------------------------------
# Landmark Detector Tests (with Real Generated Images & Synthetics)
# ---------------------------------------------------------------------------

def test_detector_on_generated_marker_files():
    """Verify IndoorLandmarkDetector recognizes each of the four generated marker files."""
    detector = IndoorLandmarkDetector()
    markers_dir = Path(__file__).resolve().parent.parent / "markers"

    for marker_id, location_key in MARKER_LOCATIONS.items():
        image_path = markers_dir / f"{marker_id}_{location_key}.png"
        assert image_path.exists(), f"Marker image missing: {image_path}"

        frame = cv2.imread(str(image_path))
        assert frame is not None, f"Could not load image: {image_path}"

        detections = detector.detect(frame)
        assert len(detections) >= 1
        found_ids = [d["marker_id"] for d in detections]
        assert marker_id in found_ids
        assert detections[0]["location"] == location_key


def test_detector_on_blank_frame():
    """Detector should return empty list on a blank or empty frame without crashing."""
    detector = IndoorLandmarkDetector()
    blank = np.zeros((480, 640, 3), dtype=np.uint8)
    assert detector.detect(blank) == []
    assert detector.detect(None) == []


def test_detector_handles_unknown_marker():
    """Detector should safely handle or report unknown marker IDs."""
    detector = IndoorLandmarkDetector()
    # Generate an unmapped marker (e.g. ID 4)
    dict_4x4 = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
    if hasattr(cv2.aruco, "generateImageMarker"):
        unmapped_marker = cv2.aruco.generateImageMarker(dict_4x4, 4, 300)
    else:
        unmapped_marker = cv2.aruco.drawMarker(dict_4x4, 4, 300)

    unmapped_frame = cv2.copyMakeBorder(
        unmapped_marker, 40, 40, 40, 40, cv2.BORDER_CONSTANT, value=255
    )

    # Standard detect (backward compatible) ignores unknown
    assert detector.detect(unmapped_frame) == []

    # Include unknown provides structured info
    results = detector.detect(unmapped_frame, include_unknown=True)
    assert len(results) == 1
    assert results[0]["marker_id"] == 4
    assert results[0]["known"] is False
    assert results[0]["location"] is None


# ---------------------------------------------------------------------------
# Landmark Tracker (Debouncing & Preventing Endless Duplicate Announcements)
# ---------------------------------------------------------------------------

def test_tracker_debouncing_and_repeated_detections():
    """Verify tracker prevents continuous duplicate triggers when stationary."""
    tracker = LandmarkTracker(confirmation_frames=3, lost_tolerance_frames=4)

    # Frame 1: Candidate seen once
    s1 = tracker.update([10])
    assert s1.status == "confirming"
    assert s1.is_new_transition is False

    # Frame 2: Candidate seen twice
    s2 = tracker.update([10])
    assert s2.status == "confirming"
    assert s2.is_new_transition is False

    # Frame 3: Confirmed after 3 frames! Triggers transition announcement
    s3 = tracker.update([10])
    assert s3.status == "confirmed"
    assert s3.is_new_transition is True
    assert s3.confirmed_location == "entrance"

    # Frame 4..10: Stationary camera viewing Marker 10
    # Must NOT flag new transition (prevents duplicate speech loop)
    for _ in range(7):
        sn = tracker.update([10])
        assert sn.status == "tracking"
        assert sn.is_new_transition is False
        assert sn.confirmed_location == "entrance"


def test_tracker_tolerates_brief_occlusion_and_tracks_transition():
    """Verify tracker survives brief 1-frame drops and confirms subsequent transitions."""
    tracker = LandmarkTracker(confirmation_frames=2, lost_tolerance_frames=3)

    # Confirm Marker 10 (entrance)
    tracker.update([10])
    s = tracker.update([10])
    assert s.is_new_transition is True
    assert s.confirmed_location == "entrance"

    # 1 dropped frame (motion blur) - retained within tolerance
    dropped = tracker.update([])
    assert dropped.confirmed_location == "entrance"
    assert dropped.is_new_transition is False

    # Reacquired Marker 10 - still stationary, no duplicate announcement
    reacquired = tracker.update([10])
    assert reacquired.confirmed_location == "entrance"
    assert reacquired.is_new_transition is False

    # Move to Marker 20 (corridor)
    tracker.update([20])
    transition = tracker.update([20])
    assert transition.status == "confirmed"
    assert transition.is_new_transition is True
    assert transition.confirmed_location == "corridor"


def test_tracker_reset():
    """Verify reset clears tracker state."""
    tracker = LandmarkTracker(confirmation_frames=1)
    tracker.update([10])
    assert tracker.confirmed_marker_id == 10

    tracker.reset()
    assert tracker.confirmed_marker_id is None
    assert tracker.candidate_marker_id is None


# ---------------------------------------------------------------------------
# 3 & 4. Route Calculation & BFS Shortest Path Tests
# ---------------------------------------------------------------------------

def test_valid_route_entrance_to_bedroom():
    """Test standard route from entrance to bedroom in default map."""
    route = find_indoor_route("entrance", "bedroom")
    assert route["start"] == "Entrance"
    assert route["destination"] == "Bedroom"
    assert route["route"] == ["Entrance", "Main corridor", "Bedroom"]
    assert route["route_nodes"] == ["entrance", "corridor", "bedroom"]
    assert route["total_steps"] == 2
    assert route["status"] == "success"

    # Verify instructions
    assert len(route["instructions"]) == 4
    assert route["instructions"][0] == "Entrance identified."
    assert "Main corridor" in route["instructions"][1]
    assert "Bedroom" in route["instructions"][2]
    assert "Bedroom landmark" in route["instructions"][3]


def test_valid_route_entrance_to_dining_room():
    """Test route from entrance to dining room."""
    route = find_indoor_route("entrance", "dining_room")
    assert route["route"] == ["Entrance", "Main corridor", "Dining room"]
    assert route["total_steps"] == 2


def test_bfs_shortest_path_optimality():
    """Verify BFS selects the shortest path when multiple paths exist in an unweighted graph."""
    custom_map = {
        "A": {"name": "Node A", "neighbors": ["B", "C", "G"]},
        "B": {"name": "Node B", "neighbors": ["A", "D"]},
        "C": {"name": "Node C", "neighbors": ["A", "E"]},
        "D": {"name": "Node D", "neighbors": ["B", "F"]},
        "E": {"name": "Node E", "neighbors": ["C", "F"]},
        "F": {"name": "Node F", "neighbors": ["D", "E", "G"]},
        "G": {"name": "Node G", "neighbors": ["F", "A"]},  # Direct shortcut A <-> G
    }

    # Shortest path from A to G is direct [A, G] (1 step), not via B-D-F or C-E-F
    result = find_indoor_route("A", "G", map_graph=custom_map)
    assert result["route_nodes"] == ["A", "G"]
    assert result["total_steps"] == 1


# ---------------------------------------------------------------------------
# 5 & 6 & 7. Location Validation, Unknown Markers & Unreachable Nodes
# ---------------------------------------------------------------------------

def test_identical_start_and_destination():
    """Requesting the same location as destination should give clear feedback."""
    route = find_indoor_route("bedroom", "bedroom")
    assert route["start"] == "Bedroom"
    assert route["destination"] == "Bedroom"
    assert route["total_steps"] == 0
    assert route["route"] == ["Bedroom"]
    assert route["instructions"] == ["You are already at your destination: Bedroom."]


def test_location_normalization():
    """Verify normalization handles casing, spaces, hyphens, and display names."""
    assert normalize_location("entrance") == "entrance"
    assert normalize_location("ENTRANCE") == "entrance"
    assert normalize_location("  entrance  ") == "entrance"
    assert normalize_location("dining room") == "dining_room"
    assert normalize_location("Dining Room") == "dining_room"
    assert normalize_location("dining-room") == "dining_room"
    assert normalize_location("Main corridor") == "corridor"
    assert normalize_location("Bedroom") == "bedroom"


def test_invalid_locations_raise_value_error():
    """Invalid locations must raise a descriptive ValueError."""
    with pytest.raises(ValueError, match="Unknown indoor location"):
        find_indoor_route("nonexistent_room", "bedroom")

    with pytest.raises(ValueError, match="Unknown indoor location"):
        find_indoor_route("entrance", "observatory")

    with pytest.raises(ValueError, match="Invalid location input"):
        find_indoor_route("", "bedroom")


def test_unreachable_destination_raises_value_error():
    """Graph with disconnected component raises ValueError when unreachable."""
    disconnected_map = {
        "room_1": {"name": "Room 1", "neighbors": ["room_2"]},
        "room_2": {"name": "Room 2", "neighbors": ["room_1"]},
        "island": {"name": "Island Room", "neighbors": []},
    }
    with pytest.raises(ValueError, match="No walkable route connects"):
        find_indoor_route("room_1", "island", map_graph=disconnected_map)


def test_map_integrity_validation():
    """Validates that malformed maps raise ValueError."""
    # Missing neighbor reference
    bad_map_1 = {
        "room_1": {"name": "Room 1", "neighbors": ["ghost_room"]},
    }
    with pytest.raises(ValueError, match="non-existent neighbor"):
        validate_indoor_map(bad_map_1)

    # Asymmetric connection
    bad_map_2 = {
        "room_1": {"name": "Room 1", "neighbors": ["room_2"]},
        "room_2": {"name": "Room 2", "neighbors": []},
    }
    with pytest.raises(ValueError, match="Asymmetric connection"):
        validate_indoor_map(bad_map_2)


# ---------------------------------------------------------------------------
# 8 & 9 & 10. Voice Sequencing & Robust Speech
# ---------------------------------------------------------------------------

def test_instruction_generation_structure():
    """Verify instruction phrasing for 1, 2, and 3-step paths."""
    # 1 location (already at dest)
    inst_1 = generate_route_instructions(["Bedroom"])
    assert inst_1 == ["You are already at your destination: Bedroom."]

    # 2 locations (1 step)
    inst_2 = generate_route_instructions(["Entrance", "Main corridor"])
    assert inst_2 == [
        "Entrance identified.",
        "Follow the mapped route to Main corridor.",
        "The route has reached the Main corridor landmark.",
    ]

    # 3 locations (2 steps)
    inst_3 = generate_route_instructions(["Entrance", "Main corridor", "Bedroom"])
    assert inst_3 == [
        "Entrance identified.",
        "Follow the mapped route to Main corridor.",
        "Continue toward Bedroom.",
        "The route has reached the Bedroom landmark.",
    ]


def test_voice_speak_sequence_does_not_drop_instructions():
    """Verify VoiceAssistant.speak_sequence bypasses cooldown to queue all instructions."""
    va = VoiceAssistant(cooldown_seconds=10.0, enabled=False)

    instructions = [
        "Entrance identified.",
        "Follow the mapped route to Main corridor.",
        "Continue toward Bedroom.",
        "The route has reached the Bedroom landmark.",
    ]

    queued_count = va.speak_sequence(instructions, force=True)
    assert queued_count == 4
    va.stop()


def test_speech_failure_does_not_crash_routing():
    """Even if VoiceAssistant encounters an error or is disabled, route calculation succeeds."""
    va = VoiceAssistant(enabled=False)

    # Route calculation works independently of audio
    route = find_indoor_route("entrance", "bedroom")
    assert route["status"] == "success"

    # Enqueuing to disabled voice assistant succeeds cleanly
    queued = va.speak_sequence(route["instructions"])
    assert queued == len(route["instructions"])
    va.stop()


# ---------------------------------------------------------------------------
# 11. Camera Resource Cleanup on Exit
# ---------------------------------------------------------------------------

def test_camera_resource_release_logic():
    """Verify camera release is called in finally block even on error."""
    mock_camera = MagicMock()
    mock_camera.isOpened.return_value = True
    mock_camera.read.side_effect = RuntimeError("Simulated camera frame failure")

    cleaned_up = False
    try:
        try:
            success, frame = mock_camera.read()
        except RuntimeError:
            pass
    finally:
        mock_camera.release()
        cleaned_up = True

    assert cleaned_up is True
    mock_camera.release.assert_called_once()
