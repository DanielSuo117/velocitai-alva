# 页面名称：登录页
"""alva.ai 登录页（/login）—— 访客点首页左下角「Log in」进入；未登录访问 /settings 等
需要登录的页面也会被重定向到这里（/login?returnTo=<原路径>）。

封装范围：到邮箱输入为止。提交邮箱之后是 6 位验证码输入框 + Resend / Close，
再往后还有 Cloudflare Turnstile 人机验证，那些都不在这里。

登录页脱离门户布局：没有左侧栏（SidebarNav 在这里不存在），离开只能靠左上角的
「Alva」Logo 链接回首页 —— 用例进来后必须经 click_back_to_home() 往返闭合。

访客态实测行为（2026-09-22，Playwright fill），决定了只读冒烟能碰什么：
- 首页点「Log in」是整页跳转（服务端渲染），页面可见后约 1s 才水合；水合前的输入会被吞掉，
  所以 fill_email() 先 wait_for_interactive()；
- 邮箱框为空时，「Submit email」按钮**不渲染**（聚焦也不出现）；
- 填入格式合法的邮箱，按钮出现且可用；填入格式不合法的文字（如 abc），按钮出现但禁用；
- 清空后按钮再次消失。只要不点这个按钮、不在邮箱框里回车，就没有任何提交。
- 点「Submit email」或在邮箱框回车，会真的往该邮箱发验证码 —— 只读冒烟禁止。
- Google / X / Telegram / Discord 四个按钮都跳第三方授权 —— 只读冒烟禁止点。
"""
from __future__ import annotations

from core.base.base_page import BasePage


class LoginPage(BasePage):
    PATH = "/login"

    # 定位符 — 来自真实页面（2026-09-22，URL: https://alva.ai/login）
    # `role=` 引擎的 name 带 s 是区分大小写的整串匹配（不是子串），这里的可及名称都是完整且稳定的文案。
    BACK_TO_HOME_LINK = "role=link[name='Alva' s]"   # P0: 左上角「Alva」Logo 链接（aria-label=Alva，href=/），登录页唯一的回首页入口
    PAGE_HEADING = "role=heading[name='Your AI Investing Agent' s][level=1]"   # P0: 登录页 h1「Your AI Investing Agent」（首页的 h1 是「Alva」，不会混淆）
    GOOGLE_LOGIN_BUTTON = "role=button[name='Log in with Google' s]"   # P0: 「Log in with Google」按钮（另有 data-testid=login-popup-google 可作 P4 替补）
    # 下面三个是纯图标按钮：只有一个 svg，没有文字、aria-label、title，可及名称为空，只能用 data-testid。
    # 用途由 testid 与图标一并确认：X 的黑色「X」字标、Telegram 蓝底纸飞机（#24A1DE）、Discord 紫底（#5762E3）。
    X_LOGIN_BUTTON = "css=[data-testid='login-popup-twitter']"   # P4: X（Twitter）登录图标按钮（第三方授权）
    TELEGRAM_LOGIN_BUTTON = "css=[data-testid='login-popup-telegram']"   # P4: Telegram 登录图标按钮（第三方授权）
    DISCORD_LOGIN_BUTTON = "css=[data-testid='login-popup-discord']"   # P4: Discord 登录图标按钮（第三方授权）
    # 可及名称来自 placeholder「Login with Email」（codegen 录制的 get_by_role 同名），input[type=email]
    EMAIL_INPUT = "role=textbox[name='Login with Email' s]"   # P0: 邮箱输入框
    # 邮箱框右侧的箭头按钮：只在邮箱框有内容时渲染；格式合法可用、不合法禁用。
    # 状态用 role 引擎的 disabled 属性表达，等待交给 Playwright，不必轮询。
    SUBMIT_EMAIL_BUTTON = "role=button[name='Submit email' s]"   # P0: 「Submit email」提交邮箱按钮（aria-label；邮箱框为空时不渲染）
    SUBMIT_EMAIL_ENABLED = "role=button[name='Submit email' s][disabled=false]"   # P0: 提交邮箱按钮·可用态（邮箱格式合法时）
    SUBMIT_EMAIL_DISABLED = "role=button[name='Submit email' s][disabled=true]"   # P0: 提交邮箱按钮·禁用态（有内容但邮箱格式不合法时）
    TERMS_LINK = "role=link[name='Terms of Service' s]"   # P0: 底部「Terms of Service」服务条款链接（新标签页打开 /compliance/terms-of-service）
    PRIVACY_LINK = "role=link[name='Privacy Policy' s]"   # P0: 底部「Privacy Policy」隐私政策链接（新标签页打开 /compliance/privacy-policy）

    # 纯图标登录按钮：判可见与点击都**不走自愈**。它们没有可及名称，自愈记下的指纹只剩
    # {tag: button, role: button}，登录页上每个登录按钮都符合、又各有唯一 testid ——
    # 其中一个下线时，自愈会拿另一个登录按钮顶替（2026-09-22 实测：本地删掉 Discord 按钮后
    # 被换成 login-popup-google，「Discord 可见」照样成立；--self-heal=auto 还会把它写回源码）。
    ICON_LOGIN_BUTTONS = (X_LOGIN_BUTTON, TELEGRAM_LOGIN_BUTTON, DISCORD_LOGIN_BUTTON)

    # 登录方式可见名称 → 定位符，供用例按名字数据驱动校验「登录方式齐全」
    LOGIN_OPTIONS = {
        "Google": GOOGLE_LOGIN_BUTTON,
        "X": X_LOGIN_BUTTON,
        "Telegram": TELEGRAM_LOGIN_BUTTON,
        "Discord": DISCORD_LOGIN_BUTTON,
        "Email": EMAIL_INPUT,
    }
    # 法律条款链接可见文案 → (定位符, 期望 href)。链接 target=_blank，用例只校验可见与指向，不点开
    LEGAL_LINKS = {
        "Terms of Service": (TERMS_LINK, "/compliance/terms-of-service"),
        "Privacy Policy": (PRIVACY_LINK, "/compliance/privacy-policy"),
    }

    # 提交按钮的出现 / 消失 / 启停都是前端状态更新，毫秒级；等太久只会拖慢「状态不对」时的失败
    STATE_TIMEOUT = 5000

    def open(self, base_url: str) -> None:
        """直接导航到登录页。base_url 不带末尾斜杠（conftest 的 base_url fixture 约定），这里仍做一次兜底。"""
        self.goto(f"{base_url.rstrip('/')}{self.PATH}")

    # ── 导航 ────────────────────────────────────────────────────────
    def click_back_to_home(self):
        """点左上角「Alva」Logo 回首页。登录页没有侧边栏，这是往返闭合走的真实 UI 入口。"""
        self.click_hydrated(self.BACK_TO_HOME_LINK)

    # ── 登录方式 ────────────────────────────────────────────────────
    def is_login_option_visible(self, name: str) -> bool:
        """name 取 LOGIN_OPTIONS 的键。

        X / Telegram / Discord 三个图标按钮不走自愈（理由见 ICON_LOGIN_BUTTONS）：
        「这种登录方式没了」正是本方法要答出的合法答案，不能被顶替成别的按钮。
        """
        selector = self.LOGIN_OPTIONS[name]
        if selector in self.ICON_LOGIN_BUTTONS:
            return self._wait_state(selector, "visible", None)
        return self.is_visible(selector)

    def click_login_with_google(self):
        """跳 Google 第三方授权。只读冒烟禁止调用。"""
        self.click_hydrated(self.GOOGLE_LOGIN_BUTTON)

    # 下面三个图标按钮用 _locate() 直接点、不经 click() 的自愈：自愈顶替后点到的会是
    # 另一家的第三方授权（理由见 ICON_LOGIN_BUTTONS）。按钮真没了就按原样超时失败。
    def click_login_with_x(self):
        """跳 X（Twitter）第三方授权。只读冒烟禁止调用。"""
        self._locate(self.X_LOGIN_BUTTON).click()

    def click_login_with_telegram(self):
        """跳 Telegram 第三方授权。只读冒烟禁止调用。"""
        self._locate(self.TELEGRAM_LOGIN_BUTTON).click()

    def click_login_with_discord(self):
        """跳 Discord 第三方授权。只读冒烟禁止调用。"""
        self._locate(self.DISCORD_LOGIN_BUTTON).click()

    # ── 邮箱登录 ────────────────────────────────────────────────────
    def wait_for_interactive(self, timeout: int | None = None):
        """等邮箱输入框被前端接管（React 水合完成），之后的输入才会进入前端状态。

        登录页是服务端渲染的整页加载（首页点「Log in」也是整页跳转，不是 SPA 路由）：
        点击后约 0.45s 标题和邮箱框就可见，is_page_loaded() 随即成立，但 React 约 1.6s 才水合
        （2026-09-22 本机无头实测）。这段约 1s 的空窗里 fill 只改了 DOM 的 value，React 状态
        仍是空串 ——「Submit email」按钮永远不出现，水合后也不会补上（连续 3 次复现）。
        已水合时本方法约 2ms 返回，可以放心在每次输入前调用。
        timeout 缺省为 BasePage.HYDRATION_TIMEOUT（15s）。
        """
        self.wait_for_hydrated(self.EMAIL_INPUT, timeout)

    def fill_email(self, email: str):
        """只输入，不提交（fill 不会触发回车）。只读冒烟只许填 example.com 之类的假地址。

        先等前端接管输入框，否则输入会被水合吞掉，见 wait_for_interactive()。
        """
        self.wait_for_interactive()
        self.fill(self.EMAIL_INPUT, email)

    def get_email_value(self) -> str:
        return self.get_value(self.EMAIL_INPUT)

    def clear_email(self):
        self.clear(self.EMAIL_INPUT)

    def click_submit_email(self):
        """提交邮箱：站点会立即往该邮箱发送 6 位验证码，随后进入验证码 + Turnstile 人机验证环节。

        只读冒烟禁止调用 —— 这是生产站点，提交即产生真实外发邮件。
        """
        self.click_hydrated(self.SUBMIT_EMAIL_BUTTON)

    def is_submit_email_enabled(self, timeout: int | None = None) -> bool:
        """提交邮箱按钮是否出现且可用（等它变为可用）。邮箱格式合法时成立。"""
        return self._wait_state(self.SUBMIT_EMAIL_ENABLED, "visible",
                                self.STATE_TIMEOUT if timeout is None else timeout)

    def is_submit_email_disabled(self, timeout: int | None = None) -> bool:
        """提交邮箱按钮是否出现但禁用（等它变为禁用）。有内容但邮箱格式不合法时成立。

        与 is_submit_email_enabled 分开：「等它变可用」超时返回 False，不等于「它是禁用的」
        —— 按钮也可能根本没渲染。
        """
        return self._wait_state(self.SUBMIT_EMAIL_DISABLED, "visible",
                                self.STATE_TIMEOUT if timeout is None else timeout)

    def is_submit_email_absent(self, timeout: int | None = None) -> bool:
        """提交邮箱按钮是否不存在（等它消失）。邮箱框为空时成立。"""
        return self._wait_state(self.SUBMIT_EMAIL_BUTTON, "hidden",
                                self.STATE_TIMEOUT if timeout is None else timeout)

    # ── 法律条款 ────────────────────────────────────────────────────
    def is_legal_link_visible(self, name: str) -> bool:
        """name 取 LEGAL_LINKS 的键。"""
        return self.is_visible(self.LEGAL_LINKS[name][0])

    def get_legal_link_href(self, name: str) -> str | None:
        """条款链接的 href。链接在新标签页打开，用例校验指向即可，不必点开。"""
        return self.get_attribute(self.LEGAL_LINKS[name][0], "href")

    # ── 内部 ────────────────────────────────────────────────────────
    def _wait_state(self, selector: str, state: str, timeout: int | None) -> bool:
        """等待元素进入某个状态，等不到返回 False，且**不触发自愈**。

        用于「否定答案也合法」的状态判定（按钮未渲染 / 未启用 / 已消失 / 图标登录方式缺失）。走 _act() 的
        is_visible() 会把超时当定位失效去自愈 —— 自愈可能把「提交按钮可用态」修成
        「提交按钮本身」，让禁用态也判成可用。理由同 HomePage._wait_state。
        timeout 不能传 0 —— Playwright 里 0 表示永不超时。
        """
        try:
            kwargs = {"timeout": timeout} if timeout is not None else {}
            self._locate(selector).wait_for(state=state, **kwargs)
            return True
        except Exception:
            return False

    def is_page_loaded(self) -> bool:
        """模式 B（标题 + 关键控件）：h1「Your AI Investing Agent」+ 邮箱输入框。

        两者在首页上都不存在（首页 h1 是「Alva」、没有邮箱框，2026-09-22 实测 count()==0），
        所以从首页跳过来时不会在来源页上被提前满足；邮箱框是本页封装范围内最关键的
        交互控件，SPA 白屏时标题可能在而它不在。登录页不是起点页，不需要模式 C 的状态判据。

        只用于「进入登录页之后」的肯定断言。不在登录页时，第一个 is_visible 要等满 page 默认
        超时（15s）才返回 False（2026-09-22 在首页实测 15.00s）。要确认已经离开登录页，
        请断言目标页的 is_page_loaded()（如返回首页后断言 HomePage.is_page_loaded()），
        不要写 assert not login.is_page_loaded()。
        """
        return self.is_visible(self.PAGE_HEADING) and self.is_visible(self.EMAIL_INPUT)
