#!/usr/bin/env python
"""Entry-point script: generate fake predictions by perturbing reference kern
scores (the testing tool for the metric pipeline).

This alters reference kern files from a prepared dataset (quartets, or the
additional quartets via --dataset) in controlled ways -- note
substitutions/deletions/insertions, pitch errors, duration errors, voice
crossovers, meter/tempo errors, dropped data lines and character noise -- and
writes them as prediction files that can be scored with
scripts/run_metrics.py. With all probabilities at 0 (or --perfect), the
output files are exact copies and every metric must be at its optimum.

Usage:
    python scripts/make_fake_predictions.py [--dataset quartets|quartets_add]
                                            [--references <dir of .kern>]
                                            [--output-dir predictions_fake]
                                            [--seed 0] [--limit 20]
"""

import argparse
import random
import re
import sys
from itertools import pairwise
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from a2s_metrics.constants import DEFAULT_DATA_ROOT
from a2s_metrics.util import load_kern_references
from data_prep.constants import DATASETS, DEFAULT_DATASET, DEFAULT_SPLIT

DURATION_PREFIX = re.compile(r"^[\[\]_]*(\d+\.*q?)(?=[a-gA-Gr]|$)")
PITCH_LETTERS = re.compile(r"[a-gA-G]+")
NOTE_TOKEN = re.compile(r"^[\[\]_]*\d+\.*[a-gA-G]")
REST_TOKEN = re.compile(r"^[\[\]_]*\d+\.*r")
METER_TOKEN = re.compile(r"\*M(\d+)/(\d+)")
METERS = [(2, 4), (3, 4), (4, 4), (6, 8), (3, 8), (9, 8), (12, 8)]

LETTERS = "cdefgab"


def token_duration(token: str) -> str | None:
    """The leading duration of a kern token, or None if there is none."""
    match = DURATION_PREFIX.match(token)
    return match.group(1) if match else None


def is_note_token(token: str) -> bool:
    return bool(NOTE_TOKEN.match(token))


def is_rest_token(token: str) -> bool:
    return bool(REST_TOKEN.match(token))


def perturb_pitches(token: str, rng: random.Random) -> str:
    """Replace every pitch letter of a note token with a random one (same case)."""

    def replace(match: re.Match) -> str:
        return "".join(
            rng.choice(LETTERS).upper() if char.isupper() else rng.choice(LETTERS)
            for char in match.group(0)
        )

    return PITCH_LETTERS.sub(replace, token)


def perturb_duration(token: str, rng: random.Random) -> str:
    """Replace the duration of a note/rest token with a different one."""
    duration = token_duration(token)
    if duration is None:
        return token
    candidates = ["4", "8", "16", "2", "4.", "8.", "2.", "16."]
    candidates = [c for c in candidates if c != duration]
    return token.replace(duration, rng.choice(candidates), 1)


def perturb_char(token: str, rng: random.Random) -> str:
    """Substitute a random character inside a token (character-level noise)."""
    if len(token) < 2:
        return token
    index = rng.randrange(len(token))
    chars = list(token)
    chars[index] = rng.choice("0123456789.abcdefgABG#-\\/=qLJ")
    return "".join(chars)


def swap_voice_tokens(line: str, kern_columns: list[int], rng: random.Random) -> str:
    """Swap same-duration note tokens between two kern columns of a line."""
    tokens = line.split("\t")
    candidates = [
        (index, tokens[index]) for index in kern_columns if is_note_token(tokens[index])
    ]
    if len(candidates) < 2:
        return line
    rng.shuffle(candidates)
    for (index_a, token_a), (index_b, token_b) in pairwise(candidates):
        if token_duration(token_a) == token_duration(token_b):
            tokens[index_a], tokens[index_b] = token_b, token_a
            break
    return "\t".join(tokens)


def _perturbation_band(roll: float, args) -> str | None:
    """Which perturbation band a random roll falls into (disjoint bands)."""
    edge = 0.0
    for name, prob in (
        ("note", args.note_prob),
        ("pitch", args.pitch_prob),
        ("duration", args.duration_prob),
        ("char", args.char_prob),
    ):
        edge += prob
        if roll < edge:
            return name
    return None


def perturb_kern(text: str, args, rng: random.Random) -> str:
    """Apply the configured perturbations to one kern document."""
    lines = text.split("\n")
    kern_columns = [
        index
        for index, token in enumerate((lines[0] if lines else "").split("\t"))
        if token == "**kern"
    ]
    output: list[str] = []
    for line in lines:
        tokens = line.split("\t")
        is_data_line = bool(tokens) and bool(tokens[0]) and not tokens[0].startswith(("!", "*", "="))
        if is_data_line and rng.random() < args.drop_line_prob:
            continue  # drop the whole line (all spines lose the same slice)
        if is_data_line and args.voice_swap_prob and rng.random() < args.voice_swap_prob:
            line = swap_voice_tokens(line, kern_columns, rng)
            tokens = line.split("\t")
        for index in kern_columns if kern_columns else range(len(tokens)):
            if index >= len(tokens):
                continue
            token = tokens[index]
            roll = rng.random()
            band = _perturbation_band(roll, args)
            if band == "note" and is_note_token(token):
                # Substitute (pitch change) or "delete" (turn into a rest of
                # the same duration, keeping the spine timing valid).
                if rng.random() < 0.5:
                    tokens[index] = perturb_pitches(token, rng)
                else:
                    tokens[index] = re.sub(r"[a-gA-G]+[#\-n]*", "r", token, count=1)
            elif band == "pitch" and is_note_token(token):
                tokens[index] = perturb_pitches(token, rng)
            elif (
                band == "duration"
                and (is_note_token(token) or is_rest_token(token))
            ):
                tokens[index] = perturb_duration(token, rng)
            elif band == "char":
                tokens[index] = perturb_char(token, rng)
        output.append("\t".join(tokens))

    text = "\n".join(output)
    if args.meter_prob:
        text = perturb_meter(text, rng, args.meter_prob)
    if args.tempo_prob:
        text = perturb_tempo(text, rng, args.tempo_prob)
    return text


def perturb_meter(text: str, rng: random.Random, meter_prob: float) -> str:
    """Replace the first *M time signature of a document with another one."""
    match = METER_TOKEN.search(text)
    if not match or rng.random() >= meter_prob:
        return text
    candidates = [m for m in METERS if m != (int(match.group(1)), int(match.group(2)))]
    numerator, denominator = rng.choice(candidates)
    return METER_TOKEN.sub(f"*M{numerator}/{denominator}", text, count=1)


def perturb_tempo(text: str, rng: random.Random, tempo_prob: float) -> str:
    """Scale every *MM tempo marking by the same ratio, shifting every onset."""
    match = re.search(r"\*MM(\d+(?:\.\d+)?)", text)
    if not match or rng.random() >= tempo_prob:
        return text
    scaled = float(match.group(1)) * rng.uniform(0.8, 1.25)
    return re.sub(r"\*MM\d+(?:\.\d+)?", f"*MM{scaled:.2f}", text)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--dataset",
        choices=sorted(DATASETS),
        default=DEFAULT_DATASET,
        help="Dataset providing the reference scores (default: %(default)s)",
    )
    parser.add_argument(
        "--references",
        type=Path,
        default=None,
        help="Directory with the reference <track>.kern files "
        "(default: the prepared test split of --dataset)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("predictions_fake"),
        help="Where to write the fake predictions (default: %(default)s)",
    )
    parser.add_argument("--seed", type=int, default=0, help="Random seed")
    parser.add_argument(
        "--limit", type=int, default=None, help="Only perturb the first N reference tracks"
    )
    parser.add_argument("--perfect", action="store_true", help="Copy references unchanged")
    parser.add_argument(
        "--note-prob", type=float, default=0.05,
        help="Probability a note is substituted (pitch change) or replaced by a rest",
    )
    parser.add_argument(
        "--pitch-prob", type=float, default=0.05, help="Probability a note's pitch is altered"
    )
    parser.add_argument(
        "--duration-prob",
        type=float,
        default=0.0,
        help="Probability a note/rest duration changes (destructive: shifts all "
        "subsequent onsets of that voice)",
    )
    parser.add_argument(
        "--voice-swap-prob",
        type=float,
        default=0.05,
        help="Probability a line's notes are swapped between two voices",
    )
    parser.add_argument(
        "--drop-line-prob",
        type=float,
        default=0.0,
        help="Probability a data line is dropped (destructive: shifts all "
        "subsequent onsets of every voice)",
    )
    parser.add_argument(
        "--meter-prob", type=float, default=0.0, help="Probability the time signature is replaced"
    )
    parser.add_argument(
        "--tempo-prob",
        type=float,
        default=0.0,
        help="Probability the tempo marking is scaled (destructive: shifts every onset)",
    )
    parser.add_argument(
        "--char-prob", type=float, default=0.01, help="Probability a token gets character noise"
    )
    args = parser.parse_args()

    if args.perfect:
        for name in (
            "note_prob",
            "pitch_prob",
            "duration_prob",
            "voice_swap_prob",
            "drop_line_prob",
            "meter_prob",
            "tempo_prob",
            "char_prob",
        ):
            setattr(args, name, 0.0)

    references_dir = args.references or (
        DEFAULT_DATA_ROOT / DATASETS[args.dataset] / DEFAULT_SPLIT
    )
    references = load_kern_references(references_dir)
    if args.limit:
        references = dict(sorted(references.items())[: args.limit])
    print(f"Perturbing {len(references)} reference track(s) from {references_dir}")

    rng = random.Random(args.seed)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    for name, text in references.items():
        (args.output_dir / f"{name}.kern").write_text(perturb_kern(text, args, rng), encoding="utf-8")
    print(f"Fake predictions written to {args.output_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
