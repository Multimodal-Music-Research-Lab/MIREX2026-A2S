"""Shared helpers for downloading and preparing the quartets dataset."""

import io
import os
from collections.abc import Iterator
from pathlib import Path

import pyarrow.parquet as pq
import soundfile as sf

from data_prep.constants import HF_ENDPOINT_DEFAULT


def hf_snapshot_download(
    repo_id: str,
    local_dir: Path,
    allow_patterns: list[str] | None = None,
    endpoint: str | None = None,
) -> Path:
    """Download a Hugging Face dataset repo snapshot into ``local_dir``.

    Args:
        repo_id: Repository id, e.g. ``PRAIG/quartets-quartets``.
        local_dir: Local destination directory.
        allow_patterns: Optional glob patterns restricting what is downloaded
            (None = everything).
        endpoint: Hub endpoint to use. Defaults to ``HF_ENDPOINT_DEFAULT``
            (hf-mirror.com) unless ``HF_ENDPOINT`` is already set in the
            environment. The variable must be set before ``huggingface_hub``
            is imported, hence the deferred import below.
    """
    os.environ.setdefault("HF_ENDPOINT", endpoint or HF_ENDPOINT_DEFAULT)
    from huggingface_hub import snapshot_download

    print(f"Downloading HF dataset {repo_id} (endpoint: {os.environ['HF_ENDPOINT']})")
    return Path(
        snapshot_download(
            repo_id=repo_id,
            repo_type="dataset",
            local_dir=str(local_dir),
            allow_patterns=allow_patterns,
        )
    )


def find_split_parquets(raw_dir: Path, split: str) -> list[Path]:
    """List the parquet shards of one split inside a downloaded snapshot."""
    data_dir = Path(raw_dir) / "data"
    shards = sorted(data_dir.glob(f"{split}-*.parquet"))
    if not shards:
        raise FileNotFoundError(
            f"No '{split}-*.parquet' shards under {data_dir}. "
            "Run scripts/download_quartets.py first."
        )
    return shards


def iter_split_records(raw_dir: Path, split: str) -> Iterator[tuple[str, bytes, str]]:
    """Iterate the records of one dataset split.

    Yields:
        ``(track_id, audio_flac_bytes, transcript)`` per example. The track id
        derives from the original audio file stem (e.g. ``k080-01.001``);
        examples with a missing or duplicated stem fall back to
        ``<split>-<row index>`` names.
    """
    seen: set[str] = set()
    row_index = 0
    for shard in find_split_parquets(raw_dir, split):
        parquet = pq.ParquetFile(shard)
        for batch in parquet.iter_batches(batch_size=64, columns=["audio", "transcript"]):
            for record in batch.to_pylist():
                stem = Path(record["audio"]["path"] or "").stem
                track_id = stem if stem and stem not in seen else f"{split}-{row_index:06d}"
                seen.add(track_id)
                row_index += 1
                yield track_id, record["audio"]["bytes"], record["transcript"]


def write_audio(audio_bytes: bytes, destination: Path, audio_format: str) -> None:
    """Write one audio excerpt in the requested format.

    ``flac`` writes the dataset bytes as-is (the dataset already ships 16-bit
    22 050 Hz mono FLAC, the challenge input format); ``wav`` decodes and
    re-encodes as 16-bit PCM WAV via soundfile.
    """
    destination.parent.mkdir(parents=True, exist_ok=True)
    if audio_format == "flac":
        destination.write_bytes(audio_bytes)
        return
    data, sample_rate = sf.read(io.BytesIO(audio_bytes), dtype="int16")
    sf.write(destination, data, sample_rate, subtype="PCM_16")


def write_kern(transcript: str, destination: Path) -> None:
    """Write one kern transcript, ensuring POSIX line endings."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(transcript.replace("\r\n", "\n").replace("\r", "\n"), encoding="utf-8")
