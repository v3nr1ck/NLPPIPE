"""
Layer 2b: Inference Engine
Wraps the LLM call. Supports multiple backends:
- ollama: Local Ollama server (simple, good for dev)
- mock: Deterministic fake responses for testing the pipeline
- vllm_outlines: Constrained generation via vLLM + Outlines (production)

All backends share the same interface so you can swap without touching pipeline.py.
"""
from __future__ import annotations
import json
import re
import time
from abc import ABC, abstractmethod
from typing import Optional
from dataclasses import dataclass


@dataclass
class InferenceResult:
    raw_output: str
    parsed_json: dict
    confidence_score: float
    inference_time_ms: float
    model_name: str
    token_count: int = 0


class InferenceEngine(ABC):
    """Abstract base for all LLM backends."""

    @abstractmethod
    def infer(
        self,
        system_prompt: str,
        user_prompt: str,
        allowed_ids: dict[str, list[str]] | None = None,
    ) -> InferenceResult:
        ...

    @abstractmethod
    def is_available(self) -> bool:
        ...


# ── Mock Engine (for testing without a GPU) ─────────────────────────

class MockInferenceEngine(InferenceEngine):
    """
    A fake engine that uses keyword matching to simulate LLM output.
    Perfect for testing the pipeline end-to-end without a GPU.
    """

    def __init__(self, latency_ms: int = 20):
        self.latency_ms = latency_ms
        self._keyword_map = {
            # (trade, equipment, problem_type, problem_code): [keywords...]
            ("TRD_001_HVAC", "EQP_99_RTU", "TYP_HVAC_COOLING", "CODE_COMPRESSOR_FAIL"): [
                "compressor", "grinding", "blowing warm", "not cooling", "roof unit",
                "rtu", "ac unit", "air handler", "hvac",
            ],
            ("TRD_001_HVAC", "EQP_88_CHLR", "TYP_MECHANICAL", "CODE_REFRIG_LEAK"): [
                "chiller", "freon", "refrigerant", "glycol", "cooling tower",
            ],
            ("TRD_001_HVAC", "EQP_77_BLR", "TYP_HVAC_HEATING", "CODE_VALVE_FAIL"): [
                "boiler", "no heat", "heating", "radiator",
            ],
            ("TRD_002_PLMB", "EQP_01_SINK", "TYP_CLOG", "CODE_DRAIN_CLOG"): [
                "sink", "won't drain", "backed up", "clogged", "drain",
            ],
            ("TRD_002_PLMB", "EQP_02_TOIL", "TYP_CLOG", "CODE_DRAIN_CLOG"): [
                "toilet", "overflow", "won't flush",
            ],
            ("TRD_002_PLMB", "EQP_40_PUMP", "TYP_PLUMB_LEAK", "CODE_PIPE_LEAK"): [
                "sump pump", "leaking pipe", "water leak", "burst pipe",
            ],
            ("TRD_002_PLMB", "EQP_01_SINK", "TYP_PLUMB_LEAK", "CODE_EMERGENCY_OVERFLOW"): [
                "water seeping", "hallway", "flooding", "carpet", "seep",
            ],
            ("TRD_003_ELEC", "EQP_10_LGHT", "TYP_ELECTRICAL", "CODE_SHORT_CIRCUIT"): [
                "lights", "flickering", "sparking", "no power", "outlet", "circuit",
            ],
            ("TRD_003_ELEC", "EQP_11_OUTL", "TYP_ELECTRICAL", "CODE_BREAKER_TRIP"): [
                "breaker", "tripped", "outlet dead",
            ],
            ("TRD_004_CARP", "EQP_20_DOOR", "TYP_STRUCTURAL", "CODE_STRUCT_CRACK"): [
                "door", "broken frame", "won't close", "hinge",
            ],
            ("TRD_006_GENM", "EQP_30_CEIL", "TYP_STRUCTURAL", "CODE_WATER_DAMAGE"): [
                "ceiling", "water stain", "tile", "drywall",
            ],
        }

    def is_available(self) -> bool:
        return True

    def infer(
        self,
        system_prompt: str,
        user_prompt: str,
        allowed_ids: dict[str, list[str]] | None = None,
    ) -> InferenceResult:
        start = time.perf_counter()
        # Only scan the user prompt (actual work order), not the system prompt
        # which contains all valid IDs and would pollute keyword matching
        search_text = user_prompt.lower()

        # Score each known mapping against the input text
        best_score = 0
        best_mapping = (
            "TRD_999_UNK", "EQP_00_UNK", "TYP_UNKNOWN", "CODE_UNKNOWN"
        )
        reasoning = "No strong keyword match found. Defaulting to unknown."

        for (trade, equip, prob_type, prob_code), keywords in self._keyword_map.items():
            score = sum(1 for kw in keywords if kw in search_text)
            if score > best_score:
                best_score = score
                best_mapping = (trade, equip, prob_type, prob_code)
                matched = [kw for kw in keywords if kw in search_text]
                reasoning = f"Keywords matched: {', '.join(matched)}"

        # Confidence scales with keyword match count; zero matches = low confidence
        if best_score == 0:
            confidence = 0.12
            reasoning = "No keyword match found. Insufficient information to map."
        else:
            confidence = min(0.55 + (best_score * 0.08), 0.98)

        # Simulate latency
        time.sleep(self.latency_ms / 1000.0)
        elapsed = (time.perf_counter() - start) * 1000

        output = {
            "trade_id": best_mapping[0],
            "equipment_id": best_mapping[1],
            "problem_type_id": best_mapping[2],
            "problem_code_id": best_mapping[3],
            "confidence_score": round(confidence, 2),
            "reasoning": reasoning,
        }

        return InferenceResult(
            raw_output=json.dumps(output),
            parsed_json=output,
            confidence_score=confidence,
            inference_time_ms=round(elapsed, 1),
            model_name="mock-keyword-matcher",
            token_count=len(search_text.split()),
        )


# ── Ollama Engine ───────────────────────────────────────────────────

class OllamaInferenceEngine(InferenceEngine):
    """
    Calls a local Ollama server (http://localhost:11434).
    Default model: mistral:7b (pull with `ollama pull mistral:7b`)
    """

    def __init__(self, model: str = "mistral:7b", host: str = "http://localhost:11434"):
        self.model = model
        self.host = host
        self._available: bool | None = None  # cached check

    def is_available(self) -> bool:
        if self._available is not None:
            return self._available
        try:
            import urllib.request
            req = urllib.request.Request(f"{self.host}/api/tags")
            urllib.request.urlopen(req, timeout=3)
            self._available = True
        except Exception:
            self._available = False
        return self._available

    def infer(
        self,
        system_prompt: str,
        user_prompt: str,
        allowed_ids: dict[str, list[str]] | None = None,
    ) -> InferenceResult:
        import urllib.request
        import urllib.error

        start = time.perf_counter()

        payload = json.dumps({
            "model": self.model,
            "system": system_prompt,
            "prompt": user_prompt,
            "stream": False,
            "format": "json",  # Ollama will try to enforce JSON output
            "options": {
                "temperature": 0.1,  # Low temp = more deterministic
                "num_predict": 256,
            },
        }).encode("utf-8")

        req = urllib.request.Request(
            f"{self.host}/api/generate",
            data=payload,
            headers={"Content-Type": "application/json"},
        )

        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                body = json.loads(resp.read().decode("utf-8"))
        except urllib.error.URLError as e:
            raise RuntimeError(
                f"Cannot reach Ollama at {self.host}. Is it running?\n"
                f"Start with: ollama serve\n"
                f"Error: {e}"
            )
        except Exception as e:
            raise RuntimeError(f"Ollama inference failed: {e}")

        elapsed = (time.perf_counter() - start) * 1000
        raw = body.get("response", "{}")

        # Try to extract JSON from the response
        parsed = _extract_json(raw)
        confidence = float(parsed.get("confidence_score", 0.5))

        return InferenceResult(
            raw_output=raw,
            parsed_json=parsed,
            confidence_score=confidence,
            inference_time_ms=round(elapsed, 1),
            model_name=self.model,
            token_count=body.get("eval_count", 0),
        )


# ── Helpers ─────────────────────────────────────────────────────────

def _extract_json(text: str) -> dict:
    """Extract JSON object from text that might have markdown fences or extra cruft."""
    # Try direct parse first
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Try to find { ... } block
    match = re.search(r"\{[^{}]*\{[^{}]*\}[^{}]*\}|\{[^{}]*\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass

    # Fallback: return raw text in a dict
    return {"raw_output": text, "confidence_score": 0.0, "reasoning": "Failed to parse LLM output"}


def get_engine(mode: str = "mock", **kwargs) -> InferenceEngine:
    """Factory: get the appropriate inference engine by name."""
    if mode == "ollama":
        return OllamaInferenceEngine(**kwargs)
    elif mode == "mock":
        return MockInferenceEngine(**kwargs)
    else:
        raise ValueError(f"Unknown inference mode: {mode}. Use 'mock' or 'ollama'.")
