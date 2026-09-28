"""Display metadata for the eight bundled hospital samples, never for user text."""
import json
from functools import lru_cache
from pathlib import Path

DISPLAY_FIELDS = {"title", "condition", "content", "source_name", "filename"}


@lru_cache(maxsize=1)
def hospital_samples():
    return json.loads((Path(__file__).parent / "hospital_samples" / "manifest.json").read_text(encoding="utf-8"))


def sample_display(external_id, values):
    sample = next((row for row in hospital_samples() if row["external_id"] == external_id), None)
    if not sample:
        return {}
    translations = sample.get("display_zh", {})
    # Never replace a patient's edited classification/topic or other free text.
    result = {key: sample[key] for key in DISPLAY_FIELDS if key in values and key in sample
              and values[key] in (sample[key], translations.get(key))}
    if values.get("source_name") == "示例医院（模拟）":
        result["source_name"] = sample["source_name"]
    return result


def record_display(record, values):
    from .record_models import ProviderImportReference
    reference = ProviderImportReference.query.filter_by(record_id=record.id, user_id=record.user_id, provider="demo_hospital").first()
    return sample_display(reference.external_id, values) if reference else {}


def with_record_display(record, values):
    display = record_display(record, values)
    return {**values, **({"sample_display": display} if display else {})}
