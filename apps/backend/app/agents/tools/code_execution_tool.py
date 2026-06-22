"""
轻量 Python 代码执行工具。

与 ManageNotebook 的区别：
- RunCode：一次性执行，无 notebook 文件开销，适合快速计算/验证/安装包
- ManageNotebook：有 notebook 文件持久化，适合多步实验、需要记录输出的场景
"""

from __future__ import annotations

import asyncio
import json
import os
from typing import Any

from pydantic import BaseModel, Field

from app.core.agent_tool import AiasysTool
from app.core.tool_result import ToolResult
from app.services.history import current_session_id, current_workspace
from app.utils.path_utils import as_system_path


class RunCodeParams(BaseModel):
    code: str = Field(description="要执行的 Python 代码，支持 IPython 魔法命令")
    restart: bool = Field(
        default=False,
        description="执行前是否重启 kernel（清空之前定义的变量）",
    )
    kernel: str = Field(
        default="python3",
        description="kernel spec 名称，默认 python3。可用 ListKernelEnvs 查询可选环境",
    )


class RunCode(AiasysTool):
    """轻量 Python 代码执行。

    直接在当前会话的 IPython kernel 中执行代码，无需创建 notebook 文件。
    适合一次性计算、快速验证、安装 Python 包等场景。
    如果需要多步实验并持久化输出，请使用 ManageNotebook。
    """

    name: str = "RunCode"
    description: str = """在当前 IPython kernel 中执行 Python 代码并返回输出。

适用场景：
- 快速计算/验证（算术、类型检查、正则测试等）
- 安装 Python 包（`%pip install xxx`）
- 调用 API 拿数据
- 一次性数据处理

不适合的场景：
- 多步实验需要记录 → 用 ManageNotebook
- 需要保留多个 cell 的输出 → 用 ManageNotebook

特点：
- 变量在同一 kernel 内保持，后续调用可复用
- 支持指定 kernel 环境（默认 python3），用 ListKernelEnvs 查询可用环境
- 支持 IPython 魔法命令（%pip, %time, %matplotlib 等）
- 支持 matplotlib 图表输出
"""
    params: type[BaseModel] = RunCodeParams

    async def invoke(
        self,
        ctx: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> ToolResult:
        from app.agents.tools.local_ipython_box import LocalIPythonBox

        params = RunCodeParams.model_validate(kwargs)

        if not params.code or not params.code.strip():
            return ToolResult(content="代码不能为空", is_error=True)

        box = LocalIPythonBox()

        workspace = current_workspace.get()
        if workspace:
            box.workspace = workspace
        session_id = current_session_id.get()
        if session_id:
            box.session_id = session_id

        box.notebook_path = None
        box.kernel_name = params.kernel
        box.record_execution = True

        return await box.invoke(
            ctx,
            code=params.code,
            restart=params.restart,
        )


class ListKernelEnvs(AiasysTool):
    """列出当前可用的 IPython kernel 环境。"""

    name: str = "ListKernelEnvs"
    description: str = """列出当前系统中所有可用的 IPython kernel 环境（kernel spec）。

返回每个 kernel 的：
- name：kernel 名称，可用于 RunCode 的 kernel 参数
- display_name：显示名称
- language：编程语言
- executable：Python 解释器路径

适用场景：
- 在执行代码前确认有哪些 Python 环境可用
- 切换到特定环境前的查询
"""
    params: type[BaseModel] | None = None

    async def invoke(
        self,
        ctx: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> ToolResult:
        try:
            from jupyter_client.kernelspec import KernelSpecManager
        except ImportError:
            return ToolResult(
                content="jupyter_client 未安装，无法查询 kernel 列表。",
                is_error=True,
            )

        ksm = KernelSpecManager()
        all_specs = await asyncio.to_thread(ksm.get_all_specs)
        kernels = []
        for name, spec in sorted(all_specs.items()):
            spec_data = spec.get("spec", {})
            executable = spec_data.get("argv", [])[0] if spec_data.get("argv") else None
            executable_exists = bool(
                executable
                and os.path.isabs(os.path.expanduser(executable))
                and os.path.isfile(os.path.expanduser(executable))
            )
            if not executable_exists:
                continue
            kernels.append(
                {
                    "name": name,
                    "display_name": spec_data.get("display_name", name),
                    "language": spec_data.get("language", "unknown"),
                    "executable": executable,
                    "executable_exists": executable_exists,
                }
            )

        return ToolResult(
            content=json.dumps(
                {"status": "success", "count": len(kernels), "kernels": kernels},
                ensure_ascii=False,
                indent=2,
            )
        )


PROTECTED_KERNELS = frozenset({"python3"})


def _register_kernel_env_sync(name: str, python_path: str) -> str:
    """在线程池中完成 kernel spec 的目录清理、临时文件写入和安装，避免阻塞事件循环。"""
    import os
    import shutil
    import tempfile

    from jupyter_client.kernelspec import KernelSpecManager

    ksm = KernelSpecManager()
    save_native = ksm.ensure_native_kernel
    try:
        ksm.ensure_native_kernel = False
        existing_specs = ksm.find_kernel_specs()
    finally:
        ksm.ensure_native_kernel = save_native
    if name in existing_specs:
        shutil.rmtree(as_system_path(str(existing_specs[name])))

    kernel_json = {
        "argv": [
            python_path,
            "-m",
            "ipykernel_launcher",
            "-f",
            "{connection_file}",
        ],
        "display_name": f"Python ({name})",
        "language": "python",
    }

    tmp_dir = tempfile.mkdtemp()
    try:
        json_path = os.path.join(tmp_dir, "kernel.json")
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(kernel_json, f, indent=1, ensure_ascii=False)
        return ksm.install_kernel_spec(tmp_dir, kernel_name=name, user=True)
    finally:
        shutil.rmtree(as_system_path(str(tmp_dir)))


class RegisterKernelEnvParams(BaseModel):
    name: str = Field(description="kernel 名称，需唯一，仅允许小写字母/数字/连字符")
    python_path: str = Field(description="Python 可执行文件的完整路径")


class RegisterKernelEnv(AiasysTool):
    """注册新的 Python kernel 环境。"""

    name: str = "RegisterKernelEnv"
    description: str = """注册一个新的 Python kernel 环境，使其可用于 RunCode 的 kernel 参数。

参数：
- name：kernel 名称（小写），后续用 RunCode(kernel=name) 选择该环境
- python_path：Python 可执行文件完整路径

注意：
- python3 是受保护的内置环境，不允许覆盖
- 注册前可用 ListKernelEnvs 确认名称不冲突
"""
    params: type[BaseModel] = RegisterKernelEnvParams

    async def invoke(
        self,
        ctx: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> ToolResult:
        import os

        params = RegisterKernelEnvParams.model_validate(kwargs)
        name = params.name.strip().lower()
        python_path = params.python_path.strip()

        if not name:
            return ToolResult(content="kernel 名称不能为空", is_error=True)
        if name in PROTECTED_KERNELS:
            return ToolResult(
                content=f"不允许覆盖受保护的内置环境: {name}",
                is_error=True,
            )
        if not os.path.isabs(os.path.expanduser(python_path)):
            return ToolResult(
                content="Python 可执行文件必须是完整绝对路径",
                is_error=True,
            )
        python_path = os.path.expanduser(python_path)
        if not os.path.isfile(python_path):
            return ToolResult(
                content=f"Python 可执行文件不存在: {python_path}",
                is_error=True,
            )

        try:
            from jupyter_client.kernelspec import KernelSpecManager  # noqa: F401
        except ImportError:
            return ToolResult(
                content="jupyter_client 未安装，无法注册 kernel。",
                is_error=True,
            )

        dest = await asyncio.to_thread(_register_kernel_env_sync, name, python_path)

        return ToolResult(
            content=json.dumps(
                {
                    "status": "success",
                    "operation": "register",
                    "name": name,
                    "python_path": python_path,
                    "installed_to": dest,
                },
                ensure_ascii=False,
                indent=2,
            )
        )


class RemoveKernelEnvParams(BaseModel):
    name: str = Field(description="要删除的 kernel 名称")


class RemoveKernelEnv(AiasysTool):
    """删除已注册的 Python kernel 环境。"""

    name: str = "RemoveKernelEnv"
    description: str = """删除一个已注册的 Python kernel 环境。

注意：
- python3 是受保护的内置环境，不允许删除
- 可用 ListKernelEnvs 查询所有已注册环境
"""
    params: type[BaseModel] = RemoveKernelEnvParams

    async def invoke(
        self,
        ctx: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> ToolResult:
        params = RemoveKernelEnvParams.model_validate(kwargs)
        name = params.name.strip().lower()

        if not name:
            return ToolResult(content="kernel 名称不能为空", is_error=True)
        if name in PROTECTED_KERNELS:
            return ToolResult(
                content=f"不允许删除受保护的内置环境: {name}",
                is_error=True,
            )

        try:
            from jupyter_client.kernelspec import KernelSpecManager
        except ImportError:
            return ToolResult(
                content="jupyter_client 未安装，无法删除 kernel。",
                is_error=True,
            )

        ksm = KernelSpecManager()
        save_native = ksm.ensure_native_kernel
        try:
            ksm.ensure_native_kernel = False
            existing_specs = ksm.find_kernel_specs()
        finally:
            ksm.ensure_native_kernel = save_native

        if name not in existing_specs:
            return ToolResult(
                content=f"kernel 不存在: {name}",
                is_error=True,
            )

        removed_path = ksm.remove_kernel_spec(name)

        return ToolResult(
            content=json.dumps(
                {
                    "status": "success",
                    "operation": "remove",
                    "name": name,
                    "removed_path": removed_path,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
