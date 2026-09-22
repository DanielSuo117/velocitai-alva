# alva.ai UI 回归 — 项目地图

> 基于 VelocitAI 的 alva.ai UI 自动化回归项目：Python + Playwright + pytest POM 框架（`framework/`）+ Claude Code 项目级 harness（`.claude/`）。本文件是唯一入口。

---

## 项目速览

| 项 | 现状 |
|----|------|
| 目标站点 | https://alva.ai（AI 投资助手 SPA） |
| 环境 | 只有 `prod`（生产），没有预发 |
| 角色 | 当前版本不区分角色：所有用例以同一登录账号运行，统一继承 `tests/base_test.py::AlvaBaseTest`（凭 token 免登：注入 `authorization` cookie 后访问 `/login` 直接进入首页） |
| 登录 token | 来源依次为环境变量 `ALVA_TOKEN`、`.auth/prod_user.json`（不入库，绝不打印值）；`.venv/bin/python framework/tools/save_auth_state.py --env prod` 在真实 Chrome 人工登录后导出 |
| 覆盖 | 首页（含 Alva agent 对话）+ 登录页（到邮箱输入为止）：`HomePage` / `LoginPage` + 全站侧边栏组件 `SidebarNav`；2 条用例（均继承 `AlvaBaseTest`）：`tests/test_login.py` 免登（只读，smoke）、`tests/test_alva_agent_chat.py` Channels → Alva 提问并等回复（**真实发送一条消息**，slow）；其余页面未封装 |

---

## 行为边界（开工前必读）

运行测试前必须确认 `--env` 与范围（只有 `prod` 也要问）；prod 即生产，会写入数据或触发外部授权/付费的操作须用户明确同意；Git 操作需用户授权；文档与代码冲突时必须询问。

完整条款 → [agent-behavior.md](./.claude/rules/agent-behavior/agent-behavior.md)

`.claude/rules/` 下的规则由 Claude Code 自动加载：不带 `paths` 的每个会话都加载，带 `paths` 的只在处理匹配文件时加载。这里不逐条复述，路由表只列需要主动查阅的入口。

---

## 路由表

| 要做什么 | 去哪里 |
|---------|--------|
| **新建**页面对象 + 测试 | [gen-page-test](./.claude/skills/gen-page-test/) |
| **增加**已有页面的回归点 | [add-regression-point](./.claude/skills/add-regression-point/) |
| **替换**定位符 / 分析 DOM | [locator-replacer](./.claude/skills/locator-replacer/) |
| **选择器自愈** / 复核写回 | [selector-self-heal](./.claude/skills/selector-self-heal/) |
| **运行**测试 / 分析结果 | [test-runner](./.claude/skills/test-runner/) |
| **排查**测试失败 | [quick-debug](./.claude/skills/quick-debug/) |
| 设计 **is_page_loaded** | [page-load-assertion](./.claude/skills/page-load-assertion/) |
| 配置**等待策略** | [wait-strategy](./.claude/skills/wait-strategy/) |
| 配置**浏览器** viewport/超时 | [browser-config](./.claude/skills/browser-config/) |
| 用例**往返闭合** | [case-round-trip](./.claude/skills/case-round-trip/) |
| **保存验证**策略 | [save-verify-strategy](./.claude/skills/save-verify-strategy/) |
| **架构**决策 / 分层 / 新角色 | [architecture](./.claude/skills/architecture/) |
| **代码审查** / 探索 / 重构 | [code-review-graph](./.claude/skills/code-review-graph/) |
| 组合场景（多 skill 串联） | [ui-automation-harness](./.claude/skills/ui-automation-harness/) |
| **落库校验** / 沉淀闸门 | [evolution-gate](./.claude/rules/agent-behavior/evolution-gate.md) |
| **自愈边界**规则 | [self-healing-boundaries](./.claude/rules/playwright/self-healing-boundaries.md) |
| **编码规范**（命名/基类/用例） | [coding-conventions](./.claude/rules/coding-conventions/coding-conventions.md) |
| **Playwright 规则**索引 | [playwright-overview](./.claude/rules/playwright/playwright-overview.md) |
| **Performance API 隔离** | [performance-api-isolation](./.claude/rules/playwright/performance-api-isolation.md) |
| **测试报告生成策略** | [report-strategy](./.claude/rules/report-strategy/report-strategy.md) |
| PageObject 清单 | [docs/pages-catalog.md](./docs/pages-catalog.md) |
| 回归测试点 | [docs/regression-points.md](./docs/regression-points.md) |
| 项目架构落地（基础测试类 / 登录态） | [docs/architecture.md](./docs/architecture.md) |
| 环境搭建 | [docs/setup.md](./docs/setup.md) |

---

## 自我进化机制（P0 最高优先级）

**触发**：任务完成前 / 踩坑 / 用户纠正 / 同类问题复现。

| 类型 | 沉淀目标 |
|------|---------|
| 经验（How-to） | `.claude/skills/<主题>/SKILL.md` |
| 规则（Must/Must-not） | `.claude/rules/<域>/<规则>.md`（必含 ❌反例 + ✅正例） |
| 项目事实（类名/URL/清单） | `docs/<文件>.md` |

执行：先过[落库闸门](./.claude/rules/agent-behavior/evolution-gate.md)（检索去重 → 带触发条件与失败现象 → 新建文件先提案）；再 Edit 最小增量写入；回复末尾声明 `📝 已沉淀至 <file>：<摘要>`。新建 skill 必须同步在上方路由表登记，否则提交时被闸门拦下。

`.claude/skills/` 与 `.claude/rules/` 只写与项目无关的方法论，alva.ai 的 URL、文案、类名一律进 `docs/`。

---

## 命令

在项目根执行，`--env` 必须由用户确认。

```bash
# 用例在 tests/test_*.py，测试类继承 tests/base_test.py::AlvaBaseTest（凭 token 免登，需先有 token）
.venv/bin/pytest tests/test_login.py --env=prod              # 访问登录页 → 免登进入首页（只读）
.venv/bin/pytest tests/test_alva_agent_chat.py --env=prod    # Alva agent 对话：真实发送一条消息，跑前须用户同意
.venv/bin/pytest --env=prod -m "not slow"                    # 全量（含 tests/unit、tests/e2e），跳过发消息的对话用例
.venv/bin/pytest tests/test_login.py --env=prod -v -k <关键字>
HEADLESS=true .venv/bin/pytest tests/test_login.py --env=prod   # 无头（默认有头）

# 获取 / 刷新登录 token（启动真实 Chrome，人工登录后自动导出并自检）
.venv/bin/python framework/tools/save_auth_state.py --env prod

# 报告（pytest.ini 默认写入 reports/allure-results，只保留最近一次运行）
allure serve reports/allure-results

# 框架与闸门自测（不访问站点）
PYTHONPATH=framework .venv/bin/python -m unittest discover -s tests/unit -t .
python3 -m unittest discover -s .claude/hooks/gate/tests -t .claude/hooks
python3 .claude/hooks/gate_cli.py --mode audit
```

私有备忘：[CLAUDE.local.md](./CLAUDE.local.md)（不入库）。

---

## 工具与代理

- **code-review-graph MCP**：探索代码库时优先使用图谱工具，再降级到 Grep/Glob/Read。工作流方法论 → [code-review-graph skill](./.claude/skills/code-review-graph/)
- **code-reviewer 子代理**：代码审查与缺陷验证 → [code-reviewer.md](./.claude/agents/code-reviewer.md)
- **agent-browser**：DOM 探索 / 定位符采集。每次 `open` 后紧跟 `set viewport 1024 768`；并行时用 `--session <名字>` 隔离
- **落库闸门**：[.claude/settings.json](./.claude/settings.json) 的 PreToolUse hooks 在 Write/Edit 与 `git commit` 时调用 `.claude/hooks/gate_cli.py`，拦截不合规的 `.claude/skills/` `.claude/rules/` `docs/` 写入与提交
