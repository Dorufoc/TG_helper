#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import json
import os
import random
from datetime import datetime
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QLineEdit, QSlider, QProgressBar,
    QRadioButton, QCheckBox, QGroupBox, QMessageBox,
    QGridLayout, QFileDialog, QFrame, QScrollArea, QMenu,
    QSizePolicy, QButtonGroup
)
from PyQt5.QtCore import Qt, QSize, QEvent
from PyQt5.QtGui import QFont, QPalette, QColor

# 导入BrowserWindow类
from browser_source_saver import BrowserWindow

try:
    from deepseek_parser import DeepSeekParserWindow
    DEEPSEEK_AVAILABLE = True
except ImportError:
    DEEPSEEK_AVAILABLE = False
    print("注意: deepseek_parser 模块不可用，DeepSeek解析功能将被禁用")




class QuestionManager:
    """题库管理类，负责题库加载、统计和题目抽取"""
    
    def __init__(self):
        self.questions = []
        self.question_stats = {}
        self.selected_questions = []
        self.current_question_index = 0
        self.user_answers = {}
        self.viewed_answers = {}
        self.current_file = "questions.json"  # 默认题库文件
        
    def load_questions(self, file_path):
        """加载题库文件"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                self.questions = json.load(f)
            self.current_file = file_path
            self._calculate_stats()
            return True
        except Exception as e:
            print(f"加载题库失败: {e}")
            return False
    
    def _calculate_stats(self):
        """计算各题型数量"""
        self.question_stats.clear()
        for question in self.questions:
            q_type = question['type']
            if q_type in self.question_stats:
                self.question_stats[q_type] += 1
            else:
                self.question_stats[q_type] = 1
    
    def get_stats(self):
        """获取题库统计信息"""
        return self.question_stats
    
    def get_total_questions(self):
        """获取题库总题数"""
        return len(self.questions)
    
    def extract_questions(self, total_count, type_ratios):
        """根据比例配置抽取题目"""
        # 计算各题型应抽取的数量
        question_counts = {}
        for q_type, ratio in type_ratios.items():
            if q_type in self.question_stats:
                # 计算数量，确保不超过实际可用数量
                count = int(total_count * ratio / 100)
                question_counts[q_type] = min(count, self.question_stats[q_type])
        
        # 分配剩余题目
        remaining = total_count - sum(question_counts.values())
        if remaining > 0:
            # 按题型数量比例分配剩余题目
            for q_type in question_counts:
                if remaining <= 0:
                    break
                available = self.question_stats[q_type] - question_counts[q_type]
                if available > 0:
                    add_count = min(remaining, available)
                    question_counts[q_type] += add_count
                    remaining -= add_count
        
        return self._extract_by_counts(question_counts)
    
    def extract_questions_by_count(self, type_counts):
        """根据直接数量配置抽取题目"""
        return self._extract_by_counts(type_counts)
    
    def _extract_by_counts(self, type_counts):
        """根据各题型数量抽取题目"""
        self.selected_questions = []
        self.user_answers = {}
        self.viewed_answers = {}
        self.current_question_index = 0
        
        # 定义题型顺序
        type_order = ['单选题', '多选题', '判断题', '填空题']
        
        # 从各题型中随机抽取题目，按题型顺序添加到列表
        for q_type in type_order:
            if q_type in type_counts and type_counts[q_type] > 0:
                # 筛选出该题型的所有题目
                type_questions = [q for q in self.questions if q['type'] == q_type]
                # 随机抽取指定数量的题目
                selected = random.sample(type_questions, min(type_counts[q_type], len(type_questions)))
                self.selected_questions.extend(selected)
        
        return self.selected_questions
    
    def get_current_question(self):
        """获取当前题目"""
        if 0 <= self.current_question_index < len(self.selected_questions):
            return self.selected_questions[self.current_question_index]
        return None
    
    def save_user_answer(self, question_index, answer):
        """保存用户答案"""
        self.user_answers[question_index] = answer
    
    def get_user_answer(self, question_index):
        """获取用户答案"""
        return self.user_answers.get(question_index, [])
    
    def mark_answer_viewed(self, question_index):
        """标记答案已查看"""
        self.viewed_answers[question_index] = True
    
    def is_answer_viewed(self, question_index):
        """检查答案是否已查看"""
        return self.viewed_answers.get(question_index, False)
    
    def get_wrong_questions(self):
        """获取答错的题目"""
        wrong_questions = []
        for i, question in enumerate(self.selected_questions):
            user_answer = self.get_user_answer(i)
            correct_answer = question['correct_answer']
            
            # 根据题型检查答案是否正确
            is_correct = False
            if question['type'] in ['单选题', '判断题', '多选题']:
                is_correct = set(user_answer) == set(correct_answer)
            elif question['type'] == '填空题':
                if len(user_answer) == len(correct_answer):
                    is_all_correct = True
                    for ua, ca in zip(user_answer, correct_answer):
                        if ua.strip() != ca.strip():
                            is_all_correct = False
                            break
                    is_correct = is_all_correct
            
            if not is_correct:
                wrong_questions.append(question)
        return wrong_questions
    
    def export_wrong_questions(self, file_path):
        """导出答错的题目到文件"""
        wrong_questions = self.get_wrong_questions()
        if not wrong_questions:
            return False, "没有答错的题目"
        
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(wrong_questions, f, ensure_ascii=False, indent=2)
            return True, f"错题本已导出到: {file_path}"
        except Exception as e:
            return False, f"导出失败: {e}"


class ConfigWindow(QWidget):
    """题目抽取配置界面"""
    
    def __init__(self, question_manager):
        super().__init__()
        self.question_manager = question_manager
        self.setWindowTitle("答题配置")
        self.setGeometry(100, 100, 600, 450)
        self.init_ui()
    
    def init_ui(self):
        """初始化界面"""
        self.main_layout = QVBoxLayout()
        
        # 标题
        title_label = QLabel("答题配置")
        title_label.setFont(QFont("Microsoft YaHei UI, Arial", 18, QFont.Bold))
        title_label.setAlignment(Qt.AlignCenter)
        self.main_layout.addWidget(title_label)
        
        # 题库选择区域
        file_layout = QHBoxLayout()
        file_label = QLabel("当前题库：")
        self.file_combo = QPushButton(self.question_manager.current_file)
        self.file_combo.clicked.connect(self.show_file_menu)
        
        # 添加手动导入题库按钮
        self.manual_import_button = QPushButton("手动导入题库")
        self.manual_import_button.clicked.connect(self.open_browser_saver)
        
        file_layout.addWidget(file_label)
        file_layout.addWidget(self.file_combo)
        file_layout.addWidget(self.manual_import_button)
        file_layout.addStretch()
        self.main_layout.addLayout(file_layout)
        
        # 加载默认题库
        self.question_manager.load_questions(self.question_manager.current_file)
        
        # 题库统计信息
        stats = self.question_manager.get_stats()
        stats_text = "题库统计：\n"
        for q_type, count in stats.items():
            stats_text += f"{q_type}: {count}题\n"
        self.stats_label = QLabel(stats_text)
        self.stats_label.setFont(QFont("Microsoft YaHei UI, Arial", 10))
        self.main_layout.addWidget(self.stats_label)
        
        # 题型数量设置区域
        self.type_layouts = []
        self.type_count_inputs = {}
        for q_type in stats.keys():
            count_layout = QHBoxLayout()
            count_label = QLabel(f"{q_type}数量：")
            count_input = QLineEdit()
            count_input.setText(str(min(5, stats[q_type])))
            count_input.setMaxLength(3)
            count_input.setFixedWidth(50)
            count_layout.addWidget(count_label)
            count_layout.addWidget(count_input)
            self.main_layout.addLayout(count_layout)
            self.type_count_inputs[q_type] = count_input
            self.type_layouts.append(count_layout)
        
        # DeepSeek解析按钮
        self.deepseek_button = QPushButton("DeepSeek解析")
        if DEEPSEEK_AVAILABLE:
            self.deepseek_button.clicked.connect(self.open_deepseek_parser)
        else:
            self.deepseek_button.setEnabled(False)
            self.deepseek_button.setToolTip("DeepSeek解析模块不可用")
        self.main_layout.addWidget(self.deepseek_button)
        
        # 开始答题按钮
        self.start_button = QPushButton("开始答题")
        self.start_button.clicked.connect(self.start_exam)
        self.main_layout.addWidget(self.start_button)
        
        # 设置布局
        self.setLayout(self.main_layout)
    
    def show_file_menu(self):
        """显示题库文件选择菜单"""
        # 获取当前目录下的所有JSON文件
        json_files = [f for f in os.listdir('.') if f.endswith('.json')]
        
        # 创建菜单
        menu = QMenu(self)
        
        # 添加默认题库选项
        default_action = menu.addAction("questions.json")
        default_action.triggered.connect(lambda: self.load_question_file("questions.json"))
        
        # 添加错题集选项
        if len(json_files) > 1:
            menu.addSeparator()
            wrong_questions_menu = QMenu("错题集", menu)
            for file in json_files:
                if file != "questions.json":
                    action = wrong_questions_menu.addAction(file)
                    action.triggered.connect(lambda checked, f=file: self.load_question_file(f))
            menu.addMenu(wrong_questions_menu)
        
        # 显示菜单
        menu.exec_(self.file_combo.mapToGlobal(self.file_combo.rect().bottomLeft()))
    
    def load_question_file(self, file_path):
        """加载指定的题库文件"""
        if self.question_manager.load_questions(file_path):
            self.file_combo.setText(file_path)
            
            # 更新统计信息
            stats = self.question_manager.get_stats()
            stats_text = "题库统计：\n"
            for q_type, count in stats.items():
                stats_text += f"{q_type}: {count}题\n"
            
            # 查找并更新统计信息标签
            stats_label = None
            for i in range(self.layout().count()):
                widget = self.layout().itemAt(i).widget()
                if widget and isinstance(widget, QLabel) and "题库统计：" in widget.text():
                    stats_label = widget
                    break
            
            if stats_label:
                stats_label.setText(stats_text)
            else:
                # 如果没有统计信息标签，创建一个
                stats_label = QLabel(stats_text)
            stats_label.setFont(QFont("Microsoft YaHei UI, Arial", 10))
            self.layout().insertWidget(3, stats_label)
            
            # 更新题型数量设置
            self.update_type_count_inputs()
        else:
            QMessageBox.warning(self, "错误", f"无法加载题库文件：{file_path}")
    
    def update_type_count_inputs(self):
        """更新题型数量输入框"""
        # 移除现有的题型数量设置
        for layout in self.type_layouts:
            # 移除所有子控件
            while layout.count() > 0:
                widget = layout.itemAt(0).widget()
                if widget:
                    widget.setParent(None)
            self.main_layout.removeItem(layout)
        self.type_layouts.clear()
        self.type_count_inputs.clear()
        
        # 移除开始答题按钮
        self.start_button.setParent(None)
        
        # 移除DeepSeek解析按钮
        if hasattr(self, 'deepseek_button') and self.deepseek_button:
            self.deepseek_button.setParent(None)
        
        # 重新创建题型数量设置
        stats = self.question_manager.get_stats()
        for q_type in stats.keys():
            count_layout = QHBoxLayout()
            count_label = QLabel(f"{q_type}数量：")
            count_input = QLineEdit()
            count_input.setText(str(min(5, stats[q_type])))
            count_input.setMaxLength(3)
            count_input.setFixedWidth(50)
            count_layout.addWidget(count_label)
            count_layout.addWidget(count_input)
            self.main_layout.addLayout(count_layout)
            self.type_count_inputs[q_type] = count_input
            self.type_layouts.append(count_layout)
        
        # 重新添加开始答题按钮
        self.start_button = QPushButton("开始答题")
        self.start_button.clicked.connect(self.start_exam)
        self.main_layout.addWidget(self.start_button)
    
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
    

    
    def start_exam(self):
        """开始答题"""
        try:
            # 获取各题型数量
            type_counts = {}
            total_count = 0
            for q_type, input_field in self.type_count_inputs.items():
                count = int(input_field.text())
                max_count = self.question_manager.question_stats[q_type]
                if count < 0 or count > max_count:
                    QMessageBox.warning(self, "输入错误", f"{q_type}数量必须在0到{max_count}之间")
                    return
                type_counts[q_type] = count
                total_count += count
            
            if total_count <= 0:
                QMessageBox.warning(self, "输入错误", "总题数必须大于0")
                return
            
            # 抽取题目
            questions = self.question_manager.extract_questions_by_count(type_counts)
            if not questions:
                QMessageBox.warning(self, "抽取失败", "无法抽取题目，请检查配置")
                return
            
            # 打开答题界面
            self.exam_window = ExamWindow(self.question_manager)
            self.exam_window.show()
            self.hide()
            
        except ValueError:
            QMessageBox.warning(self, "输入错误", "请输入有效的数字")


class ExamWindow(QWidget):
    """答题主界面"""
    
    def __init__(self, question_manager):
        super().__init__()
        self.question_manager = question_manager
        self.setWindowTitle("答题界面")
        self.setGeometry(100, 100, 1000, 600)
        # 设置焦点策略，确保窗口能接收键盘事件
        self.setFocusPolicy(Qt.StrongFocus)
        # 安装事件过滤器，捕获所有键盘事件
        self.installEventFilter(self)
        # 当前字体大小，初始值为14
        self.current_font_size = 14
        self.init_ui()
    
    def init_ui(self):
        """初始化界面"""
        # 主布局，分为左侧答题区和右侧答题卡区
        self.main_layout = QHBoxLayout()
        
        # 左侧答题区
        self.left_widget = QWidget()
        self.left_layout = QVBoxLayout(self.left_widget)
        self.left_layout.setContentsMargins(10, 10, 10, 10)
        self.left_layout.setSpacing(10)
        
        # 进度条和进度文字 - 固定高度
        self.progress_layout = QHBoxLayout()
        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedHeight(20)  # 固定高度
        self.progress_label = QLabel("已答0题/共0题")
        self.progress_label.setFixedWidth(120)
        self.progress_label.setWordWrap(True)  # 允许自动换行
        self.progress_layout.addWidget(self.progress_bar)
        self.progress_layout.addWidget(self.progress_label)
        self.left_layout.addLayout(self.progress_layout)
        
        # 题目信息区域 - 自适应高度
        self.question_frame = QFrame()
        self.question_frame.setFrameShape(QFrame.StyledPanel)
        self.question_frame.setStyleSheet("border: 1px solid #eee; border-radius: 5px; padding: 10px;")
        self.question_layout = QVBoxLayout(self.question_frame)
        self.question_layout.setContentsMargins(0, 0, 0, 0)
        self.question_layout.setSpacing(5)
        
        self.title_label = QLabel("题目标题")
        self.title_label.setFont(QFont("Microsoft YaHei UI, Arial", 14, QFont.Bold))
        self.title_label.setWordWrap(True)  # 允许自动换行
        self.question_layout.addWidget(self.title_label)
        
        self.type_label = QLabel("题目类型")
        self.type_label.setFont(QFont("Microsoft YaHei UI, Arial", 10))
        self.question_layout.addWidget(self.type_label)
        
        self.content_label = QLabel("题干内容")
        self.content_label.setWordWrap(True)  # 允许自动换行
        self.content_label.setAlignment(Qt.AlignTop)  # 顶部对齐
        self.content_label.setMinimumHeight(50)  # 最小高度
        self.question_layout.addWidget(self.content_label, 1)  # 自适应高度
        
        self.left_layout.addWidget(self.question_frame, 2)  # 自适应高度
        
        # 选项区域 - 自适应高度
        self.options_scroll = QScrollArea()
        self.options_scroll.setWidgetResizable(True)
        self.options_scroll.setStyleSheet("border: 1px solid #eee; border-radius: 5px;")
        
        self.options_widget = QWidget()
        self.options_layout = QVBoxLayout(self.options_widget)
        self.options_layout.setContentsMargins(10, 10, 10, 10)
        self.options_layout.setSpacing(10)
        
        self.options_scroll.setWidget(self.options_widget)
        
        self.left_layout.addWidget(self.options_scroll, 3)  # 自适应高度
        
        # 按钮区域 - 固定高度
        button_layout = QHBoxLayout()
        button_layout.setSpacing(10)
        
        self.prev_button = QPushButton("上一题")
        self.prev_button.clicked.connect(self.prev_question)
        button_layout.addWidget(self.prev_button)
        
        self.next_button = QPushButton("下一题")
        self.next_button.clicked.connect(self.next_question)
        button_layout.addWidget(self.next_button)
        
        self.answer_button = QPushButton("查看答案")
        self.answer_button.clicked.connect(self.view_answer)
        button_layout.addWidget(self.answer_button)
        
        self.submit_button = QPushButton("提交")
        self.submit_button.clicked.connect(self.submit_exam)
        self.submit_button.setEnabled(False)
        button_layout.addWidget(self.submit_button)
        
        self.left_layout.addLayout(button_layout)
        
        # 右侧答题卡区
        self.right_widget = QWidget()
        self.right_layout = QVBoxLayout(self.right_widget)
        self.right_widget.setFixedWidth(220)
        self.right_widget.setStyleSheet("border: 1px solid #ccc; border-radius: 5px; padding: 10px;")
        
        # 答题卡标题
        answer_sheet_title = QLabel("字体大小设置")
        answer_sheet_title.setStyleSheet("font-weight: bold; font-size: 16px; margin-bottom: 10px;")
        self.right_layout.addWidget(answer_sheet_title)
        
        # 文字大小调整控件
        font_size_layout = QHBoxLayout()
        font_size_layout.setSpacing(5)
        
        # 减号按钮
        self.decrease_font_btn = QPushButton("-")
        self.decrease_font_btn.setFixedSize(30, 30)
        self.decrease_font_btn.clicked.connect(self.decrease_font_size)
        font_size_layout.addWidget(self.decrease_font_btn)
        
        # 字体大小显示
        self.font_size_label = QLabel(str(self.current_font_size))
        self.font_size_label.setAlignment(Qt.AlignCenter)
        self.font_size_label.setFixedWidth(40)
        font_size_layout.addWidget(self.font_size_label)
        
        # 加号按钮
        self.increase_font_btn = QPushButton("+")
        self.increase_font_btn.setFixedSize(30, 30)
        self.increase_font_btn.clicked.connect(self.increase_font_size)
        font_size_layout.addWidget(self.increase_font_btn)
        
        # 添加到右侧布局
        self.right_layout.addLayout(font_size_layout)
        
        # 添加左侧和右侧布局到主布局
        self.main_layout.addWidget(self.left_widget, 7)  # 左侧占70%
        self.main_layout.addWidget(self.right_widget, 3)  # 右侧占30%
        
        # 设置主布局
        self.setLayout(self.main_layout)
        
        # 初始化答题卡
        self._init_answer_sheet()
        
        # 加载第一题
        self._load_question(0)
    
    def _init_answer_sheet(self):
        """初始化答题卡 - 按分题型后的顺序显示连续序号"""
        # 清空现有内容，但保留前3个控件（答题卡标题和文字大小调整控件）
        # 先记录需要保留的控件数量
        preserve_count = 3  # 答题卡标题 + 文字大小调整控件
        for i in reversed(range(self.right_layout.count())):
            if i >= preserve_count:
                widget = self.right_layout.itemAt(i).widget()
                if widget is not None:
                    widget.setParent(None)
        
        # 获取当前已抽取的题目（分题型后的顺序）
        questions = self.question_manager.selected_questions
        
        # 定义题型顺序
        type_order = ['单选题', '多选题', '判断题', '填空题']
        
        # 创建题型分组，按分题型后的顺序计算序号
        current_number = 1
        
        for q_type in type_order:
            # 筛选该题型的题目
            type_questions = [q for q in questions if q['type'] == q_type]
            if not type_questions:
                continue
            
            # 题型标题
            type_label = QLabel(q_type)
            type_label.setStyleSheet("font-weight: bold; margin-top: 10px; margin-bottom: 5px;")
            self.right_layout.addWidget(type_label)
            
            # 题目卡片布局
            card_layout = QGridLayout()
            card_layout.setSpacing(5)
            
            # 创建题目卡片
            for i, q in enumerate(type_questions):
                # 找到该题在原始列表中的索引
                original_index = questions.index(q)
                
                # 创建卡片，显示分题型后的顺序序号（1开始连续递增）
                card = QPushButton(str(current_number))
                card.setFixedSize(40, 40)
                card.setStyleSheet(self._get_card_style(original_index))
                card.clicked.connect(lambda checked, idx=original_index: self._jump_to_question(idx))
                
                # 添加到网格布局
                row = i // 4
                col = i % 4
                card_layout.addWidget(card, row, col)
                
                # 序号递增
                current_number += 1
            
            # 添加题型卡片组
            card_widget = QWidget()
            card_widget.setLayout(card_layout)
            self.right_layout.addWidget(card_widget)
        
        # 确保布局占满空间
        self.right_layout.addStretch()
    
    def _get_card_style(self, index):
        """根据题目状态获取卡片样式"""
        # 检查是否已查看答案
        if self.question_manager.is_answer_viewed(index):
            return """QPushButton {
                background-color: #ffff99; /* 黄色 */
                border: 1px solid #ccc;
                border-radius: 8px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #ffff66;
            }"""
        
        # 检查是否已作答
        user_answer = self.question_manager.get_user_answer(index)
        if user_answer and user_answer != ['']:
            return """QPushButton {
                background-color: #99ccff; /* 蓝色 */
                border: 1px solid #ccc;
                border-radius: 8px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #66b3ff;
            }"""
        
        # 未作答
        return """QPushButton {
            background-color: #ffffff; /* 白色 */
            border: 1px solid #ccc;
            border-radius: 8px;
            font-weight: bold;
        }
        QPushButton:hover {
            background-color: #f0f0f0;
        }"""
    
    def _load_question(self, index):
        """加载指定索引的题目"""
        if index < 0 or index >= len(self.question_manager.selected_questions):
            return
        
        self.question_manager.current_question_index = index
        question = self.question_manager.get_current_question()
        
        # 更新进度
        total = len(self.question_manager.selected_questions)
        self.progress_bar.setValue(int((index + 1) / total * 100))
        self.progress_label.setText(f"已答{index + 1}题/共{total}题")
        
        # 更新题目信息并应用当前字体大小
        self.title_label.setText(question['title'])
        self.title_label.setStyleSheet(f"font-size: {self.current_font_size + 2}px; font-weight: bold;")
        
        self.type_label.setText(question['type'])
        self.type_label.setStyleSheet(f"font-size: {self.current_font_size - 2}px;")
        
        self.content_label.setText(question['content'])
        self.content_label.setStyleSheet(f"font-size: {self.current_font_size}px;")
        
        # 清除现有选项和解析标签
        for i in reversed(range(self.options_layout.count())):
            widget = self.options_layout.itemAt(i).widget()
            if widget is not None:
                widget.setParent(None)
        
        # 清除解析标签引用
        if hasattr(self, 'analysis_label'):
            delattr(self, 'analysis_label')
        
        # 根据题型生成选项控件
        self.option_widgets = []
        # 为单选题创建按钮组，确保同一时间只能选择一个选项
        self.button_group = None
        if question['type'] in ['单选题', '判断题']:
            self.button_group = QButtonGroup()
        
        if question['type'] == '填空题':
            # 准备存储多个输入框和答案标签
            self.fill_inputs = []
            self.correct_answer_labels = []
            
            # 获取正确答案数量，确定需要的输入框数量
            correct_answers = question['correct_answer']
            # 如果没有正确答案，默认1个输入框
            input_count = max(1, len(correct_answers))
            
            # 恢复用户之前的答案
            user_answers = self.question_manager.get_user_answer(index)
            if not user_answers:
                user_answers = [''] * input_count
            
            # 创建输入框
            for i in range(input_count):
                # 输入框
                fill_input = QLineEdit()
                fill_input.setPlaceholderText(f"请输入第{i+1}个空的答案")
                fill_input.setStyleSheet(f"font-size: {self.current_font_size}px;")
                if i < len(user_answers):
                    fill_input.setText(user_answers[i])
                
                # 用于显示正确答案的标签
                correct_label = QLabel()
                correct_label.setVisible(False)
                correct_label.setStyleSheet(f"font-size: {self.current_font_size}px;")
                
                # 实时保存答案，失去焦点时也保存
                fill_input.textChanged.connect(self._save_current_answer)
                fill_input.editingFinished.connect(self._save_current_answer)
                
                self.options_layout.addWidget(fill_input)
                self.options_layout.addWidget(correct_label)
                
                self.fill_inputs.append(fill_input)
                self.correct_answer_labels.append(correct_label)
                self.option_widgets.append(fill_input)
                self.option_widgets.append(correct_label)
            
            # 如果答案已查看，显示正确答案
            if self.question_manager.is_answer_viewed(index):
                self._show_correct_answer()
        else:
            # 选择题/判断题使用单选/复选框
            options = question['options']
            original_options = options.copy()
            correct_answers = question['correct_answer']
            
            # 打乱选项顺序（仅针对单选题和多选题）
            if question['type'] in ['单选题', '多选题']:
                import random
                random.shuffle(options)
            
            # 处理选项标识
            option_letters = ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'J']
            
            for i, option in enumerate(options):
                # 检查选项开头是否有ABCD等标识
                original_text = option
                processed_text = option
                
                # 替换选项开头的ABCD标识
                import re
                # 匹配选项开头的字母标识（A. 或A：等格式）
                match = re.match(r'^([A-Za-z])[.:、]\s*', processed_text)
                if match:
                    # 替换为新的字母标识
                    new_letter = option_letters[i]
                    processed_text = re.sub(r'^[A-Za-z][.:、]\s*', f'{new_letter}. ', processed_text)
                
                # 创建包含自动换行文本的选项
                from PyQt5.QtWidgets import QHBoxLayout
                
                # 创建选项容器
                option_container = QWidget()
                option_layout = QHBoxLayout(option_container)
                option_layout.setContentsMargins(0, 0, 0, 5)
                option_layout.setSpacing(5)
                option_layout.setAlignment(Qt.AlignTop)  # 容器向上对齐
                
                # 创建单选/复选框，并直接设置文本
                if question['type'] in ['单选题', '判断题']:
                    checkbox = QRadioButton(processed_text)
                    # 将单选按钮添加到按钮组中，确保同一时间只能选择一个选项
                    if self.button_group:
                        self.button_group.addButton(checkbox)
                else:  # 多选题
                    checkbox = QCheckBox(processed_text)
                
                # 设置复选框的样式和属性
                checkbox.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)  # 自适应宽度，高度根据内容调整
                checkbox.setStyleSheet(f"font-size: {self.current_font_size}px;")
                
                # 将复选框添加到布局中
                option_layout.addWidget(checkbox, 1)  # 复选框占主要空间
                
                # 恢复用户之前的选择
                user_answer = self.question_manager.get_user_answer(index)
                # 查找用户之前选择的选项在打乱后的列表中的位置
                for original_option in original_options:
                    if original_option in user_answer:
                        # 找到原始选项在打乱后的列表中的位置
                        if original_option == option:
                            checkbox.setChecked(True)
                            break
                
                # 如果答案已查看，高亮显示
                if self.question_manager.is_answer_viewed(index):
                    # 直接检查当前选项是否为正确答案
                    is_correct = option in correct_answers
                    if is_correct:
                        checkbox.setStyleSheet(f"color: green; font-size: {self.current_font_size}px;")
                    else:
                        checkbox.setStyleSheet(f"color: red; font-size: {self.current_font_size}px;")
                
                # 实时保存答案
                def save_answer(checked):
                    self._save_current_answer()
                checkbox.toggled.connect(save_answer)
                
                self.options_layout.addWidget(option_container)
                # 保存选项相关组件，用于后续处理
                self.option_widgets.append(checkbox)
                self.option_widgets.append(option_container)
        
        # 设置选项容器布局的对齐方式为向上对齐
        self.options_layout.setAlignment(Qt.AlignTop)
        
        # 启用/禁用导航按钮
        self.prev_button.setEnabled(index > 0)
        self.next_button.setEnabled(index < total - 1)
        
        # 检查是否可以提交
        self._check_submit_enabled()
        
        # 确保所有控件都应用了当前的字体大小
        self.update_all_fonts()
    
    def _save_current_answer(self):
        """保存当前题目的答案"""
        index = self.question_manager.current_question_index
        question = self.question_manager.get_current_question()
        
        if question['type'] == '填空题':
            # 填空题
            user_answers = [input.text().strip() for input in self.fill_inputs]
            self.question_manager.save_user_answer(index, user_answers)
        else:
            # 选择题/判断题
            user_answer = []
            original_options = question['options']
            
            # 遍历所有选项，查找选中的选项
            for i, widget in enumerate(self.option_widgets):
                # 只处理单选按钮和复选框控件
                if isinstance(widget, (QRadioButton, QCheckBox)):
                    # 检查控件是否被选中
                    if widget.isChecked():
                        # 直接从复选框获取文本
                        option_text = widget.text()
                        
                        # 查找当前选项对应的原始选项
                        # 1. 提取选项内容（去除ABCD标识）
                        import re
                        current_content = re.sub(r'^[A-Za-z][.:、]\s*', '', option_text)
                        
                        # 遍历原始选项，提取内容进行匹配
                        for original_option in original_options:
                            original_content = re.sub(r'^[A-Za-z][.:、]\s*', '', original_option)
                            if current_content.strip() == original_content.strip():
                                user_answer.append(original_option)
                                break
            
            self.question_manager.save_user_answer(index, user_answer)
        
        # 检查是否可以提交
        self._check_submit_enabled()
        
        # 优化：只更新当前题目的答题卡状态，而不是重新初始化整个答题卡
        self._update_answer_sheet()
    
    def _update_answer_sheet(self):
        """更新答题卡状态，只更新当前题目的状态"""
        # 获取当前题目索引
        current_index = self.question_manager.current_question_index
        
        # 遍历右侧布局，找到对应的答题卡卡片并更新样式
        for i in range(self.right_layout.count()):
            widget = self.right_layout.itemAt(i).widget()
            if widget is not None:
                # 检查widget是否包含布局
                layout = widget.layout()
                if isinstance(layout, QGridLayout):
                    # 遍历网格布局中的所有卡片
                    for row in range(layout.rowCount()):
                        for col in range(layout.columnCount()):
                            item = layout.itemAtPosition(row, col)
                            if item is not None:
                                card = item.widget()
                                if isinstance(card, QPushButton):
                                    # 获取卡片对应的题目索引
                                    try:
                                        card_index = int(card.text()) - 1
                                        if card_index == current_index:
                                            # 更新卡片样式
                                            card.setStyleSheet(self._get_card_style(card_index))
                                    except ValueError:
                                        continue
                                elif isinstance(card, QWidget):
                                    # 递归检查子widget
                                    sub_layout = card.layout()
                                    if isinstance(sub_layout, QGridLayout):
                                        for sub_row in range(sub_layout.rowCount()):
                                            for sub_col in range(sub_layout.columnCount()):
                                                sub_item = sub_layout.itemAtPosition(sub_row, sub_col)
                                                if sub_item is not None:
                                                    sub_card = sub_item.widget()
                                                    if isinstance(sub_card, QPushButton):
                                                        try:
                                                            card_index = int(sub_card.text()) - 1
                                                            if card_index == current_index:
                                                                # 更新卡片样式
                                                                sub_card.setStyleSheet(self._get_card_style(card_index))
                                                        except ValueError:
                                                            continue
    
    def _save_answer(self, option, checked):
        """保存选择题用户答案"""
        # 这个方法现在由_save_current_answer替代
        pass
    
    def _save_multi_fill_answer(self, index, text):
        """保存多填空题用户答案"""
        # 这个方法现在由_save_current_answer替代
        pass
    
    def _highlight_answer(self, widget, option, correct_answer):
        """高亮显示答案"""
        palette = widget.palette()
        if option in correct_answer:
            palette.setColor(QPalette.WindowText, QColor(0, 128, 0))  # 绿色
        else:
            palette.setColor(QPalette.WindowText, QColor(255, 0, 0))  # 红色
        widget.setPalette(palette)
    
    def _show_correct_answer(self):
        """显示填空题的正确答案"""
        index = self.question_manager.current_question_index
        question = self.question_manager.get_current_question()
        correct_answers = question['correct_answer']
        user_answers = self.question_manager.get_user_answer(index)
        
        if not user_answers:
            user_answers = [''] * len(correct_answers)
        
        # 遍历所有输入框和答案
        for i in range(len(self.fill_inputs)):
            fill_input = self.fill_inputs[i]
            correct_label = self.correct_answer_labels[i]
            
            if i < len(correct_answers) and correct_answers[i]:
                correct_text = correct_answers[i]
                user_text = user_answers[i] if i < len(user_answers) else ""
                
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
        
        # 显示解析
        if hasattr(self, 'analysis_label'):
            self.analysis_label.setParent(None)
        
        analysis_label = QLabel()
        if 'analysis' in question and question['analysis']:
            analysis_label.setText(f"解析: {question['analysis']}")
            analysis_label.setStyleSheet("color: green; font-weight: bold;")
        else:
            analysis_label.setText("(本题暂无解析)")
            analysis_label.setStyleSheet("color: orange;")
        
        analysis_label.setVisible(True)
        analysis_label.setWordWrap(True)
        analysis_label.setStyleSheet(f"color: green; font-weight: bold; font-size: {self.current_font_size}px;")
        self.options_layout.addWidget(analysis_label)
        self.analysis_label = analysis_label
    
    def _check_submit_enabled(self):
        """检查是否可以提交"""
        questions = self.question_manager.selected_questions
        total = len(questions)
        answered = 0
        
        for i in range(total):
            user_answer = self.question_manager.get_user_answer(i)
            if user_answer and user_answer != ['']:
                answered += 1
        
        # 如果所有题目都已作答，启用提交按钮
        self.submit_button.setEnabled(answered == total)
    
    def view_answer(self):
        """查看答案"""
        index = self.question_manager.current_question_index
        question = self.question_manager.get_current_question()
        correct_answer = question['correct_answer']
        user_answer = self.question_manager.get_user_answer(index)
        
        # 先标记答案已查看
        self.question_manager.mark_answer_viewed(index)
        
        if question['type'] == '填空题':
            self._show_correct_answer()
        else:
            # 选择题/判断题直接高亮显示答案，不重新加载题目
            # 遍历选项控件，找到所有单选/复选框
            for widget in self.option_widgets:
                if isinstance(widget, (QRadioButton, QCheckBox)):
                    # 提取选项文本
                    current_text = widget.text()
                    # 找到当前选项对应的原始选项
                    for option in question['options']:
                        # 提取选项内容进行匹配
                        import re
                        current_content = re.sub(r'^[A-Za-z][.:、]\s*', '', current_text)
                        option_content = re.sub(r'^[A-Za-z][.:、]\s*', '', option)
                        if current_content.strip() == option_content.strip():
                            # 检查是否为正确答案
                            is_correct = option in correct_answer
                            if is_correct:
                                widget.setStyleSheet(f"color: green; font-size: {self.current_font_size}px;")
                            else:
                                widget.setStyleSheet(f"color: red; font-size: {self.current_font_size}px;")
                            break
            
            # 显示解析
            if hasattr(self, 'analysis_label'):
                self.analysis_label.setParent(None)
            
            analysis_label = QLabel()
            if 'analysis' in question and question['analysis']:
                analysis_label.setText(f"解析: {question['analysis']}")
                analysis_label.setStyleSheet(f"color: green; font-weight: bold; font-size: {self.current_font_size}px;")
            else:
                analysis_label.setText("(本题暂无解析)")
                analysis_label.setStyleSheet(f"color: orange; font-size: {self.current_font_size}px;")
            
            analysis_label.setVisible(True)
            analysis_label.setWordWrap(True)
            self.options_layout.addWidget(analysis_label)
            self.analysis_label = analysis_label
        
        # 只更新当前题目的答题卡状态，不重新初始化整个答题卡
        self._update_answer_sheet()
    
    def increase_font_size(self):
        """增加字体大小"""
        if self.current_font_size < 96:  # 限制最大字体大小
            self.current_font_size += 1
            self.font_size_label.setText(str(self.current_font_size))
            self.update_all_fonts()
    
    def decrease_font_size(self):
        """减小字体大小"""
        if self.current_font_size > 8:  # 限制最小字体大小
            self.current_font_size -= 1
            self.font_size_label.setText(str(self.current_font_size))
            self.update_all_fonts()
    
    def update_all_fonts(self):
        """更新所有控件的字体大小"""
        # 更新题目相关控件
        self.title_label.setStyleSheet(f"font-size: {self.current_font_size + 2}px; font-weight: bold;")
        self.type_label.setStyleSheet(f"font-size: {self.current_font_size - 2}px;")
        self.content_label.setStyleSheet(f"font-size: {self.current_font_size}px;")
        
        # 更新选项控件
        for widget in self.option_widgets:
            if isinstance(widget, (QRadioButton, QCheckBox)):
                # 保持原有的颜色样式，只更新字体大小
                current_style = widget.styleSheet()
                if "color" in current_style:
                    # 提取颜色样式
                    import re
                    color_match = re.search(r"color: ([^;]+);", current_style)
                    if color_match:
                        color = color_match.group(1)
                        widget.setStyleSheet(f"color: {color}; font-size: {self.current_font_size}px;")
                else:
                    widget.setStyleSheet(f"font-size: {self.current_font_size}px;")
            elif isinstance(widget, QLineEdit):
                # 更新填空题输入框的字体大小
                widget.setStyleSheet(f"font-size: {self.current_font_size}px;")
        
        # 更新所有按钮的字体大小
        for button in [self.prev_button, self.next_button, self.answer_button, self.submit_button]:
            button.setStyleSheet(f"font-size: {self.current_font_size}px;")
    
    def prev_question(self):
        """上一题"""
        index = self.question_manager.current_question_index
        if index > 0:
            # 保存当前答案
            self._save_current_answer()
            self._load_question(index - 1)
    
    def next_question(self):
        """下一题"""
        index = self.question_manager.current_question_index
        if index < len(self.question_manager.selected_questions) - 1:
            # 保存当前答案
            self._save_current_answer()
            self._load_question(index + 1)
    
    def _jump_to_question(self, index):
        """跳转到指定题目"""
        # 保存当前答案
        self._save_current_answer()
        self._load_question(index)
    
    def submit_exam(self):
        """提交考试，计算成绩"""
        # 保存当前答案
        self._save_current_answer()
        
        # 计算成绩
        total_questions = len(self.question_manager.selected_questions)
        correct_count = 0
        
        for i in range(total_questions):
            question = self.question_manager.selected_questions[i]
            user_answer = self.question_manager.get_user_answer(i)
            correct_answer = question['correct_answer']
            
            # 比较答案
            if question['type'] in ['单选题', '判断题']:
                # 单选题和判断题
                if set(user_answer) == set(correct_answer):
                    correct_count += 1
            elif question['type'] == '多选题':
                # 多选题
                if set(user_answer) == set(correct_answer):
                    correct_count += 1
            elif question['type'] == '填空题':
                # 填空题
                if len(user_answer) == len(correct_answer):
                    is_all_correct = True
                    for ua, ca in zip(user_answer, correct_answer):
                        if ua.strip() != ca.strip():
                            is_all_correct = False
                            break
                    if is_all_correct:
                        correct_count += 1
        
        # 计算得分（满分100）
        score = round((correct_count / total_questions) * 100, 1) if total_questions > 0 else 0
        
        # 创建自定义消息框
        msg_box = QMessageBox()
        msg_box.setWindowTitle("考试成绩")
        msg_box.setText(f"本次考试成绩：{score}分\n正确题目：{correct_count}/{total_questions}")
        
        # 添加导出错题按钮
        export_button = msg_box.addButton("导出错题", QMessageBox.ActionRole)
        msg_box.addButton(QMessageBox.Ok)
        
        # 显示消息框
        msg_box.exec_()
        
        # 检查用户是否点击了导出错题按钮
        if msg_box.clickedButton() == export_button:
            # 获取保存路径
            filename = f"错题集_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            file_path, _ = QFileDialog.getSaveFileName(
                self,
                "保存错题集",
                filename,
                "JSON Files (*.json)"
            )
            
            if file_path:
                success, message = self.question_manager.export_wrong_questions(file_path)
                if success:
                    QMessageBox.information(self, "成功", message)
                else:
                    QMessageBox.warning(self, "失败", message)
    
    def eventFilter(self, obj, event):
        """事件过滤器，捕获所有键盘事件"""
        if event.type() == QEvent.KeyPress:
            key = event.key()
            
            # 方向键处理：上一题/下一题
            if key in [Qt.Key_Left, Qt.Key_Up, Qt.Key_Right, Qt.Key_Down]:
                # 优先处理方向键，用于题目导航
                self.keyPressEvent(event)
                return True  # 阻止事件继续传播
        
        return super(ExamWindow, self).eventFilter(obj, event)
    
    def keyPressEvent(self, event):
        """处理键盘事件"""
        key = event.key()
        
        # 方向键处理：上一题/下一题
        if key in [Qt.Key_Left, Qt.Key_Up]:
            # 左键和上键对应上一题
            self.prev_question()
            # 确保窗口保持焦点
            self.setFocus()
        elif key in [Qt.Key_Right, Qt.Key_Down]:
            # 右键和下键对应下一题
            self.next_question()
            # 确保窗口保持焦点
            self.setFocus()
        
        # 数字键处理：选择选项
        elif Qt.Key_1 <= key <= Qt.Key_9:
            # 将数字键转换为索引（1-9对应0-8）
            option_index = key - Qt.Key_1
            
            # 获取当前题目
            question = self.question_manager.get_current_question()
            
            # 只处理选择题和判断题
            if question['type'] in ['单选题', '多选题', '判断题']:
                # 遍历选项控件，找到对应的选项
                checkbox_count = 0
                for widget in self.option_widgets:
                    if isinstance(widget, (QRadioButton, QCheckBox)):
                        if checkbox_count == option_index:
                            # 针对单选题和多选题分别处理
                            if question['type'] in ['单选题', '判断题']:
                                # 单选题和判断题直接选中，不需要切换状态
                                widget.setChecked(True)
                            else:  # 多选题
                                # 多选题切换选中状态
                                widget.setChecked(not widget.isChecked())
                            # 手动触发toggled信号
                            widget.toggled.emit(widget.isChecked())
                            break
                        checkbox_count += 1
            # 确保窗口保持焦点
            self.setFocus()


class MainApp(QMainWindow):
    """主应用类"""
    
    def __init__(self):
        super().__init__()
        self.question_manager = QuestionManager()
        self.init_ui()
    
    def init_ui(self):
        """初始化主界面"""
        self.setWindowTitle("答题系统")
        self.setGeometry(100, 100, 800, 600)
        
        # 显示配置界面
        self.config_window = ConfigWindow(self.question_manager)
        self.config_window.show()
        self.close()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    # 设置全局默认字体为Microsoft YaHei UI，添加后备方案
    default_font = QFont()
    default_font.setFamily("Microsoft YaHei UI, Arial, Helvetica, sans-serif")
    app.setFont(default_font)
    main_app = MainApp()
    sys.exit(app.exec_())