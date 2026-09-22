"""人工登录 alva 后保存登录态（Playwright storageState），供 user 角色用例复用。

为什么要人工：alva 只支持 Google / 邮箱验证码登录，没有 token 直登。验证码和
Google 的风控校验脚本既做不了也不该代劳，所以只自动化「开浏览器」和「存状态」
两头，中间留给人。

用法（在项目根执行）：
    .venv/bin/python framework/tools/save_auth_state.py --env prod

1. 脚本打开有头浏览器并进入 /login；
2. 在浏览器里手动登录 —— 推荐邮箱验证码。Google 常以「此浏览器可能不安全」
   拦截由自动化工具启动的浏览器；
3. 登录完成、看到首页后回到终端按回车；
4. 脚本回到首页确认确实已登录，才把状态写到 settings 里该环境的 storage_state
   路径（权限 600）。确认不了就不写 —— 一份没登录的状态文件会让 user 用例以为
   「有登录态」，再以「登录态已失效」的名义失败，排查方向全错。

alva 的 JWT 存在 cookie 里（前端 loadJwt 读的就是 cookie），storageState 默认
采集的 cookie + localStorage 已经够用；IndexedDB 里只有聊天时间线缓存，不采集。
"""
import argparse
import contextlib
import json
import os
import sys
import tempfile
from pathlib import Path

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import sync_playwright

# 作为独立脚本运行时 sys.path[0] 是 tools/ 自己，找不到 config / pages。
# 把 framework/ 放进去，与 pytest.ini 的 pythonpath = framework 用同一套导入路径，
# 这样校验登录用的就是用例里那个 HomePage，判据不会两处各写一份。
FRAMEWORK_DIR = Path(__file__).resolve().parents[1]
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


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="人工登录 alva 后保存登录态（storageState），供 user 角色用例复用",
    )
    parser.add_argument(
        "--env", required=True, choices=sorted(ENVS),
        help="目标环境，与 pytest --env 取值一致",
    )
    return parser.parse_args(argv)


def wait_until_logged_in(home: HomePage, base_url: str) -> bool:
    """等人登录完按回车，再回首页确认。没登录上就让人接着登，而不是直接退出 ——
    验证码邮件晚到、回车按早了都很常见，重跑一遍脚本还得重新走一次登录。"""
    while True:
        try:
            input("\n在浏览器里完成登录、看到首页后，回到这里按回车（Ctrl+C 放弃）… ")
        except (EOFError, KeyboardInterrupt):
            print("\n已放弃，未保存登录态。")
            return False
        home.open(base_url)
        # 先确认页面渲染完再判登录态：is_logged_in() 的依据是「Log in」按钮不可见，
        # 页面没渲染出来时它同样不可见，顺序反了会把「没加载完」当成「已登录」。
        if not home.is_page_loaded():
            print("首页没有加载出来，无法确认登录状态。检查网络后可再按回车重试。")
            continue
        if home.is_logged_in():
            return True
        print("仍未检测到登录状态（首页还显示「Log in」按钮）。可继续在浏览器里登录，完成后再按回车。")


def write_private_json(path: Path, data: dict) -> None:
    """原子写入，且文件从出生起就只有属主可读。

    先写同目录临时文件再 os.replace：中途被打断不会留下半截 JSON（半截文件会让
    Playwright 建 context 时直接报错）。临时文件由 mkstemp 创建，生来就是 600 ——
    若按默认权限写出再 chmod，中间有一段时间同机其他用户能读到会话 cookie。
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


def main(argv=None) -> int:
    args = parse_args(argv)
    env = ENVS[args.env]
    base_url = env["base_url"].rstrip("/")
    if not env.get("storage_state"):
        print(f"环境 {args.env} 未配置 storage_state，请对照 settings.example.py 补上。", file=sys.stderr)
        return 1
    state_path = Path(env["storage_state"])

    print(f"登录态将保存到：{state_path}")
    print("推荐用邮箱验证码登录；Google 登录可能被拦截（它会拒绝自动化工具启动的浏览器）。")

    with sync_playwright() as p:
        # 始终有头：得有人来登录，与 settings 的 HEADLESS 无关。
        # 也不沿用 SLOW_MO：它只拖慢脚本自己那几步，对人手操作毫无意义。
        browser = p.chromium.launch(headless=False)
        try:
            # 视口、超时与用例保持一致，登录校验看到的页面布局才和用例看到的相同
            context = browser.new_context(
                viewport={"width": VIEWPORT_WIDTH, "height": VIEWPORT_HEIGHT},
            )
            page = context.new_page()
            page.set_default_timeout(DEFAULT_TIMEOUT)
            page.set_default_navigation_timeout(DEFAULT_NAVIGATION_TIMEOUT)
            page.goto(f"{base_url}/login")

            if not wait_until_logged_in(HomePage(page), base_url):
                return 1
            state = context.storage_state()
        except PlaywrightError as exc:
            # 最常见的原因是人把浏览器窗口关掉了
            print(f"浏览器操作失败，未保存登录态：{exc}", file=sys.stderr)
            return 1
        except KeyboardInterrupt:
            print("\n已中断，未保存登录态。")
            return 130
        finally:
            with contextlib.suppress(PlaywrightError):
                browser.close()

    write_private_json(state_path, state)
    print(f"已保存登录态：{state_path}（权限 600；含会话 cookie，已被 .gitignore 忽略，切勿提交或外传）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
