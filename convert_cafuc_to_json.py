import json

def convert_cafuc_to_main_format(input_file_path, output_file_path):
    """
    将CAFUC格式的JSON转换为main.py支持的格式
    
    参数:
    input_file_path: str - CAFUC格式的JSON文件路径
    output_file_path: str - 转换后的JSON文件路径
    """
    
    # 读取CAFUC格式的JSON文件
    with open(input_file_path, 'r', encoding='utf-8') as f:
        cafuc_data = json.load(f)
    
    main_format_questions = []
    question_id_counter = 1
    
    # 遍历所有题型
    for question_type in cafuc_data['data']['studentPaperQuestionTypeVoList']:
        # 获取题型信息
        question_type_caption = question_type['questionTypeCaption']
        base_question_type = question_type['baseQuestionType']
        
        # 遍历该题型下的所有题目
        for cafuc_question in question_type['studentPaperItemVoList']:
            # 创建main格式的题目对象
            main_question = {
                'id': question_id_counter,
                'title': cafuc_data['data']['examCaption'],  # 使用考试标题作为题目标题
                'type': question_type_caption,
                'content': cafuc_question['text'],
                'options': [],
                'correct_answer': [],
                'analysis': cafuc_question['analysis']
            }
            
            # 根据题型处理选项
            if base_question_type in ['S_C', 'M_C']:  # 单选题和多选题
                if cafuc_question['answerJson']:
                    try:
                        answer_json = json.loads(cafuc_question['answerJson'])
                        if 'answerList' in answer_json:
                            for option in answer_json['answerList']:
                                # 格式化为"A 选项内容"的形式
                                main_question['options'].append(f"{option['answer']} {option['desc']}")
                    except json.JSONDecodeError:
                        print(f"解析选项失败: {cafuc_question['answerJson']}")
            elif base_question_type == 'T_O_F':  # 判断题
                # 判断题通常有两个选项：对和错
                main_question['options'] = ['正确', '错误']
            # 填空题不需要处理选项
            
            # 处理答案（注意：CAFUC格式中似乎没有直接的正确答案信息）
            # 尝试从各个可能的字段获取答案
            answer = cafuc_question['answer']
            marking_key = cafuc_question['markingKey']
            
            if answer and answer.strip():
                main_question['correct_answer'] = [answer.strip()]
            elif marking_key and marking_key.strip() and marking_key != '^~^' and marking_key != '^~^^~^':
                # 如果markingKey有值且不是特殊格式，则作为答案
                main_question['correct_answer'] = [marking_key.strip()]
            
            # 添加到结果列表
            main_format_questions.append(main_question)
            question_id_counter += 1
    
    # 保存转换后的JSON文件
    with open(output_file_path, 'w', encoding='utf-8') as f:
        json.dump(main_format_questions, f, ensure_ascii=False, indent=2)
    
    print(f"转换完成！共转换 {len(main_format_questions)} 道题目。")
    print(f"转换结果已保存到: {output_file_path}")


if __name__ == "__main__":
    input_file = "CAFUC/question.json"
    output_file = "cafuc_questions.json"
    
    convert_cafuc_to_main_format(input_file, output_file)
