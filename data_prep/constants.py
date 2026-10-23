"""Constants for preparing the Quartets Extended dataset."""

import os
from pathlib import Path

DEFAULT_DATA_ROOT = Path(
    os.environ.get("A2S_DATA_ROOT", str(Path(__file__).resolve().parents[1] / "data"))
)

# --------------------------------------------------------------------------
# Quartets Extended dataset (kern.ccarh.org sources, URLs listed in
# additional_quartets.txt at the repository root). Prepared following the
# data preparation rules of Roman et al. (2019): 3-6 measure fragments,
# grace notes/ornaments removed, upper chord notes dropped, split spines
# flattened, fragments with double dots/double sharps/double flats discarded.
ADDITIONAL_URLS_FILE = Path(__file__).resolve().parents[1] / "additional_quartets.txt"
ADDITIONAL_RAW_SUBDIR = "quartets_add_raw"
ADDITIONAL_PREPARED_SUBDIR = "quartets_add_prepared"

# Dataset registry used by metrics CLI defaults: name -> prepared-data subdir.
DATASETS = {
    "quartets_extended": ADDITIONAL_PREPARED_SUBDIR,
}
DEFAULT_DATASET = "quartets_extended"

# Fragmentation of the additional sources (Roman et al., 2019, section 2.3).
FRAGMENT_MIN_MEASURES = 3
FRAGMENT_MAX_MEASURES = 6
FRAGMENT_SEED = 0

# MIDI synthesis settings for the custom dataset audio.
AUDIO_SAMPLE_RATE = 22050
MIDI_PPQ = 480
SYNTH_RENDER_RATE = 44100
DEFAULT_SOUNDFONT = Path("/usr/share/sounds/sf2/FluidR3_GM.sf2")
# fluidsynth gain chosen so synth levels match the reference dataset audio
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

DEFAULT_SPLIT = "test"
