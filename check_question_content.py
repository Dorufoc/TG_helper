import json
import re

# 读取JSON文件
json_path = r"c:\Users\Dorufoc\Desktop\code\TG_helper\CAFUC\question.json"

with open(json_path, 'r', encoding='utf-8') as f:
    data = json.load(f)

# 检查题目内容
def check_question_content():
    print("检查题目内容...")
    has_questions = False
    
    if "data" in data and "studentPaperQuestionTypeVoList" in data["data"]:
        question_types = data["data"]["studentPaperQuestionTypeVoList"]
        
        for q_type in question_types:
            if "studentPaperItemVoList" in q_type:
                questions = q_type["studentPaperItemVoList"]
                
                for i, question in enumerate(questions[:3]):  # 只检查前3个题目
                    print(f"\n题目 {i+1}:")
                    has_questions = True
                    
                    # 检查题目文本
                    if "text" in question:
                        print(f"  题目内容: {question['text']}")
                    elif "textEnc" in question:
                        # 去除HTML标签
                        text = re.sub(r'<[^>]+>', '', question['textEnc'])
                        print(f"  题目内容: {text}")
                    
                    # 检查选项
                    if "answerJson" in question and question["answerJson"]:
                        try:
                            answer_data = json.loads(question["answerJson"])
                            if "answerList" in answer_data:
                                print(f"  选项:")
                                for option in answer_data["answerList"]:
                                    if "answer" in option and "desc" in option:
                                        # 去除HTML标签
                                        desc = re.sub(r'<[^>]+>', '', option["desc"])
                                        print(f"    {option['answer']}: {desc}")
                        except json.JSONDecodeError:
                            print(f"  选项: 解析失败")
                    
                    # 检查答案
                    print(f"  答案字段检查:")
                    if "answer" in question:
                        print(f"    answer: '{question['answer']}'")
                    if "markingKey" in question:
                        print(f"    markingKey: '{question['markingKey']}'")
                    if "studentQuestionAnswer" in question:
                        print(f"    studentQuestionAnswer: '{question['studentQuestionAnswer']}'")
                    if "studentMCPAnswer" in question:
                        print(f"    studentMCPAnswer: '{question['studentMCPAnswer']}'")
        
        # 统计题目类型和数量
        print("\n" + "=" * 50)
        print("题目类型与数量统计:")
        for q_type in question_types:
            if "questionTypeCaption" in q_type and "questionCount" in q_type:
                print(f"  {q_type['questionTypeCaption']}: {q_type['questionCount']}题")
    
    if not has_questions:
        print("未找到题目内容")

# 运行检查
check_question_content()