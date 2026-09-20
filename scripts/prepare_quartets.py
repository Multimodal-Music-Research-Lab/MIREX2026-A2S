#!/usr/bin/env python
"""Entry-point script: extract per-excerpt kern scores and audio from the
downloaded quartets parquet shards.

Usage:
    python scripts/prepare_quartets.py [--splits test] [--audio-format flac]
                                       [--limit 50]
                                       [--raw-dir $A2S_DATA_ROOT/quartets]
                                       [--output $A2S_DATA_ROOT/quartets_prepared]

Output layout: <output>/<split>/<track_id>.kern (+ <track_id>.<audio-format>,
unless --audio-format none). The test split provides the reference scores for
scripts/run_metrics.py.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from data_prep.constants import (
    DEFAULT_DATA_ROOT,
    QUARTETS_PREPARED_SUBDIR,
    QUARTETS_RAW_SUBDIR,
    SPLITS,
)
from data_prep.prepare_quartets import prepare_quartets


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--splits",
        nargs="+",
        choices=SPLITS,
        default=list(SPLITS),
        help="Splits to prepare (default: %(default)s)",
    )
    parser.add_argument(
        "--raw-dir",
        type=Path,
        default=DEFAULT_DATA_ROOT / QUARTETS_RAW_SUBDIR,
        help="Raw snapshot directory with data/*.parquet (default: %(default)s)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_DATA_ROOT / QUARTETS_PREPARED_SUBDIR,
        help="Destination root (default: %(default)s)",
    )
    parser.add_argument(
        "--audio-format",
        choices=["flac", "wav", "none"],
        default="flac",
        help="Audio output format (default: %(default)s; 'none' skips audio)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Maximum number of excerpts per split (for smoke runs)",
    )
    args = parser.parse_args()

    prepare_quartets(
        raw_dir=args.raw_dir,
        output_root=args.output,
        splits=args.splits,
        audio_format=args.audio_format,
        limit=args.limit,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
