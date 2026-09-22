# 页面名称：Alva Agent 首页
"""alva.ai 首页（/）—— Alva Agent 的对话入口，也是所有用例的起点页。

页面由三块组成：顶部操作区、Agent 分区 tab（Chat / Tasks / Alerts / Memory / Files），
以及 Chat 分区里的 onboarding 建议卡片 + 聊天输入框。左侧栏是全站共享组件，经 self.sidebar 访问。

两种登录态的差异（2026-09-22 无头 Chromium 实测，1280x900 与 1024x768 一致）：
- h1「Alva」、「Agent sections」tab 栏、Chat 默认选中、聊天输入框两种状态都在 —— is_page_loaded() 通用。
- Agent tab 名：访客态是纯文案；登录态 Tasks / Alerts / Files 带计数后缀，如「Tasks (1)」，
  随账号数据变化 —— tab 定位符一律用正则容忍可选的「 (数字)」后缀。
- 顶部操作区：访客态 Connect Portfolio / Connect IM / Agent settings；登录且已接入券商、
  已绑定 IM 的账号是 Portfolio / 已绑定 IM 按钮（aria-label 是 IM 平台名，文字是 IM 账号名）
  / Agent settings。Portfolio 按钮依赖持仓数据异步加载，比输入框晚约 1s 出现。
- 登录态首页有常驻后台请求，等 networkidle 会等满超时；导航用默认的 load，再等关键元素。
- 已登录时访问 /login：服务端照常返回 200，前端在 load 后约 0.7～4s 把 URL 改成 /（多次测量波动），登录表单全程不渲染
  —— 等「被重定向回首页」用 wait_for_home_url()，只看 is_page_loaded() 可能在 URL 仍是 /login 时就成立。

访客态实测行为（2026-09-22），决定了只读冒烟能碰什么：
- 切 Agent tab：不跳页，只把 URL 改成 /?tab=<name>，aria-selected 跟随；切回 Chat 后 URL 回到 /。
- 输入框输入文字：发送按钮由禁用变可用；清空后恢复禁用。只要不点发送、不回车，就没有任何提交。
- 建议卡片：点击会发起 onboarding 流程（前端排队一条 agent 提交，「Build your own
  automations」直接提交一句提示语），等同于发消息 —— 只读冒烟禁止点。
- Connect Portfolio / Connect IM：券商持仓、IM 账号的外部授权入口，只读冒烟禁止点。
"""
from __future__ import annotations

from urllib.parse import urlparse

from playwright.sync_api import Page
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from core.base.base_page import BasePage
from pages.components.sidebar_nav import SidebarNav


class HomePage(BasePage):
    PATH = "/"

    # 定位符 — 来自真实页面（2026-09-22，URL: https://alva.ai/，访客态 + 登录态）
    # `role=` 引擎的 name：不带标志与带 s 都是区分大小写的整串匹配，带 i 才不区分大小写，
    # 都不是子串（与 get_by_role 不同，见 SidebarNav 的说明）；前缀匹配只能写正则 name=/^.../。
    PAGE_HEADING = "role=heading[name='Alva' s][level=1]"   # P0: 首页顶部 h1「Alva」（两种登录态都在；登录态侧边栏分区标题虽也是 h1，但名称不同）

    # ── 顶部操作区 ──
    # 访客态（以及登录但未接入的账号）：
    CONNECT_PORTFOLIO_BUTTON = "role=button[name='Connect Portfolio' s]"   # P0: 顶部「Connect Portfolio」接入持仓按钮（访客 / 未接入券商）
    CONNECT_IM_BUTTON = "role=button[name='Connect IM' s]"   # P0: 顶部「Connect IM」绑定 IM 按钮（访客 / 未绑定 IM）
    # 登录且已接入：券商图标包在 aria-hidden 的 span 里，不进可及名称，所以名称就是「Portfolio」；
    # 侧边栏的同名项是 role=link，不会与这里的 role=button 混淆（2026-09-22 实测全页 count()==1）。
    PORTFOLIO_BUTTON = "role=button[name='Portfolio' s]"   # P0: 顶部「Portfolio」持仓按钮（登录且已接入券商；异步加载，晚于输入框约 1s）
    # 已绑定 IM 按钮：aria-label 是 IM 平台名（取决于绑定了哪个平台），文字是 IM 账号名（用户数据），
    # 两者都不能写死。稳定特征是它紧挨在「Agent settings」前面、且带 aria-label ——
    # 未绑定时同一位置是「Connect IM」，没有 aria-label，所以访客态 count()==0。
    CONNECTED_IM_BUTTON = "css=header button[aria-label]:has(+ a[aria-label='Agent settings'])"   # P5+P3: 顶部已绑定 IM 按钮（登录且已绑定 IM；不含平台名与账号名）
    AGENT_SETTINGS_LINK = "role=link[name='Agent settings' s]"   # P0: 顶部齿轮图标「Agent settings」链接（/settings?tab=alvaAgent；两种登录态都在）

    # ── Agent 分区 tab ──
    # Tasks 面板里还嵌套了一组 All/Active/Done 的 role=tab，所以每个 tab 都圈在「Agent sections」
    # tablist 之内，不能直接写 role=tab。
    # 登录态 tab 名带计数后缀（「Tasks (1)」「Alerts (1)」「Files (1)」，随账号数据变化），访客态没有；
    # 整串匹配会在登录态命中 0 个，所以一律写成正则：锚定 tab 名 + 可选的「 (数字)」后缀，
    # 末尾 $ 保证「Chat」不会误中别的 tab。计数写成 \d+\+? 兼容「99+」这类截断写法。
    AGENT_TABLIST = "role=tablist[name='Agent sections' s]"   # P0: Agent 分区 tab 栏
    CHAT_TAB = r"role=tablist[name='Agent sections' s] >> role=tab[name=/^Chat(\s*\(\d+\+?\))?$/]"   # P0: 「Chat」tab（默认选中）
    TASKS_TAB = r"role=tablist[name='Agent sections' s] >> role=tab[name=/^Tasks(\s*\(\d+\+?\))?$/]"   # P0: 「Tasks」tab（登录态带计数后缀）
    ALERTS_TAB = r"role=tablist[name='Agent sections' s] >> role=tab[name=/^Alerts(\s*\(\d+\+?\))?$/]"   # P0: 「Alerts」tab（登录态带计数后缀）
    MEMORY_TAB = r"role=tablist[name='Agent sections' s] >> role=tab[name=/^Memory(\s*\(\d+\+?\))?$/]"   # P0: 「Memory」tab
    FILES_TAB = r"role=tablist[name='Agent sections' s] >> role=tab[name=/^Files(\s*\(\d+\+?\))?$/]"   # P0: 「Files」tab（登录态带计数后缀）
    # 选中态（aria-selected）会跟着点击漂移，必须锁定到具体 tab 名（.claude/rules/playwright/locator-strategy.md）
    CHAT_TAB_SELECTED = r"role=tablist[name='Agent sections' s] >> role=tab[name=/^Chat(\s*\(\d+\+?\))?$/][selected=true]"   # P0: 「Chat」tab 处于选中态（起点判据）
    TASKS_TAB_SELECTED = r"role=tablist[name='Agent sections' s] >> role=tab[name=/^Tasks(\s*\(\d+\+?\))?$/][selected=true]"   # P0: 「Tasks」tab 处于选中态
    ALERTS_TAB_SELECTED = r"role=tablist[name='Agent sections' s] >> role=tab[name=/^Alerts(\s*\(\d+\+?\))?$/][selected=true]"   # P0: 「Alerts」tab 处于选中态
    MEMORY_TAB_SELECTED = r"role=tablist[name='Agent sections' s] >> role=tab[name=/^Memory(\s*\(\d+\+?\))?$/][selected=true]"   # P0: 「Memory」tab 处于选中态
    FILES_TAB_SELECTED = r"role=tablist[name='Agent sections' s] >> role=tab[name=/^Files(\s*\(\d+\+?\))?$/][selected=true]"   # P0: 「Files」tab 处于选中态

    # 建议卡片没有 role 以外的语义（class 全是 Tailwind），但它们总挂在 Chat 面板
    # （data-testid=agent-chat-tab）里 onboarding 那条消息之下；Alerts 面板里还有一套
    # 长得一样的卡片，所以必须圈在 Chat 面板内。
    SUGGESTION_CARD = "css=[data-testid='agent-chat-tab'] [data-chat-v2-turn-id*='onboarding'] button"   # P4+P3: Chat 面板 onboarding 消息下的建议卡片（同构多个）
    # aria-label 全文是「Ask Alva anything. @ for context, / for skills」，后半段是操作提示、
    # 更可能调整，所以用正则只锚定前缀（写成 name='Ask Alva anything' 是整串匹配，命中不了）
    CHAT_INPUT = "role=textbox[name=/^Ask Alva anything/]"   # P0: 聊天输入框（Lexical 富文本 contenteditable，不是 input）
    # 发送按钮既无文字也无 aria-label，只能以相邻的「Start voice input」按钮锚定：
    # 语音按钮所在 div 的下一个兄弟 div 里的 button。用 :enabled / :disabled 表达状态，
    # 等待可以交给 Playwright，不必轮询。
    SEND_BUTTON_ENABLED = "css=div:has(> button[aria-label='Start voice input']) + div > button:enabled"   # P5: 发送按钮·可用态（输入框有内容时）
    SEND_BUTTON_DISABLED = "css=div:has(> button[aria-label='Start voice input']) + div > button:disabled"   # P5: 发送按钮·禁用态（输入框为空时）

    # ── 聊天消息流（2026-09-22 登录态实测）──
    # 每轮对话（用户消息 + Alva 回复）是 Chat 面板里一个带 data-chat-v2-turn-id 的节点，最后一轮另有
    # data-chat-v2-last-turn=true。历史消息在输入框出现之后才异步渲染。发送后约 0.1s 出现新一轮（id 全程不变）；
    # 生成中轮内有 data-chat-v2-stream-thinking-status 节点；生成完毕它消失，出现 data-chat-v2-final-response=true
    # 的回复正文（外层包整段回复、内层是最终答案，nth=-1 取内层），实测约 42s。
    # 按 id 锁定「自己发的那一轮」：Portfolio Watch 等自动通知也会插入新的一轮，只看最后一轮会串台。
    CHAT_TURN_CSS = "[data-testid='agent-chat-tab'] [data-chat-v2-turn-id]"   # P4+P3: 一轮对话（纯 CSS，供 NEW_TURN_JS 使用；同构多个）
    CHAT_LAST_TURN = "css=[data-testid='agent-chat-tab'] [data-chat-v2-last-turn='true']"   # P4+P3: 最后一轮对话（历史已渲染的判据）
    CHAT_REPLY_DONE = "css=[data-testid='agent-chat-tab'] [data-chat-v2-turn-id='{turn_id}']:not(:has([data-chat-v2-stream-thinking-status])) [data-chat-v2-final-response='true'] >> nth=-1"   # P4+P3: 指定一轮里已生成完毕的回复正文（模板，填 turn_id）
    # 找「发送前不存在、且含这条消息文字」的那一轮，返回它的 id
    NEW_TURN_JS = """([turnCss, knownIds, text]) => {
        for (const turn of document.querySelectorAll(turnCss)) {
            const id = turn.getAttribute('data-chat-v2-turn-id');
            if (!knownIds.includes(id) && turn.innerText.includes(text)) return id;
        }
        return null;
    }"""

    # tab 名（可见文案去掉登录态的计数后缀）→ (tab 定位符, 选中态定位符)，供用例按名字数据驱动
    AGENT_TABS = {
        "Chat": (CHAT_TAB, CHAT_TAB_SELECTED),
        "Tasks": (TASKS_TAB, TASKS_TAB_SELECTED),
        "Alerts": (ALERTS_TAB, ALERTS_TAB_SELECTED),
        "Memory": (MEMORY_TAB, MEMORY_TAB_SELECTED),
        "Files": (FILES_TAB, FILES_TAB_SELECTED),
    }
    # 顶部操作区名称 → 定位符，按登录态各一套。登录态的「Connected IM」不是可见文案
    # （可见文案是 IM 账号名，属用户数据），是这里给它起的名字。
    GUEST_HEADER_ACTIONS = {
        "Connect Portfolio": CONNECT_PORTFOLIO_BUTTON,
        "Connect IM": CONNECT_IM_BUTTON,
        "Agent settings": AGENT_SETTINGS_LINK,
    }
    # 仅适用于已接入券商、已绑定 IM 的账号；未接入的登录账号看到的仍是 Connect 系列
    USER_HEADER_ACTIONS = {
        "Portfolio": PORTFOLIO_BUTTON,
        "Connected IM": CONNECTED_IM_BUTTON,
        "Agent settings": AGENT_SETTINGS_LINK,
    }
    # 缺省指向访客态那一套；登录态请用 USER_HEADER_ACTIONS
    HEADER_ACTIONS = GUEST_HEADER_ACTIONS

    # tab 切换、发送按钮启停都是前端状态更新，毫秒级；等太久只会拖慢「状态不对」时的失败
    STATE_TIMEOUT = 5000
    CHAT_HISTORY_TIMEOUT = 15000   # 历史消息渲染
    NEW_TURN_TIMEOUT = 15000       # 发送后新一轮出现（实测约 0.1s）
    REPLY_TIMEOUT = 180000         # agent 查数据、调工具后回复完毕（实测约 42s，留足余量）

    def __init__(self, page: Page):
        super().__init__(page)
        # 侧边栏是全站共享布局，做成组件挂在这里；别的页面对象也照此持有一份
        self.sidebar = SidebarNav(page)

    def open(self, base_url: str) -> None:
        """导航到首页。base_url 不带末尾斜杠（conftest 的 base_url fixture 约定），这里仍做一次兜底。"""
        self.goto(f"{base_url.rstrip('/')}{self.PATH}")

    # ── 顶部操作区 ──────────────────────────────────────────────────
    def click_connect_portfolio(self):
        """外部持仓授权入口。只读冒烟禁止调用。"""
        self.click_hydrated(self.CONNECT_PORTFOLIO_BUTTON)

    def click_connect_im(self):
        """IM 账号绑定入口。只读冒烟禁止调用。"""
        self.click_hydrated(self.CONNECT_IM_BUTTON)

    def click_agent_settings(self):
        """进入 Agent 设置页（/settings?tab=alvaAgent）。访客态会被重定向到 /login?returnTo=%2Fsettings。"""
        self.click_hydrated(self.AGENT_SETTINGS_LINK)

    def is_header_action_visible(self, name: str) -> bool:
        """name 取 GUEST_HEADER_ACTIONS / USER_HEADER_ACTIONS 的键。"""
        return self.is_visible({**self.GUEST_HEADER_ACTIONS, **self.USER_HEADER_ACTIONS}[name])

    # ── Agent 分区 tab ──────────────────────────────────────────────
    def click_chat_tab(self):
        self.click_hydrated(self.CHAT_TAB)

    def click_tasks_tab(self):
        self.click_hydrated(self.TASKS_TAB)

    def click_alerts_tab(self):
        self.click_hydrated(self.ALERTS_TAB)

    def click_memory_tab(self):
        self.click_hydrated(self.MEMORY_TAB)

    def click_files_tab(self):
        self.click_hydrated(self.FILES_TAB)

    def click_agent_tab(self, name: str):
        """按可见文案点 tab，name 取 AGENT_TABS 的键。供数据驱动用例使用。"""
        self.click_hydrated(self.AGENT_TABS[name][0])

    def is_tab_visible(self, name: str) -> bool:
        return self.is_visible(self.AGENT_TABS[name][0])

    def is_tab_selected(self, name: str, timeout: int | None = None) -> bool:
        """某个 tab 是否处于选中态（aria-selected=true）。

        点击后选中态是异步更新的，所以是「等它变成选中」而不是看一眼。
        「没选中」是合法答案，不走自愈 —— 自愈会把「Chat 未选中」修成「Chat tab
        本身」，从而永远返回 True。
        """
        return self._wait_state(self.AGENT_TABS[name][1], "visible",
                                self.STATE_TIMEOUT if timeout is None else timeout)

    # ── 建议卡片 ────────────────────────────────────────────────────
    def get_suggestion_count(self) -> int:
        """建议卡片个数。卡片数量属运营配置，用例只宜断言 >= 1。"""
        if not self._suggestions_rendered():
            return 0
        return self.get_element_count(self.SUGGESTION_CARD)

    def get_suggestion_titles(self) -> list:
        """每张卡片的标题（第一行，含开头的 emoji），不含下面的说明文字。"""
        if not self._suggestions_rendered():
            return []
        texts = self.get_all_texts(self.SUGGESTION_CARD)
        return [t.strip().splitlines()[0].strip() for t in texts if t.strip()]

    def click_suggestion(self, index: int):
        """点第 index 张建议卡片（从 0 开始）。

        会发起 onboarding 流程、向 agent 排队提交，等同于发消息 —— 只读冒烟禁止调用。
        """
        self._act(self.SUGGESTION_CARD, lambda loc: loc.nth(index).click())

    # ── 聊天输入框 ──────────────────────────────────────────────────
    def fill_chat_input(self, text: str):
        """只输入，不发送。输入框是 Lexical contenteditable，Playwright 的 fill 对它同样有效。
        先等前端接管输入框，否则输入只改了 DOM、编辑器状态仍为空（见 BasePage.wait_for_hydrated）。"""
        self.wait_for_hydrated(self.CHAT_INPUT)
        self.fill(self.CHAT_INPUT, text)

    def get_chat_input_value(self) -> str:
        """输入框当前文字。contenteditable 没有 value，input_value() 会报错，只能读 inner_text；
        空输入框里是 Lexical 的占位 <p><br></p>，读出来是换行，strip 后为空串。"""
        return self.get_text(self.CHAT_INPUT).strip()

    def clear_chat_input(self):
        self.wait_for_hydrated(self.CHAT_INPUT)
        self.clear(self.CHAT_INPUT)

    def is_send_enabled(self, timeout: int | None = None) -> bool:
        """发送按钮是否可用（等它变为可用）。只看状态；要发送用 send_chat_message()。"""
        return self._wait_state(self.SEND_BUTTON_ENABLED, "visible",
                                self.STATE_TIMEOUT if timeout is None else timeout)

    def is_send_disabled(self, timeout: int | None = None) -> bool:
        """发送按钮是否禁用（等它变为禁用）。与 is_send_enabled 分开：
        「等它变可用」超时返回 False，不等于「它是禁用的」。"""
        return self._wait_state(self.SEND_BUTTON_DISABLED, "visible",
                                self.STATE_TIMEOUT if timeout is None else timeout)

    # ── 发送消息与等待回复（真实提交给 agent，只在明确需要发消息的用例里调用） ──────────
    def send_chat_message(self, text: str) -> str | None:
        """输入并发送一条消息，返回它所在那一轮对话的 id；发送后新一轮没出现返回 None。

        先等历史消息渲染完再记下已有的轮次：否则历史晚到，里面同样文字的旧消息会被当成新发的。
        """
        self._locate(self.CHAT_LAST_TURN).wait_for(state="visible", timeout=self.CHAT_HISTORY_TIMEOUT)
        known = self._locate(f"css={self.CHAT_TURN_CSS}").evaluate_all(
            "els => els.map(e => e.getAttribute('data-chat-v2-turn-id'))")
        self.fill_chat_input(text)
        self.click_hydrated(self.SEND_BUTTON_ENABLED)
        try:
            handle = self.page.wait_for_function(
                self.NEW_TURN_JS, arg=[self.CHAT_TURN_CSS, known, text], timeout=self.NEW_TURN_TIMEOUT)
            return handle.json_value()
        except PlaywrightTimeoutError:
            return None

    def wait_for_reply(self, turn_id: str, timeout: int | None = None) -> bool:
        """等这一轮的回复生成完毕（生成中标记消失、回复正文出现），超时返回 False。"""
        return self._wait_state(self.CHAT_REPLY_DONE.format(turn_id=turn_id), "visible",
                                self.REPLY_TIMEOUT if timeout is None else timeout)

    def get_reply_text(self, turn_id: str) -> str:
        """这一轮已生成完毕的回复正文（最终答案部分）。先 wait_for_reply 再调用。"""
        return self._locate(self.CHAT_REPLY_DONE.format(turn_id=turn_id)).inner_text().strip()

    # ── 登录态 ──────────────────────────────────────────────────────
    def is_logged_in(self, settle_timeout: int | None = None) -> bool:
        """委托侧边栏：以「用户菜单可见」为正向信号，「Log in」不可见为辅助。
        访客态会等满 settle_timeout 才返回 False，原因见 SidebarNav.is_logged_in。"""
        return self.sidebar.is_logged_in(settle_timeout)

    def wait_for_home_url(self, timeout: int | None = None) -> bool:
        """等 URL 路径变成首页（/），等到返回 True，超时返回 False（不抛异常，便于断言）。

        用于「已登录访问 /login 被重定向回首页」：那是前端重定向，/login 的 load 事件
        触发时 URL 还没变，而首页内容可能在 URL 改写前约 0.1s 就已渲染 —— 所以
        is_page_loaded() 成立不代表已离开 /login，必须单独等 URL。
        比的是「同一主机 + 路径 /」：查询串（如 ?tab=）与片段不影响「在首页」的判断；
        主机锁定为调用时所在的主机，跳去第三方站点的根路径不算回到首页。
        timeout 缺省沿用 page 的默认超时。
        """
        host = urlparse(self.page.url).netloc
        try:
            kwargs = {"timeout": timeout} if timeout is not None else {}
            self.page.wait_for_url(
                lambda url: urlparse(url).netloc == host and urlparse(url).path == self.PATH, **kwargs
            )
            return True
        except Exception:
            return False

    # ── 内部 ────────────────────────────────────────────────────────
    def _suggestions_rendered(self, timeout: int | None = None) -> bool:
        """等第一张建议卡片出现。

        SUGGESTION_CARD 同时命中多张卡片，直接 wait_for 会触发严格模式报错，
        所以取 .first；且「没有卡片」是合法答案，不走自愈。
        """
        try:
            kwargs = {"timeout": timeout} if timeout is not None else {}
            self._locate(self.SUGGESTION_CARD).first.wait_for(state="visible", **kwargs)
            return True
        except Exception:
            return False

    def _wait_state(self, selector: str, state: str, timeout: int | None) -> bool:
        """等待元素进入某个状态，等不到返回 False，且**不触发自愈**。

        用于「否定答案也合法」的状态判定（未选中 / 未启用）。走 _act() 的
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
        """模式 C（多元素 + 激活态）：它是所有用例的起点页，必须能区分「停在起点」。

        访客态与登录态都成立，且每个定位符在两种状态下都唯一命中（2026-09-22 实测 count()==1）。
        - h1「Alva」+ Agent tab 栏：首页独有的锚点，/explore 等其他页面没有；
        - 「Chat」tab 处于选中态：切到 Tasks 等 tab 后骨架还在，只看骨架会让复位失效
          （.claude/skills/case-round-trip「起点 is_page_loaded 的严格判据」）；
        - 聊天输入框：首页最关键的交互控件，SPA 白屏时骨架可能在而它不在。
        """
        return (
            self.is_visible(self.PAGE_HEADING)
            and self.is_visible(self.AGENT_TABLIST)
            and self.is_tab_selected("Chat")
            and self.is_visible(self.CHAT_INPUT)
        )
