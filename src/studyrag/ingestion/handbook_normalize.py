"""Parser: turns the extractor's raw field values into the final schema —
canonical codes, typed numbers, validated area/faculty — via plain mapping
dicts. Any raw value with no mapping entry is flagged, not guessed.
See studyrag-handbook-module-schema.md for the extractor/parser split.
"""

from __future__ import annotations

import re

# Explicit, not auto-slugified, to match the codes already documented in
# studyrag-handbook-module-schema.md's area enum.
_AREA_MAP = {
    "Theoretical Computer Science": "theoretical_cs",
    "Visual Computing & Interaction": "visual_computing_interaction",
    "Hardware/Software Systems": "hw_sw_systems",
    "AI & Data": "ai_data",
    "Software methods, tools": "software_methods_tools",
}

# Mapping tables below are built from a real survey of all 265 modules in
# the WiSe2026 English handbook (studyrag-decisions-log.md, 2026-10-14),
# not guessed. A raw value not present here is left unmapped and flagged,
# not silently coerced — see normalization_status/unmapped_raw_values.

_MODULE_TYPE_MAP = {
    "compulsory elective subject": "compulsory_elective",
    "elective subject": "elective",
    "compulsory subject": "compulsory",
    "module node": "module_node",  # Seminar/Praktikum/Kolloquium/Masterarbeit entries
}

_CYCLE_MAP = {
    "winter semester": "winter",
    "summer semester": "summer",
    "winter/summer semester": "both",
    "irregularly": "irregular",
}

_LEVEL_MAP = {
    "master": "master",
    "bachelor": "bachelor",
    "bachelor/master": "bachelor_master",
}

_LANGUAGE_MAP = {
    "english": "en",
    "german": "de",
    "german/english": "de_en",
}

_DURATION_MAP = {
    "one semester": 1,
    "two semesters": 2,
}

_SEMESTER_RAW_RE = re.compile(r"^(Winter|Summer) semester (\d{4})$")
_SEMESTER_PREFIX = {"Winter": "WiSe", "Summer": "SoSe"}


def _collapse_whitespace(value: str | None) -> str | None:
    """Collapses any wrapped-value whitespace (e.g. "Compulsory elective\\nsubject")
    to single spaces, for lookup purposes only — the raw file keeps the
    original text untouched."""
    if value is None:
        return None
    return " ".join(value.split())


def _slugify(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.strip().lower()).strip("_")


def _parse_number(value: str | None) -> float | None:
    """Handbook numbers use a German-locale comma decimal (e.g. "180,0")."""
    if value is None:
        return None
    return float(value.replace(",", "."))


def _parse_semester(value: str | None) -> tuple[str | None, str | None]:
    """"Winter semester 2016" -> "WiSe2016". Returns (canonical, raw-if-unmapped)."""
    if value is None:
        return None, None
    match = _SEMESTER_RAW_RE.match(value)
    if not match:
        return None, value
    prefix = _SEMESTER_PREFIX[match.group(1)]
    return f"{prefix}{match.group(2)}", None


def normalize_module(raw: dict) -> dict:
    """Apply the mapping tables to one raw module record, producing the
    final schema. Any raw value with no mapping entry is left ``null`` in
    its normalized field and recorded in ``unmapped_raw_values`` instead of
    being guessed.
    """
    final = dict(raw)  # start from the raw record; overwritten/removed below
    unmapped: list[dict] = []

    def resolve(raw_field: str, mapping: dict[str, str], final_field: str) -> None:
        raw_value = _collapse_whitespace(raw.get(raw_field))
        if raw_value is None:
            final[final_field] = None
            return
        canonical = mapping.get(raw_value.lower())
        if canonical is None:
            unmapped.append({"field": raw_field, "value": raw_value})
            final[final_field] = None
        else:
            final[final_field] = canonical
        final.pop(raw_field, None)

    resolve("module_type_raw", _MODULE_TYPE_MAP, "module_type")
    resolve("cycle_raw", _CYCLE_MAP, "cycle")
    resolve("level_raw", _LEVEL_MAP, "level")
    resolve("language_raw", _LANGUAGE_MAP, "language")

    duration_raw = raw.get("duration_raw")
    if duration_raw is None:
        final["duration_semesters"] = None
    elif duration_raw.lower() in _DURATION_MAP:
        final["duration_semesters"] = _DURATION_MAP[duration_raw.lower()]
    else:
        unmapped.append({"field": "duration_raw", "value": duration_raw})
        final["duration_semesters"] = None
    final.pop("duration_raw", None)

    for field in ("valid_from_raw", "valid_until_raw"):
        canonical_field = field.removesuffix("_raw")
        canonical, unmapped_value = _parse_semester(raw.get(field))
        final[canonical_field] = canonical
        if unmapped_value:
            unmapped.append({"field": field, "value": unmapped_value})
        final.pop(field, None)

    for field in ("ects", "contact_time_wsh", "total_hours", "contact_hours"):
        final[field] = _parse_number(raw.get(field))

    area_raw = raw.get("area_raw")
    if area_raw is None:
        final["area"] = None
    else:
        canonical_area = _AREA_MAP.get(area_raw)
        if canonical_area is None:
            unmapped.append({"field": "area_raw", "value": area_raw})
        final["area"] = canonical_area
    final.pop("area_raw", None)

    faculty_raw = raw.get("contributing_faculty_raw")
    final["contributing_faculty"] = _slugify(faculty_raw) if faculty_raw else None
    final.pop("contributing_faculty_raw", None)

    final["translation_source"] = "official"
    final["normalization_status"] = "needs_mapping" if unmapped else "ok"
    final["unmapped_raw_values"] = unmapped
    final.pop("_missing_labels", None)

    return final
