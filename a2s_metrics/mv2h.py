"""MV2H adapted to ``**kern`` scores, following the reference implementations.

The components mirror the official MV2H code (apmcleod/MV2H) and its Python
port (lucasmpaim/pyMV2H), which the MIREX 2026 A2S evaluation pipeline builds
on via the A2S Transformer repository (Alfaro-Contreras et al., 2024):

- **Multi-pitch detection**: F1 over notes matched by pitch with onsets
  within ``ONSET_DELTA_MS``.
- **Voice separation**: F1 over the "connections" (note clusters chained
  within a voice) of correctly detected notes.
- **Metrical alignment**: F1 over bar / beat / sub-beat groupings derived
  from the time signature and tempo of each file.
- **Note value detection**: mean per-note duration score over the notes that
  are multi-pitch and voice matches.

The harmonic analysis component is excluded for this edition of the
challenge (the released datasets do not provide chord information), so
``MV2H`` is the mean of the four components above.
"""

from dataclasses import dataclass, field
from itertools import pairwise

from a2s_metrics.constants import (
    DEFAULT_TEMPO_QPM,
    DURATION_DELTA_MS,
    GROUPING_EPSILON_MS,
    ONSET_DELTA_MS,
)
from a2s_metrics.kern import KernScore, Note

# The MV2H reference implementations report 0.0 for degenerate (empty)
# comparisons; we keep that convention.
DEGENERATE_F1 = 0.0


def f1_score(true_positives: float, false_positives: float, false_negatives: float) -> float:
    """F1 score with the reference implementation's zero-denominator handling."""
    denominator = 2.0 * true_positives + false_positives + false_negatives
    if denominator <= 0:
        return DEGENERATE_F1
    return 2.0 * true_positives / denominator


def match_notes(reference_notes: list[Note], transcription_notes: list[Note]) -> dict[Note, Note]:
    """Greedy (pitch, onset) matching between reference and transcription.

    Mirrors ``match_note_list`` of the reference implementations: iterate the
    transcription notes in order, pairing each with the first still-unmatched
    reference note of the same pitch within ``ONSET_DELTA_MS``.
    """
    onset_order = lambda note: (note.on, note.pitch, note.voice, note.off)
    reference_pool = sorted(reference_notes, key=onset_order)
    matches: dict[Note, Note] = {}
    for trans_note in sorted(transcription_notes, key=onset_order):
        for index, ref_note in enumerate(reference_pool):
            if ref_note.pitch == trans_note.pitch and abs(ref_note.on - trans_note.on) <= (
                ONSET_DELTA_MS
            ):
                matches[trans_note] = ref_note
                del reference_pool[index]
                break
    return matches


@dataclass
class _Cluster:
    """Notes sharing (onset, offset) within one voice, plus its successors."""

    on: float
    off: float
    notes: list[Note] = field(default_factory=list)
    successors: list["_Cluster"] = field(default_factory=list)


def _build_voices(notes: list[Note]) -> dict[int, dict[tuple[float, float], _Cluster]]:
    """Group notes by voice, then into (onset, offset) clusters."""
    voices: dict[int, dict[tuple[float, float], _Cluster]] = {}
    for note in notes:
        clusters = voices.setdefault(note.voice, {})
        cluster = clusters.setdefault((note.on, note.off), _Cluster(note.on, note.off))
        cluster.notes.append(note)
    return voices


def _cluster_connections(clusters: dict[tuple[float, float], _Cluster]) -> None:
    """Fill ``cluster.successors`` in place: the clusters starting at (or,
    if none start exactly there, closest after) this cluster's offset time.
    Mirrors ``Voice.create_connections`` of the reference implementation."""
    ordered = sorted(clusters.values(), key=lambda cluster: (cluster.on, cluster.off))
    for base in ordered:
        base.successors = []
        for candidate in ordered:
            if candidate is base:
                continue
            if candidate.on == base.off:
                base.successors.append(candidate)
            elif candidate.on > base.off:
                if not base.successors or base.successors[0].on == candidate.on:
                    base.successors.append(candidate)
                else:
                    break


def _successor_notes(cluster: _Cluster) -> list[Note]:
    """Flatten the notes in a cluster's directly connected successors."""
    return [note for successor in cluster.successors for note in successor.notes]


def _find_cluster(
    voices: dict[int, dict[tuple[float, float], _Cluster]], note: Note
) -> _Cluster | None:
    """Find the cluster containing a note in its voice's cluster map."""
    return voices.get(note.voice, {}).get((note.on, note.off))


def _notes_match(reference: Note, transcription: Note) -> bool:
    """Return whether two notes meet the MV2H pitch and onset criteria."""
    return reference.pitch == transcription.pitch and (
        abs(reference.on - transcription.on) <= ONSET_DELTA_MS
    )


def voice_f1(
    reference_notes: list[Note],
    transcription_notes: list[Note],
    matches: dict[Note, Note],
) -> tuple[float, float, float, list[Note]]:
    """Voice separation F1, mirroring ``voice_score`` of pyMV2H.

    Returns:
        ``(f1, true_positives, errors, voice_notes)`` where ``errors`` pools
        false positives and false negatives, and ``voice_notes`` lists the
        transcription notes whose voice connections are consistent with the
        reference (the population of the note value metric).
    """
    # Voices restricted to correctly detected notes drive the connection
    # comparison; the original reference voices drive the note-value mapping.
    ref_matched_voices = _build_voices(list(matches.values()))
    trans_matched_voices = _build_voices(list(matches.keys()))
    ref_all_voices = _build_voices(reference_notes)
    for voices in (ref_matched_voices, trans_matched_voices, ref_all_voices):
        for clusters in voices.values():
            _cluster_connections(clusters)

    true_positives = 0.0
    errors = 0.0
    voice_notes: list[Note] = []
    for trans_clusters in trans_matched_voices.values():
        for cluster in trans_clusters.values():
            next_trans_notes = _successor_notes(cluster)
            for trans_note in cluster.notes:
                ref_note = matches[trans_note]
                ref_cluster = _find_cluster(ref_matched_voices, ref_note)
                next_ref_notes = _successor_notes(ref_cluster) if ref_cluster else []
                connection_tp = len(match_notes(next_ref_notes, next_trans_notes))
                connection_errors = abs(connection_tp - len(next_trans_notes)) + abs(
                    connection_tp - len(next_ref_notes)
                )
                weight = (len(next_ref_notes) + len(next_trans_notes)) / 2.0
                if weight > 0:
                    normalization = weight * len(cluster.notes)
                    true_positives += connection_tp / normalization
                    errors += connection_errors / normalization

                # Voice-consistency mapping for the note value metric.
                original_cluster = _find_cluster(ref_all_voices, ref_note)
                next_original_notes = (
                    _successor_notes(original_cluster) if original_cluster else []
                )
                if not next_original_notes and not next_trans_notes or any(
                    _notes_match(ref_next, trans_next)
                    for ref_next in next_original_notes
                    for trans_next in next_trans_notes
                ):
                    voice_notes.append(trans_note)

    return f1_score(true_positives, errors, 0.0), true_positives, errors, voice_notes


def multi_pitch_f1(
    matches: dict[Note, Note], reference_count: int, transcription_count: int
) -> tuple[float, float, float]:
    """Multi-pitch detection F1 from a pre-computed note matching.

    Returns ``(f1, true_positives, errors)`` with ``errors`` pooling false
    positives and false negatives.
    """
    true_positives = float(len(matches))
    false_positives = abs(true_positives - transcription_count)
    false_negatives = abs(true_positives - reference_count)
    return (
        f1_score(true_positives, false_positives, false_negatives),
        true_positives,
        false_positives + false_negatives,
    )


def _sub_beats_per_quarter(meter: tuple[int, int]) -> float:
    """Sub-beats per quarter note, as defined by the reference MIDI converter
    (half of a quarter in simple meters, a quarter of one in compound)."""
    numerator, denominator = meter
    if numerator > 3 and numerator % 3 == 0:
        return denominator / 4
    return denominator / 2


def _beat_structure(meter: tuple[int, int]) -> tuple[float, float]:
    """(beats per bar, sub-beats per beat) of a time signature, following the
    hierarchy of the reference MIDI converter."""
    numerator = meter[0]
    if numerator > 3 and numerator % 3 == 0:
        return numerator / 3, 3.0
    return float(numerator), 2.0


def meter_groupings(
    meter: tuple[int, int],
    tempo_qpm: float,
    duration_ms: float,
) -> list[tuple[float, float]]:
    """Bar / beat / sub-beat groupings of a score (mirrors ``meter_score``).

    The metrical grid is a uniform sub-beat grid starting at time 0 (as
    produced by the reference MIDI converter: one tatum per sub-beat,
    anacrusis 0), and groupings are the intervals between consecutive marks
    at each level (sub-beat, beat, bar).
    """
    beats_per_bar, sub_beats_per_beat = _beat_structure(meter)
    ms_per_quarter = 60000.0 / (tempo_qpm or DEFAULT_TEMPO_QPM)
    ms_per_sub_beat = ms_per_quarter / _sub_beats_per_quarter(meter)

    tatums = []
    time = 0.0
    while time <= duration_ms:
        tatums.append(time)
        time += ms_per_sub_beat

    groups: list[tuple[float, float]] = []
    for period in (1.0, sub_beats_per_beat, sub_beats_per_beat * beats_per_bar):
        marks = [tatums[index] for index in range(len(tatums)) if index % period == 0]
        groups.extend(pairwise(marks))
    return groups


def meter_f1(reference: KernScore, transcription: KernScore) -> tuple[float, float, float]:
    """Metrical alignment F1 with its (tp, errors) counts."""
    ref_duration = max((note.off for note in reference.notes), default=0.0)
    trans_duration = max((note.off for note in transcription.notes), default=0.0)
    ref_groups = meter_groupings(reference.meter, reference.tempo_qpm, ref_duration)
    trans_groups = meter_groupings(transcription.meter, transcription.tempo_qpm, trans_duration)

    true_positives = 0
    pool = list(trans_groups)
    for ref_group in ref_groups:
        for index, trans_group in enumerate(pool):
            if (
                abs(ref_group[0] - trans_group[0]) <= GROUPING_EPSILON_MS
                and abs(ref_group[1] - trans_group[1]) <= GROUPING_EPSILON_MS
            ):
                true_positives += 1
                del pool[index]
                break
    false_positives = float(len(ref_groups) - true_positives)
    false_negatives = float(len(trans_groups) - true_positives)
    return (
        f1_score(true_positives, false_positives, false_negatives),
        float(true_positives),
        false_positives + false_negatives,
    )


def note_value_score(
    matches: dict[Note, Note], voice_notes: list[Note]
) -> tuple[float, float, float]:
    """Note value detection score, mirroring ``note_value_score`` of pyMV2H.

    Averages a per-note duration score over the transcription notes whose
    voice connections match the reference: 1.0 if the durations are within
    ``DURATION_DELTA_MS``, otherwise ``max(0, 1 - diff / reference_duration)``.

    Returns ``(value, sum_of_scores, number_of_notes)`` for pooling.
    """
    if not voice_notes:
        return DEGENERATE_F1, 0.0, 0.0
    total = 0.0
    for trans_note in voice_notes:
        ref_note = matches[trans_note]
        ref_duration = abs(ref_note.off - ref_note.on)
        diff = abs(ref_duration - abs(trans_note.off - trans_note.on))
        if diff < DURATION_DELTA_MS:
            total += 1.0
        elif ref_duration > 0:
            total += max(0.0, 1.0 - diff / ref_duration)
    return total / len(voice_notes), total, float(len(voice_notes))


def compute_mv2h(reference: KernScore, transcription: KernScore) -> dict[str, float]:
    """Compute the MV2H components between two parsed kern scores.

    Returns:
        A dict with the four component scores (``MultiPitch``, ``Voice``,
        ``Meter``, ``NoteValue``) plus their pooled statistics
        (``<key>_tp`` / ``<key>_err``, or ``<key>_sum`` / ``<key>_n`` for the
        note value average) and the overall ``MV2H`` (mean of the components;
        harmonic analysis is excluded for the released dataset).
    """
    matches = match_notes(reference.notes, transcription.notes)
    multi_pitch, mp_tp, mp_err = multi_pitch_f1(
        matches, len(reference.notes), len(transcription.notes)
    )
    voice, voice_tp, voice_err, voice_notes = voice_f1(
        reference.notes, transcription.notes, matches
    )
    meter, meter_tp, meter_err = meter_f1(reference, transcription)
    note_value, nv_sum, nv_count = note_value_score(matches, voice_notes)

    return {
        "MultiPitch": multi_pitch,
        "MultiPitch_tp": mp_tp,
        "MultiPitch_err": mp_err,
        "Voice": voice,
        "Voice_tp": voice_tp,
        "Voice_err": voice_err,
        "Meter": meter,
        "Meter_tp": meter_tp,
        "Meter_err": meter_err,
        "NoteValue": note_value,
        "NoteValue_sum": nv_sum,
        "NoteValue_n": nv_count,
        "MV2H": (multi_pitch + voice + meter + note_value) / 4.0,
    }
