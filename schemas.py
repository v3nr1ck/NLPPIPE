"""
Pydantic schemas for the CMMS NLP Pipeline.
These define the "locked" internal IDs that the LLM must output.
Update these enums when your CMMS schema changes — no retraining needed.
"""
from __future__ import annotations
from enum import Enum
from typing import Optional, Any
from pydantic import BaseModel, Field, ConfigDict


# ── Internal ID Enums ──────────────────────────────────────────────
# These are your CMMS's canonical values. The LLM is constrained to
# ONLY output from these exact sets. Add/remove entries freely.

class TradeEnum(str, Enum):
    hvac = "TRD_001_HVAC"
    plumbing = "TRD_002_PLMB"
    electrical = "TRD_003_ELEC"
    carpentry = "TRD_004_CARP"
    painting = "TRD_005_PAINT"
    general_maintenance = "TRD_006_GENM"
    fire_safety = "TRD_007_FIRE"
    pest_control = "TRD_008_PEST"
    unknown = "TRD_999_UNK"


class EquipmentEnum(str, Enum):
    rtu = "EQP_99_RTU"          # Rooftop Unit
    chiller = "EQP_88_CHLR"
    boiler = "EQP_77_BLR"
    sink = "EQP_01_SINK"
    toilet = "EQP_02_TOIL"
    urinal = "EQP_03_URNL"
    lighting = "EQP_10_LGHT"
    outlet = "EQP_11_OUTL"
    door = "EQP_20_DOOR"
    window = "EQP_21_WIND"
    ceiling = "EQP_30_CEIL"
    flooring = "EQP_31_FLOR"
    pump = "EQP_40_PUMP"
    compressor = "EQP_41_COMP"
    fan = "EQP_42_FAN"
    unknown = "EQP_00_UNK"


class ProblemTypeEnum(str, Enum):
    mechanical = "TYP_MECHANICAL"
    electrical_fault = "TYP_ELECTRICAL"
    plumbing_leak = "TYP_PLUMB_LEAK"
    clog = "TYP_CLOG"
    structural = "TYP_STRUCTURAL"
    hvac_cooling = "TYP_HVAC_COOLING"
    hvac_heating = "TYP_HVAC_HEATING"
    noise = "TYP_NOISE"
    odor = "TYP_ODOR"
    safety_hazard = "TYP_SAFETY"
    unknown = "TYP_UNKNOWN"


class ProblemCodeEnum(str, Enum):
    compressor_failure = "CODE_COMPRESSOR_FAIL"
    refrigerant_leak = "CODE_REFRIG_LEAK"
    condensate_overflow = "CODE_CONDENSATE_OVF"
    drain_clog = "CODE_DRAIN_CLOG"
    pipe_leak = "CODE_PIPE_LEAK"
    valve_failure = "CODE_VALVE_FAIL"
    short_circuit = "CODE_SHORT_CIRCUIT"
    breaker_trip = "CODE_BREAKER_TRIP"
    structural_crack = "CODE_STRUCT_CRACK"
    water_damage = "CODE_WATER_DAMAGE"
    emergency_overflow = "CODE_EMERGENCY_OVERFLOW"
    noise_abnormal = "CODE_NOISE_ABNORMAL"
    odor_chemical = "CODE_ODOR_CHEMICAL"
    unknown = "CODE_UNKNOWN"


# ── The Constrained Output Schema ───────────────────────────────────
# This is the exact JSON shape the LLM MUST produce. Outlines/vLLM
# will enforce this at the token level.

class CMMSMapping(BaseModel):
    """
    The output schema the LLM is forced to adhere to.
    Every field is constrained to the enums above.
    """
    model_config = ConfigDict(validate_assignment=True)

    trade_id: TradeEnum = Field(
        description="Internal trade/craft ID inferred from client input"
    )
    equipment_id: EquipmentEnum = Field(
        description="Internal equipment ID inferred from client input"
    )
    problem_type_id: ProblemTypeEnum = Field(
        description="Internal problem type ID inferred from client input"
    )
    problem_code_id: ProblemCodeEnum = Field(
        description="Internal problem code ID inferred from client input"
    )
    confidence_score: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Model's self-assessed confidence (0.0 - 1.0)"
    )
    reasoning: str = Field(
        default="",
        description="Brief chain-of-thought explanation for the mapping"
    )


# ── Pipeline Input/Output Wrappers ──────────────────────────────────

class ClientWorkOrder(BaseModel):
    """
    Dynamic client input — accepts ANY field names.

    Clients send arbitrary JSON payloads (e.g. 'equipment_tag', 'work_desc',
    'trade_code', 'building', etc.). This model captures them all in
    `extra_fields` while still allowing a raw text blob for unstructured input.

    Usage:
        wo = ClientWorkOrder(
            client_name="ACME Corp",
            extra_fields={
                "equipment_tag": "AHU-04-West",
                "work_desc": "loud rattling, temp sensor reading high",
                "trade_code": "MECH",
                "building": "HQ",
                "floor": "3",
                "sla_tier": "gold",
            }
        )
    """
    model_config = ConfigDict(extra="allow")

    client_id: str = Field(default="unknown")
    client_name: str = Field(default="")
    extra_fields: dict[str, Any] = Field(
        default_factory=dict,
        description="All client-specific fields. Values can be str, int, float, list, dict — anything the client API sends."
    )
    raw_text: Optional[str] = Field(
        default=None,
        description="Optional full-text blob if client sends unstructured descriptions"
    )

    # ── Convenience accessors (read from extra_fields) ──
    @property
    def all_fields(self) -> dict[str, Any]:
        """Return all extra_fields as-is (may contain nested dicts, lists, numbers)."""
        return dict(self.extra_fields)

    def get_field(self, key: str, default: Any = "") -> Any:
        """Get a field value case-insensitively, with a default."""
        key_lower = key.lower()
        for k, v in self.extra_fields.items():
            if k.lower() == key_lower:
                return v
        return default


class PipelineResult(BaseModel):
    """Final output from the pipeline, ready for CMMS API or human review."""
    model_config = ConfigDict(validate_assignment=True)

    original: ClientWorkOrder
    mapping: CMMSMapping
    mapped_fields: dict[str, str] = Field(
        default_factory=dict,
        description="Fields hard-mapped via control table (strategy=map) — bypassed LLM"
    )
    context_fields: dict[str, Any] = Field(
        default_factory=dict,
        description="Fields injected into LLM prompt for context (strategy=context) — not mapped"
    )
    ignored_fields: list[str] = Field(
        default_factory=list,
        description="Fields dropped via control table (strategy=ignore)"
    )
    llm_called: bool = Field(default=False)
    confidence_score: float = Field(default=0.0)
    requires_review: bool = Field(default=False)
    review_reason: str = Field(default="")
    inference_time_ms: float = Field(default=0.0)


# ── Evaluation / Metrics ────────────────────────────────────────────

class EvalMetrics(BaseModel):
    """Aggregate metrics for the pipeline's performance."""
    total_processed: int = 0
    auto_processed: int = 0        # confidence > threshold
    human_reviewed: int = 0        # routed to dashboard
    human_overridden: int = 0      # human changed the mapping
    accuracy_rate: float = 0.0     # auto_processed / total_processed
    avg_confidence: float = 0.0
    avg_inference_ms: float = 0.0
    field_fill_rate: float = 0.0   # % of fields the LLM successfully filled


# ── Helper: Build the "allowed values" dictionary for prompts ───────

def get_allowed_values_dict() -> dict[str, list[str]]:
    """Returns the full set of valid IDs, used to constrain LLM output."""
    return {
        "trade_id": [e.value for e in TradeEnum],
        "equipment_id": [e.value for e in EquipmentEnum],
        "problem_type_id": [e.value for e in ProblemTypeEnum],
        "problem_code_id": [e.value for e in ProblemCodeEnum],
    }


def get_readable_label(enum_class: type[Enum], value: str) -> str:
    """Convert an enum value back to its human-readable name."""
    for member in enum_class:
        if member.value == value:
            return member.name.replace("_", " ").title()
    return value
