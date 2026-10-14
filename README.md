# MIREX 2026 — Audio-to-Score Transcription (A2S)

Code for the MIREX 2026 A2S challenge: evaluation metrics and dataset
preparation for the [Quartets dataset](https://huggingface.co/datasets/PRAIG/quartets-quartets).

Challenge description: https://music-ir.org/mirex/wiki/2026:Audio-to-Score_Transcription

## Setup

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

All datasets are stored under a single data root, set via the `A2S_DATA_ROOT`
environment variable (default: `/mnt/ssd/dhooge`). Export it before running the
scripts, e.g. `export A2S_DATA_ROOT=/mnt/ssd/dhooge`, or pass explicit paths
with `--output` / `--raw-dir` / `--references`.

## Metrics

The metrics assess both the textual quality and the musical transcription
quality of predicted `**kern` files:

- **WER**: Levenshtein distance over whitespace-separated (tab/newline) tokens
  of the kern files.
- **CER**: Levenshtein distance over the characters of the kern files.
- **LER**: Levenshtein distance over complete lines of the kern files.
- **MV2H**: mean of four sub-metrics computed on the parsed scores
  (multi-pitch detection, voice separation, metrical alignment, note value
  detection). The harmonic analysis component is excluded for the initial
  edition (no chord information in the datasets), as announced on the wiki
  page.

The MV2H implementation adapts the official MV2H code (McLeod, 2018) and its
Python port [pyMV2H](https://github.com/lucasmpaim/pyMV2H) to kern scores,
mirroring the evaluation pipeline of the A2S Transformer reference
implementation (kern -> score-time note list -> MV2H, with the same 50 ms
onset/grouping tolerances and 100 ms duration tolerance; voices are kern
spine columns, onsets are computed from note durations and the `*MM` tempo).

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

Predictions are paired with references by track name (file stem); the
reference set is selected with `--dataset` (`quartets`, default, or
`quartets_add`) or by passing an explicit `--references` directory. Missing
and extra prediction files are reported as warnings. Results contain
per-track metrics and two aggregates: `macro` (mean of per-track values) and
`micro` (pooled errors / pooled counts).

Passing `--kern-only` evaluates only the `**kern` spines: every other spine
(e.g. `**dynam`) is removed from the references and the predictions before
the metrics are computed:

```bash
.venv/bin/python scripts/run_metrics.py \
    --predictions <dir with <track>.kern files> --kern-only
```

## Dataset preparation

```bash
# Raw parquet shards from the Hugging Face Hub (via hf-mirror.com)
.venv/bin/python scripts/download_quartets.py                 # -> $A2S_DATA_ROOT/quartets

# Per-excerpt extraction: <track>.kern + <track>.flac (16-bit 22 050 Hz mono,
# the challenge input format) under $A2S_DATA_ROOT/quartets_prepared/<split>/
.venv/bin/python scripts/prepare_quartets.py                  # all splits
.venv/bin/python scripts/prepare_quartets.py --splits test    # test split only
.venv/bin/python scripts/prepare_quartets.py --limit 50       # smoke run
.venv/bin/python scripts/prepare_quartets.py --audio-format none   # kern only
```

Notes:
- `huggingface.co` may be unreachable on some networks; the download script
  uses the `https://hf-mirror.com` mirror by default (override with
  `--endpoint` or the `HF_ENDPOINT` environment variable).
- The dataset ships the audio as 16-bit 22 050 Hz mono FLAC, so the default
  `flac` extraction is a byte-for-byte copy; `--audio-format wav` re-encodes
  16-bit PCM WAV via soundfile.

### Staves metadata (Staves-Informed A2S track)

For the Staves-Informed track, participants receive the `**kern` header of
each excerpt (its leading `*` lines: spine types, instrument codes, clefs,
key signature, meter and tempo) as side information. The header of every
prepared excerpt is extracted into a per-split `<track>.krn` file:

```bash
# -> $A2S_DATA_ROOT/quartets_headers/<split>/<track>.krn
#    $A2S_DATA_ROOT/quartets_headers_kern_only/<split>/<track>.krn (**kern spines only)
.venv/bin/python scripts/extract_headers.py
.venv/bin/python scripts/extract_headers.py --input <dir with *.kern> --output <dir>
```

Input files are searched recursively under `--input` (default:
`$A2S_DATA_ROOT/quartets_prepared`) and the directory layout is mirrored
under `--output` (default: `$A2S_DATA_ROOT/quartets_headers`). A second
export keeping only the `**kern` spine columns is written to
`--kern-only-output` (default: `$A2S_DATA_ROOT/quartets_headers_kern_only`);
quartets excerpts always have exactly 4 `**kern` spines, and files deviating
from this are reported as warnings.

## Additional quartets dataset

A second, smaller evaluation set is built from eight string quartet scores
hosted on [kern.ccarh.org](https://kern.ccarh.org) (URLs in
`additional_quartets.txt`: Schubert D 87 and D 804/ii, Brahms Op. 51/1
movements 2-3, a Mendelssohn Op. 12 excerpt from Piston's *Harmony*, and
three Schubert D 87 movements). It is prepared following the data rules of
Román et al. (2019, section 2.3): non-overlapping fragments of 3-6 measures,
grace notes and ornaments removed, upper chord notes dropped, split spines
flattened (no more than four simultaneous voices), and fragments with double
dots, double sharps or double flats discarded. Section labels are expanded
along their `*>[...]` thru path, matching the MIDI rendering of the source
site; the MIDI conversion shared by both is used to cross-check the kern
parsing (tempo map and total length).

Each fragment is rendered to MIDI from its cleaned reference score and
synthesized with fluidsynth into the challenge input format (16-bit
22 050 Hz mono FLAC):

```bash
# Download <source>.kern + <source>.midi per URL, then fragment + synthesize.
.venv/bin/python scripts/prepare_additional_quartets.py   # -> $A2S_DATA_ROOT/quartets_add_raw
                                                          # -> $A2S_DATA_ROOT/quartets_add_prepared/test
.venv/bin/python scripts/prepare_additional_quartets.py --download-only
.venv/bin/python scripts/prepare_additional_quartets.py --audio-format none  # kern only
```

The result is 373 `<track>.kern` + `<track>.flac` pairs named
`<source>.<NNN>` (e.g. `quartet10-1.001`), evaluated with
`scripts/run_metrics.py --dataset quartets_add`.

## Testing with fake predictions

`scripts/make_fake_predictions.py` perturbs reference kern scores (note
substitutions/deletions, pitch errors, voice crossovers, meter/tempo errors,
dropped lines, character noise) with a fixed seed, so the metric pipeline can
be sanity checked without real model output:

```bash
# exact copies (sanity: WER/CER/LER = 0, MV2H components = 1)
.venv/bin/python scripts/make_fake_predictions.py --perfect --output-dir predictions_perfect
.venv/bin/python scripts/run_metrics.py --predictions predictions_perfect

# against the additional quartets dataset
.venv/bin/python scripts/make_fake_predictions.py --dataset quartets_add --perfect \
    --output-dir predictions_perfect_add
.venv/bin/python scripts/run_metrics.py --dataset quartets_add --predictions predictions_perfect_add

# default perturbations (graded degradation of all metrics)
.venv/bin/python scripts/make_fake_predictions.py --output-dir predictions_fake
.venv/bin/python scripts/run_metrics.py --predictions predictions_fake

# targeted perturbations, e.g. meter errors only
.venv/bin/python scripts/make_fake_predictions.py --output-dir predictions_meter \
    --note-prob 0 --pitch-prob 0 --voice-swap-prob 0 --char-prob 0 --meter-prob 1.0
```

`--dataset` selects the reference set for both scripts (default `quartets`).

Perturbation probabilities: `--note-prob` (note substituted or turned into a
rest of the same duration), `--pitch-prob`, `--duration-prob`,
`--voice-swap-prob` (same-duration notes swapped between two voices),
`--drop-line-prob`, `--meter-prob`, `--tempo-prob`, `--char-prob`.
Note that `--duration-prob`, `--drop-line-prob` and `--tempo-prob` are
destructive: they shift subsequent note onsets past the 50 ms MV2H tolerance,
so they default to 0.

## Repository layout

```
a2s_metrics/       metric implementation (kern parser, WER/CER/LER, MV2H, batch evaluation)
data_prep/         dataset download and extraction (quartets, additional quartets)
scripts/           minimal command-line entry points
```
