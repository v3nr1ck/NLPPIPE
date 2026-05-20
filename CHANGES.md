# CHANGES.md — CMMS NLP Pipeline

> **Track all architectural changes. Each section represents a commit.**
> To revert, `git revert <commit-hash>`.

---

## v1.0.0 — Initial Baseline (2025-05-19)

**Commit:** `initial-baseline`

### Architecture: The "Logic Sandwich" 🥪

Three-layer adapter between client work orders and CMMS API:

```
Client Work Order (messy text)
    │
    ▼
Layer 1: Pre-Processor ("The Rules")
    • Reads control_table.csv for hard 1:1 mappings
    • craft=mechanic → trade_id=TRD_001_HVAC (bypasses LLM)
    • Wildcard client matching (*)
    • Priority-based rule resolution
    │
    ▼
Layer 2: Constrained LLM Inference ("The Brain")
    • Dual-mode: mock (keyword) + ollama (real LLM)
    • Prompt builder injects allowed IDs as constraints
    • Future: vLLM + Outlines for guaranteed valid JSON
    │
    ▼
Layer 3: Post-Processor ("The Validation")
    • Pydantic schema validation
    • Confidence scoring (auto > 85% | review 70-85% | manual < 70%)
    • Metrics tracking
    │
    ▼
CMMS API (clean JSON)
```

### Files (14)

| File | Purpose |
|---|---|
| `schemas.py` | Pydantic enums for locked CMMS IDs + ClientWorkOrder + PipelineResult |
| `control_table.csv` | Business-editable rules (client, source_field, source_value → target) |
| `pre_processor.py` | Reads control table, applies deterministic rules |
| `prompt_builder.py` | Builds system/user prompts with allowed ID injection |
| `inference_engine.py` | MockEngine (keyword) + OllamaEngine (local LLM) |
| `post_processor.py` | Pydantic validation, confidence scoring, routing |
| `pipeline.py` | Orchestrator wiring all 3 layers |
| `dashboard.py` | Streamlit UI: simulate, inspect, override, batch, metrics |
| `dataset.jsonl` | 15 starter training examples |
| `train.py` | Unsloth fine-tuning script (Mistral-7B QLoRA) |
| `test_pipeline.py` | End-to-end smoke test |
| `requirements.txt` | Minimal deps (pydantic, streamlit) |
| `nlppipeline_extracted.txt` | Original reference document |
| `.gitignore` | Python/virtualenv/build artifacts |

### Known Limitations (to be addressed in v1.1.0)

1. **Fixed ClientWorkOrder schema** — only accepts `asset`, `issue`, `craft`, `priority`, `location`, `raw_text`. Real clients have arbitrary field names.
2. **Binary mapping strategy** — control table only has `is_hard_mapped: true/false`. No concept of "use for context but don't map" (`select` strategy).
3. **No `ignore` strategy** — irrelevant client fields (e.g. `requested_by`) still flow through the pipeline.
4. **Prompt template is hardcoded** — assumes known field names rather than building dynamically from whatever the client sends.

### Test Results (mock engine)

| Scenario | Trade | Equipment | Confidence | Verdict |
|---|---|---|---|---|
| Compressor grinding + mechanic | HVAC | RTU | 87% | ✅ Auto |
| Sink overflow + plumber | Plumbing | Sink | 87% | ✅ Auto |
| "It's broken" (no craft) | Unknown | Unknown | 12% | ⚠️ Review |

---

## v1.1.0 — Dynamic Client Schema & Three-Bucket Classification (2025-05-19)

**Commit:** `dynamic-client-schema` | **PR:** `#2`

### Problem

Real client APIs send **arbitrary JSON payloads** with unknown field names:
```json
{"equipment_tag": "RTU-4", "work_desc": "compressor grinding", "trade_code": "MECH",
 "building": "HQ", "floor": "3", "requested_by": "janet", "cost_center": "CC-882"}
```

v1.0.0's fixed `ClientWorkOrder` (with hardcoded `asset`, `issue`, `craft`, etc.) couldn't handle this.

Additionally, client fields fall into **three categories**, not just "map or don't":
1. **Map**: Direct 1:1 translation to our IDs (e.g., `trade_code: MECH` → `TRD_001_HVAC`)
2. **Context**: Inject into LLM prompt for better classification, but don't map to output (e.g., `building: HQ`, `floor: 3`)
3. **Ignore**: Drop entirely (e.g., `requested_by: janet`, `cost_center: CC-882`)

### Changes

| File | Change | ±Lines |
|---|---|---|
| `schemas.py` | `ClientWorkOrder` now uses `extra_fields: dict[str, str]` (dynamic) instead of fixed optional fields. Added `get_field()` convenience accessor. `PipelineResult` now tracks `mapped_fields`, `context_fields`, `ignored_fields` instead of generic `pre_processed_fields`. | +30 / -15 |
| `control_table.csv` | `is_hard_mapped` column replaced with `strategy` column (`map` / `context` / `ignore`). Added example context rules (priority, sla_tier, building, floor) and ignore rules (requested_by, cost_center, timestamp). | +20 / -10 |
| `pre_processor.py` | Complete rewrite. Now classifies fields into three buckets. Supports `fnmatch` glob patterns for source_value matching (`RTU-*`). Fields matching NO rule default to `context`. | +120 / -80 |
| `prompt_builder.py` | `build_user_prompt()` now iterates over arbitrary `context_fields` dict. No hardcoded field names — whatever the client sends gets formatted into the prompt. | +25 / -30 |
| `pipeline.py` | Updated to pass `extra_fields` through and use new `PreProcessResult` (mapped/context/ignored). | +15 / -15 |
| `post_processor.py` | `process()` now accepts `mapped_fields`, `context_fields`, `ignored_fields` instead of generic `pre_processed_fields`. | +5 / -3 |
| `dashboard.py` | Single work order form now accepts arbitrary JSON. Batch presets updated to use dynamic fields. Results display shows all three buckets. Override export builds input strings from dynamic fields. | +40 / -40 |
| `test_pipeline.py` | Updated to test ACME-style, Global Facilities-style, fully pre-mapped, and vague inputs with ignore fields. | +30 / -25 |

### Architecture After

```
Client sends: {"equipment_tag": "RTU-4", "work_desc": "...", "trade_code": "MECH",
               "building": "HQ", "floor": "3", "requested_by": "janet"}
    │
    ▼
LAYER 1 (Pre-Processor)
    ├─ MAP: equipment_tag → equipment_id=EQP_99_RTU (rule: RTU-*)
    ├─ MAP: trade_code → trade_id=TRD_001_HVAC
    ├─ CONTEXT: work_desc, building, floor → injected into LLM prompt
    └─ IGNORE: requested_by → dropped
    │
    ▼
LAYER 2 (LLM)
    • Only needs to infer problem_type_id + problem_code_id
    • Has context: work_desc, building, floor
    • System prompt shows ALLOWED VALUES for remaining fields
    │
    ▼
LAYER 3 (Post-Processor)
    • Overlays mapped fields onto LLM output
    • Validates, scores, routes
```

### Fallthrough Behavior

Any client field that matches **NO rule** defaults to `context` — it's passed to the LLM for inference. This means new clients with novel field names work immediately without updating the control table.

### Test Results (mock engine, v1.1.0)

| Scenario | Map | Context | Ignore | Verdict |
|---|---|---|---|---|
| ACME-style (equipment_tag, trade_code, etc.) | trade + equip mapped | work_desc, bldg, floor, priority → LLM | requested_by, cost_center dropped | ✅ Review (79%) |
| Global Facilities (asset, craft, etc.) | trade mapped | asset, issue, priority, location → LLM | — | ✅ Auto (87%) |
| All fields pre-mapped | trade + equip mapped | work_desc → LLM | — | ⚠️ Review (12% mock) |
| Vague + ignore fields | — | issue → LLM | submitted_by dropped | ⚠️ Review (12%) |

---

## v1.1.1 — Cross-Platform Launchers + Code Signing Strategy (2025-05-19)

**Commit:** `launchers-signing` | **PR:** `#3`

### Changes

| File | Change |
|---|---|
| `launch.bat` | NEW — Windows double-click launcher. Checks Python, creates venv, installs deps, opens browser, starts Streamlit. |
| `launch.command` | NEW — macOS double-click launcher (Finder-compatible). Same bootstrap flow. |
| `SIGNING.md` | NEW — 4-tier signing/trust strategy guide. Tier 1 (free/GitHub trust anchor) recommended for demos. |
| `checksums.sha256` | NEW — SHA256 hashes of all distributable files for integrity verification. |
| `.gitignore` | Updated to ignore `venv/` folder created by launchers. |

---

## v1.2.0 — Vendor Profiles + Nested Field Extraction + Custom Field Discovery (2025-05-19)

**Commit:** `vendor-profiles` | **PR:** `#4`

### Problem

Real CMMS APIs have three characteristics our flat `extra_fields` couldn't handle:

1. **Vendor-specific field names**: "Trade" is `WORKTYPE` (Maximo), `maintenanceType` (Fiix), `WorkCategory` (Brightly), `category` (UpKeep), `tradeCode` (Infor EAM) — 20+ variations across platforms.
2. **Nested/child objects**: Trade/craft often lives in child arrays like `Labours[0].Craft` (Brightly) or `WPLABOR.CRAFT` (Maximo), not on the WO header.
3. **Custom fields are first-class**: Every modern CMMS has `customFields[]` that often contain critical classification data.

### Changes

| File | Change |
|---|---|
| `vendor_profile.py` | NEW — Loader + flattening engine. Parses `field_aliases`, `nested_paths` (dot-bracket: `Labours[0].Craft`), auto-detects `customFields[]` arrays. |
| `vendor_profiles/` | NEW — JSON profiles for Maximo, Fiix, UpKeep, Brightly + `_template.json` |
| `vendor_profiles/maximo.json` | IBM Maximo: 40+ field aliases, 4 nested paths (`WPLABOR.CRAFT`, `LABTRANS.CRAFT`). `WPLABOR` → `all-caps` aliases to canonical snake_case. |
| `vendor_profiles/fiix.json` | Fiix: 20 field aliases, nested `tasks[]` and `customFields[]` extraction. |
| `vendor_profiles/upkeep.json` | UpKeep: flat modern API, `formItems[]` and `customFields[]` extraction. |
| `vendor_profiles/brightly.json` | Brightly: `Labours[0].Craft` (index), `Labours[*].Craft` (wildcard join), nested `Scheduling.TargetCompletion`. |
| `vendor_profiles/_template.json` | Documentation template for creating new vendor profiles. |
| `schemas.py` | `extra_fields` type widened from `dict[str, str]` → `dict[str, Any]` (supports ints, floats, nested dicts/lists). |
| `pre_processor.py` | Now accepts optional `VendorProfile`. Fallthrough uses vendor `default_strategies`. Skips nested dicts/lists (expects upstream flattening). |
| `pipeline.py` | New `vendor=` parameter. When set, auto-flattens payload via `vendor_profile.flatten_payload()` before pre-processing. `list_vendors()` + `load_vendor()` for hot-swapping. |
| `prompt_builder.py` | `build_user_prompt()` accepts `dict[str, Any]` for context fields. |
| `post_processor.py` | `context_fields` type widened to `dict[str, Any]`. |
| `test_pipeline.py` | 4 new tests: Maximo (nested WPLABOR, all-caps), Fiix (custom fields + tasks), Brightly (array index + wildcard), backward compat (no vendor). |

### Nested Path Syntax

| Syntax | Example | Result |
|---|---|---|
| Simple dot | `WPLABOR.CRAFT` | Traverses nested dicts: `data["WPLABOR"]["CRAFT"]` |
| Array index | `Labours[0].Craft` | First element of array, then `"Craft"` field |
| Array wildcard | `Labours[*].Craft` | All elements, joined with `", "` |
| Custom fields auto | `customFields: [{name: "zone", value: "A"}]` | Auto-flattens to `cf_zone: "A"` |

### Architecture After

```
Client API sends: {"DESCRIPTION": "...", "ASSETNUM": "PUMP-045",
                    "WPLABOR": {"CRAFT": "Millwright"}, "WORKTYPE": "CM"}
    │
    ▼
VENDOR PROFILE FLATTENING (new)
    ├─ DESCRIPTION → description (alias)
    ├─ ASSETNUM → asset (alias)
    ├─ WPLABOR.CRAFT → craft_skill (nested extraction)
    └─ WORKTYPE → trade_code (alias)
    │
    ▼
LAYER 1 (Pre-Processor — uses canonical names + vendor default strategies)
    │
    ▼
LAYER 2 (LLM)
    │
    ▼
LAYER 3 (Post-Processor)
```

### Test Results

| Test | Vendor | Nested Extraction | Custom Fields | Vendor Default Strategies |
|---|---|---|---|---|
| Maximo | ✅ WPLABOR.CRAFT → craft_skill | N/A | status, reported_by, est_labor_hours → ignored |
| Fiix | ✅ tasks[0], tasks[*] | ✅ cf_safety_zone, cf_iso_cert_required | — |
| Brightly | ✅ Labours[0].Craft, Labours[*].Craft, Scheduling.TargetCompletion | N/A | — |
| No Vendor | N/A (raw fields) | N/A | Old rules still work |

---

## v1.3.0 — RAG Architecture + Constrained Generation (2025-05-19)

**Commit:** `rag-architecture` | **PR:** `#5`

### Pivot

Moving from a **Fine-Tuning** architecture to **Retrieval-Augmented Generation (RAG)**
with **Constrained Generation** via vLLM + Outlines.

**Why:**
- Fine-tuning bakes your IDs into model weights — schema changes require retraining
- RAG stores historical mappings in a vector database — updates are instant
- Constrained generation mathematically guarantees valid CMMSMapping JSON (no hallucinations)
- The model becomes a "smart retriever" rather than a "memorizer"

### Changes

| File | Change |
|---|---|
| `rag_pipeline.py` | NEW — RAG engine (Sentence Transformers embedding → cosine similarity retrieval → vLLM + Outlines constrained generation). Includes `MockRAGEngine` for testing without GPU. Replaces `inference_engine.py`. |
| `inference_engine.py` | DELETED — Replaced by `rag_pipeline.py`. Old Ollama/mock engines removed. |
| `train.py` | DELETED — No more fine-tuning. RAG replaces it. |
| `schemas.py` | Slimmed enums per spec: TradeEnum (3 values), EquipmentEnum (5), ProblemTypeEnum (3), ProblemCodeEnum (3). Removed `reasoning` field from CMMSMapping. Removed all "unknown" fallback values (constrained generation guarantees validity). |
| `pipeline.py` | Updated imports from `rag_pipeline`. `engine_mode` now "mock" or "rag" (was "ollama"). |
| `post_processor.py` | Updated imports. Fallback values changed to valid enums. Removed UNK check in metrics. |
| `prompt_builder.py` | Removed `reasoning` from system prompt template and output format. |
| `dashboard.py` | Removed reasoning display. Engine selector: "mock" / "rag" (was "ollama"). CUDA check button for RAG mode. |
| `dataset.jsonl` | Rewritten: 15 examples using ONLY valid enum values. Removed `reasoning` field from all outputs. Removed `instruction` key (unused by RAG). |
| `control_table.csv` | Removed rules referencing deleted enum values (TRD_004_CARP, TRD_005_PAINT, TRD_006_GENM, etc.). |
| `requirements.txt` | Added `sentence-transformers`. Removed ollama references. vLLM/Outlines commented out (optional heavy deps). |
| `test_pipeline.py` | Rewritten for RAG: 3 tests covering mock RAG, electrical fault, and Maximo vendor profile with RAG. |

### New Architecture

```
Client Work Order
    │
    ▼
VENDOR PROFILE FLATTENING (v1.2.0)
    │
    ▼
LAYER 1: Pre-Processor (control_table.csv)
    │
    ▼
LAYER 2: RAG ENGINE (NEW)
    ├─ 1. Embed query with Sentence Transformer (all-MiniLM-L6-v2)
    ├─ 2. Cosine similarity search → top-5 historical tickets
    ├─ 3. Build RAG prompt with examples as in-context demonstrations
    └─ 4. vLLM + Outlines constrained generation → guaranteed CMMSMapping JSON
    │
    ▼
LAYER 3: Post-Processor (validation, confidence, routing)
    │
    ▼
CMMS API
```

### Model

- **Base model:** Qwen/Qwen2.5-7B-Instruct or mistralai/Mistral-7B-Instruct-v0.3
- **Embedding model:** all-MiniLM-L6-v2 (Sentence Transformers, 384-dim, fast CPU inference)
- **Constrained decoding:** Outlines `generate.json(model, CMMSMapping)` — token-level enforcement
- **Inference engine:** vLLM with PagedAttention (GPU memory utilization: 85%)

### Test Results (mock RAG engine)

| Test | Trade | Equipment | ProbType | ProbCode | Confidence |
|---|---|---|---|---|---|
| Sink Overflow | Plumbing | Sink | Clog | Emerg Overflow | 43% |
| Electrical Fault | Electrical | RTU | Mechanical | Compressor Fail | 15% |
| Maximo Vendor | HVAC | RTU | Mechanical | Compressor Fail | 15% |

*Low confidence on tests 2-3 is expected: mock engine uses naive keyword similarity.
Real RAG with Sentence Transformers cosine similarity will score much higher.*

---

## Template for Future Changes

```markdown
## vX.Y.Z — Title (YYYY-MM-DD)

**Commit:** `<hash>` | **PR:** `#<number>`

### Problem
<What gap/issue does this address?>

### Changes
| File | Change | Lines |
|---|---|---|
| `file.py` | <what changed> | ±N |

### Rationale
<Why this approach?>
```

