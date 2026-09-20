#!/usr/bin/env python
"""Entry-point script: batch-evaluate a directory of predicted kern files
against the quartets references.

Usage:
    python scripts/run_metrics.py --predictions <dir of .kern files>
                                  [--references $A2S_DATA_ROOT/quartets_prepared/test]
                                  [--output results.json] [--csv results.csv]

Predictions are paired with references by track name (file stem). Results
contain per-track metrics and two aggregates: ``macro`` (mean of per-track
values) and ``micro`` (pooled errors / pooled counts).
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
from data_prep.constants import QUARTETS_PREPARED_SUBDIR


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
        "--references",
        type=Path,
        default=DEFAULT_DATA_ROOT / QUARTETS_PREPARED_SUBDIR / "test",
        help="Directory with the reference <track_name>.kern files "
        "(default: the prepared quartets test split)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Write full results (per track + aggregates) as JSON",
    )
    parser.add_argument("--csv", type=Path, default=None, help="Write per-track metrics as CSV")
    args = parser.parse_args()

    references = load_kern_references(args.references)
    print(f"Loaded {len(references)} reference track(s) from {args.references}\n")

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
