from __future__ import annotations


def parse_word_list(text: str, default_status: str = "known") -> list[tuple[str, str]]:
    """Each line: word[,status]. Status defaults to known (CSV/TXT fallback)."""
    allowed = {"unknown", "learning", "known", "ignored"}
    out: list[tuple[str, str]] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "," in line:
            word, status = [p.strip() for p in line.split(",", 1)]
        elif "\t" in line:
            word, status = [p.strip() for p in line.split("\t", 1)]
        else:
            word, status = line, default_status
        status = status.lower()
        if status not in allowed:
            status = default_status
        word = word.strip().lower()
        if word:
            out.append((word, status))
    return out
