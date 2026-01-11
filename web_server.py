import os
import json
import random
import logging
import datetime
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS

# 配置日志系统
log_dir = 'logs'
if not os.path.exists(log_dir):
    os.makedirs(log_dir)

log_filename = os.path.join(log_dir, f'web_server_{datetime.datetime.now().strftime("%Y%m%d")}.log')

# 设置日志格式
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler(log_filename, encoding='utf-8'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

# 获取当前脚本所在目录的绝对路径
BASE_DIR = os.path.abspath(os.path.dirname(__file__))

app = Flask(__name__, static_folder='web', static_url_path='')
CORS(app, resources={r"/*": {"origins": "*"}})  # 允许所有跨域请求

# 确保静态资源能够被正确访问
@app.route('/<path:path>')
def serve_static(path):
    return send_from_directory(app.static_folder, path)

# 全局变量管理题库和用户会话
question_manager = {
    'questions': [],
    'selected_questions': [],
    'user_answers': {},
    'viewed_answers': {}
}

class SafeQuestionManager:
    """安全的题库管理类，防止跨目录访问和代码注入"""
    
    def __init__(self):
        self.questions = []
        self.current_file = None
    
    def get_available_files(self):
        """获取BASE_DIR下所有可用的JSON题库文件"""
        try:
            files = []
            for filename in os.listdir(BASE_DIR):
                if filename.endswith('.json'):
                    files.append(filename)
            return files
        except Exception as e:
            print(f"获取可用文件失败: {e}")
            return []
    
    def load_questions(self, file_path):
        """安全加载题库文件，仅允许访问BASE_DIR下的JSON文件"""
        # 确保文件路径在BASE_DIR内
        safe_path = os.path.abspath(os.path.join(BASE_DIR, file_path))
        if not safe_path.startswith(BASE_DIR):
            raise ValueError("非法文件路径，禁止跨目录访问")
        
        # 确保只加载JSON文件
        if not safe_path.endswith('.json'):
            raise ValueError("仅允许加载JSON格式的题库文件")
        
        try:
            with open(safe_path, 'r', encoding='utf-8') as f:
                self.questions = json.load(f)
            
            # 自动识别选择题类型：根据正确答案数量将"选择题"转换为"单选题"或"多选题"
            for question in self.questions:
                if question.get('type') == '选择题':
                    correct_answers = question.get('correct_answer', [])
                    # 过滤掉空答案
                    correct_answers = [ans for ans in correct_answers if ans.strip()]
                    
                    if len(correct_answers) > 1:
                        question['type'] = '多选题'
                    else:
                        question['type'] = '单选题'
            
            self.current_file = safe_path
            return True
        except json.JSONDecodeError:
            raise ValueError("无效的JSON文件格式")
        except PermissionError:
            raise ValueError("没有权限访问该文件")
        except Exception as e:
            print(f"加载题库失败: {e}")
            return False
    
    def get_stats(self):
        """获取题库统计信息"""
        stats = {}
        for question in self.questions:
            q_type = question['type']
            if q_type in stats:
                stats[q_type] += 1
            else:
                stats[q_type] = 1
        return stats
    
    def get_total_questions(self):
        """获取题库总题数"""
        return len(self.questions)
    
    def extract_questions(self, total_count, type_ratios):
        """根据比例配置抽取题目"""
        # 计算各题型应抽取的数量
        question_counts = {}
        stats = self.get_stats()
        
        for q_type, ratio in type_ratios.items():
            if q_type in stats:
                # 计算数量，确保不超过实际可用数量
                count = int(total_count * ratio / 100)
                question_counts[q_type] = min(count, stats[q_type])
        
        # 分配剩余题目
        remaining = total_count - sum(question_counts.values())
        if remaining > 0:
            # 按题型数量比例分配剩余题目
            for q_type in question_counts:
                if remaining <= 0:
                    break
                available = stats[q_type] - question_counts[q_type]
                if available > 0:
                    add_count = min(remaining, available)
                    question_counts[q_type] += add_count
                    remaining -= add_count
        
        return self._extract_by_counts(question_counts)
    
    def _extract_by_counts(self, type_counts):
        """根据各题型数量抽取题目"""
        selected_questions = []
        stats = self.get_stats()
        
        # 定义优先题型顺序
        type_order = ['单选题', '多选题', '判断题', '填空题', '简答题', '释义题']
        
        # 处理优先顺序中的题型
        processed_types = set()
        for q_type in type_order:
            if q_type in type_counts and type_counts[q_type] > 0:
                # 筛选出该题型的所有题目
                type_questions = [q for q in self.questions if q['type'] == q_type]
                
                # 随机抽取指定数量的题目
                selected = random.sample(type_questions, min(type_counts[q_type], len(type_questions)))
                selected_questions.extend(selected)
                processed_types.add(q_type)
        
        # 处理剩余的其他题型（不在优先顺序列表中但用户选择了的题型）
        for q_type in type_counts:
            if q_type not in processed_types and type_counts[q_type] > 0:
                # 筛选出该题型的所有题目
                type_questions = [q for q in self.questions if q['type'] == q_type]
                if type_questions:
                    # 随机抽取指定数量的题目
                    selected = random.sample(type_questions, min(type_counts[q_type], len(type_questions)))
                    selected_questions.extend(selected)
        
        return selected_questions
    
    def extract_questions_by_count(self, type_counts):
        """根据各题型数量抽取题目（公开方法）"""
        return self._extract_by_counts(type_counts)

# 初始化安全的题库管理器
safe_manager = SafeQuestionManager()

# 错题本保存目录
WRONG_QUESTIONS_DIR = os.path.join(BASE_DIR, 'wrong_questions')
# 确保错题本目录存在
if not os.path.exists(WRONG_QUESTIONS_DIR):
    os.makedirs(WRONG_QUESTIONS_DIR)

@app.route('/api/available_files', methods=['GET'])
def get_available_files():
    """获取可用的题库文件列表"""
    try:
        files = safe_manager.get_available_files()
        return jsonify({
            'success': True,
            'files': files
        })
    except Exception as e:
        logger.error(f'获取文件列表失败: {str(e)}')
        return jsonify({'success': False, 'message': f'获取文件列表失败: {str(e)}'}), 500

@app.route('/api/load_questions', methods=['POST'])
def load_questions():
    """加载题库文件"""
    data = request.get_json()
    file_path = data.get('file_path', 'questions.json')
    
    try:
        success = safe_manager.load_questions(file_path)
        if success:
            stats = safe_manager.get_stats()
            return jsonify({
                'success': True,
                'message': '题库加载成功',
                'stats': stats,
                'total_questions': safe_manager.get_total_questions()
            })
        else:
            return jsonify({'success': False, 'message': '题库加载失败'})
    except ValueError as e:
        logger.error(f'加载题库参数错误: {str(e)}')
        return jsonify({'success': False, 'message': str(e)}), 400
    except Exception as e:
        logger.error(f'加载题库失败: {str(e)}')
        return jsonify({'success': False, 'message': f'加载失败: {str(e)}'}), 500

@app.route('/api/extract_questions', methods=['POST'])
def extract_questions():
    """抽取题目"""
    data = request.get_json()
    
    try:
        type_counts = data.get('type_ratios', {})
        if not isinstance(type_counts, dict):
            logger.error('题型数量必须是对象格式')
            return jsonify({'success': False, 'message': '题型数量必须是对象格式'}), 400
        
        # 验证题型数量
        for count in type_counts.values():
            if not isinstance(count, int) or count < 0:
                logger.error('题型数量必须是非负整数')
                return jsonify({'success': False, 'message': '题型数量必须是非负整数'}), 400
        
        # 重置用户会话
        # 直接传递type_counts作为各题型的数量
        question_manager['selected_questions'] = safe_manager.extract_questions_by_count(type_counts)
        question_manager['user_answers'] = {}
        question_manager['viewed_answers'] = {}
        
        return jsonify({
            'success': True,
            'message': '题目抽取成功',
            'questions_count': len(question_manager['selected_questions']),
            'questions': question_manager['selected_questions']  # 返回完整题目数据
        })
    except ValueError as e:
        logger.error(f'抽取题目参数错误: {str(e)}')
        return jsonify({'success': False, 'message': str(e)}), 400
    except Exception as e:
        logger.error(f'抽取题目失败: {str(e)}')
        return jsonify({'success': False, 'message': f'抽取失败: {str(e)}'}), 500

@app.route('/api/questions/<int:index>', methods=['GET'])
def get_question(index):
    """获取指定索引的题目"""
    try:
        if 0 <= index < len(question_manager['selected_questions']):
            question = question_manager['selected_questions'][index]
            user_answer = question_manager['user_answers'].get(index, [])
            is_answer_viewed = question_manager['viewed_answers'].get(index, False)
            
            return jsonify({
                'success': True,
                'question': {
                    'id': question.get('id', index + 1),
                    'type': question.get('type', ''),
                    'content': question.get('content', ''),
                    'options': question.get('options', []),
                    'analysis': question.get('analysis', '') if is_answer_viewed else ''
                },
                'user_answer': user_answer,
                'is_answer_viewed': is_answer_viewed
            })
        else:
            logger.error(f'题目索引无效: {index}')
            return jsonify({'success': False, 'message': '题目索引无效'}), 404
    except Exception as e:
        logger.error(f'获取题目失败: {str(e)}')
        return jsonify({'success': False, 'message': f'获取题目失败: {str(e)}'}), 500

@app.route('/api/questions/<int:index>/answer', methods=['POST'])
def save_answer(index):
    """保存用户答案"""
    data = request.get_json()
    answer = data.get('answer', [])
    
    try:
        if 0 <= index < len(question_manager['selected_questions']):
            question_manager['user_answers'][index] = answer
            return jsonify({'success': True, 'message': '答案保存成功'})
        else:
            logger.error(f'题目索引无效: {index}')
            return jsonify({'success': False, 'message': '题目索引无效'}), 404
    except Exception as e:
        logger.error(f'保存答案失败: {str(e)}')
        return jsonify({'success': False, 'message': f'保存答案失败: {str(e)}'}), 500

@app.route('/api/submit', methods=['POST'])
def submit_exam():
    """提交考试，计算成绩并返回错题信息"""
    try:
        total_questions = len(question_manager['selected_questions'])
        correct_count = 0
        wrong_questions = []
        
        for i in range(total_questions):
            question = question_manager['selected_questions'][i]
            user_answer = question_manager['user_answers'].get(i, [])
            correct_answer = question['correct_answer']
            
            # 根据题型检查答案是否正确
            is_correct = False
            if question['type'] in ['单选题', '判断题', '多选题', '选择题']:
                is_correct = set(user_answer) == set(correct_answer)
            elif question['type'] in ['填空题', '简答题', '释义题']:
                if len(user_answer) == len(correct_answer):
                    is_all_correct = True
                    for ua, ca in zip(user_answer, correct_answer):
                        if ua.strip() != ca.strip():
                            is_all_correct = False
                            break
                    is_correct = is_all_correct
            
            if is_correct:
                correct_count += 1
            else:
                # 收集错题信息
                wrong_question = {
                    'id': i + 1,
                    'type': question['type'],
                    'content': question['content'],
                    'options': question.get('options', []),
                    'user_answer': user_answer,
                    'correct_answer': correct_answer,
                    'analysis': question.get('analysis', '')
                }
                wrong_questions.append(wrong_question)
        
        # 计算得分（满分100）
        score = round((correct_count / total_questions) * 100, 1) if total_questions > 0 else 0
        
        return jsonify({
            'success': True,
            'score': score,
            'correct_count': correct_count,
            'total_questions': total_questions,
            'wrong_questions': wrong_questions
        })
    except Exception as e:
        logger.error(f'提交考试失败: {str(e)}')
        return jsonify({'success': False, 'message': f'提交失败: {str(e)}'}), 500

@app.route('/api/questions/<int:index>/view_answer', methods=['POST'])
def view_answer(index):
    """查看答案"""
    try:
        if 0 <= index < len(question_manager['selected_questions']):
            question_manager['viewed_answers'][index] = True
            question = question_manager['selected_questions'][index]
            
            return jsonify({
                'success': True,
                'correct_answer': question['correct_answer'],
                'analysis': question.get('analysis', '')
            })
        else:
            logger.error(f'题目索引无效: {index}')
            return jsonify({'success': False, 'message': '题目索引无效'}), 404
    except Exception as e:
        logger.error(f'查看答案失败: {str(e)}')
        return jsonify({'success': False, 'message': f'查看答案失败: {str(e)}'}), 500

@app.route('/api/save_wrong_questions', methods=['POST'])
def save_wrong_questions():
    """保存错题本到服务器"""
    try:
        # 尝试获取JSON数据，不依赖Content-Type头
        try:
            data = request.get_json()
            if data is None:
                # 如果get_json()失败，尝试直接从request.data解析
                data = json.loads(request.data)
        except json.JSONDecodeError:
            logger.error('请求体不是有效的JSON格式')
            return jsonify({'success': False, 'message': '请求体不是有效的JSON格式'}), 400
        except Exception as e:
            logger.error(f'解析请求数据失败: {str(e)}')
            return jsonify({'success': False, 'message': '解析请求数据失败'}), 400
        
        wrong_questions = data.get('wrong_questions', [])
        
        if not wrong_questions:
            logger.warning('没有错题可以保存')
            return jsonify({'success': False, 'message': '没有错题可以保存'}), 400
        
        # 确保错题本目录存在
        if not os.path.exists(WRONG_QUESTIONS_DIR):
            try:
                os.makedirs(WRONG_QUESTIONS_DIR)
                logger.info(f'创建错题本目录: {WRONG_QUESTIONS_DIR}')
            except Exception as e:
                logger.error(f'创建错题本目录失败: {str(e)}')
                return jsonify({'success': False, 'message': f'创建错题本目录失败: {str(e)}'}), 500
        
        # 使用前端传递的文件名或生成新的文件名
        file_name = data.get('file_name')
        if not file_name:
            # 如果前端没有传递文件名，生成一个新的
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            file_name = f'错题本_{timestamp}.json'
        else:
            # 确保文件名是安全的
            file_name = os.path.basename(file_name)
            # 移除可能的路径分隔符
            file_name = file_name.replace('/', '_').replace('\\', '_')
            # 确保文件扩展名为.json
            if not file_name.endswith('.json'):
                file_name += '.json'
        
        file_path = os.path.join(WRONG_QUESTIONS_DIR, file_name)
        
        # 准备错题本数据
        wrong_book = {
            'title': data.get('title', '错题本'),
            'generated_at': datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            'total_questions': len(wrong_questions),
            'questions': wrong_questions
        }
        
        # 保存到文件
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(wrong_book, f, ensure_ascii=False, indent=2)
        
        logger.info(f'错题本保存成功: {file_path}')
        return jsonify({
            'success': True,
            'message': '错题本已成功保存',
            'file_name': file_name,
            'file_path': file_path
        })
    except Exception as e:
        logger.error(f'保存错题本失败: {str(e)}')
        return jsonify({'success': False, 'message': f'保存错题本失败: {str(e)}'}), 500

@app.route('/api/generate_wrong_book', methods=['POST'])
def generate_wrong_book():
    """根据错题序号和作答内容生成错题集"""
    try:
        # 获取JSON数据
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'message': '请求体不是有效的JSON格式'}), 400
        
        # 获取错题序号和作答内容
        wrong_indices = data.get('wrong_indices', [])
        user_answers = data.get('user_answers', {})
        
        if not wrong_indices:
            return jsonify({'success': False, 'message': '没有错题序号可以处理'}), 400
        
        # 确保错题本目录存在
        if not os.path.exists(WRONG_QUESTIONS_DIR):
            try:
                os.makedirs(WRONG_QUESTIONS_DIR)
                logger.info(f'创建错题本目录: {WRONG_QUESTIONS_DIR}')
            except Exception as e:
                logger.error(f'创建错题本目录失败: {str(e)}')
                return jsonify({'success': False, 'message': f'创建错题本目录失败: {str(e)}'}), 500
        
        # 从本地完整题库中获取错题
        wrong_questions = []
        for index in wrong_indices:
            # 转换为0-based索引
            question_index = index - 1
            if 0 <= question_index < len(question_manager['selected_questions']):
                question = question_manager['selected_questions'][question_index]
                user_answer = user_answers.get(str(index), [])
                wrong_question = {
                    'id': index,
                    'type': question['type'],
                    'content': question['content'],
                    'options': question.get('options', []),
                    'user_answer': user_answer,
                    'correct_answer': question['correct_answer'],
                    'analysis': question.get('analysis', '')
                }
                wrong_questions.append(wrong_question)
        
        # 生成时间戳文件名
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        file_name = f'错题本_{timestamp}.json'
        file_path = os.path.join(WRONG_QUESTIONS_DIR, file_name)
        
        # 准备错题本数据
        wrong_book = {
            'title': '错题本',
            'generated_at': datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            'total_questions': len(wrong_questions),
            'questions': wrong_questions
        }
        
        # 保存到文件
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(wrong_book, f, ensure_ascii=False, indent=2)
        
        logger.info(f'错题本生成成功: {file_path}')
        return jsonify({
            'success': True,
            'message': '错题本已成功生成并保存',
            'file_name': file_name,
            'file_path': file_path
        })
    except Exception as e:
        logger.error(f'生成错题本失败: {str(e)}')
        return jsonify({'success': False, 'message': f'生成错题本失败: {str(e)}'}), 500

@app.route('/api/available_wrong_books', methods=['GET'])
def get_available_wrong_books():
    """获取可用的错题本列表"""
    try:
        books = []
        if os.path.exists(WRONG_QUESTIONS_DIR):
            for filename in os.listdir(WRONG_QUESTIONS_DIR):
                if filename.endswith('.json'):
                    file_path = os.path.join(WRONG_QUESTIONS_DIR, filename)
                    try:
                        with open(file_path, 'r', encoding='utf-8') as f:
                            data = json.load(f)
                            books.append({
                                'file_name': filename,
                                'title': data.get('title', '错题本'),
                                'total_questions': data.get('total_questions', 0),
                                'generated_at': data.get('generated_at', 0),
                                'file_size': os.path.getsize(file_path)
                            })
                    except Exception as e:
                        logger.error(f'读取错题本 {filename} 失败: {str(e)}')
                        continue
        
        # 按生成时间倒序排序
        books.sort(key=lambda x: x['generated_at'], reverse=True)
        
        return jsonify({
            'success': True,
            'books': books
        })
    except Exception as e:
        logger.error(f'获取错题本列表失败: {str(e)}')
        return jsonify({'success': False, 'message': f'获取错题本列表失败: {str(e)}'}), 500

@app.route('/')
def index():
    """返回前端页面"""
    return send_from_directory(app.static_folder, 'index.html')

if __name__ == '__main__':
    # 确保web目录存在
    if not os.path.exists(os.path.join(BASE_DIR, 'web')):
        os.makedirs(os.path.join(BASE_DIR, 'web'))
    
    # 在0.0.0.0上运行，允许局域网访问
    app.run(host='0.0.0.0', port=5000, debug=False)  # 生产环境应关闭debug
