# MIREX 2026 — Audio-to-Score Transcription (A2S) 🎼

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/downloads/release/python-3120/)

Code for the MIREX 2026 Audio-to-Score Transcription (A2S) challenge.

This repository provides evaluation metrics and dataset preparation tools for
the [Quartets dataset](https://huggingface.co/datasets/PRAIG/quartets-quartets).

 - [Challenge description](https://music-ir.org/mirex/wiki/2026:Audio-to-Score_Transcription)
 - [Official challenge call](https://music-ir.org/mirex/wiki/2026:Audio-to-Score_Transcription)
 - [Published results](https://music-ir.org/mirex/wiki/2026:Audio-to-Score_Transcription_Results)

## Setup ⚙️

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

Datasets are stored under one data root, configured with `A2S_DATA_ROOT`.
The default is `/mnt/ssd/dhooge`.

Set it before running scripts, or pass explicit paths using `--output`,
`--raw-dir`, or `--references`:

```bash
export A2S_DATA_ROOT=/mnt/ssd/dhooge
```

## Metrics 📊

The metrics assess both the textual quality and the musical transcription
quality of predicted `**kern` files:

- **SER**: the A2S Transformer `sym-er` metric, using cleaned `**kern` tokens,
  explicit voice/row boundary tokens, and pooled Levenshtein distance. It is
  reported as a percentage, matching the upstream implementation.
- **WER**: the original raw-file metric, using whitespace-separated
  (tab/newline) tokens of the kern files. It is retained for comparison and is
  reported as a fraction.
- **CER**: Levenshtein distance over the characters of the cleaned `**kern`
  representation.
- **LER**: Levenshtein distance over complete lines of the cleaned `**kern`
  representation.
- **MV2H**: mean of four sub-metrics computed on parsed scores:
  - Multi-pitch detection
  - Voice separation
  - Metrical alignment
  - Note value detection

  Harmonic analysis is excluded in this initial edition because the datasets
  contain no chord information, as announced on the challenge wiki page.

MV2H adapts the official code (McLeod, 2018) and its Python port,
[pyMV2H](https://github.com/lucasmpaim/pyMV2H), to kern scores. It mirrors the
A2S Transformer reference pipeline:

1. Convert kern to a score-time note list.
2. Evaluate with MV2H using 50 ms onset/grouping tolerances and a 100 ms
   duration tolerance.

Voices are kern spine columns. Onsets are computed from note durations and the
`*MM` tempo.

### Batch evaluation

```bash
# References: prepared quartets test split (see below).
.venv/bin/python scripts/run_metrics.py \
    --predictions <dir with <track>.kern files> \
    --output results.json --csv results.csv

# References from the additional quartets dataset instead:
.venv/bin/python scripts/run_metrics.py --dataset quartets_add \
    --predictions <dir with <track>.kern files>
```

Predictions are paired with references by track name (file stem). Select
references with `--dataset` (`quartets` by default, or `quartets_add`) or pass
an explicit `--references` directory.

- Missing and extra prediction files are reported as warnings.
- Results include per-track metrics and two aggregates:
  - `macro`: mean of per-track values
  - `micro`: pooled errors divided by pooled counts

Use `--kern-only` to evaluate only `**kern` spines. Other spines (such as
`**dynam`) are removed from both references and predictions before evaluation:

```bash
.venv/bin/python scripts/run_metrics.py \
    --predictions <dir with <track>.kern files> --kern-only
```

## Dataset Preparation 💾

The Quartets dataset can be downloaded from the [PRAIG Quartets dataset on Hugging Face](https://huggingface.co/datasets/PRAIG/quartets-quartets).

### Staves Metadata (Staves-Informed A2S Track)

For the Staves-Informed track, participants receive each excerpt's `**kern`
header as side information. The header contains its leading `*` lines:

- Spine types and instrument codes
- Clefs and key signature
- Meter and tempo

Each prepared excerpt's header is extracted to a per-split `<track>.krn` file:

```bash
# -> $A2S_DATA_ROOT/quartets_headers/<split>/<track>.krn
#    $A2S_DATA_ROOT/quartets_headers_kern_only/<split>/<track>.krn (**kern spines only)
.venv/bin/python scripts/extract_headers.py
.venv/bin/python scripts/extract_headers.py --input <dir with *.kern> --output <dir>
```

The first command is the standard Staves-Informed export. It reads prepared
quartet excerpts from `$A2S_DATA_ROOT/quartets_prepared` and writes header files
plus `**kern`-only counterparts to the output directories shown above.

For a custom prepared directory, use the second command. Add `--flute` to also
export headers for the flute-compatible additional-quartets variant.

Input files are searched recursively under `--input` (default:
`$A2S_DATA_ROOT/quartets_prepared`), and their directory layout is mirrored
under `--output` (default: `$A2S_DATA_ROOT/quartets_headers`).

- The `**kern`-only export goes to `--kern-only-output` (default:
  `$A2S_DATA_ROOT/quartets_headers_kern_only`).
- Quartets excerpts should have exactly four `**kern` spines; deviations are
  reported as warnings.

## Additional Quartets Dataset 🎻

A second, smaller evaluation set is built from eight string quartet scores on
[kern.ccarh.org](https://kern.ccarh.org), listed in `additional_quartets.txt`:

- Schubert D 87 and D 804/ii
- Brahms Op. 51/1, movements 2-3
- A Mendelssohn Op. 12 excerpt from Piston's *Harmony*
- Three Schubert D 87 movements

Preparation follows Román et al. (2019, section 2.3):

- Use non-overlapping fragments of 3-6 measures.
- Remove grace notes and ornaments; drop upper chord notes.
- Flatten split spines to no more than four simultaneous voices.
- Discard fragments with double dots, double sharps, or double flats.
- Expand section labels along the `*>[...]` thru path to match the source site's
  MIDI rendering.

The source MIDI is also used to cross-check kern parsing, including the tempo
map and total length.

Each fragment is rendered to MIDI from its cleaned reference score and
synthesized with fluidsynth into the challenge input format (16-bit
22 050 Hz mono FLAC):

```bash
# Download <source>.kern + <source>.midi per URL, then fragment + synthesize.
.venv/bin/python scripts/prepare_additional_quartets.py   # -> $A2S_DATA_ROOT/quartets_add_raw
                                                          # -> $A2S_DATA_ROOT/quartets_add_prepared/test
.venv/bin/python scripts/prepare_additional_quartets.py \
    --output $A2S_DATA_ROOT/quartets_add_flute_prepared \
    --fourth-instrument flt                          # flute-compatible variant
.venv/bin/python scripts/prepare_additional_quartets.py --download-only
.venv/bin/python scripts/prepare_additional_quartets.py --audio-format none  # kern only
```

The result is 372 `<track>.kern` and `<track>.flac` pairs named
`<source>.<NNN>` (for example, `quartet10-1.001`). Evaluate the standard set
with `scripts/run_metrics.py --dataset quartets_add`.

Select the flute-compatible variant with
`scripts/run_metrics.py --dataset quartets_add_flute`. Generate its headers
under `$A2S_DATA_ROOT/quartets_add_flute_headers` and
`$A2S_DATA_ROOT/quartets_add_flute_headers_kern_only`:

```bash
.venv/bin/python scripts/extract_headers.py --flute
```


## Repository Layout 📁

```
a2s_metrics/       metric implementation (kern parser, WER/CER/LER, MV2H, batch evaluation)
data_prep/         dataset download and extraction (quartets, additional quartets)
scripts/           minimal command-line entry points
```
