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


class EquipmentEnum(str, Enum):
    rtu = "EQP_99_RTU"
    chiller = "EQP_88_CHLR"
    boiler = "EQP_77_BLR"
    sink = "EQP_11_SINK"
    unknown = "EQP_00_UNK"


class ProblemTypeEnum(str, Enum):
    mechanical = "TYP_MECHANICAL"
    clog = "TYP_CLOG"
    electrical_fault = "TYP_ELEC_FAULT"


class ProblemCodeEnum(str, Enum):
    compressor_fail = "CODE_COMPRESSOR_FAIL"
    emergency_overflow = "CODE_EMERGENCY_OVERFLOW"
    power_loss = "CODE_POWER_LOSS"


# ── The Constrained Output Schema ───────────────────────────────────
# This is the exact JSON shape the LLM MUST produce. Outlines/vLLM
# will enforce this at the token level.

class CMMSMapping(BaseModel):
    """
    The output schema for constrained generation.
    Outlines/vLLM enforces this exact shape at the token level.
    """
    model_config = ConfigDict(validate_assignment=True)

    trade_id: TradeEnum
    equipment_id: EquipmentEnum
    problem_type_id: ProblemTypeEnum
    problem_code_id: ProblemCodeEnum
    confidence_score: float


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
