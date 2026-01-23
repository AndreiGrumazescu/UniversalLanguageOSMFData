# Universal Language OSMF Data

Open-source language learning content for [Universal Language](https://github.com/AndreiGrumazescu/UniversalLanguage), structured using the [Open Study Model Framework (OSMF)](https://github.com/AndreiGrumazescu/OpenStudyModelFramework).

## Overview

This repository contains the language data that powers Universal Language:

- **Data Models & Documents** — Content schemas and the vocabulary/phrases implementing them
- **Relational Models & Documents** — Relationship schemas (hierarchy, user progress) and their instances
- **Pedagogy Models & Documents** — Study method schemas and configurations

All content follows OSMF specifications, enabling interoperability with any OSMF-compatible application.

## Repository Structure

Models and their implementing documents are co-located:

```
UL-Content/
├── data/                           # Data Models + Documents
│   ├── japanese-word/
│   │   ├── japanese-word.schema.json
│   │   └── documents/
│   │       ├── neko.json
│   │       ├── inu.json
│   │       └── ...
│   ├── japanese-phrase/
│   │   ├── japanese-phrase.schema.json
│   │   └── documents/
│   │       └── ...
│   └── [other-models]/
│
├── relational/                     # Relational Models + Documents
│   ├── hierarchy/
│   │   ├── hierarchy.schema.json
│   │   └── documents/
│   │       └── japanese-word-dependencies.json
│   └── user-progress/
│       ├── user-progress.schema.json
│       └── documents/              # (templates/examples only; actual user data lives in app DB)
│
├── pedagogy/                       # Pedagogy Models + Documents
│   ├── binary-srs-flashcard/
│   │   ├── binary-srs-flashcard.schema.json
│   │   └── documents/
│   │       ├── japanese-kanji-to-kana.json
│   │       └── ...
│   └── [other-pedagogies]/
│
└── validate.sh                     # Schema validation script
```

## Validation

Content is validated against OSMF meta-schemas before being accepted:

```bash
./validate.sh
```

Requires [check-jsonschema](https://github.com/python-jsonschema/check-jsonschema):
```bash
pip install check-jsonschema
```

## Contributing

Contributions are welcome. All submissions must:

1. Conform to the appropriate OSMF Model schema
2. Pass validation (`./validate.sh`)
3. Include accurate metadata (`$id`, `$schema`)

See the [OSMF specification](https://github.com/AndreiGrumazescu/OpenStudyModelFramework/blob/main/OSMF-def.md) for schema documentation.

## Deployment

Content from this repository is ingested into Universal Language's backend infrastructure. The deployment pipeline is maintained separately in the private application repository.

## License

This content is open-source. See [LICENSE](LICENSE) for details.
