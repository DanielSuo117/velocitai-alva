import json
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from gate import runner


def codes(vs):
    return sorted(v.code for v in vs)


class TestRunWrite(unittest.TestCase):
    def setUp(self):
        self.root = pathlib.Path(tempfile.mkdtemp())
        (self.root / ".git").mkdir()
        (self.root / ".claude" / "skills" / "demo").mkdir(parents=True)
        (self.root / ".claude" / "rules").mkdir(parents=True)

    def _payload(self, tool, path, **ti):
        ti["file_path"] = str(self.root / path)
        return {"tool_name": tool, "tool_input": ti, "cwd": str(self.root)}

    def test_irrelevant_file_skipped(self):
        p = self._payload("Write", "pages/base_page.py", content="x = 1")
        self.assertEqual(codes(runner.run_write(p)), [])

    def test_non_edit_tool_skipped(self):
        p = self._payload("Bash", ".claude/skills/demo/SKILL.md", content="x")
        self.assertEqual(codes(runner.run_write(p)), [])

    def test_old_layout_write_skipped(self):
        # 迁移前的顶层 skills/ 已不是 harness 位置，闸门不再介入
        p = self._payload("Write", "skills/demo/SKILL.md", content="x")
        self.assertEqual(codes(runner.run_write(p)), [])

    def test_existing_skill_bad_name_blocks(self):
        target = self.root / ".claude" / "skills" / "demo" / "SKILL.md"
        target.write_text("---\nname: demo\ndescription: d\n---\n", encoding="utf-8")
        p = self._payload("Write", ".claude/skills/demo/SKILL.md",
                          content="---\nname: other\ndescription: d\n---\n")
        self.assertEqual(codes(runner.run_write(p)), ["STR002"])

    def test_new_rule_with_paths_frontmatter_only_asks(self):
        # 带 `paths:` frontmatter 的新规则：只应得到 EVI001 提案确认，不得误报结构问题
        p = self._payload("Write", ".claude/rules/new-rule.md",
                          content='---\npaths:\n  - "framework/**"\n---\n\n'
                                  "## 🔴 P0.1 · 规则\n\n**触发**：x\n\n❌ 反例\n✅ 正例\n")
        self.assertEqual(codes(runner.run_write(p)), ["EVI001"])

    def test_new_skill_triggers_ask(self):
        p = self._payload("Write", ".claude/skills/demo/SKILL.md",
                          content="---\nname: demo\ndescription: d\n---\n")
        self.assertIn("EVI001", codes(runner.run_write(p)))

    def test_existing_skill_no_ask(self):
        target = self.root / ".claude" / "skills" / "demo" / "SKILL.md"
        target.write_text("---\nname: demo\ndescription: d\n---\n", encoding="utf-8")
        p = self._payload("Write", ".claude/skills/demo/SKILL.md",
                          content="---\nname: demo\ndescription: d\n---\n新增一行\n")
        self.assertNotIn("EVI001", codes(runner.run_write(p)))

    def test_edit_rebuilds_full_text(self):
        target = self.root / ".claude" / "rules" / "r.md"
        target.write_text("❌ 反例\n✅ 正例\n旧内容\n", encoding="utf-8")
        p = self._payload("Edit", ".claude/rules/r.md", old_string="旧内容", new_string="新内容")
        # 重建后仍含 ❌ 与 ✅ → 不应报 STR003
        self.assertNotIn("STR003", codes(runner.run_write(p)))

    def test_edit_removing_examples_blocks(self):
        target = self.root / ".claude" / "rules" / "r.md"
        target.write_text("❌ 反例\n✅ 正例\n", encoding="utf-8")
        p = self._payload("Edit", ".claude/rules/r.md", old_string="❌ 反例\n", new_string="")
        self.assertIn("STR003", codes(runner.run_write(p)))

    def test_edit_replace_all_strips_every_counter_example(self):
        # replace_all 的编辑把文件里每一处 ❌ 都删掉 —— 只模拟第一处的话，重建出来
        # 的全文里仍留着第二处 ❌，STR003 不触发，坏内容在主执行路径上被静默放行。
        target = self.root / ".claude" / "rules" / "r.md"
        target.write_text("❌ 反例一\n✅ 正例\n❌ 反例二\n", encoding="utf-8")
        p = self._payload("Edit", ".claude/rules/r.md",
                          old_string="❌", new_string="", replace_all=True)
        self.assertIn("STR003", codes(runner.run_write(p)))

    def test_edit_without_replace_all_only_replaces_first(self):
        # 反方向：同样的编辑没带 replace_all，只替换第一处，文件里仍留有 ❌ →
        # 不得误报 STR003
        target = self.root / ".claude" / "rules" / "r.md"
        target.write_text("❌ 反例一\n✅ 正例\n❌ 反例二\n", encoding="utf-8")
        p = self._payload("Edit", ".claude/rules/r.md", old_string="❌", new_string="")
        self.assertNotIn("STR003", codes(runner.run_write(p)))

    def test_edit_replace_all_false_is_not_truthy(self):
        target = self.root / ".claude" / "rules" / "r.md"
        target.write_text("❌ 反例一\n✅ 正例\n❌ 反例二\n", encoding="utf-8")
        p = self._payload("Edit", ".claude/rules/r.md",
                          old_string="❌", new_string="", replace_all=False)
        self.assertNotIn("STR003", codes(runner.run_write(p)))

    def test_edit_inserting_url_into_rule_blocks(self):
        # 回放过的真实漏网场景：往已有规则里 Edit 进一个真实站点 URL，曾被静默放行
        target = self.root / ".claude" / "rules" / "r.md"
        target.write_text("❌ 反例\n✅ 正例\n旧内容\n", encoding="utf-8")
        p = self._payload("Edit", ".claude/rules/r.md", old_string="旧内容",
                          new_string='page.goto("https://portal.acme-internal.net/")')
        self.assertEqual(codes(runner.run_write(p)), ["GEN001"])

    def test_clean_edit_of_rule_passes(self):
        target = self.root / ".claude" / "rules" / "r.md"
        target.write_text("❌ 反例\n✅ 正例\n旧内容\n", encoding="utf-8")
        p = self._payload("Edit", ".claude/rules/r.md", old_string="旧内容",
                          new_string='page.goto(f"{base_url}/")   # 地址来自配置')
        self.assertEqual(codes(runner.run_write(p)), [])

    def test_edit_with_unmatched_old_string_fails_open(self):
        target = self.root / ".claude" / "rules" / "r.md"
        target.write_text("✅ 只有正例\n", encoding="utf-8")
        p = self._payload("Edit", ".claude/rules/r.md", old_string="不存在的串", new_string="x")
        self.assertEqual(codes(runner.run_write(p)), [])

    def test_malformed_payload_fails_open(self):
        self.assertEqual(codes(runner.run_write({})), [])


@unittest.skipUnless(shutil.which("git"), "本机未安装 git，跳过 run_commit 测试")
class TestRunCommit(unittest.TestCase):
    """run_commit 依据真实的 git 暂存区（index）决定校验范围，此处不做 mock，
    直接跑真实 git —— 这正是 REG001 是否在正确时机触发的关键。"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self._tmp.name)
        subprocess.run(["git", "init", "-q"], cwd=self.root, check=True, capture_output=True)
        (self.root / ".claude" / "skills").mkdir(parents=True)
        (self.root / ".claude" / "rules").mkdir(parents=True)
        (self.root / "CLAUDE.md").write_text("# 路由表\n", encoding="utf-8")

    def tearDown(self):
        self._tmp.cleanup()

    def _stage(self, *rels):
        subprocess.run(
            ["git", "-C", str(self.root), "add", *rels],
            check=True, capture_output=True,
        )

    def test_staged_new_skill_triggers_reg001(self):
        # 新建未注册的 skill 且已 git add → 暂存集合触达 .claude/skills/，check_repo 应当运行
        skill_dir = self.root / ".claude" / "skills" / "demo"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            "---\nname: demo\ndescription: d\n---\n", encoding="utf-8")
        self._stage(".claude/skills/demo/SKILL.md")
        vs = runner.run_commit(self.root)
        self.assertIn("REG001", codes(vs))

    def test_unstaged_skill_does_not_trigger_reg001(self):
        # 未注册的 skill 存在于工作区，但没有被 git add；只暂存了一个无关的 rules/ 改动
        skill_dir = self.root / ".claude" / "skills" / "demo"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            "---\nname: demo\ndescription: d\n---\n", encoding="utf-8")
        (self.root / ".claude" / "rules" / "r.md").write_text("❌ 反例\n✅ 正例\n", encoding="utf-8")
        self._stage(".claude/rules/r.md")
        vs = runner.run_commit(self.root)
        self.assertNotIn("REG001", codes(vs))

    def test_staged_content_violation_reported(self):
        (self.root / ".claude" / "rules" / "r.md").write_text("✅ 只有正例\n", encoding="utf-8")
        self._stage(".claude/rules/r.md")
        vs = runner.run_commit(self.root)
        self.assertIn("STR003", codes(vs))

    def test_staged_rule_with_url_reported(self):
        (self.root / ".claude" / "rules" / "r.md").write_text(
            "❌ 反例\n✅ 正例\n见 https://portal.acme-internal.net/\n", encoding="utf-8")
        self._stage(".claude/rules/r.md")
        self.assertEqual(codes(runner.run_commit(self.root)), ["GEN001"])

    def test_empty_staged_set_returns_empty(self):
        vs = runner.run_commit(self.root)
        self.assertEqual(codes(vs), [])

    def test_staged_path_missing_on_disk_does_not_raise(self):
        target = self.root / ".claude" / "rules" / "r.md"
        target.write_text("❌ 反例\n✅ 正例\n", encoding="utf-8")
        self._stage(".claude/rules/r.md")
        target.unlink()  # 暂存区里仍记录该文件，但工作区文件已被删掉
        vs = runner.run_commit(self.root)  # 不应抛异常
        self.assertEqual(codes(vs), [])

    def test_bad_blob_staged_then_fixed_in_worktree_is_still_caught(self):
        """要提交进去的是 index 里的 blob，不是工作区里的文件。

        暂存坏版本 → 工作区改好 → commit，读工作区就会放行，坏 blob 照样落库。
        """
        target = self.root / ".claude" / "rules" / "r.md"
        target.write_text("✅ 只有正例\n", encoding="utf-8")
        self._stage(".claude/rules/r.md")
        target.write_text("❌ 反例\n✅ 正例\n", encoding="utf-8")  # 只改了工作区，没重新 add
        self.assertIn("STR003", codes(runner.run_commit(self.root)))

    def test_good_blob_staged_with_broken_worktree_is_not_blocked(self):
        # 反方向：暂存的是好版本，工作区正写到一半 —— 不得凭空 BLOCK
        target = self.root / ".claude" / "rules" / "r.md"
        target.write_text("❌ 反例\n✅ 正例\n", encoding="utf-8")
        self._stage(".claude/rules/r.md")
        target.write_text("✅ 写到一半\n", encoding="utf-8")
        self.assertNotIn("STR003", codes(runner.run_commit(self.root)))

    def test_staged_deletion_is_skipped(self):
        # 文件从 index 里删掉后 `git show :<path>` 会失败 —— 必须跳过而非抛异常
        target = self.root / ".claude" / "rules" / "r.md"
        target.write_text("✅ 只有正例\n", encoding="utf-8")
        self._stage(".claude/rules/r.md")
        subprocess.run(["git", "-C", str(self.root), "rm", "-q", "--cached", ".claude/rules/r.md"],
                       check=True, capture_output=True)
        self.assertEqual(codes(runner.run_commit(self.root)), [])


class TestRunAudit(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self._tmp.name)
        (self.root / ".claude" / "rules").mkdir(parents=True)

    def tearDown(self):
        self._tmp.cleanup()

    def test_violating_file_reported_clean_file_not(self):
        (self.root / ".claude" / "rules" / "clean.md").write_text("❌ 反例\n✅ 正例\n", encoding="utf-8")
        (self.root / ".claude" / "rules" / "bad.md").write_text("✅ 只有正例\n", encoding="utf-8")
        vs = runner.run_audit(self.root)
        bad_codes = [v.code for v in vs if v.path == ".claude/rules/bad.md"]
        clean_codes = [v.code for v in vs if v.path == ".claude/rules/clean.md"]
        self.assertIn("STR003", bad_codes)
        self.assertEqual(clean_codes, [])

    def test_none_root_returns_empty(self):
        self.assertEqual(runner.run_audit(None), [])

    def test_rule_with_url_reported(self):
        (self.root / ".claude" / "rules" / "bad.md").write_text(
            "❌ 反例\n✅ 正例\n见 https://portal.acme-internal.net/\n", encoding="utf-8")
        vs = runner.run_audit(self.root)
        self.assertEqual([(v.code, v.path) for v in vs], [("GEN001", ".claude/rules/bad.md")])

    def test_scans_new_layout_and_ignores_old(self):
        # 同样的坏 skill 放在新旧两处：只有 .claude/skills/ 下那份应被扫到
        bad = "# 没有 frontmatter\n"
        for base in (self.root / ".claude" / "skills" / "demo", self.root / "skills" / "demo"):
            base.mkdir(parents=True)
            (base / "SKILL.md").write_text(bad, encoding="utf-8")
        paths = {v.path for v in runner.run_audit(self.root) if v.code == "STR001"}
        self.assertEqual(paths, {".claude/skills/demo/SKILL.md"})


if __name__ == "__main__":
    unittest.main()
