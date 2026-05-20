"""End-to-end test v1.2.0 — vendor profiles, nested flattening, canonical aliasing."""
from schemas import ClientWorkOrder
from pipeline import CMMSPipeline

print("=" * 60)
print("v1.2.0 TESTS — Vendor Profiles + Nested Flattening")
print("=" * 60)

# ── Test 1: Maximo payload (nested WPLABOR, all-caps field names) ──
print("\n=== TEST 1: IBM Maximo (nested WPLABOR, all-caps fields) ===")
pipe = CMMSPipeline(engine_mode="mock", vendor="maximo")
wo = ClientWorkOrder(
    client_name="Bedford Plant",
    extra_fields={
        "DESCRIPTION": "Pump seal replacement leaking oil",
        "ASSETNUM": "PUMP-045",
        "SITEID": "BEDFORD",
        "WOPRIORITY": 2,
        "STATUS": "WAPPR",
        "WORKTYPE": "CM",
        "FAILURECODE": "SEAL_LEAK",
        "PROBLEMCODE": "OIL_CONTAM",
        "WPLABOR": {"CRAFT": "Millwright"},
        "REPORTEDBY": "ops_lead",
        "ESTLABHRS": 4.5,
    },
)
r = pipe.run(wo)
print(f"  Trade (from WORKTYPE): {r.mapping.trade_id.value}")
print(f"  Equip: {r.mapping.equipment_id.value}")
print(f"  Mapped: {r.mapped_fields}")
print(f"  Context: {dict(list(r.context_fields.items())[:5])}")
print(f"  Ignored: {r.ignored_fields}")
print(f"  Confidence: {r.confidence_score:.0%}")
print(f"  Reasoning: {r.mapping.reasoning}")

# ── Test 2: Fiix payload ──
print("\n=== TEST 2: Fiix (camelCase, nested tasks) ===")
pipe2 = CMMSPipeline(engine_mode="mock", vendor="fiix")
wo2 = ClientWorkOrder(
    client_name="Rockwell Site 1",
    extra_fields={
        "description": "Conveyor motor grinding, belt slipping",
        "assetID": "CONV-12",
        "siteID": 1,
        "maintenanceType": "Reactive",
        "priority": "Highest",
        "tasks": [
            {"description": "Inspect motor bearings"},
            {"description": "Replace drive belt"},
        ],
        "customFields": [
            {"name": "safety_zone", "value": "high_risk"},
            {"name": "iso_cert_required", "value": "true"},
        ],
    },
)
r2 = pipe2.run(wo2)
print(f"  Trade (from maintenanceType): {r2.mapping.trade_id.value}")
print(f"  Equip: {r2.mapping.equipment_id.value}")
print(f"  Mapped: {r2.mapped_fields}")
print(f"  Context keys: {sorted(r2.context_fields.keys())}")
print(f"  Custom fields detected: {[k for k in r2.context_fields if k.startswith('cf_')]}")
print(f"  Confidence: {r2.confidence_score:.0%}")

# ── Test 3: Brightly payload (Labours[0].Craft, nested Scheduling) ──
print("\n=== TEST 3: Brightly (Labours array, nested Scheduling) ===")
pipe3 = CMMSPipeline(engine_mode="mock", vendor="brightly")
wo3 = ClientWorkOrder(
    client_name="City Facilities",
    extra_fields={
        "BriefDescription": "Roof leak causing ceiling damage in hallway",
        "AssetId": 112233,
        "PriorityId": 1,
        "Status": "Open",
        "WorkCategory": "Plumbing",
        "FailureCode": "ROOF_LEAK",
        "CauseCode": "STORM_DAMAGE",
        "Scheduling": {"TargetCompletion": "2026-05-24"},
        "Labours": [
            {"Craft": "Plumber", "Hours": 4},
            {"Craft": "Carpenter", "Hours": 2},
        ],
    },
)
r3 = pipe3.run(wo3)
print(f"  Trade (from WorkCategory): {r3.mapping.trade_id.value}")
print(f"  Equip: {r3.mapping.equipment_id.value}")
print(f"  Primary craft (Labours[0].Craft): {r3.context_fields.get('primary_craft', 'N/A')}")
print(f"  All crafts (Labours[*].Craft): {r3.context_fields.get('all_crafts', 'N/A')}")
print(f"  Target completion: {r3.context_fields.get('target_completion', 'N/A')}")
print(f"  Mapped: {r3.mapped_fields}")
print(f"  Confidence: {r3.confidence_score:.0%}")

# ── Test 4: No vendor profile (raw fields, backward compatible) ──
print("\n=== TEST 4: No Vendor Profile (backward compatibility) ===")
pipe4 = CMMSPipeline(engine_mode="mock")
wo4 = ClientWorkOrder(
    client_name="ACME Corp",
    extra_fields={
        "equipment_tag": "RTU-4",
        "work_desc": "compressor grinding, blowing warm air",
        "trade_code": "MECH",
        "requested_by": "janet",
    },
)
r4 = pipe4.run(wo4)
print(f"  Trade: {r4.mapping.trade_id.value}")
print(f"  Equip: {r4.mapping.equipment_id.value}")
print(f"  Mapped: {r4.mapped_fields}")
print(f"  Confidence: {r4.confidence_score:.0%}")

# ── List available vendors ──
print("\n=== AVAILABLE VENDOR PROFILES ===")
for v in pipe.list_vendors():
    p = pipe.vendor_loader.load(v)
    print(f"  {v}: {p.vendor_name}")

print("\nALL v1.2.0 TESTS PASSED")
