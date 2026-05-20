"""
Vendor Profile System — v1.2.0
================================
Loads per-vendor JSON profiles that define:
  1. Field aliases: vendor field name → canonical field name
  2. Nested paths: extract fields from objects/arrays (dot-bracket notation)
  3. Custom field auto-detection
  4. Default strategies per canonical field

Usage:
    loader = VendorProfileLoader("vendor_profiles/")
    profile = loader.load("maximo")
    flat_fields = loader.flatten_payload(profile, raw_api_payload)
    # flat_fields is now a dict of canonical_field_name → value
"""
from __future__ import annotations
import json
import re
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class NestedPath:
    """A path specification for extracting a nested field."""
    path: str           # e.g. "Labours[0].Craft" or "WPLABOR.CRAFT"
    canonical: str      # e.g. "primary_craft"


@dataclass
class VendorProfile:
    """Loaded vendor profile with all mappings and extraction rules."""
    vendor_name: str
    field_aliases: dict[str, str] = field(default_factory=dict)
    nested_paths: list[NestedPath] = field(default_factory=list)
    custom_fields_discovery: dict = field(default_factory=dict)
    default_strategies: dict[str, str] = field(default_factory=dict)

    def get_canonical(self, vendor_field: str) -> str:
        """Map a vendor field name to its canonical name, or return as-is."""
        return self.field_aliases.get(vendor_field, vendor_field.lower())


class VendorProfileLoader:
    """
    Loads vendor profiles from a directory of JSON files.
    """

    def __init__(self, profiles_dir: str | Path):
        self.profiles_dir = Path(profiles_dir)
        self._cache: dict[str, VendorProfile] = {}

    def load(self, vendor_key: str) -> VendorProfile:
        """Load a vendor profile by its filename key (e.g. 'maximo', 'fiix')."""
        if vendor_key in self._cache:
            return self._cache[vendor_key]

        profile_path = self.profiles_dir / f"{vendor_key.lower()}.json"
        if not profile_path.exists():
            raise FileNotFoundError(
                f"No vendor profile found for '{vendor_key}'. "
                f"Expected: {profile_path}\n"
                f"Available: {self.list_available()}"
            )

        with open(profile_path, "r") as f:
            raw = json.load(f)

        nested = [
            NestedPath(path=np["path"], canonical=np["canonical"])
            for np in raw.get("nested_paths", [])
        ]

        profile = VendorProfile(
            vendor_name=raw.get("vendor_name", vendor_key),
            field_aliases=raw.get("field_aliases", {}),
            nested_paths=nested,
            custom_fields_discovery=raw.get("custom_fields_discovery", {}),
            default_strategies=raw.get("default_strategies", {}),
        )
        self._cache[vendor_key] = profile
        return profile

    def list_available(self) -> list[str]:
        """List all available vendor profile names."""
        profiles = []
        for f in self.profiles_dir.glob("*.json"):
            name = f.stem
            if name.startswith("_"):  # Skip templates
                continue
            profiles.append(name)
        return sorted(profiles)

    def flatten_payload(
        self,
        profile: VendorProfile,
        payload: dict,
    ) -> dict[str, str]:
        """
        Flatten a raw vendor API payload into canonical field names.
        Handles:
          1. Direct field aliasing (vendor field → canonical)
          2. Nested path extraction (dot-bracket notation)
          3. Auto-detection of customFields[] arrays
        Returns a flat dict of canonical_name → string_value.
        """
        result: dict[str, str] = {}

        # ── 1. Direct field aliasing ──
        for vendor_key, value in payload.items():
            canonical = profile.get_canonical(vendor_key)

            # Skip if this field would be extracted via nested paths
            if isinstance(value, (dict, list)):
                # It'll be handled by nested extraction or auto-custom-fields
                continue

            if value is not None and value != "":
                result[canonical] = str(value)

        # ── 2. Nested path extraction ──
        for np in profile.nested_paths:
            extracted = self._extract_path(payload, np.path)
            if extracted:
                result[np.canonical] = extracted

        # ── 3. Auto-detect customFields[] ──
        for key, value in payload.items():
            key_lower = key.lower()
            if key_lower in ("customfields", "custom_fields", "additionalfields"):
                if isinstance(value, list):
                    for item in value:
                        if isinstance(item, dict):
                            cf_name = item.get("name", item.get("key", item.get("fieldName", "")))
                            cf_value = item.get("value", item.get("fieldValue", ""))
                            if cf_name and cf_value is not None:
                                result[f"cf_{cf_name}"] = str(cf_value)
                elif isinstance(value, dict):
                    # Custom fields as dict: {"cf_pressure": "150 PSI"}
                    for cf_key, cf_val in value.items():
                        result[f"cf_{cf_key}"] = str(cf_val)

        return result

    def _extract_path(self, data: dict, path: str) -> Optional[str]:
        """
        Extract a value from nested data using dot-bracket notation.

        Supported syntax:
          - WPLABOR.CRAFT         → traverses nested dicts: data["WPLABOR"]["CRAFT"]
          - Labours[0].Craft      → first element of array, then "Craft"
          - WorkTasks[*].tradeCode → all array elements, joined with comma
          - Scheduling.TargetCompletion → nested dict traversal
        """
        parts = self._parse_path(path)
        current: any = data

        for part in parts:
            if current is None:
                return None

            if part["type"] == "key":
                if isinstance(current, dict):
                    current = current.get(part["value"])
                    if current is None:
                        # Try case-insensitive match
                        for k, v in current.items() if isinstance(current, dict) else []:
                            if k.lower() == part["value"].lower():
                                current = v
                                break
                        else:
                            current = None
                else:
                    return None

            elif part["type"] == "index":
                if isinstance(current, list) and len(current) > part["value"]:
                    current = current[part["value"]]
                else:
                    return None

            elif part["type"] == "wildcard":
                if isinstance(current, list):
                    # For wildcard, we need to collect remaining path from all elements
                    remaining_path = ".".join(
                        p["value"] if p["type"] == "key" else f"[{p['value']}]"
                        for p in parts[parts.index(part) + 1:]
                    )
                    if remaining_path:
                        values = []
                        for item in current:
                            if isinstance(item, dict):
                                val = item.get(remaining_path)
                                if val is not None:
                                    values.append(str(val))
                        return ", ".join(values) if values else None
                    else:
                        return ", ".join(str(x) for x in current)
                else:
                    return None

        if current is None:
            return None
        if isinstance(current, (dict, list)):
            return json.dumps(current)  # Fallback: serialize complex objects
        return str(current)

    @staticmethod
    def _parse_path(path: str) -> list[dict]:
        """
        Parse a dot-bracket path into segments.

        "Labours[0].Craft" →
            [{"type": "key", "value": "Labours"},
             {"type": "index", "value": 0},
             {"type": "key", "value": "Craft"}]

        "WorkTasks[*].tradeCode" →
            [{"type": "key", "value": "WorkTasks"},
             {"type": "wildcard", "value": "*"},
             {"type": "key", "value": "tradeCode"}]
        """
        segments = []
        # Split on dots NOT inside brackets
        tokens = re.split(r"\.(?![^\[]*\])", path)

        for token in tokens:
            # Check for bracket notation: Labours[0] or WorkTasks[*]
            match = re.match(r"^([^\[\]]+)(?:\[([^\[\]]*)\])?$", token)
            if not match:
                continue

            key = match.group(1)
            bracket = match.group(2)

            if key:
                segments.append({"type": "key", "value": key})

            if bracket is not None:
                if bracket == "*":
                    segments.append({"type": "wildcard", "value": "*"})
                elif bracket.isdigit():
                    segments.append({"type": "index", "value": int(bracket)})
                else:
                    # Named bracket (not currently supported, treat as key)
                    pass

        return segments
