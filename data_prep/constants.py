"""Constants for the data preparation package."""

import os
from pathlib import Path

# Base directory for all downloaded/derived data (per instructions, datasets
# live under /mnt/ssd/dhooge, not under /home). Override with the
# A2S_DATA_ROOT environment variable.
DEFAULT_DATA_ROOT = Path(os.environ.get("A2S_DATA_ROOT", "/mnt/ssd/dhooge"))

QUARTETS_RAW_SUBDIR = "quartets"
QUARTETS_PREPARED_SUBDIR = "quartets_prepared"

# Hugging Face is unreachable from some networks; hf-mirror.com is a working
# mirror of the Hub and is used by default (as in the MIREX2026-ALT repo).
HF_ENDPOINT_DEFAULT = "https://hf-mirror.com"
HF_QUARTETS_REPO = "PRAIG/quartets-quartets"

# Dataset splits, in repository order.
SPLITS = ("train", "val", "test")

# Audio format of the challenge input (and of the dataset audio).
AUDIO_SAMPLE_RATE = 22050
