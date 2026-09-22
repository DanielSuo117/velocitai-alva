---
paths:
  - "framework/pages/**"
  - "framework/tests/**"
---

# 定位符策略

完整六级优先级（P0 → P5）与选择流程见 [locator-replacer skill](../../skills/locator-replacer/SKILL.md)。

---

## 绝对禁止

- **哈希类名**：`sc-bdVaJa`、`css-1a2b3c`、`._module_xxx`（构建工具生成，每次 build 变化）
- **绝对 XPath**：`/html/body/div[1]/div[2]/...`（页面任何改动都会断）
- **纯数字索引**：`div[3]`（除非列表确实需要第 N 项）

> 哈希类名识别详细规则（按构建工具分类）→ [locator-replacer skill](../../skills/locator-replacer/SKILL.md) "哈希类名识别规则"

---

## 状态类 selector 必须配 text 锁定

`.active` / `aria-selected` 等状态类匹配"谁当前处于该状态"，切换 tab 后会跟随移动。

❌ 反例：

```python
OVERVIEW_ACTIVE = "css=ul.tab-bar li.tab.active"   # 切到其他 tab 时仍匹配
```

✅ 正例：

```python
OVERVIEW_ACTIVE = "css=ul.tab-bar li.tab.active >> text=起点 Tab 名"   # .active + 具体 text
```

---

## 注释规范

每个定位符行尾标注 `# P0`~`# P5`，完整级别定义 → [locator-replacer skill](../../skills/locator-replacer/SKILL.md)

---

## ARIA role 必须先验证

不要凭 UI 外观猜测 role。许多框架用 `<div>` / `<li>` + CSS 模拟组件，没有 `role` 属性。

❌ 反例：

```python
TAB = "role=tab[name='详情']"    # 实际是 <li> 没有 role → 超时
```

✅ 正例：

```python
# 先验证 DOM：<li class="active">详情</li>（无 role）
TAB = "css=.tab-container li:has-text('详情')"    # P3+P1
```

---

## `>>` 链式定位：文本直接在父元素内时会失效

当文本直接是元素的 textContent（如 `<li>详情</li>`），`css=X >> text=Y` 可能找不到匹配。

❌ 反例：

```python
TAB = "css=.tab-container li >> text=详情"    # <li> 内无子元素 → 超时
```

✅ 正例：

```python
TAB = "css=.tab-container li:has-text('详情')"    # :has-text() 匹配元素自身文本
TAB = "css=.tab-container li:text-is('详情')"     # :text-is() 精确匹配
```

---

## `text=X` 是子串匹配——有包含关系时用精确匹配

`text=添加` 会同时匹配「添加」和「批量添加」。

❌ 反例：

```python
ADD_BTN = "text=添加"        # .first 命中「批量添加」
GENERATE_BTN = "text=生成"   # 命中描述段落中的「生成」子串
```

✅ 正例：

```python
ADD_BTN = 'text="添加"'       # 带引号 = 精确匹配
# 或用 CSS scope 限定
ADD_BTN = "css=.list-card >> text=添加"
```

### 高危变体：子串命中切换按钮导致级联功能失败

当操作按钮的文本是某个切换按钮的子串时（如「筛选」vs「收起筛选」），子串匹配会优先命中切换按钮，触发**副作用**（如收起面板），导致目标按钮消失、后续操作全部在错误状态下执行。

这类 bug 特别隐蔽：测试不会报元素找不到的错，而是在未筛选的全量数据上执行了后续操作（如删除了错误的数据），断言也可能碰巧通过。

❌ 反例：

```python
# text=筛选 子串匹配，.first 命中「收起筛选」→ 面板被收起 → 真正的「筛选」按钮消失
# → 搜索未执行 → 后续在全量列表上操作了错误的数据
FILTER_BTN = "css=.list-content >> text=筛选"
```

✅ 正例：

```python
FILTER_BTN = 'css=.list-content >> text="筛选"'   # 精确匹配，不命中「收起筛选」
```

**排查信号**：操作后预期状态没变化（面板被收起、搜索没生效、列表没过滤），但后续步骤没报错 → 检查是否有同名子串的切换按钮被误点。

---

## 字符串 `role=` 的 name 是全串精确匹配——要前缀/子串时用正则

**触发**：定位符常量写成 `role=<role>[name='...']` 字符串（BasePage 走 `page.locator(字符串)`），且可及名称比你写的更长，或大小写不同。

**失败现象**：可及名称为「Log in Log in」（头像 alt + 文字各一份）的按钮，写 `role=button[name='Log in']` 命中 0 个；
aria-label 为「Ask Alva anything. @ for context, / for skills」的输入框，写前缀也命中 0 个 —— 等满超时后报元素找不到。
Playwright 1.63 实测：字符串 `role=` 引擎的 name 区分大小写、必须整串相等；只有 `page.get_by_role(name=...)` 才是不区分大小写的子串匹配，两者语义不同，不能互相类推。

❌ 反例：

```python
LOGIN_BUTTON = "role=button[name='Log in']"            # 可及名称是「Log in Log in」→ 0 个
CHAT_INPUT = "role=textbox[name='Ask Alva anything']"  # 只写了前缀 → 0 个
```

✅ 正例：

```python
LOGIN_BUTTON = "role=button[name=/^Log in/]"            # 正则：前缀匹配
CHAT_INPUT = "role=textbox[name=/^Ask Alva anything/]"  # 后半段操作提示更易变，只锁前缀
COLLAPSE_BUTTON = "role=button[name='Collapse']"        # 名称完整且稳定时，精确写法即可
```

**排查信号**：`role=` 定位符超时，但 agent-browser snapshot 里明明有这个 role 和相近的名称 → 对照 snapshot 里的完整可及名称，改成整串或 `/^前缀/` 正则。
