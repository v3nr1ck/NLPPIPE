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

