# 项目架构

## 顶层：代码与 harness 分开存放

```
.
├── tests/                  测试用例（放根目录，方便查看）
│   ├── conftest.py         fixture 层
│   ├── base_test.py        基础测试类 AlvaBaseTest（业务用例统一继承，不区分角色）
│   ├── test_*.py           业务用例（test_login.py · test_alva_agent_chat.py）
│   └── unit/ · e2e/        框架自测（不访问站点 / 本地 HTML 夹具）
│
├── framework/              代码 —— Python UI 自动化框架
│   ├── core/               框架核心（base · healing · exceptions · logger），与业务无关
│   ├── pages/              业务页面对象（home_page.py · login_page.py · components/sidebar_nav.py）
│   ├── tools/              辅助脚本（save_auth_state.py：获取登录 token）
│   └── config/             环境与浏览器配置（settings.py 不入库）
│
├── .auth/                  登录 token（storageState 格式，本地生成，不入库）
│
├── CLAUDE.md               harness —— agent 唯一入口与路由表
├── .claude/
│   ├── settings.json       harness —— 权限 + hooks 接线（闸门在这里生效）
│   ├── skills/             harness —— 操作方法论（How-to），每个 skill 一个目录
│   ├── rules/              harness —— 强制约束（Must / Must-not），自动或按 paths 加载
│   ├── hooks/              harness —— 落库闸门（gate_cli.py + gate/）
│   └── agents/             harness —— 子代理（code-reviewer.md）
└── docs/                   harness —— 本项目的事实（类名、URL、清单、架构、搭建）
```

**harness 用 Claude Code 项目级原生格式**：skill、rule、hook、子代理都放在 `.claude/` 下，
由 Claude Code 按约定位置发现，不依赖插件机制。闸门在 `.claude/settings.json` 里用
`$CLAUDE_PROJECT_DIR` 引用 `.claude/hooks/gate_cli.py`，脚本缺失时放行而不是拦截所有写入。

**为什么框架代码收进 `framework/`、用例放根目录 `tests/`**：harness 的位置由 Claude Code 决定（`.claude/`、
根目录 `CLAUDE.md`），代码没有这个约束。框架代码收进一个目录，harness 文档与 Python 代码不会混在同一层；
用例是日常最常看、最常改的部分，放在根目录 `tests/` 一眼可见。fixture 层 `conftest.py` 必须位于用例的
祖先目录才会生效，所以随用例放在 `tests/`。`pytest.ini` 留在根目录，`testpaths = tests`，
`pythonpath = framework .`：前者让 `from pages.xxx` / `from core.xxx` 可导入，后者让用例之间的
`from tests.base_test import AlvaBaseTest` 可导入。

## POM 分层

```
┌──────────────────────────────────────────────────────┐
│  tests/ 测试层                              │
│  业务用例 test_*.py，统一继承 AlvaBaseTest（不分角色）  │
├──────────────────────────────────────────────────────┤
│  framework/pages/ 业务页面对象层                       │
│  HomePage 继承 BasePage；侧边栏 SidebarNav 继承         │
│  BaseComponent，放 components/，由页面对象组合持有      │
├──────────────────────────────────────────────────────┤
│  framework/core/ 框架核心层（公共能力，与业务无关）       │
│    base/       BasePage · BaseComponent · BaseTest    │
│    healing/    interceptor · engine · runtime         │
│                llm · patcher                          │
│    exceptions.py  logger.py                           │
├──────────────────────────────────────────────────────┤
│  framework/config/ 配置层                             │
│  base_url、storageState 路径、浏览器参数、自愈产物路径    │
├──────────────────────────────────────────────────────┤
│  tests/conftest.py Fixture 层                     │
│  browser → context（访客 / 只注入 token）→ page         │
│  → AlvaBaseTest                                       │
└──────────────────────────────────────────────────────┘
```

**PO 原则**：公共能力一律沉到 `core/base/`，业务代码继承即可，不重复实现。
所有定位都经 `BasePage._act()` / `_locate()` 收口到拦截器，因此自愈对业务代码
完全透明 —— 页面对象不需要知道自愈存在。定位**作用域**同样收口在一处
（`scope_root()`）：`BaseComponent` 只覆盖它即可把组件内的定位全部限制在 root 之内。
曾经组件覆盖的是 `_locate()`，而 click/fill 走的是 `_act()`，作用域因此形同虚设。

**为什么点击走 `click_hydrated`**：alva 是服务端渲染 + React 水合，元素可见、`is_page_loaded()` 成立时前端
未必已接管节点；水合前的点击、输入不报错却被静默吞掉，水合后也不会补上（2026-09-22 实测 Agent tab 约 1/12 的点击如此）。
`BasePage.wait_for_hydrated(selector, timeout=None)` 每 50ms（`HYDRATION_POLL_MS`）检查一次该定位符命中的节点上
是否已有 React 挂的 `__reactProps$` 属性（`REACT_HYDRATED_JS`），默认上限 `HYDRATION_TIMEOUT` 15s，超时抛 `TimeoutError`；
每轮重新解析 locator 而不是持有 element handle —— 水合遇到内容不一致时 React 会换掉整个节点，旧 handle 永远等不到属性。
`click_hydrated(selector)` = 先 `wait_for_hydrated` 再 `click`，页面对象的点击都用它（只读用例禁用的第三方登录图标按钮、
按序号点的建议卡片例外），`fill_chat_input` 等输入方法也先等水合。已水合时首轮检查即返回，几乎不增加耗时。

**为什么 core/ 与 pages/ 要分开**：两者混在一起时，页面对象目录里会逐渐堆进
自愈引擎、日志、异常这类谁都不该在写登录页时读到的代码。

**为什么侧边栏做成组件**：左侧栏出现在所有页面上。挂在首页里，以后每个页面对象都得复制一份
定位符；做成 `SidebarNav` 组件，任何页面对象持有一个实例即可，定位也被限定在侧边栏 root 内，
不会误中正文里同名的链接。首页通过 `HomePage.sidebar` 暴露它。

## fixture 层

| fixture | scope | 作用 |
|---------|-------|------|
| `env` | session | `--env` 对应的 `ENVS` 配置；未知环境直接 fail |
| `base_url` | session | 站点根地址，不带末尾斜杠 |
| `auth_state_path` | session | 当前 env 的本地 token 文件路径（只给路径，不检查文件是否存在） |
| `auth_token` | session | 登录 token：环境变量 `ALVA_TOKEN` 优先，其次本地文件里的 `authorization` cookie；都没有则 skip |
| `playwright_instance` / `browser` | session | Playwright 与浏览器进程 |
| `page` | function | 访客独立 context（`tests/e2e` 自愈自测用它打开本地 HTML 夹具） |
| `class_page` | class | 访客共享 context，同时设 `request.cls.page`（当前业务用例未使用） |
| `auth_class_page` | class | 只注入 token 这一个 cookie 的共享 context（不加载整份 storageState），交出去时停在空白页；免登由 `AlvaBaseTest` 完成。`browser` 在拿到 token 之后才取，没有 token 时直接 skip，不会白白弹出浏览器窗口 |

viewport、超时、登录态都由 conftest 内部的 `_open_page()` 统一设置，三个 page fixture 不各写一遍，
避免同一个页面在不同 fixture 下跑在不同视口或超时下。

## 基础测试类与 context 共享

当前版本不区分角色：所有业务用例以同一个登录账号运行，测试类统一继承 `tests/base_test.py::AlvaBaseTest`。
它继承框架的 `core.base.base_test.BaseTest`（只做用例前后的日志记录），封装四件事，用例里不再重复：

| 封装 | 实现 | 说明 |
|------|------|------|
| 共享 page | class 级 autouse fixture `_session`，取 `auth_class_page` | 每个测试类一个全新 context，class 内用例共用。属性挂在类上（`request.cls`），用例里的 `self.page` 才读得到；写成 classmethod 是 pytest 9 的要求 |
| 页面对象 | `self.page` / `self.login_page`（`LoginPage`）/ `self.home_page`（`HomePage`） | 侧边栏经 `self.home_page.sidebar` 访问 |
| 凭 token 免登 | `login_by_token()`，由 `_session` 每个 class 调一次 | 访问 `/login` → 等前端送回首页 → 确认首页已加载且为登录态，失败处理见「登录态」一节 |
| 起点复位 | function 级 autouse fixture `_reset_to_home` | 每个用例开始前导航回首页并断言 `is_page_loaded()` |

满足决策树的 class 级共享条件：同一域名、前置统一（token 在建 context 时注入，免登每个 class 一次）、起点统一为首页。
复位是每次都导航，而不是先判断「是否偏离起点」：判定「不在起点」要等 `is_page_loaded()` 对缺席元素等满默认超时（15s），
同一 context 内直接导航回首页只要约 0.4s；整页导航还能清掉输入框草稿、切走的 tab 这类残留，上一个用例中途失败留下的
状态不会连累下一个。导航只清页面内状态，cookie / localStorage 在 class 内延续。这是每个用例固定的起点动作，
不是替没闭合的用例兜底 —— 用例离开首页后仍应在末尾走真实 UI 返回并断言。

除 `test_alva_agent_chat.py` 经用户 2026-09-22 明确同意、会真实发送一条消息外，用例一律只读：不新建频道 / 会话、
不改设置、不点 Portfolio / IM 等外部授权入口。

## 登录态

所有业务用例**凭 token 免登**，流程是「访问登录页 → 直接进入首页」，不在用例里走登录表单。

- **token 是什么**：alva.ai 域下名为 `authorization` 的 cookie（path=/，SameSite=Lax）。2026-09-22 实测：
  只把这一个 cookie 注入全新的 Playwright context，访问 `/login` 时服务端照常返回 200，前端在 load 后约 0.7～4s
  （多次测量波动）把 URL 改成 `/`，登录表单全程不渲染，页面为登录态；不经过 Cloudflare 人机验证。
  `AlvaBaseTest` 等这次跳转的上限是 `LOGIN_REDIRECT_TIMEOUT` 10s；不等 networkidle —— 登录态首页有常驻后台请求，永远等不到。
- **为什么不在用例里登录**：邮箱登录是「邮箱 → 6 位验证码 → Cloudflare Turnstile」，Google 登录的回调页
  `/oauth-login` 上同样有 Turnstile；Playwright 启动的浏览器过不了，人机验证也不应自动化绕过。
  登录页（到邮箱输入为止）的封装见 `LoginPage`。
- **来源**（`conftest.py` 的 `auth_token`）：环境变量 `ALVA_TOKEN` 优先，其次是本地 `.auth/prod_user.json` 里的
  `authorization` cookie（路径与 cookie 名由 `settings.py` 的 `ENVS["prod"]["storage_state"]` / `["auth_cookie"]` 决定）。
  两种来源都**只注入这一个 cookie**，与「凭 token 免登」的定义一致；CI 只需一个 secret。
- **获取**：`framework/tools/save_auth_state.py` 启动本机真实 Google Chrome 由人登录，登录期间只轮询
  调试接口的 URL，回到首页后经 CDP 导出（权限 600），再用无头浏览器只注入 token 自检免登。
- **缺失**：没有任何来源时 `auth_token` fixture skip 全部业务用例并提示两种提供方式 —— 新克隆的仓库或 CI 上
  本来就没有 token，整组报红只会淹没真正的回归失败。
- **失效**：`AlvaBaseTest.login_by_token()` 每个 class 访问一次 `/login`，按结果分别处理：

  | 情况 | 处理 |
  |------|------|
  | 10s 内没被送回首页，且仍停在登录表单 | fail「token 无效或已过期」，附 token 来源（不含值）与重新获取方式 |
  | 10s 内没被送回首页，也不在登录表单上 | fail，给出当前 URL |
  | 已送回首页，但首页加载失败 | fail「首页加载失败，无法校验登录态」 |
  | 首页已加载，但 `is_logged_in()` 不成立（侧边栏没有用户菜单） | 同样按「token 无效或已过期」fail |

  先判首页加载、再判登录态：顺序反过来会把「没加载完」误判成「token 失效」。fail 都在 `except` 之外、`pytrace=False`，
  报告里不会先挂一段 Playwright 超时回溯。故意用 fail 而不是 skip：提供了 token 说明使用者想跑用例，
  悄悄 skip 会让覆盖率静默归零。cookie 约在登录 21 天后到期，服务端是否提前吊销不做假设，失效就重新获取。
- **安全**：token 等同账号凭据，只存在于 `.auth/`（不入库）或环境变量；代码、日志、报告里都不打印它的值。

## 决策树

详见 [architecture skill](../.claude/skills/architecture/SKILL.md)
