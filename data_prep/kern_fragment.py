"""Parsing and fragmentation of **kern sources for Quartets Extended.

Implements the data preparation rules of Roman et al. (2019, section 2.3) on
raw ``**kern`` files downloaded from kern.ccarh.org:

- the score is split into non-overlapping fragments of 3-6 measures each,
- grace notes and ornaments are removed (fermatas, ties, staccatos and beams
  are kept, as in the published quartets dataset),
- upper notes of chords are dropped (lowest note kept) and split spines
  (``*^`` / ``*v``) are flattened to their first branch, so that no more than
  four simultaneous voices are present,
- fragments containing double dots, double sharps or double flats are
  discarded.

The walker keeps the original column layout of the file (``**kern`` plus
auxiliary spines such as ``**dynam``), so the prepared reference scores keep
the same spine structure as the quartets dataset references. Timing is
tracked per kern column, mirroring :mod:`a2s_metrics.kern`, which keeps
fragment positions consistent with the metric computation.
"""

import random
import re
from dataclasses import dataclass, field

from a2s_metrics.kern import _parse_duration

KERN_SPINE = "**kern"
PITCH_GROUP = re.compile(r"([a-gA-G]+)([#\-n]*)")
DOUBLE_DOT = re.compile(r"\d\.{2}")
KEY_LABEL = re.compile(r"^\*[A-Ga-g]:$")

# Ornament signifiers stripped from note tokens (trills, mordents, turns).
ORNAMENT_CHARS = "TtMmWwSs$"

# Interpretation line categories kept in fragment headers, in output order.
HEADER_CATEGORIES = ("instrument", "clef", "keysig", "keylabel", "meter", "tempo")


def _classify(tokens: list[str]) -> str:
    """Classify one humdrum record from its tokens."""
    if all(token.startswith("*") for token in tokens):
        return "terminator" if all(token == "*-" for token in tokens) else "interp"
    if all(token.startswith("=") for token in tokens):
        return "barline"
    return "local" if tokens[0].startswith("!") else "data"


def _cell_advance(cell: str) -> float:
    """Quarter-note advance encoded by one kern cell (0 for nulls/graces)."""
    advance = 0.0
    for sub_token in cell.split():
        quarter_length, _, is_grace = _parse_duration(sub_token)
        if not is_grace and quarter_length > 0.0:
            advance = max(advance, quarter_length)
    return advance


def clean_sub_token(sub_token: str) -> str | None:
    """Clean one kern note/rest sub-token.

    Returns ``None`` for grace notes (dropped from the score); otherwise
    returns the sub-token with ornament signifiers stripped from the tail
    (after pitch and accidentals). Ties, fermatas, stems and beams are
    preserved.
    """
    quarter_length, remainder, is_grace = _parse_duration(sub_token)
    if is_grace:
        return None
    del quarter_length
    if pitch := PITCH_GROUP.search(remainder):
        tail = remainder[pitch.end() :]
        stripped = tail.translate({ord(c): None for c in ORNAMENT_CHARS})
        if tail and stripped != tail:
            return sub_token[: -len(tail)] + stripped
    return sub_token


def clean_cell(cell: str) -> str:
    """Clean one kern data cell: drop graces, keep the lowest chord note."""
    cleaned = []
    for sub_token in cell.split():
        result = clean_sub_token(sub_token)
        if result is not None:
            cleaned.append(result)
    if not cleaned:
        return "."
    return cleaned[0]  # chords are written bottom-up: keep the lowest note


def cell_is_disallowed(cell: str) -> str | None:
    """Return the offending feature of a kern cell, if any."""
    for sub_token in cell.split():
        if DOUBLE_DOT.search(sub_token):
            return "double dot"
        _, remainder, _ = _parse_duration(sub_token)
        for match in PITCH_GROUP.finditer(remainder):
            if "##" in match.group(2):
                return "double sharp"
            if "--" in match.group(2):
                return "double flat"
    return None


@dataclass
class _Structure:
    """Live spine structure of a source while walking it.

    Split spines are flattened: on ``*^`` the extra branch is marked dropped
    (its content is removed from the output, the first branch is kept); on
    ``*v`` the branches collapse back into the first one. ``owner`` maps
    every live column to its base column index.
    """

    types: list[str]
    owner: list[int]
    dropped: list[bool]
    base_count: int

    @classmethod
    def from_spine_line(cls, tokens: list[str]) -> "_Structure":
        """Create the initial spine map from an exclusive-interpretation row."""
        count = len(tokens)
        return cls(
            types=list(tokens),
            owner=list(range(count)),
            dropped=[False] * count,
            base_count=count,
        )

    def output_columns(self) -> list[int | None]:
        """Live column feeding each base column (first branch wins)."""
        columns: list[int | None] = [None] * self.base_count
        for live, base in enumerate(self.owner):
            if not self.dropped[live] and columns[base] is None:
                columns[base] = live
        return columns

    def apply(self, tokens: list[str]) -> None:
        """Update the structure on a tandem interpretation record."""
        types: list[str] = []
        owner: list[int] = []
        dropped: list[bool] = []
        token_index = column_index = 0
        while token_index < len(tokens) and column_index < len(self.types):
            token = tokens[token_index]
            if token == "*^":
                types.append(self.types[column_index])
                owner.append(self.owner[column_index])
                dropped.append(False)
                types.append(self.types[column_index])
                owner.append(self.owner[column_index])
                dropped.append(True)
                token_index += 1
                column_index += 1
            elif token == "*v":
                run = 0
                while token_index < len(tokens) and tokens[token_index] == "*v":
                    run += 1
                    token_index += 1
                types.append(self.types[column_index])
                owner.append(self.owner[column_index])
                dropped.append(False)
                column_index += run
            else:
                types.append(self.types[column_index])
                owner.append(self.owner[column_index])
                dropped.append(self.dropped[column_index])
                token_index += 1
                column_index += 1
        while column_index < len(self.types):  # columns without a token: keep
            types.append(self.types[column_index])
            owner.append(self.owner[column_index])
            dropped.append(self.dropped[column_index])
            column_index += 1
        self.types, self.owner, self.dropped = types, owner, dropped


@dataclass
class Record:
    """One output record of a source: kind plus the cleaned output line."""

    kind: str  # "interp" | "local" | "barline" | "data"
    line: str


@dataclass
class Region:
    """One measure of the source: the records between two barlines."""

    records: list[Record] = field(default_factory=list)
    closing_barline: str | None = None
    start_q: float = 0.0
    length_q: float = 0.0
    state: dict[str, str] = field(default_factory=dict)
    disallowed: str | None = None


@dataclass
class KernSource:
    """Parsed **kern source: header context plus its list of measures."""

    stem: str
    spine_line: str
    base_count: int
    terminator: str
    regions: list[Region]
    total_q: float
    tempo_changes: list[tuple[float, float]]
    warnings: list[str] = field(default_factory=list)


def _header_category(tokens: list[str]) -> str | None:
    """Category of an interpretation record for the fragment header state."""
    if any(token.startswith("*I") for token in tokens):
        return "instrument"
    if any(token.startswith("*clef") for token in tokens):
        return "clef"
    if any(token.startswith("*k[") for token in tokens):
        return "keysig"
    if any(KEY_LABEL.match(token) for token in tokens):
        return "keylabel"
    if any(token.startswith("*MM") for token in tokens):
        return "tempo"
    if any(token.startswith("*M") and "/" in token for token in tokens):
        return "meter"
    return None


def _first_tempo(tokens: list[str]) -> float | None:
    """Return the first parseable *MM tempo marking in an interpretation row."""
    for token in tokens:
        if token.startswith("*MM"):
            try:
                return float(token[3:])
            except ValueError:
                return None
    return None


_THRU_LABEL = re.compile(r"^\*>\[([^]]*)\]$")
_SECTION_BOUNDARY = re.compile(r"^\*>(\w+)$")


def expand_thru(lines: list[str]) -> tuple[list[str], list[str]]:
    """Expand Humdrum section labels following the ``*>[...]`` thru path.

    The scores encode their performance order (with repeats) in a
    ``*>[A,A,B]`` label record; each ``*>NAME`` record starts a section that
    appears once in the file. The expanded line list plays the sections in
    label order, matching the MIDI rendering of the sources. Returns the
    expanded lines plus warnings for undefined sections.
    """
    thru: list[str] | None = None
    for line in lines:
        if match := _THRU_LABEL.match(line.split("\t")[0]):
            thru = match.group(1).split(",")
            break
    if not thru:
        return lines, []
    warnings: list[str] = []
    preamble: list[str] = []
    sections: dict[str, list[str]] = {}
    current: list[str] | None = None
    for line in lines:
        token = line.split("\t")[0]
        if match := _SECTION_BOUNDARY.match(token):
            name = match.group(1)
            if name in sections:
                warnings.append(f"duplicate section *>{name}: keeping the first occurrence")
                current = None
            else:
                current = sections[name] = []
        elif current is None:
            preamble.append(line)
        else:
            current.append(line)
    expanded = list(preamble)
    for name in thru:
        if section := sections.get(name):
            expanded.extend(section)
        else:
            warnings.append(f"thru section *>{name} not found in the score")
    return expanded, warnings


def parse_source(text: str, stem: str) -> KernSource:
    """Parse a raw **kern source into cleaned measures (regions)."""
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    lines, thru_warnings = expand_thru(lines)
    structure: _Structure | None = None
    spine_line = ""
    state: dict[str, str] = {}
    tempo_changes: list[tuple[float, float]] = []
    regions: list[Region] = []
    current = Region()
    warnings: list[str] = list(thru_warnings)
    terminator = ""
    positions: list[float] = []

    def position() -> float:
        """Return the furthest quarter-note position reached by any spine."""
        return max(positions, default=0.0)

    for raw_line in lines:
        if not raw_line.strip():
            continue
        tokens = raw_line.split("\t")
        if structure is None:
            if all(token.startswith("**") for token in tokens):
                structure = _Structure.from_spine_line(tokens)
                spine_line = raw_line
                positions = [0.0] * structure.base_count
            continue  # global comments (!!!...) and everything before spines
        kind = _classify(tokens)
        if kind == "terminator":
            terminator = raw_line
            break
        if kind == "interp":
            if tokens[0].startswith("*>"):
                continue  # section metadata: expanded away, not score content
            if any(token in ("*^", "*v") for token in tokens):
                structure.apply(tokens)  # flattened away: never emitted
                continue
            columns = structure.output_columns()
            if len(tokens) == structure.base_count and not any(structure.dropped):
                line = raw_line  # base layout: keep the original line
            else:
                out = [
                    tokens[live] if live is not None and live < len(tokens) else "*"
                    for live in columns
                ]
                line = "\t".join(out)
            if category := _header_category(tokens):
                state[category] = line
            if (qpm := _first_tempo(tokens)) and qpm > 0.0:
                tempo_changes.append((position(), qpm))
            current.records.append(Record("interp", line))
            continue
        if kind == "local":
            current.records.append(Record("local", raw_line))
            continue
        if kind == "barline":
            columns = structure.output_columns()
            if len(tokens) != structure.base_count or any(structure.dropped):
                tokens = [
                    tokens[live] if live is not None and live < len(tokens) else "="
                    for live in columns
                ]
            current.closing_barline = "\t".join(tokens)
            current.length_q = position() - current.start_q
            regions.append(current)
            current = Region(start_q=position(), state=dict(state))
            continue

        # Data record: clean the cells of the output columns.
        columns = structure.output_columns()
        out_tokens: list[str] = []
        for base, live in enumerate(columns):
            cell = tokens[live] if live is not None and live < len(tokens) else "."
            if live is not None and structure.types[live] == KERN_SPINE:
                if (reason := cell_is_disallowed(cell)) and not current.disallowed:
                    current.disallowed = reason
                cell = clean_cell(cell)
                positions[base] += _cell_advance(cell)
            out_tokens.append(cell)
        if all(token == "." for token in out_tokens):
            continue  # pure grace-note record: removed from the score
        current.records.append(Record("data", "\t".join(out_tokens)))

    if current.records:
        current.length_q = position() - current.start_q
        regions.append(current)
    regions = [region for region in regions if any(r.kind == "data" for r in region.records)]
    base_count = structure.base_count if structure else 0
    if terminator.count("\t") + 1 != base_count:
        terminator = "\t".join(["*-"] * base_count)
    return KernSource(
        stem=stem,
        spine_line=spine_line,
        base_count=base_count,
        terminator=terminator,
        regions=regions,
        total_q=position(),
        tempo_changes=tempo_changes,
        warnings=warnings,
    )


def build_fragment_text(source: KernSource, region_indices: list[int]) -> str:
    """Assemble the reference text of one fragment from its measures."""
    lines = [source.spine_line]
    state = source.regions[region_indices[0]].state
    for category in HEADER_CATEGORIES:
        if line := state.get(category):
            lines.append(line)
    for index in region_indices:
        region = source.regions[index]
        lines.extend(record.line for record in region.records)
        if region.closing_barline:
            lines.append(region.closing_barline)
    lines.append(source.terminator)
    return "\n".join(lines)  # no trailing newline, as in the quartets references


def partition_regions(total: int, rng: random.Random, lo: int, hi: int) -> list[list[int]]:
    """Randomly partition ``total`` measures into fragments of lo-hi measures.

    Sizes are chosen so that the remainder stays partitionable; a remainder
    smaller than ``lo`` is merged into the last fragment.
    """
    parts: list[list[int]] = []
    start = 0
    while start < total:
        remaining = total - start
        choices = [
            size
            for size in range(lo, min(hi, remaining) + 1)
            if remaining - size == 0 or remaining - size >= lo
        ]
        if not choices:  # only possible when the tail must extend a fragment
            choices = [min(hi, remaining)]
        size = rng.choice(choices)
        parts.append(list(range(start, start + size)))
        start += size
    return parts


@dataclass
class Fragment:
    """One prepared fragment of a source score."""

    track_id: str
    text: str
    start_q: float
    length_q: float
    measures: int


def fragment_source(
    source: KernSource, rng: random.Random, min_measures: int = 3, max_measures: int = 6
) -> tuple[list[Fragment], list[tuple[str, int]]]:
    """Split a parsed source into prepared fragments.

    Returns the kept fragments (with sequential ``<stem>.<NNN>`` track ids)
    plus ``(reason, first measure index)`` pairs for the discarded ones.
    """
    fragments: list[Fragment] = []
    discarded: list[tuple[str, int]] = []
    counter = 0
    for part in partition_regions(len(source.regions), rng, min_measures, max_measures):
        reason = next(
            (source.regions[i].disallowed for i in part if source.regions[i].disallowed), None
        )
        if reason:
            discarded.append((reason, part[0]))
            continue
        counter += 1
        regions = [source.regions[i] for i in part]
        fragments.append(
            Fragment(
                track_id=f"{source.stem}.{counter:03d}",
                text=build_fragment_text(source, part),
                start_q=regions[0].start_q,
                length_q=sum(region.length_q for region in regions),
                measures=len(part),
            )
        )
    return fragments, discarded
