"""
Pipeline Orchestrator
Wires Layer 1 (Pre-Processor), Layer 2 (LLM Inference), and Layer 3 (Post-Processor)
into a single callable pipeline.

Usage:
    pipeline = CMMSPipeline(engine_mode="mock")
    result = pipeline.run(ClientWorkOrder(
        asset="roof unit",
        issue="compressor grinding, blowing warm air",
        craft="mechanic",
    ))
    print(result.mapping.json(indent=2))
"""
from __future__ import annotations
from pathlib import Path
from typing import Optional

from schemas import ClientWorkOrder, PipelineResult
from pre_processor import PreProcessor, PreProcessResult
from prompt_builder import build_system_prompt, build_user_prompt
from inference_engine import get_engine, InferenceEngine, InferenceResult
from post_processor import PostProcessor, MetricsTracker


CONTROL_TABLE_PATH = Path(__file__).parent / "control_table.csv"


class CMMSPipeline:
    """
    The full Logic Sandwich: Rules → LLM → Validation.
    """

    def __init__(
        self,
        engine_mode: str = "mock",
        control_table_path: str | Path | None = None,
        auto_threshold: float = 0.85,
        **engine_kwargs,
    ):
        self.engine_mode = engine_mode
        self.control_table_path = Path(control_table_path or CONTROL_TABLE_PATH)

        # ── Layer 1 ──
        self.pre_processor = PreProcessor(self.control_table_path)

        # ── Layer 2 ──
        self.engine: InferenceEngine = get_engine(engine_mode, **engine_kwargs)

        # ── Layer 3 ──
        self.post_processor = PostProcessor(auto_threshold=auto_threshold)

        # ── Metrics ──
        self.metrics = MetricsTracker()

    def run(self, work_order: ClientWorkOrder) -> PipelineResult:
        """
        Process a single client work order through the full pipeline.
        """
        # ── Build raw fields dict from the work order ──
        raw_fields = {
            "asset": work_order.asset or "",
            "issue": work_order.issue or "",
            "craft": work_order.craft or "",
            "priority": work_order.priority or "",
            "location": work_order.location or "",
        }
        if work_order.raw_text:
            raw_fields["raw_text"] = work_order.raw_text

        # ── LAYER 1: Pre-Processing ──
        pre_result = self.pre_processor.process(
            client_name=work_order.client_name or work_order.client_id,
            raw_fields=raw_fields,
        )

        # ── Determine if we need the LLM ──
        llm_called = len(pre_result.remaining_fields) > 0

        if llm_called:
            # ── LAYER 2a: Build prompts ──
            system_prompt = build_system_prompt(
                hard_mapped=pre_result.hard_mapped,
                hints=pre_result.hints,
            )
            user_prompt = build_user_prompt(raw_fields)

            # ── LAYER 2b: Run inference ──
            inference_result = self.engine.infer(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
            )
        else:
            # Everything was hard-mapped — skip the LLM entirely
            inference_result = InferenceResult(
                raw_output="{}",
                parsed_json={},
                confidence_score=1.0,
                inference_time_ms=0.0,
                model_name="none (all fields hard-mapped)",
            )

        # ── LAYER 3: Post-Processing ──
        result = self.post_processor.process(
            original=work_order,
            inference_result=inference_result,
            pre_processed_fields=pre_result.hard_mapped,
            llm_called=llm_called,
        )

        # ── Track metrics ──
        self.metrics.record(result)

        return result

    def run_batch(self, work_orders: list[ClientWorkOrder]) -> list[PipelineResult]:
        """Process multiple work orders."""
        return [self.run(wo) for wo in work_orders]

    def get_metrics(self) -> dict:
        """Get aggregate pipeline metrics."""
        return self.metrics.summary()

    def reload_control_table(self) -> None:
        """Reload the control table (useful if business users edited the CSV)."""
        self.pre_processor = PreProcessor(self.control_table_path)
