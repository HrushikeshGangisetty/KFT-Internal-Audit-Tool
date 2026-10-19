"""Parsing and comparison of ArduPilot ``.param`` files.

A parameter dump is the closest thing an FC has to a configuration fingerprint,
and "what changed between these two?" is a question that comes up constantly
during firmware and tuning investigations. Doing it by eye across 1,100 lines is
how subtle differences get missed.
"""
import re

# Real dumps use a comma, but Mission Planner and hand-edited files also use
# whitespace or tabs, and some tools append a third column. Accept all of them.
_SEPARATOR = re.compile(r"[,\t]|\s{1,}")


def parse(text):
    """Parse a .param file into ``{NAME: value}``.

    Returns the parameters plus any lines that could not be read, so a
    malformed file reports what it skipped rather than silently losing values.
    """
    parameters, skipped = {}, []
    for number, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith(("#", "//")):
            continue
        parts = [p for p in _SEPARATOR.split(stripped, maxsplit=2) if p]
        if len(parts) < 2:
            skipped.append({"line": number, "text": stripped[:120]})
            continue
        name, raw = parts[0].strip().upper(), parts[1].strip()
        try:
            value = float(raw)
        except ValueError:
            skipped.append({"line": number, "text": stripped[:120]})
            continue
        parameters[name] = value
    return parameters, skipped


def _format(value):
    """Render a value the way the source file would.

    Integers keep no decimal point; floats keep their precision without
    exponent notation, because engineers match these against a GCS screen.
    """
    if value is None:
        return None
    if float(value).is_integer() and abs(value) < 1e15:
        return str(int(value))
    return f"{value:.10g}"


def group_of(name):
    """The parameter family, used to group a long diff into sections."""
    head = name.split("_", 1)[0]
    # Strip a trailing instance number so BATT2 groups with BATT, SERVO9 with
    # SERVO, EK3 stays EK3.
    stripped = re.sub(r"(?<=[A-Z])\d+$", "", head)
    return stripped or head


def compare(left, right, *, tolerance=0.0):
    """Compare two parameter sets.

    ``tolerance`` is a relative threshold: differences within it are reported as
    negligible rather than hidden, because a calibration value that drifted in
    the tenth decimal place is usually noise — but it is still a difference and
    the operator decides.
    """
    left_names, right_names = set(left), set(right)
    changed, only_left, only_right = [], [], []

    for name in sorted(left_names & right_names):
        a, b = left[name], right[name]
        if a == b:
            continue
        delta = b - a
        scale = max(abs(a), abs(b))
        relative = (abs(delta) / scale) if scale else 0.0
        changed.append({
            "name": name,
            "group": group_of(name),
            "left": _format(a),
            "right": _format(b),
            "delta": _format(delta),
            "relative": round(relative, 12),
            "negligible": bool(tolerance and relative <= tolerance),
        })

    for name in sorted(left_names - right_names):
        only_left.append({"name": name, "group": group_of(name),
                          "left": _format(left[name]), "right": None})
    for name in sorted(right_names - left_names):
        only_right.append({"name": name, "group": group_of(name),
                           "left": None, "right": _format(right[name])})

    identical = len(left_names & right_names) - len(changed)
    return {
        "changed": changed,
        "only_in_left": only_left,
        "only_in_right": only_right,
        "summary": {
            "left_total": len(left_names),
            "right_total": len(right_names),
            "identical": identical,
            "changed": len(changed),
            "only_in_left": len(only_left),
            "only_in_right": len(only_right),
            "negligible": sum(1 for c in changed if c["negligible"]),
            "groups_touched": sorted({c["group"] for c in changed}
                                     | {c["group"] for c in only_left}
                                     | {c["group"] for c in only_right}),
        },
    }
