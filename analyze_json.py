import json
import os

# 读取JSON文件
json_path = r"c:\Users\Dorufoc\Desktop\code\TG_helper\CAFUC\question.json"

with open(json_path, 'r', encoding='utf-8') as f:
    data = json.load(f)

# 定义递归函数来分析JSON结构
def analyze_json_structure(obj, path="", indent=0):
    result = []
    if isinstance(obj, dict):
        for key, value in obj.items():
            new_path = f"{path}.{key}" if path else key
            result.append((new_path, type(value).__name__))
            if isinstance(value, (dict, list)):
                result.extend(analyze_json_structure(value, new_path, indent + 2))
    elif isinstance(obj, list):
        if obj:
            # 只分析列表中的第一个元素来了解结构
            result.append((f"{path}[0]", type(obj[0]).__name__))
            if isinstance(obj[0], (dict, list)):
                result.extend(analyze_json_structure(obj[0], f"{path}[0]", indent + 2))
    return result

# 分析JSON结构
structure = analyze_json_structure(data)

# 打印结果
print("JSON文件结构分析：")
print("=" * 60)
for path, type_name in structure:
    print(f"{path} : {type_name}")

# 统计不同类型的元素
print("\n" + "=" * 60)
print("元素类型统计：")
type_counts = {}
for _, type_name in structure:
    type_counts[type_name] = type_counts.get(type_name, 0) + 1

for type_name, count in type_counts.items():
    print(f"{type_name} : {count}个")

# 打印顶层元素
print("\n" + "=" * 60)
print("顶层元素：")
for key, value in data.items():
    print(f"{key} : {type(value).__name__}")

# 如果有data字段，打印data的子元素
if "data" in data:
    print("\n" + "=" * 60)
    print("data字段的子元素：")
    for key, value in data["data"].items():
        print(f"{key} : {type(value).__name__}")

# 打印题目类型数量
if "data" in data and "studentPaperQuestionTypeVoList" in data["data"]:
    question_types = data["data"]["studentPaperQuestionTypeVoList"]
    print(f"\n" + "=" * 60)
    print(f"题目类型数量：{len(question_types)}")
    for i, q_type in enumerate(question_types):
        if "questionTypeCaption" in q_type and "questionCount" in q_type:
            print(f"  类型{i+1}: {q_type['questionTypeCaption']} ({q_type['questionCount']}题)")