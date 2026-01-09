import os
import re
import json
from bs4 import BeautifulSoup


def parse_html_to_json(file_path):
    """
    解析HTML文件，提取题目信息并转换为JSON格式
    """
    with open(file_path, 'r', encoding='utf-8') as f:
        html_content = f.read()
    
    soup = BeautifulSoup(html_content, 'html.parser')
    
    # 获取标题
    title = soup.find('title').text if soup.find('title') else '未知标题'
    
    # 提取所有题目
    questions = []
    
    # 找到所有题目容器
    subject_elements = soup.find_all(class_='subject')
    
    for i, subject in enumerate(subject_elements):
        question = {
            'id': i + 1,
            'title': title,
            'type': '',
            'content': '',
            'options': [],
            'correct_answer': [],
            'analysis': ''
        }
        
        # 提取题目内容
        content_div = subject.find(class_='subject-body')
        if content_div:
            question['content'] = content_div.text.strip()
        
        # 找到题目对应的选项容器
        subject_parent = subject.parent
        option_container = subject_parent.find(class_='option')
        
        # 检查是否为填空题（通过textarea识别）
        textarea = None
        # 查找当前题目所在的li元素
        li_element = subject.find_parent('li')
        if li_element:
            # 在li元素中查找所有textarea元素
            textareas = li_element.find_all('textarea')
            if textareas:
                textarea = textareas[0]
        
        # 如果在li中没有找到textarea，尝试其他方式
        if not textarea:
            # 查找当前题目对应的option容器
            option_div = subject.find_next_sibling('div', class_='option')
            if not option_div:
                option_div = subject_parent.find_next_sibling('div', class_='option')
            
            if option_div:
                textareas = option_div.find_all('textarea')
                if textareas:
                    textarea = textareas[0]
        
        if textarea:
            question['type'] = '填空题'
            # 填空题的正确答案在textarea的内容中
            value = textarea.text.strip() or textarea.string.strip() if textarea.string else ''
            # 检查是否有多个答案（用分号或逗号分隔）
            if value:
                # 支持多个答案，用分号或逗号分隔
                answers = re.split(r'[,;，；]', value)
                # 去除每个答案的首尾空格
                answers = [answer.strip() for answer in answers if answer.strip()]
                question['correct_answer'] = answers
            questions.append(question)
            continue
        
        # 检查是否为判断题（带选项的判断题）
        radio_group = subject_parent.find(class_='ant-radio-group')
        if radio_group:
            question['type'] = '判断题'
            # 找到所有选项
            radio_labels = radio_group.find_all(class_='ant-radio-wrapper')
            for label in radio_labels:
                option_text = label.find('span', class_='ant-radio-label').text.strip()
                # 检查是否为正确答案
                is_checked = 'ant-radio-wrapper-checked' in label.get('class', [])
                question['options'].append(option_text)
                if is_checked:
                    question['correct_answer'].append(option_text)
            questions.append(question)
            continue
        
        # 检查是否为选择题（单选或多选）
        if option_container:
            # 提取所有选项
            options = option_container.find_all('a', class_='flex-container')
            # 检查是单选还是多选
            has_radio = option_container.find('input', type='radio') is not None
            has_checkbox = option_container.find('input', type='checkbox') is not None
            
            for opt in options:
                label = opt.find(class_='checkTitle').text.strip()  # 选项标识（A、B、C、D）
                content = opt.find(class_='subject-body').text.strip()  # 选项内容
                question['options'].append(f"{label} {content}")
                
                # 检查是否为正确答案
                is_checked = opt.find('input', checked='') is not None
                if is_checked:
                    question['correct_answer'].append(f"{label} {content}")
            
            # 确定题型
            if has_checkbox:
                question['type'] = '多选题'
            elif has_radio:
                question['type'] = '单选题'
            
            questions.append(question)
        else:
            # 没有选项的题目，可能是其他类型
            questions.append(question)
    
    return questions


def process_all_html_files():
    """
    处理html文件夹中的所有HTML文件
    """
    html_dir = 'html'
    output_file = 'questions.json'
    
    all_questions = []
    
    # 遍历所有HTML文件
    for filename in os.listdir(html_dir):
        if filename.endswith('.html'):
            file_path = os.path.join(html_dir, filename)
            questions = parse_html_to_json(file_path)
            all_questions.extend(questions)
    
    # 保存为JSON文件
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(all_questions, f, ensure_ascii=False, indent=2)
    
    print(f"已成功提取{len(all_questions)}道题目，保存到{output_file}")


if __name__ == "__main__":
    process_all_html_files()
