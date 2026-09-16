"""System roles include briefs:write for owner/editor."""

from backend.modules.identity_access.system_roles import DEFAULT_PERMISSIONS, SYSTEM_ROLES


def test_briefs_write_in_default_permissions() -> None:
    codes = {code for code, _, _ in DEFAULT_PERMISSIONS}
    assert "briefs:write" in codes


def test_owner_and_editor_can_write_briefs() -> None:
    owner_codes = set(SYSTEM_ROLES["owner"][1])
    editor_codes = set(SYSTEM_ROLES["editor"][1])
    analyst_codes = set(SYSTEM_ROLES["analyst"][1])
    assert "briefs:write" in owner_codes
    assert "briefs:write" in editor_codes
    assert "briefs:write" not in analyst_codes
