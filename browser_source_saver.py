import sys
import time
import os
from PyQt5.QtCore import QUrl, QStandardPaths, QCoreApplication
from PyQt5.QtWidgets import (
    QApplication,
    QMainWindow,
    QVBoxLayout,
    QHBoxLayout,
    QWidget,
    QLineEdit,
    QPushButton,
    QMessageBox,
    QSplitter,
    QTabWidget,
    QAction,
    QProgressDialog,
    QProgressBar
)
from PyQt5.QtWebEngineWidgets import QWebEngineView, QWebEngineProfile, QWebEnginePage, QWebEngineSettings
from PyQt5.QtCore import Qt


class BrowserWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("网页源代码捕捉器")
        self.setGeometry(100, 100, 1200, 800)
        
        # 创建数据存储目录
        self.data_dir = os.path.join(os.getcwd(), "browser_data")
        if not os.path.exists(self.data_dir):
            os.makedirs(self.data_dir)
        
        # 创建持久化的WebEngineProfile
        self.profile = QWebEngineProfile("default", self)
        # 设置持久化存储路径
        self.profile.setPersistentStoragePath(os.path.join(self.data_dir, "cache"))
        # 强制启用持久化cookie
        self.profile.setPersistentCookiesPolicy(QWebEngineProfile.ForcePersistentCookies)
        # 确保缓存和cookie共享
        self.profile.setHttpCacheType(QWebEngineProfile.DiskHttpCache)
        self.profile.setHttpCacheMaximumSize(50 * 1024 * 1024)  # 50MB缓存
        
        # 启用JavaScript和相关功能
        self.profile.settings().setAttribute(QWebEngineSettings.JavascriptEnabled, True)
        self.profile.settings().setAttribute(QWebEngineSettings.JavascriptCanOpenWindows, True)
        self.profile.settings().setAttribute(QWebEngineSettings.JavascriptCanAccessClipboard, True)
        self.profile.settings().setAttribute(QWebEngineSettings.LocalStorageEnabled, True)
        self.profile.settings().setAttribute(QWebEngineSettings.PluginsEnabled, True)
        # 启用本地存储
        self.profile.settings().setAttribute(QWebEngineSettings.LocalStorageEnabled, True)
        
        # 设置默认字体为Microsoft雅黑UI
        self.profile.settings().setFontFamily(QWebEngineSettings.StandardFont, "Microsoft YaHei UI")
        self.profile.settings().setFontFamily(QWebEngineSettings.SansSerifFont, "Microsoft YaHei UI")
        self.profile.settings().setFontFamily(QWebEngineSettings.SerifFont, "Microsoft YaHei UI")
        self.profile.settings().setFontFamily(QWebEngineSettings.FixedFont, "Microsoft YaHei UI")
        self.profile.settings().setFontFamily(QWebEngineSettings.CursiveFont, "Microsoft YaHei UI")
        self.profile.settings().setFontFamily(QWebEngineSettings.FantasyFont, "Microsoft YaHei UI")
        # 设置字体大小
        self.profile.settings().setFontSize(QWebEngineSettings.DefaultFontSize, 14)
        self.profile.settings().setFontSize(QWebEngineSettings.DefaultFixedFontSize, 12)
        
        # 创建地址栏
        self.url_bar = QLineEdit()
        self.url_bar.returnPressed.connect(self.navigate_to_url)
        
        # 创建导航按钮
        self.back_button = QPushButton("后退")
        self.back_button.clicked.connect(self.navigate_back)
        
        self.forward_button = QPushButton("前进")
        self.forward_button.clicked.connect(self.navigate_forward)
        
        self.reload_button = QPushButton("刷新")
        self.reload_button.clicked.connect(self.reload_page)
        
        self.go_button = QPushButton("前往")
        self.go_button.clicked.connect(self.navigate_to_url)
        
        # 创建手动捕捉按钮
        self.capture_button = QPushButton("手动捕捉")
        self.capture_button.setStyleSheet(
            "font-size: 14px; font-weight: bold; "
            "background-color: #2196F3; "  # 蓝色背景
            "color: white; "  # 白色文字
            "border: none; "
            "padding: 5px 15px; "
            "border-radius: 3px;"
        )
        self.capture_button.clicked.connect(self.save_page_source)
        
        # 创建生成题库按钮
        self.generate_bank_button = QPushButton("生成题库")
        self.generate_bank_button.setStyleSheet(
            "font-size: 14px; font-weight: bold; "
            "background-color: #4CAF50; "  # 绿色背景
            "color: white; "  # 白色文字
            "border: none; "
            "padding: 5px 15px; "
            "border-radius: 3px;"
        )
        self.generate_bank_button.clicked.connect(self.generate_question_bank)
        
        # 创建顶部导航栏布局
        nav_layout = QHBoxLayout()
        nav_layout.addWidget(self.back_button)
        nav_layout.addWidget(self.forward_button)
        nav_layout.addWidget(self.reload_button)
        nav_layout.addWidget(self.url_bar)
        nav_layout.addWidget(self.go_button)
        nav_layout.addWidget(self.capture_button)
        nav_layout.addWidget(self.generate_bank_button)
        nav_layout.setContentsMargins(5, 5, 5, 5)
        nav_layout.setSpacing(10)  # 设置按钮间距
        
        # 创建标签页控件
        self.tabs = QTabWidget()
        self.tabs.setTabsClosable(True)
        self.tabs.tabCloseRequested.connect(self.close_tab)
        self.tabs.currentChanged.connect(self.update_ui)
        # 安装事件过滤器，监听鼠标中键点击事件
        self.tabs.installEventFilter(self)
        
        # 添加第一个标签页
        self.add_new_tab()
        
        # 主布局 - 垂直布局，包含导航栏和标签页
        main_layout = QVBoxLayout()
        main_layout.addLayout(nav_layout)
        main_layout.addWidget(self.tabs)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        container = QWidget()
        container.setLayout(main_layout)
        self.setCentralWidget(container)
    
    def create_web_view(self, url="https://www.educoder.net"):
        """创建一个新的web视图，确保使用共享的profile"""
        web_view = QWebEngineView()
        # 确保所有页面使用同一个持久化profile
        web_page = QWebEnginePage(self.profile, web_view)
        
        # 页面会自动继承profile的settings，不需要重复设置
        # 只需要连接必要的信号
        web_page.urlChanged.connect(self.update_url_bar)
        web_page.titleChanged.connect(lambda title, view=web_view: self.update_tab_title(title, view))
        
        # 处理JavaScript新窗口请求
        web_page.createWindow = lambda _: self.handle_new_window()
        
        web_view.setPage(web_page)
        web_view.setUrl(QUrl(url))
        
        return web_view
    
    def add_new_tab(self, url="https://www.educoder.net"):
        """添加一个新标签页"""
        web_view = self.create_web_view(url)
        index = self.tabs.addTab(web_view, "加载中...")
        self.tabs.setCurrentIndex(index)
    
    def close_tab(self, index):
        """关闭标签页"""
        if self.tabs.count() > 1:
            self.tabs.removeTab(index)
        else:
            # 至少保留一个标签页
            web_view = self.tabs.widget(0)
            web_view.setUrl(QUrl("https://www.educoder.net"))
    
    def update_tab_title(self, title, web_view):
        """更新标签页标题"""
        index = self.tabs.indexOf(web_view)
        if index >= 0:
            self.tabs.setTabText(index, title if title else "空页面")
    
    def handle_new_window(self):
        """处理JavaScript新窗口请求"""
        new_web_view = self.create_web_view()
        index = self.tabs.addTab(new_web_view, "新标签页")
        self.tabs.setCurrentIndex(index)
        return new_web_view.page()
    
    def update_ui(self):
        """更新UI状态"""
        current_web_view = self.tabs.currentWidget()
        if current_web_view:
            page = current_web_view.page()
            self.url_bar.setText(page.url().toString())
    
    def navigate_to_url(self):
        """导航到指定URL"""
        url = self.url_bar.text()
        if not url.startswith("http"):
            url = f"http://{url}"
        current_web_view = self.tabs.currentWidget()
        if current_web_view:
            current_web_view.setUrl(QUrl(url))
    
    def update_url_bar(self, q):
        """更新地址栏"""
        current_web_view = self.tabs.currentWidget()
        if current_web_view and current_web_view.page().url() == q:
            self.url_bar.setText(q.toString())
    
    def navigate_back(self):
        """后退"""
        current_web_view = self.tabs.currentWidget()
        if current_web_view:
            current_web_view.back()
    
    def navigate_forward(self):
        """前进"""
        current_web_view = self.tabs.currentWidget()
        if current_web_view:
            current_web_view.forward()
    
    def reload_page(self):
        """刷新页面"""
        current_web_view = self.tabs.currentWidget()
        if current_web_view:
            current_web_view.reload()
    
    def save_page_source(self):
        """保存当前网页的源代码到项目目录的html文件夹中，文件名使用时间戳"""
        # 获取当前页面
        current_web_view = self.tabs.currentWidget()
        if not current_web_view:
            QMessageBox.warning(self, "提示", "没有打开的页面")
            return
        
        page = current_web_view.page()
        
        # 请求页面源代码
        def handle_source(source):
            try:
                # 创建html文件夹
                html_dir = os.path.join(os.getcwd(), "html")
                if not os.path.exists(html_dir):
                    os.makedirs(html_dir)
                
                # 生成时间戳文件名
                timestamp = time.strftime("%Y%m%d_%H%M%S")
                filename = f"page_source_{timestamp}.html"
                file_path = os.path.join(html_dir, filename)
                
                # 保存源代码到文件
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(source)
                
                QMessageBox.information(
                    self,
                    "保存成功",
                    f"源代码已成功保存到：{file_path}"
                )
            except Exception as e:
                QMessageBox.critical(
                    self,
                    "保存失败",
                    f"保存源代码时出错：{str(e)}"
                )
        
        # 获取页面源代码
        page.toHtml(handle_source)
    
    def eventFilter(self, obj, event):
        """事件过滤器，处理鼠标中键点击关闭标签页"""
        if obj == self.tabs:
            if event.type() == event.MouseButtonPress and event.button() == Qt.MiddleButton:
                # 获取点击位置对应的标签索引
                index = self.tabs.tabBar().tabAt(event.pos())
                if index >= 0:
                    self.close_tab(index)
                    return True
        return super(BrowserWindow, self).eventFilter(obj, event)
    
    def generate_question_bank(self):
        """根据已捕获的网页生成题库"""
        # 检查html文件夹是否存在
        html_dir = os.path.join(os.getcwd(), "html")
        if not os.path.exists(html_dir):
            QMessageBox.warning(self, "提示", "未找到已捕获的网页文件，请先使用手动捕捉功能")
            return
        
        # 获取所有已捕获的html文件
        html_files = [f for f in os.listdir(html_dir) if f.endswith(".html")]
        if not html_files:
            QMessageBox.warning(self, "提示", "html文件夹中没有已捕获的网页文件")
            return
        
        # 创建进度对话框
        progress_dialog = QProgressDialog("正在生成题库...", "取消", 0, 100, self)
        progress_dialog.setWindowTitle("生成题库")
        progress_dialog.setWindowModality(Qt.WindowModal)
        progress_dialog.setMinimumDuration(0)
        progress_dialog.setValue(0)
        
        # 导入parse_questions模块
        try:
            from parse_questions import process_all_html_files
            
            # 处理进度对话框更新
            def update_progress(current, total):
                progress = int((current / total) * 100)
                progress_dialog.setValue(progress)
                progress_dialog.setLabelText(f"正在处理文件 {current}/{total}")
            
            # 调用process_all_html_files函数生成题库
            process_all_html_files()
            
            # 完成后提示
            progress_dialog.setValue(100)
            QMessageBox.information(
                self,
                "生成成功",
                f"已成功从 {len(html_files)} 个网页文件中生成题库\n\n" +
                "生成的题库文件已保存到当前目录的questions.json"
            )
        except Exception as e:
            QMessageBox.critical(
                self,
                "生成失败",
                f"生成题库时出错：{str(e)}"
            )


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = BrowserWindow()
    window.show()
    sys.exit(app.exec_())
