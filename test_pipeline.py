"""End-to-end test v1.3.0 — RAG pipeline with mock engine."""
from schemas import ClientWorkOrder
from pipeline import CMMSPipeline

print("=" * 60)
print("v1.3.0 TESTS — RAG + Constrained Generation")
print("=" * 60)

# ── Test 1: Mock RAG engine — sink overflow ──
print("\n=== TEST 1: Mock RAG — Sink Overflow ===")
pipe = CMMSPipeline(engine_mode="mock")
wo = ClientWorkOrder(
    client_name="GenericCo",
    extra_fields={
        "asset": "Men's Room Sink",
        "issue": "sink backed up and won't drain, water seeping into hallway carpet",
        "craft": "plumber",
        "priority": "emergency",
    },
)
r = pipe.run(wo)
print(f"  Trade: {r.mapping.trade_id.value}")
print(f"  Equip: {r.mapping.equipment_id.value}")
print(f"  ProbType: {r.mapping.problem_type_id.value}")
print(f"  ProbCode: {r.mapping.problem_code_id.value}")
print(f"  Confidence: {r.confidence_score:.0%}")
print(f"  Mapped: {r.mapped_fields}")
print(f"  Needs Review: {r.requires_review}")

# ── Test 2: Mock RAG — electrical fault ──
print("\n=== TEST 2: Mock RAG — Electrical Fault ===")
wo2 = ClientWorkOrder(
    client_name="Test Corp",
    extra_fields={
        "asset": "Server Room",
        "issue": "lights flickering, burning smell near outlet, no power",
        "craft": "electrician",
        "priority": "emergency",
    },
)
r2 = pipe.run(wo2)
print(f"  Trade: {r2.mapping.trade_id.value}")
print(f"  Equip: {r2.mapping.equipment_id.value}")
print(f"  ProbType: {r2.mapping.problem_type_id.value}")
print(f"  ProbCode: {r2.mapping.problem_code_id.value}")
print(f"  Confidence: {r2.confidence_score:.0%}")
print(f"  Mapped: {r2.mapped_fields}")

# ── Test 3: With vendor profile (Maximo) ──
print("\n=== TEST 3: Mock RAG + Maximo Vendor Profile ===")
pipe3 = CMMSPipeline(engine_mode="mock", vendor="maximo")
wo3 = ClientWorkOrder(
    client_name="Bedford Plant",
    extra_fields={
        "DESCRIPTION": "Compressor grinding, RTU blowing warm air",
        "ASSETNUM": "RTU-04",
        "WOPRIORITY": 1,
        "WORKTYPE": "CM",
        "WPLABOR": {"CRAFT": "HVAC Tech"},
        "SITEID": "BEDFORD",
    },
)
r3 = pipe3.run(wo3)
print(f"  Trade: {r3.mapping.trade_id.value}")
print(f"  Equip: {r3.mapping.equipment_id.value}")
print(f"  ProbType: {r3.mapping.problem_type_id.value}")
print(f"  ProbCode: {r3.mapping.problem_code_id.value}")
print(f"  Confidence: {r3.confidence_score:.0%}")
print(f"  Context keys: {sorted(r3.context_fields.keys())}")
print(f"  Ignored: {r3.ignored_fields}")

# ── Metrics ──
print("\n=== AGGREGATE METRICS ===")
for k, v in pipe.get_metrics().items():
    print(f"  {k}: {v}")

# ── Available vendors ──
print("\n=== AVAILABLE VENDORS ===")
for v in pipe3.list_vendors():
    print(f"  {v}")

print("\nALL v1.3.0 TESTS PASSED")
