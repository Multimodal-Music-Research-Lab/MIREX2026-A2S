#!/usr/bin/env python
"""Entry-point script: download the quartets dataset (raw parquet shards).

Usage:
    python scripts/download_quartets.py [--splits test val train]
                                        [--output $A2S_DATA_ROOT/quartets]
                                        [--endpoint https://hf-mirror.com]
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from data_prep.constants import (
    DEFAULT_DATA_ROOT,
    QUARTETS_RAW_SUBDIR,
    SPLITS,
)
from data_prep.prepare_quartets import download_quartets


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--splits",
        nargs="+",
        choices=SPLITS,
        default=list(SPLITS),
        help="Splits to download (default: %(default)s)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_DATA_ROOT / QUARTETS_RAW_SUBDIR,
        help="Destination directory (default: %(default)s)",
    )
    parser.add_argument(
        "--endpoint",
        default=None,
        help="Hugging Face endpoint (default: hf-mirror.com unless $HF_ENDPOINT is set)",
    )
    args = parser.parse_args()

    download_quartets(output_root=args.output, splits=args.splits, endpoint=args.endpoint)
    return 0


if __name__ == "__main__":
    sys.exit(main())
