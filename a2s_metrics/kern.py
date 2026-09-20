"""Minimal ``**kern`` parser extracting the information needed for MV2H.

The parser walks the Humdrum spines of a kern file (handling ``*^`` splits and
``*v`` joins), keeps only ``**kern`` spines (one voice per spine column), and
produces one :class:`Note` per sounded note with:

- ``pitch``: MIDI pitch number (enharmonic spellings collapse, as in MIDI),
- ``on`` / ``off``: onset / offset in milliseconds, computed from the note
  durations and the ``*MM`` tempo marking(s) (score time, not performed time),
- ``voice``: index of the kern spine column the note belongs to.

Tied notes are merged into a single sustained note, chords (space-separated
sub-tokens within one spine token) become simultaneous notes of the same voice,
and grace notes are skipped. This mirrors the kern -> MIDI -> MV2H pipeline of
the A2S Transformer reference implementation (Alfaro-Contreras et al., 2024).
"""

import re
from bisect import bisect_right
from dataclasses import dataclass, replace
from itertools import groupby

from a2s_metrics.constants import DEFAULT_METER, DEFAULT_TEMPO_QPM

KERN_SPINE = "**kern"

# Semitone offsets of the kern pitch letters.
_PITCH_CLASSES = {"c": 0, "d": 2, "e": 4, "f": 5, "g": 7, "a": 9, "b": 11}

# Duration in quarter units for kern duration digits (the denominator of a
# whole note, except 0 = breve). Exotic digits (triplet numerators such as 3,
# 6, 12) fall back to 4 / digit in :func:`_parse_duration`.
_KERN_DURATIONS = {
    "0": 8.0,
    "1": 4.0,
    "2": 2.0,
    "4": 1.0,
    "8": 0.5,
    "16": 0.25,
    "32": 0.125,
    "64": 0.0625,
    "128": 0.03125,
    "256": 0.015625,
    "512": 0.0078125,
}

_DURATION_PREFIX = re.compile(r"^(\d+)(\.*|q+\.*)")
_PITCH_GROUP = re.compile(r"([a-gA-G]+)([#\-n]*)")
_ACCIDENTAL_SEMITONES = {"#": 1, "-": -1, "n": 0}


@dataclass(frozen=True)
class Note:
    """A note event with millisecond timing (as consumed by the MV2H metric)."""

    pitch: int
    on: float
    off: float
    voice: int


@dataclass
class KernScore:
    """Parsed kern content: notes plus the meter/tempo context."""

    notes: list[Note]
    meter: tuple[int, int]
    tempo_qpm: float


@dataclass
class _Column:
    """State of one spine column while parsing."""

    is_kern: bool
    position: float = 0.0  # current position in quarter units
    notes: list[Note] = None  # type: ignore[assignment]
    open_ties: dict[int, int] = None  # type: ignore[assignment]

    def __post_init__(self):
        if self.notes is None:
            self.notes = []
        if self.open_ties is None:
            self.open_ties = {}


def _midi_pitch(letters: str, accidentals: str) -> int | None:
    """Convert a kern pitch group (e.g. ``ff#``) to a MIDI pitch number.

    A single letter is the base octave (lowercase = octave 4, uppercase =
    octave 3); every letter repetition shifts one octave up (lowercase) or
    down (uppercase).
    """
    letter = letters[0].lower()
    if letter not in _PITCH_CLASSES:
        return None
    count = max(1, len(letters))
    octave = 4 + (count - 1) if letters[0].islower() else 3 - (count - 1)
    semitones = _PITCH_CLASSES[letter] + sum(
        _ACCIDENTAL_SEMITONES.get(char, 0) for char in accidentals
    )
    return 12 * (octave + 1) + semitones


def _parse_duration(token: str) -> tuple[float, str, bool]:
    """Split the leading duration of a kern sub-token.

    Returns:
        ``(quarter_length, remainder, is_grace)``. Grace notes have a quarter
        length of 0; an unparsable sub-token yields ``(0.0, token, False)``.
    """
    match = _DURATION_PREFIX.match(token)
    if not match or not match.group(1):
        return 0.0, token, False
    digits = match.group(1)
    tail = token[match.end() :]
    if "q" in match.group(2) or tail.startswith("q"):
        return 0.0, tail, True  # grace note: not sounded
    if digits == "0":
        quarter_length = _KERN_DURATIONS["0"]
    else:
        quarter_length = _KERN_DURATIONS.get(digits, 4.0 / int(digits))
    dots = match.group(2).count(".")
    if dots:
        quarter_length *= 2.0 - 2.0**-dots
    return quarter_length, tail, False


def _pitches_in(remainder: str) -> list[int]:
    """Extract every MIDI pitch encoded in a kern sub-token body."""
    pitches = []
    for match in _PITCH_GROUP.finditer(remainder):
        letters, accidentals = match.groups()
        # A valid kern letter run repeats one letter to raise the octave; each
        # distinct letter of an (invalid) mixed run is treated as its own note
        # at base octave. Trailing accidentals apply to the last group. The
        # letter case (octave encoding) must be preserved.
        runs = ["".join(group) for _, group in groupby(letters)]
        for index, run in enumerate(runs):
            group_accidentals = accidentals if index == len(runs) - 1 else ""
            pitch = _midi_pitch(run, group_accidentals)
            if pitch is not None:
                pitches.append(pitch)
    return pitches


def _parse_token(column: _Column, token: str) -> None:
    """Parse one kern data token of one column, updating its notes/position."""
    if token == "." or token.startswith("="):
        return  # null token or barline: no time advance
    advance = 0.0
    for sub_token in token.split():
        quarter_length, remainder, is_grace = _parse_duration(sub_token)
        if is_grace or quarter_length <= 0.0:
            continue
        advance = max(advance, quarter_length)
        if remainder.startswith("r"):  # rest
            continue
        tie_start, tie_continue, tie_end = ("[" in remainder, "_" in remainder, "]" in remainder)
        on = column.position
        off = column.position + quarter_length
        for pitch in _pitches_in(remainder):
            index = column.open_ties.get(pitch)
            if index is not None:
                # Merge into the pending tied note (a tie start on an already
                # open pitch is treated as a continuation).
                column.notes[index] = replace(column.notes[index], off=off)
                if tie_end and not tie_start:
                    del column.open_ties[pitch]
            else:
                column.notes.append(Note(pitch=pitch, on=on, off=off, voice=-1))
                if tie_start or tie_continue:
                    column.open_ties[pitch] = len(column.notes) - 1
    column.position += advance


def _join_columns(first: _Column, second: _Column) -> _Column:
    """Merge two spine columns on a ``*v`` join line."""
    return _Column(
        is_kern=first.is_kern or second.is_kern,
        position=max(first.position, second.position),
        notes=first.notes + second.notes,
        open_ties={**first.open_ties, **second.open_ties},
    )


def _apply_interpretations(
    tokens: list[str], columns: list[_Column]
) -> list[tuple[str, _Column]]:
    """Process a tandem-interpretation line, handling ``*^`` splits and
    ``*v`` joins.

    Returns ``(token, column)`` pairs so that the caller can process the
    remaining interpretation tokens (``*MM``, ``*M``, ``*-`` ...).
    """
    updated: list[tuple[str, _Column]] = []
    token_index = 0
    column_index = 0
    while token_index < len(tokens) and column_index < len(columns):
        token = tokens[token_index]
        if token == "*^":
            updated.append((token, columns[column_index].clone()))
            updated.append(("", columns[column_index].clone()))
            column_index += 1
            token_index += 1
        elif token == "*v":
            run = 0
            while token_index < len(tokens) and tokens[token_index] == "*v":
                run += 1
                token_index += 1
            merged = columns[column_index]
            for offset in range(1, run):
                merged = _join_columns(merged, columns[column_index + offset])
            column_index += run
            updated.append((token, merged))
        else:
            updated.append((token, columns[column_index]))
            column_index += 1
            token_index += 1
    while column_index < len(columns):  # malformed line: keep the tail
        updated.append(("*", columns[column_index]))
        column_index += 1
    return updated


def _process_interpretation_token(
    token: str,
    column: _Column,
    tempo_changes: list[tuple[float, float]],
    meter: tuple[int, int] | None,
) -> tuple[_Column | None, tuple[int, int] | None]:
    """Handle one non-structural interpretation token.

    ``*MM`` and ``*M`` markings are recorded; every other marking (clefs,
    ``*-`` terminators, ...) is a no-op for this parser.
    """
    if token.startswith("*MM"):
        try:
            tempo_changes.append((column.position, float(token[3:])))
        except ValueError:
            pass
    elif token.startswith("*M") and "/" in token:
        try:
            numerator, denominator = token[2:].split("/")[:2]
            meter = meter or (int(numerator), int(denominator))
        except ValueError:
            pass
    return column, meter


def _tempo_map(tempo_changes: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """Normalize tempo changes into a sorted (quarter_position, qpm) map.

    The first marking at a position wins (spines normally agree; a corrupted
    spine should not override the leading marking).
    """
    merged: dict[float, float] = {}
    for position, qpm in tempo_changes:
        merged.setdefault(position, qpm)
    points = sorted(merged.items())
    if not points or points[0][0] > 0:
        points.insert(0, (0.0, DEFAULT_TEMPO_QPM))
    return points


def _ql_to_ms_converter(tempo_map: list[tuple[float, float]]):
    """Build a quarter-length -> milliseconds converter for a tempo map."""
    positions = [position for position, _ in tempo_map]
    offsets_ms = [0.0]
    for index in range(1, len(tempo_map)):
        span = tempo_map[index][0] - tempo_map[index - 1][0]
        offsets_ms.append(offsets_ms[-1] + span * 60000.0 / tempo_map[index - 1][1])

    def convert(quarter_length: float) -> float:
        index = max(0, bisect_right(positions, quarter_length) - 1)
        return offsets_ms[index] + (quarter_length - positions[index]) * 60000.0 / tempo_map[
            index
        ][1]

    return convert


def parse_kern(text: str) -> KernScore:
    """Parse a ``**kern`` document into a :class:`KernScore`."""
    columns: list[_Column] | None = None
    tempo_changes: list[tuple[float, float]] = []
    meter: tuple[int, int] | None = None

    for raw_line in text.splitlines():
        line = raw_line.strip("\n")
        if not line.strip() or line.lstrip().startswith("!"):
            continue
        tokens = line.split("\t")
        if columns is None:
            if all(token.startswith("**") for token in tokens):
                columns = [_Column(is_kern=token == KERN_SPINE) for token in tokens]
            continue
        if all(token.startswith("*") for token in tokens):
            updated = []
            for token, column in _apply_interpretations(tokens, columns):
                if token in ("*^", "*v", ""):
                    updated.append(column)
                    continue
                column, meter = _process_interpretation_token(token, column, tempo_changes, meter)
                if column is not None:
                    updated.append(column)
            columns = updated
        elif columns:
            for token, column in zip(tokens, columns, strict=False):
                if column.is_kern:
                    _parse_token(column, token)

    notes: list[Note] = []
    voice_id = 0
    for column in columns or []:
        if column.notes:  # skip non-kern (e.g. **dynam) and empty columns
            notes.extend(replace(note, voice=voice_id) for note in column.notes)
            voice_id += 1
    notes.sort(key=lambda note: (note.on, note.pitch, note.voice, note.off))

    tempo_map = _tempo_map(tempo_changes)
    convert = _ql_to_ms_converter(tempo_map)
    timed_notes = [
        Note(pitch=note.pitch, on=convert(note.on), off=convert(note.off), voice=note.voice)
        for note in notes
    ]
    return KernScore(
        notes=timed_notes,
        meter=meter or DEFAULT_METER,
        tempo_qpm=tempo_map[0][1],
    )
