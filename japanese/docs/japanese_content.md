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
| Kanji Grapheme Dependency | `data/kanji-grapheme-dependency/japanese-kanji-grapheme-dependency.schema.json` | `data/kanji-grapheme-dependency/documents/` | Schema only |
| Kanji Dependency | `data/kanji-dependency/japanese-kanji-dependency.schema.json` | `data/kanji-dependency/documents/` | Schema only |

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

## Scripts

Scripts for generating, analyzing, and maintaining Japanese content are located in `scripts/`. See the repository README for the general script architecture (adapters, analyzers, generators, lib).

### Generators

| Script | Output |
|--------|--------|
| `generators/grapheme_dependency_generator.py` | Grapheme dependency relational documents |
| `generators/grapheme_variant_group_generator.py` | Grapheme variant group relational documents |
| `generators/kanji_generator.py` | Kanji data documents (generated from kanjidic2) |

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
| `lib/grapheme_io.py` | OSMF document I/O for grapheme data |
| `lib/paths.py` | Path configuration |
| `adapters/component_analysis.py` | CHISE IDS and KanjiVG decomposition logic |
| `adapters/kanjidic.py` | kanjidic2 dataset parsing |

---

## Data Sources

- **CHISE IDS** — Primary decomposition data ([chise.org](http://chise.org/)) — Ideographic Description Sequences
- **KanjiVG** — Fallback decomposition data ([kanjivg.tagaini.net](http://kanjivg.tagaini.net/)) — CC BY-SA 3.0
- **Unihan** — Unicode Han Database ([unicode.org](https://www.unicode.org/charts/unihan.html))
- **kanjidic2** — Kanji dictionary with stroke counts and readings
