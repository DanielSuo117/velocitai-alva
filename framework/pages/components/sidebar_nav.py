# 页面名称：全站左侧栏导航（组件）
"""alva.ai 左侧栏 —— 所有页面共用同一份，所以做成组件，而不是塞进某个页面对象。

两种登录态渲染的是两条不同的前端分支（2026-09-22 读前端 bundle 确认）：
- 访客态：Collapse / Logo / New Chat / Alva / Explore / Portfolio / Markets，底部是「Log in」。
- 登录态：同样的头部与导航，但**没有「Alva」导航项**（前端传了 showAgentNavItem=false），
  底部换成用户头像入口，中间多出会话历史列表。
所以「回首页」请用 click_home()（Logo，两种状态都在），click_alva_agent() 只适用于访客态。

这里只能验证访客态：登录态的结构来自对前端源码的阅读，拿到登录态文件后应当实测补全。
"""
from __future__ import annotations

from core.base.base_component import BaseComponent


class SidebarNav(BaseComponent):
    # 定位符 — 来自真实页面（2026-09-22，URL: https://alva.ai/）
    # 根节点：侧边栏没有 nav/aside/role 语义节点，也没有 id / data-testid，class 又全是
    # Tailwind 工具类（禁用），只能用 P5 结构定位 —— 取「直接子 div 里就是 /new_chat 链接」
    # 的那一层容器。/new_chat 是路由，比样式稳定；两种登录态都把 New Chat 平铺在这一层，全页唯一。
    # 必须是纯 CSS、不能带 css= 前缀：自愈采快照时用 document.querySelector(ROOT) 圈定范围。
    ROOT = "div:has(> div > a[href='/new_chat'])"   # P5: 侧边栏内容容器（头部、导航、底部账号区都在其内）

    # 组件内的定位符都是相对 ROOT 的。注意 `role=` 引擎（不是 get_by_role）对 name 的匹配：
    # 不带标志与带 s 一样，都是区分大小写的**整串**匹配；带 i 是不区分大小写的整串匹配；都不是子串
    # （2026-09-22 在 Playwright 1.63 上实测：name='Log in' 命中不了「Log in Log in」，
    # name='log in log in' 也命中不了）。要按前缀/子串匹配只能写正则 name=/^.../。
    # 这里统一显式带 s，把「精确匹配」写在明面上，不依赖默认行为。
    COLLAPSE_BUTTON = "role=button[name='Collapse' s]"   # P0: 折叠/展开侧边栏按钮（名称来自 title，折叠后仍叫 Collapse）
    LOGO_LINK = "css=button[title='Collapse'] ~ a[href='/']"   # P5: 顶部 Logo 链接，回首页（纯 SVG 无可及名称；两种登录态都在）
    NEW_CHAT_LINK = "role=link[name='New Chat' s]"   # P0: 「New Chat」新建会话链接（/new_chat）
    AGENT_LINK = "role=link[name='Alva' s]"   # P0: 「Alva」导航项，即 Agent 首页（/；仅访客态渲染）
    EXPLORE_LINK = "role=link[name='Explore' s]"   # P0: 「Explore」导航项（/explore）
    PORTFOLIO_LINK = "role=link[name='Portfolio' s]"   # P0: 「Portfolio」导航项（/portfolio）
    MARKETS_BUTTON = "role=button[name='Markets' s]"   # P0: 「Markets」按钮（弹出 Search companies 搜索浮层，不跳路由）
    # 可及名称是「Log in Log in」（头像 alt + 文字各一份），写成 'Log in' 整串匹配不上；
    # 把重复文案原样写进去又会在前端修掉 alt 时失效，所以用正则只锚定前缀。
    # 元素另有 data-testid="sidebar-login"（P4），P0 失效时可作替补。
    LOGIN_BUTTON = "role=button[name=/^Log in/]"   # P0: 底部「Log in」登录入口（仅访客态；点击跳 /login）

    # 导航项可见文案 → 定位符，供用例按名字数据驱动校验「导航齐全」。
    # 「Alva」只在访客态出现，登录态用例不要拿全量清单去断言。
    NAV_ITEMS = {
        "New Chat": NEW_CHAT_LINK,
        "Alva": AGENT_LINK,
        "Explore": EXPLORE_LINK,
        "Portfolio": PORTFOLIO_LINK,
        "Markets": MARKETS_BUTTON,
    }

    # 登录态判定的「沉淀时间」：见 is_logged_in() 为什么要等
    LOGIN_SETTLE_TIMEOUT = 5000

    # ── 头部 ────────────────────────────────────────────────────────
    def click_collapse(self):
        """折叠/展开侧边栏。是开关：再点一次恢复。"""
        self.click(self.COLLAPSE_BUTTON)

    def click_home(self):
        """点 Logo 回首页。两种登录态都在，是跨状态回首页的首选入口。"""
        self.click(self.LOGO_LINK)

    # ── 导航 ────────────────────────────────────────────────────────
    def click_new_chat(self):
        self.click(self.NEW_CHAT_LINK)

    def click_alva_agent(self):
        """点「Alva」导航项回 Agent 首页。仅访客态存在，登录态请用 click_home()。"""
        self.click(self.AGENT_LINK)

    def click_explore(self):
        self.click(self.EXPLORE_LINK)

    def click_portfolio(self):
        self.click(self.PORTFOLIO_LINK)

    def click_markets(self):
        """打开 Markets 搜索浮层（Search companies），不离开当前页面。"""
        self.click(self.MARKETS_BUTTON)

    def is_nav_item_visible(self, name: str) -> bool:
        """name 取 NAV_ITEMS 的键，即导航项在页面上的可见文案。"""
        return self.is_visible(self.NAV_ITEMS[name])

    # ── 账号区 ──────────────────────────────────────────────────────
    def click_login(self):
        """访客态点「Log in」，页面跳到 /login。"""
        self.click(self.LOGIN_BUTTON)

    def is_login_button_visible(self, timeout: int | None = None) -> bool:
        """「Log in」按钮是否可见。

        「不可见」本身就是合法答案（登录态下它本来就不存在），所以不走自愈：
        自愈开启时，is_visible() 等不到元素会被当成定位失效，去页面上找个「像
        登录按钮」的元素顶上 —— 登录态下极可能顶替到用户头像入口，把「已登录」
        误判成「未登录」。
        """
        return self._wait_state(self.LOGIN_BUTTON, "visible", timeout)

    def is_logged_in(self, settle_timeout: int | None = None) -> bool:
        """依据侧边栏「Log in」按钮是否消失判断是否已登录。

        两个顺序问题决定了这里的写法：
        1. 必须先确认侧边栏渲染出来了 —— 页面还没渲染时「Log in」同样不可见，
           直接判会把「没加载完」误判成「已登录」。
        2. 已登录时要等「Log in」**消失**，而不是看一眼它在不在：登录态存在
           JWT cookie 里，若服务端首屏按访客渲染、客户端水合后才切换，「Log in」
           会先闪现一下。所以访客态要等满 settle_timeout 才返回 False（慢是
           刻意的），登录态一旦确认按钮不在就立刻返回 True。

        局限：前端只解析 JWT 不校验过期（useIsLogin = JWT 能解出 sub），服务端
        已吊销但 cookie 未过期的会话这里仍会判为已登录。
        """
        if not self.is_page_loaded():
            return False
        timeout = self.LOGIN_SETTLE_TIMEOUT if settle_timeout is None else settle_timeout
        return self._wait_state(self.LOGIN_BUTTON, "hidden", timeout)

    # ── 内部 ────────────────────────────────────────────────────────
    def _wait_state(self, selector: str, state: str, timeout: int | None) -> bool:
        """等待元素进入某个状态，等不到返回 False，且**不触发自愈**。

        用于「否定答案也合法」的状态判定（元素不存在 / 已消失）。走 _act() 的
        is_visible() 会把超时当定位失效去自愈，这里必须绕开，理由同基类
        get_element_count()。timeout 不能传 0 —— Playwright 里 0 表示永不超时。
        """
        try:
            kwargs = {"timeout": timeout} if timeout is not None else {}
            self._locate(selector).wait_for(state=state, **kwargs)
            return True
        except Exception:
            return False

    def is_page_loaded(self) -> bool:
        """侧边栏已渲染：以两种登录态都有的 New Chat 为准。

        覆盖基类「根节点存在即加载」的判定：根节点本身就是靠 New Chat 链接
        定位出来的，存在不代表可见（窄屏下整个侧边栏被 CSS 隐藏）。
        """
        return self.is_visible(self.NEW_CHAT_LINK)
