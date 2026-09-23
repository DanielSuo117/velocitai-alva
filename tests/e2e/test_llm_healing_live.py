"""LLM 自愈打**真实模型**的验证 —— 一跳都不桩。

与 test_llm_healing_e2e.py 的分工：那边桩掉 Anthropic 那次 HTTP 往返，守的是
「模型给出候选后，三道闸是否照常把关」；它必须能离线跑，因此桩不能去掉。

但桩也正是它的盲区：它塞进去的候选是人写的，模型**实际上能不能推出来**从未被
验证过。2026-09-22 实测发现，v4 场景下真实模型只会交白卷 —— 因为 _compact()
当时把 data-name 和祖先结构全丢了，喂过去的两条记录逐字节相同。桩版一路绿灯，
问题藏了整整一个版本。

本文件补的就是这一段：模型是否真的具备被声称的那种判断力。

运行（需要 key，且必须显式开启 —— 它会真的花钱、真的走网络）：
    SELF_HEAL_LIVE=1 .venv/bin/pytest tests/e2e/test_llm_healing_live.py --env=prod
"""
import os
from pathlib import Path

import pytest

from core.healing import llm, runtime
from core.healing.engine import Intent

FIXTURES = Path(__file__).parent / "fixtures"


def url(name: str) -> str:
    return (FIXTURES / name).as_uri()


pytestmark = pytest.mark.skipif(
    not (os.environ.get("SELF_HEAL_LIVE") == "1" and llm.available()),
    reason="实网用例：需 SELF_HEAL_LIVE=1 且已配置 API key（见 docs/setup.md）",
)


MAIN_LOGIN = Intent(
    constant="MAIN_LOGIN_BTN", selector="#main-login",
    description="页面主区(main)里的登录按钮，不是导航栏那个",
    page_object="AmbiguousLoginPage", tag="button", role="button", name="登录",
)


def test_model_discriminates_by_scope_and_data_attrs(page):
    """规则交白卷、两个按钮仅靠 data-* 与所在容器区分时，模型要能挑对。

    这正是 LLM 那一层存在的理由。它一旦失效是静默的（候选为空与「模型认为
    没有合适元素」看起来一模一样），所以必须有用例直接盯着。
    """
    page.goto(url("v4_after.html"))
    healed = runtime.attempt(page, MAIN_LOGIN, use_llm=True)

    assert healed, "模型没能给出候选 —— 检查 _compact() 是否又把区分性信息丢了"
    page.locator(runtime.scoped(healed)).click()
    assert page.evaluate("() => window.CLICKED") == ["main-login"], \
        f"模型挑错了元素：{healed}"


def test_model_still_declines_when_truly_indistinguishable(page):
    """补了上下文不等于可以开始猜。

    与上一条是一对：上一条防「该答的答不出」，这一条防「不该答的硬答」。
    只留上一条，下次有人为了提高自愈率继续往 prompt 里加料时，就没有东西
    拦住它把机制推过界。
    """
    page.goto(url("v5_same_scope.html"))
    healed = runtime.attempt(page, MAIN_LOGIN, use_llm=True)

    assert healed is None, \
        f"两个元素连 scope 都相同，模型却给了 {healed} —— 这是在猜，会造成假通过"
    assert page.evaluate("() => window.CLICKED") == [], "不该发生任何点击"
