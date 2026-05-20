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

