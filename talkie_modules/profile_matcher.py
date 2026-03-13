"""Profile matching and resolution for per-app dictation profiles."""

import copy
from typing import Any

from talkie_modules.logger import get_logger

logger = get_logger("profile_matcher")


def resolve_profile(
    profiles: list[dict[str, Any]], process_name: str, window_title: str
) -> dict[str, Any] | None:
    """Find the first matching profile for the given window.

    Iterates profiles in list order (first match wins). Skips profiles where
    both match fields are empty. Match rules:
    - match_process: case-insensitive exact match on process name
    - match_title: case-insensitive substring match on window title
    - Both set: AND logic (both must match)
    """
    for profile in profiles:
        mp = (profile.get("match_process") or "").strip()
        mt = (profile.get("match_title") or "").strip()

        # Skip profiles with no match criteria
        if not mp and not mt:
            continue

        process_ok = mp.lower() == process_name.lower() if mp else True
        title_ok = mt.lower() in window_title.lower() if mt else True

        if process_ok and title_ok:
            return profile

    return None


def apply_profile(
    config: dict[str, Any], profile: dict[str, Any] | None
) -> dict[str, Any]:
    """Apply profile overrides to a config copy. Returns config unchanged if profile is None.

    Override fields set to None (or absent) inherit from global config.
    Profile snippets/vocabulary replace (not merge) globals.
    """
    if profile is None:
        return config

    config = copy.deepcopy(config)

    # Override fields where profile provides a non-None value.
    # Snippets and vocabulary replace (not merge with) globals.
    for field in ("system_prompt", "temperature", "snippets", "custom_vocabulary"):
        val = profile.get(field)
        if val is not None:
            config[field] = val

    return config
