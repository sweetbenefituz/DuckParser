def detect_level(text: str) -> str:
    t = text.lower()

    warn_pos = t.find("warning")
    err_positions = [t.find("error"), t.find("fail")]
    err_positions = [p for p in err_positions if p != -1]

    err_pos = min(err_positions) if err_positions else -1

    if warn_pos != -1 and (err_pos == -1 or warn_pos < err_pos):
        return "WARNING"
    if err_pos != -1:
        return "ERROR"

    return "ALL"
