"""LLM 推理后端单测 —— 不发真实网络请求。

重点是失败路径：没有 key、网络挂了、模型返回垃圾，这些都必须静默退回
纯规则模式。推理层坏掉不该让任何用例失败。
"""
import io
import json
import os
import sys
import types
import unittest
from unittest import mock

from core.healing import llm
from core.healing import runtime as heal_runtime
from core.healing.engine import Intent

INTENT = Intent(constant="SUBMIT_BTN", selector="#old", description="提交订单",
                page_object="OrderPage", tag="button", role="button", name="提交订单")
ELS = [{"tag": "button", "attrs": {"data-testid": "order-submit"},
        "role": "button", "name": "确认下单", "text": "确认下单",
        "classes": ["btn", "css-1a2b3c"]}]


class TestPrompt(unittest.TestCase):
    def test_carries_intent_and_elements(self):
        p = llm.build_prompt(INTENT, ELS, ["#tried"])
        for needle in ("#old", "SUBMIT_BTN", "提交订单", "OrderPage",
                       "order-submit", "#tried"):
            self.assertIn(needle, p)

    def test_instructs_model_to_refuse_when_unsure(self):
        # 宁可交白卷也不要勉强给一个像的 —— 顶替错元素比失败更糟
        self.assertIn('{"candidates": []}', llm.build_prompt(INTENT, ELS, []))

    def test_warns_against_hash_class_names(self):
        self.assertIn("css-1a2b3c", llm.build_prompt(INTENT, ELS, []))

    def test_truncates_element_list(self):
        many = ELS * (llm.MAX_ELEMENTS + 20)
        self.assertEqual(len(llm._compact(many)), llm.MAX_ELEMENTS)


class TestParseResponse(unittest.TestCase):
    def _payload(self, text):
        return {"content": [{"type": "text", "text": text}]}

    def test_extracts_candidates_in_order(self):
        out = llm.parse_response(self._payload(
            '{"candidates":[{"selector":"#a"},{"selector":"#b"}]}'))
        self.assertEqual(out, ["#a", "#b"])

    def test_tolerates_prose_around_json(self):
        out = llm.parse_response(self._payload(
            '我认为是这个：{"candidates":[{"selector":"#a"}]} 供参考'))
        self.assertEqual(out, ["#a"])

    def test_empty_candidates_is_respected(self):
        self.assertEqual(llm.parse_response(self._payload('{"candidates":[]}')), [])

    def test_caps_at_three(self):
        many = ",".join('{"selector":"#%d"}' % i for i in range(9))
        self.assertEqual(len(llm.parse_response(self._payload(
            '{"candidates":[%s]}' % many))), 3)

    def test_garbage_returns_empty(self):
        for bad in ("我不知道", "", "{broken", '{"other":1}'):
            self.assertEqual(llm.parse_response(self._payload(bad)), [])

    def test_malformed_payload_returns_empty(self):
        for bad in ({}, {"content": "x"}, {"content": [{"type": "tool_use"}]}):
            self.assertEqual(llm.parse_response(bad), [])


class _Isolated(unittest.TestCase):
    """隔离环境变量与本地 settings.py：结论只取决于用例自己给的配置。

    settings.py 不入库、内容因人而异，单测既不能依赖它，也不该读到里面的 key；
    这里用假的 config.settings 顶替，没给的项等同于旧配置文件里缺这一项。
    """

    def setUp(self):
        self.enterContext(mock.patch.dict(os.environ))
        for name in ("ANTHROPIC_API_KEY", "SELF_HEAL_MODEL"):
            os.environ.pop(name, None)
        self.use_settings()

    def use_settings(self, **attrs):
        fake = types.ModuleType("config.settings")
        fake.__dict__.update(attrs)
        self.enterContext(mock.patch.dict(sys.modules, {"config.settings": fake}))


class TestModelName(_Isolated):
    def test_configured_value_used(self):
        self.use_settings(SELF_HEAL_MODEL=" claude-opus-5 ")
        self.assertEqual(llm.model_name(), "claude-opus-5")

    def test_empty_falls_back_to_default(self):
        for blank in ("", "   ", None):
            with self.subTest(blank=blank):
                self.use_settings(SELF_HEAL_MODEL=blank)
                self.assertEqual(llm.model_name(), llm.DEFAULT_MODEL)

    def test_old_settings_without_the_item_falls_back(self):
        self.use_settings(ANTHROPIC_API_KEY="")       # 旧配置文件没有 SELF_HEAL_MODEL
        self.assertEqual(llm.model_name(), llm.DEFAULT_MODEL)

    def test_missing_settings_file_falls_back(self):
        # 新克隆的仓库里没有 settings.py
        self.enterContext(mock.patch.dict(sys.modules, {"config.settings": None}))
        self.assertEqual(llm.model_name(), llm.DEFAULT_MODEL)

    def test_env_overrides_settings(self):
        self.use_settings(SELF_HEAL_MODEL="claude-haiku-4-5")
        os.environ["SELF_HEAL_MODEL"] = "claude-opus-5"
        self.assertEqual(llm.model_name(), "claude-opus-5")


class TestInferUsesConfiguredModel(_Isolated):
    """调用方（runtime._llm_candidate）不传 model，也要拿到配置的模型。"""

    def setUp(self):
        super().setUp()
        os.environ["ANTHROPIC_API_KEY"] = "dummy-key-for-tests"
        reply = {"content": [{"type": "text", "text": '{"candidates":[{"selector":"#a"}]}'}]}
        self.urlopen = self.enterContext(mock.patch.object(
            llm.urllib.request, "urlopen",
            side_effect=lambda req, timeout=None: io.BytesIO(json.dumps(reply).encode("utf-8"))))

    def _sent_model(self):
        req = self.urlopen.call_args.args[0]
        return json.loads(req.data.decode("utf-8"))["model"]

    def test_configured_model_is_sent(self):
        self.use_settings(SELF_HEAL_MODEL="claude-opus-5")
        self.assertEqual(llm.infer(INTENT, ELS), ["#a"])
        self.assertEqual(self._sent_model(), "claude-opus-5")

    def test_default_model_is_sent_when_unconfigured(self):
        llm.infer(INTENT, ELS)
        self.assertEqual(self._sent_model(), llm.DEFAULT_MODEL)

    def test_explicit_argument_wins(self):
        self.use_settings(SELF_HEAL_MODEL="claude-opus-5")
        llm.infer(INTENT, ELS, model="claude-haiku-4-5")
        self.assertEqual(self._sent_model(), "claude-haiku-4-5")


class _NoRulePage:
    """规则必然交白卷的假 page：快照里只有意图指纹对不上的元素。

    locator 只记账不抛 —— runtime 会吞掉验证时的异常，抛了也看不见。
    """
    url = "http://t/"

    def __init__(self):
        self.located = []

    def evaluate(self, js, arg=None):
        return ELS

    def locator(self, sel):
        self.located.append(sel)
        return mock.Mock(count=lambda: 0)


class TestNoKeyFailsSoft(_Isolated):
    """没有 key 时：不可用、不抛异常、不发任何网络请求。走真实的 api_key()，不桩它。"""

    def setUp(self):
        super().setUp()
        self.use_settings(ANTHROPIC_API_KEY="", SELF_HEAL_MODEL="")
        self.urlopen = self.enterContext(mock.patch.object(llm.urllib.request, "urlopen"))

    def test_unavailable_without_key(self):
        self.assertFalse(llm.available())

    def test_blank_key_counts_as_missing(self):
        self.use_settings(ANTHROPIC_API_KEY="   ")
        os.environ["ANTHROPIC_API_KEY"] = "  "
        self.assertFalse(llm.available())

    def test_infer_returns_empty_without_key(self):
        # 没有 key 时静默退回纯规则模式，绝不抛异常
        self.assertEqual(llm.infer(INTENT, ELS), [])

    def test_infer_makes_no_network_call_without_key(self):
        llm.infer(INTENT, ELS)
        self.urlopen.assert_not_called()

    def test_infer_returns_empty_without_elements(self):
        self.assertEqual(llm.infer(INTENT, []), [])

    def test_auto_mode_attempt_degrades_to_rules_only(self):
        # --self-heal=auto 但没有 key：规则交白卷后不调模型，按原样失败
        before = len(heal_runtime.HEALED)
        page = _NoRulePage()
        self.assertIsNone(heal_runtime.attempt(page, INTENT, use_llm=True))
        self.urlopen.assert_not_called()
        self.assertEqual(page.located, [], "没有任何候选却去页面上验证了选择器")
        self.assertEqual(len(heal_runtime.HEALED), before)


if __name__ == "__main__":
    unittest.main()
