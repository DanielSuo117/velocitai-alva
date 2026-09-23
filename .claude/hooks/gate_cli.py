#!/usr/bin/env python3
"""VelocitAI 落库校验闸门 —— 唯一入口。

用法：
    gate_cli.py --mode write     # PreToolUse(Write|Edit)，从 stdin 读 hook JSON
    gate_cli.py --mode commit    # PreToolUse(Bash git commit)，校验暂存区
    gate_cli.py --mode audit     # 全仓库扫描，供测试与 stop 模式复用（commit 模式不调用它）
    gate_cli.py --mode stop      # Stop hook：全仓兜底扫描，只提示、永不阻塞
    gate_cli.py --mode report    # 只读报告：证据覆盖率 + 上下文占用，永不拦截
    gate_cli.py --mode baseline  # 重新冻结存量条款快照（会放宽约束，需显式确认）

退出码：0 = 放行（可能带 ask 决策）；2 = 拦截。
任何异常一律 fail-open 返回 0。

接线：.claude/settings.json 的 hooks 段（Claude Code 原生格式），命令形如
    G="$CLAUDE_PROJECT_DIR/.claude/hooks/gate_cli.py"; [ -f "$G" ] || exit 0; python3 "$G" --mode write
[ -f ] 兜底是为了脚本被删/改名时 hook 直接放行，而不是让 python 报错退出码 2 误拦。
作用范围：.claude/skills/**、.claude/rules/**、docs/*.md 与根目录 CLAUDE.md（见 gate/context.py）。

自测（项目根执行；-t 指到 .claude/hooks，让 gate.tests 作为 gate 的子包被导入）：
    python3 -m unittest discover -s .claude/hooks/gate/tests -t .claude/hooks
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from gate import context, report, runner    # noqa: E402
from gate.violation import Severity         # noqa: E402


def _root():
    return context.find_repo_root(pathlib.Path(os.getcwd()))


def _emit(violations) -> int:
    if not violations:
        return 0

    out = {}

    # WARN 必须始终能被看到：无论最高档位是什么，只要出现过 WARN 就单独渲染一份
    # —— 否则一旦同批里混进 ASK/BLOCK，WARN 就会被下面按最高档位过滤的 JSON
    # 悄悄吞掉。
    #   · stderr 一份：退出码 2（BLOCK）时宿主把 stderr 回传给 agent。
    #   · stdout 的 systemMessage 一份：退出码 0 时宿主只从 **stdout** 组装要展示
    #     的 hook 消息，只写 stderr 等于没写。STR005/GEN004/EVI003/EVI004/PRV005/PRV006 这六个
    #     纯 WARN 码全部走退出码 0，不补这一份就是完全不可见（spec §13 遗留问题）。
    #     systemMessage 是宿主文档中「对所有 hook 展示给用户」的通用字段。
    warns = [v for v in violations if v.severity == Severity.WARN]
    if warns:
        text = "落库校验提示：\n" + "\n".join(v.render() for v in warns)
        print(text, file=sys.stderr)
        out["systemMessage"] = text

    top = max(v.severity for v in violations)
    rc = 0

    if top == Severity.BLOCK:
        body = "\n".join(v.render() for v in violations if v.severity == Severity.BLOCK)
        out["hookSpecificOutput"] = {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": "落库校验闸门拦截：\n" + body,
        }
        rc = 2
    elif top == Severity.ASK:
        body = "\n".join(v.render() for v in violations if v.severity == Severity.ASK)
        out["hookSpecificOutput"] = {
            "hookEventName": "PreToolUse",
            "permissionDecision": "ask",
            "permissionDecisionReason": body,
        }

    if out:
        print(json.dumps(out, ensure_ascii=False))
    return rc


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode",
                    choices=("write", "commit", "audit", "stop", "report", "baseline"),
                    required=True)
    ap.add_argument("--yes", action="store_true",
                    help="--mode baseline 专用：确认要把当前存量条款冻结为豁免快照")
    try:
        args = ap.parse_args()
    except SystemExit as exc:
        # argparse 用法错误抛的是 SystemExit(2)，而 PreToolUse 里的 2 意思是 deny。
        # 不接住的话，一个写错的 --mode 会拿 argparse 的 usage 文本当理由拒掉这次
        # 工具调用 —— fail-open 之外最后一处 fail-closed 缺口。
        if exc.code:
            print("[gate] 参数解析失败，已放行", file=sys.stderr)
        return 0

    if args.mode == "write":
        payload = json.load(sys.stdin)
        return _emit(runner.run_write(payload))

    if args.mode == "commit":
        return _emit(runner.run_commit(_root()))

    if args.mode == "stop":
        # Stop hook 的退出码 2 意思是「阻止本轮停止」，与 PreToolUse 的 deny 完全不同：
        # 直接复用 audit 的退出码会让一条 BLOCK 把 agent 卡在停不下来的循环里。
        # 这里只把结果渲染成提示，**无论如何都返回 0**。
        vs = runner.run_audit(_root())
        if vs:
            worst = max(v.severity for v in vs)
            head = ("落库兜底扫描发现问题（含绕过 Write/Edit 直接写入的改动）："
                    if worst == Severity.BLOCK else "落库兜底扫描提示：")
            print(json.dumps({
                "systemMessage": head + "\n" + "\n".join(v.render() for v in vs)
            }, ensure_ascii=False))
        return 0

    if args.mode == "report":
        # 只读：给人看的统计，不参与任何拦截决策
        print(report.render(_root()))
        return 0

    if args.mode == "baseline":
        # 冻结存量 = 批量豁免证据门槛，必须显式确认，避免「被闸门拦了就重跑一次
        # baseline」变成绕过手段
        if not args.yes:
            print("重新冻结基线会让当前所有条款免除证据门槛（PRV001–PRV004）。\n"
                  "确认要这么做请加 --yes。", file=sys.stderr)
            return 0
        n, path = report.freeze_baseline(_root())
        print(f"已冻结 {n} 个存量条款到 {path}")
        return 0

    return _emit(runner.run_audit(_root()))


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception as exc:  # fail-open：宁可漏判，绝不阻塞
        print(f"[gate] 校验器异常，已放行：{exc}", file=sys.stderr)
        sys.exit(0)
