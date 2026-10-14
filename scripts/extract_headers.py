#!/usr/bin/env python
"""Entry-point script: extract the staves metadata headers of the prepared
quartets excerpts for the Staves-Informed A2S track.

Usage:
    python scripts/extract_headers.py [--input $A2S_DATA_ROOT/quartets_prepared]
                                      [--output $A2S_DATA_ROOT/quartets_headers]
                                      [--kern-only-output $A2S_DATA_ROOT/quartets_headers_kern_only]

For every ``<track>.kern`` file under --input (all splits), the leading block
of ``*`` lines (the staves metadata provided to Staves-Informed systems) is
written to ``<output>/<split>/<track>.krn``, mirroring the input layout. A
second copy keeping only the ``**kern`` spines (exactly 4 per quartets
excerpt) is written to ``--kern-only-output``.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from data_prep.constants import (
    DEFAULT_DATA_ROOT,
    QUARTETS_HEADERS_KERN_ONLY_SUBDIR,
    QUARTETS_HEADERS_SUBDIR,
    QUARTETS_PREPARED_SUBDIR,
)
from data_prep.extract_headers import extract_headers


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=DEFAULT_DATA_ROOT / QUARTETS_PREPARED_SUBDIR,
        help="Directory with the prepared <track>.kern excerpts (default: %(default)s)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_DATA_ROOT / QUARTETS_HEADERS_SUBDIR,
        help="Destination root for the <track>.krn header files (default: %(default)s)",
    )
    parser.add_argument(
        "--kern-only-output",
        type=Path,
        default=DEFAULT_DATA_ROOT / QUARTETS_HEADERS_KERN_ONLY_SUBDIR,
        help="Destination root for the **kern-only header files (default: %(default)s)",
    )
    args = parser.parse_args()

    extract_headers(input_dir=args.input, output_dir=args.output, kern_only_dir=args.kern_only_output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
