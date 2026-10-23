"""Constants for the data preparation package."""

import os
from pathlib import Path

# Base directory for all downloaded/derived data (per instructions, datasets
# live under /mnt/ssd/dhooge, not under /home). Override with the
# A2S_DATA_ROOT environment variable.
DEFAULT_DATA_ROOT = Path(os.environ.get("A2S_DATA_ROOT", "/mnt/ssd/dhooge"))

QUARTETS_RAW_SUBDIR = "quartets"
QUARTETS_PREPARED_SUBDIR = "quartets_prepared"

# Staves metadata for the Staves-Informed A2S track: the header of each
# prepared excerpt (its leading '*' lines), one <track>.krn file per excerpt.
QUARTETS_HEADERS_SUBDIR = "quartets_headers"
# Variant keeping only the **kern spines of each header (e.g. no **dynam).
QUARTETS_HEADERS_KERN_ONLY_SUBDIR = "quartets_headers_kern_only"

# Number of **kern spines per quartets excerpt (one voice per instrument).
KERN_SPINES_PER_EXCERPT = 4

# Hugging Face is unreachable from some networks; hf-mirror.com is a working
# mirror of the Hub and is used by default (as in the MIREX2026-ALT repo).
HF_ENDPOINT_DEFAULT = "https://hf-mirror.com"
HF_QUARTETS_REPO = "PRAIG/quartets-quartets"

# Dataset splits, in repository order.
SPLITS = ("train", "val", "test")

# Default split used for evaluation references.
DEFAULT_SPLIT = "test"

# Audio format of the challenge input (and of the dataset audio).
AUDIO_SAMPLE_RATE = 22050

# --------------------------------------------------------------------------
# Additional quartets dataset (kern.ccarh.org sources, URLs listed in
# additional_quartets.txt at the repository root). Prepared following the
# data preparation rules of Roman et al. (2019): 3-6 measure fragments,
# grace notes/ornaments removed, upper chord notes dropped, split spines
# flattened, fragments with double dots/double sharps/double flats discarded.
ADDITIONAL_URLS_FILE = Path(__file__).resolve().parents[1] / "additional_quartets.txt"
ADDITIONAL_RAW_SUBDIR = "quartets_add_raw"
ADDITIONAL_PREPARED_SUBDIR = "quartets_add_prepared"
ADDITIONAL_FLUTE_PREPARED_SUBDIR = "quartets_add_flute_prepared"
ADDITIONAL_FLUTE_HEADERS_SUBDIR = "quartets_add_flute_headers"
ADDITIONAL_FLUTE_HEADERS_KERN_ONLY_SUBDIR = "quartets_add_flute_headers_kern_only"

# Evaluation dataset registry (--dataset): name -> prepared-data subdir.
DATASETS = {
    "quartets": QUARTETS_PREPARED_SUBDIR,
    "quartets_add": ADDITIONAL_PREPARED_SUBDIR,
    "quartets_add_flute": ADDITIONAL_FLUTE_PREPARED_SUBDIR,
}
DEFAULT_DATASET = "quartets"

# Fragmentation of the additional sources (Roman et al., 2019, section 2.3).
FRAGMENT_MIN_MEASURES = 3
FRAGMENT_MAX_MEASURES = 6
FRAGMENT_SEED = 0

# MIDI synthesis of the additional fragments (rendered with fluidsynth and
# resampled to AUDIO_SAMPLE_RATE mono 16-bit FLAC, the challenge format).
MIDI_PPQ = 480
SYNTH_RENDER_RATE = 44100
DEFAULT_SOUNDFONT = Path("/usr/share/sounds/sf2/FluidR3_GM.sf2")
# fluidsynth gain chosen so synth levels match the quartets dataset audio
# (peak ~0.13); the fluidsynth default of 0.2 renders ~6 dB quieter.
DEFAULT_SYNTH_GAIN = 0.5

# General MIDI programs for kern instrument codes (*I signifiers).
INSTRUMENT_PROGRAMS = {
    "violn": 40,  # violin
    "viola": 41,
    "cello": 42,
    "flt": 73,    # flute
    "cont": 42,   # contrabass -> rendered as cello (quartets register)
    "bass": 42,
}
