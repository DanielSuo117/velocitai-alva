"""路径归类、仓库根定位、gitignore 查询、frontmatter 剥离。

harness 布局是 Claude Code 原生格式：skill 在 .claude/skills/<name>/SKILL.md，
rule 在 .claude/rules/<domain>/<file>.md，项目事实在 docs/，唯一入口是根目录
CLAUDE.md。下面这组前缀常量是全包**唯一**的路径真相来源 —— checkers 与 runner
一律通过 classify() 或这些常量判断归属，不得各自硬编码 parts[0]=="skills"。
布局再迁一次时只改这里；散落各处的硬编码正是上一次迁移后闸门整体静默失效的原因。
"""
from __future__ import annotations

import functools
import pathlib
import re
import subprocess

SKILL = "skill"
RULE = "rule"
DOC = "doc"
ENTRY = "entry"
IRRELEVANT = "irrelevant"

# —— 布局前缀（相对仓库根、POSIX 风格、无尾斜杠）——
SKILLS_DIR = ".claude/skills"
RULES_DIR = ".claude/rules"
DOCS_DIR = "docs"
ENTRY_FILE = "CLAUDE.md"

# 全量扫描（audit）用的 glob。docs 故意非递归：docs/ 下的子目录是 spec/plan 这类
# 长篇流程文档（见 EXEMPT_PREFIXES），不属于 harness 知识。
SKILLS_GLOB = f"{SKILLS_DIR}/**/*.md"
RULES_GLOB = f"{RULES_DIR}/**/*.md"
DOCS_GLOB = f"{DOCS_DIR}/*.md"
# REG001 只看 skill 本体：.claude/skills/<name>/SKILL.md，不看 references/ 支撑文件
SKILL_ENTRY_GLOB = f"{SKILLS_DIR}/*/SKILL.md"

# spec §6.1 豁免：spec / plan 是长篇流程文档，不是 harness 知识
EXEMPT_PREFIXES = (f"{DOCS_DIR}/superpowers/",)

_SKILLS_PARTS = pathlib.PurePosixPath(SKILLS_DIR).parts
_RULES_PARTS = pathlib.PurePosixPath(RULES_DIR).parts
_DOCS_PARTS = pathlib.PurePosixPath(DOCS_DIR).parts


def _under(parts, prefix_parts) -> bool:
    """按路径段而非字符串前缀比较 —— 避免 .claude/skills-old/ 被当成 .claude/skills/。"""
    n = len(prefix_parts)
    return len(parts) > n and tuple(parts[:n]) == prefix_parts


def skill_name_from_link(target: str):
    """链接目标若指向 .claude/skills/<name>[/...]，返回 <name>，否则 None。

    PurePosixPath 会吃掉开头的 ./ 与末尾的 /，因此 ./.claude/skills/foo、
    ./.claude/skills/foo/、.claude/skills/foo/SKILL.md 三种写法都能认出 foo。
    """
    parts = pathlib.PurePosixPath(target).parts
    if _under(parts, _SKILLS_PARTS):
        return parts[len(_SKILLS_PARTS)]
    return None


def find_repo_root(start: pathlib.Path):
    start = pathlib.Path(start).resolve()
    for d in [start, *start.parents]:
        if (d / ".git").exists():
            return d
    return None


def relative_to_root(path, root):
    try:
        rel = pathlib.Path(path).resolve().relative_to(pathlib.Path(root).resolve())
    except (ValueError, OSError):
        return None
    return pathlib.PurePosixPath(rel.as_posix())


def classify(rel) -> str:
    if rel is None:
        return IRRELEVANT
    rel_s = str(rel)
    parts = rel.parts
    if not parts:
        return IRRELEVANT
    if any(rel_s.startswith(p) for p in EXEMPT_PREFIXES):
        return IRRELEVANT
    if rel_s == ENTRY_FILE:
        return ENTRY
    if rel.suffix != ".md":
        return IRRELEVANT
    if _under(parts, _SKILLS_PARTS):
        return SKILL
    if _under(parts, _RULES_PARTS):
        return RULE
    if _under(parts, _DOCS_PARTS):
        return DOC
    return IRRELEVANT


# 容忍开头的 UTF-8 BOM 与空行：编辑器很容易留下这两者，而它们不影响 YAML
# frontmatter 的语义。之前严格从第 0 个字符起匹配 ---，一个 BOM 就会让文件被判
# 成「缺 frontmatter」（STR001），修法提示还让人再加一遍本来就有的 frontmatter。
FRONTMATTER_RE = re.compile(r"\A﻿?(?:[ \t]*\r?\n)*---[ \t]*\r?\n(.*?)\r?\n---[ \t]*(?=\r?\n|\Z)", re.S)


def frontmatter(text):
    m = FRONTMATTER_RE.match(text)
    return m.group(1) if m else None


def body_without_frontmatter(text: str) -> str:
    """把开头的 YAML frontmatter 换成等量空行，返回正文。

    rules 现在可以带 Claude Code 的 `paths:` frontmatter。它是元数据不是正文：
    ❌/✅ 若只出现在 frontmatter 里不算有正反例（STR003），frontmatter 里的注释行
    也不能被当成 `## P0` 条款（EVI002/003/004）。换成**空行**而不是直接删掉，
    是为了让后续报出的行号仍对应原文件。
    """
    m = FRONTMATTER_RE.match(text)
    if not m:
        return text
    head = m.group(0)
    return "\n" * head.count("\n") + text[m.end():]


@functools.lru_cache(maxsize=None)
def git_ignored(path_str: str, root_str: str) -> bool:
    """目标路径是否被 .gitignore 忽略。「查不出来」一律返回 True（fail-open）。

    两处调用方（structure 的 STR004、registry 的 REG002）都把 False 读成「没被
    忽略 → 这是死链 → BLOCK」。所以本函数的 fail-open 方向是 **True** 而非
    False：git 超时、index.lock 残留、退出码 128 这类「问不出答案」的情形若返回
    False，闸门就会凭空造出一条 BLOCK 去 deny `git commit` —— 违背 §3 / §9.4
    「宁可漏判也绝不阻塞」的铁律。

    退出码语义（git check-ignore）：
      0  → 确实被忽略        → True
      1  → 确实未被忽略      → False（唯一返回 False 的分支）
      ≥2 → git 自身出错      → 未知 → True
    """
    try:
        r = subprocess.run(
            ["git", "-C", root_str, "check-ignore", "-q", path_str],
            capture_output=True, timeout=5,
        )
    except Exception:
        return True
    return r.returncode != 1
