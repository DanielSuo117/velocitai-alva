# 文件用途：Alva agent 对话 —— 从首页经左侧 Channels 进入 Alva agent，询问 SPCX 实时行情，等待 agent 回复成功
"""Alva agent 对话用例。

注意：本用例会在生产站点真实发送一条消息（用户 2026-09-22 明确要求），每跑一次，
账号的 Alva 频道里就多一轮对话。它只发这一条提示词，不点其他会产生写入的按钮。
"""
import allure
import pytest

from tests.base_test import AlvaBaseTest

PROMPT = "查看股票代码为spcx的股票实时行情"
SYMBOL = "SPCX"


@pytest.mark.slow
@allure.feature("Alva agent 对话")
class TestAlvaAgentChat(AlvaBaseTest):

    @allure.story("Channels → Alva：询问 SPCX 实时行情，agent 回复成功")
    def test_ask_spcx_quote(self):
        home, sidebar = self.home_page, self.home_page.sidebar
        with allure.step("点击左侧 Channels"):
            assert sidebar.is_section_visible("Channels"), "左侧栏没有 Channels 分区"
            sidebar.click_channels()
        with allure.step("点击 Channels 下的 Alva，进入 Alva agent 首页"):
            sidebar.click_channel_alva()
            assert home.wait_for_home_url(), f"点击 Alva 后没有进入 Alva agent 首页，当前 URL：{home.url}"
            assert home.is_page_loaded(), "Alva agent 首页加载失败：标题 / Agent tab 栏 / Chat 选中态 / 输入框 有缺失"
            assert sidebar.is_channel_alva_active(), "Channels 下的 Alva 未处于选中态"
        with allure.step(f"在底部输入框输入「{PROMPT}」并发送"):
            turn_id = home.send_chat_message(PROMPT)
            assert turn_id, f"发送后 {home.NEW_TURN_TIMEOUT // 1000}s 内对话区没有出现这条消息"
        with allure.step("等待 Alva 回复完成"):
            assert home.wait_for_reply(turn_id), f"{home.REPLY_TIMEOUT // 1000}s 内 Alva 没有回复完成"
        with allure.step(f"回复成功：内容非空且提到 {SYMBOL}"):
            reply = home.get_reply_text(turn_id)
            allure.attach(reply, "Alva 回复", allure.attachment_type.TEXT)
            assert reply, "Alva 回复为空"
            assert SYMBOL.lower() in reply.lower(), f"Alva 回复没有提到 {SYMBOL}：{reply[:200]}"
