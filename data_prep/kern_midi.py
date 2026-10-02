"""MIDI rendering of prepared kern fragments.

Each fragment reference score is converted to a type-1 Standard MIDI File
(one track per ``**kern`` spine) with the ``*MM`` tempo map of the fragment,
so that the synthesized audio matches the reference exactly: same notes
(chords reduced to their lowest note, grace notes skipped, ties merged),
same onsets and durations, same tempo. This mirrors the hum2mid step of the
Roman et al. (2019) data pipeline.
"""

import mido

from a2s_metrics.kern import _parse_duration, _pitches_in
from data_prep.constants import INSTRUMENT_PROGRAMS, MIDI_PPQ

DEFAULT_TEMPO_QPM = 120.0
NOTE_VELOCITY = 90


def _midi_program(code: str | None) -> int | None:
    """General MIDI program for a kern ``*I`` instrument code."""
    if code is None:
        return None
    return INSTRUMENT_PROGRAMS.get(code.removeprefix("*I").strip())


def parse_fragment_performance(text: str) -> dict:
    """Extract the performance information of one fragment.

    Returns a dict with ``column_notes`` (one note list per ``**kern`` column,
    each note an ``(onset_q, off_q, pitch)`` tuple with ties merged),
    ``tempo_map`` (sorted ``(position_q, qpm)``), ``meter`` and ``programs``
    (one ``*I`` code per kern column, or None).
    """
    kern_indices: list[int] = []
    notes: list[list[tuple[float, float, int]]] = []
    open_ties: list[dict[int, int]] = []
    positions: list[float] = []
    programs: list[str | None] = []
    tempo_points: dict[float, float] = {}
    meter = None

    for raw_line in text.splitlines():
        if not raw_line.strip() or raw_line.lstrip().startswith("!"):
            continue
        tokens = raw_line.split("\t")
        if not kern_indices:
            if all(token.startswith("**") for token in tokens):
                kern_indices = [i for i, token in enumerate(tokens) if token == "**kern"]
                count = len(kern_indices)
                notes, open_ties = [[] for _ in range(count)], [{} for _ in range(count)]
                positions, programs = [0.0] * count, [None] * count
            continue
        if all(token.startswith("*") for token in tokens):
            position = max(positions, default=0.0)
            for column, index in enumerate(kern_indices):
                token = tokens[index] if index < len(tokens) else "*"
                if token.startswith("*MM"):
                    try:
                        qpm = float(token[3:])
                    except ValueError:
                        continue
                    if qpm > 0.0:
                        tempo_points.setdefault(position, qpm)
                elif token.startswith("*I"):
                    programs[column] = token
                elif meter is None and token.startswith("*M") and "/" in token:
                    try:
                        numerator, denominator = token[2:].split("/")[:2]
                        meter = (int(numerator), int(denominator))
                    except ValueError:
                        pass
            continue
        if all(token.startswith("=") for token in tokens):
            continue
        for column, index in enumerate(kern_indices):
            cell = tokens[index] if index < len(tokens) else "."
            _parse_data_cell(cell, notes[column], open_ties[column], positions, column)

    tempo_map = sorted(tempo_points.items())
    if not tempo_map or tempo_map[0][0] > 0.0:
        tempo_map.insert(0, (0.0, DEFAULT_TEMPO_QPM))
    return {
        "column_notes": notes,
        "tempo_map": tempo_map,
        "meter": meter,
        "programs": programs,
    }


def _parse_data_cell(
    cell: str,
    notes: list[tuple[float, float, int]],
    open_ties: dict[int, int],
    positions: list[float],
    column: int,
) -> None:
    """Parse one kern data cell, appending notes and advancing the column."""
    if cell == "." or cell.startswith("="):
        return
    advance = 0.0
    for sub_token in cell.split():
        quarter_length, remainder, is_grace = _parse_duration(sub_token)
        if is_grace or quarter_length <= 0.0:
            continue
        advance = max(advance, quarter_length)
        if remainder.startswith("r"):
            continue
        pitches = _pitches_in(remainder)
        if not pitches:
            continue
        pitch = pitches[0]  # chords were reduced to their lowest note
        tie_start, tie_end = "[" in remainder, "]" in remainder
        on, off = positions[column], positions[column] + quarter_length
        if (open_index := open_ties.get(pitch)) is not None:
            previous_on, _, _ = notes[open_index]
            notes[open_index] = (previous_on, off, pitch)
            if tie_end and not tie_start:
                del open_ties[pitch]
        else:
            notes.append((on, off, pitch))
            if tie_start or "_" in remainder:
                open_ties[pitch] = len(notes) - 1
    positions[column] += advance


def fragment_to_midi(text: str, ppq: int = MIDI_PPQ) -> mido.MidiFile:
    """Convert one prepared fragment reference score to a MIDI file."""
    performance = parse_fragment_performance(text)
    midi = mido.MidiFile(type=1, ticks_per_beat=ppq)

    conductor = midi.add_track()
    meter = performance["meter"]
    if meter and meter[1] in (1, 2, 4, 8, 16, 32, 64):
        conductor.append(
            mido.MetaMessage(
                "time_signature",
                numerator=meter[0],
                denominator=meter[1],
                clocks_per_click=24,
                notated_32nd_notes_per_beat=8,
                time=0,
            )
        )
    last_tick = 0
    for position_q, qpm in performance["tempo_map"]:
        tick = round(position_q * ppq)
        conductor.append(
            mido.MetaMessage("set_tempo", tempo=mido.bpm2tempo(qpm), time=max(0, tick - last_tick))
        )
        last_tick = tick

    for channel, (column_notes, program_code) in enumerate(
        zip(performance["column_notes"], performance["programs"])
    ):
        if not column_notes:
            continue
        track = midi.add_track()
        program = _midi_program(program_code) or _fallback_program(column_notes)
        track.append(
            mido.Message("program_change", program=program, channel=channel, time=0)
        )
        events: list[tuple[int, bool, int]] = []
        for on_q, off_q, pitch in column_notes:
            on_tick = round(on_q * ppq)
            off_tick = max(on_tick + 1, round(off_q * ppq))
            events.append((on_tick, True, pitch))
            events.append((off_tick, False, pitch))
        last_tick = 0
        for tick, is_on, pitch in sorted(events, key=lambda event: (event[0], not event[1])):
            track.append(
                mido.Message(
                    "note_on" if is_on else "note_off",
                    note=pitch,
                    velocity=NOTE_VELOCITY if is_on else 0,
                    channel=channel,
                    time=tick - last_tick,
                )
            )
            last_tick = tick
    return midi


def _fallback_program(notes: list[tuple[float, float, int]]) -> int:
    """Instrument program for a column without a ``*I`` code, by register."""
    median = sorted(pitch for _, _, pitch in notes)[len(notes) // 2]
    if median < 48:  # below C3
        return 42  # cello
    if median < 60:  # below C4
        return 41  # viola
    return 40  # violin
