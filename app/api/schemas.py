from datetime import datetime
from typing import Dict, List, Optional
from pydantic import BaseModel, Field

from app.face.schemas import BoundingBox, RecognitionResult


class PersonCreate(BaseModel):
    """Request DTO for creating a new person profile."""

    name: str = Field(
        ...,
        min_length=1,
        max_length=100,
        json_schema_extra={"example": "John"},
    )


class MemoryProfileUpdate(BaseModel):
    """Request DTO for updating a person's relationship and memory notes."""

    relationship: Optional[str] = Field(
        None, json_schema_extra={"example": "Brother / Caregiver"}
    )
    notes: Optional[str] = Field(
        None, json_schema_extra={"example": "Loves tea with 2 sugars."}
    )


class MemoryProfileResponse(BaseModel):
    """Response DTO for person memory profile."""

    id: int
    person_id: int
    relationship: Optional[str] = "Known Contact"
    notes: Optional[str] = ""
    last_seen: datetime

    model_config = {"from_attributes": True}


class PersonResponse(BaseModel):
    """Response DTO representing an enrolled person."""

    id: int
    name: str
    created_at: datetime
    updated_at: datetime
    embeddings_count: int = 0
    profile: Optional[MemoryProfileResponse] = None

    model_config = {"from_attributes": True}


class EnrollmentUploadResponse(BaseModel):
    """Response DTO for image-based batch enrollment."""

    success: bool
    message: str
    total_frames_processed: int
    valid_samples_accepted: int


class VoiceEnrollRequest(BaseModel):
    """Request DTO for audio transcript auto-enrollment."""

    transcript: str = Field(
        ..., json_schema_extra={"example": "My name is Alex and I am a Caregiver"}
    )


class SpeakRequest(BaseModel):
    """Request DTO for TTS voice assistant announcement."""

    text: str = Field(
        ..., json_schema_extra={"example": "John is standing in front of you."}
    )


class HealthResponse(BaseModel):
    """Response DTO for system health check."""

    status: str
    service: str
    version: str
    model: str
    threshold: float


class IndoorRouteRequest(BaseModel):
    """Request DTO for finding indoor route by location names."""

    start: str = Field(
        ...,
        description="Starting landmark ID or display name (e.g. 'entrance')",
        json_schema_extra={"example": "entrance"},
    )
    destination: str = Field(
        ...,
        description="Destination landmark ID or display name (e.g. 'bedroom')",
        json_schema_extra={"example": "bedroom"},
    )


class MarkerRouteRequest(BaseModel):
    """Request DTO for finding indoor route from a scanned ArUco marker ID."""

    marker_id: int = Field(
        ...,
        description="Scanned ArUco marker identifier (e.g. 10)",
        json_schema_extra={"example": 10},
    )
    destination: str = Field(
        ...,
        description="Target destination landmark name",
        json_schema_extra={"example": "bedroom"},
    )


class IndoorRouteResponse(BaseModel):
    """Response DTO containing computed indoor route and sequential instructions."""

    start: str
    destination: str
    route: List[str]
    route_nodes: Optional[List[str]] = None
    instructions: List[str]
    total_steps: Optional[int] = None
    start_marker_id: Optional[int] = None
    location_source: Optional[str] = None
    status: str = "success"


class IndoorMapResponse(BaseModel):
    """Response DTO for indoor floor plan landmark configuration."""

    locations: Dict[str, str]
    marker_locations: Dict[int, str]
    note: str
    connections: Optional[Dict[str, List[str]]] = None
