# 文件用途：访客（未登录）角色基类 —— class 内共享一个访客 context，每个用例都从首页起点开始
"""访客角色基类。

访客用例满足 class 级共享 context 的三个条件（.claude/skills/architecture 决策树）：
只在 alva.ai 一个域名内活动；前置统一（就是一个干净的、没登录的 context）；
起点统一（首页 /，随时可导航回来）。共享省掉的是每个用例新建 context、
冷启动首页的开销 —— 2026-09-22 本机实测冷启动约 2s，同一 context 内再导航约 0.4s。
"""
import pytest
from playwright.sync_api import Page

from core.base.base_test import BaseTest
from pages.home_page import HomePage


class GuestBaseTest(BaseTest):
    # 由 _guest_session 注入；class 内所有用例共用同一个 page
    guest_page: Page
    guest_home: HomePage

    @pytest.fixture(scope="class", autouse=True)
    @classmethod
    def _guest_session(cls, class_page, request):
        # class 级 fixture 只跑一次，而每个用例都是新实例：属性必须挂在类上
        # （request.cls），用例里的 self.guest_page 才读得到。写成 classmethod 是
        # pytest 9 的要求 —— 实例方法形式的 class 级 fixture 已被弃用并告警。
        request.cls.guest_page = class_page
        request.cls.guest_home = HomePage(class_page)

    @pytest.fixture(autouse=True)
    def _reset_to_home(self, _guest_session, base_url):
        """每个用例开始前把共享 page 导航回首页，并断言起点。

        为什么每次都导航，而不是 case-round-trip 里「不在起点才复位」的写法：
        - 判定「不在起点」要等 is_page_loaded() 返回 False，而它对每个缺席的
          元素都会先等满默认超时（15s）；直接导航回首页在同一 context 内只要约 0.4s。
        - alva 首页是 SPA 聊天页，输入框里的草稿、Markets 搜索浮层、切走的 tab
          这类残留，is_page_loaded() 未必都看得出来；整页导航一次清掉页面内状态，
          上一个用例中途失败留下的烂摊子也不会连累下一个。

        与 case-round-trip 的关系：那条 skill 反对的是用 goto「兜底」替没闭合的
        用例收场、从而丢掉对返回按钮的覆盖。这里的导航是每个用例固定的起点动作，
        不是兜底 —— 用例离开首页后仍应在末尾走真实 UI 返回并断言，那是对返回
        路径本身的回归，复位不替它做。

        导航只清页面内状态，cookie / localStorage 仍在 class 内延续；
        需要彻底干净环境的用例改用 function 级的 page fixture。
        """
        self.guest_home.open(base_url)
        assert self.guest_home.is_page_loaded(), "首页（起点）加载失败"
