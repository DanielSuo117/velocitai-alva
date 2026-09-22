---
paths:
  - "framework/pages/**"
  - "framework/tests/**"
  - "framework/conftest.py"
---

# 超时排查 & 等待策略

---

## 一、超时失败排查：先确认"在哪个页面"，再排查"定位符对不对"

**触发**：`wait_for_element` / `is_visible` / `inner_text` 等操作报 `TimeoutError`。

**规则**：超时失败时，**第一步**永远是确认当前 page 对象指向的页面是否正确，**禁止**直接改定位符。

90% 的超时问题不是"元素找不到"，而是"根本不在目标页面上"。常见原因：
1. 按钮打开了**新 tab**，代码还在旧 tab 的 page 对象上等（最常见）
2. SPA 路由没跳转（前一步操作被下拉框/弹窗拦截，点击没生效）
3. 页面被重定向到登录页（token 过期、跨域认证失败）

**排查顺序（必须严格按序）**：

```
TimeoutError
   │
   ▼
① 打印 page.url 和 page.title()
   │  → URL 不对 → 页面没跳转，排查上一步的点击是否生效
   │  → URL 正确 → 进入 ②
   ▼
② 检查是否有新 tab 打开（context.pages 数量变化）
   │  → 多了新 tab → 目标内容在新 tab 里，当前 page 是旧的
   │  → 没有新 tab → 进入 ③
   ▼
③ 此时才排查定位符问题（page.locator("xxx").count()）
```

❌ 反例：超时就换定位符，换了 4 次全部超时，根因是新 tab。

✅ 正例：

```python
print(f"当前 URL: {page.url}")
print(f"当前标题: {page.title()}")
print(f"context 中 page 数量: {len(page.context.pages)}")
```

---

## 二、等待策略

**触发**：编写 fixture / PageObject 中涉及页面导航或 SPA 模块切换的等待逻辑时。

**规则**：全局隐式等待 + 仅慢路径显式 timeout。完整策略 → [wait-strategy skill](../../skills/wait-strategy/SKILL.md)

### SPA 菜单/Tab 切换后 `networkidle` 不等于渲染完成

在 Vue / React 等 SPA 框架中，点击菜单切换模块后，`networkidle` 只能保证网络请求完成，**不能保证组件已渲染到 DOM**。

**规则**：SPA 菜单/Tab 切换后，若下一步依赖新渲染元素，必须在 `networkidle` 后额外加 `wait_for_timeout(3000)` 或 `wait_for_element()` 确认稳定。

❌ 反例：

```python
def _setup_context(self, ...):
    home.click_target_menu()
    assert home.is_target_section_visible()
    home.search("<搜索关键词>")               # 搜索框正在被 Vue 重渲染
```

✅ 正例：

```python
def _setup_context(self, ...):
    home.click_target_menu()
    assert home.is_target_section_visible()
    self.<role>_page.wait_for_timeout(3000)   # 等待异步组件渲染完成
    home.search("<搜索关键词>")
```

### 服务端渲染（SSR）页面：可见 ≠ 可交互，输入前先等水合

**触发**：页面整页加载且首屏 HTML 已带表单控件（SSR / 同构渲染），用例在 `is_page_loaded()` 通过后立即 `fill`，
且下一步断言依赖前端对输入的响应（提交按钮出现 / 启用、实时校验提示）。

**失败现象**：`fill` 不报错、`input_value()` 也读得到填入的值，但依赖输入的按钮始终不出现，等满超时失败；
水合完成后也不会补上 —— 水合前的 fill 只改了 DOM 的 value，框架状态仍是空串。实测：控件点击后约 0.45s 可见，
约 1.6s 才水合，连续 3 次复现；人手操作比水合慢，手点复现不了，容易误判成定位符问题。

❌ 反例：

```python
assert form_page.is_page_loaded()        # 只看可见：SSR 首屏已有控件
form_page.fill_field("<输入值>")          # 水合前输入，被框架状态丢弃
assert form_page.is_submit_enabled()     # 按钮永不出现 → 超时
```

✅ 正例：等待封装在 PageObject 的输入方法里（调用方不必记得），等的是「框架已接管该节点」这个确定信号，而不是固定时长：

```python
REACT_HYDRATED_JS = "el => Object.keys(el).some(k => k.startsWith('__reactProps$'))"   # React 水合后挂到节点上的属性

def fill_field(self, value: str):
    handle = self._locate(self.FIELD_INPUT).element_handle()
    self.page.wait_for_function(self.REACT_HYDRATED_JS, arg=handle)   # 已水合时约 2ms 返回
    self.fill(self.FIELD_INPUT, value)
```

非 React 站点换成对应框架挂在节点上的接管标志；`wait_for_timeout` 固定等待在慢机器上照样会输。
