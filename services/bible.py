"""The 66-book Protestant canon (1,189 chapters) and a forgiving parser for
chapter references like "Jeremiah 29, Psalm 37, Matthew 6 and 7" or
"Rom 8:28-39". Used by the devotion connector to record which chapters a
morning devotion covered (Bible progress on My dashboard).
"""
import re

BOOKS = (
    ("Genesis", 50), ("Exodus", 40), ("Leviticus", 27), ("Numbers", 36), ("Deuteronomy", 34),
    ("Joshua", 24), ("Judges", 21), ("Ruth", 4), ("1 Samuel", 31), ("2 Samuel", 24),
    ("1 Kings", 22), ("2 Kings", 25), ("1 Chronicles", 29), ("2 Chronicles", 36), ("Ezra", 10),
    ("Nehemiah", 13), ("Esther", 10), ("Job", 42), ("Psalms", 150), ("Proverbs", 31),
    ("Ecclesiastes", 12), ("Song of Solomon", 8), ("Isaiah", 66), ("Jeremiah", 52),
    ("Lamentations", 5), ("Ezekiel", 48), ("Daniel", 12), ("Hosea", 14), ("Joel", 3),
    ("Amos", 9), ("Obadiah", 1), ("Jonah", 4), ("Micah", 7), ("Nahum", 3), ("Habakkuk", 3),
    ("Zephaniah", 3), ("Haggai", 2), ("Zechariah", 14), ("Malachi", 4),
    ("Matthew", 28), ("Mark", 16), ("Luke", 24), ("John", 21), ("Acts", 28), ("Romans", 16),
    ("1 Corinthians", 16), ("2 Corinthians", 13), ("Galatians", 6), ("Ephesians", 6),
    ("Philippians", 4), ("Colossians", 4), ("1 Thessalonians", 5), ("2 Thessalonians", 3),
    ("1 Timothy", 6), ("2 Timothy", 4), ("Titus", 3), ("Philemon", 1), ("Hebrews", 13),
    ("James", 5), ("1 Peter", 5), ("2 Peter", 3), ("1 John", 5), ("2 John", 1), ("3 John", 1),
    ("Jude", 1), ("Revelation", 22),
)
CHAPTER_COUNT = dict(BOOKS)
BOOK_ORDER = {name: i for i, (name, _) in enumerate(BOOKS)}
TOTAL_CHAPTERS = sum(CHAPTER_COUNT.values())  # 1,189

# Short forms that a unique-prefix match can't resolve (too short, or
# shared by two books: "phil", "jud").
_ALIASES = {
    "gn": "Genesis", "ex": "Exodus", "lv": "Leviticus", "nm": "Numbers", "dt": "Deuteronomy",
    "jdg": "Judges", "judg": "Judges", "ps": "Psalms", "psa": "Psalms", "psalm": "Psalms",
    "pss": "Psalms", "pr": "Proverbs", "qoh": "Ecclesiastes", "songofsongs": "Song of Solomon",
    "song": "Song of Solomon", "canticles": "Song of Solomon", "sos": "Song of Solomon",
    "is": "Isaiah", "jer": "Jeremiah", "ezk": "Ezekiel", "dn": "Daniel", "jl": "Joel",
    "mt": "Matthew", "mk": "Mark", "mrk": "Mark", "lk": "Luke", "jn": "John", "jhn": "John",
    "rm": "Romans", "phil": "Philippians", "php": "Philippians", "phl": "Philippians",
    "phlm": "Philemon", "philem": "Philemon", "phm": "Philemon", "jas": "James", "jud": "Jude",
    "rv": "Revelation", "revelations": "Revelation",
}
_ORDINALS = {"i": "1", "ii": "2", "iii": "3", "first": "1", "second": "2", "third": "3",
             "1st": "1", "2nd": "2", "3rd": "3"}


def _key(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", text.lower())


_BY_KEY = {_key(name): name for name, _ in BOOKS}


def find_book(text: str):
    """Canonical book name for "Jer", "1 Cor", "I John", "Song of Songs"…, or None."""
    words = text.strip().lower().replace(".", " ").split()
    if not words:
        return None
    if words[0] in _ORDINALS and len(words) > 1:
        words[0] = _ORDINALS[words[0]]
    key = _key("".join(words))
    if key in _BY_KEY:
        return _BY_KEY[key]
    if key in _ALIASES:
        return _ALIASES[key]
    if key[:1].isdigit() and key[1:] in _ALIASES:  # "1jn" → 1 John
        named = f"{key[0]} {_ALIASES[key[1:]]}"
        return named if named in CHAPTER_COUNT else None
    if len(key) >= 3:
        matches = [name for k, name in _BY_KEY.items() if k.startswith(key)]
        if len(matches) == 1:
            return matches[0]
    return None


# A book name (optionally numbered) followed by its chapter spec, e.g.
# "1 Corinthians 13", "Matthew 6 and 7", "Rom 8:28-39", "Psalm 23; 24".
_REF = re.compile(
    r"((?:(?:[123]|i{1,3}|first|second|third|1st|2nd|3rd)\s*)?[a-z][a-z.]*(?:\s+of\s+[a-z]+)?)\s*"
    r"(\d+(?:\s*:\s*\d+)?(?:\s*(?:[-–—]|,|;|&|\band\b)\s*\d+(?:\s*:\s*\d+)?)*)",
    re.IGNORECASE,
)
_PART_SPLIT = re.compile(r"\s*(?:,|;|&|\band\b)\s*", re.IGNORECASE)


def _chapters_in_part(part: str):
    """'6' → [6]; '6-7' → [6, 7]; '8:28-39' → [8]; '6:25-7:5' → [6, 7]."""
    ends = [p.strip() for p in re.split(r"[-–—]", part) if p.strip()]
    if not ends:
        return []
    first = int(ends[0].split(":")[0])
    if len(ends) == 1:
        return [first]
    last_text = ends[-1]
    if ":" in ends[0] and ":" not in last_text:
        return [first]  # verse range inside one chapter: 8:28-39
    last = int(last_text.split(":")[0])
    return list(range(first, last + 1)) if last >= first else [first]


def parse_chapters(text: str):
    """("Jeremiah 29, Psalm 37, Matthew 6 and 7") → ([("Jeremiah", 29),
    ("Psalms", 37), ("Matthew", 6), ("Matthew", 7)], problems). Duplicates
    are dropped; anything unrecognised is reported in `problems`, never guessed."""
    found, problems = [], []
    seen = set()
    for match in _REF.finditer(text or ""):
        book_text, spec = match.group(1), match.group(2)
        book = find_book(book_text)
        if book is None:
            problems.append(f"Unknown book: {book_text.strip()}")
            continue
        for part in _PART_SPLIT.split(spec):
            for chapter in _chapters_in_part(part):
                if not 1 <= chapter <= CHAPTER_COUNT[book]:
                    problems.append(f"{book} has no chapter {chapter}")
                elif (book, chapter) not in seen:
                    seen.add((book, chapter))
                    found.append((book, chapter))
    if not found and not problems:
        problems.append("No chapters found")
    return found, problems


def display_name(book: str, single: bool) -> str:
    return "Psalm" if book == "Psalms" and single else book


def format_chapters(chapters) -> str:
    """[("Psalms", 37), ("Matthew", 6), ("Matthew", 7)] → "Psalm 37, Matthew 6–7",
    keeping the order they were read in."""
    groups = []  # [book, [chapters]] runs of the same book
    for book, chapter in chapters:
        if groups and groups[-1][0] == book:
            groups[-1][1].append(chapter)
        else:
            groups.append([book, [chapter]])
    out = []
    for book, nums in groups:
        spans, start = [], nums[0]
        for prev, cur in zip(nums, nums[1:] + [None]):
            if cur != prev + 1:
                spans.append(str(start) if start == prev else f"{start}–{prev}")
                start = cur
        out.append(f"{display_name(book, len(nums) == 1)} {', '.join(spans)}")
    return ", ".join(out)
