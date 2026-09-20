"""Batch evaluation of predicted kern files against the quartets references."""

from pathlib import Path

from a2s_metrics.kern import parse_kern
from a2s_metrics.mv2h import compute_mv2h
from a2s_metrics.text_metrics import compute_text_metrics
from a2s_metrics.util import aggregate_metrics


def evaluate_file(reference_text: str, hypothesis_text: str) -> dict[str, float]:
    """Compute every MIREX 2026 A2S metric for one piece.

    Returns:
        A flat dict with the core metric values (``WER``, ``CER``, ``LER``,
        ``MultiPitch``, ``Voice``, ``Meter``, ``NoteValue``, ``MV2H``) plus
        the pooling statistics used for micro aggregates (``<key>_errors`` /
        ``<key>_length`` for the text metrics, ``<key>_tp`` / ``<key>_err``
        for the MV2H F-scores, ``NoteValue_sum`` / ``NoteValue_n``).
    """
    results: dict[str, float] = {}
    for key, rate in compute_text_metrics(reference_text, hypothesis_text).items():
        results[key] = rate.value
        results[f"{key}_errors"] = rate.errors
        results[f"{key}_length"] = rate.reference_length
    results.update(
        compute_mv2h(parse_kern(reference_text), parse_kern(hypothesis_text))
    )
    return results


def evaluate_batch(pairs: list[tuple[str, str, str, Path]]) -> dict:
    """Evaluate paired (track, reference, hypothesis, path) kern texts.

    Returns:
        A dict with ``per_track`` metrics and ``aggregate`` metrics (macro =
        mean of per-track values, micro = pooled statistics).
    """
    if not pairs:
        raise ValueError("No (track, reference, hypothesis) pairs to evaluate.")
    per_track = {
        name: evaluate_file(reference, hypothesis)
        for name, reference, hypothesis, _path in pairs
    }
    macro, micro = aggregate_metrics(per_track)
    return {"per_track": per_track, "aggregate": {"macro": macro, "micro": micro}}
