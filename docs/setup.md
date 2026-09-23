# 环境搭建

以下命令都在项目根执行。

## 前置条件

- Python 3.10+
- 能访问 https://alva.ai 的网络
- 获取登录 token 需要一个可登录 alva.ai 的账号，以及本机安装的 Google Chrome

## 安装

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/playwright install chromium
```

全程用 `.venv/bin/<命令>` 调用，不依赖 `source .venv/bin/activate`：agent 的每条 Bash 都是新 shell，
激活状态不会保留，裸 `pytest` 可能落到系统 Python 上。

## 配置

```bash
cp framework/config/settings.example.py framework/config/settings.py
```

`settings.py` 不入库，每台机器各自复制。`conftest.py` 与 `save_auth_state.py` 都从它读取配置，
缺了它会报错并提示上面这条复制命令。复制后通常不用改：路径都由文件自身位置推算，换目录克隆也指向正确位置。

| 配置项 | 含义 |
|--------|------|
| `ENVS["prod"]["base_url"]` | 站点根地址 `https://alva.ai`，不带末尾斜杠 |
| `ENVS["prod"]["storage_state"]` | 登录态文件的绝对路径，指向 `<项目根>/.auth/prod_user.json` |
| `AUTH_STATE_DIR` | 登录态目录 `<项目根>/.auth` |
| `HEADLESS` / `SLOW_MO` | 默认有头、每步间隔 500ms；无头时间隔默认 0。可用同名环境变量覆盖 |
| `DEFAULT_TIMEOUT` / `DEFAULT_NAVIGATION_TIMEOUT` | 元素操作超时 / 页面导航超时，均为 15000ms，两者分开设 |
| `VIEWPORT_WIDTH` / `VIEWPORT_HEIGHT` | 浏览器视口，1280 × 900 |
| `SELF_HEAL_ARTIFACT` / `SELF_HEAL_FINGERPRINTS` | 选择器自愈产物路径（`reports/self-heal/`） |
| `ANTHROPIC_API_KEY` | 仅 `--self-heal=auto` 使用，留空即可 |
| `SELF_HEAL_MODEL` | `--self-heal=auto` 用的模型名，留空用 `llm.py` 的 `DEFAULT_MODEL` |

环境只有 `prod`，没有预发，也没有 `DEFAULT_ENV`：环境必须用 `--env` 显式指定，留默认值只会诱导
某段代码悄悄拿它兜底。新增环境时在 `ENVS` 里加一项，`--env` 即可选用。

### 环境变量

| 变量 | 作用 |
|------|------|
| `HEADLESS` | `true` / `false`（也认 `1/0`、`yes/no`、`on/off`）。写错的值直接报错，不会被当成 false |
| `SLOW_MO` | 每步操作间隔（毫秒），覆盖跟随 `HEADLESS` 的默认值 |
| `ANTHROPIC_API_KEY` | `--self-heal=auto` 的模型推理密钥，优先于 `settings.py` 的同名项 |
| `SELF_HEAL_MODEL` | `--self-heal=auto` 的模型名，优先于 `settings.py` 的同名项 |
| `VELOCITAI_LOG_LEVEL` | 框架日志级别，默认 `INFO` |

## 登录态

所有业务用例（`tests/test_*.py`，继承 `AlvaBaseTest`）都**凭 token 免登**：只注入 alva.ai 的 `authorization` cookie，
访问 `/login` 后前端直接送回首页（已登录）。
第一次跑之前、以及 token 过期后，获取一次：

```bash
.venv/bin/python framework/tools/save_auth_state.py --env prod
```

- 脚本启动本机**真实 Google Chrome**（配置目录在 `.auth/chrome-profile-prod`），打开 `/login`，你在里面人工登录，
  邮箱验证码或 Google 都行。登录期间脚本只轮询 Chrome 调试接口里的页面 URL，不接管页面，以免干扰 Cloudflare 人机验证。
- 回到首页后，脚本导出到 `.auth/prod_user.json`（权限 600），打印 cookie 的到期时间（不打印值），关闭它启动的 Chrome，
  再用无头浏览器只注入 token 访问 `/login`，自检能否免登进入首页。
- 已经有一个用 `--remote-debugging-port` 启动并登录好的 Chrome 时，用 `--attach <端口>` 直接导出，不启动也不关闭它。
- 非 macOS 或 Chrome 不在默认位置：`--chrome <路径>` 或环境变量 `CHROME_PATH`。
- 不用 Playwright 启动的浏览器登录，是因为它过不了 Cloudflare 人机验证（邮箱验证码之后、Google 回调页上都有）。

token 来源依次为环境变量 `ALVA_TOKEN`、`.auth/prod_user.json`。CI 上把 token 配成 secret 注入 `ALVA_TOKEN` 即可，不需要文件。

- token 等同账号凭据：`.auth/` 不入库，不要贴进 issue、日志或聊天。
- 没有 token：业务用例被 skip，输出里会提示两种提供方式。
- token 无效或过期（cookie 约在登录 21 天后到期）：业务用例直接 fail（「token 无效或已过期」）并提示重新获取。

判定方式见 [architecture.md 的「登录态」一节](./architecture.md#登录态)。

## 运行测试

`--env` 必须显式传入（`conftest.py` 里 `required=True`）。prod 是生产环境：用例只做只读操作，
不提交数据、不点会触发外部授权或付费的按钮。唯一例外是 `test_alva_agent_chat.py`：它会真实发送一条消息
（用户 2026-09-22 明确要求），每跑一次账号的 Alva 频道就多一轮对话。其他要写入数据的用例须先征得同意。

```bash
# 免登冒烟（只读）：访问登录页 → 直接进入首页
.venv/bin/pytest tests/test_login.py --env=prod

# Alva agent 对话：Channels → Alva → 发送提示词 → 等回复（真实发送一条消息，回复实测约 30～42s）
.venv/bin/pytest tests/test_alva_agent_chat.py --env=prod

# 全量业务回归（pytest.ini 的 testpaths 是 tests/test_*.py，只收业务用例）
.venv/bin/pytest --env=prod
# 全量但跳过标记为 slow 的对话用例，不发消息
.venv/bin/pytest --env=prod -m "not slow"

# 按关键字筛选
.venv/bin/pytest tests/test_login.py --env=prod -v -k <关键字>

# 无头运行（默认有头）
HEADLESS=true .venv/bin/pytest tests/test_login.py --env=prod
```

两条业务用例都需要 token：拿不到（`ALVA_TOKEN` 与 `.auth/prod_user.json` 都没有）时 skip，原因里给出获取方式；
token 无效或过期时直接 fail，提示重新获取。

`tests/unit`（107 条）与 `tests/e2e`（14 条）是**框架自身**的自测（自愈引擎、组件作用域），不是站点的回归点，
因此不进默认收集 —— 否则一次「全量回归」跑出 123 条，真正该看的 2 条被淹没。两种方式都能把它们单独跑出来：
显式传目录，或用 `tests/conftest.py` 统一挂上的 `framework` 标记筛选。`tests/e2e` 不加
`--self-heal=on|strict|auto` 时整组 skip。

```bash
.venv/bin/pytest tests/e2e --env=prod --self-heal=on     # 只跑自愈端到端（本地 HTML 夹具，不访问站点）
.venv/bin/pytest tests --env=prod -m framework           # 框架自测全跑（unit + e2e）
.venv/bin/pytest tests --env=prod -m "not framework"     # 显式传 tests/ 但只要业务用例
```

### 选择器自愈

LLM 推理后端的三项配置都在 `framework/config/settings.py`（该文件已被 `.gitignore` 忽略，不入库；
新克隆的仓库里没有它，先 `cp framework/config/settings.example.py framework/config/settings.py`）：

| 配置项 | 作用 | 留空时 |
|---|---|---|
| `ANTHROPIC_API_KEY` | 推理用的 key | 自愈退回纯规则模式，不报错 |
| `ANTHROPIC_BASE_URL` | API 根地址，指向官方或自建代理／中转 | 用官方地址 |
| `SELF_HEAL_MODEL` | 推理用的模型 ID | 用 `llm.py::DEFAULT_MODEL` |

三项都可用同名环境变量临时覆盖（环境变量优先，便于 CI 注入与临时换号）。
`ANTHROPIC_BASE_URL` 三种填法都认：根地址、到 `/v1`、到 `/v1/messages`。
key 等同凭据：不打印、不入库、不外传，`settings.py` 建议权限 600。

模型若会「思考」，思考 token 同样计入 `llm.py::MAX_TOKENS`。上限给小了，响应会在产出
JSON 之前就被截断（`stop_reason=max_tokens`、只有 thinking 块），表现为模型永远交白卷；
这种情况会打 WARNING 点名，照着调大 `MAX_TOKENS` 或换不思考的模型即可。

`--self-heal` 默认 `off`。`on`：定位失效时尝试重建定位符，用例继续；`strict`：同 `on`，但只要发生过自愈就
以非零码结束，便于发现漂移；`auto`：同 `on`，并在规则修不了时让模型推理，且把修复写回页面对象源码
（会改动工作区，原文件备份为 `.heal-bak`）。写回同样要过落库闸门。

模型推理需要 `ANTHROPIC_API_KEY`。**没有 key 时 `auto` 不报错、不发网络请求，只用规则修复，但照样写回源码**。
模型名依次取环境变量 `SELF_HEAL_MODEL`、`settings.py` 的 `SELF_HEAL_MODEL`，都为空时用 `framework/core/healing/llm.py` 的 `DEFAULT_MODEL`。

### 报告

```bash
allure serve reports/allure-results
```

`pytest.ini` 的 `addopts` 已带 `--alluredir=reports/allure-results --clean-alluredir`：每次运行都写入结果，
并清掉上一次的，报告里不会混进早已修好的旧失败。这个路径相对启动目录，所以要在项目根跑 pytest。
`reports/` 不入库。

### 框架与闸门自测

不访问站点，改动 `framework/core/` 或 `.claude/hooks/` 后跑：

```bash
PYTHONPATH=framework .venv/bin/python -m unittest discover -s tests/unit -t .
python3 -m unittest discover -s .claude/hooks/gate/tests -t .claude/hooks
python3 .claude/hooks/gate_cli.py --mode audit      # rc=0 即无 BLOCK
.venv/bin/pytest tests/e2e --env=prod --self-heal=on --alluredir=reports/allure-e2e   # 自愈 e2e：只打开本地 HTML 夹具；单独的结果目录，免得清掉业务回归的报告
```

## 落库闸门

闸门在 `.claude/settings.json` 的 PreToolUse hooks 里接线：Claude Code 每次 Write/Edit、每次 `git commit`
前都会调用 `.claude/hooks/gate_cli.py`，不合规的 `.claude/skills/` `.claude/rules/` `docs/` 改动会被拦下
（退出码 2，理由回传给代理）。

排障：

- 闸门完全没有反应 —— 先确认 `.claude/hooks/gate_cli.py` 存在：hook 命令写成脚本缺失就 `exit 0` 放行，
  避免 Python 找不到脚本时以退出码 2 结束、把所有 Write/Edit 都拦下。再确认 `python3` 在 PATH 上
  （Windows 常只有 `python`，把 `.claude/settings.json` 里的 `python3` 改成 `python`）。
- 不是 `git commit` 的 Bash 命令也被 commit 闸门拦下 —— commit hook 靠 `if: "Bash(git commit *)"` 过滤，
  命令里有 heredoc 或过度复杂的复合写法时过滤可能失效，hook 会对它也跑一遍 commit 校验。
  拆成简单命令，多行脚本先写成文件再执行。

## 可选工具

- **agent-browser**：DOM 探索 / 定位符采集，比 Playwright MCP 省 token。
  每次 `agent-browser open <URL>` 后紧跟 `agent-browser set viewport 1024 768`；
  多个 agent 并行时用 `--session <名字>` 隔离会话。
- **code-review-graph**：AST 知识图谱 MCP。`.claude/settings.json` 在会话开始（`code-review-graph status`）和
  `git commit` 前（`code-review-graph build`）调用它，没装时这两个 hook 报错但不阻塞。
- **allure**：报告查看，macOS 用 `brew install allure`。
