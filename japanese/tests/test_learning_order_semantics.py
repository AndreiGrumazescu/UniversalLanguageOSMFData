#!/usr/bin/env python3
"""
test_learning_order_semantics.py

Semantic validation rules for learning-order relational documents.
These checks intentionally enforce constraints that are not fully expressible
through JSON Schema alone (for example unique contiguous positions).
"""

import re

import pytest


TRACK_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")


def validate_learning_order_document(
    document: dict,
    *,
    intended_default_track: bool = False,
) -> None:
    """Validate semantic rules for a learning-order document."""
    data = document.get("data")
    if not isinstance(data, dict):
        raise ValueError("data must be an object")

    content_type = data.get("contentType")
    if not isinstance(content_type, str) or not content_type.strip():
        raise ValueError("data.contentType is required")

    track_id = data.get("trackId")
    if not isinstance(track_id, str) or not TRACK_ID_PATTERN.match(track_id):
        raise ValueError(
            "data.trackId is required and must match ^[a-z0-9][a-z0-9-]{0,63}$"
        )

    if intended_default_track and track_id != "default":
        raise ValueError(
            "documents intended as the default track must set data.trackId to 'default'"
        )

    many = document.get("many")
    if not isinstance(many, list) or not many:
        raise ValueError("many must be a non-empty array")

    item_ids: list[str] = []
    positions: list[int] = []
    for index, entry in enumerate(many):
        if not isinstance(entry, dict):
            raise ValueError(f"many[{index}] must be an object")

        connectors = entry.get("connectors")
        if not isinstance(connectors, dict):
            raise ValueError(f"many[{index}].connectors must be an object")

        item = connectors.get("item")
        if not isinstance(item, dict):
            raise ValueError(f"many[{index}].connectors.item must be an object")

        item_id = item.get("$id")
        if not isinstance(item_id, str) or not item_id.strip():
            raise ValueError(f"many[{index}].connectors.item.$id is required")
        item_ids.append(item_id)

        entry_data = entry.get("data")
        if not isinstance(entry_data, dict):
            raise ValueError(f"many[{index}].data must be an object")

        position = entry_data.get("position")
        if isinstance(position, bool) or not isinstance(position, int) or position < 0:
            raise ValueError(f"many[{index}].data.position must be an integer >= 0")
        positions.append(position)

    if len(set(item_ids)) != len(item_ids):
        raise ValueError("many entries cannot repeat the same connectors.item.$id")

    if len(set(positions)) != len(positions):
        raise ValueError("many entries cannot repeat the same data.position value")

    expected_positions = list(range(len(positions)))
    if sorted(positions) != expected_positions:
        raise ValueError("positions must be contiguous and start at 0")


def _valid_document_fixture() -> dict:
    return {
        "$id": "learning-order:grapheme:default",
        "data": {
            "contentType": "grapheme",
            "trackId": "default",
            "trackName": "Default Grapheme Order",
        },
        "many": [
            {
                "connectors": {"item": {"$id": "grapheme:U+4E00"}},
                "data": {"position": 0},
            },
            {
                "connectors": {"item": {"$id": "grapheme:U+4E8C"}},
                "data": {"position": 1},
            },
            {
                "connectors": {"item": {"$id": "grapheme:U+4E09"}},
                "data": {"position": 2},
            },
        ],
    }


def test_valid_fixture_passes() -> None:
    document = _valid_document_fixture()
    validate_learning_order_document(document, intended_default_track=True)


def test_duplicate_position_fails() -> None:
    document = _valid_document_fixture()
    document["many"][2]["data"]["position"] = 1
    with pytest.raises(ValueError, match="repeat the same data.position"):
        validate_learning_order_document(document)


def test_gapped_position_fails() -> None:
    document = _valid_document_fixture()
    document["many"][2]["data"]["position"] = 4
    with pytest.raises(ValueError, match="contiguous and start at 0"):
        validate_learning_order_document(document)


def test_duplicate_item_id_fails() -> None:
    document = _valid_document_fixture()
    document["many"][2]["connectors"]["item"]["$id"] = "grapheme:U+4E8C"
    with pytest.raises(ValueError, match="cannot repeat the same connectors.item"):
        validate_learning_order_document(document)


def test_missing_required_data_fields_fails() -> None:
    document = _valid_document_fixture()
    del document["data"]["contentType"]
    with pytest.raises(ValueError, match="data.contentType is required"):
        validate_learning_order_document(document)

    document = _valid_document_fixture()
    del document["data"]["trackId"]
    with pytest.raises(ValueError, match="data.trackId is required"):
        validate_learning_order_document(document)


def test_default_track_requires_default_track_id() -> None:
    document = _valid_document_fixture()
    document["data"]["trackId"] = "n5-core"
    with pytest.raises(ValueError, match="default track"):
        validate_learning_order_document(document, intended_default_track=True)

