### **1\. Assessment of Strategy**

Your reasoning is logically sound. Hard-coded field mapping in ETL (Extract, Transform, Load) processes is notoriously brittle, especially in fragmented industries like facilities services where "AHU Repair" in one system might be "HVAC \- Air Handler Maint" in another.  
**Why an LLM/NLP approach works here:**

* **Semantic Mapping:** Instead of matching strings (exact characters), you are matching **intent** and **context**.  
* **Resilience:** If a client changes "Plumbing Leak" to "Water Emission Event," a semantically aware model recognizes the relationship without manual re-mapping.  
* **Normalization:** You can use the model to ingest "messy" unstructured input and output a valid, schema-compliant JSON object for your CMMS API.

**Better Alternative to Fine-Tuning:**  
Before committing to a full fine-tune, consider **RAG (Retrieval-Augmented Generation)** or **Few-Shot In-Context Learning**. You provide the model with a "dictionary" of your internal CMMS valid values in the system prompt. This is often more flexible than a fine-tuned adapter because you can update your internal schema without retraining the model.

### **2\. Truly Open-Source LLMs for Fine-Tuning**

While Llama 3.1 and Gemma 2 are popular, they use custom "community licenses." For strictly open-source (Apache 2.0 or MIT) models optimized for fine-tuning:

* **Mistral-7B-v0.3 (Apache 2.0):** The industry standard for 7B models. Highly efficient, supports Function Calling natively, and has a large ecosystem for fine-tuning.  
* **Qwen2.5-7B / 14B (Apache 2.0):** Currently leading benchmarks for reasoning and coding tasks in the open-weights category. Excellent at following strict JSON formatting.  
* **Phi-3.5-mini (MIT):** A 3.8B parameter model. Small enough to run with near-zero latency on your hardware while being surprisingly capable of logic-heavy mapping.  
* **Falcon 2 11B (Apache 2.0):** A solid middle-ground model if 7B is too simple but 27B+ is too heavy for high-speed inference.

### **3\. Tooling and Hardware Requirements**

Since you already possess an **NVIDIA RTX 5090 (32GB VRAM)**, you have sufficient overhead to handle both training (via QLoRA) and high-throughput inference locally.

#### **Hardware**

* **GPU:** Your RTX 5090 is ideal. 32GB VRAM allows you to fine-tune a 14B parameter model using 4-bit quantization (QLoRA) or run a 30B+ model for inference.  
* **Storage:** You already have a 4TB NVMe; ensure you have \~500GB free for model weights and datasets.  
* **RAM:** 64GB+ system RAM is recommended to handle data preprocessing without bottlenecks.

#### **Software & Tooling**

* **Fine-Tuning Framework:**  
  * **Unsloth:** The fastest library for fine-tuning Llama/Mistral/Phi. It reduces VRAM usage by 70% and is significantly faster than standard Hugging Face scripts.  
  * **Axolotl:** A configuration-based tool that simplifies the fine-tuning pipeline.  
* **Inference/Serving:**  
  * **vLLM:** The highest throughput engine for serving models. It utilizes PagedAttention to handle multiple API requests simultaneously.  
  * **Ollama:** Since you already use this, it's the easiest way to deploy your fine-tuned "adapter" (as a GGUF file) for internal use.  
* **NLP Pipeline:**  
  * **Sentence-Transformers:** Use this for the initial "vector match." If the client input has a 95% semantic match to an existing field, skip the LLM to save compute. Use the LLM only for the "hard" cases (the remaining 5%).  
  * **Pydantic:** Use this in Python to enforce that the LLM output strictly matches your CMMS API schema.

#### **Facilities Services Dataset**

To make this work, you need a **Mapping Dataset**. You will need to create a JSONL file containing roughly 500–2,000 examples of:

* **Input:** "Client term: \[Leaking Pipe\], Priority: \[Urgent\]"  
* **Output:** "{ 'internal\_category': 'Plumbing', 'internal\_priority': 'P1', 'trade': 'Plumber' }"

This dataset will be the "truth" the model learns to replicate.  
How many unique fields and values are you currently attempting to map across these CMMS platforms?

This clarification changes the architecture. You are not just translating vocabulary; you are doing **Multi-Label Classification** and **Schema Imputation** (inferring missing data like 'Trade' from a free-text description).  
Because your 4 internal fields (Trade, Equipment, Problem Type, Problem Code) are locked to unique IDs, your biggest risk is the LLM hallucinating an invalid ID, which will immediately break your API insertion.  
Here is the precise architectural approach and tooling required to solve this.

### **The Architecture: Constrained Generation**

You cannot rely on a standard LLM prompt to reliably output exact, locked unique IDs 100% of the time. You must use **Constrained Generation** (also called Structured Generation).  
Constrained generation intercepts the LLM's output at the token level and mathematically forces it to only generate text that matches a specific JSON schema or Regex pattern that you define.  
**Workflow:**

1. **Ingest:** Adapter receives client payload (e.g., {"asset": "Chiller 2", "issue": "freon leak, pressure dropping"}).  
2. **Contextualize (Optional but recommended):** If your internal database of "Problem Codes" is massive (thousands of rows), run a fast vector search (using Sentence-Transformers) on the word "freon leak" against your internal database to retrieve the top 10 most relevant internal Problem Codes.  
3. **Prompt Construction:** Pass the client payload and the allowed internal IDs to the LLM.  
4. **Constrained Inference:** The LLM evaluates the text, but the inference engine physically restricts its output to your exact internal unique IDs.  
5. **Output:** A guaranteed-valid JSON payload mapping to your 4 locked fields.

### **Required Tooling for Constrained Generation**

Since you are running locally on an RTX 5090, you have the ideal hardware for this.

1. **Inference Engine:** Drop Ollama for this specific production pipeline and use **vLLM** or **SGLang**. They are enterprise-grade, support massive concurrency, and most importantly, have native, high-performance support for Constrained Decoding via JSON schemas.  
2. **Constrained Generation Library:** **Outlines** (integrates with vLLM). It compiles your Pydantic models (your strict internal schema) into a finite-state machine. The LLM is forced to follow the paths of that machine. It guarantees zero parsing errors.  
3. **The Model:** **Qwen2.5-7B-Instruct** or **Mistral-7B-Instruct-v0.3**. Both are Apache 2.0 and highly optimized for following strict structural instructions. You do not need a massive model for this; a fast, smart 7B model running in fp16 will process these payloads in milliseconds.

### **Example Implementation Logic**

Instead of a fine-tune, you define your internal database structure in Python using Pydantic:  
Python  
from pydantic import BaseModel, enum

\# Define your locked internal values  
class TradeEnum(str, enum.Enum):  
    hvac \= "TRD\_001\_HVAC"  
    plumbing \= "TRD\_002\_PLMB"  
    electrical \= "TRD\_003\_ELEC"

class EquipmentEnum(str, enum.Enum):  
    rtu \= "EQP\_99\_RTU"  
    chiller \= "EQP\_88\_CHLR"  
    boiler \= "EQP\_77\_BLR"  
    unknown \= "EQP\_00\_UNK"

\# Define the exact JSON shape the LLM must output  
class CMMSMapping(BaseModel):  
    trade\_id: TradeEnum  
    equipment\_id: EquipmentEnum  
    problem\_type\_id: str \# You would constrain this similarly  
    problem\_code\_id: str   
    confidence\_score: float \# Useful for routing low-confidence matches to a human

**The Prompt:**  
You pass the engine a system prompt:  
*"You are an expert facilities maintenance dispatcher. Analyze the provided client work order. Map their raw data to our internal CMMS structure. Infer the correct Trade and Problem Type based on the description. You must select the most accurate internal IDs."*  
**The Input:**  
{"client\_craft": "mechanic", "client\_asset": "roof unit", "description": "compressor making grinding noise and blowing warm"}  
**The Engine Execution:**  
Because you pass the CMMSMapping schema to vLLM/Outlines, the LLM evaluates the input, recognizes "compressor" and "roof unit" means HVAC and RTU, and outputs the exact JSON string:  
JSON  
{  
  "trade\_id": "TRD\_001\_HVAC",  
  "equipment\_id": "EQP\_99\_RTU",  
  "problem\_type\_id": "TYP\_MECHANICAL",  
  "problem\_code\_id": "CODE\_COMPRESSOR\_FAIL",  
  "confidence\_score": 0.95  
}

### **Why this beats Fine-Tuning**

1. **Zero Drift:** If you fine-tune a model on your IDs, and next week your business adds 50 new Problem Codes or changes an ID, your fine-tuned model is instantly deprecated. With constrained generation and RAG, you just update your database or Python script, and the model instantly adapts.  
2. **Guaranteed Schema:** A fine-tuned model can still hallucinate a comma or a typo in an ID. Constrained generation mathematically guarantees schema compliance.  
3. **Cost/Time:** You can build this pipeline in an afternoon using open-source tools without spending days curating thousands of perfect training examples.

To complete this in under two hours on an **RTX 5090**, you must use **Unsloth**. It is the fastest fine-tuning library for local hardware, reducing VRAM usage and increasing speed by 2x-3x.

### **1\. Environment Setup**

Open PowerShell or a terminal and create a dedicated environment. You need Python 3.10+ and CUDA 12.1+.  
Bash  
\# Create and activate environment  
python \-m venv cmms\_train  
.\\cmms\_train\\Scripts\\activate

\# Install Unsloth and dependencies (Optimized for 50-series/Blackwell)  
pip install unsloth\[colab-new\]  
pip install \--no-deps "xformers\<0.0.27" "trl\<0.9.0" peft accelerate bitsandbytes  
pip install pydantic outlines

### **2\. Dataset Preparation**

You need a dataset.jsonl file. Since you are mapping unstructured data to 4 locked internal fields, your "training" is actually teaching the model to act as a deterministic mapper.  
**Format (JSONL):**  
JSON  
{"instruction": "Map CMMS data.", "input": "Equip: Chiller, Note: leaking at seal", "output": "{\\"trade\_id\\": \\"T101\\", \\"equip\_id\\": \\"E502\\", \\"prob\_type\\": \\"P3\\", \\"prob\_code\\": \\"C09\\"}"}  
{"instruction": "Map CMMS data.", "input": "Craft: Pipefitter, Unit: RTU 5, Issue: no cooling", "output": "{\\"trade\_id\\": \\"T202\\", \\"equip\_id\\": \\"E101\\", \\"prob\_type\\": \\"P1\\", \\"prob\_code\\": \\"C12\\"}"}

*Note: Create \~200-500 variations of your specific industry jargon vs. your internal IDs.*

### **3\. Model Selection**

Use **Mistral-7B-v0.3** (Apache 2.0 License). It is truly open-source, supports function calling, and is small enough to train in minutes on a 5090\.

* **Source:** [Hugging Face \- Unsloth Mistral-7B-v0.3](https://huggingface.co/unsloth/mistral-7b-v0.3-bnb-4bit)

### **4\. Training Script (The "Fine-Tuning")**

Save this as train.py. On an RTX 5090, this script will run in approximately 15–20 minutes for 500 rows.  
Python  
from unsloth import FastLanguageModel  
import torch  
from trl import SFTTrainer  
from transformers import TrainingArguments  
from datasets import load\_dataset

\# 1\. Load Model (4-bit for speed)  
model, tokenizer \= FastLanguageModel.from\_pretrained(  
    model\_name \= "unsloth/mistral-7b-v0.3-bnb-4bit",  
    max\_seq\_length \= 2048,  
    load\_in\_4bit \= True,  
)

\# 2\. Add LoRA Adapters (The "Fine-Tuning" layer)  
model \= FastLanguageModel.get\_peft\_model(  
    model,  
    r \= 16,   
    target\_modules \= \["q\_proj", "k\_proj", "v\_proj", "o\_proj"\],  
    lora\_alpha \= 16,  
    lora\_dropout \= 0,  
)

\# 3\. Load Dataset  
dataset \= load\_dataset("json", data\_files="dataset.jsonl", split="train")

\# 4\. Set Training Arguments  
trainer \= SFTTrainer(  
    model \= model,  
    tokenizer \= tokenizer,  
    train\_dataset \= dataset,  
    dataset\_text\_field \= "text", \# Ensure your JSONL maps to a 'text' prompt template  
    max\_seq\_length \= 2048,  
    args \= TrainingArguments(  
        per\_device\_train\_batch\_size \= 4,  
        gradient\_accumulation\_steps \= 4,  
        warmup\_steps \= 5,  
        max\_steps \= 60, \# Total iterations  
        learning\_rate \= 2e-4,  
        fp16 \= not torch.cuda.is\_bf16\_supported(),  
        bf16 \= torch.cuda.is\_bf16\_supported(),  
        logging\_steps \= 1,  
        output\_dir \= "outputs",  
    ),  
)

\# 5\. Execute  
trainer.train()

\# 6\. Save for Ollama/Production  
model.save\_pretrained\_gguf("cmms\_adapter", tokenizer, quantization\_method \= "q8\_0")

### **5\. Deployment via Ollama**

Once the script finishes, it generates a .gguf file. Use your existing Ollama installation to stand it up.

1. Create a Modelfile:  
2. Dockerfile

FROM ./cmms\_adapter.gguf  
SYSTEM "You are a CMMS Adapter. Return ONLY valid JSON mapping to internal IDs."

3.   
4.   
5. Create the model:  
6. ollama create cmms-mapper \-f Modelfile  
7. Run it:  
8. ollama run cmms-mapper

### **6\. Summary of Hardware & Tools**

* **Hardware:** You are using 1x RTX 5090\. VRAM usage will stay under 12GB during training due to Unsloth's 4-bit optimization.  
* **Source Models:** Mistral-7B-v0.3 (Apache 2.0).  
* **Libraries:** unsloth (training), trl (SFT logic), bitsandbytes (quantization), outlines (inference enforcement).

### **Logic Check**

* **Field Mapping:** 10-15 fields is a low-dimensional task. The model will easily learn the relationships between "Craft" and "Trade" within the first 20 steps of training.  
* **Private Adaptor:** This entire workflow is local. No data leaves your machine.  
* **Reliability:** By saving the model as a GGUF and using it through your existing Python infrastructure, you can wrap the Ollama API call in a Pydantic check to ensure the JSON is valid before sending it to your CMMS endpoint.

It is not only valid; it is the **primary use case** for this architecture. A hard-coded mapping tool (ETL) fails on "big text" because it cannot interpret intent. An LLM performs **Named Entity Recognition (NER)** and **Inference** simultaneously.

### **Why "Big Text" is Ideal for an LLM Adapter**

When you receive a paragraph like: *"The unit on the roof of the pharmacy is vibrating loudly and there's a puddle of oily liquid underneath it,"* a traditional system sees zero matches for your internal IDs.  
The LLM performs two logical leaps:

1. **Extraction:** It identifies "unit on the roof" as an **RTU** (Equipment) and "oily liquid" as a potential **Refrigerant/Oil Leak** (Problem Code).  
2. **Inference:** It concludes that the **Trade** must be "HVAC" because of the equipment and symptom context.

### **Refined Logic for Unstructured Text**

To handle large descriptions effectively, you should adjust your training/prompting strategy slightly:

#### **1\. The "Extraction" Prompt**

Your prompt must instruct the model to "distill" the text before mapping.

* **Input:** Big Text Description.  
* **Intermediate Logic:** Summarize key entities (Asset, Symptom, Location).  
* **Output:** The 4 Locked IDs.

#### **2\. The Confidence Guardrail**

Because big text is inherently ambiguous (e.g., a description that just says "It's broken"), you must include a confidence\_score in your JSON output.

* If confidence\_score \> 0.85: **Auto-inject** into your CMMS.  
* If confidence\_score \< 0.85: **Route to a human** for a one-click verification.

### **Practical Example of the Mapping**

**Client Input (Unstructured):**  
"Hey, we have a major issue in the men's room. The sink is backed up and won't drain, and now there is water starting to seep into the hallway carpet. We need someone here ASAP before the flooring is ruined."  
**LLM Adapter Logic:**

1. **Trade:** Identifying "sink," "drain," and "water" $\\rightarrow$ TRD\_PLUMB.  
2. **Equipment:** Identifying "sink" $\\rightarrow$ EQP\_SINK.  
3. **Problem Type:** Identifying "won't drain" $\\rightarrow$ TYPE\_CLOG.  
4. **Problem Code:** Identifying "seep into hallway" (High Severity) $\\rightarrow$ CODE\_EMERGENCY\_OVERFLOW.

**Final Output (JSON):**  
JSON  
{  
  "trade\_id": "TRD\_PLUMB",  
  "equipment\_id": "EQP\_SINK",  
  "problem\_type\_id": "TYPE\_CLOG",  
  "problem\_code\_id": "CODE\_EMERGENCY\_OVERFLOW",  
  "confidence": 0.98  
}

### **Implementation Checklist for "Big Text"**

* **Context Window:** Since you're using **Mistral-7B-v0.3**, the 32k context window is overkill for this. You can feed it 10-page inspection reports and it will still distill them into your 4 fields.  
* **Preprocessing:** Do not strip punctuation or "stop words" (like 'and', 'the'). LLMs use those to understand the relationship between nouns.  
* **Synthetic Data:** If you don't have enough "big text" examples, use a larger model (like GPT-4o or Llama-3-70B) to generate 500 "fake" technician notes based on your existing 4-field codes. Use that synthetic data to train your local Mistral model. This is called **Distillation**.

Your hardware (RTX 5090\) handles this effortlessly. The inference time for a paragraph-to-JSON conversion will be under **100ms** at FP16 precision.

Your business users are right to be skeptical of a "black box," but trying to hard-code client-specific bias into the LLM weights is a recipe for technical debt. You will end up managing 50 different "adapters" for 50 different clients.  
Instead, use a **Hybrid Architecture** where code handles the "rules" and the LLM handles the "nuance."

### **1\. Strategy: The "Logic Sandwich"**

Do not force the LLM to learn that "Trades" equals "Trade" for a specific client. Handle that in your application logic (the "Adapter") before and after the LLM call.

* **Pre-Processing (The Rules):** If a client has a known 1:1 field mapping, map it in your Python code first. Pass that "solved" value into the LLM as a **Fixed Constraint**.  
* **The LLM (The Inference):** Tell the model: *"The Trade is already identified as 'Plumbing'. Based on the description 'Sump pump failure', identify the specific Equipment ID and Problem Code."*  
* **Post-Processing (The Validation):** Use your Pydantic/Outlines schema to ensure the output matches your locked IDs.

### **2\. Overcoming the "Black Box" Perception**

To build trust with "semi-technical" stakeholders, you need to provide **Explainability** and **Control**. If they feel they can "steer" the model, they will stop fearing it.

#### **A. Show the "Reasoning" (Chain of Thought)**

Don't just output a JSON blob. Train or prompt the model to provide a brief "Reasoning" string.

* **Model Output:** "Reasoning": "User mentioned 'water leaking from ceiling' and 'AC not cold', which correlates to an HVAC condensate line clog."  
* **Business Impact:** When a user sees the logic, the result feels like a "digital technician" rather than a random number generator.

#### **B. Expose Confidence Intervals**

LLMs provide "logprobs" (logarithmic probabilities) for every token they generate. You can average these to create a **Confidence Score (0-100%)**.

* **High Confidence (\>90%):** Auto-process.  
* **Medium Confidence (70-89%):** Highlight in yellow for "Review."  
* **Low Confidence (\<70%):** Flag for "Manual Intervention."

#### **C. The "Human-in-the-Loop" (HITL) Dashboard**

Give them a simple UI (use **Streamlit** or **Gradio** for a 2-hour build) that shows:

1. **Original Client Text**  
2. **Model Mapping**  
3. **Confidence Score**  
4. **"Override" Button:** Let them manually change a mapping. **Crucial:** Save these overrides. They become your "Gold Dataset" for the next round of fine-tuning.

### **3\. Tactical Execution: Visibility Tools**

If you want to prove it’s working, you need to show them the math without the fluff.

#### **Metrics to Show Stakeholders:**

| Metric | Description | Why it matters |
| :---- | :---- | :---- |
| **Accuracy Rate** | % of mappings that required no human override. | Proves the model is learning. |
| **Field Fill Rate** | How many "missing" fields the LLM successfully inferred from text. | Shows value add over hard-coding. |
| **Throughput** | Number of work orders mapped per second on your 5090\. | Proves scalability. |

#### **Calculating Confidence ($C$)**

You can represent confidence simply as the mean of the softmax probabilities ($P$) for the generated tokens ($N$):  
$$C \= \\frac{1}{N} \\sum\_{i=1}^{N} P\_i$$  
In your Python code (using the OpenAI-compatible API from Ollama or vLLM), you can request logprobs=True. This gives the users a "percentage" they can understand.

### **4\. Implementation Step: The "Control Table"**

Create a simple SQL table or CSV that your business users can edit.

* **Columns:** Client\_Name, Source\_Field, Target\_Field, Is\_Hard\_Mapped  
* **Logic:** Your Python script reads this table. If Is\_Hard\_Mapped is True, the script bypasses the LLM for that specific field.

**Result:** The business users feel like the "boss" of the AI. They control the rules, and the AI handles the "messy text" they don't want to deal with anyway.  
Does this "Human-in-the-loop" approach satisfy the requirement for transparency, or do you need a more automated way to validate the mappings?  
