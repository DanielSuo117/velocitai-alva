# 文件用途：访客（未登录）登录页只读冒烟 —— 首页左下角 Log in 进入登录页、登录方式齐全、邮箱框与提交按钮联动（绝不提交），每条用例经「Alva」Logo 往返闭合回首页
"""访客登录页只读冒烟。

封装与覆盖范围到「邮箱输入」为止。跑在生产站点上，下面这些动作一律不做：
- 点「Submit email」、在邮箱框里回车 —— 会真的往该邮箱发验证码；
- 点 Google / X / Telegram / Discord —— 跳第三方授权；
- 碰验证码输入框与 Cloudflare Turnstile —— 提交邮箱之后才出现，不在范围内。
邮箱框只填 example.com 假地址，断言完立即清空。

登录页脱离门户布局（没有侧边栏），所以每条用例都从首页经 SidebarNav.click_login() 进入，
末尾点左上角「Alva」Logo 返回并断言首页起点（.claude/skills/case-round-trip）。
"""
from urllib.parse import urlparse

import allure
import pytest

from pages.login_page import LoginPage
from tests.guest.guest_base_test import GuestBaseTest

# 只读冒烟专用的假地址：example.com 是保留域名，不会有人收到邮件；况且这里从不提交
FAKE_EMAIL = "qa-readonly@example.com"


@pytest.mark.smoke
@allure.feature("访客登录页")
class TestGuestLogin(GuestBaseTest):

    def _enter_login_page(self) -> LoginPage:
        """从首页起点点左下角「Log in」进入登录页，并断言加载。"""
        with allure.step("首页点左下角「Log in」进入登录页"):
            self.guest_home.sidebar.click_login()
            login = LoginPage(self.guest_page)
            assert login.is_page_loaded(), "登录页加载失败：标题「Your AI Investing Agent」/ 邮箱输入框 有缺失"
        return login

    def _back_to_home(self, login: LoginPage):
        """往返闭合：走登录页真实 UI（「Alva」Logo）回首页，并断言起点。"""
        with allure.step("点登录页左上角「Alva」回首页"):
            login.click_back_to_home()
            assert self.guest_home.is_page_loaded(), "从登录页点「Alva」返回后首页未回到起点状态"

    @allure.story("首页左下角 Log in 进入登录页，经「Alva」返回首页")
    def test_login_page_round_trip(self):
        login = self._enter_login_page()
        with allure.step("登录页 URL 路径为 /login"):
            path = urlparse(login.url).path
            assert path == LoginPage.PATH, f"登录页 URL 路径应为「{LoginPage.PATH}」，实际为「{path}」"
        self._back_to_home(login)

    @allure.story("登录方式齐全：Google / X / Telegram / Discord / 邮箱，条款链接可见且指向正确")
    def test_login_options_visible(self):
        login = self._enter_login_page()
        # 只校验可见，不点：四个按钮都跳第三方授权
        for name in login.LOGIN_OPTIONS:
            with allure.step(f"登录方式 [{name}] 可见"):
                assert login.is_login_option_visible(name), f"登录页缺少「{name}」登录方式"
        # 条款链接在新标签页打开，只校验可见与 href，不点开
        for name, (_, href) in login.LEGAL_LINKS.items():
            with allure.step(f"条款链接 [{name}] 可见且指向 {href}"):
                assert login.is_legal_link_visible(name), f"登录页缺少「{name}」链接"
                actual = login.get_legal_link_href(name)
                assert actual == href, f"「{name}」链接应指向「{href}」，实际为「{actual}」"
        self._back_to_home(login)

    @allure.story("邮箱框输入后提交按钮随格式启停，清空后消失（不提交）")
    def test_email_input_toggles_submit_button(self):
        login = self._enter_login_page()
        with allure.step("初始：邮箱框为空，提交按钮不渲染"):
            assert login.get_email_value() == "", "登录页邮箱框初始不为空"
            assert login.is_submit_email_absent(), "邮箱框为空时不应出现「Submit email」按钮"

        # 只 fill，不回车、不点提交 —— 这是生产站点，提交会真的发验证码
        cases = [
            (FAKE_EMAIL, "is_submit_email_enabled", "填入合法格式的邮箱后「Submit email」按钮未出现或未变为可用"),
            ("not-an-email", "is_submit_email_disabled", "填入非法格式的文字后「Submit email」按钮未出现或未处于禁用态"),
        ]
        for text, check_method, fail_msg in cases:
            with allure.step(f"输入「{text}」后校验提交按钮状态"):
                login.fill_email(text)
                assert login.get_email_value() == text, f"邮箱框内容应为「{text}」，实际为「{login.get_email_value()}」"
                assert getattr(login, check_method)(), fail_msg

        with allure.step("清空后提交按钮消失"):
            login.clear_email()
            assert login.get_email_value() == "", "清空后邮箱框仍有内容"
            assert login.is_submit_email_absent(), "清空邮箱框后「Submit email」按钮未消失"

        self._back_to_home(login)
