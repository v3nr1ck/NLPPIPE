"""
Layer 1: Pre-Processing Engine ("The Rules")
Reads the control table and classifies every client field into one of three buckets:
  - map:     Direct 1:1 translation → bypasses the LLM for this field
  - context: Pass to LLM for inference context → NOT directly mapped
  - ignore:  Drop the field entirely

Business users edit control_table.csv without touching code.
"""
from __future__ import annotations
import csv
import fnmatch
from pathlib import Path
from dataclasses import dataclass, field
from typing import Literal, TYPE_CHECKING, Any

if TYPE_CHECKING:
    from vendor_profile import VendorProfile

Strategy = Literal["map", "context", "ignore"]


@dataclass
class ControlRule:
    client_name: str       # "*" = wildcard (all clients)
    source_field: str      # e.g. "craft", "equipment_tag", "building"
    source_value: str      # e.g. "mechanic", "RTU-*", "*" (wildcard)
    target_field: str      # e.g. "trade_id" (empty for context/ignore)
    target_value: str      # e.g. "TRD_001_HVAC" (empty for context/ignore)
    strategy: Strategy     # "map" | "context" | "ignore"
    priority: int = 0      # higher = overrides lower


@dataclass
class PreProcessResult:
    """The three buckets after pre-processing."""
    mapped: dict[str, str] = field(default_factory=dict)
    context: dict[str, str] = field(default_factory=dict)
    ignored: list[str] = field(default_factory=list)
    remaining_for_llm: set[str] = field(default_factory=set)


class PreProcessor:
    """
    Reads the control table and classifies every incoming field.

    Resolution order:
      1. Explicit control table rules (highest priority)
      2. Vendor profile default_strategies (if vendor profile loaded)
      3. Fallthrough: 'context' (pass to LLM)
    """

    def __init__(
        self,
        control_table_path: str | Path,
        vendor_profile: "VendorProfile | None" = None,
    ):
        self.vendor_profile = vendor_profile
        self.rules: list[ControlRule] = []
        self._load_rules(Path(control_table_path))

    def _load_rules(self, path: Path) -> None:
        with open(path, "r") as f:
            reader = csv.DictReader(f)
            for row in reader:
                # Skip comment lines and empty rows
                source_field = (row.get("source_field") or "").strip()
                if not source_field or source_field.startswith("#"):
                    continue

                rule = ControlRule(
                    client_name=row["client_name"].strip(),
                    source_field=source_field.lower(),
                    source_value=(row.get("source_value") or "").strip().lower(),
                    target_field=(row.get("target_field") or "").strip(),
                    target_value=(row.get("target_value") or "").strip(),
                    strategy=(row.get("strategy") or "map").strip(),  # type: ignore[arg-type]
                    priority=int(row.get("priority", 0)),
                )
                self.rules.append(rule)
        # Sort by priority descending
        self.rules.sort(key=lambda r: r.priority, reverse=True)

    def process(
        self,
        client_name: str,
        extra_fields: dict[str, Any],
    ) -> PreProcessResult:
        """
        Classify every field in extra_fields into map/context/ignore.

        For each client field, the FIRST matching rule (by priority) wins.
        Fields that match NO rule default to the vendor's default_strategy (or 'context').
        Non-string values (int, float, dict, list) are converted to strings.
        Nested dicts/lists should be flattened BEFORE calling this method
        (use vendor_profile.flatten_payload).
        """
        result = PreProcessResult()

        # Track which rules have already been applied (to avoid double-matching)
        applied_rules: set[tuple[str, str]] = set()

        for field_name, field_value in extra_fields.items():
            field_lower = field_name.lower().strip()
            # Convert non-string values to string for matching
            if isinstance(field_value, (dict, list)):
                # Skip nested structures — they should be flattened upstream
                continue
            value_lower = str(field_value).strip().lower() if field_value is not None else ""
            resolved = False

            for rule in self.rules:
                # ── Client name match? ──
                if rule.client_name != "*" and rule.client_name.lower() != client_name.lower():
                    continue

                # ── Field name match? ──
                if rule.source_field != field_lower:
                    continue

                # ── Value match? ──
                if not self._value_matches(rule.source_value, value_lower):
                    continue

                # ── Already applied this rule? ──
                rule_key = (rule.source_field, rule.source_value)
                if rule_key in applied_rules and rule.strategy == "map":
                    # Map rules are one-shot; context/ignore can match multiple values
                    continue

                # ── Apply the strategy ──
                if rule.strategy == "map":
                    if rule.target_field:
                        result.mapped[rule.target_field] = rule.target_value
                    applied_rules.add(rule_key)
                    resolved = True
                    break  # Map rules consume the field

                elif rule.strategy == "context":
                    result.context[field_name] = field_value
                    resolved = True
                    break  # Field is accounted for

                elif rule.strategy == "ignore":
                    result.ignored.append(field_name)
                    resolved = True
                    break  # Field is dropped

            # ── Fallthrough: field matched NO rule ──
            if not resolved:
                # Check vendor profile default strategy
                default_strategy = None
                if self.vendor_profile:
                    default_strategy = self.vendor_profile.default_strategies.get(field_lower)

                if default_strategy == "map":
                    # Vendor says map but no target_value in control table — treat as context
                    result.context[field_name] = field_value
                elif default_strategy == "ignore":
                    result.ignored.append(field_name)
                else:
                    # Default: context (pass to LLM)
                    result.context[field_name] = field_value

        # ── Determine remaining fields the LLM needs to fill ──
        all_target_fields = {"trade_id", "equipment_id", "problem_type_id", "problem_code_id"}
        result.remaining_for_llm = all_target_fields - set(result.mapped.keys())

        return result

    @staticmethod
    def _value_matches(pattern: str, value: str) -> bool:
        """Match a rule's source_value against an actual field value.
        Supports wildcards: '*' matches anything, 'RTU-*' matches 'RTU-4', etc."""
        if pattern == "*":
            return True
        if pattern == value:
            return True
        # fnmatch for glob-style patterns: 'RTU-*' matches 'RTU-4', 'rtu-south'
        if fnmatch.fnmatch(value, pattern):
            return True
        return False


# The four fields the pipeline must always fill
REQUIRED_OUTPUT_FIELDS: list[str] = [
    "trade_id",
    "equipment_id",
    "problem_type_id",
    "problem_code_id",
]
