"""Kernel 环境管理 API。

提供已注册 kernel spec 的列表、注册和删除能力。
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.core.auth import require_auth
from app.models.user import UserInfo

router = APIRouter(prefix="/kernel-envs", tags=["kernel-envs"])

PROTECTED_KERNELS = frozenset({"python3"})

_SYSTEM_PYTHON = sys.executable


def _is_absolute_python_path(value: str | None) -> bool:
    if not value:
        return False
    return os.path.isabs(os.path.expanduser(value))


def _is_system_python(executable: str | None) -> bool:
    if not executable:
        return False
    try:
        return os.path.samefile(executable, _SYSTEM_PYTHON)
    except OSError:
        return os.path.abspath(executable) == os.path.abspath(_SYSTEM_PYTHON)


class RegisterKernelEnvRequest(BaseModel):
    name: str = Field(description="kernel 名称，需唯一")
    python_path: str = Field(description="Python 可执行文件完整路径")


def _get_kernel_specs() -> dict[str, Any]:
    from jupyter_client.kernelspec import KernelSpecManager

    ksm = KernelSpecManager()
    return ksm.get_all_specs()


def _find_kernel_spec_dir(name: str) -> str | None:
    """查找指定 kernel 的安装目录。"""
    from jupyter_client.kernelspec import KernelSpecManager

    ksm = KernelSpecManager()
    save_native = ksm.ensure_native_kernel
    try:
        ksm.ensure_native_kernel = False
        specs = ksm.find_kernel_specs()
    finally:
        ksm.ensure_native_kernel = save_native
    return specs.get(name)


@router.get("")
async def list_kernel_envs(
    current_user: UserInfo = Depends(require_auth()),
) -> dict[str, Any]:
    """列出所有已注册的 kernel spec。"""
    try:
        all_specs = _get_kernel_specs()
    except ImportError:
        raise HTTPException(status_code=500, detail="jupyter_client 未安装")

    kernels = []
    for name, spec in sorted(all_specs.items()):
        spec_data = spec.get("spec", {})
        executable = spec_data.get("argv", [])[0] if spec_data.get("argv") else None
        is_system = _is_system_python(executable)
        executable_exists = bool(
            executable
            and _is_absolute_python_path(executable)
            and os.path.isfile(os.path.expanduser(executable))
        )
        if is_system or not executable_exists:
            continue
        kernels.append(
            {
                "name": name,
                "display_name": spec_data.get("display_name", name),
                "language": spec_data.get("language", "unknown"),
                "executable": executable,
                "executable_exists": executable_exists,
                "protected": name in PROTECTED_KERNELS,
                "forbidden": is_system,
                "forbidden_reason": (
                    "该解释器是 AIASys 后端运行环境，使用它执行代码可能导致后端依赖被破坏、服务无法启动。"
                    if is_system
                    else None
                ),
            }
        )
    return {"status": "success", "count": len(kernels), "kernels": kernels}


@router.post("")
async def register_kernel_env(
    request: RegisterKernelEnvRequest,
    current_user: UserInfo = Depends(require_auth()),
) -> dict[str, Any]:
    """注册一个新的 kernel 环境。"""
    from jupyter_client.kernelspec import KernelSpecManager

    name = request.name.strip().lower()
    python_path = request.python_path.strip()

    if not name:
        raise HTTPException(status_code=400, detail="kernel 名称不能为空")
    if name in PROTECTED_KERNELS:
        raise HTTPException(status_code=400, detail=f"不允许覆盖受保护的 kernel: {name}")
    if not _is_absolute_python_path(python_path):
        raise HTTPException(status_code=400, detail="Python 可执行文件必须是完整绝对路径")
    if _is_system_python(python_path):
        raise HTTPException(
            status_code=400,
            detail="不允许注册 AIASys 后端运行环境作为解释器，使用它执行代码可能导致后端依赖被破坏、服务无法启动。",
        )
    python_path = os.path.expanduser(python_path)
    if not os.path.isfile(python_path):
        raise HTTPException(status_code=400, detail=f"Python 可执行文件不存在: {python_path}")

    # 校验 ipykernel 是否已安装
    import subprocess

    try:
        result = subprocess.run(
            [python_path, "-m", "ipykernel", "--version"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            raise HTTPException(
                status_code=400,
                detail=f"该 Python 环境未安装 ipykernel，请先运行: {python_path} -m pip install ipykernel",
            )
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=400, detail="校验 ipykernel 超时")
    except FileNotFoundError:
        raise HTTPException(
            status_code=400,
            detail=f"Python 可执行文件无法执行: {python_path}",
        )

    # 检查是否已存在
    existing = _find_kernel_spec_dir(name)
    if existing is not None:
        shutil.rmtree(existing)

    # 创建临时 kernel.json
    kernel_json = {
        "argv": [python_path, "-m", "ipykernel_launcher", "-f", "{connection_file}"],
        "display_name": f"Python ({name})",
        "language": "python",
    }

    tmp_dir = tempfile.mkdtemp()
    try:
        json_path = os.path.join(tmp_dir, "kernel.json")
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(kernel_json, f, indent=1, ensure_ascii=False)

        ksm = KernelSpecManager()
        dest = ksm.install_kernel_spec(tmp_dir, kernel_name=name, user=True)
    finally:
        shutil.rmtree(tmp_dir)

    return {
        "status": "success",
        "operation": "register",
        "name": name,
        "python_path": python_path,
        "installed_to": dest,
    }


@router.delete("/{name}")
async def remove_kernel_env(
    name: str,
    current_user: UserInfo = Depends(require_auth()),
) -> dict[str, Any]:
    """删除一个已注册的 kernel 环境。"""
    from jupyter_client.kernelspec import KernelSpecManager

    if name in PROTECTED_KERNELS:
        raise HTTPException(status_code=400, detail=f"不允许删除受保护的 kernel: {name}")

    spec_dir = _find_kernel_spec_dir(name)
    if spec_dir is None:
        raise HTTPException(status_code=404, detail=f"kernel 不存在: {name}")

    ksm = KernelSpecManager()
    removed_path = ksm.remove_kernel_spec(name)

    return {
        "status": "success",
        "operation": "remove",
        "name": name,
        "removed_path": removed_path,
    }
