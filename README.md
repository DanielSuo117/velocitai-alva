# alva.ai UI 自动化回归

基于 [VelocitAI](https://github.com/DanielSuo117/velocitai) 搭建的 alva.ai UI 自动化回归项目。

- **被测对象**：[alva.ai](https://alva.ai)，AI 投资助手单页应用。目前只有生产环境，没有预发。
- **代码侧**：`framework/`，Python + Playwright + pytest 的 POM 框架，带选择器自愈。
- **harness 侧**：`CLAUDE.md` + `.claude/`（skills、rules、hooks、子代理、settings）+ `docs/`，
  全部采用 Claude Code 项目级原生格式，约束 AI 编程代理如何生成、运行、排查和沉淀测试代码。
- **当前进度**：框架骨架已搭好，封装了首页、登录页（到邮箱输入为止）页面对象与角色基类，已有访客只读冒烟。

## 目录结构

```
.
├── CLAUDE.md                    # agent 唯一入口：项目速览 + 行为边界 + 路由表 + 命令
├── README.md
├── LICENSE
├── requirements.txt
├── pytest.ini                   # testpaths=framework/tests，pythonpath=framework，标记注册，allure 输出目录
├── .claude/
│   ├── settings.json            # 权限 + hooks（落库闸门、code-review-graph 在这里接线）
│   ├── agents/
│   │   └── code-reviewer.md     # 代码审查子代理
│   ├── skills/<name>/SKILL.md   # 14 个 skill：操作方法论（ui-automation-harness 为组合场景路由）
│   ├── rules/<域>/<规则>.md     # 强制规则，由 Claude Code 自动或按 paths 加载
│   └── hooks/
│       ├── gate_cli.py          # 落库闸门入口（PreToolUse 调用）
│       └── gate/                # 闸门实现与自测（gate/tests/）
├── docs/                        # 项目事实：架构、环境搭建、PageObject 清单、回归点
├── .auth/                       # 登录态 storageState，本地生成，不入库
├── reports/                     # allure 结果与自愈产物，不入库
└── framework/
    ├── conftest.py              # fixture：env / base_url / auth_state_path / playwright_instance / browser / page / class_page / user_class_page
    ├── config/
    │   ├── settings.example.py  # 配置模板（入库）
    │   └── settings.py          # 本地配置，由模板复制（不入库）
    ├── core/                    # 框架核心：BasePage / BaseComponent / BaseTest、选择器自愈、日志
    ├── pages/
    │   ├── home_page.py         # HomePage：首页
    │   ├── login_page.py        # LoginPage：登录页（到邮箱输入为止）
    │   └── components/
    │       └── sidebar_nav.py   # SidebarNav：全站左侧栏
    ├── tools/
    │   └── save_auth_state.py   # 生成登录态
    └── tests/
        ├── guest/               # 访客：guest_base_test.py（GuestBaseTest）
        ├── user/                # 登录用户：user_base_test.py（UserBaseTest）
        ├── unit/                # 框架单测（unittest，不访问站点）
        └── e2e/                 # 选择器自愈端到端自测（本地 HTML 夹具）
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

# 3. 生成登录态（有头浏览器，人工登录后回终端按回车；只跑访客用例可跳过）
.venv/bin/python framework/tools/save_auth_state.py --env prod

# 4. 运行：访客只打开公开页面、不登录；默认有头，HEADLESS=true 切无头
HEADLESS=true .venv/bin/pytest framework/tests/guest --env=prod
.venv/bin/pytest framework/tests/user --env=prod

# 5. Allure 报告（pytest.ini 已默认把结果写到 reports/allure-results）
allure serve reports/allure-results
```

`--env` 必须显式传入，目前只有 `prod`。prod 是生产环境，用例只做只读操作。
当前用例：`guest/test_guest_home.py` 是 6 条首页只读冒烟（不点发送、不点建议卡片与外部授权入口），
`guest/test_guest_login.py` 是 3 条登录页只读冒烟（不提交邮箱、不点第三方登录）；
`user/test_user_home.py` 校验登录态首页，没有登录态文件时整组 skip。新用例由
[gen-page-test](./.claude/skills/gen-page-test/) 或 [add-regression-point](./.claude/skills/add-regression-point/) 生成。
配置项、环境变量与排障见 [docs/setup.md](./docs/setup.md)。

## 角色与登录态

| 角色 | 用例目录 | 基类 | 登录态 |
|------|---------|------|--------|
| guest 访客 | `framework/tests/guest/` | `GuestBaseTest` | 无 |
| user 登录用户 | `framework/tests/user/` | `UserBaseTest` | `.auth/prod_user.json` |

两个角色都在 class 内共享一个浏览器 context，每个用例开始前导航回首页并断言起点。

alva.ai 提供 Google / X / Telegram / Discord 第三方登录和邮箱验证码登录，都没有可以直接注入的 token，所以登录用户的用例复用
Playwright storageState：用 `save_auth_state.py` 打开有头浏览器，人工登录一次后保存（权限 600）。
推荐邮箱验证码，Google 可能拦截自动化工具启动的浏览器。

- 登录态文件不存在：user 用例 skip，并提示生成命令。
- 登录态失效：user 用例 fail，并提示重新生成。判定依据是打开首页后侧边栏的「Log in」按钮是否仍可见。
- `.auth/` 下的文件等同于账号凭据，不入库。

设计取舍见 [docs/architecture.md](./docs/architecture.md)。

## 落库闸门（hook）

`.claude/settings.json` 的 PreToolUse hooks 在两个时机调用 `.claude/hooks/gate_cli.py`：

- Claude Code 执行 Write / Edit 时（`--mode write`），校验写入 `.claude/skills/` `.claude/rules/` `docs/` 的内容；
- 执行 `git commit` 时（`--mode commit`），校验暂存区，包括 CLAUDE.md 路由表是否登记了全部 skill、链接是否存在。

闸门以退出码 2 表示拦截，拦截理由会回传给代理。命令写成「脚本不存在就 `exit 0`」：`.claude/hooks/`
被删或没拷全时直接放行，而不是让 Python 找不到文件、以退出码 2 结束，把所有 Write/Edit 都拦下。

手动全量检查：`python3 .claude/hooks/gate_cli.py --mode audit`（退出码 0 即无拦截项）。

## 当前覆盖范围

首页（`/`）与登录页（`/login`，到邮箱输入为止）：

- `HomePage`：打开首页、页面加载判定、Agent 分区 tab、顶部操作区、建议卡片、聊天输入框、登录状态判定，
  通过 `sidebar` 属性持有侧边栏组件。发消息、点建议卡片、Connect Portfolio / Connect IM 属写入或外部授权，
  只读冒烟不调用。
- `SidebarNav`：全站共享的左侧栏，做成组件供后续页面复用。
- `LoginPage`：登录页加载判定、回首页、登录方式（Google / X / Telegram / Discord / 邮箱）、邮箱框与提交按钮状态。
  提交邮箱会发真实验证码、第三方按钮跳外部授权，只读冒烟不调用。

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
| `framework/core/`、`framework/tests/unit/`、`framework/tests/e2e/`、`.claude/agents/code-reviewer.md` | 同路径，内容与上游一致 |
| `AGENTS.md` `GEMINI.md` `zh/` `en/` `.claude-plugin/` | 不保留 |

`CLAUDE.md` `README.md` `docs/` `framework/config/` `framework/conftest.py` `pytest.ini` 从上游骨架起步、
内容改为本项目；`framework/pages/` `framework/tests/guest/` `framework/tests/user/` `framework/tools/`
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

# 未改写的代码部分可以直接覆盖
rsync -a --delete /tmp/velocitai/framework/core/       framework/core/
rsync -a --delete /tmp/velocitai/framework/tests/unit/ framework/tests/unit/
rsync -a --delete /tmp/velocitai/framework/tests/e2e/  framework/tests/e2e/
cp /tmp/velocitai/.claude/agents/code-reviewer.md .claude/agents/

# 同步后校验
python3 -m unittest discover -s .claude/hooks/gate/tests -t .claude/hooks
python3 .claude/hooks/gate_cli.py --mode audit
.venv/bin/python -m unittest discover -s framework/tests/unit -t framework
git status --short && git diff --stat
```

合并时注意：

- 上游文本里的 `skills/…` `rules/…` `scripts/…` 路径要改成上表右列；
  规则 frontmatter 的 `paths` 要对齐本项目的 `framework/` 布局。
- 上游新增 skill 时放进 `.claude/skills/<name>/`，并在 `CLAUDE.md` 路由表补一行，否则提交时闸门的 REG001 会拦下。
- 上游改了 `hooks/hooks.json` 里的闸门命令时，把同样的改动搬进 `.claude/settings.json`
  （保留「脚本不存在就放行」的写法）。

## 许可证

上游 VelocitAI 以 MIT 许可发布，原文见 [LICENSE](./LICENSE)。
