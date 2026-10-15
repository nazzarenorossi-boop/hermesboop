"""Shared bundle operations use real filesystem and entrypoint contracts."""
from __future__ import annotations

import io
import json
import os
import shutil
import stat
import subprocess
import sys
import tarfile
from pathlib import Path


import pytest

from scripts.bundles.payload import relativize_links, snapshot
from scripts.build.inputs import project_entries
from scripts.build.agent import plant_surfaces
from scripts.build.launchers import posix_launcher
from scripts.bundles.desktop import release_version


def _stub_snapshot_archive(monkeypatch) -> None:
    """Supply the bytes that ``git archive`` would produce without a live git subprocess."""
    from scripts.bundles import payload

    def archive(command, **_kwargs):
        output = Path(command[command.index("--output") + 1])
        with tarfile.open(output, "w") as source:
            member = tarfile.TarInfo("pkg/mod.py")
            data = b"VALUE = 1\n"
            member.size = len(data)
            source.addfile(member, io.BytesIO(data))
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(payload.subprocess, "run", archive)


def test_snapshot_uses_readonly_aware_cleanup(tmp_path, monkeypatch):
    """Regression for #137717: repeated payload preparation uses the cleanup helper."""
    from scripts.bundles import payload

    repo = tmp_path / "source"
    repo.mkdir()
    destination = tmp_path / "payload"
    _stub_snapshot_archive(monkeypatch)
    snapshot(repo, "HEAD", destination)
    cleanup_calls: list[Path] = []

    def cleanup(path: Path) -> None:
        cleanup_calls.append(path)
        shutil.rmtree(path)

    monkeypatch.setattr(payload, "rmtree_readonly", cleanup)
    snapshot(repo, "HEAD", destination)

    assert cleanup_calls == [destination.resolve()]
    assert (destination / "pkg" / "mod.py").read_text(encoding="utf-8") == "VALUE = 1\n"


@pytest.mark.platforms("windows")
def test_snapshot_replaces_payload_with_readonly_bytecode_on_windows(tmp_path, monkeypatch):
    """A second prepare removes pycs sealed read-only by ``bake_bytecode`` (#137717)."""
    repo = tmp_path / "source"
    repo.mkdir()
    destination = tmp_path / "payload"
    _stub_snapshot_archive(monkeypatch)
    snapshot(repo, "HEAD", destination)
    cache = destination / "pkg" / "__pycache__"
    cache.mkdir()
    pyc = cache / "mod.cpython-314.pyc"
    pyc.write_bytes(b"baked")
    pyc.chmod(stat.S_IREAD)

    snapshot(repo, "HEAD", destination)

    assert destination.exists()
    assert (destination / "pkg" / "mod.py").read_text(encoding="utf-8") == "VALUE = 1\n"


def test_release_version_comes_from_the_release_identity_not_the_checkout(tmp_path):
    (tmp_path / "pyproject.toml").write_text('[project]\nversion="0.0.0"\n', encoding="utf-8")
    assert release_version(tmp_path, "v1.2.3") == "1.2.3"
    assert release_version(tmp_path, "v1.2.4") == "1.2.4"


def test_wrapper_rejects_unresolved_template_fields(tmp_path, monkeypatch):
    from scripts.build import launchers

    template = tmp_path / "launcher_wrapper.py"
    template.write_text('entry = "__HERMES_ENTRY_MODULE__"\nmissing = "__HERMES_NEW__"\n', encoding="utf-8")
    monkeypatch.setattr(launchers, "__file__", str(tmp_path / "payload.py"))
    with pytest.raises(ValueError, match="__HERMES_NEW__"):
        launchers.render_wrapper("entry:run", "../app", "../venv/Lib/site-packages")


@pytest.mark.platforms("posix")
def test_relocation_preserves_sibling_and_framework_links(tmp_path):
    root = tmp_path / "payload"
    store = root / "tools/python/bin"
    venv = root / "venv/bin"
    store.mkdir(parents=True)
    venv.mkdir(parents=True)
    (store / "python3").write_text("interpreter", encoding="utf-8")
    (venv / "python").symlink_to("/builder/tools/python/bin/python3")
    (venv / "python3").symlink_to("python")
    framework = root / "tools/framework"
    framework.symlink_to("python/bin/python3")
    assert relativize_links(root) == 1
    assert (venv / "python3").read_text(encoding="utf-8-sig") == "interpreter"
    assert os.readlink(venv / "python3") == "python"
    assert os.readlink(framework) == "python/bin/python3"
    assert relativize_links(root) == 0
    (venv / "bad").symlink_to("/usr/bin/python")
    with pytest.raises(ValueError, match="escapes payload"):
        relativize_links(root)


@pytest.mark.platforms("posix")
@pytest.mark.parametrize("target", ["linux-x64", "linux-arm64-bionic"])
def test_both_launchers_keep_active_home_and_call_declared_function(tmp_path, target):
    root = tmp_path / "payload with spaces"
    (root / "bin").mkdir(parents=True)
    (root / "app").mkdir()
    (root / "python").symlink_to(sys.executable)
    (root / "app/entry.py").write_text("import json,os,sys\ndef run():\n print(json.dumps([os.environ['HERMES_HOME'],sys.argv[1:]])); return 7\n", encoding="utf-8")
    launcher = root / "bin/custom"
    launcher.write_text(posix_launcher("custom", "entry:run", python="python", repo="app", site="deps", target=target), encoding="utf-8")
    result = subprocess.run(["sh", str(launcher), "two words", "$(nope)", ""], cwd=tmp_path,
                            env={**os.environ, "HERMES_HOME": str(tmp_path / "custom/profiles/memory")}, capture_output=True, text=True, check=False)
    assert result.returncode == 7, result.stderr
    assert json.loads(result.stdout) == [str(tmp_path / "custom/profiles/memory"), ["two words", "$(nope)", ""]]
