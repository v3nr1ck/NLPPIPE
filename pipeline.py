"""
Pipeline Orchestrator — v1.2.0
================================
Wires Layer 1 (Pre-Processor), Layer 2 (LLM Inference), and Layer 3 (Post-Processor)
into a single callable pipeline. Now supports vendor profiles for field aliasing
and nested payload flattening.

Usage:
    # Simple (no vendor profile — all fields treated as-is):
    pipeline = CMMSPipeline(engine_mode="mock")
    result = pipeline.run(ClientWorkOrder(
        client_name="ACME Corp",
        extra_fields={"equipment_tag": "RTU-4", "work_desc": "compressor grinding"},
    ))

    # With vendor profile (auto-flattens nested payloads, aliases fields):
    pipeline = CMMSPipeline(engine_mode="mock", vendor="maximo")
    result = pipeline.run(ClientWorkOrder(
        client_name="Bedford Plant",
        extra_fields={
            "DESCRIPTION": "Pump seal replacement",
            "ASSETNUM": "PUMP-045",
            "WOPRIORITY": 2,
            "SITEID": "BEDFORD",
            "WPLABOR": {"CRAFT": "Millwright"},
        },
    ))
"""
from __future__ import annotations
from pathlib import Path
from typing import Optional

from schemas import ClientWorkOrder, PipelineResult
from pre_processor import PreProcessor, PreProcessResult
from prompt_builder import build_system_prompt, build_user_prompt
from inference_engine import get_engine, InferenceEngine, InferenceResult
from post_processor import PostProcessor, MetricsTracker
from vendor_profile import VendorProfileLoader, VendorProfile


CONTROL_TABLE_PATH = Path(__file__).parent / "control_table.csv"
VENDOR_PROFILES_DIR = Path(__file__).parent / "vendor_profiles"


class CMMSPipeline:
    """
    The full Logic Sandwich: Rules → LLM → Validation.

    Parameters:
        engine_mode: "mock" or "ollama"
        vendor: Optional vendor profile key (e.g. "maximo", "fiix", "upkeep")
                When set, the pipeline auto-flattens nested payloads and aliases
                vendor field names to canonical names before processing.
        control_table_path: Path to the business rules CSV
        auto_threshold: Confidence threshold for auto-approval
    """

    def __init__(
        self,
        engine_mode: str = "mock",
        vendor: str | None = None,
        control_table_path: str | Path | None = None,
        auto_threshold: float = 0.85,
        **engine_kwargs,
    ):
        self.engine_mode = engine_mode
        self.vendor_key = vendor
        self.control_table_path = Path(control_table_path or CONTROL_TABLE_PATH)

        # ── Vendor Profile (optional) ──
        self.vendor_loader = VendorProfileLoader(VENDOR_PROFILES_DIR)
        self.vendor_profile: VendorProfile | None = None
        if vendor:
            self.vendor_profile = self.vendor_loader.load(vendor)

        # ── Layer 1 ──
        self.pre_processor = PreProcessor(
            self.control_table_path,
            vendor_profile=self.vendor_profile,
        )

        # ── Layer 2 ──
        self.engine: InferenceEngine = get_engine(engine_mode, **engine_kwargs)

        # ── Layer 3 ──
        self.post_processor = PostProcessor(auto_threshold=auto_threshold)

        # ── Metrics ──
        self.metrics = MetricsTracker()

    def run(self, work_order: ClientWorkOrder) -> PipelineResult:
        """
        Process a single client work order through the full pipeline.
        If a vendor profile is loaded, the payload is flattened and aliased first.
        """
        # ── 0. Flatten payload if vendor profile is active ──
        if self.vendor_profile:
            all_fields = self.vendor_loader.flatten_payload(
                self.vendor_profile,
                work_order.all_fields,
            )
        else:
            all_fields = work_order.all_fields

        # ── LAYER 1: Pre-Processing ──
        pre_result = self.pre_processor.process(
            client_name=work_order.client_name or work_order.client_id,
            extra_fields=all_fields,
        )

        # ── Determine if we need the LLM ──
        llm_called = len(pre_result.remaining_for_llm) > 0

        if llm_called:
            # ── LAYER 2a: Build prompts ──
            system_prompt = build_system_prompt(
                mapped_fields=pre_result.mapped,
            )
            user_prompt = build_user_prompt(
                context_fields=pre_result.context,
                raw_text=work_order.raw_text,
            )

            # ── LAYER 2b: Run inference ──
            inference_result = self.engine.infer(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
            )
        else:
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
            mapped_fields=pre_result.mapped,
            context_fields=pre_result.context,
            ignored_fields=pre_result.ignored,
            llm_called=llm_called,
        )

        self.metrics.record(result)
        return result

    def run_batch(self, work_orders: list[ClientWorkOrder]) -> list[PipelineResult]:
        return [self.run(wo) for wo in work_orders]

    def get_metrics(self) -> dict:
        return self.metrics.summary()

    def reload_control_table(self) -> None:
        self.pre_processor = PreProcessor(
            self.control_table_path,
            vendor_profile=self.vendor_profile,
        )

    def list_vendors(self) -> list[str]:
        """List all available vendor profiles."""
        return self.vendor_loader.list_available()

    def load_vendor(self, vendor_key: str) -> None:
        """Hot-swap the vendor profile."""
        self.vendor_key = vendor_key
        self.vendor_profile = self.vendor_loader.load(vendor_key)
        self.pre_processor = PreProcessor(
            self.control_table_path,
            vendor_profile=self.vendor_profile,
        )
