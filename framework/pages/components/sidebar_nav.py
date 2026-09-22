# 页面名称：全站左侧栏导航（组件）
"""alva.ai 左侧栏 —— 所有页面共用同一份，所以做成组件，而不是塞进某个页面对象。

两种登录态渲染的是两条不同的前端分支（2026-09-22 无头 Chromium 实测，1280x900 与 1024x768 下
侧边栏都是展开可见的，结构一致）：
- 访客态：Collapse / Logo / New Chat / Alva / Explore / Portfolio / Markets，底部是「Log in」
  （外层 data-testid=sidebar-login）。
- 登录态：同样的 Collapse / Logo / New Chat / Explore / Portfolio / Markets，但导航区**没有「Alva」项**；
  下面依次是三个分区，标题都是 role=heading：
    · Channels —— 标题里内嵌一个「New Channel」按钮，所以标题的可及名称是「Channels New Channel」；
      列表第一项是内置的「Alva」频道（href=/，与访客态「Alva」导航项同名同指向）；
    · Playbooks、Chats —— 列表是账号自己的 playbook / 会话，属于用户数据，不做定位符；
  底部是用户菜单按钮（aria-haspopup=menu，内含 data-testid=sidebar-user 的头像 + 用户名 + 套餐）。
所以「回首页」请用 click_home()（Logo，两种状态都在）。

登录态判定以「用户菜单可见」为正向信号，「Log in 不可见」只做辅助，见 is_logged_in()。
"""
from __future__ import annotations

from core.base.base_component import BaseComponent


class SidebarNav(BaseComponent):
    # 定位符 — 来自真实页面（2026-09-22，URL: https://alva.ai/，访客态 + 登录态）
    # 根节点：侧边栏没有 nav/aside/role 语义节点，也没有 id / data-testid，class 又全是
    # Tailwind 工具类（禁用），只能用 P5 结构定位 —— 取「直接子 div 里就是 /new_chat 链接」
    # 的那一层容器。/new_chat 是路由，比样式稳定；两种登录态都把 New Chat 平铺在这一层，全页唯一。
    # 必须是纯 CSS、不能带 css= 前缀：自愈采快照时用 document.querySelector(ROOT) 圈定范围。
    ROOT = "div:has(> div > a[href='/new_chat'])"   # P5: 侧边栏内容容器（头部、导航、分区、底部账号区都在其内）

    # 组件内的定位符都是相对 ROOT 的。注意 `role=` 引擎（不是 get_by_role）对 name 的匹配：
    # 不带标志与带 s 一样，都是区分大小写的**整串**匹配；带 i 是不区分大小写的整串匹配；都不是子串
    # （2026-09-22 在 Playwright 1.63 上实测：name='Log in' 命中不了「Log in Log in」，
    # name='log in log in' 也命中不了）。要按前缀/子串匹配只能写正则 name=/^.../。
    # 这里统一显式带 s，把「精确匹配」写在明面上，不依赖默认行为。
    COLLAPSE_BUTTON = "role=button[name='Collapse' s]"   # P0: 折叠/展开侧边栏按钮（名称来自 title，折叠后仍叫 Collapse）
    LOGO_LINK = "css=button[title='Collapse'] ~ a[href='/']"   # P5: 顶部 Logo 链接，回首页（纯 SVG 无可及名称；两种登录态都在）
    NEW_CHAT_LINK = "role=link[name='New Chat' s]"   # P0: 「New Chat」新建会话链接（/new_chat）
    # 访客态是导航区的「Alva」项；登录态导航区没有它，但 Channels 分区的内置「Alva」频道同名同 href，
    # 这个定位符在登录态同样命中 1 个（2026-09-22 实测）—— 所以它不能用来区分登录态。
    AGENT_LINK = "role=link[name='Alva' s]"   # P0: 「Alva」入口，即 Agent 首页（/；访客态在导航区，登录态是 Channels 里的内置频道）
    EXPLORE_LINK = "role=link[name='Explore' s]"   # P0: 「Explore」导航项（/explore）
    PORTFOLIO_LINK = "role=link[name='Portfolio' s]"   # P0: 「Portfolio」导航项（/portfolio）
    MARKETS_BUTTON = "role=button[name='Markets' s]"   # P0: 「Markets」按钮（弹出 Search companies 搜索浮层，不跳路由）
    # 可及名称是「Log in Log in」（头像 alt + 文字各一份），写成 'Log in' 整串匹配不上；
    # 把重复文案原样写进去又会在前端修掉 alt 时失效，所以用正则只锚定前缀。
    # 元素另有 data-testid="sidebar-login"（P4），P0 失效时可作替补。
    LOGIN_BUTTON = "role=button[name=/^Log in/]"   # P0: 底部「Log in」登录入口（仅访客态；点击跳 /login）

    # ── 登录态专属（访客态下 count()==0，2026-09-22 实测） ──────────────
    # 用户菜单按钮的可及名称是「<用户名> <用户名> <套餐>」、id 是 radix 动态值，都不能用；
    # 稳定的是它内部头像区的 data-testid=sidebar-user，外层 button 带 aria-haspopup=menu。
    # 圈定到外层 button：可见性、以后若要点开菜单，作用对象都是它。
    USER_MENU_BUTTON = "css=button[aria-haspopup='menu']:has([data-testid='sidebar-user'])"   # P4+P3: 底部用户菜单按钮（仅登录态；不含用户名）
    # 分区标题：Channels 标题内嵌「New Channel」按钮，可及名称是「Channels New Channel」，只锚前缀；
    # Playbooks / Chats 目前是整串，同样写前缀，免得哪天也塞进按钮就失效。
    # 标题目前是 h1 级（level=1），级别属实现细节，不写进定位符。
    CHANNELS_HEADING = "role=heading[name=/^Channels/]"   # P0: 「Channels」分区标题（仅登录态）
    PLAYBOOKS_HEADING = "role=heading[name=/^Playbooks/]"   # P0: 「Playbooks」分区标题（仅登录态）
    CHATS_HEADING = "role=heading[name=/^Chats/]"   # P0: 「Chats」分区标题（仅登录态）

    # Channels 分区：标题 h1 与频道列表同在一个 div 里，没有语义节点 / testid，只能以「直接子 div 里有
    # Channels 标题」的结构圈定分区，再在分区内按可及名称找频道（2026-09-22 实测各命中 1 个）。
    # 点标题要点在文字 span 上：标题右端内嵌「New Channel」按钮，点中它会新建频道。
    # 点标题文字没有任何效果（不折叠、不跳转，2026-09-22 实测），分区列表始终展开。
    CHANNELS_TITLE = "css=div:has(> div > h1:has-text('Channels')) h1 > span:text-is('Channels')"   # P5+P1: 「Channels」分区标题文字（仅登录态）
    CHANNEL_ALVA_LINK = "css=div:has(> div > h1:has-text('Channels')) >> role=link[name='Alva' s]"   # P5+P0: Channels 分区内置的「Alva」频道，即 Alva agent 首页（/）
    # 当前所在频道的列表项外层带 data-active=true；在 /explore 等其他页面时 count()==0
    CHANNEL_ALVA_ACTIVE = "css=div:has(> div > h1:has-text('Channels')) [data-active='true'] > a[href='/']"   # P5+P3: 「Alva」频道处于选中态

    # 导航项可见文案 → 定位符，供用例按名字数据驱动校验「导航齐全」。两种登录态各一套：
    # 登录态导航区没有「Alva」（它挪进了 Channels 分区，属于频道列表，不算导航项）。
    GUEST_NAV_ITEMS = {
        "New Chat": NEW_CHAT_LINK,
        "Alva": AGENT_LINK,
        "Explore": EXPLORE_LINK,
        "Portfolio": PORTFOLIO_LINK,
        "Markets": MARKETS_BUTTON,
    }
    USER_NAV_ITEMS = {
        "New Chat": NEW_CHAT_LINK,
        "Explore": EXPLORE_LINK,
        "Portfolio": PORTFOLIO_LINK,
        "Markets": MARKETS_BUTTON,
    }
    # 缺省指向访客态那一套（它是两套的并集），is_nav_item_visible 按它查；登录态请用 USER_NAV_ITEMS
    NAV_ITEMS = GUEST_NAV_ITEMS

    # 登录态分区标题可见文案 → 定位符。分区下的列表是用户数据，只校验标题
    USER_SECTIONS = {
        "Channels": CHANNELS_HEADING,
        "Playbooks": PLAYBOOKS_HEADING,
        "Chats": CHATS_HEADING,
    }

    # 登录态判定的「沉淀时间」：见 is_logged_in() 为什么要等
    LOGIN_SETTLE_TIMEOUT = 5000
    # 频道选中态是前端状态更新，毫秒级
    STATE_TIMEOUT = 5000

    # ── 头部 ────────────────────────────────────────────────────────
    def click_collapse(self):
        """折叠/展开侧边栏。是开关：再点一次恢复。"""
        self.click_hydrated(self.COLLAPSE_BUTTON)

    def click_home(self):
        """点 Logo 回首页。两种登录态都在，是跨状态回首页的首选入口。"""
        self.click_hydrated(self.LOGO_LINK)

    # ── 导航 ────────────────────────────────────────────────────────
    def click_new_chat(self):
        self.click_hydrated(self.NEW_CHAT_LINK)

    def click_alva_agent(self):
        """点「Alva」回 Agent 首页。访客态点的是导航项；登录态命中的是 Channels 里的内置
        「Alva」频道（同样回 /）。跨状态回首页仍首选 click_home()。"""
        self.click_hydrated(self.AGENT_LINK)

    def click_explore(self):
        self.click_hydrated(self.EXPLORE_LINK)

    def click_portfolio(self):
        self.click_hydrated(self.PORTFOLIO_LINK)

    def click_markets(self):
        """打开 Markets 搜索浮层（Search companies），不离开当前页面。"""
        self.click_hydrated(self.MARKETS_BUTTON)

    def is_nav_item_visible(self, name: str) -> bool:
        """name 取 GUEST_NAV_ITEMS / USER_NAV_ITEMS 的键，即导航项在页面上的可见文案。"""
        return self.is_visible(self.NAV_ITEMS[name])

    # ── 分区（仅登录态） ────────────────────────────────────────────
    def is_section_visible(self, name: str, timeout: int | None = None) -> bool:
        """登录态分区标题是否可见，name 取 USER_SECTIONS 的键。

        访客态下分区本来就不存在，「不可见」是合法答案，所以不走自愈（理由同
        is_login_button_visible）。
        """
        return self._wait_state(self.USER_SECTIONS[name], "visible", timeout)

    def click_channels(self):
        """点「Channels」分区标题文字。实测没有任何效果（分区不折叠、页面不跳转），只对应用户的操作步骤；
        绝不能点到标题右端的「New Channel」按钮。"""
        self.click_hydrated(self.CHANNELS_TITLE)

    def click_channel_alva(self):
        """点 Channels 分区里的「Alva」频道，进入 Alva agent 首页（/）。"""
        self.click_hydrated(self.CHANNEL_ALVA_LINK)

    def is_channel_alva_active(self, timeout: int | None = None) -> bool:
        """Channels 里的「Alva」频道是否处于选中态（等它变为选中）。"""
        return self._wait_state(self.CHANNEL_ALVA_ACTIVE, "visible",
                                self.STATE_TIMEOUT if timeout is None else timeout)

    # ── 账号区 ──────────────────────────────────────────────────────
    def click_login(self):
        """访客态点「Log in」，页面跳到 /login。"""
        self.click_hydrated(self.LOGIN_BUTTON)

    def is_login_button_visible(self, timeout: int | None = None) -> bool:
        """「Log in」按钮是否可见（等它出现）。

        「不可见」本身就是合法答案（登录态下它本来就不存在），所以不走自愈：
        自愈开启时，is_visible() 等不到元素会被当成定位失效，去页面上找个「像
        登录按钮」的元素顶上 —— 登录态下极可能顶替到用户菜单，把「已登录」
        误判成「未登录」。要断言「没有 Log in」请用 is_login_button_absent()，
        别拿本方法取反：它在登录态下要等满超时才返回 False。
        """
        return self._wait_state(self.LOGIN_BUTTON, "visible", timeout)

    def is_login_button_absent(self, timeout: int | None = None) -> bool:
        """「Log in」按钮是否不存在或不可见（等它消失，已不在时立即返回）。

        只在侧边栏已渲染之后才有意义 —— 页面还没渲染时它同样「不在」。
        """
        timeout = self.LOGIN_SETTLE_TIMEOUT if timeout is None else timeout
        return self._wait_state(self.LOGIN_BUTTON, "hidden", timeout)

    def is_user_menu_visible(self, timeout: int | None = None) -> bool:
        """底部用户菜单按钮是否可见（等它出现）。登录态的正向信号。

        访客态下它本来就不存在，「不可见」是合法答案，不走自愈 —— 自愈可能把它
        顶替成「Log in」按钮，把访客误判成已登录。
        """
        return self._wait_state(self.USER_MENU_BUTTON, "visible", timeout)

    def is_logged_in(self, settle_timeout: int | None = None) -> bool:
        """已登录 = 侧边栏已渲染 + 用户菜单可见（正向信号）+「Log in」不可见（辅助）。

        三步的顺序各有理由：
        1. 先确认侧边栏渲染出来了（New Chat 两种状态都有）—— 否则后面两步的
           「看不见」没有意义。
        2. 以「用户菜单出现」为准，而不是「Log in 消失」：后者在页面没渲染完、
           侧边栏整体被隐藏、登录入口改版等情况下同样成立，会把「没加载完」
           误判成「已登录」；用户菜单只有登录态才渲染，是正向证据。
           访客态要等满 settle_timeout 才返回 False（慢是刻意的：登录态的
           用户菜单可能在水合后才出现）；登录态一出现就立刻进入下一步。
        3. 再确认「Log in」不在：两者同时可见说明页面处于切换中间态或前端异常，
           不算已登录。登录态下它本来就不在，这一步立即返回。

        局限：前端只解析 JWT 不校验过期，服务端已吊销但 cookie 未过期的会话
        这里仍会判为已登录。
        """
        if not self.is_page_loaded():
            return False
        timeout = self.LOGIN_SETTLE_TIMEOUT if settle_timeout is None else settle_timeout
        if not self.is_user_menu_visible(timeout):
            return False
        return self.is_login_button_absent(timeout)

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
