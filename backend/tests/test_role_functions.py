"""Role → function catalog: defaults mirror the old has_role gates, overrides win,
platform_admin is locked, and a saved checklist round-trips to minimal overrides."""

import pytest
from app.core.permissions import (
    FUNCTIONS,
    FUNCTIONS_BY_CODE,
    default_allowed,
    overrides_for_desired,
    role_allows,
    role_function_states,
    user_can,
)


def test_catalog_codes_are_unique_and_grouped():
    codes = [f.code for f in FUNCTIONS]
    assert len(codes) == len(set(codes))
    assert all(f.label and f.group for f in FUNCTIONS)


def test_platform_admin_has_everything_even_against_overrides():
    overrides = {("platform_admin", f.code): False for f in FUNCTIONS}
    assert all(role_allows("platform_admin", f.code, overrides) for f in FUNCTIONS)


@pytest.mark.parametrize(
    ("role", "code", "expected"),
    [
        # sets the old has_role(...) gates allowed
        ("org_admin", "users.manage", True),
        ("auditor", "users.view", True),
        ("auditor", "users.manage", False),
        ("org_admin", "audit.view", False),  # audit log was platform_admin only
        ("app_builder", "apps.create", True),
        ("app_admin", "apps.trash", True),
        ("org_admin", "users.delete", False),
        ("custom_abc", "users.view", False),  # custom roles start with nothing
    ],
)
def test_defaults_match_previous_behaviour(role, code, expected):
    assert default_allowed(role, code) is expected
    assert role_allows(role, code, {}) is expected


def test_override_wins_in_both_directions():
    assert role_allows("org_admin", "users.manage", {("org_admin", "users.manage"): False}) is False
    assert role_allows("auditor", "audit.view", {("auditor", "audit.view"): True}) is True


def test_unknown_function_is_never_allowed():
    assert role_allows("platform_admin", "nope.nope", {}) is False
    assert user_can(["platform_admin"], "nope.nope", {}) is False


def test_user_with_several_roles_gets_the_union():
    overrides = {("org_admin", "users.manage"): False}
    # org_admin lost users.manage, but the second role is a custom role that has it
    overrides[("custom_x", "users.manage")] = True
    assert user_can(["org_admin", "custom_x"], "users.manage", overrides) is True
    assert user_can(["org_admin"], "users.manage", overrides) is False


def test_checklist_round_trips_with_minimal_overrides():
    role = "org_admin"
    defaults = {f.code for f in FUNCTIONS if default_allowed(role, f.code)}

    # saving the defaults stores nothing
    assert overrides_for_desired(role, defaults) == {}

    # remove one default, add one extra
    desired = (defaults - {"users.manage"}) | {"audit.view"}
    ov = overrides_for_desired(role, desired)
    assert ov == {(role, "users.manage"): False, (role, "audit.view"): True}

    states = role_function_states(role, ov)
    assert {c for c, ok in states.items() if ok} == desired


def test_custom_role_stores_only_the_granted_functions():
    ov = overrides_for_desired("custom_1", {"users.view", "roles.view"})
    assert ov == {("custom_1", "users.view"): True, ("custom_1", "roles.view"): True}


def test_every_default_role_references_known_functions():
    for f in FUNCTIONS:
        assert f.code in FUNCTIONS_BY_CODE
        assert "platform_admin" in f.default_roles or f.code == "x"
