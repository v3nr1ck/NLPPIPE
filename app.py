"""
CMMS NLP Pipeline — FastAPI web app.
Three pages: Field Mapping Studio / Work Order Simulator / Rules Manager.
All interactive updates use HTMX (no custom JS except preset loading).

Run:  uvicorn app:app --reload --port 8000
"""
from __future__ import annotations
import json
import html
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

import db as db_module
from pipeline import CMMSPipeline
from schemas import ClientWorkOrder, TradeEnum, EquipmentEnum, ProblemTypeEnum, ProblemCodeEnum
from vendor_profile import VendorProfileLoader

# ── Constants ─────────────────────────────────────────────────────────────────

VENDOR_PROFILES_DIR = Path(__file__).parent / "vendor_profiles"

TARGET_VALUES: dict[str, list[tuple[str, str]]] = {
    "trade_id": [
        ("TRD_001_HVAC", "HVAC"),
        ("TRD_002_PLMB", "Plumbing"),
        ("TRD_003_ELEC", "Electrical"),
    ],
    "equipment_id": [
        ("EQP_99_RTU", "RTU"),
        ("EQP_88_CHLR", "Chiller"),
        ("EQP_77_BLR", "Boiler"),
        ("EQP_11_SINK", "Sink"),
        ("EQP_00_UNK", "Unknown"),
    ],
    "problem_type_id": [
        ("TYP_MECHANICAL", "Mechanical"),
        ("TYP_CLOG", "Clog"),
        ("TYP_ELEC_FAULT", "Electrical Fault"),
    ],
    "problem_code_id": [
        ("CODE_COMPRESSOR_FAIL", "Compressor Failure"),
        ("CODE_EMERGENCY_OVERFLOW", "Emergency Overflow"),
        ("CODE_POWER_LOSS", "Power Loss"),
    ],
}

PRESETS: dict[str, dict] = {
    "compressor": {
        "label": "HVAC — Compressor Failure",
        "client_name": "ACME Facilities",
        "vendor": "",
        "payload": {
            "equipment_tag": "RTU-4",
            "work_desc": "compressor grinding, unusual noise from rooftop unit",
            "craft": "mechanic",
            "priority": "P2",
            "building": "HQ",
            "floor": "Roof",
            "requested_by": "facilities@acme.com",
            "cost_center": "CC-001",
        },
    },
    "sink_overflow": {
        "label": "Plumbing — Sink Overflow",
        "client_name": "Global Facilities",
        "vendor": "",
        "payload": {
            "asset": "sink",
            "issue": "overflow, standing water on floor",
            "craft": "plumber",
            "priority": "emergency",
            "location": "Men's restroom - 2nd floor",
            "submitted_by": "security@global.com",
        },
    },
    "electrical_fault": {
        "label": "Electrical — Burning Smell",
        "client_name": "Tech Corp",
        "vendor": "",
        "payload": {
            "work_type": "ELEC",
            "description": "flickering lights and burning smell in server room",
            "trade": "electrician",
            "priority": "urgent",
            "location": "Server Room B",
            "timestamp": "2025-05-19T09:00:00Z",
        },
    },
    "maximo": {
        "label": "IBM Maximo — Pump Seal",
        "client_name": "Bedford Plant",
        "vendor": "maximo",
        "payload": {
            "DESCRIPTION": "Pump seal failure, fluid leaking",
            "ASSETNUM": "PUMP-045",
            "WOPRIORITY": 2,
            "SITEID": "BEDFORD",
            "WORKTYPE": "CM",
            "WPLABOR": {"CRAFT": "Millwright"},
        },
    },
}

# ── Pipeline cache (keyed by vendor, shared across requests) ──────────────────

_pipeline_cache: dict[str, CMMSPipeline] = {}
_vendor_loader = VendorProfileLoader(VENDOR_PROFILES_DIR)


def get_pipeline(vendor: str = "") -> CMMSPipeline:
    key = vendor or "none"
    if key not in _pipeline_cache:
        _pipeline_cache[key] = CMMSPipeline(engine_mode="mock", vendor=vendor or None)
    return _pipeline_cache[key]


def invalidate_pipelines() -> None:
    for p in _pipeline_cache.values():
        p.reload_control_table()


def list_vendors() -> list[str]:
    return _vendor_loader.list_available()


# ── App setup ─────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    db_module.init_db()
    get_pipeline()  # warm the default (no vendor) pipeline
    yield

app = FastAPI(title="CMMS NLP Pipeline", lifespan=lifespan)
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


# ── Page routes ───────────────────────────────────────────────────────────────

@app.get("/", response_class=RedirectResponse)
def root():
    return RedirectResponse(url="/studio")


@app.get("/studio", response_class=HTMLResponse)
def studio(request: Request):
    return templates.TemplateResponse(request, "studio.html", {
        "page": "studio",
        "vendors": list_vendors(),
        "clients": db_module.get_clients(),
    })


@app.get("/simulator", response_class=HTMLResponse)
def simulator(request: Request):
    return templates.TemplateResponse(request, "simulator.html", {
        "page": "simulator",
        "vendors": list_vendors(),
        "clients": db_module.get_clients(),
        "presets": PRESETS,
    })


@app.get("/rules", response_class=HTMLResponse)
def rules_page(request: Request):
    grouped = db_module.get_rules_grouped()
    return templates.TemplateResponse(request, "rules.html", {
        "page": "rules",
        "clients": db_module.get_clients(),
        "map_rules": grouped["map"],
        "context_rules": grouped["context"],
        "ignore_rules": grouped["ignore"],
        "target_fields": list(TARGET_VALUES.keys()),
        "target_values": TARGET_VALUES,
    })


# ── HTMX: Studio ─────────────────────────────────────────────────────────────

@app.post("/htmx/detect-fields", response_class=HTMLResponse)
async def htmx_detect_fields(request: Request):
    form = await request.form()
    vendor = str(form.get("vendor", "") or "")
    json_payload = str(form.get("json_payload", "") or "").strip()

    if not json_payload:
        return HTMLResponse(_alert("warning", "Paste a JSON payload above before analyzing."))

    try:
        raw = json.loads(json_payload)
        if not isinstance(raw, dict):
            return HTMLResponse(_alert("danger", "Payload must be a JSON object { }."))
    except json.JSONDecodeError as exc:
        return HTMLResponse(_alert("danger", f"Invalid JSON — {exc}"))

    # Apply vendor flattening so studio shows canonical field names
    fields: dict = raw
    if vendor:
        try:
            vp = _vendor_loader.load(vendor)
            fields = _vendor_loader.flatten_payload(vp, raw)
        except Exception as exc:
            return HTMLResponse(_alert("warning", f"Vendor profile error: {exc}. Showing raw fields."))

    # Filter out nested dicts/lists (they'd be flattened already if vendor is set)
    flat_fields = {k: v for k, v in fields.items() if not isinstance(v, (dict, list))}

    if not flat_fields:
        return HTMLResponse(_alert("warning", "No scalar fields detected. Try selecting a vendor profile if the payload has nested objects."))

    return HTMLResponse(_render_field_cards(flat_fields))


@app.get("/htmx/map-form", response_class=HTMLResponse)
async def htmx_map_form(field: str, index: int):
    return HTMLResponse(_render_map_detail(field, index))


@app.get("/htmx/clear-form", response_class=HTMLResponse)
async def htmx_clear_form():
    return HTMLResponse("")


@app.get("/htmx/target-values/{index}", response_class=HTMLResponse)
async def htmx_target_values(index: int, request: Request):
    target_field = request.query_params.get(f"field_{index}_target_field", "")
    values = TARGET_VALUES.get(target_field, [])
    opts = '<option value="">— select value —</option>'
    opts += "".join(f'<option value="{v}">{v} — {label}</option>' for v, label in values)
    return HTMLResponse(opts)


@app.post("/htmx/save-rules", response_class=HTMLResponse)
async def htmx_save_rules(request: Request):
    form = await request.form()
    client_name = str(form.get("client_name", "") or "").strip() or "*"

    # Collect all field_N_name entries to find how many fields were analyzed
    indices: list[int] = sorted(
        int(k.split("_")[1])
        for k in form.keys()
        if k.startswith("field_") and k.endswith("_name")
    )

    created = 0
    for i in indices:
        name = str(form.get(f"field_{i}_name", "") or "").strip()
        strategy = str(form.get(f"field_{i}_strategy", "context") or "context").strip()
        source_value = str(form.get(f"field_{i}_source_value", "*") or "*").strip() or "*"
        target_field = str(form.get(f"field_{i}_target_field", "") or "").strip()
        target_value = str(form.get(f"field_{i}_target_value", "") or "").strip()

        if not name or strategy not in ("map", "context", "ignore"):
            continue
        if strategy == "map" and not (target_field and target_value):
            continue  # skip incomplete map rules

        db_module.create_rule(client_name, name, source_value,
                              target_field, target_value, strategy)
        created += 1

    if created:
        db_module.sync_to_csv()
        invalidate_pipelines()
        return HTMLResponse(_alert("success", f"{created} rule{'s' if created != 1 else ''} saved. Pipeline reloaded."))
    return HTMLResponse(_alert("warning", "No valid rules to save. Make sure MAP rules have a target field and value selected."))


# ── HTMX: Simulator ───────────────────────────────────────────────────────────

@app.post("/htmx/simulate", response_class=HTMLResponse)
async def htmx_simulate(request: Request):
    form = await request.form()
    client_name = str(form.get("client_name", "") or "").strip()
    vendor = str(form.get("vendor", "") or "").strip()
    json_payload = str(form.get("json_payload", "") or "").strip()

    if not json_payload:
        return HTMLResponse(_alert("warning", "Paste a JSON payload to simulate."))

    try:
        raw = json.loads(json_payload)
        if not isinstance(raw, dict):
            return HTMLResponse(_alert("danger", "Payload must be a JSON object."))
    except json.JSONDecodeError as exc:
        return HTMLResponse(_alert("danger", f"Invalid JSON — {exc}"))

    try:
        pipeline = get_pipeline(vendor)
        work_order = ClientWorkOrder(
            client_name=client_name or "unknown",
            extra_fields=raw,
        )
        result = pipeline.run(work_order)
        db_module.log_work_order(client_name, vendor, raw, result)
        return HTMLResponse(_render_sim_results(result, client_name or "unknown"))
    except Exception as exc:
        return HTMLResponse(_alert("danger", f"Pipeline error: {exc}"))


# ── HTMX: Rules Manager ───────────────────────────────────────────────────────

@app.get("/htmx/rules-list", response_class=HTMLResponse)
async def htmx_rules_list(request: Request):
    client = request.query_params.get("filter_client", "") or None
    strategy = request.query_params.get("filter_strategy", "") or None
    filtered = db_module.get_rules(client_name=client, strategy=strategy)
    grouped = {
        "map":     [r for r in filtered if r["strategy"] == "map"],
        "context": [r for r in filtered if r["strategy"] == "context"],
        "ignore":  [r for r in filtered if r["strategy"] == "ignore"],
    }
    return HTMLResponse(_render_rules_groups(grouped))


@app.post("/htmx/rules/create", response_class=HTMLResponse)
async def htmx_rules_create(request: Request):
    form = await request.form()
    client_name = str(form.get("new_client", "") or "").strip() or "*"
    source_field = str(form.get("new_source_field", "") or "").strip()
    source_value = str(form.get("new_source_value", "") or "").strip() or "*"
    target_field = str(form.get("new_target_field", "") or "").strip()
    target_value = str(form.get("new_target_value", "") or "").strip()
    strategy = str(form.get("new_strategy", "context") or "context").strip()
    priority = int(form.get("new_priority", 5) or 5)

    if not source_field:
        return HTMLResponse(_alert("danger", "Source field is required."))

    db_module.create_rule(client_name, source_field, source_value,
                          target_field, target_value, strategy, priority)
    db_module.sync_to_csv()
    invalidate_pipelines()

    # Return the updated rules groups so the page refreshes
    grouped = db_module.get_rules_grouped()
    return HTMLResponse(
        _alert("success", "Rule added.") +
        _render_rules_groups(grouped)
    )


@app.delete("/htmx/rules/{rule_id}", response_class=HTMLResponse)
async def htmx_rules_delete(rule_id: int):
    db_module.delete_rule(rule_id)
    db_module.sync_to_csv()
    invalidate_pipelines()
    return HTMLResponse("")  # HTMX replaces target row with empty → removes it


# ── HTML rendering helpers ────────────────────────────────────────────────────

def _alert(kind: str, message: str) -> str:
    icons = {"success": "✓", "warning": "⚠", "danger": "✕", "info": "ℹ"}
    return (
        f'<div class="alert alert-{kind} d-flex align-items-center gap-2 mb-0">'
        f'<span>{icons.get(kind, "")}</span><span>{html.escape(message)}</span></div>'
    )


def _render_field_cards(fields: dict) -> str:
    cards = []
    for i, (name, value) in enumerate(fields.items()):
        val_str = html.escape(str(value)[:60] + ("…" if len(str(value)) > 60 else ""))
        safe_name = html.escape(name)
        cards.append(f"""
        <div class="field-row border-bottom" id="fc-{i}">
          <div class="d-flex align-items-center justify-content-between gap-3 flex-wrap">
            <div class="field-label">
              <code class="fw-bold">{safe_name}</code>
              <span class="badge bg-light text-secondary border ms-2 font-monospace small">{val_str}</span>
            </div>
            <div class="btn-group btn-group-sm flex-shrink-0" role="group">
              <input type="radio" class="btn-check" name="field_{i}_strategy"
                     id="f{i}m" value="map"
                     hx-get="/htmx/map-form?field={name}&index={i}"
                     hx-target="#fd-{i}" hx-trigger="change">
              <label class="btn btn-outline-success" for="f{i}m">Direct Map</label>

              <input type="radio" class="btn-check" name="field_{i}_strategy"
                     id="f{i}c" value="context" checked
                     hx-get="/htmx/clear-form"
                     hx-target="#fd-{i}" hx-trigger="change">
              <label class="btn btn-outline-primary" for="f{i}c">Context Cloud</label>

              <input type="radio" class="btn-check" name="field_{i}_strategy"
                     id="f{i}i" value="ignore"
                     hx-get="/htmx/clear-form"
                     hx-target="#fd-{i}" hx-trigger="change">
              <label class="btn btn-outline-secondary" for="f{i}i">Ignore</label>
            </div>
          </div>
          <input type="hidden" name="field_{i}_name" value="{safe_name}">
          <div id="fd-{i}" class="mt-2"></div>
        </div>""")

    count = len(fields)
    return f"""
    <div class="card shadow-sm">
      <div class="card-header d-flex justify-content-between align-items-center">
        <span class="fw-semibold">Field Assignments</span>
        <span class="badge bg-secondary">{count} field{'s' if count != 1 else ''} detected</span>
      </div>
      <div>{''.join(cards)}</div>
      <div class="card-footer bg-white border-top">
        <button form="studio-form" type="submit" class="btn btn-success">
          Save All Rules →
        </button>
        <small class="text-muted ms-3">Rules with no selection default to Context Cloud.</small>
      </div>
    </div>"""


def _render_map_detail(field_name: str, index: int) -> str:
    opts = "".join(
        f'<option value="{k}">{k}</option>' for k in TARGET_VALUES
    )
    return f"""
    <div class="map-detail rounded-end mt-2 p-3">
      <div class="row g-2 align-items-end">
        <div class="col-sm-4">
          <label class="form-label small mb-1 text-success fw-semibold">When value matches</label>
          <input type="text" class="form-control form-control-sm"
                 name="field_{index}_source_value" value="*"
                 placeholder="* or RTU-* or exact value">
        </div>
        <div class="col-sm-4">
          <label class="form-label small mb-1 text-success fw-semibold">Maps to CMMS field</label>
          <select class="form-select form-select-sm" name="field_{index}_target_field"
                  hx-get="/htmx/target-values/{index}"
                  hx-target="#tv-{index}"
                  hx-trigger="change"
                  hx-include="this">
            <option value="">— select field —</option>
            {opts}
          </select>
        </div>
        <div class="col-sm-4">
          <label class="form-label small mb-1 text-success fw-semibold">With value</label>
          <select class="form-select form-select-sm" name="field_{index}_target_value" id="tv-{index}">
            <option value="">— select field first —</option>
          </select>
        </div>
      </div>
    </div>"""


def _render_sim_results(result, client_name: str) -> str:
    conf = result.confidence_score
    if conf >= 0.85:
        conf_cls, badge_cls, badge_txt = "text-success", "bg-success", "Auto-Approved"
    elif conf >= 0.70:
        conf_cls, badge_cls, badge_txt = "text-warning", "bg-warning text-dark", "Review Required"
    else:
        conf_cls, badge_cls, badge_txt = "text-danger", "bg-danger", "Manual Review"

    # Direct mappings
    if result.mapped_fields:
        mapped_rows = "".join(
            f'<tr><td class="text-muted small">{html.escape(tf)}</td>'
            f'<td><code class="small">{html.escape(tv)}</code></td></tr>'
            for tf, tv in result.mapped_fields.items()
        )
        mapped_html = f'<table class="table table-sm mb-0"><tbody>{mapped_rows}</tbody></table>'
    else:
        mapped_html = '<p class="text-muted small mb-0">No fields were directly mapped — all went to AI inference.</p>'

    # Context cloud
    if result.context_fields:
        ctx_pills = "".join(
            f'<span class="badge rounded-pill bg-primary-subtle text-primary border border-primary-subtle me-1 mb-1">'
            f'{html.escape(str(k))}: {html.escape(str(v)[:40])}</span>'
            for k, v in result.context_fields.items()
        )
    else:
        ctx_pills = '<span class="text-muted small">No context fields.</span>'

    # Ignored fields
    if result.ignored_fields:
        ign_pills = "".join(
            f'<span class="badge rounded-pill bg-light text-muted border me-1 mb-1">{html.escape(str(f))}</span>'
            for f in result.ignored_fields
        )
    else:
        ign_pills = '<span class="text-muted small">No fields were ignored.</span>'

    # Final mapping
    m = result.mapping
    ai_flag = "" if not result.llm_called else '<span class="badge bg-info-subtle text-info border border-info-subtle ms-2 small">AI inferred</span>'
    final_rows = "".join(f"""
        <tr>
          <td class="text-muted small fw-semibold">{field}</td>
          <td><code class="small">{html.escape(value)}</code>{ai_flag if field not in result.mapped_fields else ''}</td>
        </tr>""" for field, value in [
        ("trade_id", m.trade_id.value),
        ("equipment_id", m.equipment_id.value),
        ("problem_type_id", m.problem_type_id.value),
        ("problem_code_id", m.problem_code_id.value),
    ])

    ms = result.inference_time_ms
    return f"""
    <div class="card shadow-sm border-0 result-card">
      <div class="card-header bg-white border-bottom d-flex align-items-center justify-content-between">
        <div>
          <span class="fw-bold">Pipeline Result</span>
          <span class="text-muted small ms-2">{html.escape(client_name)} · {ms:.0f}ms</span>
        </div>
        <div class="text-end">
          <div class="fs-3 fw-bold {conf_cls}">{int(conf * 100)}%</div>
          <span class="badge {badge_cls}">{badge_txt}</span>
        </div>
      </div>
      <div class="card-body p-0">

        <div class="result-section result-section--map px-4 py-3 border-bottom">
          <h6 class="section-label mb-2">
            <span class="me-2">🔒</span>Direct Mappings
            <small class="text-muted fw-normal">(locked before AI)</small>
            <span class="badge bg-success-subtle text-success border border-success-subtle ms-2">{len(result.mapped_fields)}</span>
          </h6>
          {mapped_html}
        </div>

        <div class="result-section result-section--context px-4 py-3 border-bottom">
          <h6 class="section-label mb-2">
            <span class="me-2">☁</span>Context Cloud
            <small class="text-muted fw-normal">(AI reasoning material)</small>
            <span class="badge bg-primary-subtle text-primary border border-primary-subtle ms-2">{len(result.context_fields)}</span>
          </h6>
          <div class="d-flex flex-wrap">{ctx_pills}</div>
        </div>

        <div class="result-section result-section--ignore px-4 py-3 border-bottom">
          <h6 class="section-label mb-2">
            <span class="me-2">🚫</span>Ignored Fields
            <span class="badge bg-secondary-subtle text-secondary border border-secondary-subtle ms-2">{len(result.ignored_fields)}</span>
          </h6>
          <div class="d-flex flex-wrap">{ign_pills}</div>
        </div>

        <div class="result-section result-section--output px-4 py-3 bg-light">
          <h6 class="section-label mb-2"><span class="me-2">📋</span>Final CMMS Mapping</h6>
          <table class="table table-sm mb-0"><tbody>{final_rows}</tbody></table>
        </div>

      </div>
    </div>"""


def _render_rules_groups(grouped: dict[str, list[dict]]) -> str:
    sections = [
        _render_rules_section("map", "Direct Mappings", "success",
                              ["Client", "Source Field", "When Value", "→ CMMS Field", "→ Value", "Priority", ""],
                              grouped["map"], show_target=True),
        _render_rules_section("context", "Context Cloud", "primary",
                              ["Client", "Source Field", "When Value", "Priority", ""],
                              grouped["context"], show_target=False),
        _render_rules_section("ignore", "Ignored Fields", "secondary",
                              ["Client", "Source Field", "When Value", "Priority", ""],
                              grouped["ignore"], show_target=False),
    ]
    return "".join(sections)


def _render_rules_section(strategy: str, label: str, color: str,
                           headers: list[str], rules: list[dict],
                           show_target: bool) -> str:
    header_html = "".join(f"<th>{h}</th>" for h in headers)
    rows = []
    for r in rules:
        target_cols = ""
        if show_target:
            target_cols = (
                f'<td><code class="small">{html.escape(r["target_field"])}</code></td>'
                f'<td><code class="small">{html.escape(r["target_value"])}</code></td>'
            )
        client_display = r["client_name"] if r["client_name"] != "*" else '<span class="text-muted">all clients</span>'
        rows.append(f"""
          <tr id="rule-row-{r['id']}">
            <td class="small">{client_display}</td>
            <td><code class="small">{html.escape(r['source_field'])}</code></td>
            <td><code class="small text-muted">{html.escape(r['source_value'])}</code></td>
            {target_cols}
            <td class="small text-muted">{r['priority']}</td>
            <td>
              <button class="btn btn-sm btn-outline-danger border-0 px-2 py-0"
                      hx-delete="/htmx/rules/{r['id']}"
                      hx-target="#rule-row-{r['id']}"
                      hx-swap="outerHTML"
                      hx-confirm="Delete this rule?"
                      title="Delete rule">✕</button>
            </td>
          </tr>""")

    rows_html = "".join(rows) if rows else f'<tr><td colspan="{len(headers)}" class="text-muted text-center py-3">No rules yet.</td></tr>'

    return f"""
    <div class="mb-4">
      <h6 class="fw-semibold text-{color} mb-2">
        {label}
        <span class="badge bg-{color}-subtle text-{color} border border-{color}-subtle ms-2">{len(rules)}</span>
      </h6>
      <div class="table-responsive">
        <table class="table table-sm table-hover align-middle mb-0 border rounded overflow-hidden">
          <thead class="table-light">
            <tr>{header_html}</tr>
          </thead>
          <tbody>{rows_html}</tbody>
        </table>
      </div>
    </div>"""
