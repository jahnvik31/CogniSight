from typing import Optional, Tuple
import time
import cv2
import numpy as np
from sqlalchemy.orm import Session

from app.context.context_engine import ContextEngine, ContextState
from app.face.recognizer import FaceRecognizer
from app.memory.memory_service import MemoryService
from app.utils.logging_config import logger
from app.voice.voice_assistant import VoiceAssistant


class CogniSightPipeline:
    """Master Orchestrator Pipeline for CogniSight.

    Connects:
    Face Recognition ⟶ Person Memory ⟶ Context Engine ⟶ Voice Assistant
    """

    _latest_context: Optional[ContextState] = None

    @classmethod
    def get_latest_context(cls) -> Optional[ContextState]:
        """Returns latest synthesized context state from active camera processing pipeline."""
        return cls._latest_context

    def __init__(
        self,
        recognizer: Optional[FaceRecognizer] = None,
        memory_service: Optional[MemoryService] = None,
        context_engine: Optional[ContextEngine] = None,
        voice_assistant: Optional[VoiceAssistant] = None,
    ):
        self.recognizer = (
            recognizer if recognizer is not None else FaceRecognizer()
        )
        self.memory_service = (
            memory_service if memory_service is not None else MemoryService()
        )
        self.context_engine = (
            context_engine
            if context_engine is not None
            else ContextEngine(self.memory_service)
        )
        self.voice_assistant = (
            voice_assistant if voice_assistant is not None else VoiceAssistant()
        )
        self._unknown_announced = False
        self._last_announced_person_id: Optional[int] = None
        self._no_person_since = None
        self._unknown_reset_seconds = 5.0

    def process_frame_full_pipeline(
        self, frame: np.ndarray, db: Session, speak_voice: bool = True
    ) -> Tuple[np.ndarray, ContextState]:
        """Executes full end-to-end CogniSight perception, memory, context, and voice cycle.

        Args:
            frame: OpenCV video frame.
            db: Database session.
            speak_voice: Whether to trigger voice announcements.

        Returns:
            Tuple[np.ndarray, ContextState]: (Annotated Frame, Synthesized ContextState)
        """
        # 1. Perception: Run Face Recognition
        recognition_results = self.recognizer.process_frame(frame, db)

        # 2. Context Synthesis: Synthesize perception with Person Memory
        context_state = self.context_engine.generate_context(db, recognition_results)
        CogniSightPipeline._latest_context = context_state

        # 3. Voice Assistance: Speak context announcement (with cooldown throttling)
        
        # 3. Voice Assistance: Announce an unknown person only once
        # until the scene clears or a known person is recognized.
        now = time.monotonic()

        if context_state.recognized:
            # A known person is visible; allow a future unknown-person alert.
            self._unknown_announced = False
            self._no_person_since = None

            # Announce recognized person ONCE per interaction session; do not repeat continuously
            if speak_voice and context_state.spoken_announcement:
                if context_state.person_id != self._last_announced_person_id:
                    self.voice_assistant.speak(
                        context_state.spoken_announcement,
                        force=True,
                    )
                    self._last_announced_person_id = context_state.person_id

        elif recognition_results:
            # A person is visible but their face is not recognized.
            self._no_person_since = None

            if speak_voice and not self._unknown_announced:
                self.voice_assistant.speak(
                    context_state.spoken_announcement
                )
                self._unknown_announced = True

        else:
            # No face detected. Wait 5s before resetting, so momentary
            # camera dropouts or head turns won't repeat the announcement.
            if self._no_person_since is None:
                self._no_person_since = now
            elif now - self._no_person_since >= self._unknown_reset_seconds:
                self._unknown_announced = False
                self._last_announced_person_id = None

        # 4. Render visual overlays
        annotated_frame = self.recognizer.draw_recognition(frame, recognition_results)
        output_frame = self._render_context_ui(annotated_frame, context_state)

        return output_frame, context_state

    def _render_context_ui(
        self, frame: np.ndarray, context: ContextState
    ) -> np.ndarray:
        """Renders CogniSight heads-up visual context overlay on the live camera view."""
        h, w, _ = frame.shape
        output = frame.copy()

        # Render top context banner
        banner_height = 65
        cv2.rectangle(output, (0, 0), (w, banner_height), (20, 20, 20), cv2.FILLED)

        # Draw status color indicator bar
        color = (0, 255, 0) if context.recognized else (0, 140, 255)
        cv2.rectangle(output, (0, 0), (10, banner_height), color, cv2.FILLED)

        # Draw Headline
        cv2.putText(
            output,
            f"COGNISIGHT: {context.headline}",
            (25, 28),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.65,
            (255, 255, 255),
            2,
            cv2.LINE_AA,
        )

        # Draw Subtext
        cv2.putText(
            output,
            context.subtext,
            (25, 52),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.45,
            (200, 200, 200),
            1,
            cv2.LINE_AA,
        )

        return output

    def shutdown(self):
        """Releases pipeline resources."""
        self.voice_assistant.stop()
