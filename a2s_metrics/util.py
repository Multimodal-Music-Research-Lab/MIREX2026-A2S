"""Shared helpers for batch evaluation: reference loading, prediction pairing,
aggregation and result serialization."""

import csv
import json
from pathlib import Path

from a2s_metrics.constants import KERN_SPINE, MV2H_COMPONENT_KEYS, MV2H_KEY, TEXT_METRIC_KEYS

# Per-metric pooling statistics emitted by evaluate_file, used for micro
# aggregates: (numerator key, denominator key, pooled kind).
_POOLING = {
    "WER": ("WER_errors", "WER_length", "ratio"),
    "CER": ("CER_errors", "CER_length", "ratio"),
    "LER": ("LER_errors", "LER_length", "ratio"),
    "MultiPitch": ("MultiPitch_tp", "MultiPitch_err", "f1"),
    "Voice": ("Voice_tp", "Voice_err", "f1"),
    "Meter": ("Meter_tp", "Meter_err", "f1"),
    "NoteValue": ("NoteValue_sum", "NoteValue_n", "ratio"),
}
CORE_METRIC_KEYS = TEXT_METRIC_KEYS + MV2H_COMPONENT_KEYS + (MV2H_KEY,)


def keep_kern_spines(text: str) -> str:
    """Drop every spine column that is not a ``**kern`` spine (e.g. ``**dynam``).

    Spine types are read from the first exclusive-interpretation record
    (``**kern  **dynam  ...``); that record and all following records (data,
    comments, interpretations and ``*-`` terminators) keep only the ``**kern``
    columns. Files without an exclusive-interpretation record, or without any
    ``**kern`` spine, are returned unchanged. Spine path records (``*^`` /
    ``*v``) do not occur in the evaluation data and are not tracked.
    """
    lines = text.splitlines()
    for index, line in enumerate(lines):
        tokens = line.split("\t")
        if not (tokens and all(token.startswith("**") for token in tokens)):
            continue
        kern_columns = {i for i, token in enumerate(tokens) if token == KERN_SPINE}
        if not kern_columns:
            return text
        kept = lines[:index] + [
            "\t".join(token for i, token in enumerate(l.split("\t")) if i in kern_columns)
            for l in lines[index:]
        ]
        return "\n".join(kept)
    return text


def load_kern_references(references_dir: Path, kern_only: bool = False) -> dict[str, str]:
    """Load reference kern texts from ``<references_dir>/*.kern`` by stem.

    With ``kern_only``, every spine that is not ``**kern`` (e.g. ``**dynam``)
    is removed from the references (see :func:`keep_kern_spines`).
    """
    references_dir = Path(references_dir)
    if not references_dir.is_dir():
        raise FileNotFoundError(f"References directory not found: {references_dir}")
    references = {path.stem: path.read_text(encoding="utf-8") for path in
                  sorted(references_dir.glob("*.kern"))}
    if not references:
        raise FileNotFoundError(f"No *.kern reference files found in {references_dir}")
    if kern_only:
        references = {name: keep_kern_spines(text) for name, text in references.items()}
    return references


def collect_predictions(predictions_dir: Path) -> dict[str, Path]:
    """Map each ``*.kern`` file in ``predictions_dir`` to its track stem."""
    predictions_dir = Path(predictions_dir)
    if not predictions_dir.is_dir():
        raise FileNotFoundError(f"Predictions directory not found: {predictions_dir}")
    predictions = {path.stem: path for path in sorted(predictions_dir.glob("*.krn"))}
    if not predictions:
        raise FileNotFoundError(f"No *.kern prediction files found in {predictions_dir}")
    return predictions


def pair_predictions(
    references: dict[str, str],
    predictions: dict[str, Path],
    kern_only: bool = False,
) -> tuple[list[tuple[str, str, str, Path]], list[str], list[str]]:
    """Pair predictions with references by track stem.

    Args:
        references: Reference texts by track stem (as returned by
            :func:`load_kern_references`).
        predictions: Prediction file paths by track stem.
        kern_only: Drop every non-``**kern`` spine (e.g. ``**dynam``) from the
            predictions (see :func:`keep_kern_spines`).

    Returns:
        ``(pairs, missing, extra)`` where ``pairs`` holds
        ``(track, reference_text, hypothesis_text, prediction_path)`` triples,
        and ``missing`` / ``extra`` list unmatched reference / prediction
        names respectively.
    """
    pairs, extra = [], []
    for name, path in predictions.items():
        if name in references:
            hypothesis = path.read_text(encoding="utf-8")
            if kern_only:
                hypothesis = keep_kern_spines(hypothesis)
            pairs.append((name, references[name], hypothesis, path))
        else:
            extra.append(name)
    missing = [name for name in references if name not in predictions]
    return pairs, missing, extra


def _pooled(numerator: float, denominator: float, kind: str) -> float:
    if kind == "f1":
        return 2.0 * numerator / (2.0 * numerator + denominator) if (numerator > 0) else 0.0
    if denominator == 0:
        return 0.0
    return numerator / denominator


def aggregate_metrics(per_track: dict[str, dict[str, float]]) -> tuple[dict[str, float], dict[str, float]]:
    """Aggregate per-track metrics into macro and micro averages.

    macro: unweighted mean of per-track values for each core metric.
    micro: pooled statistics (sum of errors over sum of reference sizes for
    error rates and the note value average, pooled F1 counts for the MV2H
    F-score components); MV2H itself is the mean of the pooled components.
    """
    if not per_track:
        raise ValueError("No per-track metrics to aggregate.")
    macro = {
        key: sum(track[key] for track in per_track.values()) / len(per_track)
        for key in CORE_METRIC_KEYS
    }
    micro = {}
    for key, (numerator_key, denominator_key, kind) in _POOLING.items():
        numerator = sum(track[numerator_key] for track in per_track.values())
        denominator = sum(track[denominator_key] for track in per_track.values())
        micro[key] = _pooled(numerator, denominator, kind)
    micro[MV2H_KEY] = sum(micro[component] for component in MV2H_COMPONENT_KEYS) / len(
        MV2H_COMPONENT_KEYS
    )
    return macro, micro


def format_summary(results: dict) -> str:
    """Render a compact human-readable summary of the aggregate metrics."""
    lines = [f"Evaluated {results['counts']['evaluated']} track(s).", ""]
    for label, metrics in results["aggregate"].items():
        lines.append(f"[{label}]")
        lines.append(f"  WER        : {metrics['WER']:.4f}")
        lines.append(f"  CER        : {metrics['CER']:.4f}")
        lines.append(f"  LER        : {metrics['LER']:.4f}")
        lines.append(f"  Multi-pitch: {metrics['MultiPitch']:.4f}")
        lines.append(f"  Voice      : {metrics['Voice']:.4f}")
        lines.append(f"  Meter      : {metrics['Meter']:.4f}")
        lines.append(f"  Note value : {metrics['NoteValue']:.4f}")
        lines.append(f"  MV2H       : {metrics['MV2H']:.4f}")
        lines.append("")
    return "\n".join(lines)


def write_metrics_json(results: dict, output_path: Path) -> None:
    """Serialize the full batch results (per-track and aggregates) as JSON."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as fh:
        json.dump(results, fh, indent=2, ensure_ascii=False)


def write_metrics_csv(results: dict, output_path: Path) -> None:
    """Write per-track core metrics to CSV, with aggregate rows appended."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    rows = [{"track": name, **{key: metrics[key] for key in CORE_METRIC_KEYS}}
            for name, metrics in results["per_track"].items()]
    rows.append({"track": "AGGREGATE_MACRO", **results["aggregate"]["macro"]})
    rows.append({"track": "AGGREGATE_MICRO", **results["aggregate"]["micro"]})
    with output_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
