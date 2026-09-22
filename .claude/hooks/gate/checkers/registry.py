"""维度④ 注册闭环 —— REG001–REG002。

上游的 REG003（zh/ en/ 镜像弃用守卫）已随镜像目录一起删除：本项目只保留
Claude Code 一套 harness，不存在需要守卫的历史副本。
"""
from __future__ import annotations

import re

from .. import context
from ..context import git_ignored
from ..violation import Severity, Violation

_LINK_RE = re.compile(r"\[[^\]]*\]\(([^)]+)\)")


def _registered_skills(text):
    """从 CLAUDE.md 的真实 Markdown 链接目标中提取已注册的 skill 名。

    不做全文子串匹配 —— 正文里顺带提到 ./.claude/skills/foo/ 不构成注册（否则
    REG001 会被一句无关说明满足而失效）；同时容忍 ./.claude/skills/foo 与
    ./.claude/skills/foo/ 两种等价写法（否则合法的无尾斜杠写法会被误判为未注册）。
    """
    names = set()
    for m in _LINK_RE.finditer(text):
        target = m.group(1).split("#")[0].strip()
        name = context.skill_name_from_link(target)
        if name:
            names.add(name)
    return names


def check_repo(root):
    """commit / audit 时机：全局注册闭环。"""
    claude_md = root / context.ENTRY_FILE
    if not claude_md.exists():
        return []
    try:
        text = claude_md.read_text(encoding="utf-8")
    except Exception:
        return []

    registered = _registered_skills(text)
    out = []
    for skill_md in sorted(root.glob(context.SKILL_ENTRY_GLOB)):
        name = skill_md.parent.name
        if name not in registered:
            out.append(Violation(
                "REG001", Severity.BLOCK, f"{context.SKILLS_DIR}/{name}/SKILL.md", None,
                f"skill '{name}' 未在 {context.ENTRY_FILE} 路由表注册",
                f"在 {context.ENTRY_FILE} 路由表新增一行，链接指向 ./{context.SKILLS_DIR}/{name}/",
            ))

    root_s = str(root)
    for i, line in enumerate(text.splitlines(), 1):
        for m in _LINK_RE.finditer(line):
            target = m.group(1).split("#")[0].strip()
            if not target or target.startswith(("http://", "https://", "mailto:")):
                continue
            resolved = root / target
            if resolved.exists() or git_ignored(str(resolved), root_s):
                continue
            out.append(Violation(
                "REG002", Severity.BLOCK, context.ENTRY_FILE, i,
                f"路由表链接指向不存在的路径：{target}",
                f"修正链接（skill 写 ./{context.SKILLS_DIR}/<name>/，"
                f"rule 写 ./{context.RULES_DIR}/<domain>/<file>.md），或补上缺失的目标文件",
            ))
    return out
