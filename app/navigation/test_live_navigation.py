import sys
from pathlib import Path

# Ensure project root is in sys.path when executed directly
project_root = Path(__file__).resolve().parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

import cv2

from app.navigation.indoor_navigation import (
    INDOOR_MAP,
    find_indoor_route,
    normalize_location,
)
from app.navigation.landmark_detector import (
    IndoorLandmarkDetector,
    LandmarkTracker,
    MARKER_LOCATIONS,
)
from app.voice.voice_assistant import VoiceAssistant


def select_destination() -> str:
    """Prompts the user to enter a destination until a valid one is provided."""
    if len(sys.argv) > 1 and sys.argv[1].strip():
        arg_input = sys.argv[1].strip()
        try:
            normalized = normalize_location(arg_input)
            print(f"Target destination selected via argument: {INDOOR_MAP[normalized]['name']}")
            return normalized
        except ValueError as err:
            print(f"Invalid command line destination '{arg_input}': {err}")

    available = ", ".join(sorted(INDOOR_MAP.keys()))
    while True:
        try:
            user_input = input(
                f"\nEnter destination ({available}) [or 'q' to exit]: "
            ).strip()
            if user_input.lower() in ("q", "quit", "exit"):
                return ""
            normalized = normalize_location(user_input)
            print(f"Target destination confirmed: {INDOOR_MAP[normalized]['name']}")
            return normalized
        except (EOFError, KeyboardInterrupt):
            print("\nNon-interactive shell detected. Defaulting destination to 'bedroom'.")
            return "bedroom"
        except ValueError as err:
            print(f"Invalid destination: {err}. Please try again.")


def run_live_navigation():
    """Main live indoor navigation demonstration loop."""
    print("=" * 60)
    print("  CogniSight - Live Indoor Navigation Demonstration")
    print("=" * 60)

    target_destination = select_destination()
    if not target_destination:
        print("Navigation session canceled.")
        return

    detector = IndoorLandmarkDetector()
    tracker = LandmarkTracker(confirmation_frames=3, lost_tolerance_frames=5)
    voice = VoiceAssistant()

    camera = cv2.VideoCapture(0)
    if not camera.isOpened():
        voice.clear_queue()
        voice.stop()
        print("\nERROR: Could not open webcam.")
        print("Please check that your camera is connected and not used by another program.")
        sys.exit(1)

    print("\nWebcam opened successfully.")
    print("Point the camera toward an ArUco landmark marker (IDs: 10, 20, 30, 40).")
    print("Controls:")
    print("  - Press 'Q' in the camera window to quit.")
    print("  - Press 'C' in the camera window to change destination.\n")

    current_route_text = ""

    try:
        while True:
            success, frame = camera.read()
            if not success or frame is None:
                print("Could not read frame from webcam.")
                break

            # 1. Detect all markers in current frame
            raw_detections = detector.detect(frame, include_unknown=True)
            detected_ids = [d["marker_id"] for d in raw_detections]

            # 2. Update temporal landmark tracker
            tracker_state = tracker.update(detected_ids)

            # 3. Check for unknown markers
            unknown_ids = [d["marker_id"] for d in raw_detections if not d.get("known")]

            # 4. Handle landmark transitions and announcements
            if tracker_state.status == "confirmed" and tracker_state.is_new_transition:
                start_loc = tracker_state.confirmed_location
                marker_id = tracker_state.confirmed_marker_id
                start_name = INDOOR_MAP[start_loc]["name"]
                dest_name = INDOOR_MAP[target_destination]["name"]

                print(f"\n[LANDMARK CONFIRMED] Marker {marker_id} -> {start_name}")

                try:
                    route_data = find_indoor_route(start_loc, target_destination)
                    route_display = " -> ".join(route_data["route"])
                    current_route_text = f"Route: {route_display}"
                    print(f"Computed route: {route_display}")

                    # Speak all instructions sequentially without dropping any step
                    print("Spoken Directions:")
                    for idx, instruction in enumerate(route_data["instructions"], 1):
                        print(f"  {idx}. {instruction}")

                    # Clear any stale speech and enqueue sequential route instructions
                    voice.clear_queue()
                    voice.speak_sequence(route_data["instructions"], force=True)

                except ValueError as exc:
                    current_route_text = f"Route error: {exc}"
                    print(f"Route calculation error: {exc}")
                    voice.clear_queue()
                    voice.speak(
                        f"Sorry, no route connects {start_name} to {dest_name}.",
                        force=True,
                    )

            # 5. Visual HUD annotations on frame
            dest_display = INDOOR_MAP[target_destination]["name"]
            cv2.putText(
                frame,
                f"Target: {dest_display}",
                (20, 30),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                (255, 200, 0),
                2,
                cv2.LINE_AA,
            )

            if tracker_state.confirmed_location:
                current_loc_name = INDOOR_MAP[tracker_state.confirmed_location]["name"]
                status_color = (0, 255, 0)
                status_text = f"Current Landmark: {current_loc_name} (ID {tracker_state.confirmed_marker_id})"
            elif tracker_state.status == "confirming":
                status_color = (0, 255, 255)
                status_text = f"Locking Landmark (ID {tracker.candidate_marker_id})..."
            elif unknown_ids:
                status_color = (0, 0, 255)
                status_text = f"Unmapped Marker Detected (ID: {unknown_ids[0]})"
            else:
                status_color = (180, 180, 180)
                status_text = "Searching for indoor landmarks..."

            cv2.putText(
                frame,
                status_text,
                (20, 60),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6,
                status_color,
                2,
                cv2.LINE_AA,
            )

            if current_route_text:
                cv2.putText(
                    frame,
                    current_route_text,
                    (20, 90),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.55,
                    (255, 255, 255),
                    1,
                    cv2.LINE_AA,
                )

            cv2.putText(
                frame,
                "Press 'Q' to quit | 'C' to change destination",
                (20, frame.shape[0] - 20),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                (200, 200, 200),
                1,
                cv2.LINE_AA,
            )

            cv2.imshow("CogniSight - Live Indoor Navigation", frame)

            key = cv2.waitKey(1) & 0xFF
            if key == ord("q"):
                print("\nQuitting navigation...")
                break
            elif key == ord("c"):
                voice.clear_queue()
                new_dest = select_destination()
                if new_dest:
                    target_destination = new_dest
                    tracker.reset()
                    current_route_text = ""

    finally:
        camera.release()
        cv2.destroyAllWindows()
        voice.clear_queue()
        voice.stop()
        print("Camera and audio resources cleanly released.")


if __name__ == "__main__":
    run_live_navigation()
