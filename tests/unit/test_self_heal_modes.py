"""--self-heal 四档开关对 BasePage 类属性的影响。

锁住一条底线：任何档位都不得在运行期打开写回（规则 P0.4「运行期绝不改写源码」）——
auto 相比 on 只多开模型兜底。谁要是把写回加回 conftest，这里先红。

运行：PYTHONPATH=framework python3 -m unittest discover -s tests/unit -t .
（tests/conftest.py 顶层 import pytest / playwright，还要求本地存在不入库的
  framework/config/settings.py；系统 python3 缺这些依赖时整个模块 skip，不是 ERROR。）
"""
import types
import unittest
from unittest import mock

try:
    from tests import conftest
    from core.base.base_page import BasePage
except ImportError as exc:
    raise unittest.SkipTest(
        f"导入 tests/conftest 或 BasePage 失败（缺 pytest / playwright / settings.py），"
        f"整个模块跳过：{exc}"
    ) from exc


class SelfHealModesTest(unittest.TestCase):
    """四个档位各自应打开 BasePage 的哪些开关。"""

    def _configure(self, mode):
        """以 mode 档跑一遍 conftest.pytest_configure，返回三个开关调用后的取值。

        pytest_configure 改的是 BasePage 的**类属性**，会泄漏给同进程的其他单测——
        让别的用例跑在自愈开启甚至调模型的状态下。必须用 patch.multiple 还原：
        设定值取进入前的当前值（等于不动），退出时无论中途被改成什么都恢复原值，
        含可能被 settings.py 覆盖的两个产物路径。
        """
        with mock.patch.multiple(
            BasePage,
            self_heal_enabled=BasePage.self_heal_enabled,
            self_heal_use_llm=BasePage.self_heal_use_llm,
            self_heal_patch=BasePage.self_heal_patch,
            heal_artifact=BasePage.heal_artifact,
            heal_fingerprints=BasePage.heal_fingerprints,
        ):
            conftest.pytest_configure(
                types.SimpleNamespace(getoption=lambda name: mode)
            )
            return (
                BasePage.self_heal_enabled,
                BasePage.self_heal_use_llm,
                BasePage.self_heal_patch,
            )

    def test_off_keeps_all_switches_false(self):
        enabled, use_llm, patch = self._configure("off")
        self.assertFalse(enabled, "off 档不应开启自愈（self_heal_enabled 应保持 False）")
        self.assertFalse(use_llm, "off 档不应开启模型兜底（self_heal_use_llm 应保持 False）")
        self.assertFalse(patch, "off 档不应打开写回（self_heal_patch 应保持 False）")

    def test_on_enables_healing_only(self):
        enabled, use_llm, patch = self._configure("on")
        self.assertTrue(enabled, "on 档应开启自愈（self_heal_enabled 应为 True）")
        self.assertFalse(use_llm, "on 档不应开启模型兜底（self_heal_use_llm 应保持 False）")
        self.assertFalse(patch, "on 档不应打开写回（self_heal_patch 应保持 False）")

    def test_strict_same_as_on_at_runtime(self):
        enabled, use_llm, patch = self._configure("strict")
        self.assertTrue(enabled, "strict 档应开启自愈（self_heal_enabled 应为 True）")
        self.assertFalse(use_llm, "strict 档运行期与 on 逐字相同，不应开启模型兜底")
        self.assertFalse(patch, "strict 档不应打开写回（self_heal_patch 应保持 False）")

    def test_auto_adds_llm_but_never_patch(self):
        enabled, use_llm, patch = self._configure("auto")
        self.assertTrue(enabled, "auto 档应开启自愈（self_heal_enabled 应为 True）")
        self.assertTrue(use_llm, "auto 档应开启模型兜底（self_heal_use_llm 应为 True）")
        self.assertFalse(
            patch,
            "auto 档不得打开写回：规则 P0.4，运行期绝不改写源码；"
            "写回是 selector-self-heal skill 的职责，且要经人确认与落库闸门",
        )


if __name__ == "__main__":
    unittest.main()
