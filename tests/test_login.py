# 文件用途：免登 —— 凭 token 访问 alva 登录页，不经过登录表单，直接进入首页
"""免登用例。

流程与用户确认的方案一致：注入 token（authorization cookie）→ 访问登录页 /login →
前端把人直接送回首页，且处于登录状态。token 注入、缺失时 skip、失效时 fail，
都由 conftest 的 auth_token 与基础测试类 AlvaBaseTest 统一处理，用例里不再重复。

跑在生产站点、用的是真实账号：本用例只访问页面、只读断言，不点击任何按钮、不输入任何内容。
"""
from urllib.parse import urlparse

import allure
import pytest

from tests.base_test import AlvaBaseTest


@pytest.mark.smoke
@allure.feature("免登")
class TestLogin(AlvaBaseTest):

    @allure.story("访问登录页免登：凭 token 直接进入首页，不经过登录表单")
    def test_login_page_skips_to_home(self, base_url):
        login, home = self.login_page, self.home_page
        with allure.step("访问登录页 /login"):
            login.open(base_url)
        with allure.step("被前端重定向回首页（URL 路径为 /，不再是 /login）"):
            # 重定向发生在 /login 的 load 之后，首页内容可能先于 URL 改写渲染出来，
            # 所以先等 URL，再看页面 —— 只看 is_page_loaded() 可能在仍停在 /login 时就通过
            assert home.wait_for_home_url(), (
                f"访问登录页后未被重定向到首页，当前 URL 路径：{urlparse(home.url).path}"
            )
        with allure.step("首页加载且为登录态"):
            assert home.is_page_loaded(), "被重定向回首页后首页加载失败：标题 / Agent tab 栏 / Chat 选中态 / 输入框 有缺失"
            assert home.is_logged_in(), "被重定向回首页后未处于登录态：侧边栏没有用户菜单，或仍显示「Log in」按钮"
        with allure.step("登录表单不可见"):
            # 页面已确认停在首页，此刻数个数即可，不必再等
            form_parts = {
                "标题「Your AI Investing Agent」": login.PAGE_HEADING,
                "邮箱输入框": login.EMAIL_INPUT,
            }
            for name, selector in form_parts.items():
                count = login.get_element_count(selector)
                assert count == 0, f"已登录访问登录页后仍渲染了登录表单的{name}（{count} 个）"
