import os
import json
import random
import logging
import datetime
import io
import string
import hashlib
import hmac
import base64
import secrets
import threading
import gc
import logging.handlers
from functools import wraps
from flask import Flask, request, jsonify, send_from_directory, session, Response
from flask_cors import CORS
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from api_encryptor import decrypt_api_key, generate_encryption_key, get_secret_key, delete_secret_key, is_key_token_valid

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

# 线程本地存储，用于在 before_request 中保存请求者身份
_request_context = threading.local()

# DeepSeek解析任务状态
parsing_status = {
    'running': False,
    'status': 'idle',
    'message': '',
    'total': 0,
    'processed': 0,
    'logs': []
}

class RequestContextFilter(logging.Filter):
    """日志过滤器，自动附加请求者身份到每条日志"""
    def filter(self, record):
        # 优先使用覆盖值（来自自定义WSGIRequestHandler）
        if hasattr(record, 'user_identity_override'):
            record.user_identity = record.user_identity_override
        else:
            user_identity = getattr(_request_context, 'user_identity', '[System]')
            record.user_identity = user_identity
        return True

# 修改日志格式以包含用户身份
base_logger = logging.getLogger()
for handler in base_logger.handlers:
    handler.addFilter(RequestContextFilter())
    handler.setFormatter(logging.Formatter(
        '%(asctime)s [%(levelname)s] %(user_identity)s %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    ))

# 替换Werkzeug访问日志的handler，使其也能输出用户身份
werkzeug_logger = logging.getLogger('werkzeug')
werkzeug_logger.handlers.clear()
werkzeug_logger.setLevel(logging.INFO)
# 复用根logger的handler（带过滤器）
for handler in base_logger.handlers:
    werkzeug_logger.addHandler(handler)
werkzeug_logger.propagate = False

# 获取当前脚本所在目录的绝对路径
BASE_DIR = os.path.abspath(os.path.dirname(__file__))

# 用户配置文件路径
USERS_FILE = os.path.join(BASE_DIR, 'users.json')

# 系统配置文件路径
SETTINGS_FILE = os.path.join(BASE_DIR, 'settings.json')

# 默认配置
DEFAULT_SETTINGS = {
    "account": {
        "default_role": "guest",
        "auth_timeout_minutes": 1
    },
    "ai_providers": {
        "openai": {
            "base_url": "https://api.openai.com",
            "api_key": "",
            "model_id": "gpt-4o",
            "max_tokens": 4096
        },
        "anthropic": {
            "base_url": "https://api.anthropic.com",
            "api_key": "",
            "model_id": "claude-3-5-sonnet-latest",
            "max_tokens": 4096
        },
        "deepseek": {
            "base_url": "https://api.deepseek.com",
            "api_format": "openai",
            "api_key": "",
            "model_id": "deepseek-v4-pro",
            "thinking": "enabled",
            "reasoning_effort": "high"
        }
    }
}

def generate_invitation_code():
    """生成随机邀请码"""
    chars = string.ascii_uppercase + string.digits
    code = ''.join(random.choices(chars, k=8))
    return code

def load_users():
    """加载用户配置文件"""
    try:
        if os.path.exists(USERS_FILE):
            with open(USERS_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                users = data.get('users', [])
                # 为旧数据兼容：添加缺失字段
                for user in users:
                    if 'role' not in user:
                        user['role'] = 'user'
                    if 'status' not in user:
                        user['status'] = 'active'
                    if 'invitation_code' not in user:
                        user['invitation_code'] = generate_invitation_code()
                return users
    except Exception as e:
        logger.error(f"加载用户配置文件失败: {e}")
    return []

def verify_user(username, password):
    """验证用户名和密码（使用哈希密码）"""
    users = load_users()
    hashed_pw = hash_password(password)
    for user in users:
        if user.get('username') == username and user.get('password') == hashed_pw:
            return True
    return False

def save_users(users):
    """保存用户配置文件"""
    try:
        with open(USERS_FILE, 'w', encoding='utf-8') as f:
            json.dump({'users': users}, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        logger.error(f"保存用户配置文件失败: {e}")
        return False

def load_settings():
    """
    加载系统配置文件
    
    如果 settings.json 不存在，返回默认配置并自动创建配置文件。
    
    Returns:
        dict: 系统配置字典
    """
    try:
        if os.path.exists(SETTINGS_FILE):
            with open(SETTINGS_FILE, 'r', encoding='utf-8') as f:
                settings = json.load(f)
            logger.info('系统配置加载成功')
            return settings
        else:
            # 配置文件不存在，使用默认配置并创建文件
            logger.info('系统配置文件不存在，使用默认配置')
            save_settings(DEFAULT_SETTINGS)
            return json.loads(json.dumps(DEFAULT_SETTINGS))  # 深拷贝
    except json.JSONDecodeError as e:
        logger.error(f"系统配置文件格式错误: {e}，使用默认配置")
        return json.loads(json.dumps(DEFAULT_SETTINGS))
    except Exception as e:
        logger.error(f"加载系统配置文件失败: {e}")
        return json.loads(json.dumps(DEFAULT_SETTINGS))

def save_settings(settings):
    """
    保存系统配置文件
    
    Args:
        settings (dict): 要保存的配置字典
    
    Returns:
        bool: 保存成功返回 True，否则返回 False
    """
    try:
        with open(SETTINGS_FILE, 'w', encoding='utf-8') as f:
            json.dump(settings, f, ensure_ascii=False, indent=2)
        logger.info('系统配置保存成功')
        return True
    except Exception as e:
        logger.error(f"保存系统配置文件失败: {e}")
        return False

def hash_password(password):
    """密码哈希"""
    return hashlib.sha256(password.encode('utf-8')).hexdigest()

def generate_captcha_code(length=4):
    """生成随机验证码字符串（4位数字）"""
    return ''.join(random.choices(string.digits, k=length))

def generate_captcha_image(captcha_code):
    """生成扭曲验证码图像"""
    width = 160
    height = 60
    
    # 创建图像
    image = Image.new('RGB', (width, height), (255, 255, 255))
    draw = ImageDraw.Draw(image)
    
    # 绘制干扰线
    for _ in range(8):
        x1 = random.randint(0, width)
        y1 = random.randint(0, height)
        x2 = random.randint(0, width)
        y2 = random.randint(0, height)
        color = (random.randint(100, 200), random.randint(100, 200), random.randint(100, 200))
        draw.line([(x1, y1), (x2, y2)], fill=color, width=1)
    
    # 绘制干扰点
    for _ in range(50):
        x = random.randint(0, width)
        y = random.randint(0, height)
        color = (random.randint(100, 200), random.randint(100, 200), random.randint(100, 200))
        draw.point((x, y), fill=color)
    
    # 尝试使用系统字体
    font_path = None
    font_paths = [
        r'C:\Windows\Fonts\arial.ttf',
        r'C:\Windows\Fonts\msyh.ttc',
        r'C:\Windows\Fonts\simhei.ttf',
    ]
    for path in font_paths:
        if os.path.exists(path):
            font_path = path
            break
    
    try:
        if font_path:
            font = ImageFont.truetype(font_path, 36)
        else:
            font = ImageFont.load_default()
    except:
        font = ImageFont.load_default()
    
    # 绘制验证码文字
    char_width = width // len(captcha_code)
    for i, char in enumerate(captcha_code):
        x = char_width * i + random.randint(5, 15)
        y = random.randint(10, 20)
        angle = random.randint(-30, 30)
        color = (random.randint(0, 100), random.randint(0, 100), random.randint(0, 100))
        
        # 创建单个字符图像用于旋转
        char_image = Image.new('RGBA', (40, 50), (255, 255, 255, 0))
        char_draw = ImageDraw.Draw(char_image)
        char_draw.text((0, 0), char, font=font, fill=color)
        
        # 旋转
        char_image = char_image.rotate(angle, expand=True)
        
        # 粘贴到主图像
        image.paste(char_image, (x, y), char_image)
    
    # 应用模糊效果增加识别难度
    image = image.filter(ImageFilter.GaussianBlur(radius=0.5))
    
    return image

def admin_required(f):
    """管理员权限验证装饰器"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('logged_in'):
            return jsonify({'success': False, 'message': '未登录', 'require_login': True}), 401
        if session.get('role') != 'admin':
            return jsonify({'success': False, 'message': '需要管理员权限'}), 403
        return f(*args, **kwargs)
    return decorated_function

def login_required(f):
    """登录验证装饰器"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('logged_in'):
            return jsonify({'success': False, 'message': '未登录', 'require_login': True}), 401
        # 检查用户是否被封禁
        username = session.get('username')
        users = load_users()
        for user in users:
            if user.get('username') == username:
                if user.get('status') == 'banned':
                    session.clear()
                    return jsonify({'success': False, 'message': '当前用户已被封禁，请退出账户重新登录', 'banned': True}), 403
                break
        return f(*args, **kwargs)
    return decorated_function

# 题库JSON文件目录
PAPER_JSON_DIR = os.path.join(BASE_DIR, 'paper_json')
if not os.path.exists(PAPER_JSON_DIR):
    os.makedirs(PAPER_JSON_DIR)
    logger.info(f'创建题库目录: {PAPER_JSON_DIR}')

app = Flask(__name__, static_folder='web', static_url_path='')

# Session配置
app.secret_key = os.environ.get('FLASK_SECRET_KEY', 'dev-secret-key-change-in-production-12345')
app.config['SESSION_COOKIE_NAME'] = 'tg_helper_session'
app.config['SESSION_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'

CORS(app, resources={r"/*": {"origins": "*"}})

@app.before_request
def set_request_context():
    """在每个请求开始前，保存请求者身份信息到线程本地存储"""
    user_id = request.headers.get('X-User-Identity', 'unknown')
    ip = request.remote_addr or 'unknown'
    _request_context.user_identity = f'[User:{user_id}][IP:{ip}]'

@app.after_request
def log_request_info(response):
    """在每个请求结束后，记录访问日志"""
    method = request.method
    path = request.path
    status = response.status_code
    logger.info(f'请求: {method} {path} | 状态码: {status}')
    return response

# 确保静态资源能够被正确访问
@app.route('/<path:path>')
def serve_static(path):
    return send_from_directory(app.static_folder, path)

class SafeQuestionManager:
    """安全的题库管理类，防止跨目录访问和代码注入"""
    
    def __init__(self):
        self.questions = []
        self.current_file = None
    
    def get_available_files(self):
        """获取paper_json目录下所有可用的JSON题库文件"""
        try:
            files = []
            if os.path.exists(PAPER_JSON_DIR):
                for filename in os.listdir(PAPER_JSON_DIR):
                    if filename.endswith('.json'):
                        files.append(filename)
            return files
        except Exception as e:
            logger.error(f"获取可用文件失败: {e}")
            return []
    
    def load_questions(self, file_path):
        """安全加载题库文件，仅允许访问PAPER_JSON_DIR下的JSON文件"""
        # 确保文件路径在PAPER_JSON_DIR内
        safe_path = os.path.abspath(os.path.join(PAPER_JSON_DIR, file_path))
        if not safe_path.startswith(PAPER_JSON_DIR):
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
            
            # 数据标准化：清理HTML、修复答案格式
            normalize_questions(self.questions)
            
            self.current_file = safe_path
            return True
        except json.JSONDecodeError:
            raise ValueError("无效的JSON文件格式")
        except PermissionError:
            raise ValueError("没有权限访问该文件")
        except Exception as e:
            logger.error(f"加载题库失败: {e}")
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
        type_order = ['单选题', '多选题', '判断题', '填空题', '简答题', '释义题', '论述题', '编程题']
        
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

def normalize_questions(questions):
    """标准化题目数据，修复常见兼容性问题"""
    import re
    from html import unescape

    def clean_html(text):
        if not text:
            return ''
        text = unescape(str(text)).replace('\r\n', '\n').replace('\r', '\n')
        text = text.replace('\xa0', ' ').replace('&nbsp;', ' ')

        # 只清理明确的 HTML 标签，避免误删题目中的 <T>、<bean>、<url-pattern> 等文本内容
        text = re.sub(r'<!--.*?-->', '', text, flags=re.S)
        text = re.sub(r'<\s*br\s*/?\s*>', '\n', text, flags=re.I)
        text = re.sub(r'<\s*/\s*(?:p|div|li|tr|h[1-6]|section|article)\s*>', '\n', text, flags=re.I)
        text = re.sub(
            r'<\s*/?\s*(?:html|body|p|div|span|strong|em|b|i|u|small|sub|sup|code|pre|blockquote|'
            r'ul|ol|li|table|thead|tbody|tfoot|tr|td|th|h[1-6]|section|article|a)\b[^>]*>',
            '',
            text,
            flags=re.I,
        )

        text = re.sub(r'[ \t\f\v]+', ' ', text)
        text = re.sub(r'\n{3,}', '\n\n', text)
        return text.strip()

    for q in questions:
        # 1. 清理 HTML 标签
        if 'content' in q:
            q['content'] = clean_html(q['content'])
        if 'analysis' in q:
            q['analysis'] = clean_html(q['analysis'])
        if 'options' in q and q['options']:
            q['options'] = [clean_html(o) for o in q['options']]

        # 2. 判断题：将字母答案映射为选项文本
        #    支持三种情形：
        #    a) 选项带字母前缀 ("A 正确", "B 错误") → 按字母查找
        #    b) 选项纯文本 ("正确", "错误") → 索引映射 A=0, B=1
        #    c) 答案已是文本 ("正确") → 保持不动
        if q.get('type') == '判断题' and q.get('correct_answer'):
            opts = q.get('options', [])
            new_answers = []
            for ans in q['correct_answer']:
                # 情况 c: 答案已经是文本（非单字母），无需映射
                if ans not in ('A', 'B') or not opts:
                    new_answers.append(ans)
                    continue
                # 情况 a: 优先按字母前缀查找（兼容 A=错误, B=正确 的乱序）
                found = False
                for opt in opts:
                    m_opt = re.match(r'^([A-Za-z])[.、:\s]*(.*)', opt)
                    if m_opt and m_opt.group(1) == ans:
                        new_answers.append(m_opt.group(2).strip())
                        found = True
                        break
                if found:
                    continue
                # 情况 b: 无字母前缀时，按索引映射（A→0, B→1）
                idx = 0 if ans == 'A' else 1
                if idx < len(opts):
                    opt_text = opts[idx]
                    m = re.match(r'^[A-Za-z][.、:\s]*(.*)', opt_text)
                    if m:
                        opt_text = m.group(1).strip()
                    new_answers.append(opt_text)
                else:
                    new_answers.append(ans)
            q['correct_answer'] = new_answers

        # 3. 多选题：拆分连续字母答案
        #    ["ACD"] → ["A", "C", "D"]
        #    ["A", "C", "D"] 保持不动
        if q.get('type') == '多选题' and q.get('correct_answer'):
            new_answers = []
            for ans in q['correct_answer']:
                cleaned = ans.replace(',', '').replace('，', '').replace(' ', '')
                if re.match(r'^[A-Za-z]{2,}$', cleaned):
                    new_answers.extend(list(cleaned))
                else:
                    new_answers.append(ans)
            q['correct_answer'] = new_answers

        # 4. 填空题：拆分 ^~^ 分隔的多答案
        if q.get('type') == '填空题' and q.get('correct_answer'):
            new_answers = []
            for ans in q['correct_answer']:
                if '^~^' in ans:
                    parts = [a.strip() for a in ans.split('^~^') if a.strip()]
                    new_answers.extend(parts if parts else [ans])
                else:
                    new_answers.append(ans)
            q['correct_answer'] = new_answers

    return questions

# 初始化安全的题库管理器
safe_manager = SafeQuestionManager()

# 错题本保存根目录
WRONG_QUESTIONS_ROOT_DIR = os.path.join(BASE_DIR, 'wrong_questions')
# 确保错题本根目录存在
if not os.path.exists(WRONG_QUESTIONS_ROOT_DIR):
    os.makedirs(WRONG_QUESTIONS_ROOT_DIR)

def get_user_wrong_questions_dir(username):
    """获取指定用户的错题本目录"""
    user_dir = os.path.join(WRONG_QUESTIONS_ROOT_DIR, username)
    if not os.path.exists(user_dir):
        os.makedirs(user_dir)
    return user_dir

@app.route('/api/captcha', methods=['GET'])
def get_captcha():
    """生成验证码图像"""
    captcha_code = generate_captcha_code(4)
    session['captcha_code'] = captcha_code
    
    image = generate_captcha_image(captcha_code)
    
    # 将图像转换为PNG字节流
    img_io = io.BytesIO()
    image.save(img_io, 'PNG')
    img_io.seek(0)
    
    return Response(img_io.read(), mimetype='image/png')

@app.route('/api/register', methods=['POST'])
def register():
    """用户注册"""
    data = request.get_json()
    username = data.get('username', '').strip()
    password = data.get('password', '')
    confirm_password = data.get('confirm_password', '')
    captcha = data.get('captcha', '').strip()
    invite_code = data.get('invite_code', '').strip()
    
    if not username:
        return jsonify({'success': False, 'message': '用户名不能为空'}), 400
    
    if len(username) < 3 or len(username) > 20:
        return jsonify({'success': False, 'message': '用户名长度必须在3-20个字符之间'}), 400
    
    if not username.isalnum():
        return jsonify({'success': False, 'message': '用户名只能包含字母和数字'}), 400
    
    if not password:
        return jsonify({'success': False, 'message': '密码不能为空'}), 400
    
    if len(password) < 6:
        return jsonify({'success': False, 'message': '密码长度不能少于6个字符'}), 400
    
    if password != confirm_password:
        return jsonify({'success': False, 'message': '两次输入的密码不一致'}), 400
    
    if not captcha:
        return jsonify({'success': False, 'message': '请输入验证码'}), 400
    
    session_captcha = session.get('captcha_code', '').lower()
    if captcha.lower() != session_captcha:
        return jsonify({'success': False, 'message': '验证码错误'}), 400
    
    if not invite_code:
        return jsonify({'success': False, 'message': '请输入邀请码'}), 400
    
    users = load_users()
    for user in users:
        if user.get('username') == username:
            return jsonify({'success': False, 'message': '用户名已存在'}), 409
    
    new_user = {
        'username': username,
        'password': hash_password(password),
        'role': 'guest',
        'status': 'active',
        'invitation_code': generate_invitation_code(),
        'created_at': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    }
    users.append(new_user)
    
    if save_users(users):
        logger.info(f'用户 {username} 注册成功')
        return jsonify({
            'success': True,
            'message': '注册成功，请登录'
        })
    else:
        logger.error(f'用户注册失败：保存配置文件失败')
        return jsonify({'success': False, 'message': '注册失败，请稍后重试'}), 500

@app.route('/api/login', methods=['POST'])
def login():
    """用户登录"""
    data = request.get_json()
    username = data.get('username', '').strip()
    password = data.get('password', '')
    captcha = data.get('captcha', '').strip()
    
    if not username or not password:
        return jsonify({'success': False, 'message': '用户名和密码不能为空'}), 400
    
    if captcha:
        session_captcha = session.get('captcha_code', '').lower()
        if captcha.lower() != session_captcha:
            return jsonify({'success': False, 'message': '验证码错误'}), 400
    
    users = load_users()
    hashed_pw = hash_password(password)
    user_found = None
    for user in users:
        if user.get('username') == username and user.get('password') == hashed_pw:
            user_found = user
            break
    
    if user_found:
        if user_found.get('status') == 'banned':
            return jsonify({'success': False, 'message': '当前用户已被封禁，请联系管理员'}), 403
        
        session['logged_in'] = True
        session['username'] = username
        session['role'] = user_found.get('role', 'user')
        session.pop('captcha_code', None)
        logger.info(f'用户 {username} 登录成功')
        return jsonify({
            'success': True,
            'message': f'登录成功，欢迎 {username}',
            'username': username,
            'role': session['role']
        })
    else:
        logger.warning(f'用户 {username} 登录失败')
        return jsonify({'success': False, 'message': '用户名或密码错误'}), 401

@app.route('/api/logout', methods=['POST'])
def logout():
    """用户登出"""
    username = session.get('username', 'unknown')
    session.clear()
    logger.info(f'用户 {username} 已登出')
    return jsonify({'success': True, 'message': '已登出'})

@app.route('/api/check_login', methods=['GET'])
def check_login():
    """检查登录状态"""
    if session.get('logged_in'):
        return jsonify({
            'success': True,
            'logged_in': True,
            'username': session.get('username'),
            'role': session.get('role', 'user')
        })
    return jsonify({
        'success': True,
        'logged_in': False
    })

@app.route('/api/verify_user', methods=['GET'])
@login_required
def verify_user_status():
    """验证当前用户状态（用于定时检测）"""
    username = session.get('username')
    users = load_users()
    
    # 查找当前用户
    user_found = None
    for user in users:
        if user.get('username') == username:
            user_found = user
            break
    
    if not user_found:
        # 用户不存在，清除会话
        session.clear()
        return jsonify({
            'success': True,
            'valid': False,
            'reason': 'user_not_found',
            'message': '用户不存在'
        })
    
    if user_found.get('status') == 'banned':
        # 用户被封禁
        session.clear()
        return jsonify({
            'success': True,
            'valid': False,
            'reason': 'banned',
            'message': '当前用户已被封禁'
        })
    
    # 用户有效，返回用户信息
    return jsonify({
        'success': True,
        'valid': True,
        'role': user_found.get('role', 'user'),
        'username': username,
        'message': f'用户 {username} 验证通过'
    })

@app.route('/admin')
def admin_page():
    """返回管理员页面"""
    return send_from_directory(app.static_folder, 'admin.html')

@app.route('/api/admin/users', methods=['GET'])
@admin_required
def get_all_users():
    """获取所有用户列表（管理员专用）"""
    try:
        users = load_users()
        user_list = []
        for user in users:
            user_list.append({
                'username': user.get('username'),
                'password': user.get('password'),
                'role': user.get('role', 'user'),
                'status': user.get('status', 'active'),
                'invitation_code': user.get('invitation_code'),
                'created_at': user.get('created_at', '未知')
            })
        return jsonify({
            'success': True,
            'users': user_list
        })
    except Exception as e:
        logger.error(f'获取用户列表失败: {e}')
        return jsonify({'success': False, 'message': f'获取用户列表失败: {str(e)}'}), 500

@app.route('/api/admin/users/<username>/role', methods=['PUT'])
@admin_required
def update_user_role(username):
    """修改用户角色"""
    data = request.get_json()
    new_role = data.get('role')
    
    if new_role not in ['guest', 'user', 'admin']:
        return jsonify({'success': False, 'message': '无效的角色'}), 400
    
    users = load_users()
    for user in users:
        if user.get('username') == username:
            user['role'] = new_role
            if save_users(users):
                logger.info(f'管理员 {session.get("username")} 将用户 {username} 的角色修改为 {new_role}')
                return jsonify({
                    'success': True,
                    'message': '角色修改成功'
                })
            else:
                return jsonify({'success': False, 'message': '保存失败'}), 500
    
    return jsonify({'success': False, 'message': '用户不存在'}), 404

@app.route('/api/admin/users/<username>/status', methods=['PUT'])
@admin_required
def update_user_status(username):
    """修改用户状态（封禁/解封）"""
    data = request.get_json()
    new_status = data.get('status')
    
    if new_status not in ['active', 'banned']:
        return jsonify({'success': False, 'message': '无效的状态'}), 400
    
    users = load_users()
    for user in users:
        if user.get('username') == username:
            user['status'] = new_status
            if save_users(users):
                action = '封禁' if new_status == 'banned' else '解封'
                logger.info(f'管理员 {session.get("username")} {action}了用户 {username}')
                return jsonify({
                    'success': True,
                    'message': f'用户已{action}'
                })
            else:
                return jsonify({'success': False, 'message': '保存失败'}), 500
    
    return jsonify({'success': False, 'message': '用户不存在'}), 404

@app.route('/api/admin/users/<username>/invitation_code', methods=['PUT'])
@admin_required
def update_user_invitation_code(username):
    """重置用户邀请码"""
    users = load_users()
    for user in users:
        if user.get('username') == username:
            old_code = user.get('invitation_code')
            new_code = generate_invitation_code()
            user['invitation_code'] = new_code
            if save_users(users):
                logger.info(f'管理员 {session.get("username")} 重置了用户 {username} 的邀请码')
                return jsonify({
                    'success': True,
                    'message': '邀请码已重置',
                    'new_code': new_code
                })
            else:
                return jsonify({'success': False, 'message': '保存失败'}), 500
    
    return jsonify({'success': False, 'message': '用户不存在'}), 404

@app.route('/api/admin/deepseek/parse', methods=['POST'])
@admin_required
def deepseek_parse():
    """DeepSeek题目解析（异步任务）
    
    安全机制：
    - 接收加密的API密钥而不是明文
    - 使用key_token查找对应的解密密钥
    - 解密后立即销毁解密密钥（del语句）
    - 在parse_questions函数内的finally块中销毁api_key变量
    """
    try:
        data = request.get_json()
        encrypted_api_key = data.get('encrypted_api_key', '').strip()
        key_token = data.get('key_token', '').strip()
        file_path = data.get('file_path', 'questions.json')
        
        # 安全校验：必须提供加密API密钥和令牌
        if not encrypted_api_key or not key_token:
            return jsonify({'success': False, 'message': '缺少加密API密钥或令牌'}), 400
        
        # 校验令牌是否有效
        if not is_key_token_valid(key_token):
            return jsonify({'success': False, 'message': '加密密钥已过期或无效，请重新获取'}), 401
        
        secret_key = get_secret_key(key_token)
        
        # 解密API密钥
        api_key = decrypt_api_key(encrypted_api_key, secret_key)
        if not api_key:
            return jsonify({'success': False, 'message': 'API密钥解密失败'}), 400
        
        # 立即销毁解密密钥（安全机制：使用后立即清除）
        delete_secret_key(key_token)
        
        import threading
        import requests
        import re
        from concurrent.futures import ThreadPoolExecutor
        
        def parse_questions(api_key_to_use):
            """后台解析题目
            
            安全机制：
            - api_key_local在finally块中被彻底销毁
            - 防止内存残留导致密钥泄露
            """
            api_key_local = api_key_to_use
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    questions = json.load(f)
            except Exception as e:
                logger.error(f'加载题库失败: {e}')
                parsing_status['running'] = False
                parsing_status['status'] = 'error'
                parsing_status['message'] = f'加载题库失败: {str(e)}'
                del api_key_local
                gc.collect()
                return
            
            total = len(questions)
            parsing_status['total'] = total
            parsing_status['processed'] = 0
            parsing_status['logs'] = []
            parsing_status['status'] = 'running'
            
            system_prompt = "# Role\n你是一个顶级全科教育专家与智能助教 Agent。你的核心任务是针对各类题目（选择、填空、主观、代码、计算推理等），生成极简、专业、易懂的答案解析。\n\n# Evaluation Criteria\n1. 极致精炼：剔除所有大话、空话和过度修饰，单句尽量不超过 15 字，直奔主题。\n2. 语言通俗：用最简单的日常语言解释复杂概念，降低读者的认知负荷。\n3. 规范专业：术语使用必须严谨、标准，格式必须统一。\n\n# Workflow By Task Types\n\n## 1. 单项/多项选择题\n- 【核心答案】直接给出正确选项（例：**正确答案：A** 或 **正确答案：A、C**）。\n- 【选项剖析】逐一拆解所有选项。先说该选项对/错在哪里，再指出其背后的核心考点。\n  - 格式：\n    - A. [正确/错误] + [精炼原因]（考点：xxx）\n    - B. [正确/错误] + [精炼原因]（考点：xxx）\n\n## 2. 代码/编程题\n- 【标准源码】提供排版整洁、自带核心注释的正确代码块。\n- 【逐行解析】严禁概括。必须对代码进行逐行（或紧密代码块）说明。\n  - 格式：\n    - `第 X 行`：该行代码的具体功能与变量变化。\n- 【算法核心】用一句话总结该算法的时间复杂度和空间复杂度。\n\n## 3. 逻辑推理与计算题\n- 【最终结果】开门见山给出最终数值或推论结论。\n- 【步步为营】将解题过程拆解为不可分割的微小步骤。\n  - 格式：\n    - 步骤 1：[已知条件转化/第一步计算]\n    - 步骤 2：[公式带入/核心推理]\n    - 步骤 3：[最终推导]\n\n## 4. 普通主观题/其他题型\n- 【参考答案】给出标准、规范的得分点文本。\n- 【核心考点】一句话指出本题考察的知识模块。\n- 【答题思路】用 2-3 个核心要点（Bullet Points）阐述如何从题目联想到答案。\n\n# Output Constraints\n- 严禁任何自我介绍、寒暄或总结性套话。\n- 必须严格使用 Markdown 标题、加粗和列表进行视觉锚定。\n- 遇到公式必须使用 LaTeX 格式。\n- 每一个分析步骤或选项解析，务必做到\"一句话讲透\"。"
            
            try:
                for i, question in enumerate(questions):
                    if not parsing_status['running']:
                        parsing_status['status'] = 'stopped'
                        parsing_status['message'] = '解析被用户取消'
                        return
                    
                    if question.get('analysis', '').strip():
                        parsing_status['logs'].append(f"跳过第 {i+1} 题（已有解析）")
                        parsing_status['processed'] = i + 1
                        continue
                    
                    content = question.get('content', '')
                    options = question.get('options', [])
                    correct_answer = question.get('correct_answer', [])
                    
                    user_message = f"题目：{content}\n"
                    if options:
                        user_message += "选项：\n"
                        for opt in options:
                            user_message += f"  {opt}\n"
                    
                    if correct_answer:
                        if len(correct_answer) == 1:
                            user_message += f"正确答案：{correct_answer[0]}"
                        else:
                            user_message += "正确答案：\n"
                            for ans in correct_answer:
                                user_message += f"  {ans}\n"
                    
                    parsing_status['logs'].append(f"正在解析第 {i+1}/{total} 题...")
                    parsing_status['processed'] = i + 1
                    
                    try:
                        url = "https://api.deepseek.com/v1/chat/completions"
                        headers = {
                            "Authorization": f"Bearer {api_key_local}",
                            "Content-Type": "application/json"
                        }
                        api_data = {
                            "model": "deepseek-chat",
                            "messages": [
                                {"role": "system", "content": system_prompt},
                                {"role": "user", "content": user_message}
                            ],
                            "temperature": 0.7,
                            "max_tokens": 500
                        }
                        
                        response = requests.post(url, headers=headers, json=api_data, timeout=30)
                        response.raise_for_status()
                        result = response.json()
                        analysis = result.get('choices', [{}])[0].get('message', {}).get('content', '')
                        
                        analysis = analysis.replace('**', '').replace('`', '').strip()
                        analysis = re.sub(r'<([a-zA-Z][a-zA-Z0-9-]*)>', r'&lt;\1&gt;', analysis)
                        analysis = re.sub(r'</([a-zA-Z][a-zA-Z0-9-]*)>', r'&lt;/\1&gt;', analysis)
                        
                        if analysis:
                            question['analysis'] = analysis
                            parsing_status['logs'].append(f"第 {i+1} 题解析成功")
                        else:
                            parsing_status['logs'].append(f"第 {i+1} 题解析失败，跳过保存")
                        
                    except Exception as e:
                        logger.error(f'调用DeepSeek API失败: {e}')
                        parsing_status['logs'].append(f"第 {i+1} 题解析失败: {str(e)}")
                    
                    if (i + 1) % 5 == 0 or i + 1 == total:
                        try:
                            with open(file_path, 'w', encoding='utf-8') as f:
                                json.dump(questions, f, ensure_ascii=False, indent=2)
                        except Exception as e:
                            logger.error(f'保存题库失败: {e}')
                
                try:
                    with open(file_path, 'w', encoding='utf-8') as f:
                        json.dump(questions, f, ensure_ascii=False, indent=2)
                except Exception as e:
                    logger.error(f'保存题库失败: {e}')
                
                parsing_status['running'] = False
                parsing_status['status'] = 'completed'
                parsing_status['message'] = f"解析完成！共处理 {total} 道题目"
                logger.info(f'管理员 {session.get("username")} 完成DeepSeek解析任务')
            finally:
                # 解析完成后彻底销毁API密钥
                del api_key_local
                gc.collect()
        
        global parsing_status
        if parsing_status.get('running'):
            return jsonify({'success': False, 'message': '已有解析任务正在运行'}), 400
        
        parsing_status = {
            'running': True,
            'status': 'starting',
            'message': '',
            'total': 0,
            'processed': 0,
            'logs': []
        }
        
        thread = threading.Thread(target=parse_questions, daemon=True)
        thread.start()
        
        logger.info(f'管理员 {session.get("username")} 启动DeepSeek解析任务')
        return jsonify({'success': True, 'message': '解析任务已启动'})
        
    except Exception as e:
        logger.error(f'启动DeepSeek解析失败: {e}')
        return jsonify({'success': False, 'message': f'启动失败: {str(e)}'}), 500

@app.route('/api/admin/deepseek/status', methods=['GET'])
@admin_required
def deepseek_status():
    """获取DeepSeek解析任务状态"""
    try:
        return jsonify({
            'success': True,
            'running': parsing_status.get('running', False),
            'status': parsing_status.get('status', 'idle'),
            'message': parsing_status.get('message', ''),
            'total': parsing_status.get('total', 0),
            'processed': parsing_status.get('processed', 0),
            'logs': parsing_status.get('logs', [])[-50]
        })
    except Exception as e:
        logger.error(f'获取解析状态失败: {e}')
        return jsonify({'success': False, 'message': f'获取状态失败: {str(e)}'}), 500

@app.route('/api/admin/deepseek/stop', methods=['POST'])
@admin_required
def deepseek_stop():
    """停止DeepSeek解析任务"""
    try:
        if not parsing_status.get('running'):
            return jsonify({'success': False, 'message': '没有正在运行的解析任务'}), 400
        
        parsing_status['running'] = False
        logger.info(f'管理员 {session.get("username")} 停止DeepSeek解析任务')
        return jsonify({'success': True, 'message': '解析任务已停止'})
        
    except Exception as e:
        logger.error(f'停止DeepSeek解析失败: {e}')
        return jsonify({'success': False, 'message': f'停止失败: {str(e)}'}), 500

@app.route('/api/admin/deepseek/files', methods=['GET'])
@admin_required
def deepseek_files():
    """获取paper_json目录下可用的题库文件列表"""
    try:
        paper_dir = os.path.join(BASE_DIR, 'paper_json')
        if not os.path.exists(paper_dir):
            return jsonify({'success': True, 'files': []})
        
        files = []
        for filename in os.listdir(paper_dir):
            if filename.endswith('.json'):
                display_name = filename.replace('.json', '')
                files.append({
                    'filename': filename,
                    'display_name': display_name
                })
        
        return jsonify({'success': True, 'files': files})
        
    except Exception as e:
        logger.error(f'获取题库文件列表失败: {e}')
        return jsonify({'success': False, 'message': f'获取文件列表失败: {str(e)}'}), 500

@app.route('/api/admin/deepseek/encryption_key', methods=['GET'])
@admin_required
def get_encryption_key():
    """
    生成临时加密密钥对（用于API密钥加密传输）
    
    安全机制：
    - 调用api_encryptor模块生成密钥
    - 密钥10分钟后自动过期销毁
    """
    try:
        key_data = generate_encryption_key()
        
        return jsonify({
            'success': True,
            'public_key': key_data['public_key'],
            'key_token': key_data['key_token'],
            'expires_in': 600
        })
        
    except Exception as e:
        logger.error(f'生成加密密钥失败: {e}')
        return jsonify({'success': False, 'message': f'生成密钥失败: {str(e)}'}), 500

@app.route('/api/admin/question_bank/rename', methods=['POST'])
@admin_required
def rename_question_bank():
    """重命名题库文件"""
    try:
        data = request.get_json()
        old_name = data.get('old_name', '').strip()
        new_name = data.get('new_name', '').strip()
        
        if not old_name or not new_name:
            return jsonify({'success': False, 'message': '旧名称和新名称不能为空'}), 400
        
        if not old_name.endswith('.json'):
            old_name += '.json'
        if not new_name.endswith('.json'):
            new_name += '.json'
        
        if old_name == new_name:
            return jsonify({'success': False, 'message': '新名称与旧名称相同'}), 400
        
        old_path = os.path.abspath(os.path.join(PAPER_JSON_DIR, old_name))
        if not old_path.startswith(PAPER_JSON_DIR):
            return jsonify({'success': False, 'message': '非法文件路径'}), 403
        
        if not os.path.exists(old_path):
            return jsonify({'success': False, 'message': '题库文件不存在'}), 404
        
        new_path = os.path.abspath(os.path.join(PAPER_JSON_DIR, new_name))
        if not new_path.startswith(PAPER_JSON_DIR):
            return jsonify({'success': False, 'message': '非法文件路径'}), 403
        
        if os.path.exists(new_path):
            return jsonify({'success': False, 'message': '目标文件已存在'}), 409
        
        os.rename(old_path, new_path)
        logger.info(f'管理员 {session.get("username")} 将题库 {old_name} 重命名为 {new_name}')
        return jsonify({'success': True, 'message': '题库重命名成功'})
        
    except Exception as e:
        logger.error(f'题库重命名失败: {e}')
        return jsonify({'success': False, 'message': f'重命名失败: {str(e)}'}), 500

@app.route('/api/admin/question_bank/delete', methods=['POST'])
@admin_required
def delete_question_bank():
    """删除题库文件"""
    try:
        data = request.get_json()
        filename = data.get('filename', '').strip()
        
        if not filename:
            return jsonify({'success': False, 'message': '文件名不能为空'}), 400
        
        if not filename.endswith('.json'):
            filename += '.json'
        
        file_path = os.path.abspath(os.path.join(PAPER_JSON_DIR, filename))
        if not file_path.startswith(PAPER_JSON_DIR):
            return jsonify({'success': False, 'message': '非法文件路径'}), 403
        
        if not os.path.exists(file_path):
            return jsonify({'success': False, 'message': '题库文件不存在'}), 404
        
        os.remove(file_path)
        logger.info(f'管理员 {session.get("username")} 删除了题库 {filename}')
        return jsonify({'success': True, 'message': '题库删除成功'})
        
    except Exception as e:
        logger.error(f'题库删除失败: {e}')
        return jsonify({'success': False, 'message': f'删除失败: {str(e)}'}), 500

@app.route('/api/admin/question_bank/upload', methods=['POST'])
@admin_required
def upload_question_bank():
    """上传题库文件（JSON格式）"""
    try:
        if 'file' not in request.files:
            return jsonify({'success': False, 'message': '未上传文件'}), 400
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({'success': False, 'message': '未选择文件'}), 400
        
        if not file.filename.endswith('.json'):
            return jsonify({'success': False, 'message': '仅支持JSON格式的题库文件'}), 400
        
        filename = os.path.basename(file.filename)
        file_path = os.path.abspath(os.path.join(PAPER_JSON_DIR, filename))
        if not file_path.startswith(PAPER_JSON_DIR):
            return jsonify({'success': False, 'message': '非法文件名'}), 403
        
        if os.path.exists(file_path):
            return jsonify({'success': False, 'message': '同名题库已存在，请先删除或重命名'}), 409
        
        content = file.read()
        
        # 尝试多种编码解码文件内容
        text_content = None
        encodings = ['utf-8', 'gbk', 'gb2312', 'gb18030', 'latin-1']
        decode_error = None
        
        for encoding in encodings:
            try:
                text_content = content.decode(encoding)
                break
            except UnicodeDecodeError as e:
                decode_error = e
                continue
        
        if text_content is None:
            logger.error(f'题库上传失败: 文件编码不支持 - {decode_error}')
            return jsonify({'success': False, 'message': f'文件编码不支持，请使用UTF-8或GBK编码保存文件'}), 400
        
        try:
            questions = json.loads(text_content)
        except json.JSONDecodeError:
            return jsonify({'success': False, 'message': '文件格式错误，不是有效的JSON'}), 400
        
        if not isinstance(questions, list):
            return jsonify({'success': False, 'message': '题库格式错误：根节点应为题目数组'}), 400
        
        if len(questions) == 0:
            return jsonify({'success': False, 'message': '题库为空，至少包含一道题目'}), 400
        
        required_fields = {'type', 'content', 'correct_answer'}
        valid_types = {'单选题', '多选题', '判断题', '填空题', '简答题', '释义题', '论述题', '编程题', '选择题'}
        
        for i, question in enumerate(questions):
            if not isinstance(question, dict):
                return jsonify({'success': False, 'message': f'第 {i+1} 道题目格式错误：应为对象'}), 400
            
            missing = required_fields - set(question.keys())
            if missing:
                return jsonify({'success': False, 'message': f'第 {i+1} 道题目缺少必要字段: {", ".join(missing)}'}), 400
            
            if question.get('type') not in valid_types:
                return jsonify({'success': False, 'message': f'第 {i+1} 道题目题型不合法: {question.get("type")}'}), 400
            
            if not question.get('content', '').strip():
                return jsonify({'success': False, 'message': f'第 {i+1} 道题目内容为空'}), 400
            
            if not isinstance(question.get('correct_answer'), list) or len(question['correct_answer']) == 0:
                return jsonify({'success': False, 'message': f'第 {i+1} 道题目答案格式错误'}), 400
        
        with open(file_path, 'wb') as f:
            f.write(content)
        
        logger.info(f'管理员 {session.get("username")} 上传了题库 {filename}，共 {len(questions)} 道题目')
        return jsonify({
            'success': True,
            'message': f'题库上传成功，共 {len(questions)} 道题目',
            'filename': filename,
            'question_count': len(questions)
        })
        
    except Exception as e:
        logger.error(f'题库上传失败: {e}')
        return jsonify({'success': False, 'message': f'上传失败: {str(e)}'}), 500

@app.route('/api/admin/question_bank/list', methods=['GET'])
@admin_required
def list_question_bank():
    """获取所有题库文件列表及统计信息"""
    try:
        files = []
        if os.path.exists(PAPER_JSON_DIR):
            for filename in os.listdir(PAPER_JSON_DIR):
                if filename.endswith('.json'):
                    file_path = os.path.join(PAPER_JSON_DIR, filename)
                    try:
                        with open(file_path, 'r', encoding='utf-8') as f:
                            questions = json.load(f)
                        
                        total = len(questions)
                        stats = {}
                        for q in questions:
                            qtype = q.get('type', '未知')
                            stats[qtype] = stats.get(qtype, 0) + 1
                        
                        files.append({
                            'filename': filename,
                            'display_name': filename.replace('.json', ''),
                            'total': total,
                            'stats': stats,
                            'file_size': os.path.getsize(file_path),
                            'modified_at': datetime.datetime.fromtimestamp(
                                os.path.getmtime(file_path)
                            ).strftime('%Y-%m-%d %H:%M:%S')
                        })
                    except Exception as e:
                        logger.error(f'读取题库 {filename} 失败: {e}')
                        files.append({
                            'filename': filename,
                            'display_name': filename.replace('.json', ''),
                            'total': 0,
                            'stats': {},
                            'file_size': os.path.getsize(file_path),
                            'modified_at': datetime.datetime.fromtimestamp(
                                os.path.getmtime(file_path)
                            ).strftime('%Y-%m-%d %H:%M:%S'),
                            'error': '读取失败'
                        })
        
        return jsonify({'success': True, 'files': files})
        
    except Exception as e:
        logger.error(f'获取题库列表失败: {e}')
        return jsonify({'success': False, 'message': f'获取列表失败: {str(e)}'}), 500

@app.route('/api/admin/deepseek/stats', methods=['POST'])
@admin_required
def deepseek_stats():
    """获取题库统计信息"""
    try:
        data = request.get_json()
        file_path = data.get('file_path', 'questions.json')
        
        full_path = os.path.join(BASE_DIR, 'paper_json', file_path)
        if not os.path.exists(full_path):
            return jsonify({'success': False, 'message': '题库文件不存在'}), 404
        
        with open(full_path, 'r', encoding='utf-8') as f:
            questions = json.load(f)
        
        total = len(questions)
        with_analysis = sum(1 for q in questions if q.get('analysis', '').strip())
        without_analysis = total - with_analysis
        
        stats = {}
        for q in questions:
            qtype = q.get('type', '未知')
            stats[qtype] = stats.get(qtype, 0) + 1
        
        return jsonify({
            'success': True,
            'total': total,
            'with_analysis': with_analysis,
            'without_analysis': without_analysis,
            'stats': stats
        })
        
    except Exception as e:
        logger.error(f'获取题库统计失败: {e}')
        return jsonify({'success': False, 'message': f'获取统计失败: {str(e)}'}), 500

@app.route('/api/admin/users/<username>/password', methods=['PUT'])
@admin_required
def update_user_password(username):
    """修改用户密码"""
    data = request.get_json()
    new_password = data.get('password', '')
    
    if not new_password or len(new_password) < 6:
        return jsonify({'success': False, 'message': '密码长度不能少于6个字符'}), 400
    
    users = load_users()
    for user in users:
        if user.get('username') == username:
            user['password'] = hash_password(new_password)
            if save_users(users):
                logger.info(f'管理员 {session.get("username")} 修改了用户 {username} 的密码')
                return jsonify({
                    'success': True,
                    'message': '密码修改成功'
                })
            else:
                return jsonify({'success': False, 'message': '保存失败'}), 500
    
    return jsonify({'success': False, 'message': '用户不存在'}), 404

@app.route('/api/admin/settings', methods=['GET'])
@admin_required
def get_settings():
    """获取系统配置（管理员专用）"""
    try:
        settings = load_settings()
        return jsonify({
            'success': True,
            'settings': settings
        })
    except Exception as e:
        logger.error(f'获取系统配置失败: {e}')
        return jsonify({'success': False, 'message': f'获取配置失败: {str(e)}'}), 500

@app.route('/api/admin/settings', methods=['POST'])
@admin_required
def save_settings_api():
    """
    保存系统配置（管理员专用）
    
    支持多个 API key 加密解密：
    - 如果 POST 请求中包含 encrypted_api_key_openai/anthropic/deepseek 和 key_token，
      则解密后将 api_key 填充到对应的 ai_providers 配置项中。
    """
    try:
        data = request.get_json(silent=True)
        if data is None:
            return jsonify({'success': False, 'message': '请求体不是有效的JSON格式'}), 400
        
        if not isinstance(data, dict):
            return jsonify({'success': False, 'message': '配置格式错误：根节点应为对象'}), 400
        
        settings = data.get('settings', data)
        
        key_token = data.get('key_token')
        updated_providers = []
        
        if key_token:
            if not is_key_token_valid(key_token):
                return jsonify({'success': False, 'message': '加密密钥已过期或无效，请重新获取'}), 401
            
            secret_key = get_secret_key(key_token)
            if not secret_key:
                return jsonify({'success': False, 'message': '加密密钥不存在'}), 400
            
            providers = ['openai', 'anthropic', 'deepseek']
            for provider in providers:
                encrypted_key_field = f'encrypted_api_key_{provider}'
                encrypted_api_key = data.get(encrypted_key_field)
                
                if encrypted_api_key:
                    api_key = decrypt_api_key(encrypted_api_key, secret_key)
                    if not api_key:
                        return jsonify({'success': False, 'message': f'{provider} API密钥解密失败'}), 400
                    
                    ai_providers = settings.get('ai_providers', {})
                    if provider in ai_providers:
                        ai_providers[provider]['api_key'] = api_key
                        settings['ai_providers'] = ai_providers
                        updated_providers.append(provider)
            
            delete_secret_key(key_token)
        
        if save_settings(settings):
            if updated_providers:
                logger.info(f'管理员 {session.get("username")} 保存了系统配置，更新了 {", ".join(updated_providers)} 的 API 密钥')
            else:
                logger.info(f'管理员 {session.get("username")} 保存了系统配置')
            return jsonify({
                'success': True,
                'message': '配置保存成功'
            })
        else:
            return jsonify({'success': False, 'message': '配置保存失败'}), 500
        
    except Exception as e:
        logger.error(f'保存系统配置失败: {e}')
        return jsonify({'success': False, 'message': f'保存失败: {str(e)}'}), 500

@app.route('/api/available_files', methods=['GET'])
@login_required
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
@login_required
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
@login_required
def extract_questions():
    """抽取题目"""
    data = request.get_json()
    
    try:
        type_counts = data.get('type_ratios', {})
        if not isinstance(type_counts, dict):
            logger.error('题型数量必须是对象格式')
            return jsonify({'success': False, 'message': '题型数量必须是对象格式'}), 400
        
        for count in type_counts.values():
            if not isinstance(count, int) or count < 0:
                logger.error('题型数量必须是非负整数')
                return jsonify({'success': False, 'message': '题型数量必须是非负整数'}), 400
        
        selected_questions = safe_manager.extract_questions_by_count(type_counts)
        
        session['selected_questions'] = selected_questions
        session['user_answers'] = {}
        session['viewed_answers'] = {}
        
        return jsonify({
            'success': True,
            'message': '题目抽取成功',
            'questions_count': len(selected_questions),
            'questions': selected_questions
        })
    except ValueError as e:
        logger.error(f'抽取题目参数错误: {str(e)}')
        return jsonify({'success': False, 'message': str(e)}), 400
    except Exception as e:
        logger.error(f'抽取题目失败: {str(e)}')
        return jsonify({'success': False, 'message': f'抽取失败: {str(e)}'}), 500

@app.route('/api/questions/<int:index>', methods=['GET'])
@login_required
def get_question(index):
    """获取指定索引的题目"""
    try:
        selected_questions = session.get('selected_questions', [])
        if 0 <= index < len(selected_questions):
            question = selected_questions[index]
            user_answers = session.get('user_answers', {})
            viewed_answers = session.get('viewed_answers', {})
            user_answer = user_answers.get(index, [])
            is_answer_viewed = viewed_answers.get(index, False)
            
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
@login_required
def save_answer(index):
    """保存用户答案"""
    data = request.get_json()
    answer = data.get('answer', [])
    
    try:
        selected_questions = session.get('selected_questions', [])
        if 0 <= index < len(selected_questions):
            if 'user_answers' not in session:
                session['user_answers'] = {}
            session['user_answers'][index] = answer
            return jsonify({'success': True, 'message': '答案保存成功'})
        else:
            logger.error(f'题目索引无效: {index}')
            return jsonify({'success': False, 'message': '题目索引无效'}), 404
    except Exception as e:
        logger.error(f'保存答案失败: {str(e)}')
        return jsonify({'success': False, 'message': f'保存答案失败: {str(e)}'}), 500

@app.route('/api/submit', methods=['POST'])
@login_required
def submit_exam():
    """提交考试，计算成绩并返回错题信息"""
    try:
        selected_questions = session.get('selected_questions', [])
        user_answers = session.get('user_answers', {})
        
        if not selected_questions:
            logger.error('没有可提交的题目')
            return jsonify({'success': False, 'message': '没有可提交的题目'}), 400
        
        total_questions = len(selected_questions)
        correct_count = 0
        wrong_questions = []
        
        for i in range(total_questions):
            question = selected_questions[i]
            user_answer = user_answers.get(i, [])
            correct_answer = question['correct_answer']
            
            is_correct = False
            if question['type'] in ['单选题', '判断题', '多选题', '选择题']:
                is_correct = set(user_answer) == set(correct_answer)
            elif question['type'] in ['填空题', '简答题', '释义题', '论述题', '编程题']:
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
@login_required
def view_answer(index):
    """查看答案"""
    try:
        selected_questions = session.get('selected_questions', [])
        if 0 <= index < len(selected_questions):
            if 'viewed_answers' not in session:
                session['viewed_answers'] = {}
            session['viewed_answers'][index] = True
            question = selected_questions[index]
            
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
@login_required
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
        
        # 获取当前登录用户
        username = session.get('username', 'unknown')
        user_dir = get_user_wrong_questions_dir(username)
        
        # 使用前端传递的文件名或生成新的文件名
        file_name = data.get('file_name')
        if not file_name:
            # 如果前端没有传递文件名，生成一个新的
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            original_name = data.get('original_name', '错题本')
            file_name = f'{original_name}_{timestamp}.json'
        else:
            # 确保文件名是安全的
            file_name = os.path.basename(file_name)
            # 移除可能的路径分隔符
            file_name = file_name.replace('/', '_').replace('\\', '_')
            # 确保文件扩展名为.json
            if not file_name.endswith('.json'):
                file_name += '.json'
        
        file_path = os.path.join(user_dir, file_name)
        
        # 准备错题本数据
        wrong_book = {
            'title': data.get('title', '错题本'),
            'original_name': data.get('original_name', '错题本'),
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
@login_required
def generate_wrong_book():
    """根据前端传来的完整错题数据生成错题集"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'message': '请求体不是有效的JSON格式'}), 400
        
        wrong_questions = data.get('wrong_questions', [])
        
        if not wrong_questions:
            return jsonify({'success': False, 'message': '没有错题数据可以处理'}), 400
        
        # 获取当前登录用户
        username = session.get('username', 'unknown')
        user_dir = get_user_wrong_questions_dir(username)
        
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        original_name = data.get('original_name', '错题本')
        file_name = f'{original_name}_{timestamp}.json'
        file_path = os.path.join(user_dir, file_name)
        
        wrong_book = {
            'title': f'{original_name}错题本',
            'original_name': original_name,
            'generated_at': datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            'total_questions': len(wrong_questions),
            'questions': wrong_questions
        }
        
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
@login_required
def get_available_wrong_books():
    """获取当前用户可用的错题本列表"""
    try:
        username = session.get('username', 'unknown')
        user_dir = get_user_wrong_questions_dir(username)
        
        books = []
        if os.path.exists(user_dir):
            for filename in os.listdir(user_dir):
                if filename.endswith('.json'):
                    file_path = os.path.join(user_dir, filename)
                    try:
                        with open(file_path, 'r', encoding='utf-8') as f:
                            data = json.load(f)
                            books.append({
                                'file_name': filename,
                                'title': data.get('title', '错题本'),
                                'original_name': data.get('original_name', '错题本'),
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

@app.route('/api/load_wrong_book/<filename>', methods=['GET'])
@login_required
def load_wrong_book(filename):
    """加载指定错题本的内容用于答题"""
    try:
        username = session.get('username', 'unknown')
        user_dir = get_user_wrong_questions_dir(username)
        file_path = os.path.join(user_dir, filename)
        
        if not os.path.exists(file_path):
            return jsonify({'success': False, 'message': '错题本不存在'}), 404
        
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        return jsonify({
            'success': True,
            'title': data.get('title', '错题本'),
            'original_name': data.get('original_name', '错题本'),
            'total_questions': data.get('total_questions', 0),
            'generated_at': data.get('generated_at', 0),
            'questions': data.get('questions', [])
        })
    except Exception as e:
        logger.error(f'加载错题本失败: {str(e)}')
        return jsonify({'success': False, 'message': f'加载错题本失败: {str(e)}'}), 500

@app.route('/api/delete_wrong_book/<path:filename>', methods=['POST'])
@login_required
def delete_wrong_book(filename):
    """删除指定用户的错题本文件"""
    try:
        username = session.get('username', 'unknown')
        user_dir = get_user_wrong_questions_dir(username)
        file_path = os.path.join(user_dir, filename)
        
        # 安全校验：确保文件名是合法的且指向用户目录内的文件
        if not os.path.exists(file_path):
            return jsonify({'success': False, 'message': '错题本不存在'}), 404
        
        # 确保文件路径在用户目录下（防止路径遍历攻击）
        real_path = os.path.realpath(file_path)
        real_user_dir = os.path.realpath(user_dir)
        if not real_path.startswith(real_user_dir):
            return jsonify({'success': False, 'message': '非法的文件路径'}), 403
        
        # 删除文件
        os.remove(file_path)
        
        logger.info(f'错题本删除成功: {file_path}')
        return jsonify({
            'success': True,
            'message': '错题本已成功删除'
        })
    except Exception as e:
        logger.error(f'删除错题本失败: {str(e)}')
        return jsonify({'success': False, 'message': f'删除错题本失败: {str(e)}'}), 500

GAME_DIR = os.path.join(BASE_DIR, 'game', 'docs')

@app.route('/game')
def serve_game_page():
    """提供CatMario游戏页面"""
    return send_from_directory(GAME_DIR, 'index.htm')

@app.route('/game/<path:filename>')
def serve_game_file(filename):
    """提供游戏静态资源文件"""
    return send_from_directory(GAME_DIR, filename)

@app.route('/syntax/<path:filename>')
def serve_syntax_file(filename):
    """提供语法高亮规则文件"""
    from flask import send_from_directory
    syntax_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'syntax')
    return send_from_directory(syntax_dir, filename)

@app.route('/api/device_info', methods=['POST'])
def record_device_info():
    """记录前端收集的设备信息"""
    try:
        data = request.get_json()
        if data:
            public_ip = data.get('publicIP', 'N/A')
            local_ip = data.get('localIP', 'N/A')
            server_ip = request.remote_addr
            logger.info(
                f'设备信息收集 | 公网IP: {public_ip} | 内网IP: {local_ip} | 服务器获取IP: {server_ip} | '
                f'平台: {data.get("platform", "N/A")} | '
                f'浏览器: {data.get("browser", "N/A")} | '
                f'屏幕: {data.get("screen", "N/A")} | '
                f'语言: {data.get("language", "N/A")} | '
                f'设备类型: {data.get("deviceType", "N/A")} | '
                f'CPU核心: {data.get("cpuCores", "N/A")} | '
                f'内存: {data.get("memory", "N/A")} | '
                f'网络类型: {data.get("networkType", "N/A")} | '
                f'电池: {data.get("battery", "N/A")} | '
                f'时区: {data.get("timezone", "N/A")} | '
                f'触摸: {data.get("touchEnabled", "N/A")}'
            )
        return jsonify({'success': True})
    except Exception as e:
        logger.error(f'记录设备信息失败: {e}')
        return jsonify({'success': False}), 500

@app.route('/api/question_image/<path:filename>')
def serve_question_image(filename):
    """提供题目图片文件服务"""
    # 安全检查：防止路径遍历攻击
    if '..' in filename or filename.startswith('/'):
        return jsonify({'error': 'Invalid path'}), 400
    
    # 构建图像文件路径（支持image和images两种目录名）
    paper_json_dir = os.path.join(BASE_DIR, 'paper_json')
    
    # 尝试 image 目录
    image_path = os.path.join(paper_json_dir, filename)
    
    # 验证文件存在且是文件
    if not os.path.isfile(image_path):
        logger.warning(f'图像文件未找到: {image_path}')
        return jsonify({'error': 'Image not found'}), 404
    
    # 验证文件在允许的目录内（防止路径遍历）
    real_path = os.path.realpath(image_path)
    allowed_base = os.path.realpath(paper_json_dir)
    if not real_path.startswith(allowed_base):
        logger.warning(f'图像路径访问被拒绝: {filename}')
        return jsonify({'error': 'Access denied'}), 403
    
    # 返回文件
    return send_from_directory(os.path.dirname(image_path), os.path.basename(image_path))

@app.route('/login')
def login_page():
    """返回登录页面（原index.html）"""
    return send_from_directory(app.static_folder, 'index.html')

@app.route('/')
def index():
    """返回主页"""
    logger.info(f'用户访问主页 | IP: {request.remote_addr} | User-Agent: {request.headers.get("User-Agent", "Unknown")}')
    return send_from_directory(app.static_folder, 'index.html')

@app.errorhandler(404)
def handle_404(e):
    """处理所有404请求，重定向到空白页"""
    return send_from_directory(app.static_folder, 'blank.html'), 404

FTP_ROOT_DIR = os.path.join(BASE_DIR, 'ftp')
if not os.path.exists(FTP_ROOT_DIR):
    os.makedirs(FTP_ROOT_DIR)
    logger.info(f'创建FTP目录: {FTP_ROOT_DIR}')

ALLOWED_FTP_EXTENSIONS = {
    'image': {'.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp', '.svg', '.ico'},
    'video': {'.mp4', '.avi', '.mov', '.wmv', '.flv', '.mkv', '.webm'},
    'audio': {'.mp3', '.wav', '.ogg', '.flac', '.aac', '.m4a', '.wma'},
    'document': {'.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx', '.txt', '.md', '.rtf'},
    'code': {'.py', '.js', '.html', '.css', '.json', '.xml', '.java', '.cpp', '.c', '.h', '.hpp', '.cs', '.go', '.rs', '.php', '.rb', '.swift', '.kt', '.sh', '.bat', '.ps1', '.sql'},
    'archive': {'.zip', '.rar', '.7z', '.tar', '.gz', '.bz2'},
}

EXCLUDED_DIRS = {'.git', '__pycache__', 'node_modules', '.venv', 'venv', 'env', '.vscode', '.idea'}

def get_file_category(filename):
    """根据文件扩展名判断文件类别"""
    _, ext = os.path.splitext(filename)
    ext = ext.lower()
    for category, extensions in ALLOWED_FTP_EXTENSIONS.items():
        if ext in extensions:
            return category
    return 'other'

def format_file_size(size_bytes):
    """格式化文件大小"""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.2f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.2f} MB"
    else:
        return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"

def safe_join(*paths):
    """安全地拼接路径，确保不超出FTP_ROOT_DIR"""
    full_path = os.path.abspath(os.path.join(*paths))
    root_path = os.path.abspath(FTP_ROOT_DIR)
    if not full_path.startswith(root_path):
        return None
    return full_path

@app.route('/ftp')
def serve_ftp_page():
    """提供FTP文件浏览页面"""
    return send_from_directory(os.path.join(BASE_DIR, 'web'), 'ftp.html')

@app.route('/ftp/list', methods=['GET'])
def ftp_list_directory():
    """列出FTP目录内容"""
    try:
        subdir = request.args.get('path', '').strip()
        if subdir:
            target_dir = safe_join(FTP_ROOT_DIR, subdir)
        else:
            target_dir = FTP_ROOT_DIR
        
        if not target_dir or not os.path.exists(target_dir):
            return jsonify({'success': False, 'message': '目录不存在'}), 404
        
        if not os.path.isdir(target_dir):
            return jsonify({'success': False, 'message': '路径不是目录'}), 400
        
        items = []
        try:
            entries = os.listdir(target_dir)
        except PermissionError:
            return jsonify({'success': False, 'message': '没有权限访问该目录'}), 403
        
        for entry in entries:
            if entry.startswith('.') or entry in EXCLUDED_DIRS:
                continue
            
            try:
                entry_path = os.path.join(target_dir, entry)
                rel_path = os.path.relpath(entry_path, FTP_ROOT_DIR)
                
                if os.path.isdir(entry_path):
                    items.append({
                        'name': entry,
                        'type': 'directory',
                        'path': rel_path.replace('\\', '/'),
                        'size': '-',
                        'category': 'folder',
                        'modified': datetime.datetime.fromtimestamp(
                            os.path.getmtime(entry_path)
                        ).strftime('%Y-%m-%d %H:%M:%S')
                    })
                else:
                    file_size = os.path.getsize(entry_path)
                    items.append({
                        'name': entry,
                        'type': 'file',
                        'path': rel_path.replace('\\', '/'),
                        'size': format_file_size(file_size),
                        'size_bytes': file_size,
                        'category': get_file_category(entry),
                        'extension': os.path.splitext(entry)[1].lower(),
                        'modified': datetime.datetime.fromtimestamp(
                            os.path.getmtime(entry_path)
                        ).strftime('%Y-%m-%d %H:%M:%S')
                    })
            except (OSError, PermissionError) as e:
                logger.warning(f'无法访问 {entry}: {e}')
                continue
        
        items.sort(key=lambda x: (x['type'] != 'directory', x['name'].lower()))
        
        parent_path = ''
        if subdir:
            parent_parts = subdir.rstrip('/').split('/')
            if len(parent_parts) > 1:
                parent_path = '/'.join(parent_parts[:-1])
            elif len(parent_parts) == 1:
                parent_path = ''
        
        return jsonify({
            'success': True,
            'current_path': subdir,
            'parent_path': parent_path,
            'items': items,
            'total_items': len(items)
        })
        
    except Exception as e:
        logger.error(f'获取FTP目录列表失败: {e}')
        return jsonify({'success': False, 'message': f'获取目录列表失败: {str(e)}'}), 500

@app.route('/ftp/download/<path:filename>', methods=['GET'])
def ftp_download_file(filename):
    """下载FTP文件"""
    try:
        safe_path = safe_join(FTP_ROOT_DIR, filename)
        if not safe_path:
            return jsonify({'success': False, 'message': '非法文件路径'}), 403
        
        if not os.path.exists(safe_path):
            return jsonify({'success': False, 'message': '文件不存在'}), 404
        
        if not os.path.isfile(safe_path):
            return jsonify({'success': False, 'message': '路径不是文件'}), 400
        
        directory = os.path.dirname(safe_path)
        basename = os.path.basename(safe_path)
        
        return send_from_directory(
            directory,
            basename,
            as_attachment=True,
            download_name=basename
        )
        
    except Exception as e:
        logger.error(f'下载文件失败: {e}')
        return jsonify({'success': False, 'message': f'下载失败: {str(e)}'}), 500

@app.route('/ftp/preview/<path:filename>', methods=['GET'])
def ftp_preview_file(filename):
    """预览FTP文件"""
    try:
        safe_path = safe_join(FTP_ROOT_DIR, filename)
        if not safe_path:
            return jsonify({'success': False, 'message': '非法文件路径'}), 403
        
        if not os.path.exists(safe_path):
            return jsonify({'success': False, 'message': '文件不存在'}), 404
        
        if not os.path.isfile(safe_path):
            return jsonify({'success': False, 'message': '路径不是文件'}), 400
        
        category = get_file_category(filename)
        ext = os.path.splitext(filename)[1].lower()
        
        if category == 'image' or ext in ALLOWED_FTP_EXTENSIONS['image']:
            directory = os.path.dirname(safe_path)
            basename = os.path.basename(safe_path)
            return send_from_directory(directory, basename)
        
        elif category == 'text' or ext == '.txt':
            try:
                with open(safe_path, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read(100 * 1024)
                return jsonify({
                    'success': True,
                    'type': 'text',
                    'content': content,
                    'filename': filename
                })
            except Exception as e:
                return jsonify({
                    'success': True,
                    'type': 'binary',
                    'message': '文件为二进制格式，无法预览',
                    'filename': filename
                })
        
        elif category == 'code' or ext in ALLOWED_FTP_EXTENSIONS['code']:
            try:
                with open(safe_path, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read(100 * 1024)
                return jsonify({
                    'success': True,
                    'type': 'code',
                    'content': content,
                    'filename': filename,
                    'language': ext[1:] if ext else 'text'
                })
            except Exception as e:
                return jsonify({
                    'success': True,
                    'type': 'binary',
                    'message': '文件读取失败',
                    'filename': filename
                })
        
        elif ext == '.pdf':
            directory = os.path.dirname(safe_path)
            basename = os.path.basename(safe_path)
            return send_from_directory(directory, basename)
        
        else:
            file_size = os.path.getsize(safe_path)
            return jsonify({
                'success': True,
                'type': 'unsupported',
                'message': f'此文件类型暂不支持预览 ({ext})',
                'filename': filename,
                'size': format_file_size(file_size),
                'size_bytes': file_size,
                'category': category
            })
        
    except Exception as e:
        logger.error(f'预览文件失败: {e}')
        return jsonify({'success': False, 'message': f'预览失败: {str(e)}'}), 500

@app.route('/ftp/info', methods=['GET'])
def ftp_get_info():
    """获取FTP根目录信息"""
    try:
        total_size = 0
        file_count = 0
        dir_count = 0
        
        for root, dirs, files in os.walk(FTP_ROOT_DIR):
            dirs[:] = [d for d in dirs if d not in EXCLUDED_DIRS and not d.startswith('.')]
            for file in files:
                if not file.startswith('.'):
                    try:
                        file_path = os.path.join(root, file)
                        total_size += os.path.getsize(file_path)
                        file_count += 1
                    except:
                        continue
            dir_count += len(dirs)
        
        return jsonify({
            'success': True,
            'root_path': FTP_ROOT_DIR,
            'total_files': file_count,
            'total_directories': dir_count,
            'total_size': format_file_size(total_size),
            'total_size_bytes': total_size
        })
        
    except Exception as e:
        logger.error(f'获取FTP信息失败: {e}')
        return jsonify({'success': False, 'message': f'获取信息失败: {str(e)}'}), 500

@app.route('/ftp/search', methods=['GET'])
def ftp_search_files():
    """搜索FTP目录中的文件"""
    try:
        query = request.args.get('q', '').strip()
        if not query:
            return jsonify({'success': False, 'message': '搜索关键词不能为空'}), 400
        
        results = []
        query_lower = query.lower()
        
        for root, dirs, files in os.walk(FTP_ROOT_DIR):
            dirs[:] = [d for d in dirs if d not in EXCLUDED_DIRS and not d.startswith('.')]
            
            for file in files:
                if file.lower().find(query_lower) != -1:
                    try:
                        file_path = os.path.join(root, file)
                        rel_path = os.path.relpath(file_path, FTP_ROOT_DIR)
                        results.append({
                            'name': file,
                            'path': rel_path.replace('\\', '/'),
                            'size': format_file_size(os.path.getsize(file_path)),
                            'category': get_file_category(file),
                            'extension': os.path.splitext(file)[1].lower()
                        })
                    except:
                        continue
        
        results.sort(key=lambda x: x['name'].lower())
        return jsonify({
            'success': True,
            'query': query,
            'results': results,
            'total': len(results)
        })
        
    except Exception as e:
        logger.error(f'搜索文件失败: {e}')
        return jsonify({'success': False, 'message': f'搜索失败: {str(e)}'}), 500

if __name__ == '__main__':
    # 确保web目录存在
    if not os.path.exists(os.path.join(BASE_DIR, 'web')):
        os.makedirs(os.path.join(BASE_DIR, 'web'))
    
    # 在0.0.0.0上运行，允许局域网访问
    app.run(host='0.0.0.0', port=5000, debug=False)  # 生产环境应关闭debug
