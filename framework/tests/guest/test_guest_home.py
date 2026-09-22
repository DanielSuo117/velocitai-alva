# 文件用途：访客（未登录）首页只读冒烟 —— 首页加载、侧边栏导航、Agent 分区 tab、登录入口、建议卡片、输入框与发送按钮联动
"""访客首页只读冒烟。

跑在生产站点上，所以「只读」是硬约束，下面这些动作一律不做：
- 点发送、在输入框里回车 —— 会真的向 agent 提交一条消息；
- 点建议卡片 —— 会发起 onboarding 流程，等同于发消息；
- 点 Connect Portfolio / Connect IM —— 外部账号授权入口。

tab 切换可以做：2026-09-22 实测访客点 Agent tab 不跳页，只把 URL 改成 /?tab=<name>，
也不发起任何写操作；切回 Chat 后 URL 回到 /。

每个用例开始前 GuestBaseTest._reset_to_home 都会导航回首页并断言起点，
所以用例里不再重复打开首页。
"""
import allure
import pytest

from tests.guest.guest_base_test import GuestBaseTest


@pytest.mark.smoke
@allure.feature("访客首页")
class TestGuestHome(GuestBaseTest):

    @allure.story("首页加载：标题、Agent tab 栏、输入框与顶部操作区")
    def test_home_loaded(self):
        home = self.guest_home
        with allure.step("验证首页起点状态"):
            # 基类复位时已断言过一次；这里再断言，是让「首页加载」在报告里有一条独立的回归记录
            assert home.is_page_loaded(), "首页加载失败：标题 / Agent tab 栏 / Chat 选中态 / 输入框 有缺失"
        for name in home.HEADER_ACTIONS:
            with allure.step(f"顶部操作区 [{name}] 可见"):
                assert home.is_header_action_visible(name), f"首页顶部操作区缺少「{name}」"

    @allure.story("侧边栏导航项齐全")
    def test_sidebar_nav_items(self):
        sidebar = self.guest_home.sidebar
        assert sidebar.is_page_loaded(), "侧边栏未渲染"
        # 访客态的全量导航清单；登录态没有「Alva」项，不能照搬这份清单去断言
        for name in sidebar.NAV_ITEMS:
            with allure.step(f"导航项 [{name}] 可见"):
                assert sidebar.is_nav_item_visible(name), f"侧边栏缺少导航项「{name}」"

    @allure.story("Agent 分区 tab 齐全且可切换")
    def test_agent_tabs(self):
        home = self.guest_home
        for name in home.AGENT_TABS:
            with allure.step(f"tab [{name}] 可见"):
                assert home.is_tab_visible(name), f"Agent 分区缺少「{name}」tab"

        # Chat 是起点 tab，已在 is_page_loaded() 里校验过选中态，这里只切其余的
        for name in [n for n in home.AGENT_TABS if n != "Chat"]:
            with allure.step(f"切换到 [{name}] tab 并验证选中"):
                home.click_agent_tab(name)
                assert home.is_tab_selected(name), f"点击后「{name}」tab 未处于选中态"

        # 往返闭合：切走 tab 改变了起点状态（URL 带上 ?tab=，Chat 未选中），
        # 必须走真实 UI 切回 Chat 并断言起点，而不是交给下一个用例的复位导航去兜底
        with allure.step("切回 [Chat] tab，回到起点"):
            home.click_chat_tab()
            assert home.is_page_loaded(), "切回「Chat」tab 后首页未回到起点状态"

    @allure.story("未登录态展示登录入口")
    def test_login_entry_visible(self):
        assert self.guest_home.sidebar.is_login_button_visible(), "未登录态侧边栏未展示「Log in」登录入口"

    @allure.story("Chat 面板展示建议卡片")
    def test_suggestion_cards(self):
        home = self.guest_home
        # 卡片数量与文案属于运营配置，随时可能调整，只断言「至少一张、且每张都有标题」
        count = home.get_suggestion_count()
        assert count >= 1, "Chat 面板没有任何建议卡片"
        titles = home.get_suggestion_titles()
        assert len(titles) == count, f"有 {count} 张建议卡片，但只读到 {len(titles)} 个标题"
        for i, title in enumerate(titles, start=1):
            with allure.step(f"第 {i} 张建议卡片标题：{title}"):
                assert title, f"第 {i} 张建议卡片标题为空"

    @allure.story("输入框有内容时发送按钮可用，清空后恢复禁用（不发送）")
    def test_chat_input_toggles_send_button(self):
        home = self.guest_home
        text = "回归测试：只输入不发送"
        with allure.step("初始：输入框为空，发送按钮禁用"):
            assert home.get_chat_input_value() == "", "首页输入框初始不为空"
            assert home.is_send_disabled(), "输入框为空时发送按钮应为禁用态"
        # 只 fill，不回车、不点发送 —— 这是生产站点
        with allure.step("输入文字后发送按钮变为可用"):
            home.fill_chat_input(text)
            assert home.get_chat_input_value() == text, "输入框内容与输入的文字不一致"
            assert home.is_send_enabled(), "输入文字后发送按钮未变为可用"
        with allure.step("清空后发送按钮恢复禁用"):
            home.clear_chat_input()
            assert home.get_chat_input_value() == "", "清空后输入框仍有内容"
            assert home.is_send_disabled(), "清空输入框后发送按钮未恢复禁用"
