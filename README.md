# Universal Language OSMF Data

Open-source language learning content for [Universal Language](https://github.com/AndreiGrumazescu/UniversalLanguage), structured using the [Open Study Model Framework (OSMF)](https://github.com/AndreiGrumazescu/OpenStudyModelFramework).

## Overview

This repository contains the language data that powers Universal Language:

- **Data Models & Documents** — Content schemas and the vocabulary/phrases implementing them
- **Relational Models & Documents** — Relationship schemas (hierarchy, user progress) and their instances
- **Pedagogy Models & Documents** — Study method schemas and configurations

All content follows OSMF specifications, enabling interoperability with any OSMF-compatible application.

## Repository Structure

```
UL-Content/
├── {language}/
│   ├── data/
│   │   └── {model}/
│   │       ├── {language}-{model}.schema.json   # OSMF Model schema
│   │       └── documents/                       # OSMF Documents
│   │           └── *.json
│   ├── docs/                                    # Language-specific documentation
│   │   └── reports/                             # Generated analysis reports
│   ├── scripts/
│   │   ├── lib/                                 # Shared utilities
│   │   ├── adapters/                            # Source dataset parsers
│   │   ├── analyzers/                           # Domain analysis scripts
│   │   ├── generators/                          # OSMF document generators
│   │   └── source/                              # External source datasets
│   └── tests/                                   # Unit, integration, validation tests
```

## Scripts

Each language directory contains scripts organized into four categories:

| Category | Role | Output |
|----------|------|--------|
| **Adapters** | Reusable parsing/querying of source datasets | Python data structures |
| **Analyzers** | Scan any domain (source or product), collect metrics | Reports and visualizations |
| **Generators** | Create OSMF documents from source datasets (must be idempotent) | OSMF documents (JSON files) |
| **Lib** | Shared utilities (normalizers, paths, I/O) | — |

All generators must be **idempotent**: running them multiple times produces the same result.

See the language-specific documentation for details on individual scripts:
- [Japanese Content](japanese/docs/japanese_grapheme.md)

## Testing

Each language directory contains a `tests/` directory with test suites that validate content integrity. Tests minimally cover:

- **Schema validation** — Every document is validated against its model's JSON Schema (data models use the full nested schema; relational models validate structural conformance)
- **JSON integrity** — All document files parse as valid JSON
- **`$id` presence** — Every document has a `$id` field

Run tests from a language directory:

```bash
cd japanese
pytest tests/ -v
```

Requires `pytest` and `jsonschema`:
```bash
pip install pytest jsonschema
```

## Contributing

Contributions are welcome. All submissions must:

1. Conform to the appropriate OSMF Model schema
2. Pass all tests (`pytest tests/ -v`)
3. Include accurate metadata (`$id`, `$schema`)

See the [OSMF specification](https://github.com/AndreiGrumazescu/OpenStudyModelFramework/blob/main/OSMF-def.md) for schema documentation.

## Deployment

Content from this repository is ingested into Universal Language's backend infrastructure. The deployment pipeline is maintained separately in the private application repository.

## License

This content is open-source. See [LICENSE](LICENSE) for details.
