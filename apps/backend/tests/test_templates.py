from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.core.templates import (
    WorkspaceTemplate,
    TemplateFileSpec,
    _is_safe_relative_path,
    _is_safe_template_id,
    _dump_template_toml,
    _load_template,
    _parse_env_vars,
    _parse_recommended_capabilities,
    _generate_template_id,
    list_workspace_templates,
    get_workspace_template,
    build_template_payload,
    apply_template_to_workspace,
    export_workspace_as_template,
    delete_user_template,
)


class TestSafePathGuards:
    """路径安全校验测试。"""

    @pytest.mark.parametrize("path,expected", [
        ("README.md", True),
        ("dir/file.txt", True),
        ("", False),
        ("../secret.txt", False),
        ("./file.txt", False),
        ("/.bashrc", False),
        ("a//b", False),
        (".git/config", False),
        ("dir/../escape", False),
        ("file\x00.txt", False),
        ("windows\\path", True),
    ])
    def test_is_safe_relative_path(self, path: str, expected: bool) -> None:
        assert _is_safe_relative_path(path) is expected

    @pytest.mark.parametrize("tid,expected", [
        ("blank-workspace", True),
        ("my-template", True),
        ("", False),
        (" ", False),
        ("../etc", False),
        ("a/b", False),
        ("a\\b", False),
        ("..", False),
        ("/abs", False),
    ])
    def test_is_safe_template_id(self, tid: str, expected: bool) -> None:
        assert _is_safe_template_id(tid) is expected


class TestTomlSerialization:
    """TOML 序列化与反序列化测试。"""

    def test_dump_and_load_roundtrip(self, tmp_path: Path) -> None:
        """导出再加载后，关键字段保持一致。"""
        template_dir = tmp_path / "test-tmpl"
        template_dir.mkdir()

        data = {
            "template_id": "test-roundtrip",
            "name": "测试模板",
            "description": "包含 \"\"\" 和换行",
            "icon": "file",
            "category": "测试",
            "default_title": "新任务",
            "default_description": "",
            "initial_conversation_title": "新对话",
            "env_kind": "uv",
            "files": [
                {
                    "relative_path": "README.md",
                    "content": "# Hello\n```python\nprint(\"\"\"hi\"\"\")\n```",
                }
            ],
            "env_vars": {"FOO": "bar"},
            "recommended_skills": [],
            "recommended_mcps": [],
            "recommended_capabilities": [],
        }
        (template_dir / "template.toml").write_text(
            _dump_template_toml(data), encoding="utf-8"
        )

        loaded = _load_template(template_dir)
        assert loaded is not None
        assert loaded.template_id == "test-roundtrip"
        assert loaded.name == "测试模板"
        assert 'print("""hi""")' in loaded.files[0].content
        assert loaded.env_vars == {"FOO": "bar"}


class TestSourcePathTraversal:
    """source_path 路径穿越防护测试。"""

    def test_source_path_traversal_rejected(self, tmp_path: Path) -> None:
        """source_path 包含 .. 时必须被拒绝，不能读取模板目录外文件。"""
        template_dir = tmp_path / "tmpl"
        template_dir.mkdir()
        secret_file = tmp_path / "secret.txt"
        secret_file.write_text("SECRET", encoding="utf-8")

        toml_content = f'''
template_id = "bad-tmpl"
name = "Bad"
[[files]]
relative_path = "stolen.txt"
source_path = "../secret.txt"
'''
        (template_dir / "template.toml").write_text(toml_content, encoding="utf-8")

        loaded = _load_template(template_dir)
        assert loaded is not None
        # source_path 不安全的文件应被跳过
        assert len(loaded.files) == 0

    def test_source_path_hidden_file_rejected(self, tmp_path: Path) -> None:
        template_dir = tmp_path / "tmpl"
        template_dir.mkdir()
        (template_dir / ".env").write_text("API_KEY=123", encoding="utf-8")

        toml_content = '''
template_id = "hidden-tmpl"
name = "Hidden"
[[files]]
relative_path = "env.txt"
source_path = ".env"
'''
        (template_dir / "template.toml").write_text(toml_content, encoding="utf-8")

        loaded = _load_template(template_dir)
        assert loaded is not None
        assert len(loaded.files) == 0


class TestParseEnvVars:
    def test_parse_env_vars_valid(self) -> None:
        assert _parse_env_vars({"FOO": "bar", 1: "num_key"}) == {"FOO": "bar", "1": "num_key"}

    def test_parse_env_vars_invalid(self) -> None:
        assert _parse_env_vars(None) == {}
        assert _parse_env_vars("string") == {}
        assert _parse_env_vars([]) == {}


class TestListAndGetTemplates:
    """模板列表与查询测试。"""

    def test_user_template_overrides_builtin(self, tmp_path: Path, monkeypatch) -> None:
        """同名时用户自定义模板应覆盖系统内置。"""
        import app.core.templates as tmpl_mod

        builtin_dir = tmp_path / "builtin"
        builtin_dir.mkdir()
        user_dir = tmp_path / "user"
        user_dir.mkdir()

        (builtin_dir / "shared" / "template.toml").parent.mkdir(parents=True)
        (builtin_dir / "shared" / "template.toml").write_text(
            'template_id = "shared"\nname = "Builtin"\n', encoding="utf-8"
        )
        (user_dir / "shared" / "template.toml").parent.mkdir(parents=True)
        (user_dir / "shared" / "template.toml").write_text(
            'template_id = "shared"\nname = "User"\n', encoding="utf-8"
        )

        monkeypatch.setattr(tmpl_mod, "_TEMPLATES_DIR", builtin_dir)
        monkeypatch.setattr(
            tmpl_mod,
            "_get_user_templates_dir",
            lambda _uid: user_dir,
        )

        templates = list_workspace_templates(user_id="u1")
        shared = [t for t in templates if t.template_id == "shared"]
        assert len(shared) == 1
        assert shared[0].name == "User"

        got = get_workspace_template("shared", user_id="u1")
        assert got is not None
        assert got.name == "User"


class TestBuildTemplatePayload:
    def test_is_builtin_for_system_template(self, monkeypatch) -> None:
        import app.core.templates as tmpl_mod
        fake_dir = Path("/fake/templates")
        monkeypatch.setattr(tmpl_mod, "_TEMPLATES_DIR", fake_dir)
        tmpl = WorkspaceTemplate(
            template_id="sys",
            name="System",
            description="",
            icon="file",
            category="",
            default_title="",
            default_description="",
            initial_conversation_title="",
            env_kind="none",
            files=[],
            source_dir=fake_dir / "sys",
            recommended_skills=[],
            recommended_mcps=[],
            recommended_capabilities=[],
        )
        payload = build_template_payload(tmpl)
        assert payload["is_builtin"] is True


class TestExportWorkspaceAsTemplate:
    """导出模板功能测试。"""

    def test_export_basic_workspace(self, tmp_path: Path) -> None:
        """正常导出工作区为模板，不应抛出异常。"""
        workspace_dir = tmp_path / "ws" / "demo"
        workspace_dir.mkdir(parents=True)
        (workspace_dir / ".aiasys" / "workspace").mkdir(parents=True)
        (workspace_dir / ".aiasys" / "workspace" / "workspace.json").write_text(
            json.dumps({"title": "Demo WS", "description": "A demo"}),
            encoding="utf-8",
        )
        (workspace_dir / "README.md").write_text("# Demo", encoding="utf-8")

        import app.core.templates as tmpl_mod
        monkeypatch = pytest.MonkeyPatch()
        monkeypatch.setattr(
            tmpl_mod,
            "_get_user_templates_dir",
            lambda _uid: tmp_path / "user_templates",
        )

        result = export_workspace_as_template(
            workspace_dir=workspace_dir,
            user_id="u1",
            name="导出的模板",
        )
        assert result.template_id.startswith("导出")
        assert result.name == "导出的模板"
        assert result.files[0].relative_path == "README.md"
        monkeypatch.undo()

    def test_export_preserves_env_vars(self, tmp_path: Path) -> None:
        """导出时应保留工作区环境变量（需显式开启 include_env_vars）。"""
        workspace_dir = tmp_path / "ws" / "env-ws"
        workspace_dir.mkdir(parents=True)
        (workspace_dir / ".aiasys" / "workspace").mkdir(parents=True)
        (workspace_dir / ".aiasys" / "workspace" / "workspace.json").write_text(
            json.dumps({"title": "Env WS"}),
            encoding="utf-8",
        )

        import app.core.templates as tmpl_mod
        monkeypatch = pytest.MonkeyPatch()
        monkeypatch.setattr(
            tmpl_mod,
            "_get_user_templates_dir",
            lambda _uid: tmp_path / "user_templates",
        )

        # 默认不导出 env_vars
        result = export_workspace_as_template(
            workspace_dir=workspace_dir,
            user_id="u1",
            name="Env Template",
        )
        assert result.env_vars == {}
        monkeypatch.undo()


class TestDeleteUserTemplate:
    """删除用户模板测试。"""

    def test_delete_existing_user_template(self, tmp_path: Path, monkeypatch) -> None:
        import app.core.templates as tmpl_mod
        user_dir = tmp_path / "user_templates"
        user_dir.mkdir()
        (user_dir / "my-tmpl" / "template.toml").parent.mkdir(parents=True)
        (user_dir / "my-tmpl" / "template.toml").write_text(
            'template_id = "my-tmpl"\nname = "Mine"\n', encoding="utf-8"
        )
        monkeypatch.setattr(tmpl_mod, "_get_user_templates_dir", lambda _uid: user_dir)

        assert delete_user_template("my-tmpl", "u1") is True
        assert not (user_dir / "my-tmpl").exists()

    def test_delete_builtin_template_refused(self, tmp_path: Path, monkeypatch) -> None:
        """系统内置模板不可删除。"""
        import app.core.templates as tmpl_mod
        builtin_dir = tmp_path / "builtin"
        builtin_dir.mkdir()
        (builtin_dir / "builtin-tmpl" / "template.toml").parent.mkdir(parents=True)
        (builtin_dir / "builtin-tmpl" / "template.toml").write_text(
            'template_id = "builtin-tmpl"\nname = "Builtin"\n', encoding="utf-8"
        )
        monkeypatch.setattr(tmpl_mod, "_TEMPLATES_DIR", builtin_dir)

        assert delete_user_template("builtin-tmpl", "u1") is False

    def test_delete_unsafe_id(self) -> None:
        """不安全的 template_id 应直接拒绝。"""
        assert delete_user_template("../etc", "u1") is False
        assert delete_user_template("", "u1") is False


class TestApplyTemplateToWorkspace:
    """模板应用到工作区测试。"""

    def test_applies_files(self, tmp_path: Path) -> None:
        workspace_dir = tmp_path / "ws"
        workspace_dir.mkdir()
        tmpl = WorkspaceTemplate(
            template_id="t1",
            name="T1",
            description="",
            icon="file",
            category="",
            default_title="",
            default_description="",
            initial_conversation_title="",
            env_kind="none",
            files=[
                TemplateFileSpec(relative_path="hello.txt", content="world"),
            ],
            source_dir=workspace_dir,
            recommended_skills=[],
            recommended_mcps=[],
            recommended_capabilities=[],
        )
        apply_template_to_workspace(workspace_dir, tmpl)
        assert (workspace_dir / "hello.txt").read_text(encoding="utf-8") == "world"

    def test_skips_unsafe_file_paths(self, tmp_path: Path) -> None:
        workspace_dir = tmp_path / "ws"
        workspace_dir.mkdir()
        tmpl = WorkspaceTemplate(
            template_id="t1",
            name="T1",
            description="",
            icon="file",
            category="",
            default_title="",
            default_description="",
            initial_conversation_title="",
            env_kind="none",
            files=[
                TemplateFileSpec(relative_path="../secret.txt", content="bad"),
                TemplateFileSpec(relative_path="safe.txt", content="good"),
            ],
            source_dir=workspace_dir,
            recommended_skills=[],
            recommended_mcps=[],
            recommended_capabilities=[],
        )
        apply_template_to_workspace(workspace_dir, tmpl)
        assert not (workspace_dir / "../secret.txt").exists()
        assert (workspace_dir / "safe.txt").read_text(encoding="utf-8") == "good"
