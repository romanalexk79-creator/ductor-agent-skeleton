#!/usr/bin/env python3
"""Local speech-to-text via faster-whisper (no API key required).

Invoked as the ``DUCTOR_TRANSCRIBE_COMMAND`` hook of ``transcribe_audio.py``:
the audio path arrives as the last argv element. Prints
``{"transcript": ..., "language": ...}`` as JSON on stdout.

Dependencies live in ``_vendor/`` and model weights in
``workspace/.cache/whisper`` — both on the persistent ``/ductor`` mount,
because the container filesystem is wiped on restart.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_VENDOR = _HERE / "_vendor"
_CACHE = _HERE.parents[1] / ".cache" / "whisper"

MODEL_SIZE = "small"

sys.path.insert(0, str(_VENDOR))

_CACHE.mkdir(parents=True, exist_ok=True)
# Point every HF/CT2 cache knob at the persistent mount before the libs load.
os.environ.setdefault("HF_HOME", str(_CACHE))
os.environ.setdefault("HUGGINGFACE_HUB_CACHE", str(_CACHE))
os.environ.setdefault("XDG_CACHE_HOME", str(_CACHE))


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: local_whisper.py [options] <audio-file>", file=sys.stderr)
        return 2

    audio = Path(sys.argv[-1]).expanduser()
    if not audio.exists():
        print(f"Audio file not found: {audio}", file=sys.stderr)
        return 2

    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        print(f"faster-whisper not available in {_VENDOR}: {exc}", file=sys.stderr)
        return 3

    try:
        model = WhisperModel(
            model_size_or_path=MODEL_SIZE,
            device="cpu",
            compute_type="int8",
            download_root=str(_CACHE),
        )
        # No language= — auto-detection handles the user's German/English mix.
        segments, info = model.transcribe(str(audio), beam_size=5, vad_filter=True)
        text = "".join(segment.text for segment in segments).strip()
    except Exception as exc:  # noqa: BLE001 - surface any backend failure verbatim
        print(f"Transcription failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(
        {
            "transcript": text,
            "language": getattr(info, "language", None),
            "language_probability": getattr(info, "language_probability", None),
            "duration_seconds": getattr(info, "duration", None),
            "method": "faster_whisper_local",
            "model": MODEL_SIZE,
        },
        ensure_ascii=False,
    ))
    return 0


if __name__ == "__main__":
    sys.exit(main())
