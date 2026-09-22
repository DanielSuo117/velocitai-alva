# 文件用途：登录用户角色基类 —— class 内共享一个带登录态的 context，先校验登录态，再让每个用例从首页起点开始
"""登录用户角色基类。

alva 只提供第三方（Google / X / Telegram / Discord）与邮箱验证码登录，没有 token 直登，所以这里不做登录动作：
登录态由 framework/tools/save_auth_state.py 人工登录一次后存成 storageState，
user_class_page 用它建 context，打开页面时就已是登录状态。

两种「没登录」的处理刻意不同：
- 登录态文件不存在 → user_class_page 里 skip。新克隆的仓库、CI 上天然没有，
  整组报红只会淹没真正的回归失败。
- 文件在、但会话已过期 → 这里 fail。有文件说明使用者想跑登录用例，
  悄悄 skip 会让覆盖率静默归零，直到有人发现登录态已经坏了好几周。
"""
import pytest
from playwright.sync_api import Page

from core.base.base_test import BaseTest
from pages.home_page import HomePage


class UserBaseTest(BaseTest):
    # 由 _user_session 注入；class 内所有用例共用同一个已登录的 page
    user_page: Page
    user_home: HomePage

    @pytest.fixture(scope="class", autouse=True)
    @classmethod
    def _user_session(cls, user_class_page, base_url, request):
        # class 级 fixture 只跑一次，而每个用例都是新实例，必须挂到类上（request.cls）；
        # 写成 classmethod 理由同 GuestBaseTest._guest_session（pytest 9 弃用实例方法形式）
        request.cls.user_page = user_class_page
        request.cls.user_home = home = HomePage(user_class_page)

        # 登录态每个 class 只校验一次：已登录时要确认的是「Log in」按钮不存在，
        # 而判定「不存在」天然比判定「存在」慢（得等够一段时间才敢下结论），
        # 不适合每个用例都做一遍。
        home.open(base_url)
        # 必须先等页面渲染完再判登录态：is_logged_in() 的依据是侧边栏「Log in」按钮
        # 不可见，而页面还没渲染出来时它同样不可见 —— 顺序反过来，
        # 「没加载完」会被误判成「已登录」。
        if not home.is_page_loaded():
            pytest.fail("首页加载失败，无法校验登录态", pytrace=False)
        if not home.is_logged_in():
            pytest.fail(
                "登录态已失效（首页仍显示「Log in」按钮）。请在项目根重新执行 "
                f"`.venv/bin/python framework/tools/save_auth_state.py "
                f"--env {request.config.getoption('--env')}` 手动登录后再跑",
                pytrace=False,
            )

    @pytest.fixture(autouse=True)
    def _reset_to_home(self, _user_session, base_url):
        """每个用例开始前导航回首页并断言起点。

        为什么每次都导航而不是「不在起点才复位」、以及它和 case-round-trip 的关系，
        与 GuestBaseTest._reset_to_home 相同，见那里的说明。class 的第一个用例会
        紧接着 _user_session 再导航一次（约 0.4s），换来复位逻辑没有分支。
        """
        self.user_home.open(base_url)
        assert self.user_home.is_page_loaded(), "首页（起点）加载失败"
