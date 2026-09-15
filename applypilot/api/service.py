"""Profile parsing, reconciliation, and evidence helpers for the local API."""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from typing import Any

from applypilot.api.contracts import Conflict, FactEvidence, SourceLocation
from applypilot.domain.profile import CandidateProfile


def is_empty(value: Any) -> bool:
    return value is None or value == "" or value == [] or value == {}


def _record_key(record: Mapping[str, Any], collection: str) -> tuple[str, ...] | None:
    if record.get("id"):
        return ("id", str(record["id"]))
    fields = {
        "education": ("school_name", "start_date"),
        "experiences": ("org_name", "start_date"),
        "projects": ("project_name", "start_date"),
        "awards": ("name", "date"),
        "publications": ("title", "venue"),
        "certificates": ("name", "date"),
        "campus_practices": ("name", "start_date"),
    }.get(collection, ())
    values = tuple(str(record.get(field) or "") for field in fields)
    return ("composite", *values) if any(values) else None


def _merge_records(base: list[Any], incoming: list[Any], path: str, conflicts: list[Conflict]) -> list[Any]:
    merged = deepcopy(base)
    collection = path.rsplit("/", 1)[-1]
    positions: dict[tuple[str, ...], int] = {}
    for index, item in enumerate(merged):
        if isinstance(item, Mapping):
            key = _record_key(item, collection)
            if key:
                positions[key] = index
    for item in incoming:
        if not isinstance(item, Mapping):
            if item not in merged:
                merged.append(deepcopy(item))
            continue
        key = _record_key(item, collection)
        if key is not None and key in positions:
            index = positions[key]
            merged[index] = _merge_mapping(merged[index], item, f"{path}/{index}", conflicts)
        else:
            positions[key] = len(merged) if key is not None else len(merged)
            merged.append(deepcopy(item))
    return merged


def _merge_mapping(base: Mapping[str, Any], incoming: Mapping[str, Any], path: str, conflicts: list[Conflict]) -> dict[str, Any]:
    merged = deepcopy(dict(base))
    for key, incoming_value in incoming.items():
        child_path = f"{path}/{key}" if path else f"/{key}"
        if key not in merged or is_empty(merged[key]):
            merged[key] = deepcopy(incoming_value)
        elif isinstance(merged[key], Mapping) and isinstance(incoming_value, Mapping):
            merged[key] = _merge_mapping(merged[key], incoming_value, child_path, conflicts)
        elif isinstance(merged[key], list) and isinstance(incoming_value, list):
            merged[key] = _merge_records(merged[key], incoming_value, child_path, conflicts)
        elif not is_empty(incoming_value) and merged[key] != incoming_value:
            conflicts.append(Conflict(path=child_path, existing_value=merged[key], incoming_value=incoming_value, reason="已核实档案优先，未覆盖现有值"))
    return merged


def reconcile_profiles(base: CandidateProfile, incoming: CandidateProfile) -> tuple[CandidateProfile, list[Conflict]]:
    conflicts: list[Conflict] = []
    base_data = base.model_dump(mode="json", exclude_none=True)
    incoming_data = incoming.model_dump(mode="json", exclude_none=True)
    merged = _merge_mapping(base_data, incoming_data, "", conflicts)
    merged["profile_id"] = base.profile_id
    return CandidateProfile.model_validate(merged), conflicts


def _walk_facts(value: Any, path: str, source_name: str, text: str, output: list[FactEvidence]) -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            _walk_facts(child, f"{path}/{key}", source_name, text, output)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _walk_facts(child, f"{path}/{index}", source_name, text, output)
    elif value is not None and value != "":
        rendered = str(value)
        found = rendered in text if text else False
        output.append(FactEvidence(path=path, value=value, source=SourceLocation(document=source_name, page=1, quote=rendered if found else None), confidence=1.0 if found else 0.75, needs_review=not found))


def profile_facts(profile: CandidateProfile, source_name: str, text: str = "") -> list[FactEvidence]:
    facts: list[FactEvidence] = []
    _walk_facts(profile.model_dump(mode="json", exclude_none=True), "", source_name, text, facts)
    return facts
