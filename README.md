# MIREX 2026 Audio-to-Score Metrics and Quartets Extended

This repository contains the MIREX 2026 Audio-to-Score transcription metrics
and the preparation pipeline for Quartets Extended, a custom evaluation set
derived from public ``**kern`` scores.

> **Data availability:** The Quartets Extended source scores are hosted on
> `kern.ccarh.org`, which is currently unavailable. The preparation commands
> below will not complete until that host is back online. The listed scores
> were not found in the `humdrum-tools/humdrum-data` GitHub repository.

The official challenge call was announced [here](https://music-ir.org/mirex/wiki/2026:Audio-to-Score_Transcription),
and final results have been published [here](https://music-ir.org/mirex/wiki/2026:Audio-to-Score_Transcription_Results).

## Setup

Python 3.10 or newer is required. The Quartets Extended audio-preparation
pipeline additionally uses `wget`, `fluidsynth`, `ffmpeg`, and a General MIDI
SoundFont.

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

Dataset files are written below the repository's `data/` directory by default.
Set `A2S_DATA_ROOT` to use a different location:

```bash
export A2S_DATA_ROOT=/path/to/data
```

## Metrics

Evaluate predictions named `<track>.kern` against reference kern files:

```bash
.venv/bin/python scripts/run_metrics.py \
    --references /path/to/references \
    --predictions /path/to/predictions \
    --output results.json --csv results.csv
```

Prediction and reference files are paired by filename stem. Results include
per-track values and macro and micro aggregates. The `--references` argument
can point to any directory of reference `.kern` files, including the prepared
Quartets Extended test set. Omit `--references` to use that set from
`$A2S_DATA_ROOT` by default.

The reported metrics are:

- **WER**: raw whitespace-token word error rate.
- **CER**: character error rate on the raw kern text.
- **LER**: line error rate on raw kern records.
- **MV2H**: mean of multi-pitch detection, voice separation, metrical
  alignment, and note-value scores. Harmonic analysis is not included.

## Quartets Extended Preparation

The preparation script downloads the eight sources listed in
`additional_quartets.txt`, fragments and cleans the scores, renders MIDI, and
synthesizes mono 16-bit 22,050 Hz FLAC audio:

```bash
.venv/bin/python scripts/prepare_additional_quartets.py
```

By default, raw source files are stored in
`$A2S_DATA_ROOT/quartets_add_raw/` and prepared files in
`$A2S_DATA_ROOT/quartets_add_prepared/test/`. Each prepared track has matching
`.kern` and `.flac` files. Preparation follows the rules of Román et al.
(2019, section 2.3): fragments contain 3-6 non-overlapping measures, grace
notes and ornaments are removed, chords retain their lowest note, split
spines are flattened, and fragments with double dots or double accidentals
are discarded.

To download sources without preparing them, or to run a smaller preparation
for testing. `--limit` selects the first N source scores from
`additional_quartets.txt` before downloading (and prepares only those sources):

```bash
.venv/bin/python scripts/prepare_additional_quartets.py --download-only
.venv/bin/python scripts/prepare_additional_quartets.py --limit 2 --audio-format none
```

Use `--soundfont` to select a SoundFont. The default is
`/usr/share/sounds/sf2/FluidR3_GM.sf2`. Audio synthesis requires `fluidsynth`
and `ffmpeg`; kern-only preparation with `--audio-format none` does not.

## Repository Contents

- `a2s_metrics/`: kern parsing, text metrics, MV2H metrics, and batch
  evaluation.
- `data_prep/`: Quartets Extended score fragmentation, MIDI rendering, and
  audio synthesis.
- `scripts/run_metrics.py`: metrics command-line interface.
- `scripts/prepare_additional_quartets.py`: Quartets Extended preparation
  command-line interface.
- `additional_quartets.txt`: source score URLs used by the preparation
  pipeline.
