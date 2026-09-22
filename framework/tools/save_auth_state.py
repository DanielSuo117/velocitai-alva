"""在真实 Google Chrome 里人工登录 alva，导出登录 token（storageState），供 user 用例「凭 token 免登」。

免登原理（2026-09-22 实测）：alva 的登录态就是站点域下名为 authorization 的 cookie
（settings 里的 auth_cookie）。往全新浏览器 context 只注入这一个 cookie 再访问 /login，
前端会直接把人送回首页且为登录态，不经过登录表单与 Cloudflare Turnstile。user 用例只从
本工具导出的文件里取这一个 cookie（tests/conftest.py::auth_token）。

为什么启动真实 Chrome：登录入口只有第三方（Google / X / Telegram / Discord）与邮箱验证码，
得有人来登；而 Playwright 启动的浏览器做真实登录会卡在 Turnstile。本机 Google Chrome
带独立 --user-data-dir 与 --remote-debugging-port 启动、由人手登录，则能通过。

为什么登录过程中只轮询 http://127.0.0.1:<port>/json/list：那是调试端口上的普通 HTTP 接口，
只读标签页 URL，不与任何页面建立 CDP 会话，登录页看到的就是一个普通浏览器。直到发现
回到首页，才用 Playwright connect_over_cdp 连上去读 cookie、导出。

用法（在项目根执行）：

  默认：启动本机 Chrome → 人工登录 → 自动导出 → 自检
      .venv/bin/python framework/tools/save_auth_state.py --env prod
    - Chrome 打开 <base_url>/login 后，用邮箱验证码或 Google 登录；回到首页即可，不必回终端操作。
      导出后脚本会关掉它自己启动的这个 Chrome。
    - Chrome profile 留在 .auth/chrome-profile-<env>（已被 .gitignore 忽略）。下次运行时若
      仍是登录态，/login 会直接回到首页，免去重新登录。
    - Chrome 路径：--chrome 或环境变量 CHROME_PATH；都没给时 macOS 用默认安装位置，
      其他平台必须显式指定。

  --attach PORT：从已用 --remote-debugging-port=PORT 启动、且已登录 alva 的 Chrome 导出，
  不启动也不关闭它：
      "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \\
          --remote-debugging-port=9222 --user-data-dir=<独立目录>
      （在这个 Chrome 里登录 alva 之后）
      .venv/bin/python framework/tools/save_auth_state.py --env prod --attach 9222

导出的文件只保留本站点（base_url 主机）的 cookie 与 localStorage：真实 Chrome 里还有 Google
账号等别家的会话 cookie，用例用不到，不该跟着落盘。文件权限 600。
导出后自检：新开无头 Playwright 浏览器，只注入 auth cookie 访问 /login，确认被送回首页且为登录态。
全程不打印 token 的值，只打印 cookie 名与到期时间。
"""
import argparse
import contextlib
import http.client
import json
import os
import re
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

# 作为独立脚本运行时 sys.path[0] 是 tools/ 自己，找不到 config / pages。
# 把 framework/ 放进去，与 pytest.ini 的 pythonpath = framework 用同一套导入路径，
# 这样自检用的就是用例里那个 LoginPage / HomePage，判据不会两处各写一份。
FRAMEWORK_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = FRAMEWORK_DIR.parent
if str(FRAMEWORK_DIR) not in sys.path:
    sys.path.insert(0, str(FRAMEWORK_DIR))

try:
    from config.settings import (  # noqa: E402
        DEFAULT_NAVIGATION_TIMEOUT,
        DEFAULT_TIMEOUT,
        ENVS,
        VIEWPORT_HEIGHT,
        VIEWPORT_WIDTH,
    )
except ModuleNotFoundError as exc:
    if exc.name != "config.settings":
        raise
    sys.exit(
        "缺少 framework/config/settings.py。请先在项目根执行："
        "cp framework/config/settings.example.py framework/config/settings.py"
    )
from pages.home_page import HomePage  # noqa: E402
from pages.login_page import LoginPage  # noqa: E402

MAC_CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
DEFAULT_LOGIN_TIMEOUT = 600          # 秒。等人登录：邮箱验证码晚到、Google 二次验证都要时间
DEVTOOLS_READY_TIMEOUT = 30          # 秒。Chrome 冷启动到调试端口可用
POLL_INTERVAL = 1.0                  # 秒。轮询 /json/list 的间隔
COOKIE_SETTLE_TIMEOUT = 10           # 秒。回到首页后等 auth cookie 可读的上限
# 自检里访问 /login 后等它送回首页的上限，与 AlvaBaseTest.LOGIN_REDIRECT_TIMEOUT（tests/base_test.py）一致：
# 跳转由前端水合后发起，2026-09-22 实测 load 事件后约 0.7s。
REDIRECT_TIMEOUT_MS = 10000

# 直连本机调试端口：不走 http_proxy 等代理环境变量（代理多半转发不了 127.0.0.1）
_DIRECT_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


# ── 参数 ────────────────────────────────────────────────────────────
def _port(text: str) -> int:
    try:
        port = int(text)
    except ValueError:
        raise argparse.ArgumentTypeError(f"不是端口号：{text}") from None
    if not 1 <= port <= 65535:
        raise argparse.ArgumentTypeError("端口需在 1–65535 之间")
    return port


def _positive_int(text: str) -> int:
    try:
        value = int(text)
    except ValueError:
        raise argparse.ArgumentTypeError(f"不是整数：{text}") from None
    if value <= 0:
        raise argparse.ArgumentTypeError("必须大于 0")
    return value


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        prog="save_auth_state.py",
        description=(
            "在真实 Google Chrome 里人工登录 alva，导出登录 token（storageState，只含本站点），"
            "供 user 用例凭 token 免登。导出后自动自检：无头浏览器只注入 auth cookie 访问 /login，"
            "应被直接送回首页且为登录态。全程不打印 token 的值。"
        ),
        epilog=(
            "示例（在项目根执行）：\n"
            "  启动本机 Chrome，人工登录后自动导出：\n"
            "    .venv/bin/python framework/tools/save_auth_state.py --env prod\n"
            "  从已开远程调试端口且已登录的 Chrome 导出（不启动也不关闭它）：\n"
            "    .venv/bin/python framework/tools/save_auth_state.py --env prod --attach 9222\n"
            "\n"
            "导出位置：settings 里该环境的 storage_state（默认 .auth/<env>_user.json，权限 600，不入库）。\n"
            "user 用例也可以不用文件，改用环境变量 ALVA_TOKEN=<auth cookie 的值> 提供 token。"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--env", required=True, choices=sorted(ENVS),
        help="目标环境（必填），与 pytest --env 取值一致",
    )
    source = parser.add_mutually_exclusive_group()
    source.add_argument(
        "--chrome", metavar="PATH",
        help=(
            "Google Chrome 可执行文件路径。缺省时依次取环境变量 CHROME_PATH、macOS 默认安装位置"
            f"（{MAC_CHROME}）；非 macOS 必须指定"
        ),
    )
    source.add_argument(
        "--attach", metavar="PORT", type=_port,
        help=(
            "不启动 Chrome，改为连接本机已用 --remote-debugging-port=PORT 启动、且已登录 alva 的 Chrome "
            "导出登录 token；不会关闭它"
        ),
    )
    parser.add_argument(
        "--timeout", metavar="SECONDS", type=_positive_int, default=DEFAULT_LOGIN_TIMEOUT,
        help=f"默认模式下等待人工登录完成的最长秒数（默认 {DEFAULT_LOGIN_TIMEOUT}，即 10 分钟）",
    )
    return parser.parse_args(argv)


# ── Chrome 与调试端口 ───────────────────────────────────────────────
def resolve_chrome(cli_path: str | None) -> str:
    """定位 Chrome 可执行文件：--chrome > CHROME_PATH > macOS 默认位置。找不到直接退出。"""
    path = (cli_path or os.environ.get("CHROME_PATH", "")).strip()
    if not path:
        if sys.platform != "darwin":
            sys.exit("当前不是 macOS：请用 --chrome 或环境变量 CHROME_PATH 指定 Google Chrome 可执行文件路径")
        path = MAC_CHROME
    # 给的是 .app 包时，换成包里的可执行文件
    bundle = Path(path)
    if bundle.suffix == ".app" and bundle.is_dir():
        path = str(bundle / "Contents" / "MacOS" / bundle.stem)
    if not (os.path.isfile(path) and os.access(path, os.X_OK)):
        sys.exit(f"找不到可执行的 Google Chrome：{path}。请用 --chrome 或环境变量 CHROME_PATH 指定")
    return path


def pick_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def list_tabs(port: int) -> list | None:
    """读调试端口的 /json/list（普通 HTTP，不建立 CDP 会话）。端口不通返回 None。"""
    try:
        with _DIRECT_OPENER.open(f"http://127.0.0.1:{port}/json/list", timeout=2) as resp:
            data = json.load(resp)
    except (OSError, ValueError, http.client.HTTPException):
        return None
    return data if isinstance(data, list) else None


def launch_chrome(chrome: str, port: int, profile_dir: Path, start_url: str) -> subprocess.Popen:
    profile_dir.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    profile_dir.mkdir(mode=0o700, exist_ok=True)
    return subprocess.Popen(
        [
            chrome,
            f"--remote-debugging-port={port}",
            f"--user-data-dir={profile_dir}",
            "--no-first-run",
            "--no-default-browser-check",
            start_url,
        ],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        # 自成进程组：终端里按 Ctrl+C 只打断脚本，由脚本自己收尾关 Chrome
        start_new_session=True,
    )


def wait_devtools_ready(proc: subprocess.Popen | None, port: int, timeout: float) -> bool:
    deadline = time.monotonic() + timeout
    while True:
        if proc is not None and proc.poll() is not None:
            return False
        if list_tabs(port) is not None:
            return True
        if time.monotonic() >= deadline:
            return False
        time.sleep(0.5)


def is_home_url(url: str, base_url: str) -> bool:
    """与 base_url 同源且路径为 /。登录页 /login、第三方登录回调页 /oauth-login 自然都不算。"""
    u, b = urlsplit(url), urlsplit(base_url)
    return (u.scheme, u.netloc) == (b.scheme, b.netloc) and u.path in ("", "/")


def wait_for_home(proc: subprocess.Popen, port: int, base_url: str, timeout: int) -> bool:
    """只轮询 /json/list 的 URL，直到有标签页回到首页。Chrome 被关掉或超时返回 False。"""
    deadline = time.monotonic() + timeout
    next_notice = time.monotonic() + 60
    while True:
        if proc.poll() is not None:
            print("Chrome 已被关闭，未保存登录态。", file=sys.stderr)
            return False
        tabs = list_tabs(port) or []
        if any(t.get("type") == "page" and is_home_url(t.get("url", ""), base_url) for t in tabs):
            return True
        now = time.monotonic()
        if now >= deadline:
            print(f"等待登录超时（{timeout}s），未保存登录态。可用 --timeout 延长。", file=sys.stderr)
            return False
        if now >= next_notice:
            print(f"仍在等待登录完成……（剩余约 {int(deadline - now)}s，Ctrl+C 放弃）")
            next_notice = now + 60
        time.sleep(POLL_INTERVAL)


def shutdown_chrome(proc: subprocess.Popen, grace: float) -> None:
    """关掉本脚本启动的 Chrome：先给 grace 秒让它响应 Browser.close 自行退出（profile 正常落盘，
    下次可免重登），再 SIGTERM，最后 SIGKILL。"""
    for step in (None, proc.terminate, proc.kill):
        if proc.poll() is not None:
            return
        if step is not None:
            step()
        with contextlib.suppress(subprocess.TimeoutExpired):
            proc.wait(timeout=grace if step is None else 10)


# ── 导出 ────────────────────────────────────────────────────────────
def _cookie_sent_to(cookie_domain: str, host: str) -> bool:
    """domain 为 cookie_domain 的 cookie 会不会随请求发给 host（host-only 与「.域」cookie 都算）。"""
    domain = cookie_domain.lstrip(".")
    return bool(domain) and (host == domain or host.endswith("." + domain))


def site_only(state: dict, host: str) -> dict:
    """storageState 只留会发给 host 的 cookie 与 host 自己的 localStorage。"""
    return {
        "cookies": [c for c in state.get("cookies", []) if _cookie_sent_to(c.get("domain", ""), host)],
        "origins": [o for o in state.get("origins", []) if urlsplit(o.get("origin", "")).hostname == host],
    }


def wait_auth_cookie(context, base_url: str, host: str, cookie_name: str) -> dict | None:
    """等 auth cookie 可读（回到首页的瞬间它可能还没落地）。同名多份时优先 host-only 那份。"""
    deadline = time.monotonic() + COOKIE_SETTLE_TIMEOUT
    while True:
        found = [c for c in context.cookies(f"{base_url}/") if c.get("name") == cookie_name and c.get("value")]
        if found:
            return next((c for c in found if c.get("domain") == host), found[0])
        if time.monotonic() >= deadline:
            return None
        time.sleep(0.5)


def export_state(p, port: int, base_url: str, cookie_name: str, close_chrome: bool):
    """connect_over_cdp 读出登录态，返回 (只含本站点的 storageState, auth cookie)；
    Chrome 里没有 auth cookie 时返回 (None, None)。close_chrome=True 时顺带让 Chrome 自行退出。"""
    host = urlsplit(base_url).hostname
    browser = p.chromium.connect_over_cdp(f"http://127.0.0.1:{port}")
    try:
        if not browser.contexts:
            print("连上了 Chrome，但没有找到默认浏览器上下文，无法导出。", file=sys.stderr)
            return None, None
        context = browser.contexts[0]
        cookie = wait_auth_cookie(context, base_url, host, cookie_name)
        if cookie is None:
            print(
                f"Chrome 里没有 {host} 的 {cookie_name} cookie —— 看起来并未登录成功，未保存登录态。"
                "请在该 Chrome 里确认已登录 alva 后重试。",
                file=sys.stderr,
            )
            return None, None
        return site_only(context.storage_state(), host), cookie
    finally:
        if close_chrome:
            with contextlib.suppress(PlaywrightError):
                browser.new_browser_cdp_session().send("Browser.close")
        # connect_over_cdp 得到的 browser，close() 只断开连接，不会关掉 Chrome（--attach 靠这一点）
        with contextlib.suppress(PlaywrightError):
            browser.close()


def write_private_json(path: Path, data: dict) -> None:
    """原子写入，且文件从出生起就只有属主可读。

    先写同目录临时文件再 os.replace：中途被打断不会留下半截 JSON（半截文件会让
    user 用例读 token 时直接报错）。临时文件由 mkstemp 创建，生来就是 600 ——
    若按默认权限写出再 chmod，中间有一段时间同机其他用户能读到 token。
    """
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    except BaseException:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(tmp)
        raise
    # replace 后文件沿用临时文件的 600；这里再显式钉一次，
    # 不让「权限对不对」取决于 mkstemp 的实现细节。
    os.chmod(path, 0o600)


def describe_cookie(cookie: dict) -> str:
    """cookie 名、domain 与到期时间 —— 不含值。"""
    expires = cookie.get("expires", -1)
    if isinstance(expires, (int, float)) and expires > 0:
        at = datetime.fromtimestamp(expires)
        days = (at - datetime.now()).total_seconds() / 86400
        when = f"到期 {at:%Y-%m-%d %H:%M}（约 {days:.0f} 天后）"
    else:
        when = "会话 cookie，未记录到期时间"
    return f"{cookie['name']}（domain={cookie.get('domain')}，{when}）"


# ── 自检 ────────────────────────────────────────────────────────────
def verify_token_login(p, base_url: str, cookie: dict) -> bool:
    """与 user 用例同一条路：全新无头 context 只注入 auth cookie（形态同 conftest 的
    AuthToken.as_cookie）→ 访问 /login → 应被送回首页，且 HomePage 判定为登录态。"""
    host = urlsplit(base_url).hostname
    home_url = re.compile(rf"^{re.escape(base_url)}/(?:[?#].*)?$")
    browser = p.chromium.launch(headless=True)
    try:
        context = browser.new_context(viewport={"width": VIEWPORT_WIDTH, "height": VIEWPORT_HEIGHT})
        context.add_cookies([{
            "name": cookie["name"],
            "value": cookie["value"],
            "domain": host,
            "path": "/",
            "sameSite": "Lax",
        }])
        page = context.new_page()
        page.set_default_timeout(DEFAULT_TIMEOUT)
        page.set_default_navigation_timeout(DEFAULT_NAVIGATION_TIMEOUT)
        LoginPage(page).open(base_url)
        try:
            page.wait_for_url(home_url, timeout=REDIRECT_TIMEOUT_MS)
        except PlaywrightTimeoutError:
            print(
                f"自检失败：只注入 {cookie['name']} 后访问 /login，{REDIRECT_TIMEOUT_MS // 1000}s 内"
                f"没有被送回首页（当前 {page.url}）。",
                file=sys.stderr,
            )
            return False
        home = HomePage(page)
        if not home.is_page_loaded():
            print("自检失败：已被送回首页，但首页没有加载完整。", file=sys.stderr)
            return False
        if not home.is_logged_in():
            print("自检失败：已被送回首页，但侧边栏仍显示「Log in」，不是登录态。", file=sys.stderr)
            return False
        print(
            f"自检通过：全新无头浏览器只注入 {cookie['name']} cookie，访问 {base_url}/login "
            "被直接送回首页，且为登录态。"
        )
        return True
    except PlaywrightError as exc:
        print(f"自检出错：{str(exc).splitlines()[0]}", file=sys.stderr)
        return False
    finally:
        with contextlib.suppress(PlaywrightError):
            browser.close()


# ── 主流程 ──────────────────────────────────────────────────────────
def main(argv=None) -> int:
    # 输出被重定向到文件 / 管道时 stdout 默认整块缓冲，会排到 stderr 的报错后面，顺序全乱
    with contextlib.suppress(AttributeError, ValueError):
        sys.stdout.reconfigure(line_buffering=True)
    args = parse_args(argv)
    env = ENVS[args.env]
    base_url = env["base_url"].rstrip("/")
    cookie_name = env.get("auth_cookie")
    if not cookie_name or not env.get("storage_state"):
        print(
            f"环境 {args.env} 缺少 auth_cookie 或 storage_state 配置，"
            "请对照 framework/config/settings.example.py 补上。",
            file=sys.stderr,
        )
        return 1
    state_path = Path(env["storage_state"])
    host = urlsplit(base_url).hostname

    proc = None
    chrome_told_to_close = False
    try:
        if args.attach:
            port = args.attach
            if not wait_devtools_ready(None, port, timeout=3):
                print(
                    f"127.0.0.1:{port} 上没有可连接的 Chrome 调试端口。请先用 "
                    f"--remote-debugging-port={port} 与独立的 --user-data-dir 启动 Chrome 并登录 alva。",
                    file=sys.stderr,
                )
                return 1
            print(f"连接 127.0.0.1:{port} 上的 Chrome 导出登录 token（不会启动或关闭它）。")
        else:
            chrome = resolve_chrome(args.chrome)
            port = pick_free_port()
            profile_dir = PROJECT_ROOT / ".auth" / f"chrome-profile-{args.env}"
            proc = launch_chrome(chrome, port, profile_dir, f"{base_url}/login")
            if not wait_devtools_ready(proc, port, DEVTOOLS_READY_TIMEOUT):
                if proc.poll() is not None:
                    print(
                        f"Chrome 启动后立即退出了。常见原因：profile {profile_dir} 正被另一个 Chrome "
                        "窗口占用 —— 关掉那个窗口后重跑，或给它开调试端口后改用 --attach。",
                        file=sys.stderr,
                    )
                else:
                    print(f"Chrome 的调试端口 {port} 在 {DEVTOOLS_READY_TIMEOUT}s 内没有就绪。", file=sys.stderr)
                return 1
            print(
                f"已启动 Google Chrome（独立 profile：{profile_dir.relative_to(PROJECT_ROOT)}）并打开 {base_url}/login。\n"
                "请在这个 Chrome 窗口里完成登录（邮箱验证码或 Google 均可）。登录成功、回到首页后脚本会自动导出，"
                "不必回终端操作。\n"
                f"最长等待 {args.timeout}s（--timeout 可调），Ctrl+C 放弃。"
            )
            if not wait_for_home(proc, port, base_url, args.timeout):
                return 1
            print("检测到已回到首页，开始导出登录 token……")

        with sync_playwright() as p:
            chrome_told_to_close = proc is not None
            state, cookie = export_state(p, port, base_url, cookie_name, close_chrome=chrome_told_to_close)
    except KeyboardInterrupt:
        print("\n已中断，未保存登录态。")
        return 130
    except PlaywrightError as exc:
        print(f"连接 Chrome 导出失败，未保存登录态：{str(exc).splitlines()[0]}", file=sys.stderr)
        return 1
    finally:
        if proc is not None:
            shutdown_chrome(proc, grace=10 if chrome_told_to_close else 0)

    if cookie is None:
        return 1
    write_private_json(state_path, state)
    print(
        f"已导出登录 token：{state_path}\n"
        f"  只含 {host} 的 {len(state['cookies'])} 个 cookie 与 {len(state['origins'])} 个源的 localStorage；"
        "权限 600，已被 .gitignore 忽略，切勿提交或外传。\n"
        f"  登录 cookie：{describe_cookie(cookie)}"
    )

    print("自检中：无头浏览器只注入该 cookie 访问 /login ……")
    with sync_playwright() as p:
        ok = verify_token_login(p, base_url, cookie)
    if not ok:
        print(
            "登录 token 已保存，但自检未通过：user 用例大概率会以「token 无效或已过期」失败。"
            "请确认在 Chrome 里确实登录成功后重跑本脚本。",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
