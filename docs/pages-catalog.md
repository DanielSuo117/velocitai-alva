# PageObject 清单

> 新增页面时在此追加。格式：`类名 | 文件 | 方法列表 | 是否脱离门户布局`

| 类名 | 文件路径 | 主要方法 | 脱离门户 |
|------|---------|---------|---------|
| HomePage | framework/pages/home_page.py | open / is_page_loaded / is_header_action_visible / click_agent_tab / is_tab_visible / is_tab_selected / get_suggestion_count / get_suggestion_titles / fill_chat_input / get_chat_input_value / clear_chat_input / is_send_enabled / is_send_disabled / is_logged_in（另有 click_connect_portfolio / click_connect_im / click_agent_settings / click_suggestion，均为写操作或外部授权入口，只读冒烟禁用） | 否（首页即起点） |
| SidebarNav（组件） | framework/pages/components/sidebar_nav.py | click_home / click_collapse / click_new_chat / click_alva_agent / click_explore / click_portfolio / click_markets / is_nav_item_visible / click_login / is_login_button_visible / is_logged_in / is_page_loaded | 否（全站共享左侧栏，经 HomePage.sidebar 持有） |
| LoginPage | framework/pages/login_page.py | open / click_back_to_home / is_login_option_visible / wait_for_interactive / fill_email / get_email_value / clear_email / is_submit_email_enabled / is_submit_email_disabled / is_submit_email_absent / is_legal_link_visible / get_legal_link_href / is_page_loaded（另有 click_submit_email / click_login_with_google / click_login_with_x / click_login_with_telegram / click_login_with_discord，会发验证码或跳第三方授权，只读冒烟禁用） | ⚠️ 是（无侧边栏，经 click_back_to_home 点「Alva」Logo 返回首页） |

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
