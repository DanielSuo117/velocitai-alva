"""维度⑤ 证据溯源 —— PRV001–PRV006。

落库的规则必须是「实践中真踩过、且验证过修法有效」的，而不是推测或通用常识。
EVI002/EVI003 只检查 `**触发**` 这几个字是否出现，`**触发**：无` 照样放行 ——
形状合规不等于证据成立。本维度把证据要求变成**可机器核对**的约束：

  · 条款必须写明失败现象（PRV001），不能是「无 / 待补 / 视情况」这类空话（PRV003）
  · 条款必须给出验证引用（PRV002），且引用的对象必须真实存在（PRV004）——
    引用一个不存在的用例名或编造的 commit 会被当场拆穿，这是「自觉填写」与
    「可核验证据」的分界线
  · 已落库条款的引用后来失效了（用例被删 / 改名、commit 不在历史里），说明证据链
    断了、规则可能已过期（PRV005，仅提示）
  · 没有任何地方引用的规则文件是孤儿，从未被实际使用（PRV006，仅提示）

存量条款由 baseline.json 冻结豁免：设计本维度时仓库里绝大多数条款都没写失败
现象，强行回填只会逼人凭条款反推、编造出一份「看起来合规」的假证据 —— 与本维度的
目的正好相反。改动旧条款的标题即视为新条款，须补齐证据，存量因此会随维护自然收敛。
"""
from __future__ import annotations

import ast
import functools
import hashlib
import json
import pathlib
import re
import subprocess

from .. import context
from ..violation import Severity, Violation

# —— 条款识别 ——
# 带 P 级编号的一定是条款；此外「含 ❌ 或 ✅ 正反例」的小节也是条款 —— rules 文件
# 由 STR003 强制正反例，所以有正反例就是在讲一条规则。纯表格 / 说明小节
# （如「违规码速查」「边界速查表」）两者都不满足，不纳入，避免误报。
_H2_RE = re.compile(r"^##\s+(.*)$")
_FENCE_RE = re.compile(r"^\s*(```|~~~)")
_PLEVEL_RE = re.compile(r"\bP\d+(?:\.\d+)*")

_SYMPTOM = "**失败现象**"
_VERIFY = "**验证**"
_TRIGGER = "**触发**"

# 证据字段的最短有效长度（去掉标点与空白后的字符数）
MIN_SYMPTOM_LEN = 20
MIN_TRIGGER_LEN = 6

# 空话黑名单：命中即视为没写。全角半角、大小写在比对前已归一。
_FILLER = (
    "无", "暂无", "待补", "待定", "待填", "略", "同上", "见上", "参见上文",
    "tbd", "todo", "n/a", "na", "none", "视情况", "视情况而定", "适当", "酌情",
    "随便", "不确定", "未知", "后续补充", "有待验证", "待验证",
)
_NOISE_RE = re.compile(r"[·:：、，。；！？()（）\[\]`*#\-—\s]")

# —— 三种可核验引用 ——
# 顺序敏感：nodeid 与 file:line 都以路径开头，必须先试更长的 nodeid。
_NODEID_RE = re.compile(r"([\w./-]+\.py)::([A-Za-z_]\w*)(?:::([A-Za-z_]\w*))?")
_FILELINE_RE = re.compile(r"([\w./-]+\.(?:py|ini|md|json|txt|yml|yaml)):(\d+)\b")
# 纯 10 进制数字不算 commit（会把版本号、日期吃进来），至少含一个 a-f 字母
_COMMIT_RE = re.compile(r"(?<![\w/])(?=[0-9a-f]*[a-f])([0-9a-f]{7,40})(?![\w/])")

_BASELINE = pathlib.Path(__file__).resolve().parent.parent / "baseline.json"


# ————————————————————————— 基线 —————————————————————————

def clause_fingerprint(rel_s: str, title: str) -> str:
    """条款指纹 = 文件路径 + 归一化标题。

    标题里的 emoji、P 级编号、标点都剔除：给条款加个 🔴 或调整编号不该让它变成
    「新条款」而被要求补证据；改写标题文字则确实是在改规则本身，应当重新给证据。
    """
    norm = _NOISE_RE.sub("", _PLEVEL_RE.sub("", title))
    norm = re.sub(r"[\U0001F300-\U0001FAFF☀-➿️]", "", norm)
    return hashlib.sha1(f"{rel_s}\n{norm}".encode("utf-8")).hexdigest()[:16]


def _load_baseline() -> set:
    """读存量豁免快照。读不到一律返回空集 —— 宁可多提示，不可凭空放行。"""
    try:
        data = json.loads(_BASELINE.read_text(encoding="utf-8"))
    except Exception:
        return set()
    return set(data.get("clauses", ()))


# ————————————————————————— 条款切分 —————————————————————————

def _mask_fenced(lines):
    """把代码围栏内的行换成空行，保住行号。

    Markdown 正文与「正文里演示 Markdown」长得一模一样，不区分两者会两头出错：
      · 演示用的 `## 标题` 被切成幽灵条款，凭空要求它补证据（误拦）
      · ✅ 示例块里的 `**失败现象**：…` 被当成本条款的真证据（漏判 —— 正是本维度
        存在的理由被架空）
    掩码而不是删除，是为了让报出的行号仍对应原文件。
    """
    out, fence = [], None
    for line in lines:
        if fence is None:
            m = _FENCE_RE.match(line)
            if m:
                fence, _ = m.group(1), out.append("")
                continue
            out.append(line)
        else:
            out.append("")
            if line.strip().startswith(fence):
                fence = None
    return out


def _clauses(lines):
    """切出 (标题, 起始行号 1-based, 正文行列表)，只保留规则条款。"""
    masked = _mask_fenced(lines)
    # 标题只在围栏外认；正反例判据仍看原文（写在围栏里的 ❌/✅ 同样是正反例）
    heads = [(i, m.group(1).strip()) for i, l in enumerate(masked) if (m := _H2_RE.match(l))]
    out = []
    for pos, (i, title) in enumerate(heads):
        end = heads[pos + 1][0] if pos + 1 < len(heads) else len(lines)
        raw_body = lines[i:end]
        body = masked[i:end]        # 字段提取一律用掩码版，杜绝从示例块里偷证据
        # 表格行里的 ❌ / ✅ 不算正反例：「违规码速查」这类表格的单元格里天然出现
        # 这两个符号（在描述别的检查项），据此把说明表判成规则条款是误报。
        is_clause = bool(_PLEVEL_RE.search(title)) or any(
            ("❌" in l or "✅" in l) and not l.lstrip().startswith("|") for l in raw_body
        )
        if is_clause:
            out.append((title, i + 1, body))
    return out


def _field_value(body, field):
    """取 `**字段**：值` 的值，允许值跨到下一行（现有规则大量这样写）。"""
    for idx, line in enumerate(body):
        if not line.startswith(field):
            continue
        rest = line[len(field):].lstrip("：: ").strip()
        # 续行：直到空行或下一个 ** 字段 / 代码块
        for nxt in body[idx + 1:]:
            s = nxt.strip()
            if not s or s.startswith(("**", "```", "❌", "✅", "#", "|", "-")):
                break
            rest += s
        return rest
    return None


def _is_filler(value: str, min_len: int) -> bool:
    core = _NOISE_RE.sub("", (value or "")).lower()
    if len(core) < min_len:
        return True
    return core in _FILLER


# ————————————————————————— 引用核验 —————————————————————————

def _iter_refs(text: str):
    """从验证字段里解析出所有可核验引用，返回 (类型, 原文, 参数...) 列表。"""
    refs, spans = [], []

    def overlaps(m):
        return any(not (m.end() <= s or m.start() >= e) for s, e in spans)

    for m in _NODEID_RE.finditer(text):
        spans.append(m.span())
        refs.append(("nodeid", m.group(0), m.group(1), m.group(2), m.group(3)))
    for m in _FILELINE_RE.finditer(text):
        if overlaps(m):
            continue
        spans.append(m.span())
        refs.append(("fileline", m.group(0), m.group(1), int(m.group(2))))
    for m in _COMMIT_RE.finditer(text):
        if overlaps(m):
            continue
        spans.append(m.span())
        refs.append(("commit", m.group(0), m.group(1)))
    return refs


@functools.lru_cache(maxsize=256)
def _symbol_table(path_str):
    """(模块级名字, {类名: (自身方法集, 基类名列表)})。解析不了返回 None（不猜）。

    扁平地收集全文件的名字是不够的：那样 `x.py::TestB::test_a` 在 test_a 其实属于
    TestAlpha 时照样通过 —— 引用「看起来对得上」却指不到真东西，与可核验证据的
    初衷相悖。这里按类记录归属，核验时才能判出张冠李戴。
    """
    try:
        tree = ast.parse(pathlib.Path(path_str).read_text(encoding="utf-8"))
    except Exception:
        return None

    def own_methods(node):
        names = set()
        for child in node.body:
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                names.add(child.name)
            elif isinstance(child, ast.ClassDef):
                names |= own_methods(child)      # 嵌套类里的方法也算这个类的
        return names

    toplevel, classes = set(), {}
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            toplevel.add(node.name)
        elif isinstance(node, ast.ClassDef):
            toplevel.add(node.name)
            bases = [b.id if isinstance(b, ast.Name) else
                     (b.attr if isinstance(b, ast.Attribute) else "?")
                     for b in node.bases]
            classes[node.name] = (own_methods(node), bases)
    return toplevel, classes


@functools.lru_cache(maxsize=256)
def _commit_exists(root_str, sha):
    try:
        r = subprocess.run(
            ["git", "-C", root_str, "cat-file", "-e", f"{sha}^{{commit}}"],
            capture_output=True, timeout=5,
        )
    except Exception:
        return True          # git 不可用 → 问不出答案 → 不判
    return r.returncode == 0


def _check_nodeid(root, path, cls, func):
    """用 AST 确认 class / def 真实存在 —— 不 import、不跑 pytest，无副作用且快。"""
    f = root / path
    if not f.exists():
        return f"文件不存在：{path}"
    table = _symbol_table(str(f))
    if table is None:
        return None          # 解析不了就不猜（fail-open）
    toplevel, classes = table

    if func is None:                      # 两段式 nodeid：文件::名字
        return None if cls in toplevel else f"{path} 的模块层没有 {cls}"

    if cls not in classes:
        return f"{path} 里没有类 {cls}"

    own, bases = classes[cls]
    if func in own:
        return None

    # 顺着本文件内可见的基类继续找
    seen, queue = {cls}, list(bases)
    while queue:
        b = queue.pop()
        if b in seen or b not in classes:
            continue
        seen.add(b)
        b_own, b_bases = classes[b]
        if func in b_own:
            return None
        queue.extend(b_bases)

    # 还有基类定义在别的文件里 —— 继承来的方法看不见，属于「问不出答案」，放行
    if any(b not in classes for b in bases):
        return None
    return f"{path} 的 {cls} 里没有 {func}"


def _check_fileline(root, path, line):
    f = root / path
    if not f.exists():
        return f"文件不存在：{path}"
    try:
        n = len(f.read_text(encoding="utf-8").splitlines())
    except Exception:
        return None
    if line > n:
        return f"{path} 只有 {n} 行，引用的第 {line} 行不存在"
    return None


def _check_commit(root, sha):
    return None if _commit_exists(str(root), sha) else f"commit {sha} 不在本仓库历史里"


_CHECKERS = {
    "nodeid": lambda root, r: _check_nodeid(root, r[2], r[3], r[4]),
    "fileline": lambda root, r: _check_fileline(root, r[2], r[3]),
    "commit": lambda root, r: _check_commit(root, r[2]),
}


def _verify_refs(root, refs):
    """返回 [(原文, 失效原因)]，全部有效则为空。"""
    bad = []
    for r in refs:
        reason = _CHECKERS[r[0]](root, r)
        if reason:
            bad.append((r[1], reason))
    return bad


# ————————————————————————— 主检查 —————————————————————————

def check(rel, text, root, audit=False):
    """写入时机：新条款必须带可核验证据；audit 时追加证据链保鲜检查。"""
    if context.classify(rel) != context.RULE:
        return []
    rel_s = str(rel)
    if rel_s.endswith(("-index.md", "-overview.md")):
        return []

    lines = context.body_without_frontmatter(text).splitlines()
    baseline = _load_baseline()
    out = []

    for title, lineno, body in _clauses(lines):
        fp = clause_fingerprint(rel_s, title)
        grandfathered = fp in baseline

        symptom = _field_value(body, _SYMPTOM)
        verify = _field_value(body, _VERIFY)
        trigger = _field_value(body, _TRIGGER)

        if not grandfathered:
            if symptom is None:
                out.append(Violation(
                    "PRV001", Severity.BLOCK, rel_s, lineno,
                    f"条款「{title}」没有 {_SYMPTOM}： 行 —— 无法判断这条规则源于真实踩坑还是推测",
                    f"补一行 {_SYMPTOM}：<这次实际观察到的错误表现，含判定依据>",
                ))
            elif _is_filler(symptom, MIN_SYMPTOM_LEN):
                out.append(Violation(
                    "PRV003", Severity.BLOCK, rel_s, lineno,
                    f"条款「{title}」的失败现象是空话或过短：「{symptom[:30]}」",
                    f"写出可复现的具体表现（≥{MIN_SYMPTOM_LEN} 字）：什么操作、什么报错、"
                    "怎么判定是这个原因而不是别的",
                ))

            if trigger is not None and _is_filler(trigger, MIN_TRIGGER_LEN):
                out.append(Violation(
                    "PRV003", Severity.BLOCK, rel_s, lineno,
                    f"条款「{title}」的触发条件是空话：「{trigger[:30]}」",
                    "写明什么情况下适用，而不是「视情况」「无」",
                ))

            if verify is None:
                out.append(Violation(
                    "PRV002", Severity.BLOCK, rel_s, lineno,
                    f"条款「{title}」没有 {_VERIFY}： 行 —— 修法未经验证，不得落库",
                    f"补一行 {_VERIFY}：并给出至少一个可核对的引用 —— "
                    "用例 tests/x.py::TestY::test_z、代码位置 framework/pages/x.py:42，"
                    "或修复的 commit 短哈希",
                ))
            else:
                refs = _iter_refs(verify)
                if not refs:
                    out.append(Violation(
                        "PRV002", Severity.BLOCK, rel_s, lineno,
                        f"条款「{title}」的验证没有可核对的引用：「{verify[:40]}」",
                        "「已验证」「跑通了」无法核对。给出 tests/x.py::TestY::test_z、"
                        "framework/pages/x.py:42 或 commit 短哈希",
                    ))
                else:
                    for raw, reason in _verify_refs(root, refs):
                        out.append(Violation(
                            "PRV004", Severity.BLOCK, rel_s, lineno,
                            f"条款「{title}」的验证引用 {raw} 不存在：{reason}",
                            "引用必须指向真实存在的用例 / 代码位置 / commit；"
                            "写不出来说明这条规则还没被验证过，先验证再落库",
                        ))

        elif audit and verify:
            # 存量豁免的是「补证据」，不豁免「证据后来烂掉了」
            for raw, reason in _verify_refs(root, _iter_refs(verify)):
                out.append(Violation(
                    "PRV005", Severity.WARN, rel_s, lineno,
                    f"条款「{title}」的证据链已断：{raw} —— {reason}",
                    "规则守护的场景可能已不存在：确认规则是否仍适用，"
                    "更新引用或归档该条款",
                ))
    return out


# ————————————————————————— 孤儿检测（audit） —————————————————————————

_LINK_RE = re.compile(r"\[[^\]]*\]\(([^)]+)\)")


def check_orphans(root):
    """没有任何入口引用的 rule 文件 —— 落了库却从没被用过。

    带 paths: frontmatter 的 rule 由 Claude Code 按文件路径自动加载，不需要被链接，
    因此不算孤儿。真正的孤儿是：既没有 paths（不会自动加载），又没人链接（不会被读到）。
    """
    entry = root / context.ENTRY_FILE
    if not entry.exists():
        # 没有入口文件的仓库谈不上「没人引用」—— 引用关系的起点都不存在。
        # 此时判孤儿纯属噪声（测试用的临时仓库、尚未初始化的 harness 都会中招）。
        return []

    referenced = set()
    scan = [entry]
    scan += list(root.glob(context.SKILLS_GLOB)) + list(root.glob(context.RULES_GLOB))
    for p in scan:
        try:
            text = p.read_text(encoding="utf-8")
        except Exception:
            continue
        for m in _LINK_RE.finditer(text):
            target = m.group(1).split("#")[0].strip()
            if not target or target.startswith(("http://", "https://", "mailto:")):
                continue
            try:
                resolved = (p.parent / target).resolve()
            except Exception:
                continue
            referenced.add(str(resolved))

    out = []
    for p in sorted(root.glob(context.RULES_GLOB)):
        rel_s = p.relative_to(root).as_posix()
        if rel_s.endswith(("-index.md", "-overview.md")):
            continue
        try:
            fm = context.frontmatter(p.read_text(encoding="utf-8")) or ""
        except Exception:
            continue
        if "paths:" in fm:
            continue
        if str(p.resolve()) not in referenced:
            out.append(Violation(
                "PRV006", Severity.WARN, rel_s, None,
                "规则既没有 paths: 自动加载，也没有任何文件链接它 —— 不会被读到",
                f"在 {context.ENTRY_FILE} 路由表或相关 skill 里链接它，"
                "补 paths: frontmatter，或确认已失效后删除",
            ))
    return out
