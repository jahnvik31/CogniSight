from pathlib import Path
import sys

# Ensure project root is in sys.path when executed directly
project_root = Path(__file__).resolve().parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

import cv2
from app.navigation.landmark_detector import MARKER_LOCATIONS

output_dir = project_root / "markers"
output_dir.mkdir(exist_ok=True)

dictionary = cv2.aruco.getPredefinedDictionary(
    cv2.aruco.DICT_4X4_50
)

print(f"Generating ArUco markers into directory: '{output_dir.resolve()}'...")

for marker_id, location in MARKER_LOCATIONS.items():
    if hasattr(cv2.aruco, "generateImageMarker"):
        image = cv2.aruco.generateImageMarker(
            dictionary, marker_id, 400
        )
    else:
        image = cv2.aruco.drawMarker(
            dictionary, marker_id, 400
        )

    # Add a white border (quiet zone) to preserve marker edges when printed or displayed
    image = cv2.copyMakeBorder(
        image, 50, 50, 50, 50,
        cv2.BORDER_CONSTANT, value=255
    )

    filename = output_dir / f"{marker_id}_{location}.png"
    if not cv2.imwrite(str(filename), image):
        raise RuntimeError(f"Could not save {filename}")

    print(f"  [OK] Created marker {marker_id} ({location}): {filename}")

print("\nAll 4 indoor navigation markers successfully generated.")
