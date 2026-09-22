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
