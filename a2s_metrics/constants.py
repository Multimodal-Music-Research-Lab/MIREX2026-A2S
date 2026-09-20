"""Constants shared by the A2S metrics package."""

import os
from pathlib import Path

# Base directory holding the downloaded/prepared quartets data. Override with
# the A2S_DATA_ROOT environment variable (see data_prep/constants.py).
DEFAULT_DATA_ROOT = Path(os.environ.get("A2S_DATA_ROOT", "/mnt/ssd/dhooge"))

# Matching thresholds (milliseconds), mirroring the MV2H reference
# implementations (apmcleod/MV2H, lucasmpaim/pyMV2H).
ONSET_DELTA_MS = 50.0
GROUPING_EPSILON_MS = 50.0
DURATION_DELTA_MS = 100.0

# Fallback tempo (QPM) and meter for kern files that omit *MM / *M markings.
DEFAULT_TEMPO_QPM = 120.0
DEFAULT_METER = (4, 4)

# Metric keys produced per piece. WER / CER / LER assess the kern text,
# the MV2H components assess the transcribed score (harmonic analysis is
# excluded for the initial edition, see the MIREX 2026 A2S wiki page).
TEXT_METRIC_KEYS = ("WER", "CER", "LER")
MV2H_COMPONENT_KEYS = ("MultiPitch", "Voice", "Meter", "NoteValue")
MV2H_KEY = "MV2H"
ALL_METRIC_KEYS = TEXT_METRIC_KEYS + MV2H_COMPONENT_KEYS + (MV2H_KEY,)
