"""Split the raw Silmarillion .txt into part/chapter records.

This targets one specific OCR'd ebook .txt whose quirks drive most of the
logic below:
  - The table of contents (and a second, near-duplicate copy of it near
    the end of the file) lists every part/chapter title with no content
    between entries. The real section headings are identical text but sit
    far apart, each followed by pages of prose. Real occurrences are
    picked as whichever match starts the *longest* run of text before the
    next heading/sentinel.
  - Some Quenta Silmarillion chapters are missing their "CHAPTER N" line
    (an OCR artifact) but every chapter's "OF ..." title line survives, so
    chapters are split on that instead.
  - Chapter titles are pulled from the ebook's own (clean) table of
    contents rather than the body headings, since OCR introduces typos in
    the body (e.g. "WRAIH" for "WRATH").
  - After "Of the Rings of Power and the Third Age", the genealogical
    tables and maps degrade into unreadable OCR noise; that trailing junk
    is cut at the last legible sentence.

Output: data/processed/chapters.json — list of
  {"part": str, "chapter_number": int | None, "chapter_title": str, "text": str}
"""

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from src.config import PROCESSED_DIR, RAW_DIR

CHAPTER_TITLES = [
    "Of the Beginning of Days",
    "Of Aulë and Yavanna",
    "Of the Coming of the Elves and the Captivity of Melkor",
    "Of Thingol and Melian",
    "Of Eldamar and the Princes of the Eldalië",
    "Of Fëanor and the Unchaining of Melkor",
    "Of the Silmarils and the Unrest of the Noldor",
    "Of the Darkening of Valinor",
    "Of the Flight of the Noldor",
    "Of the Sindar",
    "Of the Sun and Moon and the Hiding of Valinor",
    "Of Men",
    "Of the Return of the Noldor",
    "Of Beleriand and its Realms",
    "Of the Noldor in Beleriand",
    "Of Maeglin",
    "Of the Coming of Men into the West",
    "Of the Ruin of Beleriand and the Fall of Fingolfin",
    "Of Beren and Lúthien",
    "Of the Fifth Battle: Nirnaeth Arnoediad",
    "Of Túrin Turambar",
    "Of the Ruin of Doriath",
    "Of Tuor and the Fall of Gondolin",
    "Of the Voyage of Eärendil and the War of Wrath",
]

PART_HEADER_PATTERNS = {
    "Ainulindalë": re.compile(r"^\s*AINULINDAL[EÉ]\s*$", re.MULTILINE),
    "Valaquenta": re.compile(r"^\s*VALAQUENTA\s*$", re.MULTILINE),
    "Akallabêth": re.compile(r"^\s*AKALLAB[EÉ]TH\s*$", re.MULTILINE),
    "Of the Rings of Power and the Third Age": re.compile(
        r"^\s*OF THE RINGS OF POWER AND THE THIRD AGE\s*$", re.MULTILINE
    ),
}
SENTINEL_PATTERNS = [re.compile(r"^\s*NOTE ON PRONUNCIATION\s*$", re.MULTILINE)]

QUENTA_START_RE = re.compile(r"^\s*CHAPTER\s+1\s*$", re.MULTILINE)
CHAPTER_TITLE_LINE_RE = re.compile(
    r"^\s*(OF [A-ZÀ-ÞÜÉÁÍÓÚÑ0-9' \-,:]{3,90})\s*$", re.MULTILINE
)
TRAILING_CHAPTER_NUM_RE = re.compile(r"\n?\s*CHAPTER\s+\d+\s*\Z")

RINGS_OF_POWER_END_MARKER = "an end was come for the Eldar of story and of song."


def find_raw_file() -> Path:
    txt_files = sorted(RAW_DIR.glob("*.txt"))
    if not txt_files:
        raise FileNotFoundError(
            f"No .txt file found in {RAW_DIR}. Add the Silmarillion source there first."
        )
    return txt_files[0]


def find_real_part_headers(text: str) -> dict[str, re.Match]:
    all_matches = []
    for name, pattern in PART_HEADER_PATTERNS.items():
        all_matches.extend((m.start(), m.end(), name, m) for m in pattern.finditer(text))
    for pattern in SENTINEL_PATTERNS:
        all_matches.extend((m.start(), m.end(), "__sentinel__", m) for m in pattern.finditer(text))
    all_matches.sort(key=lambda t: t[0])

    next_starts = [t[0] for t in all_matches[1:]] + [len(text)]

    best: dict[str, tuple[int, re.Match]] = {}
    for (start, end, name, m), next_start in zip(all_matches, next_starts):
        if name == "__sentinel__":
            continue
        gap = next_start - end
        if name not in best or gap > best[name][0]:
            best[name] = (gap, m)

    missing = set(PART_HEADER_PATTERNS) - set(best)
    if missing:
        raise ValueError(f"Could not locate real headers for: {missing}")
    return {name: m for name, (_, m) in best.items()}


def split_chapters(quenta_text: str) -> list[tuple[int, str, str]]:
    matches = list(CHAPTER_TITLE_LINE_RE.finditer(quenta_text))
    if len(matches) != len(CHAPTER_TITLES):
        raise ValueError(
            f"Expected {len(CHAPTER_TITLES)} chapter title lines, found {len(matches)} — "
            "the source formatting may have changed."
        )

    chapters = []
    for i, match in enumerate(matches):
        body_start = match.end()
        body_end = matches[i + 1].start() if i + 1 < len(matches) else len(quenta_text)
        body = quenta_text[body_start:body_end]
        body = TRAILING_CHAPTER_NUM_RE.sub("", body).strip()
        chapters.append((i + 1, CHAPTER_TITLES[i], body))
    return chapters


def main() -> None:
    raw_path = find_raw_file()
    text = raw_path.read_text(encoding="utf-8")

    headers = find_real_part_headers(text)
    ainulindale = headers["Ainulindalë"]
    valaquenta = headers["Valaquenta"]
    akallabeth = headers["Akallabêth"]
    rings = headers["Of the Rings of Power and the Third Age"]

    quenta_region = text[valaquenta.end() : akallabeth.start()]
    quenta_start_match = QUENTA_START_RE.search(quenta_region)
    if quenta_start_match is None:
        raise ValueError("Could not find start of Quenta Silmarillion (CHAPTER 1 line).")
    quenta_text = quenta_region[quenta_start_match.start() :]

    end_marker_pos = text.find(RINGS_OF_POWER_END_MARKER, rings.end())
    if end_marker_pos == -1:
        raise ValueError("Could not find end-of-narrative marker for Of the Rings of Power.")
    rings_end = end_marker_pos + len(RINGS_OF_POWER_END_MARKER)

    records = [
        {
            "part": "Ainulindalë",
            "chapter_number": None,
            "chapter_title": "",
            "text": text[ainulindale.end() : valaquenta.start()].strip(),
        },
        {
            "part": "Valaquenta",
            "chapter_number": None,
            "chapter_title": "",
            "text": quenta_region[: quenta_start_match.start()].strip(),
        },
    ]
    for chapter_number, chapter_title, body in split_chapters(quenta_text):
        records.append(
            {
                "part": "Quenta Silmarillion",
                "chapter_number": chapter_number,
                "chapter_title": chapter_title,
                "text": body,
            }
        )
    records.append(
        {
            "part": "Akallabêth",
            "chapter_number": None,
            "chapter_title": "",
            "text": text[akallabeth.end() : rings.start()].strip(),
        }
    )
    records.append(
        {
            "part": "Of the Rings of Power and the Third Age",
            "chapter_number": None,
            "chapter_title": "",
            "text": text[rings.end() : rings_end].strip(),
        }
    )

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    out_path = PROCESSED_DIR / "chapters.json"
    out_path.write_text(json.dumps(records, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"Wrote {len(records)} chapter/part records to {out_path}")
    for r in records:
        label = r["part"] + (f" — {r['chapter_number']}: {r['chapter_title']}" if r["chapter_number"] else "")
        print(f"  {label} ({len(r['text'])} chars)")


if __name__ == "__main__":
    main()
