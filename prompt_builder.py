"""
Layer 2a: Prompt Builder (Dynamic)
Builds system and user prompts from ARBITRARY client field names.
No more hardcoded 'asset', 'issue', 'craft' — whatever the client sends
gets injected into the prompt.
"""
from __future__ import annotations
from typing import Any
from schemas import get_allowed_values_dict


SYSTEM_PROMPT_TEMPLATE = """\
You are an expert facilities maintenance dispatcher and CMMS data mapper.

Your job: Analyze a client work order and map it to our internal CMMS structure.
You MUST output valid JSON conforming exactly to the schema below.

## RULES
1. Infer the most accurate Trade, Equipment, Problem Type, and Problem Code from the description.
2. If the description mentions multiple issues, pick the PRIMARY one.
3. Consider the context: equipment type implies trade (e.g., HVAC unit → HVAC trade).
4. "roof unit", "RTU", "air handler", "AC unit" all refer to Rooftop HVAC equipment.
5. If you are unsure, use your best judgment and set confidence_score LOW.

## ALLOWED VALUES (YOU CAN ONLY OUTPUT FROM THESE EXACT SETS)

Trade IDs:
{trade_ids}

Equipment IDs:
{equipment_ids}

Problem Type IDs:
{problem_type_ids}

Problem Code IDs:
{problem_code_ids}

## KNOWN CONSTRAINTS (already determined — DO NOT change these)
{constraints}

## OUTPUT FORMAT
You MUST output ONLY a single JSON object with these exact keys:
- trade_id
- equipment_id
- problem_type_id
- problem_code_id
- confidence_score (float 0.0 - 1.0)

Do NOT include markdown code fences, explanations, or any other text. Output raw JSON only."""


USER_PROMPT_TEMPLATE = """\
Client Work Order:
{context_lines}

Map these to our internal CMMS IDs. Use ALL available context fields for your inference."""


def build_system_prompt(
    mapped_fields: dict[str, str] | None = None,
) -> str:
    """Build the system prompt with allowed values and pre-mapped constraints."""
    allowed = get_allowed_values_dict()

    trade_ids = "\n".join(f"  - {v}" for v in allowed["trade_id"])
    equipment_ids = "\n".join(f"  - {v}" for v in allowed["equipment_id"])
    problem_type_ids = "\n".join(f"  - {v}" for v in allowed["problem_type_id"])
    problem_code_ids = "\n".join(f"  - {v}" for v in allowed["problem_code_id"])

    constraints = ""
    if mapped_fields:
        for field, value in mapped_fields.items():
            constraints += f"- {field} = {value} (LOCKED — do not change)\n"
    if not constraints:
        constraints = "- No pre-mapped constraints. Infer all fields."

    return SYSTEM_PROMPT_TEMPLATE.format(
        trade_ids=trade_ids,
        equipment_ids=equipment_ids,
        problem_type_ids=problem_type_ids,
        problem_code_ids=problem_code_ids,
        constraints=constraints,
    )


def build_user_prompt(
    context_fields: dict[str, Any],
    raw_text: str | None = None,
) -> str:
    """
    Build a dynamic user prompt from whatever context fields exist.
    No assumptions about field names — just iterate and format.
    Non-string values are coerced to string.
    """
    lines = []
    for field_name, field_value in sorted(context_fields.items()):
        # Clean up the field name for readability: 'equipment_tag' → 'Equipment Tag'
        readable = field_name.replace("_", " ").title()
        lines.append(f"- {readable}: {field_value}")

    if raw_text:
        lines.append(f"- Additional Notes: {raw_text}")

    if not lines:
        lines.append("- (No context fields provided)")

    context_block = "\n".join(lines)
    return USER_PROMPT_TEMPLATE.format(context_lines=context_block)
