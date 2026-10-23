"""Text-level SER, WER, CER and Line Error Rate metrics.

SER is the cleaned-token ``sym-er`` metric used by the A2S Transformer. WER
is retained as the original raw-file metric for comparison. CER and LER use
the same cleaned kern rows as SER.
"""

import re
from dataclasses import dataclass

from rapidfuzz.distance import Levenshtein

VOICE_CHANGE_TOKEN = "<COC>"
STEP_CHANGE_TOKEN = "<COR>"


@dataclass(frozen=True)
class ErrorRate:
    """An error rate together with the counts it was computed from."""

    value: float
    errors: float
    reference_length: float


def _error_rate(reference_tokens: list, hypothesis_tokens: list) -> ErrorRate:
    """Unit-cost Levenshtein error rate; empty references degenerate to 0 or 1."""
    reference_length = len(reference_tokens)
    if reference_length == 0:
        errors = 0.0 if not hypothesis_tokens else 1.0
        return ErrorRate(value=errors, errors=errors, reference_length=1.0)
    errors = Levenshtein.distance(reference_tokens, hypothesis_tokens)
    return ErrorRate(
        value=errors / reference_length, errors=errors, reference_length=reference_length
    )


def _percentage_error_rate(reference_tokens: list, hypothesis_tokens: list) -> ErrorRate:
    """Compute an error rate in percentage units, like upstream ``sym-er``."""
    rate = _error_rate(reference_tokens, hypothesis_tokens)
    return ErrorRate(
        value=100.0 * rate.value,
        errors=rate.errors,
        reference_length=rate.reference_length,
    )


def _normalize(text: str) -> str:
    """Normalize line endings."""
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _clean_kern_token(token: str) -> str | None:
    """Match the token normalization used by the A2S Transformer parser."""
    if token and any(word in token for word in ("clef", "k[", "*M")):
        return token
    if token == ".":
        return "DOT"
    if token.strip() == "*":
        return token
    if not token or token.startswith(("*", "!")):
        return None
    if token.startswith("s"):
        return "s"
    if "=" in token:
        return "="
    if "q" in token:
        return None
    if "rr" in token:
        match = re.findall(r"rr[0-9]+", token)
        return match[0] if match else None
    if "r" in token:
        return token.split("r", 1)[0] + "r"
    match = re.findall(r"\[*\d+[.]*[a-gA-G]+[n#-]*\]*", token)
    return match[0] if match else None


def _clean_kern_rows(text: str) -> list[list[str]]:
    """Convert a kern document to normalized rows of ``**kern`` tokens.

    This mirrors the cleaning phase of ``krnParser.convert``: only ``**kern``
    columns are kept, comments and unsupported interpretations are removed,
    and tokens are cleaned independently per voice.
    """
    lines = _normalize(text).splitlines()
    header_index = next((index for index, line in enumerate(lines) if "**kern" in line), None)
    if header_index is None:
        return []

    header = lines[header_index].split("\t")
    kern_columns = [index for index, token in enumerate(header) if token == "**kern"]
    if not kern_columns:
        return []

    # The upstream parser locates the header to identify columns, then cleans
    # every non-comment row in the source file using those columns.
    source_rows = [line.split("\t") for line in lines if not line.strip().startswith("!")]
    voices: list[list[str]] = []
    for column in kern_columns:
        voice = []
        for row in source_rows:
            token = row[column] if column < len(row) else ""
            cleaned = _clean_kern_token(token)
            if cleaned is not None:
                voice.append(cleaned)
        voices.append(voice)

    if not voices or any(len(voice) != len(voices[0]) for voice in voices):
        # The upstream NumPy parser cannot transpose ragged voices.
        return []

    # The upstream parser substitutes every continuation '*' with the last
    # explicit clef in that voice.
    for voice in voices:
        clef_indices = [index for index, token in enumerate(voice) if token.startswith("*clef")]
        if not clef_indices:
            continue
        clef = voice[clef_indices[-1]]
        for index, token in enumerate(voice):
            if token == "*":
                voice[index] = clef

    return [list(row) for row in zip(*voices)]


def _clean_kern_tokens(text: str) -> list[str]:
    """Flatten cleaned rows with the upstream voice and row boundary tokens."""
    rows = _clean_kern_rows(text)
    sequence: list[str] = []
    for row in rows:
        for voice_index, token in enumerate(row):
            sequence.append(token)
            if voice_index < len(row) - 1:
                sequence.append(VOICE_CHANGE_TOKEN)
        sequence.append(STEP_CHANGE_TOKEN)
    if sequence:
        sequence.pop()
    return sequence


def _clean_kern_lines(text: str) -> list[str]:
    """Serialize cleaned rows for character- and line-level comparisons."""
    return ["\t".join(row) for row in _clean_kern_rows(text)]


def compute_text_metrics(reference_text: str, hypothesis_text: str) -> dict[str, ErrorRate]:
    """Compute SER, raw WER, CER and LER between two kern documents.

    ``SER`` is in percentage units, matching upstream ``sym-er``. The other
    metrics are fractions. CER and LER compare cleaned kern rows; WER compares
    raw-file whitespace tokens. Every result carries error and reference-length
    counts for batch pooling.
    """
    reference_text = _normalize(reference_text)
    hypothesis_text = _normalize(hypothesis_text)
    reference_clean_lines = _clean_kern_lines(reference_text)
    hypothesis_clean_lines = _clean_kern_lines(hypothesis_text)
    reference_clean_text = "\n".join(reference_clean_lines)
    hypothesis_clean_text = "\n".join(hypothesis_clean_lines)
    return {
        "SER": _percentage_error_rate(
            _clean_kern_tokens(reference_text), _clean_kern_tokens(hypothesis_text)
        ),
        "WER": _error_rate(reference_text.split(), hypothesis_text.split()),
        "CER": _error_rate(list(reference_clean_text), list(hypothesis_clean_text)),
        "LER": _error_rate(reference_clean_lines, hypothesis_clean_lines),
    }
