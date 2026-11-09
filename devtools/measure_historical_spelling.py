"""Measure historical spelling against a modern Brazilian Portuguese word list.

The patterns in app/retrieval/bm25.py fold old Portuguese spellings onto modern ones (Sophia onto
Sofia). Applied to every word, some would also make two modern words identical: pacto would become
pato. Those modern keys are left as they are, and this script finds them, from a list of every word
form in modern Brazilian Portuguese. It checks them against the _KEPT_KEYS committed in bm25.py, so
run it again after any change to a pattern (specs/001-historical-spelling, FR-003 and SC-005).

The word list is Debian's wbrazilian package, version 3.0~beta4-25, from the br.ispell project
(GPL-2). It isn't kept in this repository:

    mkdir -p /tmp/wbrazilian && cd /tmp/wbrazilian && apt-get download wbrazilian \\
        && dpkg-deb -x wbrazilian_*.deb extracted && cd -
    uv run python devtools/measure_historical_spelling.py /tmp/wbrazilian/extracted/usr/share/dict/brazilian

It exits with an error if two modern words still collide, if one of the spec's 28 pairs doesn't
match, or if the kept keys differ from _KEPT_KEYS, and then prints the set to commit.
"""

import collections
import sys
import textwrap
from pathlib import Path

import Stemmer

from app.retrieval.bm25 import _AFTER_STEMMING, _KEPT_KEYS, _strip_accents, historical_key

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # for tests/, which isn't installed

from tests.historical_spelling import PAIRS  # noqa: E402


def main(word_list: Path) -> int:
    stemmer = Stemmer.Stemmer("portuguese")
    words = sorted({line.strip().casefold() for line in word_list.open(encoding="utf-8") if line.strip()})
    plain = {word: _strip_accents(stemmer.stemWord(word)) for word in words}
    folded = {word: historical_key(word, stemmer, frozenset()) for word in words}
    changing = {plain[word] for word in words if folded[word] != plain[word]}

    kept: set[str] = set()
    while True:
        groups = collections.defaultdict(set)
        for word in words:
            groups[plain[word] if plain[word] in kept else folded[word]].add(plain[word])
        colliding = {key for keys in groups.values() if len(keys) > 1 for key in keys}
        new = (colliding & changing) - kept
        if not new:
            break
        kept |= new

    collisions = [sorted(keys) for keys in groups.values() if len(keys) > 1]
    final = frozenset(kept)
    matched = [
        (modern, old)
        for modern, old in PAIRS
        if historical_key(modern.casefold(), stemmer, final) == historical_key(old.casefold(), stemmer, final)
    ]

    print(f"{word_list}: {len(words)} words, {len(set(plain.values()))} keys, {len(changing)} change")
    print(f"kept as they are: {len(kept)}")
    for pattern, count in _count_by_pattern(kept).items():
        print(f"  {pattern}: {count}")
    print(f"collisions left: {len(collisions)}")
    print(f"pairs matched: {len(matched)} of {len(PAIRS)}")
    for modern, old in PAIRS:
        if (modern, old) not in matched:
            print(f"  not matched: {modern} / {old}")

    failed = bool(collisions) or len(matched) < len(PAIRS)
    if final != _KEPT_KEYS:
        failed = True
        print(f"_KEPT_KEYS differs: {len(kept - _KEPT_KEYS)} missing, {len(_KEPT_KEYS - kept)} extra")
        print("Commit this as _KEPT_KEYS in app/retrieval/bm25.py:\n")
        body = textwrap.fill(" ".join(sorted(kept)), width=96, initial_indent="    ", subsequent_indent="    ")
        print(f'_KEPT_KEYS: frozenset[str] = frozenset(\n    """\n{body}\n    """.split()\n)')
    else:
        print("_KEPT_KEYS matches.")
    return 1 if failed else 0


def _count_by_pattern(keys: set[str]) -> dict[str, int]:
    """Which pattern changes each kept key. A key no pattern touches comes from a word with a y."""
    counts: collections.Counter[str] = collections.Counter()
    for key in keys:
        touched = [pattern.pattern for pattern, replacement in _AFTER_STEMMING if pattern.sub(replacement, key) != key]
        for name in touched or ["y -> i"]:
            counts[name] += 1
    return dict(counts.most_common())


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    sys.exit(main(Path(sys.argv[1])))
