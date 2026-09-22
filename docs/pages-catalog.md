# PageObject 清单

> 新增页面时在此追加。格式：`类名 | 文件 | 方法列表 | 是否脱离门户布局`

| 类名 | 文件路径 | 主要方法 | 脱离门户 |
|------|---------|---------|---------|
| HomePage | framework/pages/home_page.py | open / is_page_loaded / is_header_action_visible / click_agent_tab / is_tab_visible / is_tab_selected / get_suggestion_count / get_suggestion_titles / fill_chat_input / get_chat_input_value / clear_chat_input / is_send_enabled / is_send_disabled / is_logged_in（另有 click_connect_portfolio / click_connect_im / click_agent_settings / click_suggestion，均为写操作或外部授权入口，只读冒烟禁用） | 否（首页即起点） |
| SidebarNav（组件） | framework/pages/components/sidebar_nav.py | click_home / click_collapse / click_new_chat / click_alva_agent / click_explore / click_portfolio / click_markets / is_nav_item_visible / click_login / is_login_button_visible / is_logged_in / is_page_loaded | 否（全站共享左侧栏，经 HomePage.sidebar 持有） |

## 页面说明

### HomePage — Alva Agent 首页（`/`）

- 所有角色用例的起点页；`is_page_loaded()` 走模式 C：h1「Alva」+ Agent tab 栏 + **「Chat」tab 选中态** + 聊天输入框，
  切到其他 tab 后返回 False，复位与往返闭合都靠它识别「停在起点」。
- Agent 分区 tab（Chat / Tasks / Alerts / Memory / Files）切换不跳页，只改 URL 为 `/?tab=<name>`；切回 Chat 后 URL 回到 `/`（2026-09-22 访客态实测）。
- 聊天输入框是 Lexical contenteditable：读内容用 `get_chat_input_value()`（inner_text），不能用 input_value。
- 生产站点只读约束：不点发送、不回车、不点建议卡片、不点 Connect Portfolio / Connect IM。

### SidebarNav — 全站左侧栏（组件）

- ROOT 为 P5 结构定位 `div:has(> div > a[href='/new_chat'])`，组件内定位符都相对它。
- 访客态有「Alva」导航项与底部「Log in」；登录态没有「Alva」项（前端 showAgentNavItem=false），底部换成头像入口 ——
  登录态结构来自读前端 bundle，尚未用登录态文件实测。
- 跨登录态回首页用 `click_home()`（Logo），`click_alva_agent()` 只适用于访客态。
