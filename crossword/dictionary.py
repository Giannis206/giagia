"""Greek dictionary loading, normalization, and quality validation."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

GREEK_LETTERS = "ΑΒΓΔΕΖΗΘΙΚΛΜΝΞΟΠΡΣΤΥΦΧΨΩ"
GREEK_RE = re.compile(rf"^[{GREEK_LETTERS}]+$")
VOWELS = set("ΑΕΗΙΟΥΩ")
CONSONANTS = set(GREEK_LETTERS) - VOWELS

# Common Greek endings / patterns (no accents)
COMMON_SUFFIXES = (
    "ΟΣ",
    "Η",
    "Α",
    "ΕΣ",
    "ΟΙ",
    "ΑΙ",
    "ΟΥ",
    "ΕΙ",
    "ΙΑ",
    "ΜΑ",
    "ΤΑ",
    "ΝΑ",
    "ΜΕ",
    "ΣΕ",
    "ΤΟ",
    "ΝΟ",
)

_ACCENTED_TO_PLAIN = str.maketrans(
    {
        "Ά": "Α",
        "Έ": "Ε",
        "Ή": "Η",
        "Ί": "Ι",
        "Ό": "Ο",
        "Ύ": "Υ",
        "Ώ": "Ω",
        "Ϊ": "Ι",
        "Ϋ": "Υ",
        "ά": "Α",
        "έ": "Ε",
        "ή": "Η",
        "ί": "Ι",
        "ό": "Ο",
        "ύ": "Υ",
        "ώ": "Ω",
        "ϊ": "Ι",
        "ΐ": "Ι",
        "ϋ": "Υ",
        "ΰ": "Υ",
    }
)


@dataclass
class DictionaryReport:
    accepted: dict[int, list[str]] = field(default_factory=dict)
    rejected: list[tuple[str, str]] = field(default_factory=list)

    def counts(self) -> dict[int, int]:
        return {length: len(words) for length, words in sorted(self.accepted.items())}


def normalize_word(raw: str) -> str:
    """Uppercase Greek word without accents or surrounding whitespace."""
    text = raw.strip()
    if not text or text.startswith("#"):
        return ""
    text = unicodedata.normalize("NFD", text)
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    text = text.upper().translate(_ACCENTED_TO_PLAIN)
    text = "".join(ch for ch in text if ch in GREEK_LETTERS)
    return text


def rejection_reason(word: str, expected_length: int | None = None) -> str | None:
    if not word:
        return "empty"
    if expected_length is not None and len(word) != expected_length:
        return f"wrong length ({len(word)} != {expected_length})"
    if not GREEK_RE.match(word):
        return "non-greek characters"
    if len(set(word)) == 1:
        return "single repeated letter"
    if re.search(r"(.)\1{2,}", word):
        return "excessive repeated letters"
    if len(word) >= 4 and len(set(word)) <= 2:
        return "too few unique letters"
    if len(word) <= 4 and word.count("Α") >= len(word) - 1:
        return "looks like garbage initials"
    vowel_count = sum(1 for ch in word if ch in VOWELS)
    if vowel_count == 0 and len(word) <= 3:
        return "no vowels in short word"
    if len(word) >= 5 and vowel_count < 2:
        return "too few vowels"
    if re.search(r"(ΣΗ){2,}", word) or re.search(r"(ΗΣ){3,}", word):
        return "artificial suffix chain"
    from collections import Counter

    most_common = Counter(word).most_common(1)[0][1]
    if len(word) >= 6 and most_common / len(word) > 0.38:
        return "letter frequency imbalance"
    return None


def validate_word(word: str, expected_length: int | None = None) -> bool:
    return rejection_reason(word, expected_length) is None


def word_score(word: str, frequency: int = 0) -> int:
    """Higher is better — prefer common-looking Greek word shapes."""
    score = 0
    if frequency > 0:
        # Log-scale boost from corpus frequency (SUBTLEX counts).
        import math

        score += int(math.log10(frequency + 1) * 25)
    for suffix in COMMON_SUFFIXES:
        if word.endswith(suffix):
            score += 12
    vowels = sum(1 for ch in word if ch in VOWELS)
    score += min(vowels, 4) * 3
    score -= max(0, len(word) - 10) * 2
    if re.search(r"(.)\1{2,}", word):
        score -= 40
    if len(set(word)) <= max(2, len(word) // 3):
        score -= 20
    # Slight bonus for balanced vowel/consonant mix
    if 0 < vowels < len(word):
        score += 5
    return score


def load_dictionary(
    data_dir: Path,
    *,
    strict: bool = True,
) -> tuple[dict[int, set[str]], dict[str, int]]:
    """Load validated dictionary and per-word scores."""
    dictionary: dict[int, set[str]] = {}
    scores: dict[str, int] = {}

    freq_path = data_dir / "word_scores.json"
    freq_map: dict[str, int] = {}
    if freq_path.exists():
        import json

        freq_map = {k: int(v) for k, v in json.loads(freq_path.read_text(encoding="utf-8")).items()}

    for path in sorted(data_dir.glob("words_*.txt")):
        length_str = path.stem.split("_", 1)[1]
        try:
            expected_length = int(length_str)
        except ValueError:
            continue

        bucket: set[str] = set()
        for line in path.read_text(encoding="utf-8").splitlines():
            word = normalize_word(line)
            reason = rejection_reason(word, expected_length)
            if reason:
                if not strict and word:
                    continue
                continue
            if word in bucket:
                continue
            bucket.add(word)
            scores[word] = word_score(word, freq_map.get(word, 0))

        if bucket:
            dictionary[expected_length] = bucket

    return dictionary, scores


def load_dictionary_report(data_dir: Path) -> DictionaryReport:
    """Validate every dictionary file and collect accepted/rejected entries."""
    report = DictionaryReport()

    for path in sorted(data_dir.glob("words_*.txt")):
        length_str = path.stem.split("_", 1)[1]
        try:
            expected_length = int(length_str)
        except ValueError:
            continue

        accepted: list[str] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            raw = line.strip()
            if not raw or raw.startswith("#"):
                continue
            word = normalize_word(raw)
            reason = rejection_reason(word, expected_length)
            if reason:
                report.rejected.append((raw, reason))
            elif word not in accepted:
                accepted.append(word)

        if accepted:
            report.accepted[expected_length] = sorted(accepted)

    return report


def dictionary_stats(dictionary: dict[int, set[str]]) -> dict[int, int]:
    return {length: len(words) for length, words in sorted(dictionary.items())}
