import json
import os
import re
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from urllib.parse import urlsplit

import pytest
from playwright.sync_api import sync_playwright

from core.logger import get_logger

try:
    from config.settings import (
        DEFAULT_NAVIGATION_TIMEOUT,
        DEFAULT_TIMEOUT,
        ENVS,
        HEADLESS,
        SLOW_MO,
        VIEWPORT_HEIGHT,
        VIEWPORT_WIDTH,
    )
except ModuleNotFoundError as exc:
    # settings.py 被 .gitignore 忽略，新克隆的仓库里必然没有。原生报错只说
    # 「No module named config.settings」，看不出该从哪份模板复制。
    if exc.name != "config.settings":
        raise
    raise ImportError(
        "缺少 framework/config/settings.py（不随仓库分发）。请先在项目根执行："
        "cp framework/config/settings.example.py framework/config/settings.py"
    ) from exc

log = get_logger("velocitai.auth")

# 免登 token 的环境变量名，值为 settings 里 auth_cookie（authorization）那个 cookie 的值。
# 设置后优先于 storage_state 文件：临时换号、CI 注入都不必动本地文件。
AUTH_TOKEN_ENV_VAR = "ALVA_TOKEN"

# RFC 6265 的 cookie-octet：可见 ASCII，去掉双引号、逗号、分号、反斜杠。
# 不合规的值浏览器会拒收或截断；先在这里拦下，给出可操作的提示，
# 而不是让 add_cookies 报一句看不懂、还可能带出原值的错。
_COOKIE_VALUE_RE = re.compile(r"[!#-+\--:<-\[\]-~]+")


@dataclass(frozen=True)
class AuthToken:
    """免登 token（auth_cookie 那一个 cookie 的值）及其来源。

    值等同账号凭据，repr 里不含它：pytest 的失败回溯、--showlocals、断言改写都可能
    打印 fixture 的值，不能让 token 借此落进终端、日志或 allure 报告。
    """
    cookie_name: str
    host: str            # 注入时的 domain：base_url 的主机名（不带点 = host-only cookie，与站点下发的一致）
    source: str          # 给人看的来源说明（环境变量名 / 文件路径 + 记录的到期时间），不含值
    refresh_hint: str    # token 失效时该怎么换一个新的，供 AlvaBaseTest 的 fail 提示复用
    value: str = field(repr=False)

    def as_cookie(self) -> dict:
        """待注入的 cookie。只在 add_cookies 的调用处现取，不要存进变量或写进日志。"""
        return {
            "name": self.cookie_name,
            "value": self.value,
            "domain": self.host,
            "path": "/",
            "sameSite": "Lax",
        }


def _cookie_sent_to(cookie_domain: str, host: str) -> bool:
    """domain 为 cookie_domain 的 cookie 会不会随请求发给 host（host-only 与「.域」cookie 都算）。"""
    domain = cookie_domain.lstrip(".")
    return bool(domain) and (host == domain or host.endswith("." + domain))


def _token_from_env(cookie_name: str, host: str, regen_cmd: str) -> AuthToken | None:
    """来源一：环境变量 ALVA_TOKEN。未设置或为空返回 None。"""
    value = os.environ.get(AUTH_TOKEN_ENV_VAR, "").strip()
    if not value:
        return None
    if not _COOKIE_VALUE_RE.fullmatch(value) or value.startswith(f"{cookie_name}="):
        # 设置了却填错，说明使用者就是想跑需要登录的用例 —— fail 而不是 skip；出于安全不回显该值
        pytest.fail(
            f"环境变量 {AUTH_TOKEN_ENV_VAR} 的值不是合法的 cookie 值：只填 {cookie_name} cookie 的值本身，"
            f"不要带「{cookie_name}=」前缀、引号、空格或分号",
            pytrace=False,
        )
    return AuthToken(
        cookie_name=cookie_name,
        host=host,
        source=f"环境变量 {AUTH_TOKEN_ENV_VAR}",
        refresh_hint=(
            f"请把环境变量 {AUTH_TOKEN_ENV_VAR} 换成最新的 {cookie_name} cookie 值；"
            f"或 unset 它，改用本地登录态文件（生成：在项目根执行 `{regen_cmd}`）"
        ),
        value=value,
    )


def _token_from_state_file(path: str, cookie_name: str, host: str, regen_cmd: str) -> AuthToken | None:
    """来源二：storageState 文件。只取其中名为 cookie_name、且会发给 host 的那一个 cookie；
    文件不存在或里面没有它，返回 None。

    整份 storageState 不加载：免登只认这一个 cookie，文件里的其他 cookie（真实 Chrome
    导出的 Google 账号会话等）与 localStorage 一概不进 context。
    """
    broken = None
    try:
        with open(path, encoding="utf-8") as fh:
            cookies = json.load(fh).get("cookies") or []
    except FileNotFoundError:
        return None
    except (OSError, ValueError, AttributeError) as exc:
        broken = type(exc).__name__
    if broken:
        # 只报异常类型、且在 except 之外 fail：解析错误的消息可能带出文件片段，而文件里是 token
        pytest.fail(
            f"登录态文件无法解析（{broken}）：{path}。请在项目根重新执行 `{regen_cmd}` 生成",
            pytrace=False,
        )
    matches = [
        c for c in cookies
        if isinstance(c, dict)
        and c.get("name") == cookie_name
        and c.get("value")
        and _cookie_sent_to(str(c.get("domain", "")), host)
    ]
    if not matches:
        return None
    # 同名多份时（host-only 与「.域」各一份）优先取 host-only 那份，即站点实际下发的形态
    cookie = next((c for c in matches if c.get("domain") == host), matches[0])
    return AuthToken(
        cookie_name=cookie_name,
        host=host,
        source=f"登录态文件 {path}{_describe_expiry(cookie.get('expires'))}",
        refresh_hint=f"请在项目根重新执行 `{regen_cmd}` 人工登录，导出新的 token 后再跑",
        value=cookie["value"],
    )


def _describe_expiry(expires) -> str:
    """文件里记录的到期时间，只作排查提示；有没有失效以站点的实际表现为准（AlvaBaseTest 校验）。"""
    if not isinstance(expires, (int, float)) or expires <= 0:
        return ""                     # -1 = 会话 cookie，没有记录到期时间
    at = datetime.fromtimestamp(expires)
    expired = "，已过期" if at <= datetime.now() else ""
    return f"（文件记录 {at:%Y-%m-%d %H:%M} 到期{expired}）"


def pytest_addoption(parser):
    parser.addoption(
        "--env",
        action="store",
        required=True,
        help=f"目标环境：{' | '.join(ENVS)}",
    )
    parser.addoption(
        "--self-heal",
        action="store",
        default="off",
        choices=["off", "on", "strict", "auto"],
        help=(
            "选择器自愈：off=关闭（默认）；on=失效时尝试重建定位符，用例继续；"
            "strict=同 on，但只要发生过自愈就让会话以非零码结束，便于 CI 发现漂移；"
            "auto=同 on，并让模型在规则交白卷时推理（需要 ANTHROPIC_API_KEY，没有 key 只用规则），"
            "且无论有没有 key 都把修复写回 PageObject 源码（会改动工作区文件）"
        ),
    )


@pytest.fixture(scope="session")
def env(request):
    name = request.config.getoption("--env")
    if name not in ENVS:
        pytest.fail(f"Unknown env '{name}'. Available: {list(ENVS.keys())}")
    return ENVS[name]


@pytest.fixture(scope="session")
def base_url(env):
    # 统一去掉末尾斜杠：调用方一律写 f"{base_url}/path"，
    # settings 里哪天多写了一个 / 也不会拼出 https://alva.ai//path。
    return env["base_url"].rstrip("/")


@pytest.fixture(scope="session")
def auth_state_path(env, request):
    """当前环境的登录态（storageState）文件路径。只给路径，不管文件在不在 ——
    缺文件该 skip 还是该 fail，由使用它的 fixture 决定。"""
    path = env.get("storage_state")
    if not path:
        pytest.fail(
            f"环境 {request.config.getoption('--env')} 未配置 storage_state，"
            f"请对照 framework/config/settings.example.py 补上",
            pytrace=False,
        )
    return path


@pytest.fixture(scope="session")
def auth_token(env, base_url, request) -> AuthToken:
    """免登 token。取值优先级：环境变量 ALVA_TOKEN > storage_state 文件里的 auth_cookie。

    两处都取不到时 skip 而不是 fail：token 要人工登录才拿得到、且不入库，新克隆的仓库
    和 CI 上天然没有，整组用例报红只会淹没真正的回归失败。取到了但已失效是另一回事
    —— 由 AlvaBaseTest 访问登录页后校验并直接 fail。
    """
    env_name = request.config.getoption("--env")
    cookie_name = env.get("auth_cookie")
    if not cookie_name:
        pytest.fail(
            f"环境 {env_name} 未配置 auth_cookie（承载登录态的 cookie 名），"
            f"请对照 framework/config/settings.example.py 补上",
            pytrace=False,
        )
    host = urlsplit(base_url).hostname
    regen_cmd = f".venv/bin/python framework/tools/save_auth_state.py --env {env_name}"

    token = _token_from_env(cookie_name, host, regen_cmd)
    if token is None:
        # 只在没有环境变量时才要文件路径：用 ALVA_TOKEN 跑时，storage_state 配没配都无所谓
        state_path = request.getfixturevalue("auth_state_path")
        token = _token_from_state_file(state_path, cookie_name, host, regen_cmd)
        if token is None:
            why = "文件里没有该 cookie" if os.path.isfile(state_path) else "文件不存在"
            pytest.skip(
                f"未提供登录 token，跳过需要登录的用例。任选一种方式提供："
                f"① 环境变量 {AUTH_TOKEN_ENV_VAR}=<{cookie_name} cookie 的值>；"
                f"② 登录态文件 {state_path} 中名为 {cookie_name} 的 cookie（当前{why}），"
                f"在项目根执行 `{regen_cmd}` 人工登录后生成"
            )
    log.info("免登 token 来源：%s", token.source)
    return token


@pytest.fixture(scope="session")
def playwright_instance():
    with sync_playwright() as p:
        yield p


@pytest.fixture(scope="session")
def browser(playwright_instance):
    browser = playwright_instance.chromium.launch(
        headless=HEADLESS,
        slow_mo=SLOW_MO,
        args=["--incognito"],
    )
    yield browser
    browser.close()


@contextmanager
def _open_page(browser, auth_token: AuthToken | None = None):
    """所有 page fixture 的唯一出口：viewport、超时、登录 token 都在这一处决定。

    三个 fixture 各写一遍 new_context / set_default_timeout 时，改一处漏一处的后果
    是不同角色跑在不同的视口或超时下 —— 同一个页面访客用例过、登录用例挂，
    查半天却不是业务问题。分层沿用 .claude/skills/browser-config：viewport 在 context 层，
    超时在 page 层。
    """
    context = browser.new_context(
        viewport={"width": VIEWPORT_WIDTH, "height": VIEWPORT_HEIGHT},
    )
    try:
        if auth_token is not None:
            # 「凭 token 免登」：只注入这一个 cookie，且赶在建 page、发出任何请求之前
            context.add_cookies([auth_token.as_cookie()])
        page = context.new_page()
        page.set_default_timeout(DEFAULT_TIMEOUT)
        page.set_default_navigation_timeout(DEFAULT_NAVIGATION_TIMEOUT)
        yield page
    finally:
        # 关 context 会连带关掉其下所有 page，包括用例中途打开、没来得及关的新 tab
        context.close()


@pytest.fixture
def page(browser):
    """访客态、每个用例独立的 page。自愈 e2e 用例（tests/e2e）依赖它打开本地夹具。"""
    with _open_page(browser) as new_page:
        yield new_page


@pytest.fixture(scope="class")
def class_page(browser, request):
    """访客态、同一个 class 内共享的 page（条件见 .claude/rules/playwright/browser-context.md）。"""
    with _open_page(browser) as new_page:
        if request.cls is not None:       # 模块级函数也可能借用它，那里没有 cls 可挂
            request.cls.page = new_page
        yield new_page


@pytest.fixture(scope="class")
def auth_class_page(auth_token, request):
    """带登录 token、同一个 class 内共享的 page（条件见 .claude/rules/playwright/browser-context.md）。

    全新 context 里只注入 auth_token 那一个 cookie，不加载整份 storageState：登录与否
    只取决于 token 本身。交出去时 page 还停在空白页 —— 访问登录页、等它把人送回首页、
    校验登录态，由 AlvaBaseTest._session 完成。

    token 缺失由 auth_token skip，token 无效 / 过期由 AlvaBaseTest fail。
    browser 在拿到 token 之后才取：先要 browser 会在默认有头模式下白白弹出一个
    浏览器窗口，然后立刻 skip。
    """
    browser = request.getfixturevalue("browser")
    with _open_page(browser, auth_token=auth_token) as new_page:
        yield new_page


def pytest_configure(config):
    """按需开启自愈。默认关闭 —— 它会改变「失败」的含义，不能悄悄生效。"""
    if config.getoption("--self-heal") == "off":
        return
    from core.base.base_page import BasePage

    BasePage.self_heal_enabled = True
    if config.getoption("--self-heal") == "auto":
        BasePage.self_heal_use_llm = True
        BasePage.self_heal_patch = True
    try:
        from config.settings import SELF_HEAL_ARTIFACT, SELF_HEAL_FINGERPRINTS

        BasePage.heal_artifact = SELF_HEAL_ARTIFACT
        BasePage.heal_fingerprints = SELF_HEAL_FINGERPRINTS
    except ImportError:
        pass      # 旧配置文件没有这两项时沿用类默认值


def pytest_terminal_summary(terminalreporter, exitstatus, config):
    """自愈过的用例不能被当成干净通过，必须在报告里显式点名。"""
    from core.healing import runtime as heal_runtime

    if not heal_runtime.HEALED:
        return
    terminalreporter.section("选择器自愈", sep="=", bold=True)
    for h in heal_runtime.HEALED:
        terminalreporter.write_line(
            f"  {h['page_object']}.{h['constant']}: {h['old']} -> {h['new']} "
            f"（{h['strategy']}，置信 {h['confidence']}）"
        )
    if heal_runtime.PATCHED:
        terminalreporter.section("源码已被改写", sep="=", bold=True)
        for h in heal_runtime.PATCHED:
            flag = "已写回" if h["ok"] else "写回失败"
            terminalreporter.write_line(
                f"  [{flag}] {h['file']}::{h['constant']}  {h['old']} -> {h['new']}"
            )
        terminalreporter.write_line(
            "  原文件已备份为同名 .heal-bak。请 review 后再提交 —— "
            "写回同样要过落库闸门。"
        )
        terminalreporter.write_line(
            f"  共 {len(heal_runtime.HEALED)} 处定位符已修复，其中 "
            f"{sum(1 for h in heal_runtime.PATCHED if h['ok'])} 处已写回源码。"
        )
    else:
        terminalreporter.write_line(
            f"  共 {len(heal_runtime.HEALED)} 处定位符已在运行期临时修复；"
            f"源码尚未改动，写回需经 selector-self-heal skill 并通过落库闸门。"
        )


def pytest_sessionfinish(session, exitstatus):
    """strict 模式下，发生过自愈即以非零码结束，避免定位符漂移被沉默吞掉。"""
    from core.healing import runtime as heal_runtime

    if heal_runtime.HEALED and session.config.getoption("--self-heal") == "strict":
        session.exitstatus = 1
