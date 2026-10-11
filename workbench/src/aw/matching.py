"""Patient/member identity matching (CAP-06, BL-11).

Indian names arrive in many romanisations (LAKSHMI / LAXMI, SHRINIVAS / SRINIVAS), with titles
(Mr., Smt., Dr.), initials (S. SHARMA) and spacing differences. The matcher:
  1. normalises: uppercase, strip titles and punctuation, collapse spaces;
  2. folds common transliteration variants (KSH→X, AA→A, EE→I, W→V, PH→F, aspirates, doubled letters);
  3. scores each token of the observed name against the best member token with Jaro-Winkler;
     an initial matches a token with the same first letter at a fixed partial score;
  4. decides: gender conflict → BLOCK; every token ≥ PASS_MIN → PASS; every token ≥ REVIEW_MIN → REVIEW; else BLOCK.

Thresholds are starting values to calibrate on pilot data (07 §6). They are conservative: a similar but
different name (SUNITA vs SUNIL) lands in REVIEW, never PASS.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

PASS_MIN = 0.95
REVIEW_MIN = 0.80
INITIAL_SCORE = 0.85

_TITLES = {"MR", "MRS", "MS", "MISS", "DR", "SMT", "SHRI", "SRI", "SHRIMATI", "KUMARI", "KUM", "MASTER", "BABY", "MX", "PROF", "LATE", "B/O", "BO"}
_FOLDS = [("KSH", "X"), ("KS", "X"), ("SHR", "SR"), ("AA", "A"), ("EE", "I"), ("II", "I"), ("OO", "U"), ("UU", "U"),
          ("PH", "F"), ("TH", "T"), ("DH", "D"), ("BH", "B"), ("KH", "K"), ("GH", "G"), ("JH", "J"), ("W", "V"), ("Z", "J"),
          ("Q", "K"), ("CK", "K")]


def normalise_name(raw: str) -> str:
    s = raw.upper()
    s = re.sub(r"[^A-Z/ ]+", " ", s)
    tokens = [t for t in s.split() if t not in _TITLES]
    return " ".join(tokens)


def fold(token: str) -> str:
    t = token
    for a, b in _FOLDS:
        t = t.replace(a, b)
    t = re.sub(r"(.)\1+", r"\1", t)          # doubled letters
    if len(t) > 3 and t.endswith("Y"):
        t = t[:-1] + "I"
    return t


def jaro_winkler(a: str, b: str) -> float:
    if a == b:
        return 1.0
    if not a or not b:
        return 0.0
    window = max(len(a), len(b)) // 2 - 1
    a_flags, b_flags = [False] * len(a), [False] * len(b)
    matches = 0
    for i, ch in enumerate(a):
        lo, hi = max(0, i - window), min(i + window + 1, len(b))
        for j in range(lo, hi):
            if not b_flags[j] and b[j] == ch:
                a_flags[i] = b_flags[j] = True
                matches += 1
                break
    if matches == 0:
        return 0.0
    k = transpositions = 0
    for i, f in enumerate(a_flags):
        if f:
            while not b_flags[k]:
                k += 1
            if a[i] != b[k]:
                transpositions += 1
            k += 1
    m = matches
    jaro = (m / len(a) + m / len(b) + (m - transpositions / 2) / m) / 3
    prefix = 0
    for x, y in zip(a[:4], b[:4]):
        if x != y:
            break
        prefix += 1
    return jaro + prefix * 0.1 * (1 - jaro)


@dataclass
class MatchResult:
    decision: str          # PASS | REVIEW | BLOCK
    score: float           # lowest per-token score
    reason: str


def score_identity(observed_name: str, observed_gender: str | None, member_name: str, member_gender: str | None) -> MatchResult:
    if observed_gender in ("F", "M") and member_gender in ("F", "M") and observed_gender != member_gender:
        return MatchResult("BLOCK", 0.0, "gender conflict")
    obs = [fold(t) for t in normalise_name(observed_name).split()]
    mem = [fold(t) for t in normalise_name(member_name).split()]
    if not obs or not mem:
        return MatchResult("REVIEW", 0.0, "name missing")
    scores = []
    for t in obs:
        best = 0.0
        for u in mem:
            s = INITIAL_SCORE if (len(t) == 1 and u.startswith(t)) or (len(u) == 1 and t.startswith(u)) else jaro_winkler(t, u)
            best = max(best, s)
        scores.append(best)
    low = min(scores)
    if abs(len(obs) - len(mem)) > 1:
        low = min(low, REVIEW_MIN)
    if low >= PASS_MIN:
        return MatchResult("PASS", round(low, 4), "all name tokens match after transliteration folding")
    if low >= REVIEW_MIN:
        return MatchResult("REVIEW", round(low, 4), "name similar but not certain")
    return MatchResult("BLOCK", round(low, 4), "name does not match")
