# 项目架构

## 顶层：代码与 harness 分开存放

```
.
├── framework/              代码 —— Python UI 自动化框架
│   ├── core/               框架核心（base · healing · exceptions · logger），与业务无关
│   ├── pages/              业务页面对象（home_page.py · components/sidebar_nav.py）
│   ├── tests/              业务用例（guest/ · user/）+ 框架自测（unit/ · e2e/）
│   ├── tools/              辅助脚本（save_auth_state.py：生成登录态）
│   ├── config/             环境与浏览器配置（settings.py 不入库）
│   └── conftest.py         fixture 层
│
├── .auth/                  登录态 storageState（本地生成，不入库）
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

**为什么代码收进 `framework/`**：harness 的位置由 Claude Code 决定（`.claude/`、根目录 `CLAUDE.md`），
代码没有这个约束。收进一个目录后，规则的 `paths` 可以用 `framework/**` 精确匹配，
harness 文档与 Python 代码也不会混在同一层。`pytest.ini` 留在根目录并设 `pythonpath = framework`，
在项目根直接跑 pytest 即可找到代码与包路径。

## POM 分层

```
┌──────────────────────────────────────────────────────┐
│  framework/tests/ 测试层                              │
│  按角色拆目录：guest/ · user/，各有角色基类            │
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
│  framework/conftest.py Fixture 层                     │
│  browser → context（访客 / 带 storageState）→ page     │
│  → 角色基类                                           │
└──────────────────────────────────────────────────────┘
```

**PO 原则**：公共能力一律沉到 `core/base/`，业务代码继承即可，不重复实现。
所有定位都经 `BasePage._act()` / `_locate()` 收口到拦截器，因此自愈对业务代码
完全透明 —— 页面对象不需要知道自愈存在。定位**作用域**同样收口在一处
（`scope_root()`）：`BaseComponent` 只覆盖它即可把组件内的定位全部限制在 root 之内。
曾经组件覆盖的是 `_locate()`，而 click/fill 走的是 `_act()`，作用域因此形同虚设。

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
| `auth_state_path` | session | 当前 env 的 storageState 文件路径（只给路径，不检查文件是否存在） |
| `playwright_instance` / `browser` | session | Playwright 与浏览器进程 |
| `page` | function | 访客独立 context |
| `class_page` | class | 访客共享 context，同时设 `request.cls.page` |
| `user_class_page` | class | 带 storageState 的共享 context；文件不存在时 skip 并提示如何生成 |

viewport、超时、登录态都由 conftest 内部的 `_open_page()` 统一设置，三个 page fixture 不各写一遍，
避免不同角色跑在不同视口或超时下。

## 角色与 context 共享

| 角色 | 基类 | context scope | 起点页面 |
|------|------|--------------|---------|
| guest（访客） | `GuestBaseTest`（`framework/tests/guest/guest_base_test.py`） | class 级共享（`class_page`），无登录态 | 首页 `/` |
| user（登录用户） | `UserBaseTest`（`framework/tests/user/user_base_test.py`） | class 级共享（`user_class_page`）+ storage_state | 首页 `/` |

两个角色都满足决策树的 class 级共享条件：同一域名、前置统一（访客无前置；登录用户的前置在
创建 context 时由 storageState 一次完成）、起点统一为首页。每个用例开始前由 function 级
autouse fixture `_reset_to_home` 导航回首页并断言 `is_page_loaded()`：同一 context 内再导航约 0.4s，
比先判断「是否偏离起点」更快，也能清掉输入框草稿、切走的 tab 这类残留。

基类注入的属性：`GuestBaseTest` → `self.guest_page` / `self.guest_home`；
`UserBaseTest` → `self.user_page` / `self.user_home`（`*_home` 均为 `HomePage` 实例）。

## 登录态

alva.ai 只支持 Google 与邮箱验证码登录，没有 token 直登入口，因此登录用户的用例复用
Playwright storageState（cookie + localStorage 快照），而不是每个用例自动登录。

- **生成**：`.venv/bin/python framework/tools/save_auth_state.py --env prod` 打开有头浏览器并进入 `/login`，
  由人手动登录后回终端按回车；脚本回到首页确认已登录才保存，确认不了就不写文件。
  推荐邮箱验证码 —— Google 可能拦截自动化工具启动的浏览器。
- **存放**：`.auth/prod_user.json`（路径由 `settings.py` 的 `ENVS["prod"]["storage_state"]` 决定，权限 600）。
  文件等同于账号凭据，`.auth/` 不入库，也不要贴进 issue 或日志。
- **缺失**：`user_class_page` 直接 skip 并提示生成命令 —— 新克隆的仓库或没配凭据的机器上，
  登录用例本来就跑不了，不该算失败。
- **失效**：`UserBaseTest` 每个 class 打开首页一次，先确认 `is_page_loaded()`，再用 `HomePage.is_logged_in()`
  判定：侧边栏仍有「Log in」按钮即 `pytest.fail` 并提示重新生成。先判加载再判登录，是因为页面没渲染出来时
  「Log in」按钮同样不可见，顺序反了会把「没加载完」当成「已登录」。这里故意用 fail 而不是 skip：
  文件存在却失效，说明登录态过期了，skip 会让整组登录用例悄无声息地不跑。登录态的有效期由站点决定，
  项目不做假设，失效就重新生成。

## 决策树

详见 [architecture skill](../.claude/skills/architecture/SKILL.md)
