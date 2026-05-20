"""
Layer 2a: Prompt Builder
Builds the system prompt and user prompt for the LLM.
Injects the allowed ID dictionary and any pre-mapped fields as constraints.
"""
from __future__ import annotations
from schemas import get_allowed_values_dict, TradeEnum, EquipmentEnum, ProblemTypeEnum, ProblemCodeEnum


SYSTEM_PROMPT_TEMPLATE = """\
You are an expert facilities maintenance dispatcher and CMMS data mapper.

Your job: Analyze a client work order and map it to our internal CMMS structure.
You MUST output valid JSON conforming exactly to the schema below.

## RULES
1. Infer the most accurate Trade, Equipment, Problem Type, and Problem Code from the description.
2. If the description mentions multiple issues, pick the PRIMARY one.
3. Consider the context: equipment type implies trade (e.g., HVAC unit → HVAC trade).
4. "roof unit", "RTU", "air handler", "AC unit" all refer to Rooftop HVAC equipment.
5. If you are unsure, use the "unknown" option but set confidence_score LOW.
6. Include a brief "reasoning" string explaining your logic.

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
- reasoning (string)

Do NOT include markdown code fences, explanations, or any other text. Output raw JSON only."""


USER_PROMPT_TEMPLATE = """\
Client Work Order:
- Asset/Equipment: {asset}
- Issue/Description: {issue}
- Craft/Trade (client term): {craft}
- Priority: {priority}
- Location: {location}
- Additional Notes: {raw_text}

Map these to our internal CMMS IDs."""


def build_system_prompt(
    hard_mapped: dict[str, str] | None = None,
    hints: dict[str, str] | None = None,
) -> str:
    """Build the system prompt with allowed values and any pre-mapped constraints."""
    allowed = get_allowed_values_dict()

    # Format allowed values as readable lists
    trade_ids = "\n".join(f"  - {v}" for v in allowed["trade_id"])
    equipment_ids = "\n".join(f"  - {v}" for v in allowed["equipment_id"])
    problem_type_ids = "\n".join(f"  - {v}" for v in allowed["problem_type_id"])
    problem_code_ids = "\n".join(f"  - {v}" for v in allowed["problem_code_id"])

    # Format constraints
    constraints = ""
    if hard_mapped:
        for field, value in hard_mapped.items():
            constraints += f"- {field} = {value} (LOCKED — do not change)\n"
    if hints:
        for field, value in hints.items():
            constraints += f"- {field}: prefer {value} (hint from rules)\n"
    if not constraints:
        constraints = "- No pre-mapped constraints. Infer all fields."

    return SYSTEM_PROMPT_TEMPLATE.format(
        trade_ids=trade_ids,
        equipment_ids=equipment_ids,
        problem_type_ids=problem_type_ids,
        problem_code_ids=problem_code_ids,
        constraints=constraints,
    )


def build_user_prompt(work_order_dict: dict) -> str:
    """Build the user prompt from a client work order dict."""
    return USER_PROMPT_TEMPLATE.format(
        asset=work_order_dict.get("asset", "Not specified"),
        issue=work_order_dict.get("issue", work_order_dict.get("raw_text", "Not specified")),
        craft=work_order_dict.get("craft", "Not specified"),
        priority=work_order_dict.get("priority", "Not specified"),
        location=work_order_dict.get("location", "Not specified"),
        raw_text=work_order_dict.get("raw_text", ""),
    )
