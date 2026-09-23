"""自愈的 LLM 推理后端 —— 启发式规则找不出候选时，让模型看页面结构自己判断。

为什么要有这一层：规则只会按固定策略（testid / id / role+名称 / 文本 / 类名）
拼选择器。碰上「按钮被换成了带图标的 div」「文案从『提交』改成『确认下单』」
这类改版，规则拼不出任何东西，但人一眼能看出来是哪个元素 —— 模型也能。

为什么规则仍然排在前面：有 testid 摆在那儿时，调一次模型既慢又贵，且结论
不会比规则更好。模型只在规则交白卷时才出场。

依赖边界：只用 stdlib urllib，不引 SDK。没有 API key 时静默跳过，
自愈退回纯规则模式 —— 缺这一层不该让任何用例失败。
"""
from __future__ import annotations

import importlib
import json
import os
import urllib.error
import urllib.request

from core.logger import get_logger

# API 根地址。未配置时用官方地址，见 base_url()。抽成配置项是为了能指向自建代理或
# 中转服务 —— 那类地址因人而异、常带私有 token，和 key 一样属于本机配置，
# 不能写死在入库的源码里。
log = get_logger("velocitai.healing")

DEFAULT_BASE_URL = "https://api.anthropic.com"
MESSAGES_PATH = "/v1/messages"
DEFAULT_MODEL = "claude-sonnet-5"   # 未配置 SELF_HEAL_MODEL 时使用，见 model_name()
MAX_ELEMENTS = 60       # 喂给模型的元素上限，超出部分按出现顺序截断
# 单次响应的 token 上限。**会思考的模型把思考 token 也算进这里** —— 2026-09-22 实测
# deepseek-flash 在一个两按钮难分的场景上思考就花掉 4521 token，上限 1024/2048/4096
# 时全部 stop_reason=max_tokens、只产出 thinking 块、一个 text 块都没有，候选恒为空。
# 目标本身明确时仅需约 511 token，所以这个上限只在难例上被用到，平时不产生额外开销。
MAX_TOKENS = 8192
TIMEOUT = 30


def _configured(env_var: str, settings_attr: str, default: str = "") -> str:
    """按 环境变量 → config.settings → 默认值 的顺序取一项配置。

    key、模型、API 根地址共用同一套优先级。各写一遍就是三个出口，改优先级时
    必然漏掉一个 —— 收口在这里。环境变量排前面是为了临时换号与 CI 注入不必动
    本地文件；settings.py 不入库，新克隆的仓库里根本没有，因此读不到、文件里
    缺这一项、值为空三种情况一律当成没配，退到默认值：缺配置只该让自愈退回
    纯规则模式，不该报错。

    用 import_module 而不是 `from config.settings import X`：前者只认
    sys.modules 里的那一份，单测顶替掉 config.settings 时拿到的才是假模块，
    不会从真实的本机配置里漏出 key。
    """
    v = os.environ.get(env_var, "").strip()
    if v:
        return v
    try:
        mod = importlib.import_module("config.settings")
        v = (getattr(mod, settings_attr, "") or "").strip()
    except Exception:
        v = ""
    return v or default


def api_key() -> str:
    """自愈推理用的 API key。取不到返回空串（自愈退回纯规则模式）。"""
    return _configured("ANTHROPIC_API_KEY", "ANTHROPIC_API_KEY")


def model_name() -> str:
    """自愈推理用的模型 ID。都没配时退回 DEFAULT_MODEL。"""
    return _configured("SELF_HEAL_MODEL", "SELF_HEAL_MODEL", DEFAULT_MODEL)


def base_url() -> str:
    """API 根地址。都没配时退回官方地址 DEFAULT_BASE_URL。"""
    return _configured("ANTHROPIC_BASE_URL", "ANTHROPIC_BASE_URL", DEFAULT_BASE_URL)


def api_url() -> str:
    """Messages API 的完整地址。

    三种填法都认：只填根地址（https://host）、填到 /v1、或直接填完整的
    /v1/messages —— 代理与中转服务给出的地址这三种都有。不容忍的话，填法
    不符就是 404，而 infer() 把网络错误一律静默吞掉，最终只表现为「模型
    永远交白卷」，没有任何线索指向是地址填错了。
    """
    u = base_url().rstrip("/")
    if u.endswith(MESSAGES_PATH):
        return u
    if u.endswith("/v1"):
        return u + "/messages"
    return u + MESSAGES_PATH


def available() -> bool:
    return bool(api_key())


# 固定保留的属性。data-* 一律保留，不在这里列举 —— 见 _pick_attrs。
_KEEP_ATTRS = ("id", "name", "type", "placeholder", "href", "alt", "value")
# 已知的测试锚点属性，排在其他 data-* 前面：它们最稳定，也最可能是答案本身。
_ANCHOR_ATTRS = ("data-testid", "data-test", "data-qa", "data-cy")
MAX_ATTRS = 8           # 每个元素最多带几个属性，防止埋点类 data-* 挤掉别的元素
MAX_ATTR_LEN = 40       # 单个属性值截断长度


def _pick_attrs(attrs: dict) -> dict:
    """挑出对定位有用的属性。

    旧版是一份固定白名单（id/data-testid/data-test/data-qa/name/type/placeholder），
    有两个毛病：一是和 runtime.SNAPSHOT_JS 的采集范围对不上 —— 那边把 [data-cy]
    采回来了，这边不保留，等于白采；二是真实站点的自定义 data-* 千奇百怪
    （data-name、data-track、data-id），固定名单一个都接不住。

    2026-09-22 实测 tests/e2e/fixtures/v4_after.html：两个按钮仅靠 data-name 区分，
    被白名单丢掉后模型收到两条逐字节相同的记录，只能交白卷。

    改为「已知锚点 → 其余 data-* → 固定几项」。加上限是因为一个元素可能挂十几个
    data-*（埋点、状态、i18n），全塞进去会把别的元素挤出 MAX_ELEMENTS。
    """
    picked: dict = {}

    def take(k, v):
        if v and k not in picked and len(picked) < MAX_ATTRS:
            picked[k] = str(v)[:MAX_ATTR_LEN]

    for k in _ANCHOR_ATTRS:
        take(k, attrs.get(k))
    for k, v in attrs.items():
        if k.startswith("data-"):
            take(k, v)
    for k in _KEEP_ATTRS:
        take(k, attrs.get(k))
    return picked


def _compact(elements: list) -> list:
    """把快照压成模型够用的最小形态，省 token 也少干扰。"""
    out = []
    for e in elements[:MAX_ELEMENTS]:
        item = {"tag": e.get("tag")}
        item.update(_pick_attrs(e.get("attrs") or {}))
        if e.get("role"):
            item["role"] = e["role"]
        if e.get("name"):
            item["aria"] = e["name"]
        if e.get("text"):
            item["text"] = e["text"][:60]
        # 所在容器。两个元素其余字段全都相同时，这常常是唯一能把它们分开的线索。
        if e.get("scope"):
            item["scope"] = e["scope"]
        cls = [c for c in (e.get("classes") or [])][:4]
        if cls:
            item["class"] = cls
        out.append(item)
    return out


def build_prompt(intent, elements: list, tried: list) -> str:
    return (
        "你是 UI 自动化测试的定位符专家。一个 Playwright 选择器因页面改版失效了，"
        "请根据它原本的意图，从当前页面元素中判断它现在应该指向哪个元素。\n\n"
        f"【失效的选择器】{intent.selector}\n"
        f"【所属页面对象】{intent.page_object or '未知'}\n"
        f"【常量名】{intent.constant}\n"
        f"【代码注释说明】{intent.description or '（无）'}\n"
        f"【上次成功命中时的元素形态】"
        f"标签={intent.tag or '未知'} role={intent.role or '未知'} 可及名称={intent.name or '未知'}\n\n"
        f"【规则已尝试且不可用的候选】{json.dumps(tried, ensure_ascii=False) if tried else '（无）'}\n\n"
        f"【当前页面元素】\n{json.dumps(_compact(elements), ensure_ascii=False, indent=1)}\n\n"
        "说明：元素记录里的 scope 是该元素所在的最内层容器（如 main、nav、#sidebar、"
        "[data-testid=\"panel\"]），它本身就是一个可用的选择器前缀。\n\n"
        "要求：\n"
        "1. 只返回 JSON，形如 {\"candidates\": [{\"selector\": \"...\", \"why\": \"...\"}]}，最多 3 个，按把握从高到低。\n"
        "2. 选择器必须是 Playwright 支持的语法（CSS、或 role=xxx[name=\"yyy\"]、或 text=）。\n"
        "3. 优先用 data-testid / id 等稳定锚点；不要使用构建工具生成的哈希类名"
        "（如 css-1a2b3c、sc-bdVaJa），它们下次构建就会变。\n"
        "4. 必须唯一命中一个元素。若干元素其余字段完全相同、只有 scope 不同时，"
        "用 scope 作前缀把范围收窄，例如 `main button[...]` 或 "
        "`main >> role=button[name=\"...\"]`。\n"
        "5. **如果没有任何元素符合原本的意图，返回 {\"candidates\": []}。**"
        "宁可交白卷，也不要勉强给一个看起来像的 —— 顶替错元素会让用例假通过，"
        "那比失败更糟。连 scope 也分不开几个元素时，同样交白卷。\n"
    )


def infer(intent, elements: list, tried: list | None = None,
          model: str | None = None) -> list:
    """返回模型给出的候选选择器字符串列表。任何失败都返回空列表。

    model 缺省时取 model_name()，调用方不必自己传。没有 key 时在发请求前就
    返回，不产生任何网络调用。
    """
    key = api_key()
    if not key or not elements:
        return []
    body = json.dumps({
        "model": model or model_name(),
        "max_tokens": MAX_TOKENS,
        "messages": [{"role": "user", "content": build_prompt(intent, elements, tried or [])}],
    }).encode("utf-8")
    req = urllib.request.Request(api_url(), data=body, method="POST", headers={
        "content-type": "application/json",
        "x-api-key": key,
        "anthropic-version": "2023-06-01",
    })
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            payload = json.loads(r.read().decode("utf-8"))
    except Exception:
        return []       # 网络/鉴权/超时一律静默退回规则模式
    candidates = parse_response(payload)
    if not candidates:
        _warn_if_truncated(payload)
    return candidates


def _warn_if_truncated(payload: dict) -> None:
    """响应被 max_tokens 截断时出声。

    这是配置问题而不是偶发故障 —— 会思考的模型能把整个预算花在 thinking 块上，
    一个 text 块都不产出，于是每一次都失败。infer() 对失败一律静默是对的
    （推理层故障不该影响测试结论），但静默到查不出该调哪个参数就过头了：
    表现只剩「模型永远交白卷」，和「模型认为没有合适元素」完全分不开。
    """
    if payload.get("stop_reason") != "max_tokens":
        return
    used = (payload.get("usage") or {}).get("output_tokens")
    log.warning(
        "模型响应被 max_tokens 截断（已用 %s，上限 %s），未能拿到候选。"
        "会思考的模型其思考 token 也计入该上限 —— 调大 core/healing/llm.py::MAX_TOKENS，"
        "或改用不思考的模型。", used, MAX_TOKENS)


def parse_response(payload: dict) -> list:
    """从 Messages API 响应里抽出候选选择器。格式不符即返回空列表。"""
    try:
        text = "".join(b.get("text", "") for b in payload.get("content", [])
                       if b.get("type") == "text")
        start, end = text.find("{"), text.rfind("}")
        if start < 0 or end <= start:
            return []
        data = json.loads(text[start:end + 1])
        out = []
        for c in data.get("candidates", [])[:3]:
            sel = (c.get("selector") or "").strip() if isinstance(c, dict) else ""
            if sel:
                out.append(sel)
        return out
    except Exception:
        return []
