"""Skill 管理工具。

提供 Agent 发现和使用 Skill 的能力，配合渐进式披露机制：
- ListSkills: 列出所有可用 Skill（builtin + workspace）
- LoadSkill: 按需加载指定 Skill 的 SKILL.md 或子文件
- SearchStoreSkills: 搜索 Skill 仓库
- EnableSkill: 将 Skill 从仓库启用到当前工作区或我的默认
- DisableSkill: 从当前工作区禁用 Skill
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from app.core.agent_tool import AiasysTool
from app.core.tool_result import ToolResult
from app.services.history import current_workspace


class ListSkillsParams(BaseModel):
    """ListSkills 参数。"""

    pass


class LoadSkillParams(BaseModel):
    """LoadSkill 参数。"""

    name: str = Field(description="Skill 名称（目录名或 SKILL.md frontmatter 中的 name）")
    file: str = Field(
        default="SKILL.md",
        description="Skill 目录下的相对文件路径，默认读取 SKILL.md",
    )


class SearchStoreSkillsParams(BaseModel):
    """SearchStoreSkills 参数。"""

    query: str = Field(
        default="",
        description="搜索关键词，匹配 Skill 名称、展示名或描述。为空时返回全部。",
    )
    source: str = Field(
        default="",
        description="按来源过滤：builtin（系统内置）、store（用户导入）。为空时不过滤。",
    )


class EnableSkillParams(BaseModel):
    """EnableSkill 参数。"""

    name: str = Field(description="要启用的 Skill 名称（Skill 仓库中的目录名）")
    scope: str = Field(
        default="workspace",
        description="启用范围：workspace（当前工作区，默认）或 global（我的默认）",
    )
    force: bool = Field(
        default=False,
        description="如果目标范围中已存在同名 Skill，是否强制覆盖",
    )


class DisableSkillParams(BaseModel):
    """DisableSkill 参数。"""

    name: str = Field(description="要禁用的 Skill 名称（工作区中的目录名）")
    scope: str = Field(
        default="workspace",
        description="禁用范围：workspace（当前工作区，默认）或 global（我的默认）",
    )


class ListSkills(AiasysTool):
    """列出当前工作区所有可用 Skill（内置 + 工作区自有）。

    返回每个 Skill 的名称、描述和来源（builtin/workspace）。
    同名 Skill 以工作区版本优先。
    """

    name: str = "ListSkills"
    description: str = """列出当前上下文所有可用 Skill。

返回信息包括：
- name: Skill 目录名
- display_name: SKILL.md frontmatter 中的名称（如有）
- description: Skill 功能描述
- source: builtin（系统内置）或 workspace（工作区自有）

使用场景：
- 不确定当前有哪些 Skill 可用时
- 想查看某个 Skill 的简要描述时
- 需要确认 Skill 来源时

返回格式为 JSON 数组，每个元素是一个 Skill 元数据对象。
"""
    params: type[BaseModel] = ListSkillsParams

    async def invoke(
        self,
        ctx: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> ToolResult:
        params = ListSkillsParams.model_validate(kwargs)
        del params

        from app.skills.manager import get_skill_manager

        workspace = current_workspace.get()
        if not workspace:
            return ToolResult(content="当前上下文未设置工作区", is_error=True)

        workspace_path = Path(workspace)
        mgr = get_skill_manager()
        skills = mgr.list_all_skills(workspace_path)

        items = []
        for skill in skills:
            items.append(
                {
                    "name": skill.name,
                    "display_name": skill.display_name,
                    "description": skill.description,
                    "source": skill.source,
                    "path": str(skill.path),
                }
            )

        return ToolResult(
            content=f"可用 Skill 共 {len(items)} 个",
            artifacts=[{"skills": items}],
        )


class LoadSkill(AiasysTool):
    """加载指定 Skill 的 SKILL.md 或目录下的其他文件。

    支持读取 builtin（系统内置）和 workspace（工作区自有）两种来源的 Skill。
    同名 Skill 以工作区版本优先。
    """

    name: str = "LoadSkill"
    description: str = """加载指定 Skill 的文件内容。

参数：
- name: Skill 名称（ListSkills 返回的 name 字段）
- file: Skill 目录下的相对文件路径，默认 "SKILL.md"

使用场景：
- 需要某个 Skill 的详细指导时，加载其 SKILL.md
- Skill 指导中提到 references/ 下的文档时，用 file 参数加载
- 想查看 Skill 目录下有哪些脚本可用时

返回内容包括：
- skill_name: Skill 名称
- display_name: 显示名称
- source: builtin 或 workspace
- file: 读取的文件路径
- content: 文件内容
- files: 该 Skill 目录下所有文件列表（方便你发现可用资源）

注意：Skill 中的脚本请通过 Shell 工具执行，不要通过 LoadSkill 执行。
"""
    params: type[BaseModel] = LoadSkillParams

    async def invoke(
        self,
        ctx: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> ToolResult:
        params = LoadSkillParams.model_validate(kwargs)

        from app.skills.manager import get_skill_manager

        if not params.name or not params.name.strip():
            return ToolResult(content="name 参数不能为空", is_error=True)

        workspace = current_workspace.get()
        if not workspace:
            return ToolResult(content="当前上下文未设置工作区", is_error=True)

        workspace_path = Path(workspace)
        mgr = get_skill_manager()
        result = mgr.get_skill_file_content(
            skill_name=params.name.strip(),
            workspace_path=workspace_path,
            relative_path=params.file.strip() if params.file else "SKILL.md",
        )

        if result is None:
            # 尝试按 display_name 匹配（Agent 有时会传 display_name 而不是 name）
            all_skills = mgr.list_all_skills(workspace_path)
            for s in all_skills:
                if s.display_name and s.display_name.strip().lower() == params.name.strip().lower():
                    result = mgr.get_skill_file_content(
                        skill_name=s.name,
                        workspace_path=workspace_path,
                        relative_path=params.file.strip() if params.file else "SKILL.md",
                    )
                    break

        if result is None:
            # 尝试查找相似名称提示
            names = [s.name for s in all_skills]
            hint = f"。可用 Skill: {', '.join(names)}" if names else ""
            return ToolResult(
                content=f"Skill '{params.name}' 不存在或文件无法读取{hint}",
                is_error=True,
            )

        info, content, files = result
        return ToolResult(
            content=content
            or f"已加载 {info.display_name or info.name} 的 {params.file or 'SKILL.md'}",
            artifacts=[
                {
                    "skill_name": info.name,
                    "display_name": info.display_name,
                    "source": info.source,
                    "file": params.file or "SKILL.md",
                    "content": content,
                    "files": files,
                }
            ],
        )


class SearchStoreSkills(AiasysTool):
    """搜索 Skill 仓库中的 Skill（系统内置 + 用户导入）。

    与 ListSkills 不同：ListSkills 列出的是"当前工作区已启用"的 Skill，
    而 SearchStoreSkills 列出的是"Skill 仓库里所有可以启用的" Skill。
    """

    name: str = "SearchStoreSkills"
    description: str = """搜索 Skill 仓库中可启用的 Skill。

参数：
- query: 搜索关键词，匹配 Skill 名称、展示名或描述。为空时返回全部
- source: 按来源过滤，可选 builtin（系统内置）或 store（用户导入）。为空时不过滤

使用场景：
- 工作区缺少某个能力，想查看系统提供了哪些 Skill 时
- 不确定某个 Skill 是否已安装到系统时
- 想浏览所有可用 Skill 时

重要：搜索到需要的 Skill 后，必须调用 `EnableSkill` 将其安装到当前工作区（或全局工作区）。只搜索不安装，Skill 无法在当前工作区使用。

返回格式为 JSON 数组，每个元素包含 name、display_name、description、source。返回的 `name` 字段可直接传给 `EnableSkill(name=...)` 进行安装。
"""
    params: type[BaseModel] = SearchStoreSkillsParams

    async def invoke(
        self,
        ctx: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> ToolResult:
        params = SearchStoreSkillsParams.model_validate(kwargs)

        from app.skills.manager import get_skill_manager

        mgr = get_skill_manager()
        all_skills = mgr.list_store_skills()

        query = params.query.strip().lower() if params.query else ""
        source_filter = params.source.strip().lower() if params.source else ""

        items = []
        for skill in all_skills:
            if source_filter and skill.source.lower() != source_filter:
                continue
            if query:
                haystack = f"{skill.name} {skill.display_name} {skill.description}".lower()
                # 分词匹配：query 中任意一个词/字匹配即可
                # 英文按空格分词；中文按单个字符拆分（因为中文没有空格分隔）
                query_parts = []
                for part in query.split():
                    if len(part) >= 2:
                        # 检测是否包含 CJK 字符（中文/日文/韩文）
                        has_cjk = any("\u4e00" <= ch <= "\u9fff" for ch in part)
                        if has_cjk:
                            # 中文：每个字符作为一个匹配单元
                            query_parts.extend([ch for ch in part if "\u4e00" <= ch <= "\u9fff"])
                        else:
                            query_parts.append(part)
                if query_parts:
                    if not any(part in haystack for part in query_parts):
                        continue
                else:
                    if query not in haystack:
                        continue
            items.append(
                {
                    "name": skill.name,
                    "display_name": skill.display_name,
                    "description": skill.description,
                    "source": skill.source,
                }
            )

        if not items:
            msg = "Skill 仓库中没有匹配的 Skill"
            if query:
                msg += f"（关键词: {params.query}）"
            return ToolResult(content=msg, artifacts=[{"skills": []}])

        # 明确提示 Agent 下一步调用 EnableSkill
        names = [item["name"] for item in items]
        install_hint = ""
        if len(names) == 1:
            install_hint = f"\n\n请立即调用 EnableSkill(name='{names[0]}') 将其安装到当前工作区。"
        else:
            install_hint = f"\n\n请从中选择一个最合适的，立即调用 EnableSkill(name='<skill_name>') 安装到当前工作区。推荐的 Skill 名称: {', '.join(names)}"

        return ToolResult(
            content=f"Skill 仓库中找到 {len(items)} 个 Skill{install_hint}",
            artifacts=[{"skills": items}],
        )


class EnableSkill(AiasysTool):
    """将指定 Skill 从 Skill 仓库启用到当前工作区。

    启用后，该 Skill 即可在当前工作区使用（等同于 ListSkills 可见）。
    """

    name: str = "EnableSkill"
    description: str = """将 Skill 从 Skill 仓库启用到当前工作区或我的默认。

参数：
- name: Skill 名称（SearchStoreSkills 返回的 name 字段）
- scope: 启用范围，workspace（当前工作区，默认）或 global（我的默认）
- force: 是否强制覆盖目标范围中已存在的同名 Skill，默认 false

使用场景：
- Agent 发现工作区缺少某个能力，需要从 Skill 仓库启用时
- 想让某个 Skill 作为我的默认被各工作区继承时，选择 global
- 用户要求启用某个 Skill 时

注意：
- 只能启用 Skill 仓库中已存在的 Skill，不能导入外部 zip
- global 范围表示启用到我的默认，工作区按继承规则获得该 Skill
- 启用后可用 ListSkills 确认
"""
    params: type[BaseModel] = EnableSkillParams

    async def invoke(
        self,
        ctx: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> ToolResult:
        params = EnableSkillParams.model_validate(kwargs)

        from app.skills.manager import get_skill_manager

        if not params.name or not params.name.strip():
            return ToolResult(content="name 参数不能为空", is_error=True)

        workspace = current_workspace.get()
        if not workspace:
            return ToolResult(content="当前上下文未设置工作区", is_error=True)

        workspace_path = Path(workspace)
        mgr = get_skill_manager()
        scope = params.scope.strip().lower() if params.scope else "workspace"

        if scope == "global":
            global_ws = mgr._infer_global_workspace_path(workspace_path)
            if global_ws is None:
                return ToolResult(
                    content="无法推断我的默认配置路径",
                    is_error=True,
                )
            result = mgr.enable_skill_global(
                skill_name=params.name.strip(),
                global_workspace_path=global_ws,
                force=params.force,
            )
        else:
            result = mgr.enable_skill(
                skill_name=params.name.strip(),
                workspace_path=workspace_path,
                force=params.force,
            )

        return ToolResult(
            content=result.message,
            is_error=not result.success,
            artifacts=[
                {
                    "success": result.success,
                    "skill_name": result.skill_name,
                    "scope": scope,
                    "package_path": str(result.package_path) if result.package_path else None,
                }
            ],
        )


class DisableSkill(AiasysTool):
    """从当前工作区禁用指定 Skill。

    禁用后，该 Skill 不再出现在目标范围的 ListSkills 结果中，Skill 仓库中的原始 Skill 不受影响。
    """

    name: str = "DisableSkill"
    description: str = """从当前工作区或我的默认禁用 Skill。

参数：
- name: Skill 名称（ListSkills 返回的 name 字段）
- scope: 禁用范围，workspace（当前工作区，默认）或 global（我的默认）

使用场景：
- 某个 Skill 不再需要，想清理工作区时
- 启用错了 Skill，需要撤销时
- 想让我的默认不再继承某个 Skill 时，选择 global

注意：
- 只影响目标范围，Skill 仓库中的原始 Skill 不会被删除
- 禁用后可用 ListSkills 确认
"""
    params: type[BaseModel] = DisableSkillParams

    async def invoke(
        self,
        ctx: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> ToolResult:
        params = DisableSkillParams.model_validate(kwargs)

        from app.skills.manager import get_skill_manager

        if not params.name or not params.name.strip():
            return ToolResult(content="name 参数不能为空", is_error=True)

        workspace = current_workspace.get()
        if not workspace:
            return ToolResult(content="当前上下文未设置工作区", is_error=True)

        workspace_path = Path(workspace)
        mgr = get_skill_manager()
        scope = params.scope.strip().lower() if params.scope else "workspace"

        if scope == "global":
            global_ws = mgr._infer_global_workspace_path(workspace_path)
            if global_ws is None:
                return ToolResult(
                    content="无法推断我的默认配置路径",
                    is_error=True,
                )
            result = mgr.disable_skill_global(
                skill_name=params.name.strip(),
                global_workspace_path=global_ws,
            )
        else:
            result = mgr.disable_skill(
                skill_name=params.name.strip(),
                workspace_path=workspace_path,
            )

        return ToolResult(
            content=result.message,
            is_error=not result.success,
            artifacts=[
                {
                    "success": result.success,
                    "skill_name": result.skill_name,
                    "scope": scope,
                }
            ],
        )
