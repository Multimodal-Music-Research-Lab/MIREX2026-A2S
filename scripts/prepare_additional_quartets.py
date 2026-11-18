#!/usr/bin/env python
"""Entry-point script: download the additional quartet sources and prepare
them for evaluation following the Roman et al. (2019) data rules.

Usage:
    python scripts/prepare_additional_quartets.py [--download-only]
        [--urls-file additional_quartets.txt]
        [--raw-dir $A2S_DATA_ROOT/quartets_add_raw]
        [--output $A2S_DATA_ROOT/quartets_add_prepared]
        [--split test] [--seed 0] [--min-measures 3] [--max-measures 6]
         [--soundfont <path to a SoundFont>]
         [--fourth-instrument flt]
        [--audio-format flac] [--limit N] [--skip-existing]

Each source score is split into non-overlapping fragments of 3-6 measures
(grace notes/ornaments removed, upper chord notes dropped, split spines
flattened, fragments with double dots/double sharps/double flats discarded).
Every fragment yields <track>.kern + <track>.flac (16-bit 22 050 Hz mono,
the challenge input format). The output can be evaluated with
scripts/run_metrics.py --dataset quartets_add.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from data_prep.constants import (
    ADDITIONAL_PREPARED_SUBDIR,
    ADDITIONAL_RAW_SUBDIR,
    DEFAULT_DATA_ROOT,
    DEFAULT_SOUNDFONT,
    DEFAULT_SYNTH_GAIN,
    FRAGMENT_MAX_MEASURES,
    FRAGMENT_MIN_MEASURES,
    FRAGMENT_SEED,
)
from data_prep.prepare_additional import download_additional, prepare_additional


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--urls-file",
        type=Path,
        default=None,
        help="File with the source URLs (default: additional_quartets.txt in the repo)",
    )
    parser.add_argument(
        "--raw-dir",
        type=Path,
        default=DEFAULT_DATA_ROOT / ADDITIONAL_RAW_SUBDIR,
        help="Directory for the downloaded kern/midi sources (default: %(default)s)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_DATA_ROOT / ADDITIONAL_PREPARED_SUBDIR,
        help="Destination root (default: %(default)s)",
    )
    parser.add_argument(
        "--split", default="test", help="Split name under --output (default: %(default)s)"
    )
    parser.add_argument(
        "--download-only",
        action="store_true",
        help="Only download the kern/midi sources, skip preparation",
    )
    parser.add_argument("--seed", type=int, default=FRAGMENT_SEED, help="Fragmentation seed")
    parser.add_argument(
        "--min-measures", type=int, default=FRAGMENT_MIN_MEASURES, help="Minimum fragment size"
    )
    parser.add_argument(
        "--max-measures", type=int, default=FRAGMENT_MAX_MEASURES, help="Maximum fragment size"
    )
    parser.add_argument(
        "--soundfont",
        type=Path,
        default=DEFAULT_SOUNDFONT,
        help="Soundfont for fluidsynth (required unless --audio-format none)",
    )
    parser.add_argument(
        "--gain",
        type=float,
        default=DEFAULT_SYNTH_GAIN,
        help="fluidsynth gain (default: %(default)s)",
    )
    parser.add_argument(
        "--fourth-instrument",
        default=None,
        help="Replace the fourth **kern instrument code before synthesis (e.g. flt)",
    )
    parser.add_argument(
        "--audio-format",
        choices=["flac", "none"],
        default="flac",
        help="Audio output format (default: %(default)s; 'none' skips synthesis)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Maximum number of fragments per source (for smoke runs)",
    )
    parser.add_argument(
        "--skip-existing",
        action="store_true",
        help="Skip fragments whose output files already exist",
    )
    args = parser.parse_args()

    from data_prep.constants import ADDITIONAL_URLS_FILE

    urls_file = args.urls_file or ADDITIONAL_URLS_FILE
    download_additional(args.raw_dir, urls_file)
    if args.download_only:
        return 0
    if args.soundfont is None and args.audio_format != "none":
        parser.error("--soundfont is required unless --audio-format none is selected")
    if args.soundfont is not None and not args.soundfont.exists():
        raise SystemExit(f"Soundfont not found: {args.soundfont}")
    prepare_additional(
        raw_dir=args.raw_dir,
        output_root=args.output,
        split=args.split,
        seed=args.seed,
        min_measures=args.min_measures,
        max_measures=args.max_measures,
        soundfont=args.soundfont,
        audio_format=args.audio_format,
        gain=args.gain,
        fourth_instrument=args.fourth_instrument,
        limit=args.limit,
        skip_existing=args.skip_existing,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
