"""Quick end-to-end test of the mock pipeline."""
from schemas import ClientWorkOrder
from pipeline import CMMSPipeline

pipe = CMMSPipeline(engine_mode="mock")

# Test 1: Known scenario (compressor)
print("=== TEST 1: Compressor Failure ===")
wo = ClientWorkOrder(
    client_name="ACME Corp",
    asset="roof unit",
    issue="compressor grinding, blowing warm air",
    craft="mechanic",
    priority="urgent",
)
r = pipe.run(wo)
print(f"  Trade: {r.mapping.trade_id.value}")
print(f"  Equip: {r.mapping.equipment_id.value}")
print(f"  ProbType: {r.mapping.problem_type_id.value}")
print(f"  ProbCode: {r.mapping.problem_code_id.value}")
print(f"  Confidence: {r.confidence_score:.0%}")
print(f"  Pre-mapped: {r.pre_processed_fields}")
print(f"  LLM Called: {r.llm_called}")
print(f"  Needs Review: {r.requires_review}")
print(f"  Reasoning: {r.mapping.reasoning}")

# Test 2: Plumbing
print()
print("=== TEST 2: Sink Overflow ===")
wo2 = ClientWorkOrder(
    client_name="GenericCo",
    asset="sink",
    issue="water seeping into hallway carpet, sink backed up",
    craft="plumber",
    priority="emergency",
)
r2 = pipe.run(wo2)
print(f"  Trade: {r2.mapping.trade_id.value}")
print(f"  Equip: {r2.mapping.equipment_id.value}")
print(f"  ProbType: {r2.mapping.problem_type_id.value}")
print(f"  ProbCode: {r2.mapping.problem_code_id.value}")
print(f"  Confidence: {r2.confidence_score:.0%}")
print(f"  Pre-mapped: {r2.pre_processed_fields}")
print(f"  Needs Review: {r2.requires_review}")
print(f"  Reasoning: {r2.mapping.reasoning}")

# Test 3: Vague
print()
print("=== TEST 3: Vague ===")
wo3 = ClientWorkOrder(
    client_name="Test Corp",
    asset="",
    issue="its broken",
    craft="",
    priority="",
)
r3 = pipe.run(wo3)
print(f"  Trade: {r3.mapping.trade_id.value}")
print(f"  Equip: {r3.mapping.equipment_id.value}")
print(f"  Confidence: {r3.confidence_score:.0%}")
print(f"  Needs Review: {r3.requires_review}")

# Metrics
print()
print("=== AGGREGATE METRICS ===")
for k, v in pipe.get_metrics().items():
    print(f"  {k}: {v}")

print()
print("ALL TESTS PASSED")
