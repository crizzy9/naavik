"""Tests for naavik_ops.lib.jsonl — atomic JSON / JSONL helpers."""

from __future__ import annotations

from naavik_ops.lib import jsonl


def test_read_write_json_roundtrip(tmp_path):
    path = tmp_path / "data.json"
    payload = {"a": 1, "nested": {"b": [1, 2, 3]}}
    jsonl.write_json(path, payload)
    assert jsonl.read_json(path) == payload


def test_write_json_no_partial_files(tmp_path):
    path = tmp_path / "data.json"
    jsonl.write_json(path, {"x": 1})
    # Sibling tempfiles must not be visible after write.
    leftovers = list(tmp_path.glob(".data.json.tmp.*"))
    assert leftovers == []


def test_write_json_creates_parent_dirs(tmp_path):
    path = tmp_path / "nested" / "dirs" / "data.json"
    jsonl.write_json(path, {"x": 1})
    assert path.exists()


def test_jsonl_append_and_read(tmp_path):
    path = tmp_path / "log.jsonl"
    jsonl.append_jsonl(path, {"id": 1})
    jsonl.append_jsonl(path, {"id": 2})
    items = jsonl.read_jsonl(path)
    assert items == [{"id": 1}, {"id": 2}]


def test_read_jsonl_missing_file(tmp_path):
    path = tmp_path / "absent.jsonl"
    assert jsonl.read_jsonl(path) == []


def test_read_jsonl_skips_blank_lines(tmp_path):
    path = tmp_path / "log.jsonl"
    path.write_text('{"a":1}\n\n{"b":2}\n', encoding="utf-8")
    assert jsonl.read_jsonl(path) == [{"a": 1}, {"b": 2}]
