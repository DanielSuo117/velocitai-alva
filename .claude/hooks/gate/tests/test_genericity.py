import pathlib
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from gate.checkers import genericity
from gate.violation import Severity

P = pathlib.PurePosixPath
SKILL = P(".claude/skills/demo/SKILL.md")
RULE = P(".claude/rules/playwright/demo.md")


def codes(vs):
    return sorted(v.code for v in vs)


def words(*ws):
    """构造与 _wordlist() 同形的返回值，让用例不依赖真实黑名单的内容。"""
    return tuple((w, genericity._term_pattern(w)) for w in ws)


class TestScope(unittest.TestCase):
    def test_applies_to_skills_and_rules(self):
        # rules 曾不在范围内：把真实站点 URL 写进已有规则的 Edit 被静默放行
        for rel in (SKILL, RULE, P(".claude/rules/x.md")):
            with self.subTest(rel=str(rel)):
                vs = genericity.check(rel, "见 https://intranet.corp.example/a\n")
                self.assertEqual(codes(vs), ["GEN001"])

    def test_docs_and_old_layout_not_checked(self):
        # docs/ 本来就该写项目事实；旧顶层 skills/ rules/ 已不是 harness 位置
        for rel in ("docs/setup.md", "skills/demo/SKILL.md", "rules/playwright/x.md"):
            with self.subTest(rel=rel):
                vs = genericity.check(P(rel), "见 https://intranet.corp.example/a\n")
                self.assertEqual(codes(vs), [])

    def test_skill_references_are_checked(self):
        vs = genericity.check(P(".claude/skills/demo/references/x.md"),
                              "见 https://intranet.corp.example/a\n")
        self.assertIn("GEN001", codes(vs))


class TestUrl(unittest.TestCase):
    def test_concrete_url_blocks(self):
        vs = genericity.check(SKILL, "打开 https://portal.acme-internal.net/home\n")
        self.assertIn("GEN001", codes(vs))

    def test_example_com_whitelisted(self):
        vs = genericity.check(SKILL, "打开 https://example.com/xxx\n")
        self.assertNotIn("GEN001", codes(vs))

    def test_ellipsis_placeholder_whitelisted(self):
        # 现有 gen-page-test/SKILL.md:11 的真实写法，末尾紧跟全角括号
        vs = genericity.check(SKILL, "给定页面（https://...）生成页面对象和测试\n")
        self.assertNotIn("GEN001", codes(vs))

    def test_doc_domains_whitelisted(self):
        vs = genericity.check(SKILL, "见 https://playwright.dev/docs/locators\n")
        self.assertNotIn("GEN001", codes(vs))


class TestAbsPath(unittest.TestCase):
    def test_mac_user_path_blocks(self):
        vs = genericity.check(SKILL, "打开 /Users/alice/repo/pages/x.py\n")
        self.assertIn("GEN002", codes(vs))

    def test_relative_path_passes(self):
        vs = genericity.check(SKILL, "打开 pages/base_page.py\n")
        self.assertNotIn("GEN002", codes(vs))


class TestHashClass(unittest.TestCase):
    def test_real_assignment_blocks(self):
        vs = genericity.check(SKILL, 'LOGIN_BTN = "css=.sc-bdVaJa"\n')
        self.assertIn("GEN003", codes(vs))

    def test_bad_comment_exempt(self):
        # locator-replacer/SKILL.md:71 的真实写法
        vs = genericity.check(SKILL, '# BAD: "css=.sc-bdVaJa.bVjGWg"         (styled-components 哈希)\n')
        self.assertNotIn("GEN003", codes(vs))

    def test_table_row_exempt(self):
        # locator-replacer/SKILL.md:84 的真实写法
        vs = genericity.check(SKILL, "| Emotion | 前缀 css- | `.css-1a2b3c` |\n")
        self.assertNotIn("GEN003", codes(vs))

    def test_checklist_exempt(self):
        # locator-replacer/SKILL.md:186 的真实写法
        vs = genericity.check(SKILL, "- [ ] 没有使用哈希类名（`sc-xxx`, `css-xxx`, `_module_xxx`）\n")
        self.assertNotIn("GEN003", codes(vs))

    def test_cross_mark_line_exempt(self):
        vs = genericity.check(SKILL, '❌ 反例：LOGIN = "css=.css-1a2b3c"\n')
        self.assertNotIn("GEN003", codes(vs))

    def test_python_method_name_not_flagged(self):
        # 本仓库 skills 正文里大量出现 Playwright/Python 方法调用，
        # 早期正则未要求哈希段含数字，把这些全判成了哈希类名（实测 36 处误报）
        for line in (
            'self.page.set_default_timeout(30000)',
            'assert page.is_page_loaded()',
            'page.wait_for_load_state("networkidle")',
            'count = self.get_element_count(sel)',
        ):
            with self.subTest(line=line):
                self.assertNotIn("GEN003", codes(genericity.check(SKILL, line + "\n")))

    def test_business_class_name_not_flagged(self):
        for line in ('CARD = "css=.list-card"', 'FORM = "css=.login-form"', 'NAV = "css=.main-navigation"'):
            with self.subTest(line=line):
                self.assertNotIn("GEN003", codes(genericity.check(SKILL, line + "\n")))

    def test_css_modules_hash_flagged(self):
        for line in ('X = "css=._component_1x2y3"', 'Y = "css=.header_abc123"', 'Z = "css=.module_1a2b3c"'):
            with self.subTest(line=line):
                self.assertIn("GEN003", codes(genericity.check(SKILL, line + "\n")))


class TestAbsPathPrefixesMatchSpec(unittest.TestCase):
    r"""GEN002 的前缀表必须严格等于 spec §6.2：/Users/ 、/Applications/ 、C:\ 。

    正则不锚定行首，多一个 /home/ 就会把普通的 URL 路径段判成本地绝对路径 ——
    Playwright 项目里 goto("/home/...") 是最常见的写法之一。
    """

    def test_url_path_segment_home_not_flagged(self):
        vs = genericity.check(SKILL, 'self.page.goto("/home/dashboard")\n')
        self.assertEqual(codes(vs), [])

    def test_external_home_url_not_flagged(self):
        vs = genericity.check(SKILL, "见 https://example.com/home/list\n")
        self.assertEqual(codes(vs), [])

    def test_relative_home_link_not_flagged(self):
        vs = genericity.check(SKILL, "路由 /home/settings 对应设置页\n")
        self.assertEqual(codes(vs), [])

    # ---- 真阳性方向：spec 列出的三种前缀必须照样拦下 ----
    def test_users_path_still_blocks(self):
        self.assertIn("GEN002", codes(genericity.check(SKILL, "见 /Users/alice/proj/x.py\n")))

    def test_applications_path_still_blocks(self):
        self.assertIn(
            "GEN002",
            codes(genericity.check(SKILL, "见 /Applications/Chrome.app/x\n")))

    def test_windows_path_still_blocks(self):
        self.assertIn("GEN002", codes(genericity.check(SKILL, "见 C:\\Users\\alice\\x.py\n")))


class TestTeachingLineExemptionCoversAllCodes(unittest.TestCase):
    """反例教学豁免必须统一作用于 GEN001–GEN004，不能只给 GEN003。

    本项目自己的规范要求每条规则配 ❌ 反例 —— 包括 P0.5「skill 正文不得写入项目
    专有标识」这一条本身。若只豁免 GEN003，闸门会把它自己要求人写的那个 ❌ 反例
    判成违规：闸门禁止教它存在的意义所在的那件事。
    """

    def test_counter_example_url_exempt(self):
        vs = genericity.check(SKILL, '❌ 反例：page.goto("https://portal.example-x.net/login")\n')
        self.assertEqual(codes(vs), [])

    def test_bad_comment_url_exempt(self):
        vs = genericity.check(SKILL, "# BAD: https://portal.example-x.net/login\n")
        self.assertEqual(codes(vs), [])

    def test_counter_example_abs_path_exempt(self):
        vs = genericity.check(SKILL, "❌ 不要写 /Users/alice/proj\n")
        self.assertEqual(codes(vs), [])

    def test_forbidden_marker_line_exempt(self):
        vs = genericity.check(SKILL, "禁止在 skill 里写 /Users/alice/proj\n")
        self.assertEqual(codes(vs), [])

    def test_table_row_exempt(self):
        vs = genericity.check(SKILL, "| ❌ 写死 | `https://portal.example-x.net` |\n")
        self.assertEqual(codes(vs), [])

    def test_checklist_item_exempt(self):
        vs = genericity.check(SKILL, "- [ ] 正文没有 /Users/ 开头的绝对路径\n")
        self.assertEqual(codes(vs), [])

    # ---- 真阳性方向：不带教学标记的行必须照样拦下 ----
    def test_plain_url_still_blocks(self):
        vs = genericity.check(SKILL, 'page.goto("https://portal.example-x.net/login")\n')
        self.assertIn("GEN001", codes(vs))

    def test_plain_abs_path_still_blocks(self):
        vs = genericity.check(SKILL, 'BASE = "/Users/alice/proj"\n')
        self.assertIn("GEN002", codes(vs))

    # ---- 结构前缀本身不构成教学语境：表格与标题在 skills 正文里极其常见，
    # 整体豁免会让 GEN001/GEN002 对表格内的硬编码标识符彻底失明 ----
    def test_table_row_without_marker_still_blocks(self):
        vs = genericity.check(SKILL, "| 登录页 | https://portal.example-x.net/login | 入口 |\n")
        self.assertIn("GEN001", codes(vs))

    def test_heading_without_marker_still_blocks(self):
        vs = genericity.check(SKILL, "# 部署到 https://portal.example-x.net\n")
        self.assertIn("GEN001", codes(vs))

    def test_table_row_abs_path_without_marker_still_blocks(self):
        vs = genericity.check(SKILL, "| 配置 | /Users/alice/proj/config.py |\n")
        self.assertIn("GEN002", codes(vs))

    def test_bare_prefix_mention_is_not_a_path(self):
        # 「/Users/ 开头的」是在描述规则，不是写死路径
        vs = genericity.check(SKILL, "正文不得出现 /Users/ 开头的绝对路径\n")
        self.assertEqual(codes(vs), [])

    def test_good_marked_line_is_not_a_teaching_line(self):
        # ✅ 正例里写死真 URL 依然是写死真 URL —— 豁免只认反例标记
        vs = genericity.check(SKILL, '✅ 正例：page.goto("https://portal.example-x.net")\n')
        self.assertIn("GEN001", codes(vs))


class TestRules(unittest.TestCase):
    """rules 与 skills 用同一套判据：同样只写方法论，同样要配 ❌/✅（STR003 强制）。"""

    def test_concrete_url_blocks_with_rule_label(self):
        vs = genericity.check(RULE, 'page.goto("https://portal.acme-internal.net/")\n')
        self.assertEqual(codes(vs), ["GEN001"])
        self.assertEqual(vs[0].severity, Severity.BLOCK)
        self.assertTrue(vs[0].message.startswith("rule 正文"), vs[0].message)

    def test_counterexample_line_exempt(self):
        # rules 的 ❌ 反例是强制项，闸门不能拦下它自己要求人写的反例
        for line in ('❌ 反例：page.goto("https://portal.acme-internal.net/")',
                     "# BAD: https://portal.acme-internal.net/",
                     "禁止在规则里写 /Users/alice/proj"):
            with self.subTest(line=line):
                self.assertEqual(codes(genericity.check(RULE, line + "\n")), [])

    def test_placeholders_pass(self):
        # 规则的 ✅ 正例靠占位符与白名单域名保持可写
        for line in ('page.goto(f"{base_url}/")',
                     'page.goto("<BASE_URL>/login")',
                     "✅ 正例：打开 https://example.com/login",
                     "给定页面（https://...）生成页面对象",
                     "见 https://playwright.dev/docs/locators"):
            with self.subTest(line=line):
                self.assertEqual(codes(genericity.check(RULE, line + "\n")), [])

    def test_abs_path_and_hash_class_block(self):
        self.assertEqual(codes(genericity.check(RULE, "打开 /Users/alice/repo/x.py\n")), ["GEN002"])
        self.assertEqual(codes(genericity.check(RULE, 'BTN = "css=.sc-bdVaJa"\n')), ["GEN003"])

    def test_skill_label_unchanged(self):
        vs = genericity.check(SKILL, 'page.goto("https://portal.acme-internal.net/")\n')
        self.assertEqual(codes(vs), ["GEN001"])
        self.assertTrue(vs[0].message.startswith("skill 正文"), vs[0].message)


class TestWordlist(unittest.TestCase):
    """GEN004：不区分大小写、词首不接英文字母、词尾不限；只给 WARN。"""

    def _check(self, rel, line, *ws):
        with mock.patch.object(genericity, "_wordlist", return_value=words(*ws)):
            return genericity.check(rel, line + "\n")

    def test_rule_hit_is_warn(self):
        vs = self._check(RULE, "输入框的可及名称以 Acme 开头", "acme")
        self.assertEqual(codes(vs), ["GEN004"])
        self.assertEqual(vs[0].severity, Severity.WARN)
        self.assertIn("rule 正文", vs[0].message)

    def test_skill_hit_is_warn(self):
        vs = self._check(SKILL, "登录 Acme 后台", "acme")
        self.assertEqual([(v.code, v.severity) for v in vs], [("GEN004", Severity.WARN)])

    def test_case_insensitive_and_open_suffix(self):
        for line in ("ACME_TOKEN 未设置", "见 acme.io 首页", "class AcmeBaseTest",
                     "tests/test_acme_chat.py", "代码为acme的记录"):
            with self.subTest(line=line):
                self.assertEqual(codes(self._check(RULE, line, "acme")), ["GEN004"])

    def test_letter_before_term_not_hit(self):
        # 词首卡英文字母：salvage / galvanize 里的 alva 不是产品名
        for line in ("salvage the run", "galvanize", "Salvador"):
            with self.subTest(line=line):
                self.assertEqual(codes(self._check(RULE, line, "alva")), [])

    def test_multi_word_term(self):
        self.assertEqual(codes(self._check(RULE, "名称是 Sign in Sign in", "Sign in Sign in")),
                         ["GEN004"])

    def test_teaching_lines_exempt(self):
        for line in ("| 名称 | Acme |", "## Acme 专项", "# Acme 的注释",
                     "- [ ] 正文没有 Acme", "❌ 反例：写死 Acme"):
            with self.subTest(line=line):
                self.assertEqual(codes(self._check(RULE, line, "acme")), [])

    def test_docs_not_checked(self):
        self.assertEqual(codes(self._check(P("docs/setup.md"), "Acme 首页", "acme")), [])


class TestRealWordlist(unittest.TestCase):
    """真实黑名单：必须真的有词，且不能误伤各 skill 讲方法论时用的通用 POM 名。"""

    def test_wordlist_not_empty(self):
        self.assertTrue(genericity._wordlist(), "wordlist.txt 为空，GEN004 形同虚设")

    def test_generic_pom_names_not_flagged(self):
        for line in ("home = HomePage(page)", "login = LoginPage(page)",
                     "class BasePage:", "assert page.is_page_loaded()",
                     "self.click_hydrated(self.SUBMIT_BUTTON)",
                     'page.wait_for_load_state("networkidle")'):
            with self.subTest(line=line):
                self.assertEqual(codes(genericity.check(RULE, line + "\n")), [])


if __name__ == "__main__":
    unittest.main()
