"""环境与浏览器配置模板（alva.ai）。

使用：复制为同目录的 settings.py 再按需修改。settings.py 已被 .gitignore 忽略 ——
它可能被改成指向私人账号的登录态文件，或填上 API key，不能入库。

路径一律由本文件位置推算，不写死绝对路径：仓库换一台机器、换一个目录克隆，
配置照样指向正确位置；也不依赖 pytest 从哪个目录启动。
"""
import os
from pathlib import Path


def _env_bool(name: str, default: bool) -> bool:
    """读布尔型环境变量。认不出的取值直接报错，而不是悄悄当成 False ——
    HEADLESS=ture 这种笔误若被静默吞掉，CI 上就会去开一个没有屏幕的有头浏览器。"""
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    value = raw.strip().lower()
    if value in ("1", "true", "yes", "on"):
        return True
    if value in ("0", "false", "no", "off"):
        return False
    raise ValueError(f"环境变量 {name}={raw!r} 无法识别，请用 true/false、1/0、yes/no 或 on/off")


# 本文件位于 <项目根>/framework/config/，向上两级即项目根
PROJECT_ROOT = Path(__file__).resolve().parents[2]

# 登录 token 的本地存放目录。整个目录已在 .gitignore 中忽略，token 不入库。
#
# alva 的登录入口只有第三方（Google / X / Telegram / Discord）与邮箱验证码，自动化做不了；
# 但登录成功后的登录态就是站点域下名为 authorization 的 cookie（2026-09-22 实测：path=/、
# SameSite=Lax、非 httpOnly、非 secure，签发后约 21 天到期）。往一个全新的浏览器 context
# 里只注入这一个 cookie，再访问 /login，前端会直接把人送回首页且为登录态 —— 不经过登录表单，
# 也不经过 Cloudflare Turnstile 人机验证。这就是用例的「凭 token 免登」。
#
# 用例按以下优先级取 token（tests/conftest.py::auth_token）：
#   1. 环境变量 ALVA_TOKEN，值为 authorization cookie 的值（临时换号 / CI 注入用）；
#   2. 下方 storage_state 指向的 Playwright storageState 文件，只从中取 auth_cookie 那一个 cookie。
# 文件的生成：Playwright 自己启动的浏览器过不了 Turnstile，工具改为启动本机真实的
# Google Chrome，人工登录一次后导出（Chrome profile 也留在本目录，下次可免重登）：
#   .venv/bin/python framework/tools/save_auth_state.py --env prod
# token 等同账号凭据：不打印、不入库、不外传。
AUTH_STATE_DIR = str(PROJECT_ROOT / ".auth")

# 环境配置。目前 alva 只有生产环境，没有 pre。
# 不提供 DEFAULT_ENV：环境必须由使用者用 --env 显式指定（见 .claude/rules/agent-behavior），
# 留一个默认值只会诱导某段代码悄悄拿它兜底。
ENVS = {
    "prod": {
        "base_url": "https://alva.ai",       # 不带末尾斜杠，拼路径时统一写成 f"{base_url}/xxx"
        # token 的本地存放处（Playwright storageState，权限 600），说明见上方 AUTH_STATE_DIR
        "storage_state": str(Path(AUTH_STATE_DIR) / "prod_user.json"),
        # 承载登录态的 cookie 名（2026-09-22 实测）。免登时只注入这一个 cookie：
        # domain 取 base_url 的主机名，path=/，SameSite=Lax
        "auth_cookie": "authorization",
    },
}

# 浏览器配置
# 默认有头：本项目目前只在本机跑，调试时要能看见浏览器在做什么；
# CI / 无人值守时用环境变量 HEADLESS=true 覆盖，不必改这份文件。
HEADLESS = _env_bool("HEADLESS", False)
# 放慢每步操作只对「有人盯着看」有意义，所以默认值跟随 HEADLESS：
# 有头 500ms 便于肉眼跟上，无头 0 —— 没人看还放慢，纯属浪费回归时间。
# 两者都可以用环境变量 SLOW_MO=<毫秒> 单独覆盖。
SLOW_MO = int(os.environ.get("SLOW_MO") or (0 if HEADLESS else 500))
# 2026-09-22 本机实测访客态冷启动：首页可交互约 2.2s、load 事件约 4.8s，
# 同一 context 内再次导航约 0.4s。15s 对外网生产环境仍留有约 3 倍余量，
# 因此沿用上游默认值；弱网时单独调大导航超时即可（见 .claude/skills/browser-config）。
DEFAULT_TIMEOUT = 15000
DEFAULT_NAVIGATION_TIMEOUT = 15000
VIEWPORT_WIDTH = 1280
VIEWPORT_HEIGHT = 900

# 选择器自愈配置
# 产物路径。proposals 供 agent 侧复核与写回，fingerprints 是自愈所依据的
# 「旧有逻辑」—— 定位符上次成功命中时的元素形态。
# 锚定到项目根而不是相对当前目录：从别的目录启动 pytest 时，指纹库不会被
# 悄悄换成一份空的新库（那等于自愈失去了判断依据）。
SELF_HEAL_ARTIFACT = str(PROJECT_ROOT / "reports" / "self-heal" / "proposals.jsonl")
SELF_HEAL_FINGERPRINTS = str(PROJECT_ROOT / "reports" / "self-heal" / "fingerprints.json")

# 自愈的 LLM 推理后端（--self-heal=auto 时使用）。
# 留空则自愈退回纯规则模式，不会因此报错。环境变量 ANTHROPIC_API_KEY 优先于这里
# （见 core/healing/llm.py::api_key）。刻意写成字面量而不是 os.environ.get(...)：
# 在导入时把环境变量冻结进来，会让用例里 monkeypatch 掉的 key 仍从这里漏回去。
ANTHROPIC_API_KEY = ""
# 自愈推理用的模型 ID。留空则用 core/healing/llm.py::DEFAULT_MODEL；环境变量
# SELF_HEAL_MODEL 优先于这里（见 llm.py::model_name）。同样写成字面量，理由同上。
SELF_HEAL_MODEL = ""
# 自愈推理请求打到哪个地址。留空则用 core/healing/llm.py::DEFAULT_BASE_URL（Anthropic
# 官方地址）；环境变量 ANTHROPIC_BASE_URL 优先于这里（见 llm.py::base_url）。
# 指向自建代理或中转服务时填它们给的地址 —— 这类地址因人而异、常常本身就带私有
# token，和 key 一样属于本机配置，所以只放在这份不入库的文件里。
# 三种填法都认：根地址（https://host）、到 /v1、到 /v1/messages。同样写成字面量。
ANTHROPIC_BASE_URL = ""
