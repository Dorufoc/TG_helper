#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import json
import os
import requests
from typing import List, Dict, Optional
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QLineEdit, QProgressBar, QTextEdit,
    QMessageBox, QFileDialog, QGroupBox, QScrollArea, QGridLayout
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtGui import QFont, QPalette, QColor, QTextCursor


class DeepSeekWorker(QThread):
    """后台工作线程，负责调用DeepSeek API并更新解析"""
    
    progress_signal = pyqtSignal(int, str)  # 进度值，日志消息
    finished_signal = pyqtSignal(bool, str)  # 是否成功，最终消息
    
    def __init__(self, api_key: str, questions: List[Dict], file_path: str):
        super().__init__()
        self.api_key = api_key
        self.questions = questions
        self.file_path = file_path
        self.running = True
        
    def run(self):
        """主工作逻辑"""
        try:
            total = len(self.questions)
            for i, question in enumerate(self.questions):
                if not self.running:
                    self.progress_signal.emit(0, "用户取消操作")
                    break
                    
                # 跳过已有解析的题目
                if question.get('analysis', '').strip():
                    self.progress_signal.emit(int((i + 1) / total * 100), 
                                            f"跳过第 {i+1} 题（已有解析）")
                    continue
                    
                # 构建用户消息
                user_message = self._build_user_message(question)
                
                # 调用DeepSeek API
                self.progress_signal.emit(int((i + 1) / total * 100), 
                                        f"正在解析第 {i+1}/{total} 题...")
                analysis = self._call_deepseek_api(user_message)
                
                if analysis:
                    question['analysis'] = analysis
                    self.progress_signal.emit(int((i + 1) / total * 100), 
                                            f"第 {i+1} 题解析成功")
                else:
                    question['analysis'] = "解析失败"
                    self.progress_signal.emit(int((i + 1) / total * 100), 
                                            f"第 {i+1} 题解析失败")
                
                # 每解析5题保存一次
                if (i + 1) % 5 == 0 or i + 1 == total:
                    self._save_questions()
            
            if self.running:
                self._save_questions()  # 最终保存
                self.finished_signal.emit(True, f"解析完成！共处理 {total} 道题目")
            else:
                self.finished_signal.emit(False, "解析被用户取消")
                
        except Exception as e:
            self.finished_signal.emit(False, f"解析过程中出现错误：{str(e)}")
    
    def _build_user_message(self, question: Dict) -> str:
        """构建用户消息"""
        content = question.get('content', '')
        options = question.get('options', [])
        correct_answer = question.get('correct_answer', [])
        
        message = f"题目：{content}\n"
        
        if options:
            message += "选项：\n"
            for opt in options:
                message += f"  {opt}\n"
        
        if correct_answer:
            if len(correct_answer) == 1:
                message += f"正确答案：{correct_answer[0]}"
            else:
                message += "正确答案：\n"
                for ans in correct_answer:
                    message += f"  {ans}\n"
        
        return message.strip()
    
    def _call_deepseek_api(self, user_message: str) -> Optional[str]:
        """调用DeepSeek API获取解析"""
        url = "https://api.deepseek.com/v1/chat/completions"
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        data = {
            "model": "deepseek-chat",
            "messages": [
                {
                    "role": "system",
                    "content": "你是一个计算机科学与技术专业的老师，现在有一名同学想要你简单且准确的解释这道题的答案，用简单的描述来直接回答问题，如果是选择题，告诉为什么其他选项错误目标选项正确输出纯文本，不要markdown格式！"
                },
                {
                    "role": "user",
                    "content": user_message
                }
            ],
            "temperature": 0.7,
            "max_tokens": 500
        }
        
        try:
            response = requests.post(url, headers=headers, json=data, timeout=30)
            response.raise_for_status()
            
            result = response.json()
            analysis = result.get('choices', [{}])[0].get('message', {}).get('content', '')
            
            # 清理可能的markdown格式
            analysis = analysis.replace('**', '').replace('`', '').strip()
            return analysis
            
        except requests.exceptions.RequestException as e:
            print(f"API调用失败: {e}")
            return None
        except (KeyError, IndexError) as e:
            print(f"解析API响应失败: {e}")
            return None
    
    def _save_questions(self):
        """保存题目到文件"""
        try:
            with open(self.file_path, 'w', encoding='utf-8') as f:
                json.dump(self.questions, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"保存文件失败: {e}")
    
    def stop(self):
        """停止工作线程"""
        self.running = False


class DeepSeekParserWindow(QWidget):
    """DeepSeek解析窗口"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("DeepSeek题目解析")
        self.setGeometry(100, 100, 800, 600)
        
        self.api_key = ""
        self.questions = []
        self.file_path = "questions.json"
        self.worker = None
        
        self.init_ui()
        self.load_questions()
    
    def init_ui(self):
        """初始化界面"""
        self.main_layout = QVBoxLayout()
        
        # 标题
        title_label = QLabel("DeepSeek题目解析")
        title_label.setFont(QFont("Microsoft YaHei UI, Arial", 18, QFont.Bold))
        title_label.setAlignment(Qt.AlignCenter)
        self.main_layout.addWidget(title_label)
        
        # API密钥输入区域
        api_group = QGroupBox("DeepSeek API配置")
        api_layout = QVBoxLayout()
        
        key_layout = QHBoxLayout()
        key_label = QLabel("API密钥：")
        self.api_key_input = QLineEdit()
        self.api_key_input.setEchoMode(QLineEdit.Password)
        self.api_key_input.setPlaceholderText("请输入您的DeepSeek API密钥")
        key_layout.addWidget(key_label)
        key_layout.addWidget(self.api_key_input)
        api_layout.addLayout(key_layout)
        
        api_group.setLayout(api_layout)
        self.main_layout.addWidget(api_group)
        
        # 文件选择区域
        file_group = QGroupBox("题库文件")
        file_layout = QVBoxLayout()
        
        path_layout = QHBoxLayout()
        file_label = QLabel("文件路径：")
        self.file_path_label = QLabel(self.file_path)
        self.file_path_label.setWordWrap(True)
        self.select_file_btn = QPushButton("选择文件")
        self.select_file_btn.clicked.connect(self.select_file)
        
        path_layout.addWidget(file_label)
        path_layout.addWidget(self.file_path_label, 1)
        path_layout.addWidget(self.select_file_btn)
        file_layout.addLayout(path_layout)
        
        # 题库统计
        self.stats_label = QLabel("加载题库后显示统计信息")
        self.stats_label.setFont(QFont("Microsoft YaHei UI, Arial", 10))
        file_layout.addWidget(self.stats_label)
        
        file_group.setLayout(file_layout)
        self.main_layout.addWidget(file_group)
        
        # 进度条
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        self.main_layout.addWidget(self.progress_bar)
        
        # 日志显示区域
        log_group = QGroupBox("解析日志")
        log_layout = QVBoxLayout()
        
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMaximumHeight(200)
        log_layout.addWidget(self.log_text)
        
        log_group.setLayout(log_layout)
        self.main_layout.addWidget(log_group)
        
        # 按钮区域
        button_layout = QHBoxLayout()
        
        self.start_btn = QPushButton("开始解析")
        self.start_btn.clicked.connect(self.start_parsing)
        
        self.stop_btn = QPushButton("停止解析")
        self.stop_btn.clicked.connect(self.stop_parsing)
        self.stop_btn.setEnabled(False)
        
        self.close_btn = QPushButton("关闭窗口")
        self.close_btn.clicked.connect(self.close)
        
        button_layout.addWidget(self.start_btn)
        button_layout.addWidget(self.stop_btn)
        button_layout.addWidget(self.close_btn)
        button_layout.addStretch()
        
        self.main_layout.addLayout(button_layout)
        
        # 设置布局
        self.setLayout(self.main_layout)
        
        # 更新统计信息
        self.update_stats()
    
    def select_file(self):
        """选择题库文件"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择题库文件", "", "JSON文件 (*.json);;所有文件 (*.*)"
        )
        
        if file_path:
            self.file_path = file_path
            self.file_path_label.setText(file_path)
            self.load_questions()
    
    def load_questions(self):
        """加载题库文件"""
        try:
            with open(self.file_path, 'r', encoding='utf-8') as f:
                self.questions = json.load(f)
            self.update_stats()
            self.log_message(f"成功加载题库：{self.file_path}")
        except Exception as e:
            self.log_message(f"加载题库失败：{str(e)}")
            self.questions = []
    
    def update_stats(self):
        """更新统计信息"""
        if not self.questions:
            self.stats_label.setText("题库为空或加载失败")
            return
        
        total = len(self.questions)
        with_analysis = sum(1 for q in self.questions if q.get('analysis', '').strip())
        without_analysis = total - with_analysis
        
        stats_text = f"""
        题库统计：
        总题数：{total}
        已有解析：{with_analysis}
        待解析：{without_analysis}
        """
        self.stats_label.setText(stats_text)
    
    def log_message(self, message: str):
        """添加日志消息"""
        self.log_text.append(f"[{self._get_current_time()}] {message}")
        # 滚动到底部
        cursor = self.log_text.textCursor()
        cursor.movePosition(QTextCursor.End)
        self.log_text.setTextCursor(cursor)
    
    def _get_current_time(self):
        """获取当前时间字符串"""
        import datetime
        return datetime.datetime.now().strftime("%H:%M:%S")
    
    def start_parsing(self):
        """开始解析"""
        # 获取API密钥
        self.api_key = self.api_key_input.text().strip()
        if not self.api_key:
            QMessageBox.warning(self, "警告", "请输入DeepSeek API密钥")
            return
        
        if not self.questions:
            QMessageBox.warning(self, "警告", "题库为空，请先加载题库文件")
            return
        
        # 检查网络连接
        try:
            requests.head("https://api.deepseek.com", timeout=5)
        except:
            reply = QMessageBox.question(self, "网络连接", 
                                        "无法连接到DeepSeek API，是否继续？",
                                        QMessageBox.Yes | QMessageBox.No)
            if reply == QMessageBox.No:
                return
        
        # 禁用开始按钮，启用停止按钮
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.api_key_input.setEnabled(False)
        self.select_file_btn.setEnabled(False)
        
        # 清空日志
        self.log_text.clear()
        self.log_message("开始解析题目...")
        
        # 创建工作线程
        self.worker = DeepSeekWorker(self.api_key, self.questions, self.file_path)
        self.worker.progress_signal.connect(self.update_progress)
        self.worker.finished_signal.connect(self.parsing_finished)
        self.worker.start()
    
    def stop_parsing(self):
        """停止解析"""
        if self.worker and self.worker.isRunning():
            self.worker.stop()
            self.log_message("正在停止解析...")
            self.stop_btn.setEnabled(False)
    
    def update_progress(self, value: int, message: str):
        """更新进度"""
        self.progress_bar.setValue(value)
        self.log_message(message)
    
    def parsing_finished(self, success: bool, message: str):
        """解析完成"""
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.api_key_input.setEnabled(True)
        self.select_file_btn.setEnabled(True)
        
        self.log_message(message)
        if success:
            self.progress_bar.setValue(100)
            QMessageBox.information(self, "完成", message)
        else:
            QMessageBox.warning(self, "完成", message)
        
        # 更新统计信息
        self.update_stats()
    
    def closeEvent(self, event):
        """窗口关闭事件"""
        if self.worker and self.worker.isRunning():
            reply = QMessageBox.question(self, "确认关闭", 
                                        "解析仍在进行中，是否强制关闭？",
                                        QMessageBox.Yes | QMessageBox.No)
            if reply == QMessageBox.No:
                event.ignore()
                return
            
            self.worker.stop()
            self.worker.wait(2000)  # 等待2秒
        
        event.accept()


def main():
    """主函数，用于独立运行窗口"""
    app = QApplication(sys.argv)
    window = DeepSeekParserWindow()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()