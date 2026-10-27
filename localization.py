"""Shared German, English and Spanish message catalog for API and browser."""
import json
from pathlib import Path
import re

CATALOG = json.loads((Path(__file__).parent / "static" / "locales.json").read_text(encoding="utf-8"))
EXACT = {row[0]: row for row in CATALOG}
PATTERNS = []
for row in CATALOG:
    if "{" in row[0]:
        names = re.findall(r"\{(\w+)\}", row[0])
        regex = re.escape(row[0])
        for name in names:
            regex = regex.replace(re.escape("{" + name + "}"), f"(?P<{name}>.+?)", 1)
        PATTERNS.append((re.compile("^" + regex + "$", re.S), row))


def language(header):
    first = (header or "de").split(",")[0].split(";")[0].strip().lower().split("-")[0]
    return first if first in ("de", "en", "es") else "de"


def text(value, lang):
    if not isinstance(value, str) or lang == "de":
        return value
    index = 1 if lang == "en" else 2
    if value in EXACT:
        return EXACT[value][index]
    for regex, row in PATTERNS:
        match = regex.fullmatch(value)
        if match:
            translated = row[index]
            for key, part in match.groupdict().items():
                translated = translated.replace("{" + key + "}", part)
            return translated
    return value


def payload(body, lang):
    """Translate display messages, never filenames, log evidence or identifiers."""
    def walk(value, key="", action=""):
        if isinstance(value, dict):
            action = value.get("action", action)
            return {k: walk(v, k, action) for k, v in value.items()}
        if isinstance(value, list):
            return [walk(v, key, action) for v in value]
        if isinstance(value, str) and (key in ("note", "error", "progress", "findings") or key in ("name", "value") and action in ("system", "log", "checklist")):
            return text(value, lang)
        return value
    return walk(body)
