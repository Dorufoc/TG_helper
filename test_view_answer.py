#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
    QRadioButton, QCheckBox, QPushButton, QGroupBox, QLineEdit
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont, QPalette, QColor

class TestViewAnswer(QWidget):
    """测试查看答案功能"""
    
    def __init__(self):
        super().__init__()
        self.init_ui()
    
    def init_ui(self):
        """初始化界面"""
        self.setWindowTitle("查看答案功能测试")
        self.setGeometry(100, 100, 700, 500)
        
        # 创建主布局
        main_layout = QVBoxLayout(self)
        
        # 添加测试标题
        title = QLabel("查看答案功能测试")
        title.setFont(QFont("Microsoft YaHei UI, Arial", 16, QFont.Bold))
        title.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(title)
        
        # 添加说明
        instructions = QLabel("测试说明：\n- 点击'查看答案'按钮，验证选项颜色是否变化\n- 测试选择题、多选题和填空题的答案显示")
        instructions.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(instructions)
        
        # 测试选择题
        main_layout.addWidget(self.create_radio_test())
        
        # 测试多选题
        main_layout.addWidget(self.create_checkbox_test())
        
        # 测试填空题
        main_layout.addWidget(self.create_fill_test())
        
        # 测试结果
        self.result_label = QLabel("测试结果: 等待测试")
        self.result_label.setAlignment(Qt.AlignCenter)
        self.result_label.setStyleSheet("font-weight: bold; color: blue;")
        main_layout.addWidget(self.result_label)
        
        # 查看答案按钮
        self.view_answer_button = QPushButton("查看答案")
        self.view_answer_button.clicked.connect(self.test_view_answer)
        main_layout.addWidget(self.view_answer_button)
    
    def create_radio_test(self):
        """创建选择题测试"""
        group = QGroupBox("1. 选择题测试")
        group_layout = QVBoxLayout(group)
        
        # 添加选项
        options = ["A. 选项1", "B. 选项2", "C. 选项3", "D. 选项4"]
        self.radio_buttons = []
        self.radio_labels = []
        for option in options:
            # 创建选项容器
            option_layout = QHBoxLayout()
            
            # 创建单选按钮
            radio = QRadioButton()
            self.radio_buttons.append(radio)
            
            # 创建选项文本标签
            label = QLabel(option)
            self.radio_labels.append(label)
            
            option_layout.addWidget(radio)
            option_layout.addWidget(label, 1)
            group_layout.addLayout(option_layout)
        
        return group
    
    def create_checkbox_test(self):
        """创建多选题测试"""
        group = QGroupBox("2. 多选题测试")
        group_layout = QVBoxLayout(group)
        
        # 添加选项
        options = ["A. 选项A", "B. 选项B", "C. 选项C", "D. 选项D"]
        self.checkboxes = []
        self.checkbox_labels = []
        for option in options:
            # 创建选项容器
            option_layout = QHBoxLayout()
            
            # 创建复选框
            checkbox = QCheckBox()
            self.checkboxes.append(checkbox)
            
            # 创建选项文本标签
            label = QLabel(option)
            self.checkbox_labels.append(label)
            
            option_layout.addWidget(checkbox)
            option_layout.addWidget(label, 1)
            group_layout.addLayout(option_layout)
        
        return group
    
    def create_fill_test(self):
        """创建填空题测试"""
        group = QGroupBox("3. 填空题测试")
        group_layout = QVBoxLayout(group)
        
        # 添加输入框
        self.fill_inputs = []
        for i in range(2):
            input_layout = QHBoxLayout()
            input_label = QLabel(f"第{i+1}个空:")
            fill_input = QLineEdit()
            fill_input.setPlaceholderText(f"请输入第{i+1}个空的答案")
            self.fill_inputs.append(fill_input)
            
            input_layout.addWidget(input_label)
            input_layout.addWidget(fill_input)
            group_layout.addLayout(input_layout)
        
        # 添加正确答案标签
        self.correct_labels = []
        for i in range(2):
            correct_label = QLabel()
            correct_label.setVisible(False)
            self.correct_labels.append(correct_label)
            group_layout.addWidget(correct_label)
        
        return group
    
    def test_view_answer(self):
        """测试查看答案功能"""
        # 测试选择题
        self.test_radio_answer()
        
        # 测试多选题
        self.test_checkbox_answer()
        
        # 测试填空题
        self.test_fill_answer()
        
        self.result_label.setText("测试结果: 查看答案功能测试完成")
        self.result_label.setStyleSheet("font-weight: bold; color: green;")
    
    def test_radio_answer(self):
        """测试选择题查看答案"""
        # 模拟正确答案为选项B
        correct_answer = ["B. 选项2"]
        
        # 高亮显示答案
        for label in self.radio_labels:
            palette = label.palette()
            if label.text() in correct_answer:
                palette.setColor(QPalette.WindowText, QColor(0, 128, 0))  # 绿色
            else:
                palette.setColor(QPalette.WindowText, QColor(255, 0, 0))  # 红色
            label.setPalette(palette)
    
    def test_checkbox_answer(self):
        """测试多选题查看答案"""
        # 模拟正确答案为选项A和选项C
        correct_answer = ["A. 选项A", "C. 选项C"]
        
        # 高亮显示答案
        for label in self.checkbox_labels:
            palette = label.palette()
            if label.text() in correct_answer:
                palette.setColor(QPalette.WindowText, QColor(0, 128, 0))  # 绿色
            else:
                palette.setColor(QPalette.WindowText, QColor(255, 0, 0))  # 红色
            label.setPalette(palette)
    
    def test_fill_answer(self):
        """测试填空题查看答案"""
        # 模拟正确答案
        correct_answers = ["答案1", "答案2"]
        
        # 显示正确答案
        for i in range(len(self.fill_inputs)):
            fill_input = self.fill_inputs[i]
            correct_label = self.correct_labels[i]
            
            if i < len(correct_answers):
                correct_text = correct_answers[i]
                user_text = fill_input.text()
                
                # 比较用户答案和正确答案
                is_correct = user_text.strip() == correct_text.strip()
                
                # 设置用户输入框的样式
                if is_correct:
                    fill_input.setStyleSheet("background-color: lightgreen;")
                else:
                    fill_input.setStyleSheet("background-color: lightcoral;")
                
                # 显示正确答案
                correct_label.setText(f"正确答案 {i+1}: {correct_text}")
                correct_label.setStyleSheet("color: green; font-weight: bold;")
            else:
                # 如果没有正确答案，显示提示
                correct_label.setText("(本题暂无标准答案)")
                correct_label.setStyleSheet("color: orange;")
            
            correct_label.setVisible(True)

def test_view_answer():
    """测试查看答案功能"""
    print("测试查看答案功能...")
    print("1. 创建测试应用")
    
    app = QApplication(sys.argv)
    # 设置全局默认字体为Microsoft YaHei UI，添加后备方案
    default_font = QFont()
    default_font.setFamily("Microsoft YaHei UI, Arial, Helvetica, sans-serif")
    app.setFont(default_font)
    window = TestViewAnswer()
    print("2. 显示测试窗口")
    window.show()
    
    print("3. 运行测试应用")
    print("\n测试说明：")
    print("- 点击'查看答案'按钮，验证选项颜色是否变化")
    print("- 测试选择题、多选题和填空题的答案显示")
    
    sys.exit(app.exec_())

if __name__ == "__main__":
    test_view_answer()
