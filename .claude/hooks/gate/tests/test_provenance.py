"""维度⑤ 证据溯源的行为契约。

核心主张只有一句：**证据必须指向真实存在的东西**。
「写了失败现象」「写了验证」这类形状检查挡不住编造，所以这里的重点用例是
「引用看起来规范但对象不存在时必须拦下」——那是自觉填写与可核验证据的分界线。
"""
import pathlib
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from gate.checkers import provenance
from gate.violation import Severity

REL = pathlib.PurePosixPath(".claude/rules/playwright/demo.md")

GOOD_SYMPTOM = "断言在 URL 仍是登录页时就通过，后续按 URL 的断言随机失败，连续 3 次复现"


def clause(symptom=GOOD_SYMPTOM, verify="tests/test_demo.py::TestDemo::test_ok",
           trigger="在登录页做断言时", title="P9.1 · 示例条款"):
    parts = [f"## {title}", ""]
    if trigger is not None:
        parts.append(f"**触发**：{trigger}")
    if symptom is not None:
        parts.append(f"**失败现象**：{symptom}")
    if verify is not None:
        parts.append(f"**验证**：{verify}")
    parts += ["", "❌ 错误写法", "✅ 正确写法", ""]
    return "\n".join(parts)


class _Base(unittest.TestCase):
    """每个用例一个临时仓库，内含一个真实可被引用的测试文件。"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self._tmp.name)
        (self.root / "tests").mkdir(parents=True)
        (self.root / "tests" / "test_demo.py").write_text(
            "class TestDemo:\n    def test_ok(self):\n        pass\n", encoding="utf-8")
        (self.root / ".claude/rules/playwright").mkdir(parents=True)
        # 默认空基线：不 patch 的话会读到仓库真实的 baseline.json
        self._p = mock.patch.object(provenance, "_load_baseline", return_value=set())
        self._p.start()
        self.addCleanup(self._p.stop)
        self.addCleanup(self._tmp.cleanup)

    def codes(self, text):
        return [v.code for v in provenance.check(REL, text, self.root)]

    def check(self, text, audit=False):
        return provenance.check(REL, text, self.root, audit=audit)


class TestEvidenceRequired(_Base):
    def test_missing_symptom_blocks(self):
        self.assertIn("PRV001", self.codes(clause(symptom=None)))

    def test_missing_verify_blocks(self):
        self.assertIn("PRV002", self.codes(clause(verify=None)))

    def test_complete_evidence_passes(self):
        self.assertEqual(self.check(clause()), [])

    def test_all_violations_are_block(self):
        for v in self.check(clause(symptom=None, verify=None)):
            self.assertEqual(v.severity, Severity.BLOCK)


class TestFillerRejected(_Base):
    def test_filler_symptom_blocks(self):
        for word in ("无", "待补", "TBD", "N/A", "视情况", "暂无"):
            with self.subTest(word=word):
                self.assertIn("PRV003", self.codes(clause(symptom=word)))

    def test_too_short_symptom_blocks(self):
        self.assertIn("PRV003", self.codes(clause(symptom="会报错")))

    def test_filler_trigger_blocks(self):
        self.assertIn("PRV003", self.codes(clause(trigger="视情况")))

    def test_prose_without_reference_blocks(self):
        # 「已验证过」是典型的不可核对说法
        codes = self.codes(clause(verify="已验证过，跑通了"))
        self.assertIn("PRV002", codes)


class TestReferenceMustExist(_Base):
    """本维度存在的唯一理由：编造的引用必须被拆穿。"""

    def test_fabricated_test_name_blocks(self):
        codes = self.codes(clause(verify="tests/test_demo.py::TestDemo::test_nope"))
        self.assertIn("PRV004", codes)

    def test_fabricated_class_name_blocks(self):
        codes = self.codes(clause(verify="tests/test_demo.py::TestNope::test_ok"))
        self.assertIn("PRV004", codes)

    def test_missing_file_blocks(self):
        codes = self.codes(clause(verify="tests/test_ghost.py::TestDemo::test_ok"))
        self.assertIn("PRV004", codes)

    def test_two_segment_nodeid_supported(self):
        (self.root / "tests" / "test_plain.py").write_text(
            "def test_plain():\n    pass\n", encoding="utf-8")
        self.assertEqual(self.check(clause(verify="tests/test_plain.py::test_plain")), [])

    def test_line_reference_beyond_eof_blocks(self):
        codes = self.codes(clause(verify="tests/test_demo.py:999"))
        self.assertIn("PRV004", codes)

    def test_valid_line_reference_passes(self):
        self.assertEqual(self.check(clause(verify="tests/test_demo.py:2")), [])

    def test_fabricated_commit_blocks(self):
        # 临时目录不是 git 仓库 → git cat-file 非 0 → 判为不存在
        codes = self.codes(clause(verify="修复见 commit deadbee"))
        self.assertIn("PRV004", codes)

    def test_unparsable_source_fails_open(self):
        (self.root / "tests" / "test_broken.py").write_text("def (((\n", encoding="utf-8")
        # 语法错误时不猜、不误拦
        self.assertEqual(self.check(clause(verify="tests/test_broken.py::TestX::test_y")), [])


class TestBaselineGrandfathering(_Base):
    def test_baselined_clause_is_exempt(self):
        text = clause(symptom=None, verify=None)
        fp = provenance.clause_fingerprint(str(REL), "P9.1 · 示例条款")
        with mock.patch.object(provenance, "_load_baseline", return_value={fp}):
            self.assertEqual(provenance.check(REL, text, self.root), [])

    def test_retitled_clause_loses_exemption(self):
        fp = provenance.clause_fingerprint(str(REL), "P9.1 · 示例条款")
        text = clause(symptom=None, verify=None, title="P9.1 · 改了名的条款")
        with mock.patch.object(provenance, "_load_baseline", return_value={fp}):
            self.assertIn("PRV001", [v.code for v in provenance.check(REL, text, self.root)])

    def test_fingerprint_ignores_emoji_and_level_renumbering(self):
        a = provenance.clause_fingerprint(str(REL), "P0.1 · 某条规则")
        b = provenance.clause_fingerprint(str(REL), "🔴 P0.7 · 某条规则")
        self.assertEqual(a, b)

    def test_fingerprint_differs_across_files(self):
        other = pathlib.PurePosixPath(".claude/rules/playwright/other.md")
        self.assertNotEqual(
            provenance.clause_fingerprint(str(REL), "同名条款"),
            provenance.clause_fingerprint(str(other), "同名条款"))


class TestClauseDetection(_Base):
    def test_table_rows_do_not_make_a_clause(self):
        # 「违规码速查」这类说明表的单元格里天然有 ❌ / ✅，不得被判成规则条款
        text = "## 违规码速查\n\n| 码 | 含义 |\n|---|---|\n| STR003 | 缺 ❌ 反例或 ✅ 正例 |\n"
        self.assertEqual(self.check(text), [])

    def test_section_with_real_examples_is_a_clause(self):
        text = "## 某个没有 P 级编号的规则\n\n❌ 错的\n\n✅ 对的\n"
        self.assertIn("PRV001", [v.code for v in provenance.check(REL, text, self.root)])

    def test_index_files_are_exempt(self):
        idx = pathlib.PurePosixPath(".claude/rules/playwright/playwright-overview.md")
        text = "## 子规则索引\n\n❌ a\n✅ b\n"
        self.assertEqual(provenance.check(idx, text, self.root), [])

    def test_non_rule_kinds_ignored(self):
        for rel in (pathlib.PurePosixPath("docs/x.md"),
                    pathlib.PurePosixPath(".claude/skills/demo/SKILL.md")):
            with self.subTest(rel=rel):
                self.assertEqual(provenance.check(rel, clause(symptom=None), self.root), [])


class TestStaleEvidence(_Base):
    def test_broken_reference_in_baselined_clause_warns_on_audit(self):
        """存量豁免的是「补证据」，不豁免「证据后来烂掉了」。"""
        fp = provenance.clause_fingerprint(str(REL), "P9.1 · 示例条款")
        text = clause(verify="tests/test_demo.py::TestDemo::test_deleted")
        with mock.patch.object(provenance, "_load_baseline", return_value={fp}):
            vs = provenance.check(REL, text, self.root, audit=True)
        self.assertEqual([v.code for v in vs], ["PRV005"])
        self.assertEqual(vs[0].severity, Severity.WARN)

    def test_stale_check_is_audit_only(self):
        fp = provenance.clause_fingerprint(str(REL), "P9.1 · 示例条款")
        text = clause(verify="tests/test_demo.py::TestDemo::test_deleted")
        with mock.patch.object(provenance, "_load_baseline", return_value={fp}):
            self.assertEqual(provenance.check(REL, text, self.root, audit=False), [])


class TestOrphanDetection(_Base):
    def _write(self, rel, text):
        p = self.root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
        return p

    def test_no_entry_file_means_no_orphan_check(self):
        """没有 CLAUDE.md 的仓库里，引用关系的起点都不存在，判孤儿纯属噪声。"""
        self._write(".claude/rules/playwright/lonely.md", "# 没人引用我\n")
        self.assertEqual(provenance.check_orphans(self.root), [])

    def test_rule_with_paths_is_not_orphan(self):
        self._write("CLAUDE.md", "# 入口\n")
        self._write(".claude/rules/playwright/auto.md",
                    '---\npaths:\n  - "framework/**"\n---\n\n# X\n')
        self.assertEqual(provenance.check_orphans(self.root), [])

    def test_unlinked_rule_without_paths_is_orphan(self):
        self._write("CLAUDE.md", "# 入口\n")
        self._write(".claude/rules/playwright/lonely.md", "# 没人引用我\n")
        codes = [v.code for v in provenance.check_orphans(self.root)]
        self.assertIn("PRV006", codes)

    def test_linked_rule_is_not_orphan(self):
        self._write(".claude/rules/playwright/linked.md", "# 被引用\n")
        self._write("CLAUDE.md", "见 [规则](./.claude/rules/playwright/linked.md)\n")
        self.assertEqual(provenance.check_orphans(self.root), [])

    def test_orphan_is_warn_never_block(self):
        self._write("CLAUDE.md", "# 入口\n")
        self._write(".claude/rules/playwright/lonely.md", "# 没人引用我\n")
        for v in provenance.check_orphans(self.root):
            self.assertEqual(v.severity, Severity.WARN)


if __name__ == "__main__":
    unittest.main()
