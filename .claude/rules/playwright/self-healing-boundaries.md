---
# 自愈的开关在 conftest / pytest.ini，判定在 core/healing，写回落在 pages —— 只在碰这些文件时加载。
paths:
  - "framework/core/healing/**"
  - "tests/conftest.py"
  - "framework/pages/**"
  - "pytest.ini"
---

# 选择器自愈边界

**触发**：启用 `--self-heal`、复核自愈提案、调整自愈判定阈值、或自愈让某个用例由红转绿时。

自愈的价值是消除误报，风险是制造假通过。下列条款全部围绕同一条底线：
**自愈只能修复「定位」，绝不能把真失败变成假通过。**

---

## P0.1 · 自愈必须显式开启

**触发**：在 CI 或本地脚本里配置回归命令时。

自愈改变了「失败」的含义，不能悄悄生效。默认 `off`；CI 建议 `strict`
（发生自愈即以非零码结束，让定位符漂移被看见）。

❌ 在 conftest 或基类里把 `self_heal_enabled` 默认设为 True，让所有人无感知地跑在自愈模式下

✅ `pytest tests/ --env=<env> --self-heal=strict`，开关写在命令里，谁开的、开了什么一目了然

---

## P0.2 · 候选必须唯一命中且意图一致

**触发**：修改 `rank()` 的判定条件或新增候选生成策略时。

「唯一命中」和「意图指纹一致」是防假通过的两道闸，缺一不可。只要唯一性，
可能顶替到页面上另一个恰好唯一的无关元素；只要指纹，可能同时匹配多个同类元素。

❌ 因为某个用例总也自愈不成功，就把 `_matches_fingerprint` 里的 role 判定去掉

✅ 承认这次找不到可靠替代，让用例按原样失败，再人工看 DOM 到底改了什么

---

## P0.3 · 找不到可靠替代就失败，不许凑

**触发**：自愈成功率偏低，想调低 `MIN_CONFIDENCE` 时。

置信度阈值是「证据够不够」的刻度，不是成功率旋钮。调低它不会让定位更准，
只会让更弱的猜测被当成结论。

❌ 把 `MIN_CONFIDENCE` 从 70 降到 40，让 stable-class 候选也能被采纳，换取「自愈率提升」

✅ 保持阈值，转而推动前端补 `data-testid` —— 那才是真正让定位稳定的办法

---

## P0.4 · 运行期绝不改写源码

**触发**：想让自愈「一步到位」自动改 PageObject 时。

测试进程里自动改源码，意味着一次跑飞的回归可以静默重写整个 PageObject 层，
而改动淹没在测试输出里。写回必须是独立、可审阅、可回滚的一步。

❌ 在 `attempt()` 里直接用新选择器覆盖 PageObject 源文件

✅ 运行期只写 `proposals.jsonl`，由 [selector-self-heal](../../skills/selector-self-heal/) 复核后写回，并过落库闸门

---

## P0.5 · 自愈过的用例不算干净通过

**触发**：查看启用自愈后的测试报告时。

自愈成功说明定位符已经漂移。沉默地放过去，下次就是真失败，而且没人知道
从哪一次开始坏的。

❌ 自愈成功后当作普通通过，报告里不留痕迹

✅ 终端汇总里逐条列出 `旧选择器 -> 新选择器（策略，置信度）`，并保留提案文件待写回

---

## P0.6 · 哈希类名不得作为自愈锚点

**触发**：扩展候选生成策略、或发现自愈选出的选择器很快再次失效时。

构建工具生成的类名（`css-1a2b3c`、`sc-bdVaJa`、`Button_a1b2c3`）下次构建就会变。
拿它当锚点等于把下一次失效写进代码。

❌ 采用 `.css-1a2b3c` 作为修复结果，因为它在当前页面确实唯一命中

✅ 跳过哈希段，优先 `data-testid` → `id` → `role + 可及名称`，都没有就放弃自愈

## P0.7 · 自愈必须反应式触发，不得预探测

**触发**：修改拦截器的触发时机，或想「提前判断选择器是否还有效」时。

`locator.count()` 不做自动等待。用它在操作前预探测，会把 SPA 页面上
「元素还没渲染」误判成「定位失效」，从而在半渲染的页面上启动自愈 ——
顶替到一个恰好已渲染的无关元素，用例照绿而点的是别的按钮。

❌ 在操作前用 `if page.locator(sel).count() == 0: heal(sel)` 提前判断选择器是否失效

✅ 正常执行操作，捕获异常后用 `is_location_failure(exc)` 判定，确属定位失败才自愈并重试一次

---

## P0.8 · 定位作用域必须收口在一处

**触发**：给基类加新的定位方法、或让子类（组件、iframe 包装）改变定位范围时。

`BaseComponent` 曾只覆盖 `_locate()`，而 `click` / `fill` 这些操作走的是 `_act()` ——
覆盖被整条绕过，组件的 `ROOT` 形同虚设，弹窗里的 `.btn-ok` 跑到整页去找。
同名元素在页面主区也有一个时就点错了，且**自愈关闭也照样错**。

作用域一旦有两个出口，加方法的人迟早漏掉一个。

❌ 子类覆盖 `_locate()` 来改变定位范围，而基类另有 `_act()` 直接 `page.locator(selector)`

✅ 基类提供唯一的 `scope_root()`，`_act()` / `_locate()` 都经 `_scoped()` 取用；子类只覆盖 `scope_root()`

---

## P0.9 · 定位失败判定宁可漏判，不可误判

**触发**：扩充 `is_location_failure` 的关键词、或发现某类失败「本该自愈却没愈」时。

漏判的代价是用例照常失败 —— 等于没有自愈，安全。误判的代价是在不该动的场景上
启动自愈，可能把真失败变成假通过。两者不对等，判定必须偏保守。

实测踩过的两个坑：`page.goto` 的导航超时同样是 `TimeoutError`，「凡超时即定位失败」
会在一个根本没加载出来的页面上启动自愈；一个写着 `no element matches the criteria`
的业务 `ValueError` 也会被纯文本匹配误判。

❌ `if type(exc).__name__ == "TimeoutError": return True`，或只靠 `"no element matches" in str(exc)`

✅ 页面级操作（`page.goto` / `page.wait_for_url` / `page.wait_for_load_state`）先硬否决；
普通措辞只在异常确由 Playwright 抛出时才认；拿不准返回 `False`

---

## P0.10 · 推理的 token 上限必须容纳「思考」，截断不得静默

**触发**：给自愈的 LLM 后端设 `max_tokens`，或换用一个会思考（reasoning）的模型时。

**失败现象**：会思考的模型把思考 token 也计入 `max_tokens`。上限给小了，整个预算会被
思考耗尽，响应里只有 thinking 块、一个 text 块都没有，`stop_reason=max_tokens`。
解析器拿不到 JSON 就返回空候选 —— 而这与「模型认为没有合适元素、正确地交白卷」
在调用方看来完全一样。实测某会思考的模型在一个难例上思考就花掉约 4500 token，
上限 1024/2048/4096 时 **100% 落进这种情况**，且没有任何报错线索。

推理层对故障静默是对的（它不该影响测试结论），但不能静默到查不出该调哪个参数。

❌ 反例：

```python
body = {"model": model, "max_tokens": 1024, "messages": [...]}
...
return parse_response(payload)      # 截断和「交白卷」都返回 []，无从区分
```

✅ 正例：上限按难例实测值留足余量，并在截断时点名：

```python
MAX_TOKENS = 8192      # 实测难例思考约 4500 token；目标明确时仅约 500，不产生额外开销

candidates = parse_response(payload)
if not candidates and payload.get("stop_reason") == "max_tokens":
    log.warning("响应被 max_tokens 截断（已用 %s，上限 %s）：思考 token 也计入该上限",
                (payload.get("usage") or {}).get("output_tokens"), MAX_TOKENS)
return candidates
```

---

## P0.11 · 桩掉外部依赖的用例，证明不了被测对象真有那个能力

**触发**：为「调用外部服务并依据其返回做判断」的逻辑写用例时，把那次调用桩掉。

**失败现象**：桩注入的返回值是人写的，于是用例只验证了「拿到这个返回之后处理得对不对」，
而「外部服务实际上会不会给出这个返回」从未被验证。实测本项目：LLM 自愈的端到端用例
桩掉模型响应后一路通过，但真实模型在同一场景下**只会交白卷** —— 因为喂过去的元素快照
被压缩步骤丢掉了区分性字段，两个候选元素的记录逐字节相同。桩版绿灯，缺陷藏了整版。

桩本身没错（用例要能离线跑、不花钱、结论确定），错在只有桩版。两类断言必须分开守：
桩版守「拿到候选之后闸是否照常把关」，实网版守「模型是否真的给得出这个候选」。
实网版默认 skip，靠显式环境变量开启，这样默认套件仍然离线、免费、确定。

**验证**：`tests/e2e/test_llm_healing_live.py::test_model_discriminates_by_scope_and_data_attrs`
—— 该用例在修复前必然失败（真实模型交白卷），修复后通过；配套的
`test_model_still_declines_when_truly_indistinguishable` 守住反向边界。

❌ 反例：只有桩版，且桩里塞的是人推理出来的理想答案

```python
fake_api(['main >> role=button[name="登录"]'])   # 模型当时根本推不出这个
po.click(AmbiguousLoginPage.MAIN_LOGIN_BTN)
assert len(drift()) == 1                          # 绿灯，但什么都没证明
```

✅ 正例：桩版守闸，另加一条默认 skip 的实网用例守能力

```python
pytestmark = pytest.mark.skipif(
    not (os.environ.get("SELF_HEAL_LIVE") == "1" and llm.available()),
    reason="实网用例：需显式开启且已配置 key")

def test_model_discriminates(page):
    healed = runtime.attempt(page, MAIN_LOGIN, use_llm=True)
    assert healed, "模型没能给出候选 —— 检查快照是否又把区分性信息丢了"
    page.locator(runtime.scoped(healed)).click()
    assert page.evaluate("() => window.CLICKED") == ["main-login"]
```

---

相关：[selector-self-heal skill](../../skills/selector-self-heal/) ·
[locator-strategy](./locator-strategy.md) · [落库闸门](../agent-behavior/evolution-gate.md)
