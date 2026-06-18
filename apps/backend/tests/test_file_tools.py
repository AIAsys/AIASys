"""通用文件读写工具测试。"""

from __future__ import annotations

import pytest
from pathlib import Path

from app.agents.tools.file_tools import (
    ReadFileParams,
    ReadFile,
    StrReplaceFileParams,
    StrReplaceFile,
    WriteFileParams,
    WriteFile,
    FileEdit,
)
from app.services.history import current_global_workspace, current_session_root, current_workspace
from app.services.file_history import file_history_service


@pytest.fixture
def tmp_workspace(tmp_path: Path):
    """设置临时工作区上下文。"""
    token = current_workspace.set(str(tmp_path))
    yield tmp_path
    current_workspace.reset(token)


@pytest.fixture
def tmp_global_workspace(tmp_path: Path):
    """设置临时全局工作区上下文。"""
    global_path = tmp_path / "global"
    global_path.mkdir(parents=True, exist_ok=True)
    token = current_global_workspace.set(str(global_path))
    yield global_path
    current_global_workspace.reset(token)


# ---------------------------------------------------------------------------
# ReadFile
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_read_file_basic(tmp_workspace: Path) -> None:
    (tmp_workspace / "test.txt").write_text("line1\nline2\nline3\n", encoding="utf-8")

    tool = ReadFile()
    result = await tool.invoke(**ReadFileParams(path="test.txt").model_dump())

    assert not result.is_error
    assert "line1" in result.output
    assert "line2" in result.output
    assert "line3" in result.output


@pytest.mark.asyncio
async def test_read_file_line_offset(tmp_workspace: Path) -> None:
    (tmp_workspace / "test.txt").write_text("a\nb\nc\nd\n", encoding="utf-8")

    tool = ReadFile()
    result = await tool.invoke(
        **ReadFileParams(path="test.txt", line_offset=2, n_lines=2).model_dump()
    )

    assert not result.is_error
    assert "a" not in result.output
    assert "b" in result.output
    assert "c" in result.output
    assert "d" not in result.output


@pytest.mark.asyncio
async def test_read_file_tail_mode(tmp_workspace: Path) -> None:
    (tmp_workspace / "test.txt").write_text("1\n2\n3\n4\n5\n", encoding="utf-8")

    tool = ReadFile()
    result = await tool.invoke(**ReadFileParams(path="test.txt", line_offset=-2).model_dump())

    assert not result.is_error
    assert "4" in result.output
    assert "5" in result.output
    assert "1" not in result.output


@pytest.mark.asyncio
async def test_read_file_not_found(tmp_workspace: Path) -> None:
    tool = ReadFile()
    result = await tool.invoke(**ReadFileParams(path="nonexistent.txt").model_dump())

    assert result.is_error
    assert "不存在" in result.message


@pytest.mark.asyncio
async def test_read_file_binary_rejected(tmp_workspace: Path) -> None:
    # 使用无黑名单扩展名的文件，验证 NUL 字节兜底检测
    (tmp_workspace / "binary.data").write_bytes(b"\x00\x01\x02\x03")

    tool = ReadFile()
    result = await tool.invoke(**ReadFileParams(path="binary.data").model_dump())

    assert result.is_error
    assert "二进制" in result.message


@pytest.mark.asyncio
async def test_read_file_non_text_suffix_rejected(tmp_workspace: Path) -> None:
    """验证已知非文本扩展名会被直接拒绝并给出替代建议。"""
    (tmp_workspace / "report.xlsx").write_bytes(b"\x00mock excel")

    tool = ReadFile()
    result = await tool.invoke(**ReadFileParams(path="report.xlsx").model_dump())

    assert result.is_error
    assert "Excel" in result.message
    assert "pandas" in result.message or "openpyxl" in result.message


@pytest.mark.asyncio
async def test_read_file_sensitive_rejected(tmp_workspace: Path) -> None:
    (tmp_workspace / ".env").write_text("SECRET=123")

    tool = ReadFile()
    result = await tool.invoke(**ReadFileParams(path=".env").model_dump())

    assert result.is_error
    assert "敏感文件" in result.message


@pytest.mark.asyncio
async def test_read_file_sensitive_gitignore_patterns(tmp_workspace: Path) -> None:
    """验证 .gitignore 风格敏感文件模式覆盖常见变体。"""
    patterns = [
        ".env.local",
        ".env.production",
        "config/.env",
        "id_rsa",
        "id_ed25519.pub",
        "credentials.json",
        "client_secret_123.json",
        ".aws/credentials",
        ".ssh/config",
    ]
    tool = ReadFile()
    for name in patterns:
        path = tmp_workspace / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("SECRET=123", encoding="utf-8")

        result = await tool.invoke(**ReadFileParams(path=name).model_dump())

        assert result.is_error, f"{name} 应被识别为敏感文件"
        assert "敏感文件" in result.message


@pytest.mark.asyncio
async def test_read_file_magic_byte_rejected(tmp_workspace: Path) -> None:
    """验证扩展名不可信时通过 magic byte 识别二进制文件。"""
    (tmp_workspace / "fake_text.txt").write_bytes(b"\x89PNG\r\n\x1a\n")

    tool = ReadFile()
    result = await tool.invoke(**ReadFileParams(path="fake_text.txt").model_dump())

    assert result.is_error
    assert "PNG" in result.message
    assert "ReadMediaFile" in result.message


@pytest.mark.asyncio
async def test_read_file_expand_block_function(tmp_workspace: Path) -> None:
    """验证缩进感知代码块读取能自动扩展完整函数。"""
    code = "def outer():\n    if True:\n        return 1\n\ndef other():\n    pass\n"
    (tmp_workspace / "code.py").write_text(code, encoding="utf-8")

    tool = ReadFile()
    result = await tool.invoke(
        **ReadFileParams(path="code.py", line_offset=2, expand_block=True).model_dump()
    )

    assert not result.is_error
    assert "def outer():" in result.output
    assert "return 1" in result.output
    assert "def other():" not in result.output


@pytest.mark.asyncio
async def test_read_file_expand_block_class(tmp_workspace: Path) -> None:
    """验证缩进感知读取以 class 自身为锚点时返回整个类。"""
    code = "class Foo:\n    def method(self):\n        pass\n\nclass Bar:\n    pass\n"
    (tmp_workspace / "code.py").write_text(code, encoding="utf-8")

    tool = ReadFile()
    result = await tool.invoke(
        **ReadFileParams(path="code.py", line_offset=1, expand_block=True).model_dump()
    )

    assert not result.is_error
    assert "class Foo:" in result.output
    assert "class Bar:" not in result.output


@pytest.mark.asyncio
async def test_read_file_crlf_normalized_for_display(tmp_workspace: Path) -> None:
    """验证 ReadFile 读取 CRLF 文件时成功显示并把换行符规范化为 LF。"""
    (tmp_workspace / "crlf.txt").write_bytes(b"line1\r\nline2\r\n")

    tool = ReadFile()
    result = await tool.invoke(**ReadFileParams(path="crlf.txt").model_dump())

    assert not result.is_error
    assert "line1" in result.output
    assert "line2" in result.output
    assert "\r\n" not in result.output


# ---------------------------------------------------------------------------
# WriteFile
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_write_file_overwrite(tmp_workspace: Path) -> None:
    tool = WriteFile()
    result = await tool.invoke(
        **WriteFileParams(path="new.txt", content="hello world").model_dump()
    )

    assert not result.is_error
    assert (tmp_workspace / "new.txt").read_text(encoding="utf-8") == "hello world"


@pytest.mark.asyncio
async def test_write_file_append(tmp_workspace: Path) -> None:
    (tmp_workspace / "append.txt").write_text("first\n", encoding="utf-8")

    tool = WriteFile()
    result = await tool.invoke(
        **WriteFileParams(path="append.txt", content="second\n", mode="append").model_dump()
    )

    assert not result.is_error
    content = (tmp_workspace / "append.txt").read_text(encoding="utf-8")
    assert content == "first\nsecond\n"


@pytest.mark.asyncio
async def test_write_file_records_workspace_history(tmp_workspace: Path) -> None:
    (tmp_workspace / "history.txt").write_text("before\n", encoding="utf-8")

    tool = WriteFile()
    result = await tool.invoke(
        **WriteFileParams(path="history.txt", content="after\n").model_dump()
    )

    assert not result.is_error
    entries = file_history_service.list_entries(tmp_workspace, "history.txt")
    assert len(entries) == 1
    assert entries[0].operation == "before_overwrite"
    _, content = file_history_service.read_entry_text(tmp_workspace, entries[0].id)
    assert content == "before\n"


@pytest.mark.asyncio
async def test_write_file_auto_mkdir(tmp_workspace: Path) -> None:
    tool = WriteFile()
    result = await tool.invoke(
        **WriteFileParams(path="sub/dir/file.txt", content="deep").model_dump()
    )

    assert not result.is_error
    assert (tmp_workspace / "sub" / "dir" / "file.txt").read_text(encoding="utf-8") == "deep"


# ---------------------------------------------------------------------------
# StrReplaceFile
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_str_replace_file_single(tmp_workspace: Path) -> None:
    (tmp_workspace / "edit.txt").write_text("hello world", encoding="utf-8")

    tool = StrReplaceFile()
    result = await tool.invoke(
        **StrReplaceFileParams(
            path="edit.txt",
            edit=FileEdit(old="world", new="AIASys"),
        ).model_dump()
    )

    assert not result.is_error
    assert (tmp_workspace / "edit.txt").read_text(encoding="utf-8") == "hello AIASys"


@pytest.mark.asyncio
async def test_str_replace_file_records_workspace_history(tmp_workspace: Path) -> None:
    (tmp_workspace / "edit-history.txt").write_text("hello world", encoding="utf-8")

    tool = StrReplaceFile()
    result = await tool.invoke(
        **StrReplaceFileParams(
            path="edit-history.txt",
            edit=FileEdit(old="world", new="AIASys"),
        ).model_dump()
    )

    assert not result.is_error
    entries = file_history_service.list_entries(tmp_workspace, "edit-history.txt")
    assert len(entries) == 1
    assert entries[0].operation == "before_update"
    _, content = file_history_service.read_entry_text(tmp_workspace, entries[0].id)
    assert content == "hello world"


@pytest.mark.asyncio
async def test_str_replace_file_multi_edit(tmp_workspace: Path) -> None:
    (tmp_workspace / "edit.txt").write_text("foo bar baz", encoding="utf-8")

    tool = StrReplaceFile()
    result = await tool.invoke(
        **StrReplaceFileParams(
            path="edit.txt",
            edit=[
                FileEdit(old="foo", new="FOO"),
                FileEdit(old="baz", new="BAZ"),
            ],
        ).model_dump()
    )

    assert not result.is_error
    assert (tmp_workspace / "edit.txt").read_text(encoding="utf-8") == "FOO bar BAZ"


@pytest.mark.asyncio
async def test_str_replace_file_not_found(tmp_workspace: Path) -> None:
    tool = StrReplaceFile()
    result = await tool.invoke(
        **StrReplaceFileParams(
            path="missing.txt",
            edit=FileEdit(old="a", new="b"),
        ).model_dump()
    )

    assert result.is_error
    assert "不存在" in result.message


@pytest.mark.asyncio
async def test_str_replace_file_no_match(tmp_workspace: Path) -> None:
    (tmp_workspace / "edit.txt").write_text("content", encoding="utf-8")

    tool = StrReplaceFile()
    result = await tool.invoke(
        **StrReplaceFileParams(
            path="edit.txt",
            edit=FileEdit(old="notfound", new="replacement"),
        ).model_dump()
    )

    assert result.is_error
    assert "未找到" in result.message


@pytest.mark.asyncio
async def test_str_replace_file_preserves_crlf(tmp_workspace: Path) -> None:
    """验证 StrReplaceFile 编辑后保持 CRLF 换行符风格。"""
    (tmp_workspace / "edit.txt").write_bytes(b"hello\r\nworld\r\n")

    tool = StrReplaceFile()
    result = await tool.invoke(
        **StrReplaceFileParams(
            path="edit.txt",
            edit=FileEdit(old="hello", new="hi"),
        ).model_dump()
    )

    assert not result.is_error
    assert "保持原换行符风格" in result.output
    assert (tmp_workspace / "edit.txt").read_bytes() == b"hi\r\nworld\r\n"


@pytest.mark.asyncio
async def test_str_replace_file_preserves_lf(tmp_workspace: Path) -> None:
    """验证 StrReplaceFile 编辑后保持 LF 换行符风格。"""
    (tmp_workspace / "edit.txt").write_bytes(b"hello\nworld\n")

    tool = StrReplaceFile()
    result = await tool.invoke(
        **StrReplaceFileParams(
            path="edit.txt",
            edit=FileEdit(old="hello", new="hi"),
        ).model_dump()
    )

    assert not result.is_error
    assert (tmp_workspace / "edit.txt").read_bytes() == b"hi\nworld\n"


@pytest.mark.asyncio
async def test_str_replace_file_magic_byte_rejected(tmp_workspace: Path) -> None:
    """验证 StrReplaceFile 通过 magic byte 拒绝二进制文件。"""
    (tmp_workspace / "fake.txt").write_bytes(b"\x89PNG\r\n\x1a\n")

    tool = StrReplaceFile()
    result = await tool.invoke(
        **StrReplaceFileParams(
            path="fake.txt",
            edit=FileEdit(old="old", new="new"),
        ).model_dump()
    )

    assert result.is_error
    assert "PNG" in result.message


# ---------------------------------------------------------------------------
# Global workspace path support
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_read_file_global_path(tmp_global_workspace: Path) -> None:
    (tmp_global_workspace / "shared.txt").write_text("global content", encoding="utf-8")

    tool = ReadFile()
    result = await tool.invoke(**ReadFileParams(path="/global/shared.txt").model_dump())

    assert not result.is_error
    assert "global content" in result.output


@pytest.mark.asyncio
async def test_write_file_global_path(tmp_global_workspace: Path) -> None:
    tool = WriteFile()
    result = await tool.invoke(
        **WriteFileParams(path="/global/new.txt", content="written to global").model_dump()
    )

    assert not result.is_error
    assert (tmp_global_workspace / "new.txt").read_text(encoding="utf-8") == "written to global"


@pytest.mark.asyncio
async def test_str_replace_file_global_path(tmp_global_workspace: Path) -> None:
    (tmp_global_workspace / "edit.txt").write_text("hello global", encoding="utf-8")

    tool = StrReplaceFile()
    result = await tool.invoke(
        **StrReplaceFileParams(
            path="/global/edit.txt",
            edit=FileEdit(old="global", new="world"),
        ).model_dump()
    )

    assert not result.is_error
    assert (tmp_global_workspace / "edit.txt").read_text(encoding="utf-8") == "hello world"


@pytest.mark.asyncio
async def test_write_file_records_global_history(tmp_global_workspace: Path) -> None:
    (tmp_global_workspace / "shared-history.txt").write_text("global before", encoding="utf-8")

    tool = WriteFile()
    result = await tool.invoke(
        **WriteFileParams(
            path="/global/shared-history.txt",
            content="global after",
        ).model_dump()
    )

    assert not result.is_error
    entries = file_history_service.list_entries(
        tmp_global_workspace,
        "shared-history.txt",
    )
    assert len(entries) == 1
    assert entries[0].source == "agent_tool"


@pytest.mark.asyncio
async def test_global_path_escape_rejected(tmp_global_workspace: Path) -> None:
    tool = ReadFile()
    result = await tool.invoke(**ReadFileParams(path="/global/../etc/passwd").model_dump())

    assert result.is_error
    assert "非法" in result.message or "超出" in result.message


# ---------------------------------------------------------------------------
# /workspace/ prefix support (upload API returns this format)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_read_file_workspace_prefix(tmp_workspace: Path) -> None:
    (tmp_workspace / "A-Attachment.txt").write_text("mock attachment content", encoding="utf-8")

    tool = ReadFile()
    result = await tool.invoke(**ReadFileParams(path="/workspace/A-Attachment.txt").model_dump())

    assert not result.is_error
    assert "mock attachment content" in result.output


@pytest.mark.asyncio
async def test_write_file_workspace_prefix(tmp_workspace: Path) -> None:
    tool = WriteFile()
    result = await tool.invoke(
        **WriteFileParams(path="/workspace/uploaded.txt", content="from upload").model_dump()
    )

    assert not result.is_error
    assert (tmp_workspace / "uploaded.txt").read_text(encoding="utf-8") == "from upload"


@pytest.mark.asyncio
async def test_str_replace_file_workspace_prefix(tmp_workspace: Path) -> None:
    (tmp_workspace / "edit.txt").write_text("hello workspace", encoding="utf-8")

    tool = StrReplaceFile()
    result = await tool.invoke(
        **StrReplaceFileParams(
            path="/workspace/edit.txt",
            edit=FileEdit(old="workspace", new="world"),
        ).model_dump()
    )

    assert not result.is_error
    assert (tmp_workspace / "edit.txt").read_text(encoding="utf-8") == "hello world"


@pytest.mark.asyncio
async def test_workspace_prefix_escape_rejected(tmp_workspace: Path) -> None:
    tool = ReadFile()
    result = await tool.invoke(**ReadFileParams(path="/workspace/../etc/passwd").model_dump())

    assert result.is_error
    assert "非法" in result.message or "超出" in result.message
