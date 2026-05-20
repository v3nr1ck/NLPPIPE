"""
RAG Pipeline — v1.3.0
======================
Retrieval-Augmented Generation + Constrained Generation engine.

Replaces the old inference_engine.py. Instead of fine-tuning, we:
  1. Embed dataset.jsonl into a vector store (Sentence Transformers)
  2. On each new ticket, retrieve the top-5 most similar historical examples
  3. Build a RAG prompt with those examples as in-context demonstrations
  4. Use vLLM + Outlines to force the LLM to output exactly the CMMSMapping schema

Architecture: RAG (retrieve → augment → generate) with constrained decoding.
"""
from __future__ import annotations
import json
import time
from pathlib import Path
from typing import Optional
from dataclasses import dataclass

from schemas import CMMSMapping


# ── Inference Result ───────────────────────────────────────────────

@dataclass
class InferenceResult:
    raw_output: str
    parsed_json: dict
    confidence_score: float
    inference_time_ms: float
    model_name: str
    token_count: int = 0


# ═══════════════════════════════════════════════════════════════════════
# RAG Engine (vLLM + Outlines)
# ═══════════════════════════════════════════════════════════════════════

class RAGEngine:
    """
    Full RAG pipeline: embed → retrieve → augment → constrained generate.

    Uses:
      - Sentence Transformers (all-MiniLM-L6-v2) for embedding/retrieval
      - vLLM for GPU-accelerated inference
      - Outlines for constrained JSON generation (guarantees valid CMMSMapping)
    """

    def __init__(
        self,
        model_name: str = "Qwen/Qwen2.5-7B-Instruct",
        dataset_path: str = "dataset.jsonl",
        top_k: int = 5,
        gpu_memory_utilization: float = 0.85,
        max_model_len: int = 4096,
    ):
        self.model_name = model_name
        self.top_k = top_k
        self._available: bool | None = None

        # ── 1. Load Sentence Transformer & embed dataset ──
        print(f"[RAG] Loading Sentence Transformer (all-MiniLM-L6-v2)...")
        from sentence_transformers import SentenceTransformer, util as st_util
        self.st_util = st_util
        self.embedder = SentenceTransformer("all-MiniLM-L6-v2")

        self.corpus_texts: list[str] = []
        self.corpus_outputs: list[str] = []
        self.corpus_embeddings = None

        dataset_file = Path(dataset_path)
        if dataset_file.exists():
            print(f"[RAG] Loading dataset from {dataset_path}...")
            with open(dataset_file, "r") as f:
                for line in f:
                    data = json.loads(line)
                    self.corpus_texts.append(data["input"])
                    self.corpus_outputs.append(data["output"])
            print(f"[RAG] Loaded {len(self.corpus_texts)} examples.")
        else:
            print(f"[RAG] Warning: {dataset_path} not found. RAG will have no context.")

        if self.corpus_texts:
            print("[RAG] Encoding corpus embeddings...")
            self.corpus_embeddings = self.embedder.encode(
                self.corpus_texts, convert_to_tensor=True
            )
        else:
            self.corpus_embeddings = None

        # ── 2. Load vLLM + Outlines constrained generator ──
        print(f"[RAG] Loading LLM {model_name} via vLLM + Outlines...")
        import outlines
        self.outlines_model = outlines.models.vllm(
            model_name,
            gpu_memory_utilization=gpu_memory_utilization,
            max_model_len=max_model_len,
        )
        self.generator = outlines.generate.json(self.outlines_model, CMMSMapping)
        print("[RAG] Constrained generator ready.")

    def is_available(self) -> bool:
        return True

    def retrieve(self, query: str) -> list[dict]:
        """
        Retrieve top-k most similar historical tickets from the vector store.
        Returns list of {"input": str, "output": str} dicts.
        """
        if self.corpus_embeddings is None or not self.corpus_texts:
            return []

        query_embedding = self.embedder.encode(query, convert_to_tensor=True)
        cos_scores = self.st_util.cos_sim(query_embedding, self.corpus_embeddings)[0]

        import torch
        actual_k = min(self.top_k, len(self.corpus_texts))
        top_results = torch.topk(cos_scores, k=actual_k)

        examples = []
        for score, idx in zip(top_results.values, top_results.indices):
            examples.append({
                "input": self.corpus_texts[idx],
                "output": self.corpus_outputs[idx],
                "similarity": round(float(score), 4),
            })
        return examples

    def infer(
        self,
        system_prompt: str = "",
        user_prompt: str = "",
        allowed_ids: dict[str, list[str]] | None = None,
    ) -> InferenceResult:
        """
        RAG inference: retrieve similar examples, build augmented prompt,
        run constrained generation.
        """
        start = time.perf_counter()

        # ── 1. Retrieve similar examples ──
        # Use the user prompt (actual work order text) as the search query
        query = user_prompt or system_prompt
        examples = self.retrieve(query)

        # ── 2. Build RAG-augmented prompt ──
        prompt = (
            "You are an expert facilities maintenance dispatcher. "
            "Map the client work order to the strict internal CMMS structure.\n\n"
        )

        if examples:
            prompt += "Here are examples of how similar tickets were mapped historically:\n"
            for i, ex in enumerate(examples, 1):
                prompt += f"Example {i}:\n"
                prompt += f"Input: {ex['input']}\n"
                prompt += f"Output: {ex['output']}\n\n"

        prompt += f"Now, map the following new ticket.\nInput: {query}\nOutput:"

        # ── 3. Constrained generation ──
        result: CMMSMapping = self.generator(prompt)
        elapsed = (time.perf_counter() - start) * 1000

        parsed = {
            "trade_id": result.trade_id.value,
            "equipment_id": result.equipment_id.value,
            "problem_type_id": result.problem_type_id.value,
            "problem_code_id": result.problem_code_id.value,
            "confidence_score": result.confidence_score,
        }

        return InferenceResult(
            raw_output=json.dumps(parsed),
            parsed_json=parsed,
            confidence_score=result.confidence_score,
            inference_time_ms=round(elapsed, 1),
            model_name=self.model_name,
        )


# ═══════════════════════════════════════════════════════════════════════
# Mock RAG Engine (for testing without GPU)
# ═══════════════════════════════════════════════════════════════════════

class MockRAGEngine:
    """
    Simulates RAG behavior without needing a GPU, vLLM, or Outlines.
    Uses keyword matching on the embedded dataset for retrieval,
    then returns the top match's output (or synthesizes one).
    Perfect for CI/testing/demos.
    """

    def __init__(self, dataset_path: str = "dataset.jsonl", top_k: int = 5, **_):
        self.top_k = top_k
        self.corpus_texts: list[str] = []
        self.corpus_outputs: list[dict] = []

        dataset_file = Path(dataset_path)
        if dataset_file.exists():
            with open(dataset_file, "r") as f:
                for line in f:
                    data = json.loads(line)
                    self.corpus_texts.append(data["input"])
                    try:
                        self.corpus_outputs.append(json.loads(data["output"]))
                    except (json.JSONDecodeError, KeyError):
                        self.corpus_outputs.append({})

        # Build a simple TF-IDF-like keyword index
        self._keyword_index: dict[str, list[int]] = {}
        for i, text in enumerate(self.corpus_texts):
            for word in set(text.lower().split()):
                if word not in self._keyword_index:
                    self._keyword_index[word] = []
                self._keyword_index[word].append(i)

    def is_available(self) -> bool:
        return True

    def retrieve(self, query: str) -> list[dict]:
        """Keyword-based retrieval simulating cosine similarity."""
        query_words = set(query.lower().split())
        scores: dict[int, int] = {}

        for word in query_words:
            for idx in self._keyword_index.get(word, []):
                scores[idx] = scores.get(idx, 0) + 1

        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        actual_k = min(self.top_k, len(ranked))

        examples = []
        for idx, score in ranked[:actual_k]:
            examples.append({
                "input": self.corpus_texts[idx],
                "output": json.dumps(self.corpus_outputs[idx]) if self.corpus_outputs[idx] else "{}",
                "similarity": min(score / max(len(query_words), 1), 0.99),
            })
        return examples

    def infer(
        self,
        system_prompt: str = "",
        user_prompt: str = "",
        allowed_ids: dict[str, list[str]] | None = None,
    ) -> InferenceResult:
        start = time.perf_counter()
        query = user_prompt or system_prompt
        examples = self.retrieve(query)

        # Return the top match if confidence is high enough
        if examples and examples[0]["similarity"] > 0.3:
            top = examples[0]
            try:
                parsed = json.loads(top["output"]) if isinstance(top["output"], str) else top["output"]
            except json.JSONDecodeError:
                parsed = {}
            confidence = min(float(top["similarity"]) + 0.1, 0.95)
        else:
            # No good match — return defaults
            parsed = {
                "trade_id": "TRD_001_HVAC",
                "equipment_id": "EQP_99_RTU",
                "problem_type_id": "TYP_MECHANICAL",
                "problem_code_id": "CODE_COMPRESSOR_FAIL",
            }
            confidence = 0.15

        elapsed = (time.perf_counter() - start) * 1000
        parsed["confidence_score"] = confidence

        return InferenceResult(
            raw_output=json.dumps(parsed),
            parsed_json=parsed,
            confidence_score=confidence,
            inference_time_ms=round(elapsed, 1),
            model_name="mock-rag",
        )


# ═══════════════════════════════════════════════════════════════════════
# Factory
# ═══════════════════════════════════════════════════════════════════════

def get_engine(mode: str = "mock", **kwargs) -> RAGEngine | MockRAGEngine:
    """Factory: get the appropriate inference engine by name."""
    if mode == "rag":
        return RAGEngine(**kwargs)
    elif mode == "mock":
        return MockRAGEngine(**kwargs)
    else:
        raise ValueError(f"Unknown engine mode: {mode}. Use 'mock' or 'rag'.")


# ── Quick test ─────────────────────────────────────────────────────
if __name__ == "__main__":
    print("Testing MockRAGEngine...")
    engine = MockRAGEngine(dataset_path="dataset.jsonl")

    test_ticket = (
        "Hey, we have a major issue in the men's room. "
        "The sink is backed up and won't drain, and now there is water "
        "starting to seep into the hallway carpet. We need someone here "
        "ASAP before the flooring is ruined."
    )

    result = engine.infer(user_prompt=test_ticket)
    print(f"Confidence: {result.confidence_score:.0%}")
    print(f"Time: {result.inference_time_ms:.1f}ms")
    print(f"Model: {result.model_name}")
    print(json.dumps(result.parsed_json, indent=2))
