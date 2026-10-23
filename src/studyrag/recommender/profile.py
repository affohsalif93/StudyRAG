"""The student profile the quiz produces. Stored client-side, not in
SQLite -- no login, just a small file on the student's own device.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from pydantic import BaseModel, Field


class Skill(BaseModel):
    level: int = Field(ge=0, le=3)  # 0=never seen, 1=know basics, 2=comfortable, 3=strong
    weak: bool = False


class Target(BaseModel):
    job_title: str
    track_id: str
    sector: str  # industry | startup | research | phd
    certainty: str  # exploring | leaning | decided


class WorkStyle(BaseModel):
    theory_vs_practice: int = Field(ge=1, le=5)
    exam_formats_avoid: list[str] = Field(default_factory=list)


class ProgressEntry(BaseModel):
    module_id: str
    grade: float | None = None


class CurrentEntry(BaseModel):
    module_id: str
    exam_date: str | None = None


class Progress(BaseModel):
    passed: list[ProgressEntry] = Field(default_factory=list)
    current: list[CurrentEntry] = Field(default_factory=list)
    failed_or_not_taken: list[ProgressEntry] = Field(default_factory=list)


class Constraints(BaseModel):
    cp_missing_total: int | None = None
    language: list[str] = Field(default_factory=list)
    semesters_left: int | None = None
    next_semester: str | None = None
    exam_formats_avoid: list[str] = Field(default_factory=list)


class Profile(BaseModel):
    profile_version: int = 1
    program: str = "MSInf_2023"
    interests: list[str] = Field(default_factory=list)
    sub_areas: list[str] = Field(default_factory=list)
    work_style: WorkStyle | None = None
    targets: list[Target] = Field(default_factory=list)
    skills: dict[str, Skill] = Field(default_factory=dict)
    progress: Progress = Field(default_factory=Progress)
    constraints: Constraints | None = None
    created: str = Field(default_factory=lambda: date.today().isoformat())
    updated: str = Field(default_factory=lambda: date.today().isoformat())


def save_profile(profile: Profile, path: Path) -> None:
    profile.updated = date.today().isoformat()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(profile.model_dump_json(indent=2), encoding="utf-8")


def load_profile(path: Path) -> Profile | None:
    if not path.exists():
        return None
    return Profile.model_validate(json.loads(path.read_text(encoding="utf-8")))
