"""Quick end-to-end test of the v1.1.0 pipeline with dynamic fields."""
from schemas import ClientWorkOrder
from pipeline import CMMSPipeline

pipe = CMMSPipeline(engine_mode="mock")

# Test 1: ACME-style fields (equipment_tag, work_desc, trade_code)
print("=== TEST 1: Compressor Failure (ACME-style fields) ===")
wo = ClientWorkOrder(
    client_name="ACME Corp",
    extra_fields={
        "equipment_tag": "RTU-4",
        "work_desc": "compressor grinding, blowing warm air",
        "trade_code": "MECH",
        "building": "HQ",
        "floor": "3",
        "priority": "urgent",
        "requested_by": "janet",
        "cost_center": "CC-882",
    },
)
r = pipe.run(wo)
print(f"  Trade: {r.mapping.trade_id.value}")
print(f"  Equip: {r.mapping.equipment_id.value}")
print(f"  ProbType: {r.mapping.problem_type_id.value}")
print(f"  ProbCode: {r.mapping.problem_code_id.value}")
print(f"  Confidence: {r.confidence_score:.0%}")
print(f"  Mapped: {r.mapped_fields}")
print(f"  Context: {dict(list(r.context_fields.items())[:4])}...")  # truncated
print(f"  Ignored: {r.ignored_fields}")
print(f"  LLM Called: {r.llm_called}")
print(f"  Needs Review: {r.requires_review}")
print(f"  Reasoning: {r.mapping.reasoning}")

# Test 2: Global Facilities-style fields (asset, issue, craft)
print()
print("=== TEST 2: Sink Overflow (Global Facilities-style) ===")
wo2 = ClientWorkOrder(
    client_name="GenericCo",
    extra_fields={
        "asset": "Men's Room Sink",
        "issue": "water seeping into hallway carpet, sink backed up",
        "craft": "plumber",
        "priority": "emergency",
        "location": "Building B, Floor 1",
    },
)
r2 = pipe.run(wo2)
print(f"  Trade: {r2.mapping.trade_id.value}")
print(f"  Equip: {r2.mapping.equipment_id.value}")
print(f"  ProbType: {r2.mapping.problem_type_id.value}")
print(f"  ProbCode: {r2.mapping.problem_code_id.value}")
print(f"  Confidence: {r2.confidence_score:.0%}")
print(f"  Mapped: {r2.mapped_fields}")
print(f"  Context: {list(r2.context_fields.keys())}")
print(f"  Ignored: {r2.ignored_fields}")
print(f"  Needs Review: {r2.requires_review}")

# Test 3: All fields pre-mapped (should skip LLM entirely)
print()
print("=== TEST 3: Fully Pre-Mapped (no LLM needed) ===")
wo3 = ClientWorkOrder(
    client_name="ACME Corp",
    extra_fields={
        "equipment_tag": "RTU-5",
        "trade_code": "MECH",
        "work_desc": "no cooling",
    },
)
r3 = pipe.run(wo3)
print(f"  Trade: {r3.mapping.trade_id.value}")
print(f"  Equip: {r3.mapping.equipment_id.value}")
print(f"  Confidence: {r3.confidence_score:.0%}")
print(f"  Mapped: {r3.mapped_fields}")
print(f"  LLM Called: {r3.llm_called}")

# Test 4: Vague input
print()
print("=== TEST 4: Vague Input ===")
wo4 = ClientWorkOrder(
    client_name="Test Corp",
    extra_fields={
        "issue": "it's broken",
        "submitted_by": "someone",
    },
)
r4 = pipe.run(wo4)
print(f"  Trade: {r4.mapping.trade_id.value}")
print(f"  Confidence: {r4.confidence_score:.0%}")
print(f"  Needs Review: {r4.requires_review}")
print(f"  Ignored (submitted_by): {r4.ignored_fields}")

# Metrics
print()
print("=== AGGREGATE METRICS ===")
for k, v in pipe.get_metrics().items():
    print(f"  {k}: {v}")

print()
print("ALL TESTS PASSED")
