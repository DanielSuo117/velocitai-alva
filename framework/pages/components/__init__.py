"""可复用 UI 组件层。

这里放在多个页面重复出现的片段（侧边栏、弹窗、搜索浮层……），一律继承
core.base.BaseComponent：组件内的定位符写成相对形态，真正定位时由基类拼上
ROOT 作用域（`ROOT >> 选择器`），同一个 class 在页面别处出现时不会串台。

页面对象通过属性持有组件实例（如 HomePage.sidebar），而不是复制组件的定位符
—— 组件改版时只改这一处。
"""
from pages.components.sidebar_nav import SidebarNav

__all__ = ["SidebarNav"]
