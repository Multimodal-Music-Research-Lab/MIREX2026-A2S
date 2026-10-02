"""Audio synthesis of fragment MIDI files with fluidsynth.

Renders each fragment MIDI with fluidsynth (as in the Roman et al. 2019 data
pipeline) and converts the result to the challenge input format: 16-bit
22 050 Hz mono FLAC.
"""

import subprocess
import tempfile
from os import replace
from pathlib import Path

import soundfile as sf

from data_prep.constants import AUDIO_SAMPLE_RATE, DEFAULT_SYNTH_GAIN, SYNTH_RENDER_RATE

SILENCE_FRAME_MS = 10
SILENCE_RMS_THRESHOLD = 1e-4


def trim_trailing_silence(
    audio_path: Path,
    frame_ms: int = SILENCE_FRAME_MS,
    rms_threshold: float = SILENCE_RMS_THRESHOLD,
) -> float:
    """Remove digital silence after the final audible audio frame.

    Fluidsynth keeps its output stream alive after all MIDI notes have ended.
    The additional data should have the same endpoint convention as the
    reference quartets, so retain the final active frame and discard only
    subsequent frames below the audio noise floor.
    """
    audio, sample_rate = sf.read(audio_path, dtype="float32")
    if audio.ndim == 2:
        audio = audio.mean(axis=1)
    frame_size = max(1, round(sample_rate * frame_ms / 1000))
    active_end = 0
    for start in range(0, len(audio), frame_size):
        frame = audio[start : start + frame_size]
        if frame.size and float((frame * frame).mean()) ** 0.5 >= rms_threshold:
            active_end = min(len(audio), start + frame_size)
    if active_end == 0:
        raise RuntimeError(f"Synthesized audio is silent: {audio_path}")
    if active_end < len(audio):
        with tempfile.NamedTemporaryFile(suffix=".flac", dir=audio_path.parent, delete=False) as tmp:
            trimmed_path = Path(tmp.name)
        sf.write(trimmed_path, audio[:active_end], sample_rate, format="FLAC", subtype="PCM_16")
        replace(trimmed_path, audio_path)
    return active_end / sample_rate


def synthesize_flac(
    midi_path: Path,
    flac_path: Path,
    soundfont: Path,
    sample_rate: int = AUDIO_SAMPLE_RATE,
    render_rate: int = SYNTH_RENDER_RATE,
    gain: float = DEFAULT_SYNTH_GAIN,
) -> float:
    """Render one MIDI file to a mono 16-bit FLAC at ``sample_rate``.

    Returns the duration of the produced audio in seconds.
    """
    flac_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        wav_path = Path(tmp) / "render.wav"
        subprocess.run(
            [
                "fluidsynth", "-ni",
                "-g", str(gain),
                "-r", str(render_rate),
                "-F", str(wav_path),
                str(soundfont),
                str(midi_path),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        subprocess.run(
            [
                "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                "-i", str(wav_path),
                "-ac", "1", "-ar", str(sample_rate),
                "-c:a", "flac", "-sample_fmt", "s16",
                str(flac_path),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
    info = sf.info(flac_path)
    if info.frames == 0:
        raise RuntimeError(f"Synthesized empty audio for {midi_path}")
    return trim_trailing_silence(flac_path)
