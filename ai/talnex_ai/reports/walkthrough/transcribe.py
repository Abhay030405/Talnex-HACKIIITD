"""Speech to text for a recorded walkthrough question (architecture section 31.3, step 2), with faster-whisper.

faster-whisper is imported only when a recording arrives, so the worker starts (and every other stage runs) without it.
The model is loaded once per worker process. Tests install a fake with `set_transcriber`.
"""
from __future__ import annotations

import io
import threading
from typing import Callable, Optional

from talnex_ai.settings import WalkthroughSettings

Transcriber = Callable[[bytes], str]

_lock = threading.Lock()
_transcriber: Optional[Transcriber] = None


class WhisperTranscriber:
    def __init__(self, cfg: WalkthroughSettings):
        try:
            from faster_whisper import WhisperModel
        except ImportError as exc:  # a clear message instead of a bare import error deep in a job
            raise RuntimeError("faster-whisper is not installed, so recorded questions cannot be turned into text "
                               "(install the ai package's dependencies)") from exc
        self._model = WhisperModel(cfg.whisper_model, device=cfg.whisper_device, compute_type=cfg.whisper_compute_type)
        self._lock = threading.Lock()

    def __call__(self, audio: bytes) -> str:
        with self._lock:  # one recording at a time per loaded model
            segments, _info = self._model.transcribe(io.BytesIO(audio), vad_filter=True)
            return " ".join(s.text.strip() for s in segments if s.text.strip())


def set_transcriber(transcriber: Optional[Transcriber]) -> None:
    """Install (or clear) the transcriber. For tests."""
    global _transcriber
    _transcriber = transcriber


def get_transcriber(cfg: WalkthroughSettings) -> Transcriber:
    global _transcriber
    with _lock:
        if _transcriber is None:
            _transcriber = WhisperTranscriber(cfg)
        return _transcriber
