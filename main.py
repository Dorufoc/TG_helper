#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import os
import tkinter as tk
from tkinter import messagebox
import subprocess
import threading

# 功能模块延迟加载标记
DEEPSEEK_AVAILABLE = False
DeepSeekParserWindow = None

# 尝试导入DeepSeek解析器
try:
    from deepseek_parser import DeepSeekParserWindow as DSPW
    DeepSeekParserWindow = DSPW
    DEEPSEEK_AVAILABLE = True
except ImportError:
    print("注意: deepseek_parser 模块不可用，DeepSeek解析功能将被禁用")


def launch_browser_saver_in_subprocess():
    """在新的进程中启动浏览器源代码保存器"""
    script = """
import sys
from PyQt5.QtWidgets import QApplication
from PyQt5.QtGui import QFont
from browser_source_saver import BrowserWindow

app = QApplication(sys.argv)
app.setFont(QFont("Microsoft YaHei UI"))
window = BrowserWindow()
window.show()
sys.exit(app.exec_())
"""
    subprocess.Popen([sys.executable, "-c", script], cwd=os.getcwd())


def launch_deepseek_parser_in_subprocess():
    """在新的进程中启动DeepSeek解析窗口"""
    script = """
import sys
from PyQt5.QtWidgets import QApplication
from PyQt5.QtGui import QFont
from deepseek_parser import DeepSeekParserWindow

app = QApplication(sys.argv)
app.setFont(QFont("Microsoft YaHei UI"))
window = DeepSeekParserWindow()
window.show()
sys.exit(app.exec_())
"""
    subprocess.Popen([sys.executable, "-c", script], cwd=os.getcwd())


class MainWindow:
    """主窗口：题库管理工具（使用tkinter实现）"""
    
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("题库管理工具")
        self.root.geometry("400x300")
        self.root.resizable(False, False)
        
        # 设置窗口图标（如果有的话）
        try:
            self.root.iconbitmap("icon.ico")
        except:
            pass
        
        self.init_ui()
    
    def init_ui(self):
        """初始化界面"""
        # 标题
        title_label = tk.Label(
            self.root,
            text="题库管理工具",
            font=("Microsoft YaHei UI", 18, "bold"),
            fg="#333333"
        )
        title_label.pack(pady=(40, 30))
        
        # 按钮容器
        button_frame = tk.Frame(self.root)
        button_frame.pack(pady=10)
        
        # 手动导入题库按钮
        self.import_button = tk.Button(
            button_frame,
            text="手动导入题库（浏览器捕捉）",
            font=("Microsoft YaHei UI", 11),
            width=28,
            height=2,
            bg="#2196F3",
            fg="white",
            relief="flat",
            cursor="hand2",
            activebackground="#1976D2",
            activeforeground="white",
            command=self.on_browser_saver_click
        )
        self.import_button.pack(pady=8)
        
        # DeepSeek解析按钮
        if DEEPSEEK_AVAILABLE:
            self.deepseek_button = tk.Button(
                button_frame,
                text="DeepSeek解析题库",
                font=("Microsoft YaHei UI", 11),
                width=28,
                height=2,
                bg="#4CAF50",
                fg="white",
                relief="flat",
                cursor="hand2",
                activebackground="#388E3C",
                activeforeground="white",
                command=self.on_deepseek_parser_click
            )
        else:
            self.deepseek_button = tk.Button(
                button_frame,
                text="DeepSeek解析题库（不可用）",
                font=("Microsoft YaHei UI", 11),
                width=28,
                height=2,
                bg="#BDBDBD",
                fg="#757575",
                relief="flat",
                state="disabled",
                cursor="arrow"
            )
        self.deepseek_button.pack(pady=8)
    
    def on_browser_saver_click(self):
        """点击浏览器捕捉按钮"""
        try:
            launch_browser_saver_in_subprocess()
        except Exception as e:
            messagebox.showerror("启动失败", f"无法启动浏览器模块：{str(e)}")
    
    def on_deepseek_parser_click(self):
        """点击DeepSeek解析按钮"""
        if not DEEPSEEK_AVAILABLE:
            messagebox.showwarning("功能不可用", "DeepSeek解析模块不可用")
            return
        
        try:
            launch_deepseek_parser_in_subprocess()
        except Exception as e:
            messagebox.showerror("启动失败", f"无法启动DeepSeek解析模块：{str(e)}")
    
    def run(self):
        """运行主循环"""
        self.root.mainloop()


if __name__ == "__main__":
    # Windows平台DPI优化
    if sys.platform == 'win32':
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    
    main_window = MainWindow()
    main_window.run()
