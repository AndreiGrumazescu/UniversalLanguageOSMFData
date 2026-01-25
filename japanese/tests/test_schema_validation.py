#!/usr/bin/env python3
"""
test_schema_validation.py

Tests that all OSMF documents in the repository validate against their
corresponding JSON schemas.

Supports two schema types:
- Data models: Have a nested `schema` property with the document JSON Schema
- Relational models: Have `connectors`, `many` definitions that describe relationships
"""

import json
import sys
from pathlib import Path
from typing import Any

import pytest

# Add parent directories to path for lib imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from lib.paths import DATA_DIR

# Try to import jsonschema - required for validation
try:
    from jsonschema import Draft7Validator, ValidationError
    from jsonschema.validators import validator_for
except ImportError:
    pytest.skip("jsonschema not installed", allow_module_level=True)


# ---------------------------------------------------------------------------
# Schema Discovery and Loading
# ---------------------------------------------------------------------------

def discover_models() -> list[tuple[Path, Path]]:
    """
    Discover all model directories and their schema files.

    Returns:
        List of (schema_path, documents_dir) tuples
    """
    models = []

    if not DATA_DIR.exists():
        return models

    for model_dir in DATA_DIR.iterdir():
        if not model_dir.is_dir():
            continue

        # Find schema file (*.schema.json)
        schema_files = list(model_dir.glob("*.schema.json"))
        if not schema_files:
            continue

        schema_path = schema_files[0]  # Take first if multiple
        documents_dir = model_dir / "documents"

        if documents_dir.exists() and documents_dir.is_dir():
            models.append((schema_path, documents_dir))

    return models


def load_json(path: Path) -> dict[str, Any]:
    """Load JSON file and return parsed content."""
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Schema Type Detection and Validation Schema Construction
# ---------------------------------------------------------------------------

def is_data_model_schema(schema: dict) -> bool:
    """Check if schema is a data model (has nested 'schema' property)."""
    return "schema" in schema and isinstance(schema["schema"], dict)


def is_relational_model_schema(schema: dict) -> bool:
    """Check if schema is a relational model (has 'connectors' property)."""
    return "connectors" in schema


def build_data_model_validator(schema: dict) -> Draft7Validator:
    """
    Build validator for data model documents.

    Data models have the actual JSON Schema nested in the 'schema' property.
    """
    document_schema = schema["schema"]
    validator_cls = validator_for(document_schema)
    return validator_cls(document_schema)


def build_relational_model_validator(schema: dict) -> Draft7Validator:
    """
    Build validator for relational model documents.

    Relational models define connectors and optional 'many' relationships.
    We construct a JSON Schema that validates the document structure.
    """
    # Extract connector names from the model
    connector_names = list(schema.get("connectors", {}).keys())

    # Build connector criteria schemas
    connector_properties = {}
    for name, connector_def in schema.get("connectors", {}).items():
        criteria = connector_def.get("criteria", {})
        # Build schema for this connector reference
        connector_properties[name] = {
            "type": "object",
            "properties": {
                "$id": {"type": "string"}
            },
            "required": ["$id"]
        }

    # Build the document schema
    document_schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "$id": {"type": "string"}
        },
        "required": ["$id"]
    }

    # Add top-level connectors if defined
    if connector_names:
        document_schema["properties"]["connectors"] = {
            "type": "object",
            "properties": connector_properties
        }

    # Add 'many' array if defined
    if "many" in schema:
        many_def = schema["many"]

        # Build item schema from itemConnectors
        item_schema: dict[str, Any] = {
            "type": "object",
            "properties": {
                "connectors": {
                    "type": "object"
                }
            }
        }

        # Add itemData properties if defined
        if "itemData" in many_def:
            item_schema["properties"]["data"] = {"type": "object"}

        document_schema["properties"]["many"] = {
            "type": "array",
            "items": item_schema
        }

        # Handle minItems constraint
        if isinstance(many_def, dict) and "minItems" in many_def:
            document_schema["properties"]["many"]["minItems"] = many_def["minItems"]

    # Add optional 'name' field (common in relational documents)
    document_schema["properties"]["name"] = {"type": "string"}

    validator_cls = validator_for(document_schema)
    return validator_cls(document_schema)


def build_validator(schema: dict) -> Draft7Validator:
    """Build appropriate validator based on schema type."""
    if is_data_model_schema(schema):
        return build_data_model_validator(schema)
    elif is_relational_model_schema(schema):
        return build_relational_model_validator(schema)
    else:
        # Fallback: minimal validation (just require $id)
        minimal_schema = {
            "type": "object",
            "properties": {
                "$id": {"type": "string"}
            },
            "required": ["$id"]
        }
        return Draft7Validator(minimal_schema)


# ---------------------------------------------------------------------------
# Test Collection
# ---------------------------------------------------------------------------

def collect_test_cases() -> list[tuple[str, Path, Path]]:
    """
    Collect all (model_name, schema_path, document_path) tuples for testing.
    """
    test_cases = []
    models = discover_models()

    for schema_path, documents_dir in models:
        model_name = schema_path.stem.replace(".schema", "")

        for doc_path in documents_dir.glob("*.json"):
            test_cases.append((model_name, schema_path, doc_path))

    return test_cases


# Collect test cases once at module load
TEST_CASES = collect_test_cases()

# Generate test IDs from document filenames
TEST_IDS = [
    f"{model_name}/{doc_path.stem}"
    for model_name, _, doc_path in TEST_CASES
]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("model_name,schema_path,doc_path", TEST_CASES, ids=TEST_IDS)
def test_document_validates_against_schema(
    model_name: str,
    schema_path: Path,
    doc_path: Path
):
    """Test that each document validates against its model schema."""
    # Load schema and document
    schema = load_json(schema_path)
    document = load_json(doc_path)

    # Build validator
    validator = build_validator(schema)

    # Collect all validation errors
    errors = list(validator.iter_errors(document))

    if errors:
        error_messages = []
        for error in errors:
            path = ".".join(str(p) for p in error.absolute_path) or "(root)"
            error_messages.append(f"  - {path}: {error.message}")

        error_report = "\n".join(error_messages)
        pytest.fail(
            f"Document {doc_path.name} failed validation:\n{error_report}"
        )


def test_all_schemas_have_documents():
    """Report which schemas have documents (informational)."""
    models = discover_models()
    empty_schemas = []

    for schema_path, documents_dir in models:
        doc_count = len(list(documents_dir.glob("*.json")))
        if doc_count == 0:
            empty_schemas.append(schema_path.name)

    if empty_schemas:
        pytest.skip(
            f"Schemas without documents (expected during development): "
            f"{', '.join(empty_schemas)}"
        )


def test_all_documents_are_valid_json():
    """Test that all document files are valid JSON."""
    models = discover_models()

    for schema_path, documents_dir in models:
        for doc_path in documents_dir.glob("*.json"):
            try:
                load_json(doc_path)
            except json.JSONDecodeError as e:
                pytest.fail(f"Invalid JSON in {doc_path}: {e}")


def test_all_documents_have_id():
    """Test that all documents have a $id field."""
    models = discover_models()

    for schema_path, documents_dir in models:
        for doc_path in documents_dir.glob("*.json"):
            doc = load_json(doc_path)
            assert "$id" in doc, f"Document {doc_path} missing $id field"


# ---------------------------------------------------------------------------
# Unicode Consistency
# ---------------------------------------------------------------------------

def collect_symbol_unicode_pairs(
    obj: Any, path: str = ""
) -> list[tuple[str, str, str]]:
    """
    Recursively walk a JSON object and collect all co-located
    (symbol, unicode) pairs.

    Returns list of (json_path, symbol_value, unicode_value) tuples.
    """
    pairs = []
    if isinstance(obj, dict):
        if "symbol" in obj and "unicode" in obj:
            pairs.append((path or "(root)", obj["symbol"], obj["unicode"]))
        for key, value in obj.items():
            child_path = f"{path}.{key}" if path else key
            pairs.extend(collect_symbol_unicode_pairs(value, child_path))
    elif isinstance(obj, list):
        for i, item in enumerate(obj):
            pairs.extend(collect_symbol_unicode_pairs(item, f"{path}[{i}]"))
    return pairs


def symbol_to_codepoint_str(symbol: str) -> str:
    """Convert a single-character symbol to 'U+XXXX' format."""
    if len(symbol) != 1:
        return None
    cp = ord(symbol)
    if cp > 0xFFFF:
        return f"U+{cp:05X}"
    return f"U+{cp:04X}"


SYMBOL_UNICODE_CASES = []
SYMBOL_UNICODE_IDS = []

for _model_name, _schema_path, _doc_path in TEST_CASES:
    _doc = load_json(_doc_path)
    for _json_path, _symbol, _unicode in collect_symbol_unicode_pairs(_doc):
        SYMBOL_UNICODE_CASES.append((_doc_path, _json_path, _symbol, _unicode))
        SYMBOL_UNICODE_IDS.append(f"{_doc_path.stem}:{_json_path}")


@pytest.mark.parametrize(
    "doc_path,json_path,symbol,declared_unicode",
    SYMBOL_UNICODE_CASES,
    ids=SYMBOL_UNICODE_IDS,
)
def test_symbol_matches_declared_unicode(
    doc_path: Path, json_path: str, symbol: str, declared_unicode: str
):
    """Test that every symbol character has the codepoint its unicode field claims."""
    if len(symbol) != 1:
        pytest.fail(
            f"{doc_path.name} {json_path}: symbol {symbol!r} is not a single character"
        )

    actual = symbol_to_codepoint_str(symbol)
    assert actual == declared_unicode, (
        f"{doc_path.name} {json_path}: symbol {symbol!r} has codepoint {actual}, "
        f"but unicode field declares {declared_unicode}"
    )


# ---------------------------------------------------------------------------
# Summary Statistics (for verbose output)
# ---------------------------------------------------------------------------

def test_print_summary():
    """Print summary of discovered models and documents."""
    models = discover_models()

    print("\n" + "=" * 60)
    print("OSMF Schema Validation Summary")
    print("=" * 60)

    total_docs = 0
    for schema_path, documents_dir in models:
        model_name = schema_path.stem.replace(".schema", "")
        doc_count = len(list(documents_dir.glob("*.json")))
        total_docs += doc_count

        schema = load_json(schema_path)
        schema_type = "data" if is_data_model_schema(schema) else "relational"
        print(f"  {model_name}: {doc_count} documents ({schema_type} model)")

    print("-" * 60)
    print(f"  Total: {len(models)} models, {total_docs} documents")
    print("=" * 60)
