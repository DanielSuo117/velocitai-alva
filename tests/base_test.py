# 文件用途：alva 用例基础测试类 —— 封装所有用例共有的部分：带 token 的共享 page、页面对象、凭 token 免登、每个用例从首页起点开始
"""alva 用例的基础测试类。新的测试类继承 AlvaBaseTest 即可，不要在用例里重复写下面这些。

当前版本不区分角色，所有用例都以同一个登录账号运行。基类负责四件事：

1. 共享 page：每个测试类一个全新 context，只注入登录 token（conftest 的 auth_class_page）；
   同一个 class 里的用例共用这一个 page。
2. 页面对象：self.page / self.login_page / self.home_page，用例里直接用。
3. 凭 token 免登：每个 class 只走一次 —— 访问 alva 登录页 /login，前端识别到 token
   后直接把人送回首页（客户端跳转，不经过登录表单与 Turnstile），再确认首页已加载、为登录态。
4. 起点复位：每个用例开始前导航回首页并断言起点，上一个用例的残留不会带进下一个。

alva 的登录入口只有第三方（Google / X / Telegram / Discord）与邮箱验证码，自动化做不了；
但登录态就是一个名为 authorization 的 cookie，所以走「凭 token 免登」。
三种「没登录」的处理刻意不同：
- 拿不到 token（环境变量 ALVA_TOKEN 与本地 token 文件都没有）→ conftest 的 auth_token 里 skip。
  新克隆的仓库、CI 上天然没有，整组报红只会淹没真正的回归失败。
- 有 token，但访问登录页后仍停在登录页 → 这里 fail「token 无效或已过期」。
  有 token 说明使用者想跑用例，悄悄 skip 会让覆盖率静默归零。
- 被送回了首页、却不是登录态 → 同样按 token 失效 fail。

用例跑在生产站点、用的是真实账号，默认只读：不发消息、不新建频道 / 会话、不改设置、
不点 Portfolio / IM 等外部授权入口。例外须经用户同意并在用例文档串里写明（如 test_alva_agent_chat.py 会真实发一条消息）。
"""
import re

import pytest
from playwright.sync_api import Page
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from core.base.base_test import BaseTest
from pages.home_page import HomePage
from pages.login_page import LoginPage


class AlvaBaseTest(BaseTest):
    # 由 _session 注入；class 内所有用例共用同一个已登录的 page
    page: Page
    login_page: LoginPage
    home_page: HomePage

    # 访问登录页后等它把人送回首页的上限。跳转是前端水合后做的（/login 本身返回 200，
    # 不是 HTTP 3xx）：2026-09-22 本机无头实测，load 事件后约 0.7～2.3s 跳到 /（多次测量波动）。
    # 10s 留足弱网余量；token 无效时页面停在登录页不会跳，这也是判定失效前要等的时长。
    # 不用 networkidle：登录态首页有常驻后台请求，永远等不到网络空闲。
    LOGIN_REDIRECT_TIMEOUT = 10000

    @pytest.fixture(scope="class", autouse=True)
    @classmethod
    def _session(cls, auth_class_page, auth_token, base_url, request):
        # class 级 fixture 只跑一次，而每个用例都是新实例：属性必须挂在类上（request.cls），
        # 用例里的 self.page 才读得到。写成 classmethod 是 pytest 9 的要求 ——
        # 实例方法形式的 class 级 fixture 已被弃用并告警。
        page = auth_class_page
        request.cls.page = page
        request.cls.login_page = LoginPage(page)
        request.cls.home_page = HomePage(page)
        # 免登每个 class 只走一次：访问登录页、等前端送回首页、再确认登录态，
        # 这一串比每个用例开头直接导航首页慢得多，没必要每个用例都做一遍。
        request.cls.login_by_token(base_url, auth_token)

    @classmethod
    def login_by_token(cls, base_url, auth_token):
        """访问登录页 → 等前端凭 token 送回首页 → 确认首页已加载且为登录态。任何一步不成立都 fail。"""
        page, login, home = cls.page, cls.login_page, cls.home_page
        login.open(base_url)
        # 首页 URL：base_url + "/"，允许带查询串或锚点；/login 等其他路径都不算
        home_url = re.compile(rf"^{re.escape(base_url)}/(?:[?#].*)?$")
        try:
            page.wait_for_url(home_url, timeout=cls.LOGIN_REDIRECT_TIMEOUT)
            redirected = True
        except PlaywrightTimeoutError:
            redirected = False
        # 在 except 之外 fail：否则报告里会先挂一段 Playwright 超时回溯，把真正的结论挤到后面
        if not redirected:
            still_on_login = (
                page.url.split("?", 1)[0].rstrip("/") == f"{base_url}{LoginPage.PATH}"
                and login.is_page_loaded()
            )
            if still_on_login:
                pytest.fail(
                    f"token 无效或已过期，请重新生成：注入 {auth_token.cookie_name} cookie"
                    f"（来源：{auth_token.source}）后访问登录页，"
                    f"{cls.LOGIN_REDIRECT_TIMEOUT // 1000}s 内没有被送回首页，仍停在登录表单。"
                    f"{auth_token.refresh_hint}",
                    pytrace=False,
                )
            pytest.fail(
                f"访问登录页后 {cls.LOGIN_REDIRECT_TIMEOUT // 1000}s 内既没有被送回首页，"
                f"也不在登录表单上，当前 URL：{page.url}",
                pytrace=False,
            )

        # 必须先等页面渲染完再判登录态：页面还没渲染出来时，登录态的判据同样不成立，
        # 顺序反过来会把「没加载完」误判成「token 失效」。
        if not home.is_page_loaded():
            pytest.fail("已被送回首页，但首页加载失败，无法校验登录态", pytrace=False)
        if not home.is_logged_in():
            pytest.fail(
                f"token 无效或已过期，请重新生成：已被送回首页，但侧边栏没有用户菜单"
                f"（token 来源：{auth_token.source}）。{auth_token.refresh_hint}",
                pytrace=False,
            )

    @pytest.fixture(autouse=True)
    def _reset_to_home(self, _session, base_url):
        """每个用例开始前把共享 page 导航回首页，并断言起点。

        为什么每次都导航，而不是 case-round-trip 里「不在起点才复位」的写法：
        - 判定「不在起点」要等 is_page_loaded() 返回 False，而它对每个缺席的
          元素都会先等满默认超时（15s）；直接导航回首页在同一 context 内只要约 0.4s。
        - alva 首页是 SPA 聊天页，输入框里的草稿、搜索浮层、切走的 tab 这类残留，
          is_page_loaded() 未必都看得出来；整页导航一次清掉页面内状态，
          上一个用例中途失败留下的烂摊子也不会连累下一个。

        与 case-round-trip 的关系：那条 skill 反对的是用 goto「兜底」替没闭合的
        用例收场、从而丢掉对返回按钮的覆盖。这里的导航是每个用例固定的起点动作，
        不是兜底 —— 用例离开首页后仍应在末尾走真实 UI 返回并断言。

        导航只清页面内状态，cookie / localStorage 仍在 class 内延续。
        class 的第一个用例会紧接着 _session 再导航一次（约 0.4s），换来复位逻辑没有分支。
        """
        self.home_page.open(base_url)
        assert self.home_page.is_page_loaded(), "首页（起点）加载失败"
