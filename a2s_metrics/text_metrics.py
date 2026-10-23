"""Text-level kern metrics: Word, Character and Line Error Rate.

All three are Levenshtein-based error rates over different tokenizations of
the kern files:

- **CER**: Levenshtein distance over the file characters.
- **WER**: Levenshtein distance over whitespace-separated tokens (kern files
  separate spines with tabs and records with newlines, so this is the
  "tab- and newline-separated" tokenization).
- **LER**: Levenshtein distance over complete lines.

Each metric is reported together with its ``(errors, reference_length)``
counts so that micro aggregates can be pooled over a batch. The Levenshtein
distance itself is delegated to the C++ ``rapidfuzz`` implementation (unit
costs), which is required to process a whole split in reasonable time.
"""

from dataclasses import dataclass

from rapidfuzz.distance import Levenshtein


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
        # Degenerate case: an empty reference counts as perfect (both empty)
        # or as a single full error (anything predicted).
        errors = 0.0 if not hypothesis_tokens else 1.0
        return ErrorRate(value=errors, errors=errors, reference_length=1.0)
    errors = Levenshtein.distance(reference_tokens, hypothesis_tokens)
    return ErrorRate(
        value=errors / reference_length, errors=errors, reference_length=reference_length
    )


def _normalize(text: str) -> str:
    """Normalize line endings (the only normalization applied to kern text)."""
    return text.replace("\r\n", "\n").replace("\r", "\n")


def compute_text_metrics(reference_text: str, hypothesis_text: str) -> dict[str, ErrorRate]:
    """Compute WER, CER and LER between two kern documents.

    Returns:
        A dict mapping ``WER`` / ``CER`` / ``LER`` to :class:`ErrorRate`
        objects carrying the value and its ``(errors, reference_length)``
        counts for micro pooling.
    """
    reference_text = _normalize(reference_text)
    hypothesis_text = _normalize(hypothesis_text)
    return {
        "WER": _error_rate(reference_text.split(), hypothesis_text.split()),
        "CER": _error_rate(list(reference_text), list(hypothesis_text)),
        "LER": _error_rate(reference_text.split("\n"), hypothesis_text.split("\n")),
    }
