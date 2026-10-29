import sys
from pathlib import Path

# Ensure project root is in sys.path when executed directly
project_root = Path(__file__).resolve().parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

import cv2

from app.navigation.landmark_detector import IndoorLandmarkDetector

camera = cv2.VideoCapture(0)
detector = IndoorLandmarkDetector()

if not camera.isOpened():
    print("ERROR: Could not open webcam. Ensure camera is connected and not in use.")
    raise SystemExit(1)

print("CogniSight Indoor Landmark Detection Test")
print("Show printed ArUco markers (IDs: 10, 20, 30, 40) to the webcam.")
print("Press 'Q' in the camera window to quit.\n")

try:
    while True:
        success, frame = camera.read()

        if not success:
            print("Could not read a camera frame.")
            break

        results = detector.detect(frame, include_unknown=True)

        for result in results:
            marker_id = result["marker_id"]
            if result.get("known"):
                label = f"Marker {marker_id}: {result['location']}"
                color = (0, 255, 0)
            else:
                label = f"Marker {marker_id}: Unknown landmark"
                color = (0, 0, 255)

            cv2.putText(
                frame,
                label,
                (20, 40),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.8,
                color,
                2,
                cv2.LINE_AA,
            )
            print(f"[DETECTED] {label}")

        cv2.imshow("CogniSight - Indoor Landmark Test", frame)

        if cv2.waitKey(1) & 0xFF == ord("q"):
            break
finally:
    camera.release()
    cv2.destroyAllWindows()
