from __future__ import annotations

from dataclasses import dataclass

import simplemma

from era.nlp.tokenize import strip_contraction


@dataclass(frozen=True)
class DictHit:
    word: str
    frq: int
    bnc: int

    @property
    def rank(self) -> int:
        vals = [v for v in (self.frq, self.bnc) if v and v > 0]
        return min(vals) if vals else 10**7


def extra_stems(word: str) -> list[str]:
    """Suffix guesses so acting→act, studies→study. Do not use ECDICT exchange."""
    w = word.lower()
    out: list[str] = []
    if w.endswith("ing") and len(w) > 5:
        stem = w[:-3]
        out.extend([stem, stem + "e"])
        if len(stem) >= 2 and stem[-1] == stem[-2]:
            out.append(stem[:-1])
    if w.endswith("ies") and len(w) > 4:
        out.append(w[:-3] + "y")
    if w.endswith("es") and len(w) > 4:
        out.append(w[:-2])
    if w.endswith("s") and not w.endswith("ss") and len(w) > 3:
        out.append(w[:-1])
    if w.endswith("ed") and len(w) > 4:
        out.extend([w[:-2], w[:-1], w[:-2] + "e"])
        if len(w) > 5 and w[-3] == w[-4]:
            out.append(w[:-3])
    return out


def lemma_candidates(word: str) -> list[str]:
    stripped = strip_contraction(word).lower()
    if not stripped:
        return []
    found: list[str] = []
    seen: set[str] = set()
    try:
        sm = simplemma.lemmatize(stripped, lang="en")
    except Exception:  # pragma: no cover
        sm = stripped
    for cand in [sm, stripped]:
        c = cand.lower()
        if c and c not in seen:
            seen.add(c)
            found.append(c)
    # Suffix guesses only when simplemma left the surface unchanged
    # (acting→acting). This avoids routing→rout via naive -ing stripping.
    if sm.lower() == stripped:
        for cand in extra_stems(stripped):
            c = cand.lower()
            if c and c not in seen:
                seen.add(c)
                found.append(c)
    return found


def pick_lemma(word: str, lookup) -> str | None:
    """lookup(word) -> DictHit | None. Prefer the candidate with the best (lowest) rank."""
    scored: list[tuple[int, str]] = []
    for cand in lemma_candidates(word):
        hit = lookup(cand)
        if hit is not None:
            scored.append((hit.rank, hit.word))
    if not scored:
        return None
    scored.sort()
    return scored[0][1]
