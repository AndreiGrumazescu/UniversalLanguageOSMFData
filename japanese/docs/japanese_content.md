# Japanese Content

Documentation for the Japanese language content in Universal Language, structured using the Open Study Model Framework (OSMF).

## Data Locations

### Data Models (content)

| Model | Schema | Documents | Status |
|-------|--------|-----------|--------|
| Grapheme | `data/grapheme/japanese-grapheme.schema.json` | `data/grapheme/documents/` | Populated |
| Kanji | `data/kanji/japanese-kanji.schema.json` | `data/kanji/documents/` | Populated |
| Kana | `data/kana/japanese-kana.schema.json` | `data/kana/documents/` | Schema only |
| Vocabulary | `data/vocabulary/japanese-vocabulary.schema.json` | `data/vocabulary/documents/` | Schema only |
| Phrase | `data/phrase/japanese-phrase.schema.json` | `data/phrase/documents/` | Schema only |
| Grammar | `data/grammar/japanese-grammar.schema.json` | `data/grammar/documents/` | Schema only |

### Relational Models (relationships)

| Model | Schema | Documents | Status |
|-------|--------|-----------|--------|
| Grapheme Dependency | `data/grapheme-dependency/japanese-grapheme-dependency.schema.json` | `data/grapheme-dependency/documents/` | Populated |
| Grapheme Variant Group | `data/grapheme-variant-group/japanese-grapheme-variant-group.schema.json` | `data/grapheme-variant-group/documents/` | Populated |
| Learning Order | `../../shared-models/learning-order.schema.json` | `data/learning-order/documents/` | Populated |
| Kanji Grapheme Dependency | `data/kanji-grapheme-dependency/japanese-kanji-grapheme-dependency.schema.json` | `data/kanji-grapheme-dependency/documents/` | Populated |
| Kanji Dependency | `data/kanji-dependency/japanese-kanji-dependency.schema.json` | `data/kanji-dependency/documents/` | Populated |

---

## Graphemes

### Concept

Graphemes are the fundamental visual building blocks for learning kanji. Rather than memorizing each kanji as an atomic unit, learners recognize familiar components that recur across many characters.

Graphemes include:

- **Kangxi Radicals** — the 214 traditional radicals used for kanji classification
- **Positional Variants** — radicals that change form based on position (e.g., 水 → 氵 when on the left)
- **Sub-kanji Morphemes** — components that appear across multiple kanji but aren't standalone characters
- **Kanji as Primitive** — kanji that frequently serve as building blocks for other kanji

### Variants

Some graphemes have visually similar alternate forms. These are tracked in two ways:

- **Embedded variants**: stored in the `variants` array of a grapheme document. These are forms close enough to be treated as the same grapheme during decomposition (e.g., ⻌/⻍/⻎ are all treated as 辶).
- **Non-embedded variants**: separate grapheme documents grouped via Grapheme Variant Groups (see below). These represent the same concept but are visually distinct enough that they are represented in the data model separately (e.g., 水 and 氵).

### Model & Document Format

**Model:** `data/grapheme/japanese-grapheme.schema.json`

**Example document:**
```json
{
  "$id": "grapheme:U+5DDD",
  "unicode": "U+5DDD",
  "symbol": "川",
  "name": "River",
  "strokeCount": 3,
  "variants": [
    { "unicode": "U+5DDB", "symbol": "巛" }
  ]
}
```

---

## Grapheme Dependencies

### Concept

Dependency relationships express how graphemes are composed of other graphemes. This forms a directed graph used for determining learning order — a grapheme's components should be learned before the grapheme itself.

Decomposition uses CHISE IDS (primary) and KanjiVG (fallback) data, following variant chains to find all grapheme components. See the generator script for algorithm details.

### Model & Document Format

**Model:** `data/grapheme-dependency/japanese-grapheme-dependency.schema.json`

This is an OSMF Relational Model with:
- `parent` connector — the grapheme being decomposed
- `component` connector — a grapheme the parent is composed of

Uses the `many` pattern to express multiple components per parent.

**Example document:** 林 (Forest) = 木 (Tree) + 木 (Tree)
```json
{
  "$id": "grapheme-dep:U+6797",
  "connectors": { "parent": { "$id": "grapheme:U+6797" } },
  "many": [
    { "connectors": { "component": { "$id": "grapheme:U+6728" } } }
  ]
}
```

---

## Grapheme Variant Groups

### Concept

Variant groups collect graphemes that are non-embedded variants of one another — separate grapheme documents representing the same semantic concept with different visual forms based on position. Users study these together to learn differentiation.

Groups are generated based on naming conventions: if a grapheme has "Variant" in its name (e.g., "Water Variant"), it is grouped with the base grapheme (e.g., "Water").

### Model & Document Format

**Model:** `data/grapheme-variant-group/japanese-grapheme-variant-group.schema.json`

This is an OSMF Relational Model that groups graphemes using the `many` pattern with a `member` connector.

**Example document:**
```json
{
  "$id": "grapheme-variant-group:water",
  "name": "Water",
  "many": [
    { "connectors": { "member": { "$id": "grapheme:U+6C34" } } },
    { "connectors": { "member": { "$id": "grapheme:U+6C35" } } }
  ]
}
```

---

## Kanji Dependencies

### Concept

Kanji-to-kanji dependency relationships express how kanji are composed of other kanji. A parent kanji has prerequisite kanji that should be studied first, based on visual decomposition — the prerequisite kanji physically appears as a component within the parent.

Decomposition uses CHISE IDS (primary) and KanjiVG (fallback) data, iterating on un-normalized kanji from kanjidic2 for better decomposition coverage.

### Model & Document Format

**Model:** `data/kanji-dependency/japanese-kanji-dependency.schema.json`

This is an OSMF Relational Model with:
- `parent` connector — the kanji being decomposed
- `prerequisite` connector — a kanji that should be studied before the parent

Uses the `many` pattern to express multiple prerequisites per parent.

**Example document:** 明 (Bright) depends on 日 (Sun) and 月 (Moon)
```json
{
  "$id": "kanji-dep:U+660E",
  "connectors": { "parent": { "$id": "kanji:U+660E" } },
  "many": [
    { "connectors": { "prerequisite": { "$id": "kanji:U+65E5" } } },
    { "connectors": { "prerequisite": { "$id": "kanji:U+6708" } } }
  ]
}
```

---

## Kanji Grapheme Dependencies

### Concept

Kanji-to-grapheme dependency relationships express which graphemes compose each kanji. This connects the grapheme decomposition system to the kanji content, enabling grapheme readiness scoring — determining which grapheme building blocks a user needs before studying a given kanji.

### Model & Document Format

**Model:** `data/kanji-grapheme-dependency/japanese-kanji-grapheme-dependency.schema.json`

This is an OSMF Relational Model with:
- `parent` connector — the kanji being decomposed
- `component` connector — a grapheme that is a component of the parent kanji

Uses the `many` pattern to express multiple grapheme components per kanji.

**Example document:** 七 (Seven) = 一 (One) + 乙 (Second Rank)
```json
{
  "$id": "kanji-grapheme-dep:U+4E03",
  "connectors": { "parent": { "$id": "kanji:U+4E03" } },
  "many": [
    { "connectors": { "component": { "$id": "grapheme:U+4E00" } } },
    { "connectors": { "component": { "$id": "grapheme:U+4E59" } } }
  ]
}
```

---

## Learning Order

### Concept

Learning order documents define the sequence in which content should be presented to users. Each order is a "track" targeting a specific content type (graphemes, kanji, etc.). Multiple tracks can exist for the same content type (e.g., a default order and an alternative frequency-based order).

The learning order is separate from the dependency graph — the app uses dependencies for gating (what the user *can* study), and the learning order for prioritization (what should be *suggested* next among unlocked content).

### Tracks

**Grapheme default track** (`japanese-grapheme-learning-order-default`):
- Sort: stroke count ASC, popularity DESC, `$id` ASC
- Variant groups kept together (base grapheme first, then variants)
- Validated against grapheme dependencies (0 violations)

**Kanji default track** (`japanese-kanji-learning-order-default`):
- Sort: stroke count ASC, grapheme readiness ASC, kanjidic grade ASC, popularity DESC, `$id` ASC
- Grapheme readiness = max position of any grapheme component in the grapheme learning order
- Validated against kanji dependencies (22 warnings from decomposition artifacts; app gates independently)

### Model & Document Format

**Model:** `../../shared-models/learning-order.schema.json` (shared across languages)

This is an OSMF Relational Model with an `item` connector and `many` pattern. Each item has a `position` (0-indexed).

**Example document (abbreviated):**
```json
{
  "$schema": "../../../../shared-models/learning-order.schema.json",
  "$id": "japanese-grapheme-learning-order-default",
  "data": {
    "contentType": "grapheme",
    "trackId": "default",
    "trackName": "Default Grapheme Order"
  },
  "many": [
    { "connectors": { "item": { "$id": "grapheme:U+4E00" } }, "data": { "position": 0 } },
    { "connectors": { "item": { "$id": "grapheme:U+4E3F" } }, "data": { "position": 1 } }
  ]
}
```

---

## Scripts

Scripts for generating, analyzing, and maintaining Japanese content are located in `scripts/`. See [README-CONTENT.md](../../README-CONTENT.md) for the general script architecture (adapters, analyzers, generators, lib).

### Generators

| Script | Output |
|--------|--------|
| `generators/grapheme_dependency_generator.py` | Grapheme dependency relational documents |
| `generators/grapheme_variant_group_generator.py` | Grapheme variant group relational documents |
| `generators/kanji_generator.py` | Kanji data documents (generated from kanjidic2) |
| `generators/kanji_dependency_generator.py` | Kanji-to-kanji dependency relational documents |
| `generators/kanji_grapheme_dependency_generator.py` | Kanji-to-grapheme dependency relational documents |
| `generators/learning_order_generator.py` | Grapheme learning order document |
| `generators/kanji_learning_order_generator.py` | Kanji learning order document |

### Analyzers

| Script | Output |
|--------|--------|
| `analyzers/find_component_popularity.py` | Component popularity metrics across all kanji |
| `analyzers/create_grapheme_web_graph.py` | HTML visualization of grapheme composition (`docs/reports/grapheme-graph.html`) |
| `analyzers/dump_graphemes.py` | All graphemes sorted by stroke count (`docs/reports/graphemes_all.txt`) |
| `analyzers/gather_grapheme_variants.py` | Embedded variant summary for documentation |

### Shared Modules

| Module | Purpose |
|--------|---------|
| `lib/normalizers.py` | NFKC_PLUS normalization — extends Unicode NFKC with additional CJK variant mappings |
| `lib/grapheme_io.py` | OSMF document I/O for grapheme and relational data |
| `lib/paths.py` | Path configuration for all data, source, and output directories |
| `adapters/component_analysis.py` | CHISE IDS and KanjiVG decomposition logic |
| `adapters/kanjidic.py` | kanjidic2 dataset parsing |

---

## Data Sources

- **CHISE IDS** — Primary decomposition data ([chise.org](http://chise.org/)) — Ideographic Description Sequences
- **KanjiVG** — Fallback decomposition data ([kanjivg.tagaini.net](http://kanjivg.tagaini.net/)) — CC BY-SA 3.0
- **Unihan** — Unicode Han Database ([unicode.org](https://www.unicode.org/charts/unihan.html))
- **kanjidic2** — Kanji dictionary with stroke counts and readings
