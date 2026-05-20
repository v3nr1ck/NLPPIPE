"""
CMMS NLP Pipeline — Interactive Dashboard
==========================================
Run with: streamlit run dashboard.py

A Streamlit front-end for:
- Simulating client work orders and watching the pipeline process them
- Viewing confidence scores / eval metrics per mapping
- Human-in-the-loop review & override (with override logging)
- Aggregate pipeline performance metrics
- Control table editor

Author: farts 🐶 (code-puppy-472b42)
"""
from __future__ import annotations
import json
import csv
import time
from pathlib import Path
from datetime import datetime

import streamlit as st

# ── Project imports ──
import sys
sys.path.insert(0, str(Path(__file__).parent))

from schemas import (
    ClientWorkOrder, CMMSMapping, PipelineResult,
    TradeEnum, EquipmentEnum, ProblemTypeEnum, ProblemCodeEnum,
    get_readable_label,
)
from pipeline import CMMSPipeline, CONTROL_TABLE_PATH
from post_processor import MetricsTracker


# ── Page Config ─────────────────────────────────────────────────────

st.set_page_config(
    page_title="CMMS NLP Pipeline",
    page_icon="🔧",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ── Session State Init ──────────────────────────────────────────────

def init_session():
    defaults = {
        "pipeline": None,
        "history": [],          # list of PipelineResult
        "override_log": [],     # list of override dicts
        "metrics": MetricsTracker(),
        "engine_mode": "mock",
        "auto_threshold": 0.85,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


init_session()


# ── Sidebar: Engine & Settings ──────────────────────────────────────

with st.sidebar:
    st.title("🔧 Pipeline Settings")

    engine_mode = st.selectbox(
        "Inference Engine",
        options=["mock", "rag"],
        index=0 if st.session_state.engine_mode == "mock" else 1,
        help="mock = keyword-based demo (no GPU needed)\nrag = vLLM + Outlines constrained generation",
    )

    if engine_mode == "rag":
        rag_model = st.text_input("Model", value="Qwen/Qwen2.5-7B-Instruct")
        if st.button("Check CUDA"):
            try:
                import torch
                if torch.cuda.is_available():
                    st.success(f"CUDA ready — {torch.cuda.get_device_name(0)}")
                else:
                    st.warning("CUDA not available. RAG mode needs GPU.")
            except ImportError:
                st.warning("PyTorch not installed.")

    auto_threshold = st.slider(
        "Auto-Approve Confidence Threshold",
        min_value=0.50, max_value=0.99, value=0.85, step=0.01,
        help="Results with confidence >= this value are auto-approved."
    )

    if st.button("🔄 (Re)Initialize Pipeline"):
        kwargs = {}
        if engine_mode == "ollama":
            kwargs["model"] = ollama_model
        st.session_state.pipeline = CMMSPipeline(
            engine_mode=engine_mode,
            auto_threshold=auto_threshold,
            **kwargs,
        )
        st.session_state.engine_mode = engine_mode
        st.session_state.auto_threshold = auto_threshold
        st.session_state.history = []
        st.session_state.metrics = MetricsTracker()
        st.success(f"Pipeline initialized with `{engine_mode}` engine!")

    st.divider()

    # Quick metrics
    if st.session_state.history:
        m = st.session_state.metrics.summary()
        st.metric("Total Processed", m["total_processed"])
        st.metric("Auto-Approved", f"{m['auto_approved']} ({m['accuracy_rate']:.0%})")
        st.metric("Flagged for Review", m["human_reviewed"])
        st.metric("Avg Confidence", f"{m['avg_confidence']:.2f}")
        st.metric("Avg Latency", f"{m['avg_inference_ms']:.0f}ms")
        st.metric("Field Fill Rate", f"{m['field_fill_rate']:.0%}")
        if "llm_call_rate" in m:
            st.metric("LLM Call Rate", f"{m['llm_call_rate']:.0%}")


# ── Main Tabs ───────────────────────────────────────────────────────

tab_sim, tab_batch, tab_control, tab_overrides = st.tabs([
    "🎯 Single Work Order",
    "📊 Batch Simulation",
    "🗂️ Control Table",
    "✏️ Override Log",
])


# ═══════════════════════════════════════════════════════════════════════
# TAB 1: Single Work Order Simulation
# ═══════════════════════════════════════════════════════════════════════

with tab_sim:
    st.header("Simulate a Client Work Order")

    if st.session_state.pipeline is None:
        st.info("👆 Initialize the pipeline in the sidebar first!")
    else:
        col_left, col_right = st.columns([1, 1])

        with col_left:
            st.subheader("📥 Input")

            # Dynamic field input — add as many client fields as you want
            st.caption("Add client fields below. Use the field names YOUR client actually sends.")

            with st.form("work_order_form"):
                client_name = st.text_input("Client Name", value="ACME Corp")

                # Pre-populate with typical fields
                extra_fields_str = st.text_area(
                    "Client Fields (JSON format)",
                    value='''{
  "equipment_tag": "RTU-4",
  "work_desc": "compressor making grinding noise and blowing warm air",
  "trade_code": "MECH",
  "building": "HQ",
  "floor": "3",
  "priority": "urgent",
  "requested_by": "janet"
}''',
                    height=200,
                    help="Paste or type the JSON payload your client's API sends. ANY field names work."
                )

                raw_text = st.text_area(
                    "Raw Text (optional — for unstructured blobs)",
                    value="",
                    help="If the client sends a big paragraph instead of structured fields, put it here."
                )

                submitted = st.form_submit_button("🚀 Run Pipeline", use_container_width=True)

            if submitted:
                try:
                    extra_fields = json.loads(extra_fields_str)
                except json.JSONDecodeError:
                    st.error("Invalid JSON in Client Fields. Please fix and resubmit.")
                    extra_fields = {}

                work_order = ClientWorkOrder(
                    client_name=client_name,
                    extra_fields=extra_fields,
                    raw_text=raw_text if raw_text else None,
                )
                with st.spinner("Running pipeline..."):
                    start = time.perf_counter()
                    result = st.session_state.pipeline.run(work_order)
                    total_ms = (time.perf_counter() - start) * 1000

                st.session_state.history.append(result)

        with col_right:
            st.subheader("📤 Result")
            if st.session_state.history:
                result = st.session_state.history[-1]

                # ── Confidence gauge ──
                conf = result.confidence_score
                color = "green" if conf >= 0.85 else ("orange" if conf >= 0.70 else "red")
                st.markdown(f"### Confidence: :{color}[{conf:.0%}]")

                if result.requires_review:
                    st.warning(f"⚠️ {result.review_reason}")
                else:
                    st.success("✅ Auto-approved — ready for CMMS API")

                # ── Mapping display ──
                mapping = result.mapping
                mapping_data = {
                    "Trade": (mapping.trade_id.value, get_readable_label(TradeEnum, mapping.trade_id.value)),
                    "Equipment": (mapping.equipment_id.value, get_readable_label(EquipmentEnum, mapping.equipment_id.value)),
                    "Problem Type": (mapping.problem_type_id.value, get_readable_label(ProblemTypeEnum, mapping.problem_type_id.value)),
                    "Problem Code": (mapping.problem_code_id.value, get_readable_label(ProblemCodeEnum, mapping.problem_code_id.value)),
                }

                for label, (code, readable) in mapping_data.items():
                    st.metric(label, readable, delta=code, delta_color="off")

                # ── Reasoning removed in v1.3.0 — constrained generation guarantees valid output

                # ── Full JSON ──
                if result.mapped_fields:
                    with st.expander("📋 Mapped Fields (Hard-Mapped via Control Table)", expanded=False):
                        st.json(result.mapped_fields)
                if result.context_fields:
                    with st.expander("🔍 Context Fields (Passed to LLM for Inference)", expanded=False):
                        st.json(result.context_fields)
                if result.ignored_fields:
                    with st.expander("🗑️ Ignored Fields (Dropped)", expanded=False):
                        st.json(result.ignored_fields)

                # ── Full JSON ──
                with st.expander("📄 Full Output JSON", expanded=False):
                    st.json(json.loads(mapping.model_dump_json()))

                # ── Latency ──
                st.caption(f"⏱️ LLM inference: {result.inference_time_ms:.1f}ms | Total: {total_ms:.1f}ms")

                # ── Human Override ──
                if result.requires_review:
                    st.divider()
                    st.subheader("✏️ Human Override")
                    with st.form("override_form"):
                        new_trade = st.selectbox(
                            "Correct Trade",
                            options=[e.value for e in TradeEnum],
                            format_func=lambda v: f"{v} — {get_readable_label(TradeEnum, v)}",
                            index=[e.value for e in TradeEnum].index(mapping.trade_id.value),
                        )
                        new_equip = st.selectbox(
                            "Correct Equipment",
                            options=[e.value for e in EquipmentEnum],
                            format_func=lambda v: f"{v} — {get_readable_label(EquipmentEnum, v)}",
                            index=[e.value for e in EquipmentEnum].index(mapping.equipment_id.value),
                        )
                        new_ptype = st.selectbox(
                            "Correct Problem Type",
                            options=[e.value for e in ProblemTypeEnum],
                            format_func=lambda v: f"{v} — {get_readable_label(ProblemTypeEnum, v)}",
                            index=[e.value for e in ProblemTypeEnum].index(mapping.problem_type_id.value),
                        )
                        new_pcode = st.selectbox(
                            "Correct Problem Code",
                            options=[e.value for e in ProblemCodeEnum],
                            format_func=lambda v: f"{v} — {get_readable_label(ProblemCodeEnum, v)}",
                            index=[e.value for e in ProblemCodeEnum].index(mapping.problem_code_id.value),
                        )
                        override_note = st.text_input("Override Reason", placeholder="e.g. 'Should be HVAC not Plumbing'")

                        if st.form_submit_button("✅ Submit Override"):
                            override = {
                                "timestamp": datetime.now().isoformat(),
                                "original_mapping": json.loads(mapping.model_dump_json()),
                                "corrected_mapping": {
                                    "trade_id": new_trade,
                                    "equipment_id": new_equip,
                                    "problem_type_id": new_ptype,
                                    "problem_code_id": new_pcode,
                                },
                                "note": override_note,
                                "original_input": dict(result.original.extra_fields),
                            }
                            st.session_state.override_log.append(override)
                            st.session_state.metrics.record_override()
                            st.success("Override logged! This will be used for future fine-tuning.")
                            st.balloons()


# ═══════════════════════════════════════════════════════════════════════
# TAB 2: Batch Simulation
# ═══════════════════════════════════════════════════════════════════════

with tab_batch:
    st.header("Batch Simulation — Run Multiple Work Orders")

    col1, col2 = st.columns([1, 2])

    with col1:
        st.subheader("Test Scenarios")

        # Preset scenarios — now using dynamic extra_fields
        presets = {
            "Compressor Failure (ACME style)": {
                "client": "ACME Corp",
                "fields": {"equipment_tag": "RTU-4", "work_desc": "compressor grinding, blowing warm air", "trade_code": "MECH", "priority": "urgent"},
            },
            "Sink Overflow Emergency": {
                "client": "GenericCo",
                "fields": {"asset": "Men's Room Sink", "issue": "sink backed up, water seeping into hallway carpet", "craft": "plumber", "priority": "emergency"},
            },
            "Boiler Banging": {
                "client": "Global Facilities",
                "fields": {"asset": "Basement Boiler", "description": "loud banging noise, radiators cold upstairs", "craft": "pipefitter", "priority": "high"},
            },
            "Electrical Burning Smell": {
                "client": "Test Corp",
                "fields": {"location": "Server Room", "issue": "lights flickering in west wing, burning smell near outlet", "craft": "sparky", "priority": "emergency"},
            },
            "Sump Pump Failure": {
                "client": "GenericCo",
                "fields": {"asset": "Basement Sump Pump", "description": "pump not running, water pooling in basement", "craft": "plumber", "priority": "urgent"},
            },
            "Ceiling Water Damage": {
                "client": "ACME Corp",
                "fields": {"asset": "Hallway Ceiling", "issue": "big water stain, ceiling tiles sagging", "craft": "handyman", "priority": "medium"},
            },
            "Toilet Overflow": {
                "client": "GenericCo",
                "fields": {"asset": "Men's Room Toilet", "description": "toilet overflowing, water all over floor", "craft": "plumber", "priority": "emergency"},
            },
            "Broken Door with Extra Fields": {
                "client": "ACME Corp",
                "fields": {"asset": "Main Entrance Door", "issue": "front door won't latch, hinge seems bent", "craft": "carpenter", "building": "HQ", "floor": "1", "requested_by": "reception"},
            },
            "Vague — 'It's broken' (no craft)": {
                "client": "Test Corp",
                "fields": {"issue": "It's broken"},
            },
            "Chiller Chemical Smell (with ignore fields)": {
                "client": "Global Facilities",
                "fields": {"asset": "Chiller", "work_desc": "weird chemical smell near chiller", "trade_code": "MECH", "requested_by": "janet", "cost_center": "CC-882", "timestamp": "2025-01-15"},
            },
        }

        selected_presets = []
        for name, scenario in presets.items():
            if st.checkbox(name, value=True):
                selected_presets.append((name, scenario))

        if st.button("🚀 Run All Selected", use_container_width=True, type="primary"):
            if st.session_state.pipeline is None:
                st.warning("Initialize the pipeline first!")
            else:
                pipeline = st.session_state.pipeline
                with st.spinner(f"Processing {len(selected_presets)} work orders..."):
                    for name, scenario in selected_presets:
                        wo = ClientWorkOrder(
                            client_name=scenario["client"],
                            extra_fields=scenario["fields"],
                        )
                        result = pipeline.run(wo)
                        st.session_state.history.append(result)

                st.success(f"Done! Processed {len(selected_presets)} work orders.")

    with col2:
        st.subheader("Results Summary")

        if not st.session_state.history:
            st.info("Run some work orders to see results here.")
        else:
            # Only show results from this batch (most recent N)
            batch_results = st.session_state.history[-len(selected_presets):] if selected_presets else st.session_state.history

            for r in reversed(batch_results):
                conf = r.confidence_score
                icon = "🟢" if conf >= 0.85 else ("🟠" if conf >= 0.70 else "🔴")
                orig = r.original
                # Build display summary from whatever fields exist
                field_summary = " | ".join(f"{k}={v[:30]}" for k, v in list(orig.extra_fields.items())[:3])
                if not field_summary:
                    field_summary = "(no fields)"

                with st.expander(
                    f"{icon} {conf:.0%} | {field_summary}...",
                    expanded=(conf < 0.85)
                ):
                    c1, c2 = st.columns(2)
                    with c1:
                        st.markdown("**Input Fields**")
                        st.json(dict(orig.extra_fields))
                    with c2:
                        st.markdown("**Mapping**")
                        m = r.mapping
                        st.text(
                            f"Trade: {m.trade_id.value}\n"
                            f"Equip: {m.equipment_id.value}\n"
                            f"Prob Type: {m.problem_type_id.value}\n"
                            f"Prob Code: {m.problem_code_id.value}"
                        )
                    if r.review_reason:
                        st.warning(r.review_reason)


# ═══════════════════════════════════════════════════════════════════════
# TAB 3: Control Table Editor
# ═══════════════════════════════════════════════════════════════════════

with tab_control:
    st.header("Control Table — Business Rules")

    st.markdown("""
    This table defines **hard rules** that bypass the LLM. When a client uses a known term,
    we map it directly without calling the model. Business users can edit this CSV.
    """)

    # Read and display the control table
    try:
        with open(CONTROL_TABLE_PATH, "r") as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        if rows:
            st.dataframe(rows, use_container_width=True)
        else:
            st.info("Control table is empty.")

        # Quick-add rule
        with st.expander("➕ Add a New Rule"):
            with st.form("add_rule_form"):
                nc = st.text_input("Client Name (* for all)", value="*")
                sf = st.selectbox("Source Field", ["craft", "asset", "priority", "issue"])
                sv = st.text_input("Source Value", placeholder="e.g. 'mechanic'")
                tf = st.selectbox("Target Field", ["trade_id", "equipment_id", "problem_type_id", "problem_code_id"])
                tv = st.text_input("Target Value", placeholder="e.g. 'TRD_001_HVAC'")
                hm = st.checkbox("Is Hard-Mapped?", value=True)
                pri = st.number_input("Priority", min_value=0, max_value=100, value=10)

                if st.form_submit_button("Add Rule"):
                    new_row = {
                        "client_name": nc,
                        "source_field": sf,
                        "source_value": sv,
                        "target_field": tf,
                        "target_value": tv,
                        "is_hard_mapped": str(hm).lower(),
                        "priority": str(pri),
                    }
                    with open(CONTROL_TABLE_PATH, "a", newline="") as f:
                        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
                        writer.writerow(new_row)
                    st.success("Rule added! Reload the pipeline to apply.")
                    st.rerun()

        if st.button("🔄 Reload Control Table in Pipeline"):
            if st.session_state.pipeline:
                st.session_state.pipeline.reload_control_table()
                st.success("Control table reloaded!")
    except FileNotFoundError:
        st.error(f"Control table not found at {CONTROL_TABLE_PATH}")


# ═══════════════════════════════════════════════════════════════════════
# TAB 4: Override Log
# ═══════════════════════════════════════════════════════════════════════

with tab_overrides:
    st.header("Override Log — Human Corrections")

    if not st.session_state.override_log:
        st.info("No overrides yet. When you correct a low-confidence mapping, it'll show up here.")
        st.markdown("""
        **Why this matters:** Every override becomes training data for the next fine-tuning run.
        After 200+ overrides, you can train a model that rarely needs correction.
        """)
    else:
        st.metric("Total Overrides", len(st.session_state.override_log))

        for i, override in enumerate(reversed(st.session_state.override_log)):
            with st.expander(f"Override #{len(st.session_state.override_log) - i} — {override['timestamp'][:19]}"):
                c1, c2, c3 = st.columns(3)
                with c1:
                    st.markdown("**Original Input**")
                    st.json(override["original_input"])
                with c2:
                    st.markdown("**Model Output**")
                    st.json(override["original_mapping"])
                with c3:
                    st.markdown("**Human Correction**")
                    st.json(override["corrected_mapping"])
                if override.get("note"):
                    st.caption(f"📝 Note: {override['note']}")

        # Export overrides as JSONL for training
        if st.button("📥 Export Overrides as JSONL"):
            jsonl_content = ""
            for ov in st.session_state.override_log:
                # Build input string from whatever fields were present
                input_parts = []
                for k, v in ov["original_input"].items():
                    input_parts.append(f"{k}: {v}")
                input_str = ", ".join(input_parts)

                record = {
                    "instruction": "Map CMMS data.",
                    "input": input_str,
                    "output": json.dumps(ov["corrected_mapping"]),
                }
                jsonl_content += json.dumps(record) + "\n"

            st.download_button(
                label="Download overrides.jsonl",
                data=jsonl_content,
                file_name="overrides.jsonl",
                mime="application/jsonl",
            )
            st.success(f"Exported {len(st.session_state.override_log)} records for training!")


# ── Footer ──────────────────────────────────────────────────────────

st.divider()
st.caption(
    "🐶 CMMS NLP Pipeline · v1.3.0 RAG + Constrained Generation · "
    f"Engine: `{st.session_state.engine_mode}`"
)
