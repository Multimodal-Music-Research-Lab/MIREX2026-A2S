"""Extraction of the staves metadata headers for the Staves-Informed A2S track.

For the Staves-Informed track, the challenge provides participants with the
``**kern`` header of each excerpt (its leading ``*`` lines: spine types,
instrument codes, clefs, key signatures, meter and tempo) as side information
(see the MIREX 2026 A2S wiki page). :func:`extract_header` isolates that
header block from a full kern score and :func:`extract_headers` writes one
``<track>.krn`` header file per prepared ``<track>.kern`` excerpt, mirroring
the input directory layout.
"""

from pathlib import Path

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


def extract_headers(input_dir: Path, output_dir: Path) -> dict[str, int]:
    """Extract the header of every ``*.kern`` file under ``input_dir``.

    Headers are written to ``<output_dir>/<relative path>.krn`` (same name as
    the source excerpt, ``.krn`` extension, split sub-directories mirrored).

    Returns:
        Mapping with the ``extracted`` and ``empty`` (headerless) file counts.
    """
    input_dir, output_dir = Path(input_dir), Path(output_dir)
    kern_files = sorted(input_dir.rglob("*.kern"))
    if not kern_files:
        raise FileNotFoundError(f"No *.kern files found under {input_dir}")
    empty = 0
    for index, path in enumerate(kern_files, start=1):
        header = extract_header(path.read_text(encoding="utf-8"))
        destination = (output_dir / path.relative_to(input_dir)).with_suffix(".krn")
        write_kern(f"{header}\n" if header else "", destination)
        if not header:
            empty += 1
            print(f"WARNING: no header lines in {path}")
        if index % 5000 == 0:
            print(f"  {index}/{len(kern_files)} headers extracted")
    print(f"{len(kern_files) - empty} header file(s) written under {output_dir}")
    if empty:
        print(f"WARNING: {empty} file(s) had no header lines")
    return {"extracted": len(kern_files), "empty": empty}
