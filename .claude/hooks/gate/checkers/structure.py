"""维度② 结构合规 —— STR001–STR006。"""
from __future__ import annotations

import re

from .. import context
from ..context import git_ignored
from ..violation import Severity, Violation

MAX_LINES_WARN = 300
MAX_LINES_BLOCK = 500

# 索引 / 总览文件只放链接，不承载具体条款，豁免 STR003 的正反例要求
INDEX_SUFFIXES = ("-index.md", "-overview.md")

_LINK_RE = re.compile(r"\[[^\]]*\]\(([^)]+)\)")  # 同时覆盖 Markdown 链接和图片语法
_FM_COMMENT_RE = re.compile(r"\s+#.*$")


def _fm_field(fm, key):
    """取 frontmatter 字段的**值**，剥掉 YAML 引号与行尾注释。

    不剥的话 `name: "demo"` 取出的是带引号的 '"demo"'，STR002 会报出
    「name='"demo"' 与目录名 'demo' 不一致，修法：把 name 改为 demo」——
    一条要求把值改成它已经是的样子的、无法满足的指令，足以让自纠正的 agent
    陷入改了又报的死循环。闸门吐垃圾，正是本项目要防的那类事故。
    """
    prefix = key + ":"
    for line in fm.splitlines():
        if not line.startswith(prefix):
            continue
        val = line[len(prefix):].strip()
        quote = val[:1]
        if quote in ('"', "'"):
            end = val.find(quote, 1)
            if end != -1:
                return val[1:end]        # 引号内原样保留，闭合引号之后是注释
        return _FM_COMMENT_RE.sub("", val).strip()   # 无引号：` #` 起为行内注释
    return None


def check(rel, text, root):
    kind = context.classify(rel)
    if kind not in (context.SKILL, context.RULE, context.DOC):
        return []      # 含 docs/superpowers/ 豁免：classify 已判为 IRRELEVANT

    rel_s = str(rel)
    out = []

    if kind == context.SKILL and rel.name == "SKILL.md":
        out.extend(_check_skill_frontmatter(rel, rel_s, text))

    if kind == context.RULE and not rel_s.endswith(INDEX_SUFFIXES):
        # rules 可带 Claude Code 的 `paths:` frontmatter —— 那是元数据，只在正文里找正反例
        body = context.body_without_frontmatter(text)
        if "❌" not in body or "✅" not in body:
            out.append(Violation(
                "STR003", Severity.BLOCK, rel_s, None,
                "规则文件必须同时含 ❌ 反例与 ✅ 正例",
                "为每条规则补一组 ❌ 反例 / ✅ 正例代码块",
            ))

    out.extend(_check_links(rel_s, text, root))
    out.extend(_check_size(rel_s, text))
    return out


def _check_skill_frontmatter(rel, rel_s, text):
    fm = context.frontmatter(text)
    if fm is None:
        return [Violation(
            "STR001", Severity.BLOCK, rel_s, 1,
            "SKILL.md 缺少 YAML frontmatter",
            "在文件开头加：\n---\nname: <目录名>\ndescription: <触发词>\n---",
        )]
    name = _fm_field(fm, "name")
    if name is None or _fm_field(fm, "description") is None:
        return [Violation(
            "STR001", Severity.BLOCK, rel_s, 1,
            "frontmatter 缺少 name 或 description 字段",
            "补齐 name 与 description 两个字段",
        )]
    # Claude Code 只识别 .claude/skills/<name>/SKILL.md。直接放在 .claude/skills/
    # 根下的 SKILL.md 不会被加载 —— 上游那个「路由 skill 放根层」的特例已随原生化
    # 取消，路由现在是普通 skill（ui-automation-harness），同样受目录名约束。
    if str(rel.parent) == context.SKILLS_DIR:
        return [Violation(
            "STR002", Severity.BLOCK, rel_s, 1,
            f"SKILL.md 直接放在 {context.SKILLS_DIR}/ 根下，Claude Code 不会加载",
            f"移到 {context.SKILLS_DIR}/{name}/SKILL.md（目录名 = frontmatter name）",
        )]
    expect = rel.parent.name
    if name != expect:
        return [Violation(
            "STR002", Severity.BLOCK, rel_s, 1,
            f"frontmatter name='{name}' 与目录名 '{expect}' 不一致",
            f"把 name 改为 {expect}（Claude Code 以目录名定位 skill）",
        )]
    return []


def _check_links(rel_s, text, root):
    out = []
    base = (root / rel_s).parent
    root_s = str(root)
    for i, line in enumerate(text.splitlines(), 1):
        for m in _LINK_RE.finditer(line):
            target = m.group(1).split("#")[0].strip()
            if not target or target.startswith(("http://", "https://", "mailto:")):
                continue
            resolved = base / target
            if resolved.exists():
                continue
            if git_ignored(str(resolved), root_s):
                continue
            out.append(Violation(
                "STR004", Severity.BLOCK, rel_s, i,
                f"链接指向不存在的路径：{target}",
                "修正相对路径层级（按本文件所在目录计算，"
                f"{context.SKILLS_DIR}/<name>/ 到仓库根是 ../../../），或补上缺失的目标文件",
            ))
    return out


def _check_size(rel_s, text):
    n = len(text.splitlines())
    if n > MAX_LINES_BLOCK:
        return [Violation(
            "STR006", Severity.BLOCK, rel_s, None,
            f"文件 {n} 行，超过上限 {MAX_LINES_BLOCK}",
            "拆分为多个按主题聚焦的文件，并在索引文件中互相引用",
        )]
    if n > MAX_LINES_WARN:
        return [Violation(
            "STR005", Severity.WARN, rel_s, None,
            f"文件 {n} 行，超过建议值 {MAX_LINES_WARN}",
            "考虑拆分；单文件过长会挤占 agent 上下文",
        )]
    return []
