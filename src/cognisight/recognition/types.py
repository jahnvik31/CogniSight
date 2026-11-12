"""Module-local contracts, not repository-wide APIs."""

import time
import uuid
from dataclasses import dataclass, asdict
from typing import Any, Optional
from pathlib import Path


def clock_utc():
    now = time.time()
    # systemd-timesyncd creates this volatile marker after successful sync.
    # No marker (including development hosts) means history timestamps unavailable.
    synced = Path("/run/systemd/timesync/synchronized").exists()
    return now if synced and now >= 1735689600 else None


@dataclass(frozen=True)
class FramePacket:
    frame_id: int
    captured_at: float
    utc: Optional[float]
    image: Any


@dataclass(frozen=True)
class RecognitionEvent:
    kind: str
    track_id: int
    person_id: str
    timestamp: Optional[float]
    model_version: str
    event_id: str = ""
    schema_version: int = 1

    def to_dict(self):
        result = asdict(self)
        result["event_id"] = self.event_id or str(uuid.uuid4())
        return result
