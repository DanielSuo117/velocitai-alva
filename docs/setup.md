# 环境搭建

以下命令都在项目根执行。

## 前置条件

- Python 3.10+
- 能访问 https://alva.ai 的网络
- 生成登录态需要一个可登录 alva.ai 的账号（推荐邮箱验证码登录）

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

环境只有 `prod`，没有预发，也没有 `DEFAULT_ENV`：环境必须用 `--env` 显式指定，留默认值只会诱导
某段代码悄悄拿它兜底。新增环境时在 `ENVS` 里加一项，`--env` 即可选用。

### 环境变量

| 变量 | 作用 |
|------|------|
| `HEADLESS` | `true` / `false`（也认 `1/0`、`yes/no`、`on/off`）。写错的值直接报错，不会被当成 false |
| `SLOW_MO` | 每步操作间隔（毫秒），覆盖跟随 `HEADLESS` 的默认值 |
| `ANTHROPIC_API_KEY` | `--self-heal=auto` 的模型推理密钥，优先于 `settings.py` 的同名项 |
| `VELOCITAI_LOG_LEVEL` | 框架日志级别，默认 `INFO` |

## 登录态

`user` 角色的用例复用 Playwright storageState，第一次跑之前、以及登录态失效后，都要重新生成：

```bash
.venv/bin/python framework/tools/save_auth_state.py --env prod
```

脚本打开有头浏览器（不受 `HEADLESS` 影响）并进入 `/login`。在浏览器里手动登录，看到首页后回到终端按回车；
脚本回到首页确认已登录后，才把登录态保存到 `.auth/prod_user.json`（权限 600）。没检测到登录会让你继续登、
再按回车，不必重跑脚本；Ctrl+C 放弃则不写文件。

推荐邮箱验证码登录 —— Google 常以「此浏览器可能不安全」拦截由自动化工具启动的浏览器。

- 文件等同于账号凭据：`.auth/` 不入库，不要贴进 issue、日志或聊天。
- 文件不存在时，`user` 用例被 skip，输出里会提示上面的命令。
- 文件存在但失效时，`user` 用例直接 fail 并提示重新生成。

判定方式见 [architecture.md 的「登录态」一节](./architecture.md#登录态)。

## 运行测试

`--env` 必须显式传入（`conftest.py` 里 `required=True`）。prod 是生产环境：用例只做只读操作，
不发送消息、不提交数据、不点会触发外部授权或付费的按钮；要写入数据的用例须先征得同意。

```bash
# 访客（不需要登录态）
.venv/bin/pytest framework/tests/guest --env=prod

# 登录用户（需先生成登录态）
.venv/bin/pytest framework/tests/user --env=prod

# 按关键字筛选
.venv/bin/pytest framework/tests/guest --env=prod -v -k <关键字>

# 无头运行（默认有头）
HEADLESS=true .venv/bin/pytest framework/tests/guest --env=prod
```

`framework/tests/user` 在 `.auth/prod_user.json` 不存在时整组 skip（原因里给出生成命令）；
文件存在但会话已过期时直接 fail，提示重新生成。

### 选择器自愈

`--self-heal` 默认 `off`。`on`：定位失效时尝试重建定位符，用例继续；`strict`：同 `on`，但只要发生过自愈就
以非零码结束，便于发现漂移；`auto`：同 `on`，并让模型推理且把修复写回页面对象源码（需要
`ANTHROPIC_API_KEY`，会改动工作区，原文件备份为 `.heal-bak`）。写回同样要过落库闸门。

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
.venv/bin/python -m unittest discover -s framework/tests/unit -t framework
python3 -m unittest discover -s .claude/hooks/gate/tests -t .claude/hooks
python3 .claude/hooks/gate_cli.py --mode audit      # rc=0 即无 BLOCK
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
