from __future__ import annotations

from pathlib import Path

from app.services.export import markdown_export


def test_binary_candidates_checks_windows_venv_scripts(
    monkeypatch,
    tmp_path: Path,
) -> None:
    scripts_dir = tmp_path / "Scripts"
    scripts_dir.mkdir()
    pandoc_cmd = scripts_dir / "pandoc.cmd"
    pandoc_cmd.write_text("@echo off\n", encoding="utf-8")

    monkeypatch.setattr(markdown_export.shutil, "which", lambda command: None)
    monkeypatch.setattr(markdown_export.sys, "prefix", str(tmp_path))
    monkeypatch.setattr(markdown_export.sys, "executable", str(tmp_path / "python.exe"))
    monkeypatch.setattr(
        markdown_export,
        "_binary_script_names",
        lambda command: [command, f"{command}.exe", f"{command}.cmd", f"{command}.bat"],
    )
    monkeypatch.delenv("VIRTUAL_ENV", raising=False)

    assert markdown_export._binary_candidates("pandoc") == [str(pandoc_cmd)]
