"""Behaviour contracts for the prompt-guidance ablation harness (#134640)."""
import importlib.util
from pathlib import Path

def _harness_module():
    path = Path(__file__).parents[2] / "evals" / "toolperf_abeval" / "ab_eval.py"
    spec = importlib.util.spec_from_file_location("toolperf_abeval", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_guidance_arm_uses_isolated_home_and_only_changes_guidance(tmp_path, monkeypatch):
    harness = _harness_module()
    source_home = tmp_path / "source-home"
    source_home.mkdir()
    (source_home / ".env").write_text("OPENROUTER_API_KEY=test\n", encoding="utf-8")
    (source_home / "config.yaml").write_text(
        "model:\n  provider: openrouter\nagent:\n  task_completion_guidance: true\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(harness, "HOME", source_home)

    arm_home = harness._home_for_guidance_arm(tmp_path / "run", "execution_off")

    config = (arm_home / "config.yaml").read_text(encoding="utf-8")
    assert "model:\n  provider: openrouter\n" in config
    assert "agent:\n  task_completion_guidance: true\n" in config
    assert "  tool_use_enforcement: true\n" in config
    assert "  execution_guidance: false\n" in config
    assert (arm_home / ".env").read_text(encoding="utf-8") == "OPENROUTER_API_KEY=test\n"
    assert (source_home / "config.yaml").read_text(encoding="utf-8") == (
        "model:\n  provider: openrouter\nagent:\n  task_completion_guidance: true\n"
    )


def test_guidance_tasks_score_both_required_tool_work_and_trivial_edit(tmp_path):
    harness = _harness_module()
    harness.make_sandbox(tmp_path)
    project = tmp_path / "proj"

    assert harness.SUCCESS["guidance_tool_action"]("TOKEN=tool_action_2c47", tmp_path)
    (project / "release.txt").write_text("release=ready\n", encoding="utf-8")
    assert harness.SUCCESS["guidance_write_readback"]("release=ready", tmp_path)
    (project / "flag.txt").write_text("enabled\n", encoding="utf-8")
    assert harness.SUCCESS["guidance_trivial_edit"]("DONE", tmp_path)
