"""
Layer 3: Post-Processing Engine ("The Validation")
Validates LLM output against the Pydantic schema, computes confidence,
and routes results to either auto-approve or human review.
"""
from __future__ import annotations
from typing import Optional
from pydantic import ValidationError
from schemas import CMMSMapping, PipelineResult, ClientWorkOrder
from inference_engine import InferenceResult


# ── Confidence Thresholds ──────────────────────────────────────────

AUTO_APPROVE_THRESHOLD = 0.85     # >= this → auto-post to CMMS
REVIEW_THRESHOLD = 0.70           # >= this → flag for review (yellow)
# Below 0.70 → flag for manual intervention (red)


class PostProcessor:
    """
    Validates LLM output, computes confidence, and routes the result.
    """

    def __init__(
        self,
        auto_threshold: float = AUTO_APPROVE_THRESHOLD,
        review_threshold: float = REVIEW_THRESHOLD,
    ):
        self.auto_threshold = auto_threshold
        self.review_threshold = review_threshold

    def process(
        self,
        original: ClientWorkOrder,
        inference_result: InferenceResult,
        pre_processed_fields: dict[str, str],
        llm_called: bool,
    ) -> PipelineResult:
        """Validate and route a single inference result."""

        # ── 1. Validate against Pydantic schema ──
        mapping, validation_errors = self._validate(inference_result.parsed_json)

        # ── 2. Override with pre-processed (hard-mapped) fields ──
        # These are the "locked" fields from Layer 1 — the LLM can't override them
        if mapping:
            for field, value in pre_processed_fields.items():
                setattr(mapping, field, value)

        # ── 3. Compute effective confidence ──
        confidence = inference_result.confidence_score
        if validation_errors:
            confidence = max(0.0, confidence - 0.2)  # Penalize invalid output

        # ── 4. Route based on confidence ──
        requires_review = confidence < self.auto_threshold
        if confidence < self.review_threshold:
            review_reason = f"LOW CONFIDENCE ({confidence:.0%}) — manual intervention recommended"
        elif requires_review:
            review_reason = f"MEDIUM CONFIDENCE ({confidence:.0%}) — please verify"
        else:
            review_reason = ""

        if validation_errors:
            review_reason += f" | Validation issues: {validation_errors}"
            requires_review = True

        # ── 5. Build the result ──
        return PipelineResult(
            original=original,
            mapping=mapping or CMMSMapping(
                trade_id="TRD_999_UNK",
                equipment_id="EQP_00_UNK",
                problem_type_id="TYP_UNKNOWN",
                problem_code_id="CODE_UNKNOWN",
                confidence_score=confidence,
                reasoning=inference_result.parsed_json.get("reasoning", "Validation failed"),
            ),
            pre_processed_fields=pre_processed_fields,
            llm_called=llm_called,
            confidence_score=confidence,
            requires_review=requires_review,
            review_reason=review_reason,
            inference_time_ms=inference_result.inference_time_ms,
        )

    def _validate(self, parsed: dict) -> tuple[Optional[CMMSMapping], str]:
        """Attempt to parse LLM output into the CMMSMapping schema."""
        try:
            mapping = CMMSMapping(**parsed)
            return mapping, ""
        except ValidationError as e:
            errors = []
            for err in e.errors():
                field = ".".join(str(loc) for loc in err["loc"])
                errors.append(f"{field}: {err['msg']}")
            return None, "; ".join(errors)


# ── Metrics Accumulator ─────────────────────────────────────────────

class MetricsTracker:
    """Tracks aggregate pipeline metrics across many work orders."""

    def __init__(self):
        self.total = 0
        self.auto_approved = 0
        self.human_reviewed = 0
        self.human_overridden = 0
        self.total_confidence = 0.0
        self.total_inference_ms = 0.0
        self.fields_filled = 0
        self.total_llm_calls = 0

    def record(self, result: PipelineResult) -> None:
        self.total += 1
        self.total_confidence += result.confidence_score
        self.total_inference_ms += result.inference_time_ms

        if result.llm_called:
            self.total_llm_calls += 1

        if result.requires_review:
            self.human_reviewed += 1
        else:
            self.auto_approved += 1

        # Count non-unknown fields as "filled"
        m = result.mapping
        for val in [m.trade_id, m.equipment_id, m.problem_type_id, m.problem_code_id]:
            if val and "UNK" not in str(val):
                self.fields_filled += 1

    def record_override(self) -> None:
        self.human_overridden += 1

    def summary(self) -> dict:
        if self.total == 0:
            return {"error": "No results recorded yet"}

        total_fields = self.total * 4  # 4 fields per work order
        return {
            "total_processed": self.total,
            "auto_approved": self.auto_approved,
            "human_reviewed": self.human_reviewed,
            "human_overridden": self.human_overridden,
            "accuracy_rate": round(self.auto_approved / self.total, 3),
            "avg_confidence": round(self.total_confidence / self.total, 3),
            "avg_inference_ms": round(self.total_inference_ms / self.total, 1),
            "field_fill_rate": round(self.fields_filled / total_fields, 3) if total_fields else 0,
            "llm_call_rate": round(self.total_llm_calls / self.total, 3),
        }
