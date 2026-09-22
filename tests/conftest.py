import os
from contextlib import contextmanager

import pytest
from playwright.sync_api import sync_playwright

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
            "auto=同 on，并让模型在规则交白卷时推理，且把修复写回 PageObject 源码"
            "（需要 ANTHROPIC_API_KEY；会改动工作区文件）"
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
def _open_page(browser, storage_state=None):
    """所有 page fixture 的唯一出口：viewport、超时、登录态都在这一处决定。

    三个 fixture 各写一遍 new_context / set_default_timeout 时，改一处漏一处的后果
    是不同角色跑在不同的视口或超时下 —— 同一个页面访客用例过、登录用例挂，
    查半天却不是业务问题。分层沿用 .claude/skills/browser-config：viewport 在 context 层，
    超时在 page 层。
    """
    context = browser.new_context(
        viewport={"width": VIEWPORT_WIDTH, "height": VIEWPORT_HEIGHT},
        storage_state=storage_state,
    )
    try:
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
def user_class_page(auth_state_path, request):
    """带登录态、同一个 class 内共享的 page。

    登录态文件缺失时 skip 而不是 fail：它要人工登录才能生成、且不入库，新克隆的
    仓库和 CI 上天然没有，整组 user 用例报红只会淹没真正的回归失败。
    文件在、但登录态已过期是另一回事 —— 由 UserBaseTest 打开首页后校验并直接 fail。

    browser 在确认文件存在之后才取：先要 browser 会在默认有头模式下白白弹出一个
    浏览器窗口，然后立刻 skip。
    """
    if not os.path.isfile(auth_state_path):
        pytest.skip(
            f"登录态文件不存在：{auth_state_path}。请先在项目根执行 "
            f"`.venv/bin/python framework/tools/save_auth_state.py "
            f"--env {request.config.getoption('--env')}` 手动登录生成"
        )
    browser = request.getfixturevalue("browser")
    with _open_page(browser, storage_state=auth_state_path) as new_page:
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
