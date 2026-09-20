"""Download and extraction logic for the quartets dataset.

The dataset (Roman et al., 2019; Alfaro-Contreras et al., 2024 splits) is
published on the Hugging Face Hub as ``PRAIG/quartets-quartets``: parquet
shards per split, each row holding one excerpt's audio (16-bit 22 050 Hz
mono FLAC) and its full ``**kern`` transcript. :func:`download_quartets`
fetches the raw shards; :func:`prepare_quartets` extracts one ``.kern`` and
one audio file per excerpt into a per-split layout directly usable by the
metrics pipeline.
"""

from pathlib import Path

from data_prep.constants import (
    HF_QUARTETS_REPO,
    SPLITS,
)
from data_prep.util import hf_snapshot_download, iter_split_records, write_audio, write_kern


def download_quartets(
    output_root: Path,
    splits: list[str] | None = None,
    endpoint: str | None = None,
) -> Path:
    """Download the raw quartets parquet shards of the given splits."""
    splits = splits or list(SPLITS)
    patterns = [f"data/{split}-*.parquet" for split in splits] + ["README.md"]
    hf_snapshot_download(
        repo_id=HF_QUARTETS_REPO,
        local_dir=Path(output_root),
        allow_patterns=patterns,
        endpoint=endpoint,
    )
    print(f"Quartets dataset downloaded to {output_root} (splits: {', '.join(splits)})")
    return Path(output_root)


def prepare_quartets(
    raw_dir: Path,
    output_root: Path,
    splits: list[str] | None = None,
    audio_format: str = "flac",
    limit: int | None = None,
) -> dict[str, int]:
    """Extract per-excerpt kern scores and audio from the raw parquet shards.

    Args:
        raw_dir: Raw snapshot directory (containing ``data/*.parquet``).
        output_root: Destination root; excerpts are written to
            ``<output_root>/<split>/<track_id>.kern`` (plus
            ``<track_id>.<audio_format>`` unless ``audio_format`` is ``none``).
        splits: Splits to prepare (default: all).
        audio_format: ``flac`` (as shipped), ``wav`` (16-bit PCM) or ``none``.
        limit: Optional maximum number of excerpts per split (for smoke runs).

    Returns:
        Mapping from split to the number of excerpts extracted.
    """
    splits = splits or list(SPLITS)
    raw_dir, output_root = Path(raw_dir), Path(output_root)
    counts: dict[str, int] = {}
    for split in splits:
        count = 0
        for track_id, audio_bytes, transcript in iter_split_records(raw_dir, split):
            if limit is not None and count >= limit:
                break
            write_kern(transcript, output_root / split / f"{track_id}.kern")
            if audio_format != "none":
                write_audio(
                    audio_bytes, output_root / split / f"{track_id}.{audio_format}", audio_format
                )
            count += 1
            if count % 500 == 0:
                print(f"  {split}: {count} excerpts extracted")
        counts[split] = count
        print(f"{split}: {count} excerpt(s) prepared under {output_root / split}")
    return counts
