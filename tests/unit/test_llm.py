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
        for name in ("ANTHROPIC_API_KEY", "SELF_HEAL_MODEL", "ANTHROPIC_BASE_URL"):
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


class TestBaseUrl(_Isolated):
    """API 根地址与 key / 模型共用同一套优先级。"""

    def test_configured_value_used(self):
        self.use_settings(ANTHROPIC_BASE_URL=" https://proxy.example/anthropic ")
        self.assertEqual(llm.base_url(), "https://proxy.example/anthropic")

    def test_empty_falls_back_to_official(self):
        for blank in ("", "   ", None):
            with self.subTest(blank=blank):
                self.use_settings(ANTHROPIC_BASE_URL=blank)
                self.assertEqual(llm.base_url(), llm.DEFAULT_BASE_URL)

    def test_old_settings_without_the_item_falls_back(self):
        self.use_settings(ANTHROPIC_API_KEY="")     # 旧配置文件没有 ANTHROPIC_BASE_URL
        self.assertEqual(llm.base_url(), llm.DEFAULT_BASE_URL)

    def test_missing_settings_file_falls_back(self):
        self.enterContext(mock.patch.dict(sys.modules, {"config.settings": None}))
        self.assertEqual(llm.base_url(), llm.DEFAULT_BASE_URL)

    def test_env_overrides_settings(self):
        self.use_settings(ANTHROPIC_BASE_URL="https://from-settings.example")
        os.environ["ANTHROPIC_BASE_URL"] = "https://from-env.example"
        self.assertEqual(llm.base_url(), "https://from-env.example")

    def test_settings_key_never_leaks_through_a_stubbed_module(self):
        # 顶替掉 config.settings 后必须读不到本机真实配置里的 key
        self.use_settings()
        self.assertEqual(llm.api_key(), "")


class TestApiUrl(_Isolated):
    """代理/中转给出的地址三种写法都得能用 —— 填法不符就是 404，而 404 被静默吞掉。"""

    def test_three_accepted_forms_resolve_to_the_same_endpoint(self):
        want = "https://h.example/anthropic/v1/messages"
        for given in ("https://h.example/anthropic",
                      "https://h.example/anthropic/",
                      "https://h.example/anthropic/v1",
                      "https://h.example/anthropic/v1/messages"):
            with self.subTest(given=given):
                self.use_settings(ANTHROPIC_BASE_URL=given)
                self.assertEqual(llm.api_url(), want)

    def test_default_is_official_messages_endpoint(self):
        self.assertEqual(llm.api_url(),
                         llm.DEFAULT_BASE_URL + llm.MESSAGES_PATH)


class TestTruncationIsNotSilent(_Isolated):
    """被 max_tokens 截断是配置问题，每次都会复发，不能和「模型交白卷」混为一谈。"""

    def test_truncated_response_warns(self):
        payload = {"stop_reason": "max_tokens", "content": [{"type": "thinking"}],
                   "usage": {"output_tokens": 1024}}
        with self.assertLogs("velocitai.healing", level="WARNING") as cm:
            llm._warn_if_truncated(payload)
        self.assertIn("max_tokens", cm.output[0])

    def test_model_declining_does_not_warn(self):
        payload = {"stop_reason": "end_turn",
                   "content": [{"type": "text", "text": '{"candidates":[]}'}]}
        with mock.patch.object(llm.log, "warning") as w:
            llm._warn_if_truncated(payload)
        w.assert_not_called()

    def test_infer_sends_the_configured_budget(self):
        os.environ["ANTHROPIC_API_KEY"] = "dummy-key-for-tests"
        reply = {"content": [{"type": "text", "text": '{"candidates":[{"selector":"#a"}]}'}]}
        urlopen = self.enterContext(mock.patch.object(
            llm.urllib.request, "urlopen",
            side_effect=lambda req, timeout=None: io.BytesIO(json.dumps(reply).encode("utf-8"))))
        llm.infer(INTENT, ELS)
        sent = json.loads(urlopen.call_args.args[0].data.decode("utf-8"))
        self.assertEqual(sent["max_tokens"], llm.MAX_TOKENS)


class TestPickAttrs(unittest.TestCase):
    """属性挑选 —— 旧版固定白名单丢掉自定义 data-*，是模型交白卷的直接原因。"""

    def test_all_data_attrs_survive_not_just_the_known_ones(self):
        got = llm._pick_attrs({"data-name": "main-login", "data-track": "cta", "class": "x"})
        self.assertEqual(got, {"data-name": "main-login", "data-track": "cta"})

    def test_known_anchors_come_first(self):
        # 位次决定被 MAX_ATTRS 截断时谁先出局；testid 类最稳定，必须最先保住
        attrs = {f"data-x{i}": str(i) for i in range(12)}
        attrs["data-testid"] = "keep-me"
        got = llm._pick_attrs(attrs)
        self.assertEqual(next(iter(got)), "data-testid")
        self.assertEqual(len(got), llm.MAX_ATTRS)

    def test_long_values_are_truncated(self):
        got = llm._pick_attrs({"data-blob": "x" * 500})
        self.assertEqual(len(got["data-blob"]), llm.MAX_ATTR_LEN)

    def test_class_is_not_taken_here(self):
        # class 另有 item["class"] 承载（且只取前 4 个），在这里重复会挤掉真锚点
        self.assertEqual(llm._pick_attrs({"class": "a b c"}), {})

    def test_empty_values_skipped(self):
        self.assertEqual(llm._pick_attrs({"id": "", "data-x": None}), {})


class TestCompactCarriesScope(unittest.TestCase):
    """scope 是「两个元素其余字段全同」时唯一的区分线索，不能在压缩这步丢掉。"""

    def test_scope_is_forwarded(self):
        got = llm._compact([{"tag": "button", "attrs": {}, "scope": "main"}])
        self.assertEqual(got[0]["scope"], "main")

    def test_absent_scope_adds_no_key(self):
        got = llm._compact([{"tag": "button", "attrs": {}, "scope": None}])
        self.assertNotIn("scope", got[0])

    def test_prompt_explains_scope(self):
        # 采回来却不告诉模型它是什么，等于没采
        prompt = llm.build_prompt(INTENT, [{"tag": "button", "attrs": {}, "scope": "main"}], [])
        self.assertIn("scope", prompt)
        self.assertIn("最内层容器", prompt)


if __name__ == "__main__":
    unittest.main()
