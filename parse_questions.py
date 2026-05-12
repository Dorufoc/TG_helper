import re
import json

def parse_question_bank(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        lines = f.read().splitlines()

    questions = []
    i = 0
    total = len(lines)

    # 跳过开头课程名称行
    while i < total and not re.match(r'^\d+[、.．]\s*(单选题|填空题|简答题)', lines[i]):
        i += 1

    while i < total:
        line = lines[i].strip()

        # 检测大题标题行，如 "第2大题 填空题"
        big_title_match = re.match(r'^第\d+大题\s*(.*)', line)
        if big_title_match:
            i += 1
            continue

        # 检测题目开始：如 "1、单选题" 或 "1. 单选题" 或 "1．单选题"
        q_match = re.match(r'^(\d+)[、.．]\s*(单选题|填空题|简答题)', line)
        if not q_match:
            i += 1
            continue

        q_type = q_match.group(2)
        q_number = q_match.group(1)
        i += 1

        # 收集题目内容（可能多行，直到遇到选项A或下一个题目或参考答案）
        content_lines = []
        while i < total:
            l = lines[i].strip()
            if not l:
                i += 1
                continue
            # 如果是单选题且遇到 A. 开头，停止收集题干
            if q_type == '单选题' and re.match(r'^[A-D][.、．]', l):
                break
            # 如果是填空题且遇到 【参考答案】，停止收集题干
            if q_type == '填空题' and l.startswith('【参考答案】'):
                break
            # 如果是简答题且遇到 【参考答案】，停止收集题干
            if q_type == '简答题' and l.startswith('【参考答案】'):
                break
            # 如果遇到下一道题，停止
            if re.match(r'^\d+[、.．]\s*(单选题|填空题|简答题)', l):
                break
            # 如果遇到新的大题标题
            if re.match(r'^第\d+大题', l):
                break
            content_lines.append(l)
            i += 1

        content = ' '.join(content_lines).strip()
        # 清理多余空格
        content = re.sub(r'\s+', ' ', content)

        question = {
            'type': q_type,
            'content': content,
        }

        if q_type == '单选题':
            options = []
            # 读取选项（A. B. C. D.）
            while i < total:
                l = lines[i].strip()
                if not l:
                    i += 1
                    continue
                opt_match = re.match(r'^([A-D])[.、．]\s*(.*)', l)
                if opt_match:
                    options.append(opt_match.group(2).strip())
                    i += 1
                else:
                    break
            question['options'] = options

            # 寻找【参考答案】
            correct_answer = []
            while i < total:
                l = lines[i].strip()
                if not l:
                    i += 1
                    continue
                ref_match = re.search(r'【参考答案】\s*([A-D])', l)
                if ref_match:
                    correct_answer.append(ref_match.group(1))
                    i += 1
                    break
                # 如果遇到下一道题，停止
                if re.match(r'^\d+[、.．]\s*(单选题|填空题|简答题)', l):
                    break
                if re.match(r'^第\d+大题', l):
                    break
                i += 1

            question['correct_answer'] = correct_answer if correct_answer else []

        elif q_type == '填空题':
            # 寻找【参考答案】
            while i < total:
                l = lines[i].strip()
                if not l:
                    i += 1
                    continue
                if l.startswith('【参考答案】'):
                    # 解析参考答案，格式如 (1)、13 (2)、7856H
                    ref_text = l[len('【参考答案】'):].strip()
                    # 可能有多行参考答案
                    full_ref = ref_text
                    i += 1
                    while i < total:
                        next_l = lines[i].strip()
                        if not next_l or re.match(r'^\d+[、.．]', next_l) or next_l.startswith('第') or next_l.startswith('第'):
                            break
                        # 如果下一行仍然是参考答案的一部分（以(数字)、开头）
                        if re.match(r'^\(\d+\)[、，,]\s*', next_l) or re.match(r'^\(\d+\)[、，,]\s*', next_l):
                            full_ref += ' ' + next_l
                            i += 1
                        else:
                            break

                    # 解析答案
                    answers = []
                    # 匹配 (1)、xxx (2)、xxx 或 (1), xxx (2), xxx 等模式
                    parts = re.findall(r'\((\d+)\)[、，,]\s*([^\s(]+(?:\s+[^\s(]+)*)', full_ref)
                    if parts:
                        for num, ans in parts:
                            ans = ans.strip().rstrip('}').rstrip('{')
                            # 清理 {或} xxx 语法
                            ans = re.sub(r'\{或\}\s*.*', '', ans).strip()
                            answers.append(ans)
                    else:
                        # 尝试直接提取所有答案文本
                        raw_answers = re.findall(r'[（(]\d+[)）][、，,]\s*([^（(]+)', full_ref)
                        for ans in raw_answers:
                            ans = ans.strip().rstrip('}').rstrip('{')
                            ans = re.sub(r'\{或\}\s*.*', '', ans).strip()
                            answers.append(ans)

                    # 如果是单答案，直接使用
                    if not answers:
                        # 尝试直接取参考答案后的内容
                        clean = ref_text.strip()
                        if clean and not re.match(r'^\d', clean):
                            answers = [clean]

                    question['correct_answer'] = answers if answers else [full_ref.strip()]
                    break
                elif re.match(r'^\d+[、.．]', l) or re.match(r'^第\d+大题', l):
                    break
                i += 1

            # 如果还没找到参考答案
            if 'correct_answer' not in question:
                question['correct_answer'] = []

        elif q_type == '简答题':
            # 简答题：收集内容后，寻找参考答案
            answer_lines = []
            while i < total:
                l = lines[i].strip()
                if not l:
                    i += 1
                    continue
                if l.startswith('【参考答案】'):
                    ref_text = l[len('【参考答案】'):].strip()
                    if ref_text:
                        answer_lines.append(ref_text)
                    i += 1
                    # 继续收集多行答案
                    while i < total:
                        next_l = lines[i].strip()
                        if not next_l:
                            i += 1
                            continue
                        if re.match(r'^\d+[、.．]\s*(单选题|填空题|简答题)', next_l):
                            break
                        if next_l.startswith('第') and '大题' in next_l:
                            break
                        answer_lines.append(next_l)
                        i += 1
                    break
                elif re.match(r'^\d+[、.．]', l):
                    break
                elif re.match(r'^第\d+大题', l):
                    break
                i += 1

            if answer_lines:
                # 清理答案行
                clean_answers = []
                for a_line in answer_lines:
                    a_line = a_line.strip()
                    if a_line:
                        clean_answers.append(a_line)
                question['correct_answer'] = clean_answers
            else:
                question['correct_answer'] = []

        questions.append(question)

    return questions


if __name__ == '__main__':
    result = parse_question_bank('汇编原理题库.txt')
    output_path = '汇编原理题库.json'
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f'成功转换 {len(result)} 道题目到 {output_path}')

    # 统计各题型数量
    stats = {}
    for q in result:
        t = q['type']
        stats[t] = stats.get(t, 0) + 1
    print('题型统计:', stats)