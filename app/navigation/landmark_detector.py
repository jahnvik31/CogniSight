from dataclasses import dataclass
from typing import Any, Dict, List, Optional
import cv2

# Temporary sample map: marker ID -> indoor location.
MARKER_LOCATIONS: Dict[int, str] = {
    10: "entrance",
    20: "corridor",
    30: "dining_room",
    40: "bedroom",
}


@dataclass
class TrackerState:
    """State snapshot returned by LandmarkTracker."""

    confirmed_marker_id: Optional[int]
    confirmed_location: Optional[str]
    is_new_transition: bool
    status: str  # "tracking", "confirming", "lost", "idle", "confirmed"


class IndoorLandmarkDetector:
    """Detect printed ArUco landmarks in an OpenCV camera frame."""

    def __init__(self, marker_locations: Optional[Dict[int, str]] = None):
        if not hasattr(cv2, "aruco"):
            raise RuntimeError("OpenCV ArUco support is unavailable.")

        self.marker_locations = (
            marker_locations if marker_locations is not None else MARKER_LOCATIONS
        )

        self.dictionary = cv2.aruco.getPredefinedDictionary(
            cv2.aruco.DICT_4X4_50
        )

        if hasattr(cv2.aruco, "DetectorParameters"):
            parameters = cv2.aruco.DetectorParameters()
            self.detector = cv2.aruco.ArucoDetector(
                self.dictionary, parameters
            )
            self._legacy = False
        else:
            self.parameters = cv2.aruco.DetectorParameters_create()
            self._legacy = True

    def detect_raw(self, frame):
        """Runs marker detection and returns raw OpenCV (corners, ids)."""
        if frame is None or getattr(frame, "size", 0) == 0:
            return [], None

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY) if len(frame.shape) == 3 else frame

        if self._legacy:
            corners, ids, _ = cv2.aruco.detectMarkers(
                gray, self.dictionary, parameters=self.parameters
            )
        else:
            corners, ids, _ = self.detector.detectMarkers(gray)

        return corners, ids

    def detect(self, frame, include_unknown: bool = False) -> List[Dict[str, Any]]:
        """Return the recognized marker IDs and mapped locations.

        Args:
            frame: OpenCV image frame.
            include_unknown: If True, includes detected markers not in the mapping.

        Returns:
            List of dicts with marker information.
        """
        corners, ids = self.detect_raw(frame)

        if ids is None:
            return []

        results = []
        for marker_id in ids.flatten().tolist():
            is_known = marker_id in self.marker_locations
            if is_known:
                results.append({
                    "marker_id": marker_id,
                    "location": self.marker_locations[marker_id],
                    "known": True,
                })
            elif include_unknown:
                results.append({
                    "marker_id": marker_id,
                    "location": None,
                    "known": False,
                })

        return results

    def get_location_for_marker(self, marker_id: int) -> Optional[str]:
        """Resolves a marker ID to its configured indoor location key."""
        return self.marker_locations.get(marker_id)


class LandmarkTracker:
    """Temporal filter and state manager for ArUco landmarks.

    Filters out transient detections (lighting flicker, motion blur)
    and prevents duplicate triggers when viewing a stationary marker.
    """

    def __init__(
        self,
        confirmation_frames: int = 3,
        lost_tolerance_frames: int = 4,
        marker_map: Optional[Dict[int, str]] = None,
    ):
        self.confirmation_frames = max(1, confirmation_frames)
        self.lost_tolerance_frames = max(1, lost_tolerance_frames)
        self.marker_map = marker_map if marker_map is not None else MARKER_LOCATIONS

        self.confirmed_marker_id: Optional[int] = None
        self.candidate_marker_id: Optional[int] = None
        self.candidate_count: int = 0
        self.lost_count: int = 0

    def update(self, detected_marker_ids: List[int]) -> TrackerState:
        """Processes marker IDs observed in the current frame.

        Args:
            detected_marker_ids: List of marker IDs detected in the current frame.

        Returns:
            TrackerState containing confirmation status and transition flag.
        """
        # Filter for recognized mapped landmarks
        known_ids = [mid for mid in detected_marker_ids if mid in self.marker_map]

        if not known_ids:
            self.lost_count += 1
            if self.lost_count >= self.lost_tolerance_frames:
                self.confirmed_marker_id = None
                self.candidate_marker_id = None
                self.candidate_count = 0
                return TrackerState(
                    confirmed_marker_id=None,
                    confirmed_location=None,
                    is_new_transition=False,
                    status="lost",
                )
            else:
                loc = (
                    self.marker_map.get(self.confirmed_marker_id)
                    if self.confirmed_marker_id
                    else None
                )
                return TrackerState(
                    confirmed_marker_id=self.confirmed_marker_id,
                    confirmed_location=loc,
                    is_new_transition=False,
                    status="tracking" if self.confirmed_marker_id else "idle",
                )

        primary_id = known_ids[0]
        self.lost_count = 0

        # Already confirmed this marker: camera is stationary
        if primary_id == self.confirmed_marker_id:
            self.candidate_marker_id = None
            self.candidate_count = 0
            return TrackerState(
                confirmed_marker_id=self.confirmed_marker_id,
                confirmed_location=self.marker_map.get(self.confirmed_marker_id),
                is_new_transition=False,
                status="tracking",
            )

        # Transition candidate
        if primary_id == self.candidate_marker_id:
            self.candidate_count += 1
        else:
            self.candidate_marker_id = primary_id
            self.candidate_count = 1

        if self.candidate_count >= self.confirmation_frames:
            self.confirmed_marker_id = self.candidate_marker_id
            self.candidate_marker_id = None
            self.candidate_count = 0
            return TrackerState(
                confirmed_marker_id=self.confirmed_marker_id,
                confirmed_location=self.marker_map.get(self.confirmed_marker_id),
                is_new_transition=True,
                status="confirmed",
            )

        return TrackerState(
            confirmed_marker_id=self.confirmed_marker_id,
            confirmed_location=(
                self.marker_map.get(self.confirmed_marker_id)
                if self.confirmed_marker_id
                else None
            ),
            is_new_transition=False,
            status="confirming",
        )

    def reset(self):
        """Resets all tracking states to initial clean state."""
        self.confirmed_marker_id = None
        self.candidate_marker_id = None
        self.candidate_count = 0
        self.lost_count = 0
