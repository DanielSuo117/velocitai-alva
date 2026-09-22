# 回归测试点

> 新增回归点时在此追加。格式：`页面 | 测试点 | 关键定位符 | 定位级别`

| 页面 | 测试点 | 关键定位符 | 级别 |
|------|-------|-----------|------|
| LoginPage → HomePage | 访问登录页凭 token 免登直接进入首页：先等 URL 路径变为 /（`wait_for_home_url`），再断言首页起点与已登录（用户菜单可见、无「Log in」），登录表单不渲染（只读，`smoke`）`test_login.py::TestLogin::test_login_page_skips_to_home` | HomePage.PAGE_HEADING / AGENT_TABLIST / CHAT_TAB_SELECTED / CHAT_INPUT / SidebarNav.NEW_CHAT_LINK / USER_MENU_BUTTON / LOGIN_BUTTON（等其消失）/ LoginPage.PAGE_HEADING + LoginPage.EMAIL_INPUT（count()==0） | P0 + P4+P3 |
| SidebarNav → HomePage（Alva agent 对话）⚠️ 真实发送消息 | 点 Channels 标题 → 点 Channels 内置「Alva」频道 → Alva agent 首页加载且频道选中 → 发送「查看股票代码为spcx的股票实时行情」→ 等回复完成 → 回复非空且提到 SPCX（`slow`）`test_alva_agent_chat.py::TestAlvaAgentChat::test_ask_spcx_quote` | SidebarNav.CHANNELS_HEADING / CHANNELS_TITLE / CHANNEL_ALVA_LINK / CHANNEL_ALVA_ACTIVE；HomePage 起点判据（PAGE_HEADING / AGENT_TABLIST / CHAT_TAB_SELECTED / CHAT_INPUT）/ SEND_BUTTON_ENABLED / CHAT_LAST_TURN / CHAT_TURN_CSS / CHAT_REPLY_DONE | P0 / P5+P1 / P5+P0 / P5+P3；P0 / P5 / P4+P3 |

两条用例都继承 `AlvaBaseTest`（`tests/base_test.py`），前置每个 class 走一次：往全新 context 注入 authorization cookie
→ 访问 /login → 前端把人送回首页 → 断言首页起点且已登录。拿不到 token 时 skip；有 token 却没被送回首页、或送回后仍显示「Log in」，
按 token 失效 fail。每个用例开始前 `_reset_to_home` 导航回首页并断言起点。侧边栏列表、tab 计数等账号数据不断言。

### Alva agent 对话用例（`test_alva_agent_chat.py`）

- ⚠️ 每跑一次都会在生产站点**真实发送一条消息**（用户 2026-09-22 明确要求），账号的 Alva 频道里多一轮对话；只发这一条提示词，
  不点其他会产生写入的按钮。标记 `slow`，`-m "not slow"` 可跳过。
- 实测时序（2026-09-22 登录态）：发送后约 0.1s 出现新一轮（`NEW_TURN_TIMEOUT` 15s）；回复完成约 30～42s（`REPLY_TIMEOUT` 180s，留足余量）；
  历史消息在输入框出现之后异步渲染（`CHAT_HISTORY_TIMEOUT` 15s）。
- 点 Channels 标题文字没有任何效果（不折叠、不跳转），这一步只为对应用户的操作步骤。标题右端内嵌「New Channel」按钮，点中会新建频道，
  所以 `CHANNELS_TITLE` 落在标题文字 span 上，绝不能点整个标题。
- 按轮次 id（`data-chat-v2-turn-id`）锁定自己发的那一轮：Portfolio Watch 等自动通知也会插入新的一轮，只看最后一轮会串台。
- 回复只断言「非空 + 提到 SPCX（不区分大小写）」，行情数值属数据级内容，不断言；回复全文作为 allure 附件「Alva 回复」。

## 关键定位符

定位符均于 2026-09-22 在 https://alva.ai/ 访客态实测：1280x900 与 1024x768 两种视口下 count()==1 且可见
（SUGGESTION_CARD 为同构多元素，断言 ≥1；各 `*_SELECTED` 与 SEND_BUTTON_ENABLED 是状态型，起点时 count()==0）。
首页起点判据 PAGE_HEADING / AGENT_TABLIST / CHAT_TAB_SELECTED / CHAT_INPUT 在登录态同样唯一命中；登录态专属定位符见下节。

| 定位符 | 选择器 | 说明 |
|-------|-------|------|
| HomePage.PAGE_HEADING | `role=heading[name='Alva' s][level=1]` | P0。全页唯一 h1（登录态侧边栏分区标题虽也是 h1，但名称不同） |
| HomePage.AGENT_TABLIST | `role=tablist[name='Agent sections' s]` | P0。Tasks 面板里嵌有另一组 role=tab，所有 tab 定位符都圈在它之内 |
| HomePage.CHAT_TAB / CHAT_TAB_SELECTED | `role=tablist[name='Agent sections' s] >> role=tab[name=/^Chat(\s*\(\d+\+?\))?$/]` / 同上加 `[selected=true]` | P0。TASKS / ALERTS / MEMORY / FILES 同构，只换 tab 名。name 正则容忍登录态计数后缀（如「Tasks (1)」，`\d+\+?` 兼容「99+」），末尾 `$` 防止误中别的 tab；选中态锁定到具体 tab 名，Chat 选中是起点判据 |
| HomePage.CONNECT_PORTFOLIO_BUTTON / CONNECT_IM_BUTTON / AGENT_SETTINGS_LINK | `role=button[name='Connect Portfolio' s]` / `role=button[name='Connect IM' s]` / `role=link[name='Agent settings' s]` | P0。GUEST_HEADER_ACTIONS（旧名 HEADER_ACTIONS）；Agent settings 两种登录态都在 |
| HomePage.CHAT_INPUT | `role=textbox[name=/^Ask Alva anything/]` | P0。`role=` 引擎的 name 是整串匹配，前缀匹配必须写正则 |
| HomePage.SUGGESTION_CARD | `css=[data-testid='agent-chat-tab'] [data-chat-v2-turn-id*='onboarding'] button` | P4+P3。圈在 Chat 面板内，Alerts 面板有同款卡片 |
| HomePage.SEND_BUTTON_ENABLED / DISABLED | `css=div:has(> button[aria-label='Start voice input']) + div > button:enabled` / `:disabled` | P5。发送按钮无文字无 aria-label，以语音按钮锚定 |
| SidebarNav.ROOT | `div:has(> div > a[href='/new_chat'])` | P5。侧边栏无语义节点，结构定位 |
| SidebarNav.AGENT_LINK | `role=link[name='Alva' s]` | P0。访客态是导航项；登录态命中 Channels 分区里的内置「Alva」频道，同样 count()==1 —— 不能用来区分登录态 |
| SidebarNav.LOGIN_BUTTON | `role=button[name=/^Log in/]` | P0。可及名称是「Log in Log in」；备选 `[data-testid='sidebar-login']`（P4） |

### 登录态关键定位符

2026-09-22 在 https://alva.ai/ 登录态（注入 authorization cookie）无头实测，1280x900 与 1024x768 一致。
SidebarNav 的 USER_MENU_BUTTON 与三个分区标题访客态下 count()==0；HomePage 的 PORTFOLIO_BUTTON / CONNECTED_IM_BUTTON
（USER_HEADER_ACTIONS）只在已接入券商、已绑定 IM 的账号上出现，未接入的登录账号看到的仍是 Connect 系列。

| 定位符 | 选择器 | 说明 |
|-------|-------|------|
| HomePage.PORTFOLIO_BUTTON | `role=button[name='Portfolio' s]` | P0。券商图标在 aria-hidden 的 span 里，不进可及名称；侧边栏同名项是 role=link，不混淆（全页 count()==1）。依赖持仓数据异步加载，晚于输入框约 1s |
| HomePage.CONNECTED_IM_BUTTON | `css=header button[aria-label]:has(+ a[aria-label='Agent settings'])` | P5+P3。aria-label 是 IM 平台名、文字是 IM 账号名，都不写进定位符，以「紧挨 Agent settings 且带 aria-label」锚定；未绑定时同位置是无 aria-label 的「Connect IM」，count()==0 |
| SidebarNav.USER_MENU_BUTTON | `css=button[aria-haspopup='menu']:has([data-testid='sidebar-user'])` | P4+P3。登录态正向信号（`is_logged_in` / `is_user_menu_visible`，不走自愈）。可及名称含用户名与套餐、id 是动态值，都不能用；圈定到外层 button |
| SidebarNav.CHANNELS_HEADING / PLAYBOOKS_HEADING / CHATS_HEADING | `role=heading[name=/^Channels/]` / `role=heading[name=/^Playbooks/]` / `role=heading[name=/^Chats/]` | P0。Channels 标题内嵌「New Channel」按钮，可及名称是「Channels New Channel」，只锚前缀；另两个同样写前缀防改版；不锁 heading level。分区下的列表是账号数据，不做定位符（内置「Alva」频道除外，见下节） |

### 对话用例关键定位符

2026-09-22 在 https://alva.ai/ 登录态实测。Channels 分区没有语义节点 / testid，三个 Channels 定位符都以
「直接子 div 里有 Channels 标题」的结构圈定分区（各命中 1 个）；对话区的轮次节点是同构多个，按 turn id 锁定。

| 定位符 | 选择器 | 说明 |
|-------|-------|------|
| SidebarNav.CHANNELS_TITLE | `css=div:has(> div > h1:has-text('Channels')) h1 > span:text-is('Channels')` | P5+P1。标题文字 span；点它没有任何效果。不能点整个标题：右端内嵌的「New Channel」按钮会新建频道 |
| SidebarNav.CHANNEL_ALVA_LINK | `css=div:has(> div > h1:has-text('Channels')) >> role=link[name='Alva' s]` | P5+P0。分区内置的「Alva」频道（href=/），即 Alva agent 首页 |
| SidebarNav.CHANNEL_ALVA_ACTIVE | `css=div:has(> div > h1:has-text('Channels')) [data-active='true'] > a[href='/']` | P5+P3。当前频道的列表项外层带 data-active=true；在 /explore 等其他页面 count()==0 |
| HomePage.CHAT_TURN_CSS | `[data-testid='agent-chat-tab'] [data-chat-v2-turn-id]` | P4+P3。一轮对话，同构多个；纯 CSS（不带 `css=`），供 NEW_TURN_JS 的 querySelectorAll 使用 |
| HomePage.CHAT_LAST_TURN | `css=[data-testid='agent-chat-tab'] [data-chat-v2-last-turn='true']` | P4+P3。最后一轮，历史消息已渲染的判据 |
| HomePage.CHAT_REPLY_DONE | `css=[data-testid='agent-chat-tab'] [data-chat-v2-turn-id='{turn_id}']:not(:has([data-chat-v2-stream-thinking-status])) [data-chat-v2-final-response='true'] >> nth=-1` | P4+P3。模板，填 turn_id：该轮已无生成中标记、回复正文已出现；final-response 外层包整段回复、内层是最终答案，`nth=-1` 取内层 |

### LoginPage 关键定位符

2026-09-22 在 https://alva.ai/login（从首页点「Log in」进入）访客态实测：1280x900 与 1024x768 两种视口下，
下表静态定位符 count()==1 且可见；PAGE_HEADING / EMAIL_INPUT / SUBMIT_EMAIL_BUTTON 在首页上 count()==0；
提交按钮的三个定位符是状态型，邮箱框为空时 count()==0。

| 定位符 | 选择器 | 说明 |
|-------|-------|------|
| LoginPage.BACK_TO_HOME_LINK | `role=link[name='Alva' s]` | 左上角 Logo（aria-label=Alva，href=/），登录页唯一回首页入口 |
| LoginPage.PAGE_HEADING | `role=heading[name='Your AI Investing Agent' s][level=1]` | 登录页 h1；首页 h1 是「Alva」 |
| LoginPage.GOOGLE_LOGIN_BUTTON | `role=button[name='Log in with Google' s]` | 备选 `[data-testid='login-popup-google']`（P4） |
| LoginPage.X_LOGIN_BUTTON / TELEGRAM_LOGIN_BUTTON / DISCORD_LOGIN_BUTTON | `css=[data-testid='login-popup-twitter']` / `-telegram` / `-discord` | 纯图标按钮，无可及名称，只能 P4。判可见与点击都**不走自愈**：无名称的指纹只剩 {tag: button, role: button}，自愈会拿另一个登录按钮的 testid 顶替（实测删掉 Discord 后被换成 Google，用例照绿） |
| LoginPage.EMAIL_INPUT | `role=textbox[name='Login with Email' s]` | 可及名称来自 placeholder，元素为 input[type=email] |
| LoginPage.SUBMIT_EMAIL_BUTTON | `role=button[name='Submit email' s]` | aria-label；邮箱框为空时不渲染 |
| LoginPage.SUBMIT_EMAIL_ENABLED / DISABLED | 同上加 `[disabled=false]` / `[disabled=true]` | 格式合法可用 / 不合法禁用 |
| LoginPage.TERMS_LINK / PRIVACY_LINK | `role=link[name='Terms of Service' s]` / `role=link[name='Privacy Policy' s]` | target=_blank，用例只校验 href，不点开 |
