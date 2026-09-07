DEFAULT_ERROR_WORDS = ("error", "fail")
DEFAULT_WARNING_WORDS = ("warning",)


def _first_hit(text: str, words) -> int:
    """Position of the earliest of `words` in `text`, or -1 when none appear."""
    hits = [p for p in (text.find(w) for w in words if w) if p != -1]
    return min(hits) if hits else -1


def detect_level(text: str,
                 error_words=DEFAULT_ERROR_WORDS,
                 warning_words=DEFAULT_WARNING_WORDS) -> str:
    """Words must be lowercase; whichever appears first in the line wins."""
    t = text.lower()

    warn_pos = _first_hit(t, warning_words)
    err_pos = _first_hit(t, error_words)

    if warn_pos != -1 and (err_pos == -1 or warn_pos < err_pos):
        return "WARNING"
    if err_pos != -1:
        return "ERROR"

    return "ALL"
