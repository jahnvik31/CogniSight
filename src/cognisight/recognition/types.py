"""Module-local contracts, not repository-wide APIs."""

import time
import math
import uuid
from dataclasses import dataclass, asdict, field
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
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    schema_version: int = 1

    def __post_init__(self):
        if type(self.schema_version) is not int or self.schema_version != 1:
            raise ValueError("Unsupported event schema")
        if self.kind not in ("confirmed", "lost"):
            raise ValueError("Invalid event kind")
        if type(self.track_id) is not int or self.track_id < 1:
            raise ValueError("Invalid event track")
        if not all(isinstance(value, str) and 0 < len(value) <= limit
                   for value, limit in ((self.person_id, 100), (self.model_version, 100),
                                        (self.event_id, 100))):
            raise ValueError("Invalid event identity")
        if self.timestamp is not None and (
            isinstance(self.timestamp, bool) or not isinstance(self.timestamp, (float, int))
            or not math.isfinite(self.timestamp) or not 0 <= self.timestamp <= 253402300799
        ):
            raise ValueError("Invalid event timestamp")

    def to_dict(self):
        return asdict(self)
