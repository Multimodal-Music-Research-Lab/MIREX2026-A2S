#!/usr/bin/env python
"""Entry-point script: batch-evaluate a directory of predicted kern files
against a dataset's references.

Usage:
    python scripts/run_metrics.py --predictions <dir of .kern files>
                                  [--dataset quartets|quartets_add]
                                  [--references <dir of .kern files>]
                                  [--output results.json] [--csv results.csv]

References are selected by --dataset (default: quartets); --references
overrides it with an explicit directory. Predictions are paired with
references by track name (file stem). Results contain per-track metrics and
two aggregates: ``macro`` (mean of per-track values) and ``micro`` (pooled
errors / pooled counts).
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from a2s_metrics.constants import DEFAULT_DATA_ROOT
from a2s_metrics.evaluate_batch import evaluate_batch
from a2s_metrics.util import (
    collect_predictions,
    format_summary,
    load_kern_references,
    pair_predictions,
    write_metrics_csv,
    write_metrics_json,
)
from data_prep.constants import DATASETS, DEFAULT_DATASET, DEFAULT_SPLIT


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--predictions",
        type=Path,
        required=True,
        help="Directory with one <track_name>.kern file per piece",
    )
    parser.add_argument(
        "--dataset",
        choices=sorted(DATASETS),
        default=DEFAULT_DATASET,
        help="Dataset providing the reference scores (default: %(default)s)",
    )
    parser.add_argument(
        "--references",
        type=Path,
        default=None,
        help="Directory with the reference <track_name>.kern files "
        "(default: the prepared %(default)s split of --dataset)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Write full results (per track + aggregates) as JSON",
    )
    parser.add_argument("--csv", type=Path, default=None, help="Write per-track metrics as CSV")
    args = parser.parse_args()

    references_dir = args.references or (
        DEFAULT_DATA_ROOT / DATASETS[args.dataset] / DEFAULT_SPLIT
    )
    references = load_kern_references(references_dir)
    print(f"Loaded {len(references)} reference track(s) from {references_dir}\n")

    predictions = collect_predictions(args.predictions)
    pairs, missing, extra = pair_predictions(references, predictions)
    if not pairs:
        raise SystemExit(
            "No predictions could be paired with references. "
            f"Prediction files: {sorted(predictions)[:5]}...; "
            f"reference names: {sorted(references)[:5]}..."
        )
    if missing:
        print(f"WARNING: {len(missing)} reference track(s) without a prediction file:")
        for name in missing[:10]:
            print(f"  - {name}")
    if extra:
        print(f"WARNING: {len(extra)} prediction file(s) without a reference:")
        for name in extra[:10]:
            print(f"  - {name}")

    results = evaluate_batch(pairs)
    results["counts"] = {
        "evaluated": len(pairs),
        "missing_predictions": missing,
        "extra_predictions": extra,
    }
    print(format_summary(results))

    if args.output:
        write_metrics_json(results, args.output)
        print(f"Full results written to {args.output}")
    if args.csv:
        write_metrics_csv(results, args.csv)
        print(f"Per-track CSV written to {args.csv}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
