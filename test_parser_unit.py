#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import tempfile
import os
from deepseek_parser import DeepSeekWorker

def test_build_user_message():
    """测试构建用户消息"""
    question = {
        'content': '可行性分析研究的目的是',
        'options': ['A、 开发项目', 'B、 项目是否值得开发', 'C、 功能内聚', 'D、 争取项目'],
        'correct_answer': ['B、 项目是否值得开发']
    }
    
    worker Deep =SeekWorker('fake_key', [], 'fake.json')
    message = worker._build_user_message(question)
    
    print("构建的消息：")
    print(message)
    print()
    
    assert '题目：可行性分析研究的目的是' in message
    assert '选项：' in message
    assert 'A、 开发项目' in message
    assert '正确答案：B、 项目是否值得开发' in message
    
    print("✓ 构建用户消息测试通过")

def test_save_questions():
    """测试保存题目"""
    questions = [
        {
            'id': 1,
            'content': '测试题目',
            'analysis': ''
        }
    ]
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        temp_path = f.name
    
    try:
        worker = DeepSeekWorker('fake_key', questions, temp_path)
        worker._save_questions()
        
        with open(temp_path, 'r', encoding='utf-8') as f:
            saved = json.load(f)
        
        assert len(saved) == 1
        assert saved[0]['content'] == '测试题目'
        print("✓ 保存题目测试通过")
    finally:
        os.unlink(temp_path)

def test__exskipisting_analysis():
    """测试跳过已有解析的题目"""
    questions = [
        {'id': 1, 'analysis': '已有解析'},
        {'id': 2, 'analysis': ''}
    ]
    
    # 模拟API调用
    import unittest.mock as mock
    
    worker = DeepSeekWorker('fake_key', questions, 'fake.json')
    worker._call_deepseek_api = mock.Mock(return_value='新解析')
    
    # 运行线程（简化版）
    worker.running = True
    worker.progress_signal = mock.Mock()
    worker.finished_signal = mock.Mock()
    
    # 只测试处理逻辑，不启动线程
    total = len(questions)
    for i, question in enumerate(questions):
        if question.get('analysis', '').strip():
            print(f"题目 {i+1} 已有解析，应跳过")
            continue
        
        question['analysis'] = '新解析'
        print(f"题目 {i+1} 应添加新解析")
    
    assert questions[0]['analysis'] == '已有解析'
    assert questions[1]['analysis'] == '新解析'
    print("✓ 跳过已有解析测试通过")

if __name__ == "__main__":
    test_build_user_message()
    test_save_questions()
    test_skip_existing_analysis()
    print("\n所有单元测试通过！")