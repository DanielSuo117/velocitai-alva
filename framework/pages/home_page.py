# 页面名称：Alva Agent 首页
"""alva.ai 首页（/）—— Alva Agent 的对话入口，也是所有角色用例的起点页。

页面由三块组成：顶部操作区（Connect Portfolio / Connect IM / Agent settings）、
Agent 分区 tab（Chat / Tasks / Alerts / Memory / Files），以及 Chat 分区里的
onboarding 建议卡片 + 聊天输入框。左侧栏是全站共享组件，经 self.sidebar 访问。

访客态实测行为（2026-09-22），决定了只读冒烟能碰什么：
- 切 Agent tab：不跳页，只把 URL 改成 /?tab=<name>，aria-selected 跟随；切回 Chat 后 URL 回到 /。
- 输入框输入文字：发送按钮由禁用变可用；清空后恢复禁用。只要不点发送、不回车，就没有任何提交。
- 建议卡片：点击会发起 onboarding 流程（前端排队一条 agent 提交，「Build your own
  automations」直接提交一句提示语），等同于发消息 —— 只读冒烟禁止点。
- Connect Portfolio / Connect IM：券商持仓、IM 账号的外部授权入口，只读冒烟禁止点。
"""
from __future__ import annotations

from playwright.sync_api import Page

from core.base.base_page import BasePage
from pages.components.sidebar_nav import SidebarNav


class HomePage(BasePage):
    PATH = "/"

    # 定位符 — 来自真实页面（2026-09-22，URL: https://alva.ai/）
    # `role=` 引擎的 name：不带标志与带 s 都是区分大小写的整串匹配，带 i 才不区分大小写，
    # 都不是子串（与 get_by_role 不同，见 SidebarNav 的说明）；前缀匹配只能写正则 name=/^.../。
    PAGE_HEADING = "role=heading[name='Alva' s][level=1]"   # P0: 首页顶部 h1「Alva」（全页唯一的 h1）
    CONNECT_PORTFOLIO_BUTTON = "role=button[name='Connect Portfolio' s]"   # P0: 顶部「Connect Portfolio」接入持仓按钮
    CONNECT_IM_BUTTON = "role=button[name='Connect IM' s]"   # P0: 顶部「Connect IM」绑定 IM 按钮
    AGENT_SETTINGS_LINK = "role=link[name='Agent settings' s]"   # P0: 顶部齿轮图标「Agent settings」链接（/settings?tab=alvaAgent）

    # Agent 分区 tab。Tasks 面板里还嵌套了一组 All/Active/Done 的 role=tab，
    # 所以每个 tab 都圈在「Agent sections」tablist 之内，不能直接写 role=tab。
    AGENT_TABLIST = "role=tablist[name='Agent sections' s]"   # P0: Agent 分区 tab 栏
    CHAT_TAB = "role=tablist[name='Agent sections' s] >> role=tab[name='Chat' s]"   # P0: 「Chat」tab（默认选中）
    TASKS_TAB = "role=tablist[name='Agent sections' s] >> role=tab[name='Tasks' s]"   # P0: 「Tasks」tab
    ALERTS_TAB = "role=tablist[name='Agent sections' s] >> role=tab[name='Alerts' s]"   # P0: 「Alerts」tab
    MEMORY_TAB = "role=tablist[name='Agent sections' s] >> role=tab[name='Memory' s]"   # P0: 「Memory」tab
    FILES_TAB = "role=tablist[name='Agent sections' s] >> role=tab[name='Files' s]"   # P0: 「Files」tab
    # 选中态（aria-selected）会跟着点击漂移，必须锁定到具体 tab 名（.claude/rules/playwright/locator-strategy.md）
    CHAT_TAB_SELECTED = "role=tablist[name='Agent sections' s] >> role=tab[name='Chat' s][selected=true]"   # P0: 「Chat」tab 处于选中态（起点判据）
    TASKS_TAB_SELECTED = "role=tablist[name='Agent sections' s] >> role=tab[name='Tasks' s][selected=true]"   # P0: 「Tasks」tab 处于选中态
    ALERTS_TAB_SELECTED = "role=tablist[name='Agent sections' s] >> role=tab[name='Alerts' s][selected=true]"   # P0: 「Alerts」tab 处于选中态
    MEMORY_TAB_SELECTED = "role=tablist[name='Agent sections' s] >> role=tab[name='Memory' s][selected=true]"   # P0: 「Memory」tab 处于选中态
    FILES_TAB_SELECTED = "role=tablist[name='Agent sections' s] >> role=tab[name='Files' s][selected=true]"   # P0: 「Files」tab 处于选中态

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

    # tab 可见文案 → (tab 定位符, 选中态定位符)，供用例按名字数据驱动
    AGENT_TABS = {
        "Chat": (CHAT_TAB, CHAT_TAB_SELECTED),
        "Tasks": (TASKS_TAB, TASKS_TAB_SELECTED),
        "Alerts": (ALERTS_TAB, ALERTS_TAB_SELECTED),
        "Memory": (MEMORY_TAB, MEMORY_TAB_SELECTED),
        "Files": (FILES_TAB, FILES_TAB_SELECTED),
    }
    # 顶部操作区可见文案 → 定位符
    HEADER_ACTIONS = {
        "Connect Portfolio": CONNECT_PORTFOLIO_BUTTON,
        "Connect IM": CONNECT_IM_BUTTON,
        "Agent settings": AGENT_SETTINGS_LINK,
    }

    # tab 切换、发送按钮启停都是前端状态更新，毫秒级；等太久只会拖慢「状态不对」时的失败
    STATE_TIMEOUT = 5000

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
        self.click(self.CONNECT_PORTFOLIO_BUTTON)

    def click_connect_im(self):
        """IM 账号绑定入口。只读冒烟禁止调用。"""
        self.click(self.CONNECT_IM_BUTTON)

    def click_agent_settings(self):
        """进入 Agent 设置页（/settings?tab=alvaAgent）。访客态会被重定向到 /login?returnTo=%2Fsettings。"""
        self.click(self.AGENT_SETTINGS_LINK)

    def is_header_action_visible(self, name: str) -> bool:
        """name 取 HEADER_ACTIONS 的键。"""
        return self.is_visible(self.HEADER_ACTIONS[name])

    # ── Agent 分区 tab ──────────────────────────────────────────────
    def click_chat_tab(self):
        self.click(self.CHAT_TAB)

    def click_tasks_tab(self):
        self.click(self.TASKS_TAB)

    def click_alerts_tab(self):
        self.click(self.ALERTS_TAB)

    def click_memory_tab(self):
        self.click(self.MEMORY_TAB)

    def click_files_tab(self):
        self.click(self.FILES_TAB)

    def click_agent_tab(self, name: str):
        """按可见文案点 tab，name 取 AGENT_TABS 的键。供数据驱动用例使用。"""
        self.click(self.AGENT_TABS[name][0])

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
        """只输入，不发送。输入框是 Lexical contenteditable，Playwright 的 fill 对它同样有效。"""
        self.fill(self.CHAT_INPUT, text)

    def get_chat_input_value(self) -> str:
        """输入框当前文字。contenteditable 没有 value，input_value() 会报错，只能读 inner_text；
        空输入框里是 Lexical 的占位 <p><br></p>，读出来是换行，strip 后为空串。"""
        return self.get_text(self.CHAT_INPUT).strip()

    def clear_chat_input(self):
        self.clear(self.CHAT_INPUT)

    def is_send_enabled(self, timeout: int | None = None) -> bool:
        """发送按钮是否可用（等它变为可用）。仅用于断言状态，本类不提供点击发送的方法。"""
        return self._wait_state(self.SEND_BUTTON_ENABLED, "visible",
                                self.STATE_TIMEOUT if timeout is None else timeout)

    def is_send_disabled(self, timeout: int | None = None) -> bool:
        """发送按钮是否禁用（等它变为禁用）。与 is_send_enabled 分开：
        「等它变可用」超时返回 False，不等于「它是禁用的」。"""
        return self._wait_state(self.SEND_BUTTON_DISABLED, "visible",
                                self.STATE_TIMEOUT if timeout is None else timeout)

    # ── 登录态 ──────────────────────────────────────────────────────
    def is_logged_in(self, settle_timeout: int | None = None) -> bool:
        """委托侧边栏：依据「Log in」按钮是否消失判定。访客态会等满 settle_timeout
        才返回 False，原因见 SidebarNav.is_logged_in。"""
        return self.sidebar.is_logged_in(settle_timeout)

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
