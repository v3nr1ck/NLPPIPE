"""
Layer 1: Pre-Processing Engine ("The Rules")
Reads the control table and applies deterministic mappings before the LLM ever sees the data.
Business users can edit control_table.csv without touching code.
"""
from __future__ import annotations
import csv
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, field


@dataclass
class ControlRule:
    client_name: str      # "*" = wildcard (all clients)
    source_field: str     # e.g. "craft", "asset", "priority"
    source_value: str     # e.g. "mechanic", "roof unit"
    target_field: str     # e.g. "trade_id", "equipment_id"
    target_value: str     # e.g. "TRD_001_HVAC"
    is_hard_mapped: bool  # True = bypass LLM, False = hint only
    priority: int = 0     # higher = overrides lower


@dataclass
class PreProcessResult:
    hard_mapped: dict[str, str] = field(default_factory=dict)
    hints: dict[str, str] = field(default_factory=dict)
    remaining_fields: set[str] = field(default_factory=set)
    original_fields: dict[str, str] = field(default_factory=dict)


class PreProcessor:
    """
    Reads the control table and applies hard-mapping rules.
    Wildcards ('*' for client_name) match all clients.
    Higher priority rules win on conflict.
    """

    def __init__(self, control_table_path: str | Path):
        self.rules: list[ControlRule] = []
        self._load_rules(Path(control_table_path))

    def _load_rules(self, path: Path) -> None:
        with open(path, "r") as f:
            reader = csv.DictReader(f)
            for row in reader:
                rule = ControlRule(
                    client_name=row["client_name"].strip(),
                    source_field=row["source_field"].strip(),
                    source_value=row["source_value"].strip().lower(),
                    target_field=row["target_field"].strip(),
                    target_value=row["target_value"].strip(),
                    is_hard_mapped=row.get("is_hard_mapped", "true").strip().lower() == "true",
                    priority=int(row.get("priority", 0)),
                )
                self.rules.append(rule)
        # Sort by priority descending so higher-priority rules apply first
        self.rules.sort(key=lambda r: r.priority, reverse=True)

    def process(
        self,
        client_name: str,
        raw_fields: dict[str, str],
    ) -> PreProcessResult:
        """
        Apply control table rules to raw input fields.
        Returns what was hard-mapped, what hints exist, and what's left for the LLM.
        """
        result = PreProcessResult(original_fields=dict(raw_fields))
        applied_rules: set[tuple[str, str]] = set()  # (source_field, source_value)

        for rule in self.rules:
            # Check client match (exact or wildcard)
            if rule.client_name != "*" and rule.client_name.lower() != client_name.lower():
                continue

            # Check if we have this field in the input
            if rule.source_field not in raw_fields:
                continue

            raw_value = raw_fields[rule.source_field].strip().lower()
            if raw_value != rule.source_value:
                continue

            # Avoid duplicate rule application
            rule_key = (rule.source_field, rule.source_value)
            if rule_key in applied_rules:
                continue
            applied_rules.add(rule_key)

            if rule.is_hard_mapped and rule.target_value:
                result.hard_mapped[rule.target_field] = rule.target_value
            elif rule.target_value:
                result.hints[rule.target_field] = rule.target_value

        # Determine remaining fields the LLM needs to fill
        all_target_fields = {"trade_id", "equipment_id", "problem_type_id", "problem_code_id"}
        result.remaining_fields = all_target_fields - set(result.hard_mapped.keys())

        return result


# The four fields the pipeline must always fill
REQUIRED_OUTPUT_FIELDS: list[str] = [
    "trade_id",
    "equipment_id",
    "problem_type_id",
    "problem_code_id",
]
