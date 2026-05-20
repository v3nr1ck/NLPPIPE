"""
Fine-Tuning Script — Unsloth + QLoRA
====================================
Trains Mistral-7B (or similar) to act as a CMMS field mapper.
Uses the dataset.jsonl file as training data.

Usage:
    python train.py

Requirements (install first):
    pip install unsloth[colab-new] trl peft accelerate bitsandbytes

On an RTX 5090 (32GB VRAM), this completes in ~15-20 minutes for 500 examples.
VRAM usage stays under 12GB due to 4-bit quantization.
"""
from __future__ import annotations
import json
from pathlib import Path
from typing import Optional


# ── Configuration ────────────────────────────────────────────────────

# Model to fine-tune (Apache 2.0 licensed)
MODEL_NAME = "unsloth/mistral-7b-v0.3-bnb-4bit"
# Alternative: "unsloth/Qwen2.5-7B-bnb-4bit"

# Training data
DATASET_PATH = Path(__file__).parent / "dataset.jsonl"

# Output directory for the fine-tuned adapter
OUTPUT_DIR = Path(__file__).parent / "cmms_adapter"

# Training hyperparameters
MAX_SEQ_LENGTH = 2048
LORA_R = 16
LORA_ALPHA = 16
BATCH_SIZE = 4
GRADIENT_ACCUMULATION = 4
WARMUP_STEPS = 5
MAX_STEPS = 60
LEARNING_RATE = 2e-4

# Quantization for export (q8_0 = 8-bit, good balance of size/quality)
EXPORT_QUANT = "q8_0"


# ── Prompt Formatter ─────────────────────────────────────────────────

PROMPT_TEMPLATE = """<|system|>
You are an expert CMMS data mapper. Map the client work order to the exact internal IDs.
Output ONLY valid JSON with these keys: trade_id, equipment_id, problem_type_id, problem_code_id, confidence_score, reasoning.
</s>
<|user|>
{input}
</s>
<|assistant|>
{output}</s>"""


def format_dataset(jsonl_path: Path, output_path: Optional[Path] = None) -> Path:
    """
    Convert raw dataset.jsonl into the prompt format Unsloth/SFT expects.
    Each record gets a 'text' field with the full formatted prompt.
    """
    records = []
    with open(jsonl_path, "r") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            formatted = PROMPT_TEMPLATE.format(
                input=record["input"],
                output=record["output"],
            )
            records.append({"text": formatted})

    out_path = output_path or (jsonl_path.parent / "dataset_formatted.jsonl")
    with open(out_path, "w") as f:
        for rec in records:
            f.write(json.dumps(rec) + "\n")

    print(f"✅ Formatted {len(records)} records → {out_path}")
    return out_path


# ── Training ─────────────────────────────────────────────────────────

def train() -> None:
    """Run the fine-tuning job."""
    print("=" * 60)
    print("🐶 CMMS Adapter — Fine-Tuning with Unsloth")
    print(f"   Model: {MODEL_NAME}")
    print(f"   Dataset: {DATASET_PATH}")
    print(f"   Output: {OUTPUT_DIR}")
    print("=" * 60)

    # Check dependencies
    try:
        from unsloth import FastLanguageModel
        import torch
    except ImportError:
        print("❌ Unsloth not installed! Run:")
        print("   pip install unsloth[colab-new] trl peft accelerate bitsandbytes")
        return

    # Format dataset
    formatted_path = format_dataset(DATASET_PATH)

    # Load model in 4-bit
    print("\n📦 Loading model (4-bit quantized)...")
    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=MODEL_NAME,
        max_seq_length=MAX_SEQ_LENGTH,
        load_in_4bit=True,
    )

    # Add LoRA adapters
    print("🔧 Attaching LoRA adapters...")
    model = FastLanguageModel.get_peft_model(
        model,
        r=LORA_R,
        target_modules=[
            "q_proj", "k_proj", "v_proj", "o_proj",
            "gate_proj", "up_proj", "down_proj",
        ],
        lora_alpha=LORA_ALPHA,
        lora_dropout=0,
        use_gradient_checkpointing="unsloth",
    )

    # Load dataset
    from datasets import load_dataset
    dataset = load_dataset("json", data_files=str(formatted_path), split="train")
    print(f"📊 Loaded {len(dataset)} training examples")

    # Train
    from trl import SFTTrainer
    from transformers import TrainingArguments

    trainer = SFTTrainer(
        model=model,
        tokenizer=tokenizer,
        train_dataset=dataset,
        dataset_text_field="text",
        max_seq_length=MAX_SEQ_LENGTH,
        args=TrainingArguments(
            per_device_train_batch_size=BATCH_SIZE,
            gradient_accumulation_steps=GRADIENT_ACCUMULATION,
            warmup_steps=WARMUP_STEPS,
            max_steps=MAX_STEPS,
            learning_rate=LEARNING_RATE,
            fp16=not torch.cuda.is_bf16_supported(),
            bf16=torch.cuda.is_bf16_supported(),
            logging_steps=1,
            output_dir=str(OUTPUT_DIR),
            save_steps=20,
            save_total_limit=2,
        ),
    )

    print("\n🚀 Starting training...")
    trainer.train()
    print("✅ Training complete!")

    # Save GGUF for Ollama
    print(f"\n💾 Saving GGUF ({EXPORT_QUANT} quantization)...")
    model.save_pretrained_gguf(
        str(OUTPUT_DIR / "gguf"),
        tokenizer,
        quantization_method=EXPORT_QUANT,
    )
    print(f"✅ GGUF saved to {OUTPUT_DIR / 'gguf'}")

    # Save LoRA adapter
    model.save_pretrained(str(OUTPUT_DIR / "lora"))
    tokenizer.save_pretrained(str(OUTPUT_DIR / "lora"))
    print(f"✅ LoRA adapter saved to {OUTPUT_DIR / 'lora'}")

    print("\n" + "=" * 60)
    print("🎉 Done! To use in Ollama:")
    print(f"   1. Copy the GGUF file: {OUTPUT_DIR / 'gguf'}")
    print(f"   2. Create a Modelfile pointing to it")
    print(f"   3. Run: ollama create cmms-mapper -f Modelfile")
    print(f"   4. Then: ollama run cmms-mapper")
    print("=" * 60)


if __name__ == "__main__":
    train()
