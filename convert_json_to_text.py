import json

# 读取JSON文件
input_file = input("请输入JSON文件路径: ")
with open(input_file, 'r', encoding='utf-8') as f:
    questions = json.load(f)

# 转换为纯文本格式
output_lines = []
for idx, question in enumerate(questions, 1):
    # 题目行：序号.【题型】题目内容
    question_line = f"{idx}.【{question['type']}】{question['content']}"
    
    # 选项行：各个选项之间用空格隔开
    options = ' '.join(question['options'])
    
    # 答案行：提取答案的选项字母
    correct_answers = question['correct_answer']
    # 提取每个正确答案的选项字母（如 "A、" 中的 "A"）
    answer_letters = []
    for ans in correct_answers:
        if ans.startswith(('A、', 'B、', 'C、', 'D、', 'E、', 'F、')):
            answer_letters.append(ans[0])
        elif ans in ['正确', '错误']:
            answer_letters.append(ans)
        else:
            # 填空题直接使用答案
            answer_letters.append(ans)
    # 合并答案字母，如 "A C"
    answers = ' '.join(answer_letters)
    
    # 添加到输出行
    output_lines.append(question_line)
    output_lines.append(options)
    output_lines.append(f"答案：{answers}")
    # 解析行：如果有解析内容则显示，否则显示"无"
    analysis = question.get('analysis', '')
    analysis_text = analysis if analysis else "无"
    output_lines.append(f"解析：{analysis_text}")
    output_lines.append("")  # 空行分隔不同题目

# 写入txt文件
with open('questions.txt', 'w', encoding='utf-8') as f:
    f.write('\n'.join(output_lines))

print("转换完成！结果已保存到 questions.txt")