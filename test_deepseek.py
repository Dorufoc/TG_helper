#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
from PyQt5.QtWidgets import QApplication
from deepseek_parser import DeepSeekParserWindow

def test_window():
    app = QApplication(sys.argv)
    window = DeepSeekParserWindow()
    window.show()
    
    # 3秒后自动关闭
    from PyQt5.QtCore import QTimer
    QTimer.singleShot(3000, app.quit)
    
    sys.exit(app.exec_())

if __name__ == "__main__":
    test_window()