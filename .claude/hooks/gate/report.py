"""只读报告与基线冻结 —— 不参与任何拦截决策。

两件事：
  · render()          给人看的现状：证据覆盖率、上下文占用、待复核项
  · freeze_baseline() 把当前存量条款冻结为豁免快照

上下文占用**只统计不设上限**：harness 的体量该由人按需要权衡，闸门给数据、不替人
做决定。真正要守住的是每条规则的证据成色 —— 规则确实有效时，多一条是净收益；
规则是推测时，一条都嫌多。
"""
from __future__ import annotations

import json
import pathlib
import re

from . import context, runner
from .checkers import provenance
from .violation import Severity

_FM_PATHS_RE = re.compile(r'^\s*-\s*"?([^"\n]+?)"?\s*$', re.M)


def _rule_files(root):
    for p in sorted(root.glob(context.RULES_GLOB)):
        rel = p.relative_to(root).as_posix()
        if rel.endswith(("-index.md", "-overview.md")):
            continue
        try:
            yield rel, p, p.read_text(encoding="utf-8")
        except Exception:
            continue


def _clauses_of(text):
    return provenance._clauses(context.body_without_frontmatter(text).splitlines())


def freeze_baseline(root):
    """把当前所有条款的指纹写入 baseline.json，使其免除证据门槛。

    只记指纹不记内容：条款标题一旦被改写，指纹随之改变，该条款重新受门槛约束 ——
    存量因此会随日常维护自然收敛，而不是永久豁免。
    """
    fps, total = {}, 0
    for rel, _p, text in _rule_files(root):
        for title, _ln, _body in _clauses_of(text):
            fps[provenance.clause_fingerprint(rel, title)] = f"{rel} · {title}"
            total += 1
    path = pathlib.Path(provenance._BASELINE)
    path.write_text(json.dumps({
        "_说明": "存量条款豁免快照。指纹 = 文件路径 + 归一化标题；改写标题即视为新条款，"
                 "须按 PRV001–PRV004 补齐可核验证据。重新生成需 gate_cli.py --mode baseline --yes。",
        "clauses": sorted(fps),
        "_条款一览": [fps[k] for k in sorted(fps)],
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return total, path.relative_to(root) if path.is_relative_to(root) else path


def _fmt_kb(n):
    return f"{n/1024:.1f}KB"


def render(root):
    if root is None:
        return "不在 git 仓库里，无法生成报告。"
    baseline = provenance._load_baseline()

    total = with_symptom = with_verify = grandfathered = 0
    resident, groups = [], {}

    for rel, p, text in _rule_files(root):
        size = len(text.encode("utf-8"))
        fm = context.frontmatter(text) or ""
        if "paths:" in fm:
            for g in _FM_PATHS_RE.findall(fm.split("paths:", 1)[1]):
                groups.setdefault(g.strip(), []).append((rel, size))
        else:
            resident.append((rel, size))

        for title, _ln, body in _clauses_of(text):
            total += 1
            if provenance.clause_fingerprint(rel, title) in baseline:
                grandfathered += 1
            if provenance._field_value(body, provenance._SYMPTOM):
                with_symptom += 1
            if provenance._field_value(body, provenance._VERIFY):
                with_verify += 1

    entry = (root / context.ENTRY_FILE)
    entry_size = entry.stat().st_size if entry.exists() else 0
    resident_total = entry_size + sum(s for _, s in resident)

    L = ["═══ 落库现状报告 ═══", "", "【证据成色】"]
    new_total = total - grandfathered
    L.append(f"  规则条款 {total} 个，其中 {grandfathered} 个受存量基线豁免、"
             f"{new_total} 个受证据门槛约束")
    L.append(f"  写了失败现象：{with_symptom}/{total}    给出可核验验证：{with_verify}/{total}")
    if grandfathered:
        L.append(f"  存量豁免会随维护自然收敛 —— 改写任一条款标题，该条款即重新受约束")

    L += ["", "【上下文占用】只统计，不设上限"]
    L.append(f"  常驻（每个会话都加载）：{context.ENTRY_FILE} {_fmt_kb(entry_size)}"
             + "".join(f" + {pathlib.Path(r).name} {_fmt_kb(s)}" for r, s in resident)
             + f" = {_fmt_kb(resident_total)}")
    if groups:
        L.append("  按需加载（命中 paths 时才进上下文，取前 5 大分组）：")
        for g, items in sorted(groups.items(), key=lambda kv: -sum(s for _, s in kv[1]))[:5]:
            tot = sum(s for _, s in items)
            L.append(f"    {g:<26} {len(items)} 个规则 {_fmt_kb(tot)}")
    skills = list(root.glob(context.SKILL_ENTRY_GLOB))
    if skills:
        sk = sum(p.stat().st_size for p in skills)
        L.append(f"  skills：{len(skills)} 个 SKILL.md 合计 {_fmt_kb(sk)}"
                 "（frontmatter 常驻，正文命中才加载）")

    vs = runner.run_audit(root)
    blocks = [v for v in vs if v.severity == Severity.BLOCK]
    stale = [v for v in vs if v.code == "PRV005"]
    orphan = [v for v in vs if v.code == "PRV006"]
    dup = [v for v in vs if v.code == "EVI004"]

    L += ["", "【待复核】"]
    L.append(f"  证据链已断（引用的用例/代码/commit 不存在了）：{len(stale)}")
    L.append(f"  孤儿规则（无 paths 也无人链接，读不到）：{len(orphan)}")
    L.append(f"  标题疑似重复：{len(dup)}")
    L.append(f"  BLOCK 级违规：{len(blocks)}")
    for v in stale + orphan + blocks:
        L.append(f"    [{v.code}] {v.path}" + (f":{v.line}" if v.line else "") + f" — {v.message}")
    return "\n".join(L)
