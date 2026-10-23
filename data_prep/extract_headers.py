"""Extraction of the staves metadata headers for the Staves-Informed A2S track.

For the Staves-Informed track, the challenge provides participants with the
``**kern`` header of each excerpt (its leading ``*`` lines: spine types,
instrument codes, clefs, key signatures, meter and tempo) as side information
(see the MIREX 2026 A2S wiki page). :func:`extract_header` isolates that
header block from a full kern score and :func:`extract_headers` writes one
``<track>.krn`` header file per prepared ``<track>.kern`` excerpt, mirroring
the input directory layout, plus a variant keeping only the ``**kern`` spines.
"""

from pathlib import Path

from a2s_metrics.constants import KERN_SPINE
from a2s_metrics.util import keep_kern_spines
from data_prep.constants import KERN_SPINES_PER_EXCERPT
from data_prep.util import write_kern


def extract_header(text: str) -> str:
    """Return the header block of a kern document.

    The header is the leading block of lines starting with ``*`` (the
    exclusive/tandem interpretations, e.g. ``**kern``, ``*Icello``,
    ``*clefF4``, ``*M3/4``, ``*MM71``); it ends at the first line starting
    with another character (comments, data or the ``*-`` terminators).
    """
    header: list[str] = []
    for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        if not header and not line.strip():
            continue  # tolerate blank lines before the header
        if not line.startswith("*"):
            break
        header.append(line.rstrip())
    return "\n".join(header)


def _kern_spine_count(header: str) -> int:
    """Number of ``**kern`` spine columns in a header (0 if empty)."""
    if not header:
        return 0
    return sum(1 for token in header.splitlines()[0].split("\t") if token == KERN_SPINE)


def extract_headers(
    input_dir: Path, output_dir: Path, kern_only_dir: Path | None = None
) -> dict[str, int]:
    """Extract the header of every ``*.kern`` file under ``input_dir``.

    Headers are written to ``<output_dir>/<relative path>.krn`` (same name as
    the source excerpt, ``.krn`` extension, split sub-directories mirrored).
    With ``kern_only_dir``, a second copy keeping only the ``**kern`` spine
    columns (see :func:`a2s_metrics.util.keep_kern_spines`) is written there;
    headers deviating from ``KERN_SPINES_PER_EXCERPT`` kern spines are warned
    about.

    Returns:
        Mapping with the ``extracted`` and ``empty`` (headerless) file counts
        and, if ``kern_only_dir`` is set, the ``kern_spine_mismatch`` count.
    """
    input_dir, output_dir = Path(input_dir), Path(output_dir)
    kern_files = sorted(input_dir.rglob("*.kern"))
    if not kern_files:
        raise FileNotFoundError(f"No *.kern files found under {input_dir}")
    empty = 0
    mismatched = 0
    for index, path in enumerate(kern_files, start=1):
        header = extract_header(path.read_text(encoding="utf-8"))
        destination = (output_dir / path.relative_to(input_dir)).with_suffix(".krn")
        write_kern(f"{header}\n" if header else "", destination)
        if not header:
            empty += 1
            print(f"WARNING: no header lines in {path}")
        if kern_only_dir is not None:
            kern_only_header = keep_kern_spines(header)
            kern_only_destination = (kern_only_dir / path.relative_to(input_dir)).with_suffix(
                ".krn"
            )
            write_kern(f"{kern_only_header}\n" if kern_only_header else "", kern_only_destination)
            spine_count = _kern_spine_count(kern_only_header)
            if spine_count != KERN_SPINES_PER_EXCERPT:
                mismatched += 1
                print(
                    f"WARNING: {path} has {spine_count} **kern spine(s) "
                    f"(expected {KERN_SPINES_PER_EXCERPT})"
                )
        if index % 5000 == 0:
            print(f"  {index}/{len(kern_files)} headers extracted")
    print(f"{len(kern_files) - empty} header file(s) written under {output_dir}")
    if kern_only_dir is not None:
        print(
            f"{len(kern_files) - empty} **kern-only header file(s) written under {kern_only_dir}"
        )
    if empty:
        print(f"WARNING: {empty} file(s) had no header lines")
    if kern_only_dir is not None and mismatched:
        print(
            f"WARNING: {mismatched} file(s) deviate from "
            f"{KERN_SPINES_PER_EXCERPT} **kern spines"
        )
    counts = {"extracted": len(kern_files), "empty": empty}
    if kern_only_dir is not None:
        counts["kern_spine_mismatch"] = mismatched
    return counts
