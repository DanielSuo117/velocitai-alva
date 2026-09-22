"""业务页面对象层。

这里只放具体页面的 PageObject，一律继承 core.base.BasePage：

    from core.base.base_page import BasePage

    class LoginPage(BasePage):
        USERNAME = "#username"   # P0: 用户名输入框
        ...

多个页面共用的片段（侧边栏等）放在 components/，继承 core.base.BaseComponent，
由页面对象以属性持有（如 HomePage.sidebar）。

框架能力（基类、自愈、日志、异常）在 core/ —— 写登录页的人不该在这个目录
里读到自愈引擎。
"""
from pages.components.sidebar_nav import SidebarNav
from pages.home_page import HomePage
from pages.login_page import LoginPage

__all__ = ["HomePage", "LoginPage", "SidebarNav"]
