"""Tests for profile template definitions and helpers."""

from talkie_modules.profile_templates import PROFILE_TEMPLATES, apply_template_apps, get_template


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


class TestApplyTemplateApps:
    def test_creates_profiles_for_selected_apps(self) -> None:
        template = get_template("chat")
        result = apply_template_apps(template, ["slack", "discord"], [])
        assert len(result["created"]) == 2
        assert len(result["skipped"]) == 0
        names = {p["name"] for p in result["created"]}
        assert "Chat / IM — Slack" in names
        assert "Chat / IM — Discord" in names

    def test_skips_duplicate_process_match(self) -> None:
        existing = [{"match_process": "slack.exe", "match_title": ""}]
        template = get_template("chat")
        result = apply_template_apps(template, ["slack"], existing)
        assert len(result["created"]) == 0
        assert len(result["skipped"]) == 1

    def test_null_and_empty_string_treated_equal(self) -> None:
        existing = [{"match_process": "slack.exe", "match_title": None}]
        template = get_template("chat")
        result = apply_template_apps(template, ["slack"], existing)
        assert len(result["skipped"]) == 1

    def test_created_profiles_have_template_snapshot(self) -> None:
        template = get_template("email")
        result = apply_template_apps(template, ["outlook"], [])
        profile = result["created"][0]
        assert profile["template_id"] == "email"
        assert "template_snapshot" in profile
        assert "system_prompt" in profile["template_snapshot"]

    def test_snapshot_is_deep_copy(self) -> None:
        template = get_template("chat")
        result = apply_template_apps(template, ["slack", "discord"], [])
        result["created"][0]["snippets"]["new_key"] = "new_val"
        assert "new_key" not in result["created"][1]["snippets"]
        assert "new_key" not in result["created"][0]["template_snapshot"]["snippets"]

    def test_created_profiles_have_unique_ids(self) -> None:
        template = get_template("chat")
        result = apply_template_apps(template, ["slack", "discord", "whatsapp"], [])
        ids = [p["id"] for p in result["created"]]
        assert len(ids) == len(set(ids))

    def test_invalid_app_id_ignored(self) -> None:
        template = get_template("email")
        result = apply_template_apps(template, ["nonexistent"], [])
        assert len(result["created"]) == 0
        assert len(result["skipped"]) == 0
