# PageObject 清单

> 新增页面时在此追加。格式：`类名 | 文件 | 方法列表 | 是否脱离门户布局`

| 类名 | 文件路径 | 主要方法 | 脱离门户 |
|------|---------|---------|---------|
| HomePage | framework/pages/home_page.py | open / is_page_loaded / is_header_action_visible / click_chat_tab / click_tasks_tab / click_alerts_tab / click_memory_tab / click_files_tab / click_agent_tab / is_tab_visible / is_tab_selected / get_suggestion_count / get_suggestion_titles / fill_chat_input / get_chat_input_value / clear_chat_input / is_send_enabled / is_send_disabled / wait_for_reply / get_reply_text / is_logged_in / wait_for_home_url（另有 send_chat_message，真实发送消息，仅经用户同意的对话用例调用；click_connect_portfolio / click_connect_im / click_agent_settings / click_suggestion，均为写操作或外部授权入口，只读用例禁用） | 否（首页即起点） |
| SidebarNav（组件） | framework/pages/components/sidebar_nav.py | click_collapse / click_home / click_new_chat / click_alva_agent / click_explore / click_portfolio / click_markets / is_nav_item_visible / is_section_visible / click_channels / click_channel_alva / is_channel_alva_active / click_login / is_login_button_visible / is_login_button_absent / is_user_menu_visible / is_logged_in / is_page_loaded | 否（全站共享左侧栏，经 HomePage.sidebar 持有） |
| LoginPage | framework/pages/login_page.py | open / click_back_to_home / is_login_option_visible / wait_for_interactive / fill_email / get_email_value / clear_email / is_submit_email_enabled / is_submit_email_disabled / is_submit_email_absent / is_legal_link_visible / get_legal_link_href / is_page_loaded（另有 click_submit_email / click_login_with_google / click_login_with_x / click_login_with_telegram / click_login_with_discord，会发验证码或跳第三方授权，只读冒烟禁用） | ⚠️ 是（无侧边栏，经 click_back_to_home 点「Alva」Logo 返回首页） |

## 页面说明

### BasePage — 页面对象基类（framework/core/base/base_page.py，本项目新增部分）

alva 是服务端渲染 + React 水合：元素可见、`is_page_loaded()` 成立时前端未必已接管节点，水合前的点击、输入不报错却被静默吞掉，
水合后也不会补上（2026-09-22 实测 Agent tab 约 1/12 的点击如此）。

| 成员 | 说明 |
|------|------|
| `REACT_HYDRATED_JS` | `el => Object.keys(el).some(k => k.startsWith('__reactProps$'))`：React 水合时往接管的节点上挂 `__reactProps$<随机串>`，有它才说明事件已绑定 |
| `HYDRATION_POLL_MS` / `HYDRATION_TIMEOUT` | 轮询间隔 50ms / 默认上限 15000ms（实测水合在可见后约 1～2s 内完成） |
| `wait_for_hydrated(selector, timeout=None)` | 轮询该定位符命中的节点，直到出现 `__reactProps$`；超时抛 `TimeoutError`。每轮重新解析 locator，不持有 element handle —— 水合遇到内容不一致时 React 会换掉整个节点，旧 handle 永远等不到。已水合时首轮即返回。非 React 元素会等满超时报错，不会在没接管的节点上继续操作 |
| `click_hydrated(selector, **kwargs)` | 先 `wait_for_hydrated` 再 `click`。页面对象的点击都走它（例外：`click_suggestion` 按序号点、X / Telegram / Discord 图标登录按钮不经自愈直接点，均为只读用例禁用的入口）；`fill_chat_input` / `clear_chat_input` / `LoginPage.fill_email` 等输入方法也先等水合 |

### HomePage — Alva Agent 首页（`/`）

- 所有用例的起点页；`is_page_loaded()` 走模式 C：h1「Alva」+ Agent tab 栏 + **「Chat」tab 选中态** + 聊天输入框，
  切到其他 tab 后返回 False，复位与往返闭合都靠它识别「停在起点」。访客态与登录态通用（2026-09-22 实测两种状态下各定位符 count()==1）。
- Agent 分区 tab（Chat / Tasks / Alerts / Memory / Files）切换不跳页，只改 URL 为 `/?tab=<name>`；切回 Chat 后 URL 回到 `/`
  （2026-09-22 访客态与登录态实测）。登录态 Tasks / Alerts / Files 的 tab 名带计数后缀（如「Tasks (1)」），随账号数据变化，
  所以 `*_TAB` / `*_TAB_SELECTED` 都写成正则：锚定 tab 名 + 可选的「 (数字)」后缀；`AGENT_TABS` 的键是去掉后缀的 tab 名，用例不断言计数。
- 顶部操作区按登录态分两套：`GUEST_HEADER_ACTIONS`（Connect Portfolio / Connect IM / Agent settings，访客与未接入的登录账号）、
  `USER_HEADER_ACTIONS`（Portfolio / Connected IM / Agent settings，仅限已接入券商且已绑定 IM 的账号）；`HEADER_ACTIONS` 是
  `GUEST_HEADER_ACTIONS` 的旧名（当前用例未使用）。`is_header_action_visible()` 两套的键都接受。
  - `PORTFOLIO_BUTTON` 依赖持仓数据异步加载，比输入框晚约 1s 出现。
  - 「Connected IM」不是页面文案：该按钮的 aria-label 是 IM 平台名、文字是 IM 账号名（用户数据），`CONNECTED_IM_BUTTON`
    以「紧挨 Agent settings 且带 aria-label」结构定位，两者都不写死。
- 登录态首页有常驻后台请求，等 `networkidle` 会等满超时；导航用默认的 load，再等关键元素。
- 已登录访问 `/login`：服务端照常返回 200，由前端把 URL 改成 `/`（不是 HTTP 3xx），登录表单全程不渲染。
  等「被送回首页」用 `wait_for_home_url()`（同主机 + 路径 `/`，查询串不影响）；只看 `is_page_loaded()` 可能在 URL 仍是 `/login` 时就成立。
- `is_logged_in()` 委托 `SidebarNav.is_logged_in()`，以用户菜单可见为正向信号，见下节。
- 聊天输入框是 Lexical contenteditable：读内容用 `get_chat_input_value()`（inner_text），不能用 input_value。
- 聊天消息流（2026-09-22 登录态实测）：每轮对话（用户消息 + Alva 回复）是 Chat 面板里一个带 `data-chat-v2-turn-id` 的节点，
  最后一轮另有 `data-chat-v2-last-turn=true`；历史消息在输入框出现之后才异步渲染。发送后约 0.1s 出现新一轮（id 全程不变）；
  生成中轮内有 `data-chat-v2-stream-thinking-status` 节点，生成完毕它消失，出现 `data-chat-v2-final-response=true` 的回复正文
  （外层包整段回复、内层是最终答案，`nth=-1` 取内层），回复实测约 30～42s。
  - `send_chat_message(text) -> turn_id | None`：先等 `CHAT_LAST_TURN`（历史已渲染，上限 `CHAT_HISTORY_TIMEOUT` 15s）再记下已有轮次 id
    —— 否则历史晚到，里面同样文字的旧消息会被当成新发的；然后 `fill_chat_input` → `click_hydrated(SEND_BUTTON_ENABLED)` →
    用 `NEW_TURN_JS` 等「发送前不存在、且含这条消息文字」的一轮（上限 `NEW_TURN_TIMEOUT` 15s），返回它的 id，等不到返回 None。
  - 按 id 锁定自己发的那一轮：Portfolio Watch 等自动通知也会插入新的一轮，只看最后一轮会串台。
  - `wait_for_reply(turn_id, timeout=None) -> bool`：等 `CHAT_REPLY_DONE`（模板，填 turn_id：该轮内已无生成中标记、回复正文已出现）可见，
    缺省上限 `REPLY_TIMEOUT` 180s（留足余量），超时返回 False，不走自愈。`get_reply_text(turn_id)` 取最终答案正文，先 `wait_for_reply` 再调用。
- 生产站点约束：不点建议卡片、不点 Connect Portfolio / Connect IM，登录态另外不点 Portfolio / 已绑定 IM 按钮；
  不点发送、不回车 —— 唯一例外是经用户同意的对话用例（`test_alva_agent_chat.py`）调用 `send_chat_message` 发一条提示词。

### SidebarNav — 全站左侧栏（组件）

- ROOT 为 P5 结构定位 `div:has(> div > a[href='/new_chat'])`，组件内定位符都相对它；`is_page_loaded()` 以两种登录态都有的 New Chat 为准。
- 两种登录态是两条前端分支（2026-09-22 无头实测，1280x900 与 1024x768 结构一致）：
  - 访客态：导航项 New Chat / Alva / Explore / Portfolio / Markets（`GUEST_NAV_ITEMS`，旧名 `NAV_ITEMS`），底部「Log in」。
  - 登录态：导航区没有「Alva」项（`USER_NAV_ITEMS`：New Chat / Explore / Portfolio / Markets），其下是 Channels / Playbooks / Chats
    三个分区（`USER_SECTIONS`，标题为 role=heading），底部是用户菜单按钮（`USER_MENU_BUTTON`）。分区下的频道 / playbook / 会话列表是账号数据，
    只校验分区标题（`is_section_visible()`），不做定位符、不断言内容与条数。
  - `USER_NAV_ITEMS` 是 `GUEST_NAV_ITEMS` 的子集，`is_nav_item_visible()` 两套的键都接受。
- `AGENT_LINK`（「Alva」）在登录态同样命中 1 个 —— 那是 Channels 分区里的内置「Alva」频道（同名、同指向 `/`），**不能**用来区分登录态。
  跨登录态回首页首选 `click_home()`（Logo）。
- 登录态判定 `is_logged_in()`：侧边栏已渲染 → 用户菜单可见（正向信号，访客态等满 `LOGIN_SETTLE_TIMEOUT` 才返回 False）→「Log in」不可见（辅助）。
  不以「Log in 消失」为准：页面没渲染完、侧边栏被隐藏时它同样成立，会把「没加载完」误判成「已登录」。
  局限：前端只解析 JWT 不校验过期，服务端已吊销但 cookie 未过期的会话仍判为已登录。
- Channels 分区（2026-09-22 登录态实测）：标题 h1 与频道列表同在一个 div 里，没有语义节点 / testid，以「直接子 div 里有 Channels 标题」
  的结构圈定分区（P5），再在分区内定位：
  - `click_channels()` 点 `CHANNELS_TITLE`（标题文字 span）。实测没有任何效果（分区不折叠、页面不跳转，列表始终展开），只对应用户的操作步骤。
    标题右端内嵌「New Channel」按钮，点中会新建频道 —— 所以定位落在文字 span 上，绝不能点整个标题。
  - `click_channel_alva()` 点 `CHANNEL_ALVA_LINK`：分区内置的「Alva」频道（href=/），进入 Alva agent 首页。
  - `is_channel_alva_active(timeout=None)` 等 `CHANNEL_ALVA_ACTIVE`：当前所在频道的列表项外层带 `data-active=true`，在 /explore 等其他页面 count()==0；
    缺省上限 `STATE_TIMEOUT` 5s，不走自愈。
- `is_user_menu_visible()` / `is_login_button_visible()` / `is_login_button_absent()` / `is_section_visible()` 都**不走自愈**：
  「不存在」是合法答案，自愈可能拿「Log in」顶替用户菜单（或反之），把登录态判反。断言「没有 Log in」用 `is_login_button_absent()`，
  不要对 `is_login_button_visible()` 取反（登录态下要等满超时）。

### LoginPage — 登录页（`/login`）

- 入口：首页左下角「Log in」（`SidebarNav.click_login()`），是**整页跳转**而非 SPA 路由；未登录访问 `/settings` 等页面会被重定向到 `/login?returnTo=<原路径>`。
- 封装范围到邮箱输入为止：「Alva」Logo、h1「Your AI Investing Agent」、Google / X / Telegram / Discord 登录按钮、邮箱框与「Submit email」按钮、Terms of Service / Privacy Policy 链接。
- ⚠️ 跳转目标脱离门户布局：登录页没有侧边栏，用例须经 `click_back_to_home()`（点「Alva」Logo）往返闭合回首页。
- `is_page_loaded()` 走模式 B：h1「Your AI Investing Agent」+ 邮箱框，两者在首页上 count()==0。
- 水合空窗：标题与邮箱框约 0.45s 可见，React 约 1.6s 才水合；水合前 fill 的值不进前端状态，「Submit email」永不出现。`fill_email()` 已内置 `wait_for_interactive()`（2026-09-22 无头实测，连续 3 次复现）。
- 「Submit email」按钮三态（2026-09-22 实测）：邮箱框为空时不渲染；格式合法时可用；有内容但格式不合法时禁用；清空后再次消失。
- X / Telegram / Discord 是纯图标按钮（无可及名称），只能靠 `data-testid=login-popup-{twitter,telegram,discord}` 定位，用途由 testid 与图标（X 字标、Telegram 蓝底纸飞机、Discord 紫底）确认。
- 生产站点只读约束：不点「Submit email」、不在邮箱框回车（会往该邮箱发验证码）、不点四个第三方登录按钮；邮箱框只填 `example.com` 假地址并清空。
- 提交邮箱之后的流程（6 位验证码 + Cloudflare Turnstile）不在封装范围，见 [architecture.md「登录态」](./architecture.md#登录态)。
