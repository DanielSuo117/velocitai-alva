# alva.ai UI 自动化回归

基于 [VelocitAI](https://github.com/DanielSuo117/velocitai) 搭建的 alva.ai UI 自动化回归项目。

- **被测对象**：[alva.ai](https://alva.ai)，AI 投资助手单页应用。目前只有生产环境，没有预发。
- **代码侧**：`framework/`，Python + Playwright + pytest 的 POM 框架，带选择器自愈（规则优先、模型兜底，默认关闭）。
- **harness 侧**：`CLAUDE.md` + `.claude/`（skills、rules、hooks、子代理、settings）+ `docs/`，
  全部采用 Claude Code 项目级原生格式，约束 AI 编程代理如何生成、运行、排查和沉淀测试代码。
- **当前进度**：框架骨架已搭好，封装了首页、登录页（到邮箱输入为止）页面对象与基础测试类 `AlvaBaseTest`，
  已有 2 条业务用例：凭 token 免登冒烟（只读）与 Alva agent 对话（会真实发送一条消息）。

## 目录结构

```
.
├── CLAUDE.md                    # agent 唯一入口：项目速览 + 行为边界 + 路由表 + 命令
├── README.md
├── LICENSE
├── requirements.txt
├── pytest.ini                   # testpaths=tests/test_*.py（默认只收业务用例），pythonpath=framework 与项目根，标记注册，allure 输出目录
├── tests/                       # 测试用例（放根目录，方便查看）
│   ├── conftest.py              # fixture：env / base_url / auth_state_path / auth_token / browser / page / class_page / auth_class_page
│   ├── base_test.py             # AlvaBaseTest：带 token 的共享 page + 页面对象 + 凭 token 免登 + 起点复位
│   ├── test_login.py            # 免登：访问登录页 → 直接进入首页（只读，smoke）
│   ├── test_alva_agent_chat.py  # Alva agent 对话：Channels → Alva → 发一条提示词 → 等回复（真实发送，slow）
│   ├── unit/                    # 框架单测（unittest，不开浏览器、不访问站点）
│   └── e2e/                     # 选择器自愈端到端自测（只开本地 HTML 夹具；test_llm_healing_live.py 打真实模型，默认跳过）
├── .claude/
│   ├── settings.json            # 权限 + hooks（落库闸门、code-review-graph 在这里接线）
│   ├── agents/
│   │   └── code-reviewer.md     # 代码审查子代理
│   ├── skills/<name>/SKILL.md   # 14 个 skill：操作方法论（ui-automation-harness 为组合场景路由）
│   ├── rules/<域>/<规则>.md     # 强制规则，由 Claude Code 自动或按 paths 加载
│   └── hooks/
│       ├── gate_cli.py          # 落库闸门入口（PreToolUse 调用）
│       └── gate/                # 闸门实现与自测（gate/tests/）
├── docs/                        # 项目事实：架构、环境搭建、PageObject 清单、回归点，外加自愈 / 闸门两份机制图解
├── .auth/                       # 登录 token（storageState 格式），本地生成，不入库
├── reports/                     # allure 结果与自愈产物，不入库
└── framework/                   # 框架代码
    ├── config/
    │   ├── settings.example.py  # 配置模板（入库）
    │   └── settings.py          # 本地配置，由模板复制（不入库）
    ├── core/                    # 框架核心：BasePage / BaseComponent / BaseTest、日志
    │   └── healing/             # 选择器自愈：engine（候选排序）/ interceptor（失败拦截）/ runtime（实跑验证）
    │                            #             / llm（模型兜底）/ patcher（写回源码）
    ├── pages/
    │   ├── home_page.py         # HomePage：首页
    │   ├── login_page.py        # LoginPage：登录页（到邮箱输入为止）
    │   └── components/
    │       └── sidebar_nav.py   # SidebarNav：全站左侧栏
    └── tools/
        └── save_auth_state.py   # 获取登录 token（真实 Chrome 人工登录后导出）
```

## 快速开始

在项目根执行：

```bash
# 1. 虚拟环境与依赖（Python 3.10+）
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/playwright install chromium

# 2. 本地配置（settings.py 不入库）
cp framework/config/settings.example.py framework/config/settings.py

# 3. 获取登录 token（在真实 Chrome 里人工登录一次；所有业务用例都需要它）
.venv/bin/python framework/tools/save_auth_state.py --env prod

# 4. 运行：默认有头，HEADLESS=true 切无头
HEADLESS=true .venv/bin/pytest tests/test_login.py --env=prod   # 免登冒烟，只读
.venv/bin/pytest tests/test_alva_agent_chat.py --env=prod       # Alva agent 对话，会真实发送一条消息

# 5. Allure 报告（pytest.ini 已默认把结果写到 reports/allure-results）
allure serve reports/allure-results
```

`--env` 必须显式传入，目前只有 `prod`。prod 是生产环境：除经用户明确同意的对话用例外，用例只做只读操作。
当前用例共 2 条，都继承 `AlvaBaseTest`，没有 token 时 skip：

- `test_login.py::TestLogin::test_login_page_skips_to_home`（`smoke`）：访问 `/login` 被前端送回首页、处于登录态、
  登录表单不渲染。只访问页面、只读断言。
- `test_alva_agent_chat.py::TestAlvaAgentChat::test_ask_spcx_quote`（`slow`）：点左侧 Channels 标题 → 点 Channels 内置的
  「Alva」频道 → 断言 Alva agent 首页加载且频道选中 → 发送「查看股票代码为spcx的股票实时行情」→ 等回复完成，断言回复非空且提到 SPCX。
  **会在生产站点真实发送一条消息**（用户 2026-09-22 明确要求），每跑一次账号的 Alva 频道就多一轮对话；回复实测约 30～42s。
  不想发消息时加 `-m "not slow"` 跳过。

新用例由 [gen-page-test](./.claude/skills/gen-page-test/) 或 [add-regression-point](./.claude/skills/add-regression-point/) 生成。
配置项、环境变量与排障见 [docs/setup.md](./docs/setup.md)。

## 基础测试类与登录态

当前版本不区分角色：所有用例以同一个登录账号运行，测试类统一继承 `tests/base_test.py::AlvaBaseTest`
（它继承框架的 `core.base.base_test.BaseTest`）。基类封装四件事，用例里不再重复：

- **共享 page**：每个测试类一个全新 context，只注入登录 token（fixture `auth_class_page`），class 内用例共用；
- **页面对象**：`self.page` / `self.login_page` / `self.home_page`，侧边栏经 `self.home_page.sidebar`；
- **凭 token 免登**：每个 class 走一次 `login_by_token()`；
- **起点复位**：每个用例开始前 `_reset_to_home` 导航回首页并断言起点。

用例**凭 token 免登**：alva 的登录态就是 alva.ai 域下名为 `authorization` 的 cookie。
只注入这一个 cookie 后访问登录页 `/login`，前端会直接把人送回首页，且处于登录状态，
不经过登录表单和 Cloudflare 人机验证（2026-09-22 实测）。

- **token 来源**（按优先级）：环境变量 `ALVA_TOKEN` → 本地 `.auth/prod_user.json` 中的 `authorization` cookie。
  两种来源都只注入这一个 cookie。
- **获取 token**：`save_auth_state.py` 启动本机**真实 Google Chrome**（用独立的配置目录），你在里面人工登录一次
  （邮箱验证码或 Google 都行），脚本导出到 `.auth/prod_user.json`（权限 600），再用无头浏览器自检一遍免登。
  不用 Playwright 启动的浏览器登录，是因为它过不了 Cloudflare 人机验证。
- **有效期**：cookie 在登录后约 21 天到期；服务端是否会提前失效，站点没有公开说明。
- **没有 token**：业务用例全部 skip，并提示两种提供方式。
- **token 无效或过期**：访问登录页 10s 内没被送回首页、或送回后不是登录态，`AlvaBaseTest` 以「token 无效或已过期」fail，
  并提示重新获取。
- token 等同账号凭据：只放 `.auth/`（不入库）或 CI 的 secret，全程不打印它的值。

设计取舍见 [docs/architecture.md](./docs/architecture.md)。

## 选择器自愈

前端改版把定位符改废时，用例可以在运行期自己重建定位符，而不是一路红到底。开关是 `--self-heal`，
**默认 `off`** —— 自愈会改变「失败」的含义，不能悄悄生效：

| 取值 | 行为 |
|------|------|
| `off`（默认） | 完全关闭，拦截器不实例化 |
| `on` | 定位失效时尝试重建定位符，用例继续；愈过的用例在终端汇总里被显式点名，不算干净通过 |
| `strict` | 运行期与 `on` 逐字相同，但只要发生过自愈就让会话以非零码结束，便于 CI 发现定位符漂移 |
| `auto` | 同 `on`，并在规则交白卷时让模型推理，**且把修复写回 PageObject 源码** |

`auto` 一个开关打开两件互不依赖的事：模型推理要 API key，写回源码不要 —— **没有 key 时它不报错、
不走网络，只用规则修，但照样改工作区里的源码**（原文件备份为同名 `.heal-bak`）。所以别把 `auto`
理解成「AI 模式」，它首先是「改源码模式」。

安全底线只有一条：自愈只修「定位」，绝不允许把真失败变成假通过。候选要在真实页面上实跑并过三道闸，
拿不准就放弃自愈、让用例按原样失败 —— 误报只是吵，假通过是骗。

产物写在 `reports/self-heal/`（不入库）：`proposals.jsonl` 是给人复核的提案，`fingerprints.json`
是定位符上次命中时的元素形态，也就是自愈据以判断的「旧有逻辑」。运行期修好 ≠ 已入库：写回源码要经
[selector-self-heal](./.claude/skills/selector-self-heal/) skill 复核，并同样过落库闸门。

模型兜底的三项配置都在 `framework/config/settings.py`（不入库），同名环境变量优先：`ANTHROPIC_API_KEY`
（留空即退回纯规则模式，不报错）、`ANTHROPIC_BASE_URL`（留空用官方地址，可指向自建代理）、
`SELF_HEAL_MODEL`（留空用 `llm.py::DEFAULT_MODEL`）。

```bash
# 框架自身的自测，不访问 alva.ai（pytest.ini 的 testpaths 已把它们排除在默认收集之外）
PYTHONPATH=framework .venv/bin/python -m unittest discover -s tests/unit -t .        # 自愈引擎单测，不开浏览器
.venv/bin/pytest tests/e2e --env=prod --self-heal=on --alluredir=reports/allure-e2e  # 端到端：只开本地 HTML 夹具，单独的结果目录免得清掉业务回归的报告
SELF_HEAL_LIVE=1 .venv/bin/pytest tests/e2e/test_llm_healing_live.py --env=prod      # 打真实模型：要 key、要花钱，默认跳过
```

显式传 `tests/` 时用 `-m framework` / `-m "not framework"` 把框架自测与业务用例分开跑。

机制原理图解 → [docs/self-healing-mechanism.md](docs/self-healing-mechanism.md)；
边界条款（什么能做、什么不许做）→ [self-healing-boundaries.md](.claude/rules/playwright/self-healing-boundaries.md)

## 落库闸门（hook）

`.claude/settings.json` 在三个时机调用 `.claude/hooks/gate_cli.py`：

- PreToolUse，Claude Code 执行 Write / Edit 时（`--mode write`），校验写入 `.claude/skills/` `.claude/rules/` `docs/` 的内容；
- PreToolUse，执行 `git commit` 时（`--mode commit`），校验暂存区，包括 CLAUDE.md 路由表是否登记了全部 skill、链接是否存在；
- Stop，每轮对话结束时（`--mode stop`），全仓兜底扫描，抓住用 Bash 直接写盘、绕过 Write/Edit 的改动。

前两者以退出码 2 表示拦截，理由回传给代理；Stop 那一路**只提示、永远返回 0**——那里的退出码 2 在宿主协议里
意思是「阻止本轮停止」，与 deny 完全不同，用错会把会话卡进停不下来的循环。

命令写成「脚本不存在就 `exit 0`」：`.claude/hooks/` 被删或没拷全时直接放行，而不是让 Python 找不到文件、
以退出码 2 结束，把所有 Write/Edit 都拦下。

手动全量检查：`python3 .claude/hooks/gate_cli.py --mode audit`（退出码 0 即无拦截项）。
现状报告（证据成色 + 上下文占用 + 待复核项）：`python3 .claude/hooks/gate_cli.py --mode report`。

建这套检查时仓库里的存量条款绝大多数没写失败现象，强行回填只会逼人编证据，所以选择**冻结而非回填**：
存量条款的指纹记在 `.claude/hooks/gate/baseline.json` 里免除证据门槛，指纹 = 文件路径 + 归一化标题，
**改写标题即视为改写规则本身**，须重新给证据 —— 存量因此随日常维护自然收敛。重新冻结要
`--mode baseline --yes`，它等于批量豁免所有条款，不要拿它绕过拦截。

机制原理图解 → [docs/gate-mechanism.md](docs/gate-mechanism.md)

## 当前覆盖范围

首页（`/`）与登录页（`/login`，到邮箱输入为止）：

- `HomePage`：打开首页、页面加载判定、Agent 分区 tab、顶部操作区、建议卡片、聊天输入框、发送消息并等待回复、
  登录状态判定，通过 `sidebar` 属性持有侧边栏组件。点建议卡片、Connect Portfolio / Connect IM 属写入或外部授权，
  用例不调用；发消息（`send_chat_message`）只在经用户同意的对话用例里调用。
- `SidebarNav`：全站共享的左侧栏，做成组件供后续页面复用；含登录态 Channels 分区与内置「Alva」频道的进入与选中态判定。
- `LoginPage`：登录页加载判定、回首页、登录方式（Google / X / Telegram / Discord / 邮箱）、邮箱框与提交按钮状态。
  提交邮箱会发真实验证码、第三方按钮跳外部授权，只读冒烟不调用。

alva 是服务端渲染 + React 水合，元素可见早于可交互：页面对象的点击走 `BasePage.click_hydrated`、
输入前先 `wait_for_hydrated`，等前端接管节点后再操作。

页面对象与回归点清单分别见 [docs/pages-catalog.md](./docs/pages-catalog.md) 与
[docs/regression-points.md](./docs/regression-points.md)。其他页面尚未封装。

## 让 AI 代理参与开发

Claude Code 打开本项目时加载 `CLAUDE.md` 与 `.claude/rules/` 下的规则，按路由表找到对应 skill
（新建页面对象、加回归点、替换定位符、运行与排查等）。约束要点：

- 跑测试前代理必须向你确认 `--env` 与范围。
- 代理不会自动 `git commit` / `push`。
- How-to 沉淀进 `.claude/skills/<主题>/SKILL.md`，Must / Must-not 沉淀进 `.claude/rules/<域>/<规则>.md`，
  项目事实沉淀进 `docs/`，写入前都要过落库闸门。

## 与上游 VelocitAI 的关系

本项目以「拷贝进项目」的方式使用 VelocitAI，不装插件。上游的 harness 是插件布局（根级 `skills/`
`rules/` `scripts/` `hooks/hooks.json`，外加 `AGENTS.md` `GEMINI.md` 与 `zh/` `en/` 镜像），
这里已转为 Claude Code 项目级格式，只保留 Claude Code 用得到的部分：

| 上游路径 | 本项目路径 |
|---------|-----------|
| `skills/<name>/` | `.claude/skills/<name>/` |
| `skills/SKILL.md`（组合场景路由） | `.claude/skills/ui-automation-harness/SKILL.md` |
| `rules/**` | `.claude/rules/**` |
| `scripts/gate_cli.py`、`scripts/gate/` | `.claude/hooks/gate_cli.py`、`.claude/hooks/gate/` |
| `hooks/hooks.json` | 合并进 `.claude/settings.json` 的 `hooks`，用 `$CLAUDE_PROJECT_DIR` 引用脚本 |
| `framework/core/`、`.claude/agents/code-reviewer.md` | 同路径。三个文件已被本项目改写：`core/base/base_page.py` 新增 `wait_for_hydrated` / `click_hydrated`（等 React 水合后再交互）；`core/healing/llm.py` 把模型 ID 与 API 地址改为可配、喂给模型的属性从固定白名单改成「已知锚点 → 其余 `data-*` → 固定几项」、响应被截断时点名告警；`core/healing/runtime.py` 的 DOM 快照补上 `scope`（元素所在容器，止步于组件根节点）。其余与上游一致 |
| `framework/tests/unit/`、`framework/tests/e2e/` | `tests/unit/`、`tests/e2e/`（用例目录挪到了根目录）。配合上面那三处改动一起改过：`tests/unit/test_llm.py`、`tests/e2e/test_llm_healing_e2e.py`、`tests/e2e/test_self_heal_e2e.py`、`tests/unit/test_base_component.py`、`tests/unit/test_reactive_healing.py`；`tests/e2e/test_llm_healing_live.py` 与 `fixtures/v5_same_scope.html` 为本项目新增 |
| `framework/tests/guest/`（上游示例用例） | 不保留 |
| `framework/conftest.py` | `tests/conftest.py`（需与用例同在 `tests/` 下才生效；内容已改为本项目） |
| `AGENTS.md` `GEMINI.md` `zh/` `en/` `.claude-plugin/` | 不保留 |

`CLAUDE.md` `README.md` `docs/` `framework/config/` `tests/conftest.py` `pytest.ini` 从上游骨架起步、
内容改为本项目；`framework/pages/` `tests/base_test.py` `tests/test_*.py` `framework/tools/`
为本项目新增。

同步上游时，harness 部分因路径与链接已改写，不能整目录覆盖，先比对再手工合并：

```bash
git clone https://github.com/DanielSuo117/velocitai.git /tmp/velocitai
git -C /tmp/velocitai log --oneline -1       # 记下同步到的上游提交

diff -ru /tmp/velocitai/skills .claude/skills
diff -u /tmp/velocitai/skills/SKILL.md .claude/skills/ui-automation-harness/SKILL.md
diff -ru -x __pycache__ /tmp/velocitai/rules .claude/rules
diff -ru -x __pycache__ /tmp/velocitai/scripts/gate .claude/hooks/gate
diff -u /tmp/velocitai/scripts/gate_cli.py .claude/hooks/gate_cli.py

# 代码部分同样不能整目录覆盖了：水合等待与自愈那几处改写都在本项目这边，
# 只覆盖没动过的文件，改写过的逐个比对、手工合并（--exclude 的文件也不会被 --delete 删掉）
rsync -a --delete --exclude base/base_page.py --exclude healing/llm.py --exclude healing/runtime.py \
      /tmp/velocitai/framework/core/ framework/core/
diff -u /tmp/velocitai/framework/core/base/base_page.py  framework/core/base/base_page.py
diff -u /tmp/velocitai/framework/core/healing/llm.py     framework/core/healing/llm.py
diff -u /tmp/velocitai/framework/core/healing/runtime.py framework/core/healing/runtime.py

# 框架自测跟着上面的改动一起改过，也改为先比对再合并，别再 rsync --delete 覆盖
diff -ru -x __pycache__ /tmp/velocitai/framework/tests/unit/ tests/unit/
diff -ru -x __pycache__ /tmp/velocitai/framework/tests/e2e/  tests/e2e/
cp /tmp/velocitai/.claude/agents/code-reviewer.md .claude/agents/

# 同步后校验
python3 -m unittest discover -s .claude/hooks/gate/tests -t .claude/hooks
python3 .claude/hooks/gate_cli.py --mode audit
PYTHONPATH=framework .venv/bin/python -m unittest discover -s tests/unit -t .
.venv/bin/pytest tests/e2e --env=prod --self-heal=on --alluredir=reports/allure-e2e
git status --short && git diff --stat
```

合并时注意：

- 上游文本里的 `skills/…` `rules/…` `scripts/…` 路径要改成上表右列；
  规则 frontmatter 的 `paths` 要对齐本项目的 `framework/` 布局。
- 上游新增 skill 时放进 `.claude/skills/<name>/`，并在 `CLAUDE.md` 路由表补一行，否则提交时闸门的 REG001 会拦下。
- 上游改了 `hooks/hooks.json` 里的闸门命令时，把同样的改动搬进 `.claude/settings.json`
  （保留「脚本不存在就放行」的写法）。
- 上游若也动过 `core/healing/`，与本项目的自愈改动可能正面冲突：合并完必须把单测与自愈 e2e 都跑绿
  （见上方校验块），只看 `git status` 干净不算合完。

## 许可证

上游 VelocitAI 以 MIT 许可发布，原文见 [LICENSE](./LICENSE)。
