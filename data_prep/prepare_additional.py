"""Download and preparation pipeline for the additional quartets dataset.

Sources are ``**kern`` files listed in ``additional_quartets.txt`` (kern
scores hosted on kern.ccarh.org). For every URL, the ``format`` argument is
rewritten to fetch the kern score and its MIDI rendering. Preparation follows
the Roman et al. (2019) rules (see :mod:`data_prep.kern_fragment`): the kern
scores are split into 3-6 measure fragments, each fragment is rendered to
MIDI (:mod:`data_prep.kern_midi`) and synthesized to 16-bit 22 050 Hz mono
FLAC with fluidsynth (:mod:`data_prep.synthesis`), producing the same
``<track>.kern`` + ``<track>.flac`` layout as the quartets dataset.
"""

import io
import random
import re
import subprocess
import tempfile
from pathlib import Path

import mido

from a2s_metrics.kern import parse_kern
from data_prep.constants import (
    ADDITIONAL_URLS_FILE,
    DEFAULT_SOUNDFONT,
    DEFAULT_SYNTH_GAIN,
)
from data_prep.kern_fragment import Fragment, KernSource, fragment_source, parse_source
from data_prep.kern_midi import fragment_to_midi, parse_fragment_performance
from data_prep.synthesis import synthesize_flac

_FORMAT_PARAM = re.compile(r"([?&])format=[^&]*")
_LENGTH_TOLERANCE_Q = 2.0
_TEMPO_TOLERANCE_Q = 1.0
_TEMPO_TOLERANCE_BPM = 1.0


def rewrite_fourth_instrument(text: str, instrument: str = "flt") -> str:
    """Set the fourth ``**kern`` spine's instrument interpretation.

    The additional sources use a fourth violin part, whereas the published
    Quartets dataset uses flute for that voice. The fourth ``**kern`` spine and
    any immediately following auxiliary spines belonging to it (normally its
    paired ``**dynam`` spine) receive the new instrument token; musical content
    remains untouched.
    """
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    spine_line_index = next(
        (index for index, line in enumerate(lines) if line.split("\t").count("**kern") >= 4),
        None,
    )
    if spine_line_index is None:
        return text
    spine_tokens = lines[spine_line_index].split("\t")
    kern_indices = [index for index, token in enumerate(spine_tokens) if token == "**kern"]
    if len(kern_indices) < 4:
        return text
    fourth_kern_index = kern_indices[3]
    instrument_line_index = next(
        (
            index
            for index in range(spine_line_index + 1, len(lines))
            if any(token.startswith("*I") for token in lines[index].split("\t"))
        ),
        None,
    )
    if instrument_line_index is None:
        raise ValueError("Score does not contain instrument interpretations")
    instrument_tokens = lines[instrument_line_index].split("\t")
    if fourth_kern_index >= len(instrument_tokens):
        raise ValueError("Instrument interpretation has fewer columns than spine line")
    next_kern_index = next(
        (
            index
            for index in kern_indices
            if index > fourth_kern_index
        ),
        len(spine_tokens),
    )
    for index in range(fourth_kern_index, next_kern_index):
        if instrument_tokens[index].startswith("*I"):
            instrument_tokens[index] = f"*I{instrument}"
    lines[instrument_line_index] = "\t".join(instrument_tokens)
    return "\n".join(lines)


def _kern_spine_count(text: str) -> int:
    """Return the number of ``**kern`` spines in a score."""
    return next(
        (line.split("\t").count("**kern") for line in text.splitlines() if "**kern" in line),
        0,
    )


def download_additional(
    raw_dir: Path, urls_file: Path = ADDITIONAL_URLS_FILE, force: bool = False
) -> list[str]:
    """Download the kern and MIDI files of every URL in ``urls_file``.

    The ``format`` argument of each URL is rewritten to ``kern`` and ``midi``
    respectively. Returns the list of source stems.
    """
    raw_dir = Path(raw_dir)
    raw_dir.mkdir(parents=True, exist_ok=True)
    stems: list[str] = []
    for url in urls_file.read_text(encoding="utf-8").splitlines():
        url = url.strip()
        if not url or url.startswith("#"):
            continue
        stem = re.search(r"[?&]file=([^&]+)", url).group(1)
        stem = stem.removesuffix(".krn")
        for fmt, extension in (("kern", "kern"), ("midi", "midi")):
            destination = raw_dir / f"{stem}.{extension}"
            if destination.exists() and destination.stat().st_size > 0 and not force:
                continue
            fmt_url = _FORMAT_PARAM.sub(rf"\g<1>format={fmt}", url)
            subprocess.run(
                ["wget", "-q", "-O", str(destination), fmt_url],
                check=True,
                capture_output=True,
            )
        stems.append(stem)
        print(f"downloaded {stem} (.kern + .midi)")
    return stems


def _midi_tempo_map(midi: mido.MidiFile) -> list[tuple[float, float]]:
    """Tempo map of a MIDI file as sorted (position_q, qpm) points."""
    tempos: dict[int, int] = {}
    for track in midi.tracks:
        tick = 0
        for message in track:
            tick += message.time
            if message.type == "set_tempo":
                tempos.setdefault(tick, message.tempo)
    return sorted((tick / midi.ticks_per_beat, round(60e6 / tempo, 2)) for tick, tempo in tempos.items())


def _midi_end_q(midi: mido.MidiFile) -> float:
    """Total length of a MIDI file in quarter notes (last event)."""
    return max(
        (sum(message.time for message in track) / midi.ticks_per_beat for track in midi.tracks),
        default=0.0,
    )


def validate_against_midi(source: KernSource, midi_path: Path) -> list[str]:
    """Cross-check a parsed kern source against its downloaded MIDI rendering.

    The kern.ccarh.org MIDI conversion shares the tempo markings and the
    total length of the score, so both are compared as a sanity check of the
    kern parsing. Returns human-readable report lines.
    """
    midi = mido.MidiFile(midi_path)
    lines = []
    midi_tempos = _midi_tempo_map(midi)
    if not source.tempo_changes:
        lines.append(f"    tempo: kern has no *MM marking; MIDI map: {midi_tempos or 'default 120'}")
    else:
        for position, qpm in source.tempo_changes:
            match = next(
                (
                    m_position
                    for m_position, m_qpm in midi_tempos
                    if abs(m_position - position) <= _TEMPO_TOLERANCE_Q
                    and abs(m_qpm - qpm) <= _TEMPO_TOLERANCE_BPM
                ),
                None,
            )
            status = "ok" if match is not None else "MISMATCH"
            lines.append(f"    tempo {qpm:g} qpm at {position:g}q: {status}")
    expected = source.total_q
    actual = _midi_end_q(midi)
    status = "ok" if abs(expected - actual) <= _LENGTH_TOLERANCE_Q else "MISMATCH"
    lines.append(f"    length: kern {expected:.2f}q vs MIDI {actual:.2f}q: {status}")
    return lines


def _expected_duration_q(length_q: float, tempo_map: list[tuple[float, float]]) -> float:
    """Seconds spanned by ``length_q`` quarters under a (position, qpm) map."""
    seconds = 0.0
    for (start, qpm), (end, _) in zip(tempo_map, tempo_map[1:] + [(length_q, 0.0)]):
        span = min(end, length_q) - start
        if span > 0:
            seconds += span * 60.0 / qpm
    return seconds


def prepare_additional(
    raw_dir: Path,
    output_root: Path,
    split: str = "test",
    seed: int = 0,
    min_measures: int = 3,
    max_measures: int = 6,
    soundfont: Path = DEFAULT_SOUNDFONT,
    audio_format: str = "flac",
    gain: float = DEFAULT_SYNTH_GAIN,
    fourth_instrument: str | None = None,
    limit: int | None = None,
    skip_existing: bool = False,
) -> dict[str, int]:
    """Fragment the downloaded sources and synthesize the fragment audio.

    Writes ``<track>.kern`` (+ ``<track>.flac`` unless ``audio_format`` is
    ``none``) under ``<output_root>/<split>/``. Returns per-source fragment
    counts.
    """
    output_dir = Path(output_root) / split
    output_dir.mkdir(parents=True, exist_ok=True)
    rng = random.Random(seed)
    counts: dict[str, int] = {}
    for kern_path in sorted(Path(raw_dir).glob("*.kern")):
        stem = kern_path.stem
        source = parse_source(kern_path.read_text(encoding="utf-8"), stem)
        print(f"{stem}: {len(source.regions)} measures, {source.total_q:.1f}q")
        for warning in source.warnings:
            print(f"    WARNING: {warning}")
        midi_path = Path(raw_dir) / f"{stem}.midi"
        if midi_path.exists():
            for line in validate_against_midi(source, midi_path):
                print(line)
        fragments, discarded = fragment_source(source, rng, min_measures, max_measures)
        if fourth_instrument:
            fragments = [fragment for fragment in fragments if _kern_spine_count(fragment.text) == 4]
        for reason, measure in discarded:
            print(f"    discarded fragment at measure {measure + 1}: {reason}")
        if limit is not None:
            fragments = fragments[:limit]
        for fragment in fragments:
            _prepare_fragment(
                fragment,
                output_dir,
                soundfont,
                audio_format,
                skip_existing,
                gain,
                fourth_instrument,
            )
        counts[stem] = len(fragments)
        print(f"    {len(fragments)} fragment(s) prepared ({len(discarded)} discarded)")
    total = sum(counts.values())
    print(f"total: {total} fragment(s) under {output_dir}")
    return counts


def _prepare_fragment(
    fragment: Fragment,
    output_dir: Path,
    soundfont: Path,
    audio_format: str,
    skip_existing: bool,
    gain: float,
    fourth_instrument: str | None = None,
) -> None:
    """Write one fragment reference (and its synthesized audio)."""
    kern_path = output_dir / f"{fragment.track_id}.kern"
    flac_path = output_dir / f"{fragment.track_id}.flac"
    if skip_existing and kern_path.exists() and (audio_format == "none" or flac_path.exists()):
        return
    fragment_text = (
        rewrite_fourth_instrument(fragment.text, fourth_instrument)
        if fourth_instrument
        else fragment.text
    )
    kern_path.write_text(fragment_text, encoding="utf-8")
    if audio_format == "none":
        return
    score = parse_kern(fragment_text)
    if not score.notes:
        raise RuntimeError(f"{fragment.track_id}: fragment without notes")
    if len({note.voice for note in score.notes}) > 4:
        raise RuntimeError(f"{fragment.track_id}: more than four voices")
    performance = parse_fragment_performance(fragment_text)
    note_end_q = max(
        off_q
        for column_notes in performance["column_notes"]
        for _, off_q, _ in column_notes
    )
    expected = _expected_duration_q(note_end_q, performance["tempo_map"])
    with tempfile.TemporaryDirectory() as tmp:
        midi_path = Path(tmp) / f"{fragment.track_id}.mid"
        buffer = io.BytesIO()
        fragment_to_midi(fragment_text).save(file=buffer)
        midi_path.write_bytes(buffer.getvalue())
        duration = synthesize_flac(midi_path, flac_path, soundfont, gain=gain)
    if not expected - 0.5 <= duration <= expected + 8.0:
        raise RuntimeError(
            f"{fragment.track_id}: audio {duration:.2f}s outside expected "
            f"{expected:.2f}s (+release tail)"
        )
