"""Key sentences for the reader pop-up, picked locally (no AI).

Each word gets a weight: how often it appears in this story times how rare it is across all stored
stories (TF-IDF), with a bonus for words in the headline. A sentence scores the weights of its words,
so the sentences that carry the story's own topic win over background and filler."""
from __future__ import annotations

import math
import re
from collections import Counter
from typing import Iterable

MAX_SENTENCES = 3
SENTENCES_PER_PICK = 8   # one highlight per ~8 sentences: 1 for a short story, 3 for a long one
MIN_WORDS = 8            # skip fragments ("Read more.") ...
MAX_WORDS = 60           # ... and run-on blocks that are hard to read as one highlight
TITLE_BONUS = 1.6
LEAD_BONUS = 1.2         # news puts the main point first
SAME_POINT = 0.6         # two sentences sharing 60 % of their words make the same point

# Common English words plus news filler; they carry no topic.
STOPWORDS = frozenset("""
a about above after again against ago all almost also although always am among an and another any
anyone anything are around as at away back be became because become been before being below
between both but by came can cannot could day days did do does doing done down during each early
either else end enough even ever every few first for four from further get gets getting give given
go going gone got had has have having he her here hers herself him himself his how however i if in
including into is it its itself just know known last later least less let like made make makes
many may me might more most much must my myself near need never new next no nor not now of off
often on once one only or other others our ours out over own part past people per put rather really
said same say saying says second see seen set several she should show since so some something soon
still such take taken than that the their theirs them themselves then there these they thing things
think third this those though three through time times to today told too took toward two under
until up upon us use used using very via want was way ways we week weeks well went were what when
where whether which while who whom whose why will with within without would year years yet you
your yours yourself according added adding asked called comes coming continue expected
reported reports report recent recently amid across mr mrs ms dr latest
monday tuesday wednesday thursday friday saturday sunday january february march april may june july
august september october november december percent cent
hundred hundreds thousand thousands million millions billion billions trillion trillions dozen dozens
""".split())

# A period after these doesn't end a sentence ("Mr. Huang", "U.S. officials", "Donald J. Trump").
ABBREVIATIONS = frozenset("""mr mrs ms dr prof st jr sr inc corp co ltd plc gov sen rep gen lt col
capt sgt no vs etc approx est u.s u.k u.n e.u e.g i.e a.m p.m jan feb aug sept oct nov dec""".split())

WORD_RE = re.compile(r"[A-Za-z][A-Za-z'’\-]*[A-Za-z]")
END_RE = re.compile(r"[.!?]+[\"'”’)\]]*(?=\s)")


def tokens(text: str) -> list[str]:
    return [w.lower().replace("’", "'") for w in WORD_RE.findall(text or "")]


def stem(word: str) -> str:
    """Group simple word forms: possessive, plural (gorillas -> gorilla, companies -> company)."""
    if word.endswith("'s"):
        word = word[:-2]
    if len(word) > 4 and word.endswith("ies"):
        return word[:-3] + "y"
    if len(word) > 4 and word.endswith(("ches", "shes", "sses", "xes", "zes")):
        return word[:-2]
    if len(word) > 3 and word.endswith("s") and not word.endswith(("ss", "us", "is")):
        return word[:-1]
    return word


def content_stems(text: str) -> list[str]:
    out = []
    for w in tokens(text):
        if len(w) < 3 or w in STOPWORDS:
            continue
        s = stem(w)
        if len(s) >= 3 and s not in STOPWORDS:
            out.append(s)
    return out


def split_sentences(paragraph: str) -> list[str]:
    """Split a paragraph into sentences, exactly as written (each one is a substring of it)."""
    text = paragraph.strip()
    out, start = [], 0
    for m in END_RE.finditer(text):
        before = text[start:m.start()].split()
        last = before[-1].lower().strip("\"'“‘(") if before else ""
        rest = text[m.end():].lstrip()
        nxt = rest[:1]
        if (m.group().startswith(".") and (last in ABBREVIATIONS or (len(last) == 1 and last.isalpha())))\
                or not nxt or not (nxt.isupper() or nxt.isdigit() or nxt in "\"“‘'("):
            continue
        out.append(text[start:m.end()].strip())
        start = len(text) - len(rest)
    tail = text[start:].strip()
    if tail:
        out.append(tail)
    return out


class Corpus:
    """Document frequencies (by word stem) over all stored stories, for the IDF part of the score."""

    def __init__(self, texts: Iterable[str]):
        self.df: Counter[str] = Counter()
        self.n_docs = 0
        for text in texts:
            self.n_docs += 1
            self.df.update(set(content_stems(text)))

    def idf(self, word_stem: str) -> float:
        return math.log((self.n_docs + 1) / (self.df.get(word_stem, 0) + 1)) + 1.0


def word_weights(title: str, paragraphs: list[str], corpus: Corpus, exclude: Iterable[str] = ()) -> dict[str, float]:
    """TF-IDF weight per word stem in this story; words of the source/author names weigh nothing."""
    banned = {stem(w) for x in exclude for w in tokens(x)}
    title_stems = set(content_stems(title))
    tf = Counter(s for p in paragraphs for s in content_stems(p) if s not in banned)
    return {s: n * corpus.idf(s) * (TITLE_BONUS if s in title_stems else 1.0) for s, n in tf.items()}


def key_sentences(title: str, paragraphs: list[str], corpus: Corpus, exclude: Iterable[str] = ()) -> list[str]:
    """The story's most important sentences, in reading order, at most one per paragraph.
    Each is returned exactly as it appears in its paragraph, so the page can find and mark it."""
    weights = word_weights(title, paragraphs, corpus, exclude)
    title_norm = _norm(title)
    candidates = []                                   # (score, paragraph index, order, sentence)
    order = 0
    for pi, para in enumerate(paragraphs):
        for sentence in split_sentences(para):
            n_words = len(tokens(sentence))
            stems = content_stems(sentence)
            if MIN_WORDS <= n_words <= MAX_WORDS and stems and _norm(sentence) != title_norm:
                score = sum(weights.get(s, 0.0) for s in set(stems)) / math.sqrt(len(stems))
                if order == 0:
                    score *= LEAD_BONUS
                candidates.append((score, pi, order, sentence))
            order += 1
    if not candidates:
        return []
    want = min(MAX_SENTENCES, math.ceil(len(candidates) / SENTENCES_PER_PICK))
    chosen, used_paragraphs, used_words = [], set(), []
    for score, pi, o, sentence in sorted(candidates, key=lambda c: (-c[0], c[2])):
        words = set(content_stems(sentence))
        # Skip a sentence that repeats one already picked (sites often restate the lead as a bullet).
        if pi in used_paragraphs or any(_overlap(words, u) >= SAME_POINT for u in used_words):
            continue
        chosen.append((o, sentence))
        used_paragraphs.add(pi)
        used_words.append(words)
        if len(chosen) >= want:
            break
    return [s for _, s in sorted(chosen)]


def _overlap(a: set[str], b: set[str]) -> float:
    """Share of the smaller sentence's words that the other one also has."""
    return len(a & b) / max(1, min(len(a), len(b)))


def _norm(text: str) -> str:
    return "".join(ch for ch in (text or "").lower() if ch.isalnum())
