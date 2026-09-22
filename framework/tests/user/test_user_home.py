# 文件用途：登录用户首页冒烟 —— 带登录态打开首页，确认页面加载且处于已登录状态
"""登录用户首页冒烟。

登录态文件（.auth/prod_user.json）不存在时，整组用例由 user_class_page 统一 skip，
并提示生成命令；文件在但会话过期，则由 UserBaseTest 在 class 开始时直接 fail。
"""
import allure
import pytest

from tests.user.user_base_test import UserBaseTest


@pytest.mark.smoke
@allure.feature("登录用户首页")
class TestUserHome(UserBaseTest):

    @allure.story("登录态首页加载且处于已登录状态")
    def test_home_loaded_logged_in(self):
        home = self.user_home
        with allure.step("验证首页起点状态"):
            assert home.is_page_loaded(), "登录态首页加载失败：标题 / Agent tab 栏 / Chat 选中态 / 输入框 有缺失"
        with allure.step("验证已登录（侧边栏不再展示「Log in」）"):
            # 基类每个 class 已校验过一次；用例里再断言，让「已登录」在报告里有独立的回归记录
            assert home.is_logged_in(), "首页仍显示「Log in」按钮，登录态未生效"
