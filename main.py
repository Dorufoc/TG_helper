#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import os
from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout,
    QLabel, QPushButton, QMessageBox
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont

# 导入BrowserWindow类
from browser_source_saver import BrowserWindow

try:
    from deepseek_parser import DeepSeekParserWindow
    DEEPSEEK_AVAILABLE = True
except ImportError:
    DEEPSEEK_AVAILABLE = False
    print("注意: deepseek_parser 模块不可用，DeepSeek解析功能将被禁用")


class MainWindow(QWidget):
    """主窗口：题库管理、浏览器捕捉、DeepSeek解析"""
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle("题库管理工具")
        self.setGeometry(100, 100, 600, 400)
        self.init_ui()
    
    def init_ui(self):
        """初始化界面"""
        self.main_layout = QVBoxLayout()
        
        # 标题
        title_label = QLabel("题库管理工具")
        title_label.setFont(QFont("Microsoft YaHei UI, Arial", 18, QFont.Bold))
        title_label.setAlignment(Qt.AlignCenter)
        self.main_layout.addWidget(title_label)
        
        # 功能按钮区域
        button_layout = QVBoxLayout()
        button_layout.setSpacing(15)
        
        # 手动导入题库按钮
        self.import_button = QPushButton("手动导入题库（浏览器捕捉）")
        self.import_button.setFont(QFont("Microsoft YaHei UI, Arial", 12))
        self.import_button.clicked.connect(self.open_browser_saver)
        button_layout.addWidget(self.import_button)
        
        # DeepSeek解析按钮
        self.deepseek_button = QPushButton("DeepSeek解析题库")
        self.deepseek_button.setFont(QFont("Microsoft YaHei UI, Arial", 12))
        if DEEPSEEK_AVAILABLE:
            self.deepseek_button.clicked.connect(self.open_deepseek_parser)
        else:
            self.deepseek_button.setEnabled(False)
            self.deepseek_button.setToolTip("DeepSeek解析模块不可用")
        button_layout.addWidget(self.deepseek_button)
        
        self.main_layout.addLayout(button_layout)
        self.main_layout.addStretch()
        
        # 设置布局
        self.setLayout(self.main_layout)
    
    def open_browser_saver(self):
        """打开浏览器源代码保存器"""
        self.browser_window = BrowserWindow()
        self.browser_window.show()
    
    def open_deepseek_parser(self):
        """打开DeepSeek解析窗口"""
        if DEEPSEEK_AVAILABLE:
            self.deepseek_window = DeepSeekParserWindow()
            self.deepseek_window.show()
        else:
            QMessageBox.warning(self, "功能不可用", "DeepSeek解析模块不可用，请确保deepseek_parser.py文件存在")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    # 设置全局默认字体为Microsoft YaHei UI，添加后备方案
    default_font = QFont()
    default_font.setFamily("Microsoft YaHei UI, Arial, Helvetica, sans-serif")
    app.setFont(default_font)
    main_window = MainWindow()
    main_window.show()
    sys.exit(app.exec_())
