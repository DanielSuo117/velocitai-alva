"""维度③ 通用化检测 —— GEN001–GEN004，作用于 .claude/skills/** 与 .claude/rules/**。

skills 与 rules 都只写项目无关的方法论（CLAUDE.md 约定）；站点 URL、界面文案、类名等
项目事实一律放 docs/，docs 不在此检查。rules 曾不在范围内，一次把真实站点 URL 和业务
类名写进已有规则的 Edit 因此被静默放行。两类文件用同一套判据与反例豁免。
GEN004 的黑名单在 ../wordlist.txt，匹配语义见 _term_pattern。
"""
from __future__ import annotations

import functools
import pathlib
import re

from .. import context
from ..violation import Severity, Violation

# 全角标点需排除，否则中文正文里的 URL 会一路吞到句末
_URL_RE = re.compile(r"https?://[^\s)\]\"'`，。）、；：]+")
# 前缀表严格对齐 spec §6.2：/Users/ 、/Applications/ 、C:\ 。不含 /home/ ——
# 正则不锚定行首，加上它会把 page.goto("/home/dashboard")、
# https://example.com/home/list 这类普通 URL 路径段判成本地绝对路径。
# 尾部用 + 而非 *：裸前缀「/Users/ 开头的绝对路径」这类描述性提及不是路径本身，
# 判成违规属误报；真实路径必然还有至少一段。
_ABS_PATH_RE = re.compile(r"(?:/Users/|/Applications/|[A-Za-z]:\\)[^\s)\]\"'`，。）]+")
# 判别依据：构建工具的哈希段必然含数字（abc123 / 1x2y3 / 1a2b3c），
# 而 Python 方法名每一段都是纯字母（is_page_loaded / set_default_timeout）。
# 不要求数字就会把整个 Playwright 项目的方法名全判成哈希类名。
_HASH_CLASS_RE = re.compile(
    r"\."
    r"(?:"
    r"sc-[A-Za-z]{4,}"                                       # styled-components: .sc-bdVaJa
    r"|css-(?=[0-9a-z]*[0-9])[0-9a-z]{5,}"                   # Emotion: .css-1a2b3c
    r"|[A-Za-z_]*_(?=[0-9a-z]*[0-9])[0-9a-z]{3,}"            # CSS Modules: ._component_1x2y3 / .header_abc123
    r")"
)

_URL_WHITELIST = (
    "example.com", "example.org", "example.net",
    "github.com/DanielSuo117/velocitai",
    "docs.claude.com", "code.claude.com",
    "playwright.dev", "docs.pytest.org",
)
_URL_PLACEHOLDER_PREFIXES = ("https://...", "http://...")

_EXEMPT_MARKERS = ("BAD", "❌", "禁止")
_WORDLIST = pathlib.Path(__file__).resolve().parent.parent / "wordlist.txt"


def _is_teaching_line(line: str) -> bool:
    """宽豁免 —— 注释 / 表格 / 清单 / 显式反例标记。供 GEN003 / GEN004 使用。

    这两条检查的目标（哈希类名、业务术语）在表格与标题里天然大量出现于
    对照说明中，沿用宽判据是已验证过的零误报行为。
    """
    s = line.lstrip()
    if s.startswith(("#", "|", "- [ ]", "- [x]")):
        return True
    return any(mark in line for mark in _EXEMPT_MARKERS)


def _is_counterexample_line(line: str) -> bool:
    """窄豁免 —— 仅显式反例标记。供 GEN001 / GEN002 使用。

    结构前缀（# 标题、| 表格行）不算教学语境。skills 正文里表格极其常见，
    把它们整体豁免等于让这两条检查对表格内的硬编码 URL 与绝对路径彻底失明，
    而堵住这类标识符正是它们存在的唯一理由。
    真正需要豁免的是「❌ 反例：...」这类显式对照，显式标记已足够覆盖。
    """
    return any(mark in line for mark in _EXEMPT_MARKERS)


def _term_pattern(word: str):
    """业务术语的匹配规则：不区分大小写；词首前一个字符不能是英文字母，词尾不限。

    不区分大小写，一个 acme 就能覆盖 Acme / ACME_TOKEN / acme.io；词尾放开，
    AcmeBaseTest、test_acme_xxx 照样命中；词首卡住英文字母，是为了不在普通单词
    内部命中（黑名单写 alva 时不误中 salvage）。中文、下划线、标点都算边界。
    """
    return re.compile(r"(?<![A-Za-z])" + re.escape(word), re.IGNORECASE)


@functools.lru_cache(maxsize=1)
def _wordlist():
    try:
        lines = _WORDLIST.read_text(encoding="utf-8").splitlines()
    except Exception:
        return ()
    words = (w for w in (l.strip() for l in lines) if w and not w.startswith("#"))
    return tuple((w, _term_pattern(w)) for w in words)


def check(rel, text, root=None):
    kind = context.classify(rel)
    if kind not in (context.SKILL, context.RULE):
        return []
    rel_s = str(rel)
    label = "skill" if kind == context.SKILL else "rule"
    out = []
    words = _wordlist()

    for i, line in enumerate(text.splitlines(), 1):
        # 反例教学豁免作用于 GEN001–GEN004，不只 GEN003：本项目规范要求每条规则
        # 配 ❌ 反例（rules 文件由 STR003 强制；含 P0.5「skill 正文不得写入项目专有标识」这一条本身），
        # 若只豁免 GEN003，闸门就会拦下它自己要求人写的那些反例。
        # 但两组用的判据宽窄不同 —— 见 _is_counterexample_line 的说明。
        if not _is_counterexample_line(line):
            for m in _URL_RE.finditer(line):
                url = m.group(0)
                if url.startswith(_URL_PLACEHOLDER_PREFIXES):
                    continue
                if any(w in url for w in _URL_WHITELIST):
                    continue
                out.append(Violation(
                    "GEN001", Severity.BLOCK, rel_s, i,
                    f"{label} 正文出现具体 URL：{url}",
                    f"抽象为占位符（如 <目标页面URL>）；项目级 URL 放 {context.DOCS_DIR}/ 或 framework/config/",
                ))

            for m in _ABS_PATH_RE.finditer(line):
                out.append(Violation(
                    "GEN002", Severity.BLOCK, rel_s, i,
                    f"{label} 正文出现本地绝对路径：{m.group(0)}",
                    "改为相对仓库根的路径，或抽象为占位符",
                ))

        if _is_teaching_line(line):
            continue

        m = _HASH_CLASS_RE.search(line)
        if m:
            out.append(Violation(
                "GEN003", Severity.BLOCK, rel_s, i,
                f"{label} 正文出现哈希类名：{m.group(0)}",
                "哈希类名每次构建都会变；升级到 P0 role 或 P1 text 定位",
            ))

        for w, pat in words:
            if pat.search(line):
                out.append(Violation(
                    "GEN004", Severity.WARN, rel_s, i,
                    f"{label} 正文出现业务术语「{w}」",
                    f"skills / rules 须保持项目无关；业务术语抽象为占位符，事实移入 {context.DOCS_DIR}/",
                ))
    return out
