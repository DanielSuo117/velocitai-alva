# 回归测试点

> 新增回归点时在此追加。格式：`页面 | 测试点 | 关键定位符 | 定位级别`

| 页面 | 测试点 | 关键定位符 | 级别 |
|------|-------|-----------|------|
| HomePage（访客） | 首页加载（起点状态 + 顶部操作区）`test_guest_home.py::test_home_loaded` | PAGE_HEADING / AGENT_TABLIST / CHAT_TAB_SELECTED / CHAT_INPUT / HEADER_ACTIONS | P0 |
| SidebarNav（访客） | 侧边栏导航项齐全（New Chat / Alva / Explore / Portfolio / Markets）`test_guest_home.py::test_sidebar_nav_items` | ROOT + NAV_ITEMS | P5 + P0 |
| HomePage（访客） | Agent 分区 tab 齐全、逐个切换选中、切回 Chat 往返闭合 `test_guest_home.py::test_agent_tabs` | AGENT_TABS（*_TAB / *_TAB_SELECTED） | P0 |
| SidebarNav（访客） | 未登录态展示「Log in」登录入口 `test_guest_home.py::test_login_entry_visible` | LOGIN_BUTTON | P0 |
| HomePage（访客） | Chat 面板建议卡片 ≥1 且每张有标题（不写死文案/数量）`test_guest_home.py::test_suggestion_cards` | SUGGESTION_CARD | P4+P3 |
| HomePage（访客） | 输入框输入后发送按钮可用、清空后恢复禁用（绝不发送）`test_guest_home.py::test_chat_input_toggles_send_button` | CHAT_INPUT / SEND_BUTTON_ENABLED / SEND_BUTTON_DISABLED | P0 / P5 |
| HomePage（登录用户） | 登录态首页加载且已登录 `test_user_home.py::test_home_loaded_logged_in` | PAGE_HEADING / CHAT_INPUT / SidebarNav.LOGIN_BUTTON（等其消失） | P0 |
| LoginPage（访客）⚠️ 脱离门户布局 | 首页左下角 Log in 进入登录页（URL 路径 /login），点「Alva」返回首页起点 `test_guest_login.py::test_login_page_round_trip` | SidebarNav.LOGIN_BUTTON / PAGE_HEADING / EMAIL_INPUT / BACK_TO_HOME_LINK | P0 |
| LoginPage（访客） | 登录方式齐全（Google / X / Telegram / Discord / 邮箱）+ 条款链接可见且 href 正确（不点击）`test_guest_login.py::test_login_options_visible` | LOGIN_OPTIONS / LEGAL_LINKS | P0 + P4 |
| LoginPage（访客） | 邮箱框为空时无提交按钮、填合法假地址可用、填非法格式禁用、清空后消失（绝不提交）`test_guest_login.py::test_email_input_toggles_submit_button` | EMAIL_INPUT / SUBMIT_EMAIL_BUTTON / SUBMIT_EMAIL_ENABLED / SUBMIT_EMAIL_DISABLED | P0 |

## 关键定位符

定位符均于 2026-09-22 在 https://alva.ai/ 访客态实测：1280x900 与 1024x768 两种视口下 count()==1 且可见
（SUGGESTION_CARD 为同构多元素，断言 ≥1；各 `*_SELECTED` 与 SEND_BUTTON_ENABLED 是状态型，起点时 count()==0）。

| 定位符 | 选择器 | 说明 |
|-------|-------|------|
| HomePage.PAGE_HEADING | `role=heading[name='Alva' s][level=1]` | 全页唯一 h1 |
| HomePage.AGENT_TABLIST | `role=tablist[name='Agent sections' s]` | Tasks 面板里嵌有另一组 role=tab，所有 tab 定位符都圈在它之内 |
| HomePage.CHAT_TAB_SELECTED | `role=tablist[name='Agent sections' s] >> role=tab[name='Chat' s][selected=true]` | 起点判据，锁定到具体 tab 名 |
| HomePage.CHAT_INPUT | `role=textbox[name=/^Ask Alva anything/]` | `role=` 引擎的 name 是整串匹配，前缀匹配必须写正则 |
| HomePage.SUGGESTION_CARD | `css=[data-testid='agent-chat-tab'] [data-chat-v2-turn-id*='onboarding'] button` | 圈在 Chat 面板内，Alerts 面板有同款卡片 |
| HomePage.SEND_BUTTON_ENABLED / DISABLED | `css=div:has(> button[aria-label='Start voice input']) + div > button:enabled` / `:disabled` | 发送按钮无文字无 aria-label，以语音按钮锚定 |
| SidebarNav.ROOT | `div:has(> div > a[href='/new_chat'])` | 侧边栏无语义节点，P5 结构定位 |
| SidebarNav.LOGIN_BUTTON | `role=button[name=/^Log in/]` | 可及名称是「Log in Log in」；备选 `[data-testid='sidebar-login']`（P4） |

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
