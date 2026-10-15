"""Regression coverage for the plugin-owned ``ctx.goals`` surface (#138280)."""

from __future__ import annotations

from pathlib import Path

import pytest

from hermes_cli.plugins import PluginContext, PluginManager, PluginManifest


@pytest.fixture
def hermes_home(tmp_path, monkeypatch):
    home = tmp_path / ".hermes"
    home.mkdir()
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setenv("HERMES_HOME", str(home))
    from hermes_cli import goals

    goals._DB_CACHE.clear()
    yield home
    goals._DB_CACHE.clear()


def _context(plugin_id: str = "plan-mode") -> PluginContext:
    return PluginContext(PluginManifest(name=plugin_id, key=plugin_id), PluginManager())


def test_plugin_goal_snapshot_is_read_only_and_owner_scoped(hermes_home):
    ctx = _context()

    assert ctx.goals.set("session", "finish the approved plan", max_turns=7)
    goal = ctx.goals.get("session")

    assert goal is not None
    assert (goal.objective, goal.status, goal.turns_used, goal.max_turns, goal.owner) == (
        "finish the approved plan", "active", 0, 7, "plan-mode",
    )
    with pytest.raises(AttributeError):
        goal.status = "paused"


def test_legacy_goal_state_without_owner_remains_user_owned():
    from hermes_cli.goals import GoalState

    restored = GoalState.from_json('{"goal": "existing user goal", "status": "active"}')

    assert restored.owner is None


def test_cached_manager_keeps_live_goal_when_storage_is_temporarily_unavailable(hermes_home, monkeypatch):
    from hermes_cli import goals
    from hermes_cli.goals import GoalManager

    manager = GoalManager("session")
    manager.set("live goal")
    monkeypatch.setattr(goals, "load_goal", lambda _session_id: None)

    assert manager.is_active()


def test_plugin_goal_does_not_replace_existing_standing_goal(hermes_home):
    from hermes_cli.goals import GoalManager

    GoalManager("session").set("user goal")

    assert not _context().goals.set("session", "plugin goal")
    assert GoalManager("session").state.goal == "user goal"


def test_plugin_goal_clear_requires_same_plugin_owner(hermes_home):
    owner = _context("plan-mode")
    other = _context("other-plugin")
    assert owner.goals.set("session", "plugin goal")

    assert not other.goals.clear("session")
    assert owner.goals.clear("session")
    assert owner.goals.get("session") is None


def test_plugin_cannot_impersonate_another_goal_owner(hermes_home):
    ctx = _context("plan-mode")

    with pytest.raises(PermissionError):
        ctx.goals.set("session", "plugin goal", owner="other-plugin")
    with pytest.raises(PermissionError):
        ctx.goals.clear("session", owner="other-plugin")


def test_cached_goal_manager_observes_plugin_goal_and_preserves_it_on_clear(hermes_home):
    from hermes_cli.goals import GoalManager

    cached_cli_manager = GoalManager("session")
    ctx = _context()
    assert ctx.goals.set("session", "plugin-created goal")

    assert cached_cli_manager.is_active()
    assert "plugin-created goal" in cached_cli_manager.status_line()
    assert cached_cli_manager.state.owner == "plan-mode"
    cached_cli_manager.clear()
    assert ctx.goals.get("session") is None
