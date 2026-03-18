"""Tests for profile template definitions and helpers."""

from talkie_modules.profile_templates import PROFILE_TEMPLATES, get_template


class TestTemplateIntegrity:
    """Verify template data is well-formed."""

    def test_all_templates_have_required_fields(self) -> None:
        required = {"id", "name", "description", "icon", "apps",
                    "system_prompt", "snippets", "custom_vocabulary", "temperature"}
        for t in PROFILE_TEMPLATES:
            missing = required - set(t.keys())
            assert not missing, f"Template {t.get('id', '?')} missing: {missing}"

    def test_all_app_entries_have_required_fields(self) -> None:
        required = {"id", "name", "match_process", "match_title"}
        for t in PROFILE_TEMPLATES:
            for app in t["apps"]:
                missing = required - set(app.keys())
                assert not missing, f"App {app.get('id', '?')} in {t['id']} missing: {missing}"

    def test_template_ids_unique(self) -> None:
        ids = [t["id"] for t in PROFILE_TEMPLATES]
        assert len(ids) == len(set(ids))

    def test_app_ids_unique_within_template(self) -> None:
        for t in PROFILE_TEMPLATES:
            ids = [a["id"] for a in t["apps"]]
            assert len(ids) == len(set(ids)), f"Duplicate app id in {t['id']}"

    def test_app_ids_globally_unique(self) -> None:
        all_ids = []
        for t in PROFILE_TEMPLATES:
            all_ids.extend(a["id"] for a in t["apps"])
        assert len(all_ids) == len(set(all_ids))

    def test_system_prompts_contain_placeholders(self) -> None:
        for t in PROFILE_TEMPLATES:
            prompt = t["system_prompt"]
            assert "{snippets}" in prompt, f"{t['id']} prompt missing {{snippets}}"
            assert "{vocabulary}" in prompt, f"{t['id']} prompt missing {{vocabulary}}"

    def test_temperatures_in_valid_range(self) -> None:
        for t in PROFILE_TEMPLATES:
            assert 0 <= t["temperature"] <= 2.0, f"{t['id']} temp out of range"

    def test_six_templates_exist(self) -> None:
        assert len(PROFILE_TEMPLATES) == 6
        ids = {t["id"] for t in PROFILE_TEMPLATES}
        assert ids == {"email", "chat", "code", "documents", "notes", "browser"}


class TestGetTemplate:
    def test_get_existing(self) -> None:
        t = get_template("email")
        assert t is not None
        assert t["id"] == "email"

    def test_get_nonexistent(self) -> None:
        assert get_template("nonexistent") is None
