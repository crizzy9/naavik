"""OpenAI strict-schema transform regression tests.

OpenAI `strict: true` json_schema mode rejects `$ref` nodes carrying
sibling keywords and rejects `default` anywhere. Pydantic emits exactly
that shape for enum fields with defaults (`{"$ref": ..., "default": ...}`),
which broke job enrichment live:

    Invalid schema for response_format 'JobExtraction':
    context=('properties', 'remote_policy'),
    $ref cannot have keywords {'default'}.

These tests pin `_to_strict_schema` against the two real production
schemas (JobExtraction, ExtractedResume) plus a synthetic worst case.
"""

from __future__ import annotations

import pytest
from pydantic import BaseModel, Field

from llm.openai import OpenAIProvider
from llm.prompts.extract_job import JobExtraction
from llm.prompts.extract_resume import ExtractedResume
from models.enums import RemotePolicy

pytestmark = pytest.mark.uses_sample_data_shims


def _assert_strict(node: object, path: str = "$") -> None:
    """Walk a transformed schema and assert every strict-mode invariant."""
    if isinstance(node, dict):
        assert "default" not in node, f"{path}: 'default' survived the transform"
        if "$ref" in node:
            assert set(node) == {"$ref"}, f"{path}: $ref has siblings {set(node) - {'$ref'}}"
        if node.get("type") == "object" or "properties" in node:
            props = node.get("properties", {})
            assert node.get("additionalProperties") is False, (
                f"{path}: object missing additionalProperties=false"
            )
            assert node.get("required") == list(props.keys()), (
                f"{path}: required must list every property"
            )
        for key, value in node.items():
            _assert_strict(value, f"{path}.{key}")
    elif isinstance(node, list):
        for i, value in enumerate(node):
            _assert_strict(value, f"{path}[{i}]")


def test_job_extraction_schema_is_strict_legal():
    schema = JobExtraction.model_json_schema()
    # Pre-condition: the raw Pydantic emission actually contains the
    # offending shape — otherwise this test would silently pin nothing.
    raw_remote = schema["properties"]["remote_policy"]
    assert "$ref" in raw_remote and "default" in raw_remote

    OpenAIProvider._to_strict_schema(schema)
    _assert_strict(schema)

    # Stripping the default leaves a bare $ref (strict-legal) and the enum
    # definition survives in $defs so the model can still see the values.
    remote = schema["properties"]["remote_policy"]
    assert remote == {"$ref": "#/$defs/RemotePolicy"}
    assert set(schema["$defs"]["RemotePolicy"]["enum"]) == {p.value for p in RemotePolicy}


def test_job_extraction_optional_enum_union_is_strict_legal():
    schema = JobExtraction.model_json_schema()
    OpenAIProvider._to_strict_schema(schema)
    seniority = schema["properties"]["seniority_level"]
    assert "default" not in seniority
    assert "anyOf" in seniority


def test_extracted_resume_schema_is_strict_legal():
    schema = ExtractedResume.model_json_schema()
    OpenAIProvider._to_strict_schema(schema)
    _assert_strict(schema)


def test_transform_is_idempotent():
    once = JobExtraction.model_json_schema()
    OpenAIProvider._to_strict_schema(once)
    twice = JobExtraction.model_json_schema()
    OpenAIProvider._to_strict_schema(twice)
    OpenAIProvider._to_strict_schema(twice)
    assert once == twice


def test_synthetic_nested_ref_with_default_inlines():
    class Inner(BaseModel):
        mode: RemotePolicy = RemotePolicy.UNKNOWN

    class Outer(BaseModel):
        inner: Inner = Field(default_factory=Inner)
        note: str | None = None

    schema = Outer.model_json_schema()
    OpenAIProvider._to_strict_schema(schema)
    _assert_strict(schema)
    # default_factory sibling stripped → bare $ref survives (strict-legal).
    assert schema["properties"]["inner"] == {"$ref": "#/$defs/Inner"}
    assert schema["$defs"]["Inner"]["properties"]["mode"] == {"$ref": "#/$defs/RemotePolicy"}


def test_ref_with_description_sibling_inlines():
    schema = {
        "$defs": {"Mode": {"enum": ["a", "b"], "type": "string"}},
        "type": "object",
        "properties": {"m": {"$ref": "#/$defs/Mode", "description": "pick one", "default": "a"}},
    }
    OpenAIProvider._to_strict_schema(schema)
    _assert_strict(schema)
    m = schema["properties"]["m"]
    assert m["enum"] == ["a", "b"] and m["description"] == "pick one" and "$ref" not in m


def test_unresolvable_ref_with_siblings_collapses_to_bare_ref():
    schema = {
        "type": "object",
        "properties": {"x": {"$ref": "#/definitions/External", "default": 1}},
    }
    OpenAIProvider._to_strict_schema(schema)
    assert schema["properties"]["x"] == {"$ref": "#/definitions/External"}
