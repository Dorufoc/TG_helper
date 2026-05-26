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
import time
import platform
import re
import logging.handlers
from typing import Optional
from functools import wraps
from queue import Queue
from flask import Flask, request, jsonify, send_from_directory, session, Response, stream_with_context
from flask_cors import CORS
from werkzeug.security import safe_join as werkzeug_safe_join
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from api_encryptor import (
    decrypt_api_key, generate_encryption_key, get_secret_key, delete_secret_key, is_key_token_valid,
    get_current_key_pair, rotate_key_pair, encrypt_api_key, load_key_pair, save_key_pair
)
from rag_module import (
    create_rag_system, KnowledgeBase, Document, Chunk,
    RAGDatabase, KnowledgeBaseManager, DocumentProcessor, VectorRetriever, RAGChat,
    DocumentParser, TextSplitter, EmbeddingClient
)
from user_database import (
    get_user_db, load_users, verify_user, save_users
)
from file_router import (
    create_file_router, FileRouter, FilePermission,
    FileRouterConfig, FileRouterError, PermissionDeniedError,
    PathNotAllowedError, FileNotFoundError as FileRouterNotFoundError
)
from file_trash_manager import TrashManager, create_trash_manager
from file_audit_logger import get_file_audit_logger

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

# 会话注册表：维护活跃会话的 SSE 队列
# 格式: {session_id: Queue}
sse_queues = {}
sse_lock = threading.Lock()

# 登录限流：记录登录尝试 {ip: [(timestamp, count)]}
login_attempts = {}
login_attempts_lock = threading.Lock()
LOGIN_MAX_ATTEMPTS = 5
LOGIN_WINDOW_SECONDS = 300  # 5分钟窗口

def _notify_session_invalidated(username, reason):
    """通过SSE队列通知所有该用户的会话已失效"""
    with sse_lock:
        for sid, queue in list(sse_queues.items()):
            if sid.startswith(username + ':'):
                try:
                    queue.put_nowait({
                        'event': 'session_invalidated',
                        'data': json.dumps({
                            'reason': reason,
                            'message': f'会话已失效: {reason}',
                            'timestamp': datetime.datetime.now().isoformat()
                        })
                    })
                except:
                    pass

def _check_login_rate_limit(ip):
    """检查IP的登录频率限制，返回(是否允许, 剩余等待秒数)"""
    now = time.time()
    with login_attempts_lock:
        # 清理过期记录
        if ip in login_attempts:
            login_attempts[ip] = [
                (t, c) for t, c in login_attempts[ip]
                if now - t < LOGIN_WINDOW_SECONDS
            ]
        
        attempts = login_attempts.get(ip, [])
        total = sum(c for _, c in attempts)
        
        if total >= LOGIN_MAX_ATTEMPTS:
            # 计算需要等待的时间
            oldest = min(t for t, _ in attempts)
            wait_seconds = LOGIN_WINDOW_SECONDS - (now - oldest)
            return False, max(1, int(wait_seconds))
        
        return True, 0

def _record_login_attempt(ip, success=False):
    """记录登录尝试"""
    now = time.time()
    with login_attempts_lock:
        if ip not in login_attempts:
            login_attempts[ip] = []
        login_attempts[ip].append((now, 1 if not success else 0))
        
        # 清理过旧的记录
        login_attempts[ip] = [
            (t, c) for t, c in login_attempts[ip]
            if now - t < LOGIN_WINDOW_SECONDS
        ]

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

# 系统配置文件路径
SETTINGS_FILE = os.path.join(BASE_DIR, 'settings.json')

# AI提供商常量
AI_PROVIDER_NAMES = ('openai', 'anthropic', 'deepseek')
QUESTION_ANALYSIS_AGENT_KEY = 'question_analysis'

# 默认题目解析Agent提示词
DEFAULT_QUESTION_ANALYSIS_PROMPT = """# Role
你是一个顶级全科教育专家与智能助教 Agent。你的核心任务是针对各类题目（选择、填空、主观、代码、计算推理等），生成极简、专业、易懂的答案解析。

# Evaluation Criteria
1. 极致精炼：剔除所有大话、空话和过度修饰，单句尽量不超过 15 字，直奔主题。
2. 语言通俗：用最简单的日常语言解释复杂概念，降低读者的认知负荷。
3. 规范专业：术语使用必须严谨、标准，格式必须统一。

# Workflow By Task Types

## 1. 单项/多项选择题
- 【核心答案】直接给出正确选项（例：**正确答案：A** 或 **正确答案：A、C**）。
- 【选项剖析】逐一拆解所有选项。先说该选项对/错在哪里，再指出其背后的核心考点。
  - 格式：
    - A. [正确/错误] + [精炼原因]（考点：xxx）
    - B. [正确/错误] + [精炼原因]（考点：xxx）

## 2. 代码/编程题
- 【标准源码】提供排版整洁、自带核心注释的正确代码块。
- 【逐行解析】严禁概括。必须对代码进行逐行（或紧密代码块）说明。
  - 格式：
    - `第 X 行`：该行代码的具体功能与变量变化。
- 【算法核心】用一句话总结该算法的时间复杂度和空间复杂度。

## 3. 逻辑推理与计算题
- 【最终结果】开门见山给出最终数值或推论结论。
- 【步步为营】将解题过程拆解为不可分割的微小步骤。
  - 格式：
    - 步骤 1：[已知条件转化/第一步计算]
    - 步骤 2：[公式带入/核心推理]
    - 步骤 3：[最终推导]

## 4. 普通主观题/其他题型
- 【参考答案】给出标准、规范的得分点文本。
- 【核心考点】一句话指出本题考察的知识模块。
- 【答题思路】用 2-3 个核心要点（Bullet Points）阐述如何从题目联想到答案。

# Output Constraints
- 严禁任何自我介绍、寒暄或总结性套话。
- 必须严格使用 Markdown 标题、加粗和列表进行视觉锚定。
- 遇到公式必须使用 LaTeX 格式。
- 每一个分析步骤或选项解析，务必做到"一句话讲透"。"""

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
            "reasoning_effort": "high",
            "max_tokens": 4096
        }
    },
    "ai_agents": {
        QUESTION_ANALYSIS_AGENT_KEY: {
            "name": "题目解析 Agent",
            "provider": "deepseek",
            "model_id": "",
            "temperature": 0.7,
            "max_tokens": 500,
            "system_prompt": DEFAULT_QUESTION_ANALYSIS_PROMPT
        }
    }
}


def decrypt_api_key_for_reencryption(encrypted_data: str, old_private_key_pem: str) -> Optional[str]:
    """使用旧私钥解密（用于转码场景）"""
    return decrypt_api_key(encrypted_data, use_private_key=old_private_key_pem)


def reencrypt_api_key(plaintext: str, new_public_key_pem: str) -> Optional[str]:
    """使用新公钥重新加密（用于转码场景）"""
    return encrypt_api_key(plaintext, use_public_key=new_public_key_pem)


def reencrypt_settings_keys(settings: dict, old_private_key: str, new_public_key: str) -> dict:
    """
    对settings中所有加密的API密钥进行转码
    
    Args:
        settings: 系统配置字典
        old_private_key: 旧私钥PEM
        new_public_key: 新公钥PEM
    
    Returns:
        转码后的settings字典
    """
    import copy
    new_settings = copy.deepcopy(settings)
    
    ai_providers = new_settings.get('ai_providers', {})
    for provider in AI_PROVIDER_NAMES:
        provider_data = ai_providers.get(provider, {})
        encrypted_key = provider_data.get('api_key', '')
        
        # 如果api_key存在且非空，则进行转码
        if encrypted_key and encrypted_key.strip():
            # 用旧私钥解密
            decrypted_key = decrypt_api_key_for_reencryption(encrypted_key, old_private_key)
            if decrypted_key:
                # 用新公钥重新加密
                reencrypted_key = reencrypt_api_key(decrypted_key, new_public_key)
                if reencrypted_key:
                    ai_providers[provider]['api_key'] = reencrypted_key
                    logger.info(f"API密钥转码成功: provider={provider}")
                else:
                    logger.warning(f"API密钥转码失败（重新加密失败）: provider={provider}")
            else:
                logger.warning(f"API密钥转码失败（解密失败）: provider={provider}")
    
    new_settings['ai_providers'] = ai_providers
    return new_settings


def rotate_encryption_keys(reencrypt_existing: bool = True) -> dict:
    """
    轮换加密密钥对
    
    Args:
        reencrypt_existing: 是否重新加密现有的API密钥
    
    Returns:
        包含操作结果的字典
    """
    # 加载旧密钥对
    old_key_pair = load_key_pair()
    if not old_key_pair or not old_key_pair.get('private_key'):
        return {
            'success': False,
            'message': '当前无可用密钥对，无法轮换'
        }
    
    old_private_key = old_key_pair['private_key']
    old_key_id = old_key_pair.get('key_id', 'unknown')
    
    # 生成并保存新密钥对
    new_key_pair = rotate_key_pair()
    new_public_key = new_key_pair['public_key']
    new_key_id = new_key_pair.get('key_id', 'unknown')
    
    reencrypted_count = 0
    if reencrypt_existing:
        # 加载现有settings
        settings = load_settings()
        
        # 对现有加密密钥进行转码
        new_settings = reencrypt_settings_keys(settings, old_private_key, new_public_key)
        
        # 保存转码后的settings
        if save_settings(new_settings):
            # 统计转码的密钥数量
            for provider in AI_PROVIDER_NAMES:
                key = new_settings.get('ai_providers', {}).get(provider, {}).get('api_key', '')
                if key and key.strip():
                    reencrypted_count += 1
        else:
            logger.error("转码后保存settings失败")
    
    logger.info(
        f"密钥对轮换完成: 旧key_id={old_key_id}, 新key_id={new_key_id}, "
        f"转码密钥数={reencrypted_count}"
    )
    
    return {
        'success': True,
        'message': '密钥对轮换成功',
        'old_key_id': old_key_id,
        'new_key_id': new_key_id,
        'reencrypted_count': reencrypted_count
    }


def merge_settings(defaults, current):
    """递归合并设置，保留已有值并补全默认值"""
    if not isinstance(defaults, dict):
        return current if current is not None else defaults

    merged = {}
    current = current if isinstance(current, dict) else {}
    for key, default_value in defaults.items():
        current_value = current.get(key)
        if isinstance(default_value, dict):
            merged[key] = merge_settings(default_value, current_value)
        else:
            merged[key] = current_value if current_value is not None else default_value

    for key, value in current.items():
        if key not in merged:
            merged[key] = value
    return merged


def normalize_settings(settings):
    """规范化系统配置结构"""
    normalized = merge_settings(DEFAULT_SETTINGS, settings or {})

    account = normalized.get('account', {})
    try:
        timeout = int(account.get('auth_timeout_minutes', 1))
    except (TypeError, ValueError):
        timeout = 1
    account['auth_timeout_minutes'] = max(1, timeout)
    if account.get('default_role') not in ('guest', 'user'):
        account['default_role'] = 'guest'
    normalized['account'] = account

    ai_providers = normalized.get('ai_providers', {})
    for provider in AI_PROVIDER_NAMES:
        provider_settings = ai_providers.get(provider, {})
        if provider == 'deepseek':
            if provider_settings.get('api_format') not in ('openai', 'anthropic'):
                provider_settings['api_format'] = 'openai'
            if provider_settings.get('thinking') not in ('enabled', 'disabled'):
                provider_settings['thinking'] = 'enabled'
            if provider_settings.get('reasoning_effort') not in ('low', 'medium', 'high'):
                provider_settings['reasoning_effort'] = 'high'
        if provider != 'deepseek' or provider_settings.get('max_tokens') is not None:
            try:
                provider_settings['max_tokens'] = max(1, int(provider_settings.get('max_tokens', 4096)))
            except (TypeError, ValueError):
                provider_settings['max_tokens'] = 4096
        ai_providers[provider] = provider_settings
    normalized['ai_providers'] = ai_providers

    ai_agents = normalized.get('ai_agents', {})
    analysis_agent = ai_agents.get(QUESTION_ANALYSIS_AGENT_KEY, {})
    if analysis_agent.get('provider') not in AI_PROVIDER_NAMES:
        analysis_agent['provider'] = 'deepseek'
    try:
        analysis_agent['temperature'] = float(analysis_agent.get('temperature', 0.7))
    except (TypeError, ValueError):
        analysis_agent['temperature'] = 0.7
    analysis_agent['temperature'] = min(max(analysis_agent['temperature'], 0), 2)
    try:
        analysis_agent['max_tokens'] = max(1, int(analysis_agent.get('max_tokens', 500)))
    except (TypeError, ValueError):
        analysis_agent['max_tokens'] = 500
    if not str(analysis_agent.get('system_prompt', '')).strip():
        analysis_agent['system_prompt'] = DEFAULT_QUESTION_ANALYSIS_PROMPT
    ai_agents[QUESTION_ANALYSIS_AGENT_KEY] = analysis_agent
    normalized['ai_agents'] = ai_agents

    return normalized


def get_public_settings(settings):
    """返回可安全下发到前端的系统配置"""
    public_settings = deep_copy_json_compatible(normalize_settings(settings))
    for provider_name in AI_PROVIDER_NAMES:
        if provider_name in public_settings.get('ai_providers', {}):
            public_settings['ai_providers'][provider_name]['api_key'] = ''
    return public_settings


def build_openai_chat_url(base_url):
    """
    构建OpenAI兼容接口URL，智能识别各种基础URL格式

    支持的输入格式：
    - https://api.openai.com
    - https://api.openai.com/
    - https://api.openai.com/v1
    - https://api.openai.com/v1/
    - https://token.sensenova.cn/v1/chat/completions
    - https://token.sensenova.cn/v1/chat/completions/
    - https://api.example.com/api/v1/chat
    - https://api.example.com/openai/v1/chat/completions

    返回格式：确保以 /v1/chat/completions 结尾的完整URL
    """
    base = (base_url or 'https://api.openai.com').rstrip('/')
    if not base:
        base = 'https://api.openai.com'

    lower_base = base.lower()

    # 如果已经包含完整的 /v1/chat/completions，直接返回
    if '/v1/chat/completions' in lower_base:
        return base

    # 如果以 /chat/completions 结尾（缺少 /v1），在前面补 /v1
    if lower_base.endswith('/chat/completions'):
        return base

    # 如果以 /v1/chat 结尾，补 /completions
    if lower_base.endswith('/v1/chat'):
        return f'{base}/completions'

    # 如果以 /v1 结尾，补 /chat/completions
    if lower_base.endswith('/v1'):
        return f'{base}/chat/completions'

    # 其他情况，追加 /v1/chat/completions
    return f'{base}/v1/chat/completions'


def build_anthropic_messages_url(base_url):
    """
    构建Anthropic消息接口URL，智能识别各种基础URL格式

    支持的输入格式：
    - https://api.anthropic.com
    - https://api.anthropic.com/v1
    - https://api.anthropic.com/v1/messages

    返回格式：确保以 /v1/messages 结尾的完整URL
    """
    base = (base_url or 'https://api.anthropic.com').rstrip('/')
    if not base:
        base = 'https://api.anthropic.com'

    lower_base = base.lower()

    # 如果已经包含完整的 /v1/messages，直接返回
    if '/v1/messages' in lower_base:
        return base

    # 如果以 /messages 结尾（缺少 /v1），在前面补 /v1
    if lower_base.endswith('/messages'):
        return base

    # 如果以 /v1 结尾，补 /messages
    if lower_base.endswith('/v1'):
        return f'{base}/messages'

    # 其他情况，追加 /v1/messages
    return f'{base}/v1/messages'


def invoke_ai_completion(provider_name, provider_settings, agent_settings, api_key, system_prompt, user_message):
    """按提供商配置调用AI补全接口"""
    import requests

    model_id = str(agent_settings.get('model_id') or provider_settings.get('model_id') or '').strip()
    if not model_id:
        raise ValueError('未配置模型ID')

    temperature = agent_settings.get('temperature', 0.7)
    max_tokens = agent_settings.get('max_tokens') or provider_settings.get('max_tokens') or 500

    if provider_name == 'anthropic' or (
        provider_name == 'deepseek' and provider_settings.get('api_format') == 'anthropic'
    ):
        url = build_anthropic_messages_url(provider_settings.get('base_url'))
        headers = {
            'x-api-key': api_key,
            'anthropic-version': '2023-06-01',
            'content-type': 'application/json'
        }
        payload = {
            'model': model_id,
            'system': system_prompt,
            'messages': [{'role': 'user', 'content': user_message}],
            'temperature': temperature,
            'max_tokens': max_tokens
        }
        response = requests.post(url, headers=headers, json=payload, timeout=60)
        response.raise_for_status()
        result = response.json()
        content_blocks = result.get('content', [])
        text_parts = [
            block.get('text', '')
            for block in content_blocks
            if isinstance(block, dict) and block.get('type') == 'text'
        ]
        return '\n'.join(part for part in text_parts if part).strip()

    url = build_openai_chat_url(provider_settings.get('base_url'))
    headers = {
        'Authorization': f'Bearer {api_key}',
        'Content-Type': 'application/json'
    }
    payload = {
        'model': model_id,
        'messages': [
            {'role': 'system', 'content': system_prompt},
            {'role': 'user', 'content': user_message}
        ],
        'temperature': temperature,
        'max_tokens': max_tokens
    }
    if provider_name == 'deepseek':
        payload['thinking'] = provider_settings.get('thinking', 'enabled')
        payload['reasoning_effort'] = provider_settings.get('reasoning_effort', 'high')
    response = requests.post(url, headers=headers, json=payload, timeout=60)
    response.raise_for_status()
    result = response.json()
    return result.get('choices', [{}])[0].get('message', {}).get('content', '').strip()


def deep_copy_json_compatible(data):
    """深拷贝JSON兼容对象"""
    return json.loads(json.dumps(data))


def generate_invitation_code():
    """生成随机邀请码"""
    chars = string.ascii_uppercase + string.digits
    code = ''.join(random.choices(chars, k=8))
    return code



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
                settings = normalize_settings(json.load(f))
            logger.info('系统配置加载成功')
            return settings
        else:
            # 配置文件不存在，使用默认配置并创建文件
            logger.info('系统配置文件不存在，使用默认配置')
            save_settings(DEFAULT_SETTINGS)
            return deep_copy_json_compatible(DEFAULT_SETTINGS)
    except json.JSONDecodeError as e:
        logger.error(f"系统配置文件格式错误: {e}，使用默认配置")
        return deep_copy_json_compatible(DEFAULT_SETTINGS)
    except Exception as e:
        logger.error(f"加载系统配置文件失败: {e}")
        return deep_copy_json_compatible(DEFAULT_SETTINGS)

def save_settings(settings):
    """
    保存系统配置文件
    
    Args:
        settings (dict): 要保存的配置字典
    
    Returns:
        bool: 保存成功返回 True，否则返回 False
    """
    try:
        settings = normalize_settings(settings)
        with open(SETTINGS_FILE, 'w', encoding='utf-8') as f:
            json.dump(settings, f, ensure_ascii=False, indent=2)
        logger.info('系统配置保存成功')
        return True
    except Exception as e:
        logger.error(f"保存系统配置文件失败: {e}")
        return False

def hash_password(password):
    """密码哈希 - 使用PBKDF2安全哈希"""
    from werkzeug.security import generate_password_hash
    return generate_password_hash(password, method='pbkdf2:sha256', salt_length=16)

import math

def generate_captcha_code(length=5):
    """生成随机验证码字符串（数字+大小写字母，排除易混淆字符）"""
    # 排除易混淆字符：0/O, 1/I/l
    chars = '23456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz'
    return ''.join(random.choices(chars, k=length))

def _generate_gradient_background(draw, width, height):
    """生成渐变背景"""
    # 随机选择背景色系
    base_hue = random.randint(0, 360)
    for y in range(height):
        r = int(200 + 30 * math.sin(base_hue + y * 0.1))
        g = int(200 + 30 * math.sin(base_hue + 120 + y * 0.1))
        b = int(200 + 30 * math.sin(base_hue + 240 + y * 0.1))
        draw.line([(0, y), (width, y)], fill=(r % 256, g % 256, b % 256))

def _apply_wave_distortion(image, amplitude=3, frequency=2):
    """应用波浪扭曲效果，破坏OCR字符分割"""
    width, height = image.size
    distorted = Image.new('RGBA', (width, height), (255, 255, 255, 0))
    
    for y in range(height):
        for x in range(width):
            offset_x = int(amplitude * math.sin(frequency * math.pi * y / height))
            offset_y = int(amplitude * math.cos(frequency * math.pi * x / width))
            
            src_x = x - offset_x
            src_y = y - offset_y
            
            if 0 <= src_x < width and 0 <= src_y < height:
                pixel = image.getpixel((src_x, src_y))
                distorted.putpixel((x, y), pixel)
    
    return distorted

def _apply_radial_distortion(image, center_x=None, center_y=None, strength=3):
    """应用径向扭曲效果，从中心向外产生鱼眼/桶形畸变"""
    width, height = image.size
    if center_x is None:
        center_x = width // 2
    if center_y is None:
        center_y = height // 2
    
    distorted = Image.new('RGBA', (width, height), (255, 255, 255, 0))
    max_dist = math.sqrt(center_x ** 2 + center_y ** 2)
    
    for y in range(height):
        for x in range(width):
            dx = x - center_x
            dy = y - center_y
            dist = math.sqrt(dx ** 2 + dy ** 2)
            
            if dist == 0:
                distorted.putpixel((x, y), image.getpixel((x, y)))
                continue
            
            # 归一化距离
            norm_dist = dist / max_dist
            
            # 桶形畸变公式：偏移量与距离的平方成正比
            distortion_factor = 1.0 - strength * (norm_dist ** 2)
            
            src_x = int(center_x + dx * distortion_factor)
            src_y = int(center_y + dy * distortion_factor)
            
            if 0 <= src_x < width and 0 <= src_y < height:
                pixel = image.getpixel((src_x, src_y))
                distorted.putpixel((x, y), pixel)
            else:
                distorted.putpixel((x, y), (255, 255, 255, 0))
    
    return distorted

def _draw_curve_interference(draw, width, height, num_curves=4):
    """绘制贝塞尔曲线干扰，替代简单的直线干扰"""
    for _ in range(num_curves):
        # 随机选择曲线参数
        x_start = random.randint(0, width // 4)
        y_start = random.randint(0, height)
        x_end = random.randint(3 * width // 4, width)
        y_end = random.randint(0, height)
        
        # 控制点
        ctrl_x = random.randint(width // 4, 3 * width // 4)
        ctrl_y = random.randint(0, height)
        
        color = (random.randint(100, 200), random.randint(100, 200), random.randint(100, 200))
        thickness = random.randint(1, 2)
        
        # 绘制二次贝塞尔曲线近似
        points = []
        num_points = 50
        for i in range(num_points + 1):
            t = i / num_points
            x = int((1 - t) ** 2 * x_start + 2 * (1 - t) * t * ctrl_x + t ** 2 * x_end)
            y = int((1 - t) ** 2 * y_start + 2 * (1 - t) * t * ctrl_y + t ** 2 * y_end)
            points.append((x, y))
        
        if len(points) > 1:
            draw.line(points, fill=color, width=thickness)

def _draw_noise_dots(draw, width, height, num_dots=80):
    """绘制随机噪点，使用不同大小和透明度模拟"""
    for _ in range(num_dots):
        x = random.randint(0, width)
        y = random.randint(0, height)
        size = random.randint(1, 3)
        color = (
            random.randint(80, 220),
            random.randint(80, 220),
            random.randint(80, 220)
        )
        draw.ellipse([x, y, x + size, y + size], fill=color)

def _draw_arc_interference(draw, width, height, num_arcs=3):
    """绘制随机圆弧干扰"""
    for _ in range(num_arcs):
        x = random.randint(0, width)
        y = random.randint(0, height)
        radius = random.randint(10, 40)
        
        color = (
            random.randint(120, 200),
            random.randint(120, 200),
            random.randint(120, 200)
        )
        
        start_angle = random.randint(0, 180)
        end_angle = start_angle + random.randint(60, 180)
        
        draw.arc(
            [x - radius, y - radius, x + radius, y + radius],
            start_angle, end_angle,
            fill=color, width=random.randint(1, 2)
        )

def generate_captcha_image(captcha_code):
    """生成高安全性验证码图像，抗AI识别"""
    width = 200
    height = 80
    
    # 创建图像（RGBA模式支持半透明效果）
    image = Image.new('RGBA', (width, height), (255, 255, 255, 255))
    draw = ImageDraw.Draw(image)
    
    # 1. 绘制渐变背景
    _generate_gradient_background(draw, width, height)
    
    # 2. 绘制圆弧干扰
    _draw_arc_interference(draw, width, height, num_arcs=3)
    
    # 3. 绘制贝塞尔曲线干扰
    _draw_curve_interference(draw, width, height, num_curves=5)
    
    # 4. 绘制噪点
    _draw_noise_dots(draw, width, height, num_dots=80)
    
    # 5. 加载字体（优先使用多种字体混合）
    font_paths = [
        r'C:\Windows\Fonts\arial.ttf',
        r'C:\Windows\Fonts\arialbd.ttf',
        r'C:\Windows\Fonts\arialbi.ttf',
        r'C:\Windows\Fonts\msyh.ttc',
        r'C:\Windows\Fonts\msyhbd.ttc',
        r'C:\Windows\Fonts\simhei.ttf',
        r'C:\Windows\Fonts\times.ttf',
        r'C:\Windows\Fonts\timesbd.ttf',
        r'C:\Windows\Fonts\verdana.ttf',
        r'C:\Windows\Fonts\verdanab.ttf',
    ]
    available_fonts = []
    for path in font_paths:
        if os.path.exists(path):
            available_fonts.append(path)
    
    # 6. 绘制验证码文字（每个字符独立随机处理）
    char_width = width // (len(captcha_code) + 1)
    
    for i, char in enumerate(captcha_code):
        if available_fonts:
            font_path = random.choice(available_fonts)
            try:
                font = ImageFont.truetype(font_path, random.randint(32, 48))
            except:
                font = ImageFont.load_default()
        else:
            font = ImageFont.load_default()
        
        angle = random.randint(-30, 30)
        
        color = (
            random.randint(0, 80),
            random.randint(0, 80),
            random.randint(0, 80)
        )
        
        char_image = Image.new('RGBA', (60, 70), (255, 255, 255, 0))
        char_draw = ImageDraw.Draw(char_image)
        
        scale = random.uniform(0.8, 1.2)
        
        char_draw.text((5, 5), char, font=font, fill=color)
        
        new_size = (int(60 * scale), int(70 * scale))
        char_image = char_image.resize(new_size, Image.LANCZOS)
        
        char_image = char_image.rotate(angle, expand=True, fillcolor=(255, 255, 255, 0))
        
        char_w, char_h = char_image.size
        
        base_x = char_width * i + random.randint(5, 15)
        base_y = random.randint(10, 25)
        
        x = max(0, min(width - char_w, base_x))
        y = max(0, min(height - char_h, base_y))
        
        image.paste(char_image, (x, y), char_image)
    
    # 7. 应用全局多重扭曲（破坏OCR字符分割）
    image = _apply_wave_distortion(image, amplitude=1.5, frequency=1.2)
    
    image = image.convert('RGB')
    
    image = image.filter(ImageFilter.GaussianBlur(radius=0.8))
    image = image.filter(ImageFilter.SHARPEN)
    
    final_draw = ImageDraw.Draw(image)
    for _ in range(40):
        x = random.randint(0, width - 1)
        y = random.randint(0, height - 1)
        color = (
            random.randint(100, 180),
            random.randint(100, 180),
            random.randint(100, 180)
        )
        final_draw.point((x, y), fill=color)
    
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
                if user.get('role') == 'banned':
                    session.clear()
                    return jsonify({'success': False, 'message': '当前用户已被封禁，请退出账户重新登录', 'banned': True}), 403
                break
        return f(*args, **kwargs)
    return decorated_function

# 题库JSON文件目录
PAPER_JSON_DIR = os.path.join(BASE_DIR, 'paper_json')
if not os.path.exists(PAPER_JSON_DIR):
    os.makedirs(PAPER_JSON_DIR)

def validate_file_path_input(file_path):
    if not file_path:
        return 'questions.json'
    if len(file_path) > 255:
        raise ValueError("文件路径过长")
    if not re.match(r'^[\w\-\./]+$', file_path):
        raise ValueError("文件路径包含非法字符")
    if '..' in file_path or '~' in file_path:
        raise ValueError("文件路径包含非法模式")
    return file_path
    logger.info(f'创建题库目录: {PAPER_JSON_DIR}')

app = Flask(__name__, static_folder='web', static_url_path='')

# 文件路由配置
FILE_ROUTER_CONFIG = FileRouterConfig(
    allowed_base_dirs=[
        os.path.join(BASE_DIR, 'paper_json'),
        os.path.join(BASE_DIR, 'uploads'),
        os.path.join(BASE_DIR, 'data')
    ],
    trash_enabled=True,
    trash_path=os.path.join(BASE_DIR, '.trash'),
    trash_retention_days=7,
    audit_enabled=True,
    audit_log_dir=os.path.join(BASE_DIR, 'logs', 'file_audit'),
    max_file_size_mb=100,
    allowed_extensions=['.json', '.txt', '.pdf', '.png', '.jpg', '.jpeg']
)

# 初始化文件路由（单例）
file_router = create_file_router(FILE_ROUTER_CONFIG)

# 在线用户跟踪：{username: last_activity_time}
_online_users = {}
_online_users_lock = threading.Lock()

# Session配置 - 安全加固
# 生成或加载持久化密钥，避免每次重启后所有用户被迫重新登录
SESSION_KEY_FILE = os.path.join(BASE_DIR, '.session_key')

def _load_or_generate_session_key():
    """加载或生成会话密钥"""
    if os.path.exists(SESSION_KEY_FILE):
        try:
            with open(SESSION_KEY_FILE, 'r', encoding='utf-8') as f:
                key = f.read().strip()
                if key and len(key) >= 32:
                    return key
        except Exception:
            pass
    # 生成新的随机密钥并持久化
    new_key = secrets.token_hex(32)
    try:
        with open(SESSION_KEY_FILE, 'w', encoding='utf-8') as f:
            f.write(new_key)
        if platform.system() == 'Windows':
            try:
                import subprocess
                subprocess.run(
                    ['icacls', SESSION_KEY_FILE, '/inheritance:r'],
                    check=False, capture_output=True, timeout=5
                )
                subprocess.run(
                    ['icacls', SESSION_KEY_FILE, '/grant', f'{os.getlogin()}:F'],
                    check=False, capture_output=True, timeout=5
                )
            except Exception as e:
                logger.warning(f'Windows文件权限设置失败: {e}')
        else:
            os.chmod(SESSION_KEY_FILE, 0o600)
        logger.info('已生成并持久化新的会话密钥')
    except Exception as e:
        logger.warning(f'持久化会话密钥失败，使用内存密钥: {e}')
    return new_key

_is_production = os.environ.get('FLASK_ENV') == 'production'

app.secret_key = _load_or_generate_session_key()
app.config['SESSION_COOKIE_NAME'] = 'tg_helper_session'
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_SECURE'] = _is_production
app.config['PERMANENT_SESSION_LIFETIME'] = datetime.timedelta(hours=2)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

_cors_origins = os.environ.get('CORS_ORIGINS', '').split(',') if os.environ.get('CORS_ORIGINS') else (['*'] if not _is_production else [])
CORS(app, resources={r"/api/*": {"origins": _cors_origins, "supports_credentials": True}})

@app.before_request
def set_request_context():
    """在每个请求开始前，保存请求者身份信息到线程本地存储"""
    user_id = request.headers.get('X-User-Identity', 'unknown')
    ip = request.remote_addr or 'unknown'
    _request_context.user_identity = f'[User:{user_id}][IP:{ip}]'
    # 更新会话活跃时间
    if session.get('logged_in'):
        session['last_activity'] = time.time()
        # 更新在线用户状态
        username = session.get('username')
        if username:
            with _online_users_lock:
                _online_users[username] = time.time()

@app.before_request
def generate_csp_nonce():
    if not hasattr(request, '_csp_nonce'):
        request._csp_nonce = secrets.token_urlsafe(16)

@app.before_request
def enforce_csrf_protection():
    if request.method in ('POST', 'PUT', 'PATCH', 'DELETE') and request.path.startswith('/api/'):
        if not request.headers.get('X-Requested-With'):
            return jsonify({'success': False, 'message': '缺少CSRF防护头'}), 403

@app.after_request
def add_security_and_cache_headers(response):
    """添加安全响应头和缓存控制"""
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    response.headers['Permissions-Policy'] = 'camera=(), microphone=(), geolocation=()'

    if _is_production and request.is_secure:
        response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'

    _csp_nonce = getattr(request, '_csp_nonce', '')
    csp_script_src = f"'self' 'nonce-{_csp_nonce}' 'unsafe-eval'"
    csp_policy = (
        "default-src 'self'; "
        f"script-src {csp_script_src}; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data: blob:; "
        "connect-src 'self'; "
        "font-src 'self'; "
        "frame-ancestors 'none'; "
        "base-uri 'self'; "
        "form-action 'self'"
    )
    response.headers['Content-Security-Policy'] = csp_policy
    
    # 禁用静态文件缓存
    path = request.path
    if path.endswith(('.css', '.html', '.js')):
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
    
    # 日志记录
    method = request.method
    status = response.status_code
    logger.info(f'请求: {method} {path} | 状态码: {status}')
    return response

# 确保静态资源能够被正确访问
@app.route('/<path:path>')
def serve_static(path):
    return send_from_directory(app.static_folder, path)

# 加密相关路由
@app.route('/api/admin/encryption/key_pair', methods=['GET'])
@admin_required
def get_encryption_key_pair_info():
    """获取当前加密密钥对信息（仅返回公钥和key_id，不返回私钥）"""
    try:
        key_pair = get_current_key_pair()
        if key_pair.get('public_key'):
            return jsonify({
                'success': True,
                'public_key': key_pair['public_key'],
                'key_id': key_pair.get('key_id', 'unknown')
            })
        else:
            return jsonify({
                'success': False,
                'message': '当前无可用密钥对'
            })
    except Exception as e:
        logger.error(f'获取密钥对信息失败: {e}')
        return jsonify({'success': False, 'message': f'获取失败: {str(e)}'}), 500


@app.route('/api/admin/encryption/rotate', methods=['POST'])
@admin_required
def rotate_encryption_keys_api():
    """
    轮换加密密钥对
    
    安全机制：
    - 生成新的RSA密钥对
    - 自动使用旧私钥解密现有API密钥
    - 使用新公钥重新加密所有API密钥
    - 确保旧密钥被彻底覆盖删除
    """
    try:
        data = request.get_json(silent=True)
        reencrypt_existing = True
        if data and 'reencrypt_existing' in data:
            reencrypt_existing = bool(data['reencrypt_existing'])
        
        result = rotate_encryption_keys(reencrypt_existing=reencrypt_existing)
        
        if result.get('success'):
            logger.info(
                f'管理员 {session.get("username")} 执行了密钥对轮换, '
                f'旧key_id={result.get("old_key_id")}, 新key_id={result.get("new_key_id")}'
            )
            return jsonify(result)
        else:
            return jsonify(result), 400
        
    except Exception as e:
        logger.error(f'密钥对轮换失败: {e}')
        return jsonify({'success': False, 'message': f'轮换失败: {str(e)}'}), 500


@app.route('/api/admin/encryption/initialize', methods=['POST'])
@admin_required
def initialize_encryption_keys():
    """
    初始化加密密钥对
    
    安全机制：
    - 如果不存在密钥对，则生成新的
    - 如果已存在，要求确认覆盖
    - 支持自定义密钥对导入
    """
    try:
        data = request.get_json(silent=True) or {}
        force = data.get('force', False)
        custom_public_key = data.get('public_key')
        custom_private_key = data.get('private_key')
        
        existing = load_key_pair()
        if existing and not force:
            return jsonify({
                'success': False,
                'message': '密钥对已存在，如需覆盖请设置force=true',
                'key_id': existing.get('key_id')
            }), 400
        
        if custom_public_key and custom_private_key:
            # 导入自定义密钥对
            key_pair = {
                'public_key': custom_public_key,
                'private_key': custom_private_key
            }
        else:
            # 生成新的密钥对
            from api_encryptor import _generate_rsa_key_pair, secrets
            key_pair = _generate_rsa_key_pair()
            key_pair['key_id'] = secrets.token_hex(8)
        
        result = save_key_pair(key_pair)
        
        if result:
            logger.info(f'管理员 {session.get("username")} 初始化了加密密钥对')
            return jsonify({
                'success': True,
                'message': '密钥对初始化成功',
                'key_id': key_pair.get('key_id', 'unknown'),
                'is_custom': bool(custom_public_key and custom_private_key)
            })
        else:
            return jsonify({'success': False, 'message': '密钥对保存失败'}), 500
        
    except Exception as e:
        logger.error(f'密钥对初始化失败: {e}')
        return jsonify({'success': False, 'message': f'初始化失败: {str(e)}'}), 500


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
        safe_path = werkzeug_safe_join(PAPER_JSON_DIR, file_path)
        if safe_path is None:
            raise ValueError("非法文件路径，禁止跨目录访问")
        
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
    session.pop('captcha_code', None)

    db = get_user_db()

    # 检查用户名是否已存在
    if db.user_exists(username):
        return jsonify({'success': False, 'message': '用户名已存在'}), 409

    default_role = 'guest'
    inviter = None
    if invite_code:
        inviter_user = db.get_user_by_invitation_code(invite_code)
        if not inviter_user:
            return jsonify({'success': False, 'message': '邀请码无效'}), 400
        inviter = inviter_user.get('username')
        default_role = 'user'
        logger.info(f'用户 {username} 使用用户 {inviter} 的邀请码注册')

    new_user = {
        'username': username,
        'password': hash_password(password),
        'role': default_role,
        'status': 'active',
        'invitation_code': generate_invitation_code(),
        'created_at': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'invited_by': inviter if invite_code else None
    }

    if db.create_user(new_user):
        logger.info(f'用户 {username} 注册成功，角色: {default_role}')
        return jsonify({
            'success': True,
            'message': '注册成功，请登录'
        })
    else:
        logger.error(f'用户注册失败：保存到数据库失败')
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
    
    # 检查登录频率限制
    client_ip = request.remote_addr or 'unknown'
    allowed, wait_seconds = _check_login_rate_limit(client_ip)
    if not allowed:
        return jsonify({
            'success': False, 
            'message': f'登录尝试过于频繁，请{wait_seconds}秒后再试',
            'rate_limited': True,
            'retry_after': wait_seconds
        }), 429
    
    if captcha:
        session_captcha = session.get('captcha_code', '').lower()
        if captcha.lower() != session_captcha:
            session.pop('captcha_code', None)
            _record_login_attempt(client_ip, success=False)
            return jsonify({'success': False, 'message': '验证码错误'}), 400
    
    db = get_user_db()
    user_found = db.get_user_by_username(username)

    if user_found and verify_user(username, password):
        if user_found.get('role') == 'banned':
            _record_login_attempt(client_ip, success=False)
            return jsonify({'success': False, 'message': '当前用户已被封禁，请联系管理员'}), 403

        session['logged_in'] = True
        session['username'] = username
        session['role'] = user_found.get('role', 'user')
        session['last_activity'] = time.time()
        session['login_time'] = datetime.datetime.now().isoformat()
        session.pop('captcha_code', None)

        # 更新用户 last_login 字段
        db.update_last_login(username, session['login_time'])
        
        _record_login_attempt(client_ip, success=True)
        logger.info(f'用户 {username} 登录成功')
        return jsonify({
            'success': True,
            'message': f'登录成功，欢迎 {username}',
            'username': username,
            'role': session['role']
        })
    else:
        _record_login_attempt(client_ip, success=False)
        logger.warning(f'用户 {username} 登录失败')
        return jsonify({'success': False, 'message': '用户名或密码错误'}), 401

@app.route('/api/logout', methods=['POST'])
def logout():
    """用户登出"""
    username = session.get('username', 'unknown')
    session.clear()
    # 从在线用户列表中移除
    with _online_users_lock:
        _online_users.pop(username, None)
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

@app.route('/api/events', methods=['GET'])
@login_required
def sse_events():
    """Server-Sent Events 端点 - 实时推送会话状态变更"""
    username = session.get('username', 'unknown')
    session_id = f"{username}:{secrets.token_hex(8)}"
    
    # 创建消息队列
    queue = Queue(maxsize=50)
    with sse_lock:
        sse_queues[session_id] = queue
    
    def event_stream():
        try:
            # 发送初始连接确认
            yield f"event: connected\ndata: {json.dumps({'session_id': session_id, 'username': username})}\n\n"
            
            # 定期发送心跳保活
            last_heartbeat = time.time()
            
            while True:
                try:
                    # 等待消息，超时30秒发送心跳
                    msg = queue.get(timeout=30)
                    if msg.get('event') == 'session_invalidated':
                        yield f"event: {msg['event']}\ndata: {msg['data']}\n\n"
                        break  # 会话失效，关闭连接
                except:
                    # 超时，发送心跳
                    now = time.time()
                    if now - last_heartbeat >= 25:
                        yield f"event: heartbeat\ndata: {json.dumps({'timestamp': datetime.datetime.now().isoformat()})}\n\n"
                        last_heartbeat = now
        except GeneratorExit:
            pass
        finally:
            # 清理队列
            with sse_lock:
                sse_queues.pop(session_id, None)
    
    return Response(
        stream_with_context(event_stream()),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
            'X-Accel-Buffering': 'no'  # 禁用nginx缓冲
        }
    )

@app.route('/api/verify_user', methods=['GET'])
@login_required
def verify_user_status():
    """验证当前用户状态（用于SSE事件触发，非轮询）"""
    username = session.get('username')
    db = get_user_db()
    user_found = db.get_user_by_username(username)

    if not user_found:
        # 用户不存在，清除会话
        _notify_session_invalidated(username, 'user_not_found')
        session.clear()
        return jsonify({
            'success': True,
            'valid': False,
            'reason': 'user_not_found',
            'message': '用户不存在'
        })
    
    if user_found.get('role') == 'banned':
        # 用户被封禁
        _notify_session_invalidated(username, 'banned')
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

@app.route('/api/heartbeat', methods=['POST'])
@login_required
def heartbeat():
    """心跳接口 - 保持会话活跃，轻量级验证用户状态"""
    username = session.get('username')
    db = get_user_db()
    user_found = db.get_user_by_username(username)

    if not user_found:
        _notify_session_invalidated(username, 'user_not_found')
        session.clear()
        return jsonify({
            'success': True,
            'valid': False,
            'reason': 'user_not_found'
        })
    
    if user_found.get('role') == 'banned':
        _notify_session_invalidated(username, 'banned')
        session.clear()
        return jsonify({
            'success': True,
            'valid': False,
            'reason': 'banned'
        })
    
    return jsonify({
        'success': True,
        'valid': True,
        'role': user_found.get('role', 'user'),
        'timestamp': datetime.datetime.now().isoformat()
    })

@app.route('/admin')
def admin_page():
    """返回管理员页面"""
    return _serve_html_with_nonce('admin.html')

@app.route('/editor')
def editor_page():
    """返回题库编辑独立页面"""
    return _serve_html_with_nonce('editor.html')

@app.route('/api/admin/users', methods=['GET'])
@admin_required
def get_all_users():
    """获取所有用户列表（管理员专用）"""
    try:
        users = load_users()
        # 获取鉴权超时时间（秒）
        settings = load_settings()
        auth_timeout_minutes = settings.get('account', {}).get('auth_timeout_minutes', 1)
        auth_timeout_seconds = auth_timeout_minutes * 60
        current_time = time.time()
        
        user_list = []
        for user in users:
            username = user.get('username')
            # 判断是否在线
            is_online = False
            with _online_users_lock:
                last_active = _online_users.get(username, 0)
                if last_active > 0 and (current_time - last_active) < auth_timeout_seconds:
                    is_online = True
            
            user_list.append({
                'username': username,
                'role': user.get('role', 'user'),
                'status': user.get('status', 'active'),
                'invitation_code': user.get('invitation_code'),
                'created_at': user.get('created_at', '未知'),
                'last_login': user.get('last_login', '从未登录'),
                'is_online': is_online
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

    if new_role not in ['guest', 'user', 'admin', 'banned']:
        return jsonify({'success': False, 'message': '无效的角色'}), 400

    db = get_user_db()
    if db.update_user(username, {'role': new_role}):
        logger.info(f'管理员 {session.get("username")} 将用户 {username} 的角色修改为 {new_role}')
        return jsonify({
            'success': True,
            'message': '角色修改成功'
        })
    else:
        return jsonify({'success': False, 'message': '用户不存在或保存失败'}), 404

@app.route('/api/admin/users/<username>/status', methods=['PUT'])
@admin_required
def update_user_status(username):
    """修改用户状态（封禁/解封）"""
    data = request.get_json()
    new_status = data.get('status')

    if new_status not in ['active', 'banned']:
        return jsonify({'success': False, 'message': '无效的状态'}), 400

    db = get_user_db()
    if db.update_user(username, {'status': new_status}):
        action = '封禁' if new_status == 'banned' else '解封'
        logger.info(f'管理员 {session.get("username")} {action}了用户 {username}')
        return jsonify({
            'success': True,
            'message': f'用户已{action}'
        })
    else:
        return jsonify({'success': False, 'message': '用户不存在或保存失败'}), 404

@app.route('/api/admin/users/<username>/invitation_code', methods=['PUT'])
@admin_required
def update_user_invitation_code(username):
    """重置用户邀请码"""
    db = get_user_db()
    user = db.get_user_by_username(username)

    if not user:
        return jsonify({'success': False, 'message': '用户不存在'}), 404

    new_code = generate_invitation_code()
    if db.update_user(username, {'invitation_code': new_code}):
        logger.info(f'管理员 {session.get("username")} 重置了用户 {username} 的邀请码')
        return jsonify({
            'success': True,
            'message': '邀请码已重置',
            'new_code': new_code
        })
    else:
        return jsonify({'success': False, 'message': '保存失败'}), 500

@app.route('/api/admin/deepseek/parse', methods=['POST'])
@admin_required
def deepseek_parse():
    """AI题目解析（异步任务）
    
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
        raw_file_path = validate_file_path_input(data.get('file_path', 'questions.json'))
        file_path = werkzeug_safe_join(PAPER_JSON_DIR, raw_file_path)
        if file_path is None:
            return jsonify({'success': False, 'message': '非法文件路径'}), 400

        settings = load_settings()
        agent_settings = settings.get('ai_agents', {}).get(QUESTION_ANALYSIS_AGENT_KEY, {})
        provider_name = agent_settings.get('provider', 'deepseek')
        provider_settings = settings.get('ai_providers', {}).get(provider_name, {})

        api_key = ''
        if encrypted_api_key:
            if not key_token:
                return jsonify({'success': False, 'message': '缺少加密密钥令牌'}), 400
            if not is_key_token_valid(key_token):
                return jsonify({'success': False, 'message': '加密密钥已过期或无效，请重新获取'}), 401
            secret_key = get_secret_key(key_token)
            api_key = decrypt_api_key(encrypted_api_key, secret_key)
            if not api_key:
                return jsonify({'success': False, 'message': 'API密钥解密失败'}), 400
            delete_secret_key(key_token)
        else:
            api_key = str(provider_settings.get('api_key', '')).strip()

        if not api_key:
            return jsonify({'success': False, 'message': '当前解析Agent未提供可用API Key，请在设置页保存或在解析页临时输入'}), 400

        import re
        
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
            system_prompt = agent_settings.get('system_prompt', DEFAULT_QUESTION_ANALYSIS_PROMPT)
            agent_model = agent_settings.get('model_id') or provider_settings.get('model_id') or '未配置模型'
            parsing_status['message'] = f'正在使用 {provider_name} / {agent_model} 解析题目'
            
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
                        analysis = invoke_ai_completion(
                            provider_name,
                            provider_settings,
                            agent_settings,
                            api_key_local,
                            system_prompt,
                            user_message
                        )
                        analysis = analysis.replace('**', '').replace('`', '').strip()
                        analysis = re.sub(r'<([a-zA-Z][a-zA-Z0-9-]*)>', r'&lt;\1&gt;', analysis)
                        analysis = re.sub(r'</([a-zA-Z][a-zA-Z0-9-]*)>', r'&lt;/\1&gt;', analysis)
                        
                        if analysis:
                            question['analysis'] = analysis
                            parsing_status['logs'].append(f"第 {i+1} 题解析成功")
                        else:
                            parsing_status['logs'].append(f"第 {i+1} 题解析失败，跳过保存")
                        
                    except Exception as e:
                        logger.error(f'调用AI解析接口失败: {e}')
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
                logger.info(f'管理员 {session.get("username")} 完成AI解析任务，provider={provider_name}')
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
        
    except ValueError as e:
        return jsonify({'success': False, 'message': str(e)}), 400
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
    """删除题库文件（使用文件路由，支持回收站）"""
    try:
        data = request.get_json()
        filename = data.get('filename', '').strip()
        immediate = data.get('immediate', False)  # 是否立即永久删除

        if not filename:
            return jsonify({'success': False, 'message': '文件名不能为空'}), 400

        if not filename.endswith('.json'):
            filename += '.json'

        # 构建相对路径
        file_path = os.path.join('paper_json', filename)

        username = session.get('username', 'unknown')

        # 使用文件路由删除文件
        result = file_router.delete(
            file_path,
            FilePermission.ADMIN,
            immediate=immediate,
            user_context=username
        )

        if result:
            action = '永久删除' if immediate else '移入回收站'
            logger.info(f'管理员 {username} {action}了题库 {filename}')
            return jsonify({
                'success': True,
                'message': f'题库已{action}'
            })
        else:
            return jsonify({'success': False, 'message': '删除失败'}), 500

    except FileRouterNotFoundError:
        return jsonify({'success': False, 'message': '题库文件不存在'}), 404
    except PermissionDeniedError:
        return jsonify({'success': False, 'message': '权限不足'}), 403
    except Exception as e:
        logger.error(f'题库删除失败: {e}')
        return jsonify({'success': False, 'message': str(e)}), 500

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

@app.route('/api/admin/question_bank/content', methods=['GET'])
@admin_required
def get_question_bank_content():
    """加载题库内容（返回所有题目数组及统计信息）"""
    try:
        filename = request.args.get('filename', '').strip()
        if not filename:
            return jsonify({'success': False, 'message': '缺少filename参数'}), 400
        
        if not filename.endswith('.json'):
            filename += '.json'
        
        file_path = os.path.abspath(os.path.join(PAPER_JSON_DIR, filename))
        if not file_path.startswith(PAPER_JSON_DIR):
            return jsonify({'success': False, 'message': '非法的文件路径'}), 400
        
        if not os.path.exists(file_path):
            return jsonify({'success': False, 'message': f'题库文件不存在: {filename}'}), 404
        
        with open(file_path, 'r', encoding='utf-8') as f:
            questions = json.load(f)
        
        total = len(questions)
        stats = {}
        for q in questions:
            qtype = q.get('type', '未知')
            stats[qtype] = stats.get(qtype, 0) + 1
        
        return jsonify({
            'success': True,
            'filename': filename,
            'questions': questions,
            'total': total,
            'stats': stats
        })
        
    except json.JSONDecodeError as e:
        logger.error(f'题库文件格式错误 {filename}: {e}')
        return jsonify({'success': False, 'message': f'题库文件格式错误: {str(e)}'}), 400
    except Exception as e:
        logger.error(f'加载题库内容失败: {e}')
        return jsonify({'success': False, 'message': f'加载失败: {str(e)}'}), 500

@app.route('/api/admin/question_bank/save', methods=['POST'])
@admin_required
def save_question_bank_content():
    """保存题库内容"""
    try:
        data = request.get_json()
        filename = data.get('filename', '').strip()
        questions = data.get('questions')
        
        if not filename:
            return jsonify({'success': False, 'message': '缺少filename参数'}), 400
        
        if questions is None or not isinstance(questions, list):
            return jsonify({'success': False, 'message': '缺少questions参数或格式错误'}), 400
        
        if not filename.endswith('.json'):
            filename += '.json'
        
        file_path = os.path.abspath(os.path.join(PAPER_JSON_DIR, filename))
        if not file_path.startswith(PAPER_JSON_DIR):
            return jsonify({'success': False, 'message': '非法的文件路径'}), 400
        
        for i, question in enumerate(questions):
            if not isinstance(question, dict):
                return jsonify({'success': False, 'message': f'第 {i+1} 道题目格式错误'}), 400
            
            if not question.get('content', '').strip():
                return jsonify({'success': False, 'message': f'第 {i+1} 道题目内容为空'}), 400
            
            if not isinstance(question.get('correct_answer'), list) or len(question['correct_answer']) == 0:
                return jsonify({'success': False, 'message': f'第 {i+1} 道题目答案格式错误'}), 400
        
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(questions, f, ensure_ascii=False, indent=2)
        
        logger.info(f'管理员 {session.get("username")} 保存了题库 {filename}，共 {len(questions)} 道题目')
        return jsonify({
            'success': True,
            'message': f'题库保存成功，共 {len(questions)} 道题目',
            'filename': filename,
            'question_count': len(questions)
        })
        
    except Exception as e:
        logger.error(f'保存题库失败: {e}')
        return jsonify({'success': False, 'message': f'保存失败: {str(e)}'}), 500

@app.route('/api/admin/question_bank/ai_parse', methods=['POST'])
@admin_required
def ai_parse_question():
    """AI解析单道题目（支持生成解析和生成答案两种模式）"""
    try:
        data = request.get_json()
        question_content = data.get('content', '').strip()
        options = data.get('options', [])
        correct_answer = data.get('correct_answer', [])
        question_type = data.get('type', 'single')
        mode = data.get('mode', 'parse_analysis')
        
        if mode not in ('parse_analysis', 'parse_answer'):
            return jsonify({'success': False, 'message': f'不支持的解析模式: {mode}'}), 400
        
        if not question_content:
            return jsonify({'success': False, 'message': '题目内容为空'}), 400
        
        settings = load_settings()
        agent_settings = settings.get('ai_agents', {}).get(QUESTION_ANALYSIS_AGENT_KEY, {})
        provider_name = agent_settings.get('provider', 'deepseek')
        provider_settings = settings.get('ai_providers', {}).get(provider_name, {})
        
        api_key = str(provider_settings.get('api_key', '')).strip()
        if not api_key:
            return jsonify({'success': False, 'message': '当前解析Agent未配置API Key，请在设置页保存'}), 400
        
        if mode == 'parse_analysis':
            system_prompt = agent_settings.get('system_prompt', DEFAULT_QUESTION_ANALYSIS_PROMPT)
            user_message = f"题目：{question_content}\n"
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
        else:
            system_prompt = """# Role
你是一位专业的考试题目答案生成专家。

# Task
根据题目内容、选项等信息，直接给出正确答案。

# Requirements
1. 仔细阅读题目内容和选项
2. 分析题目要点和考点
3. 直接给出正确答案
4. 对于单选题，返回单个选项字母
5. 对于多选题，返回多个选项字母（按字母顺序排列，用逗号分隔）
6. 对于判断题，返回"正确"或"错误"
7. 对于填空题，返回填空内容
8. 对于简答题，返回简洁的答案要点

# Output Format
仅返回答案，不需要解释过程。"""
            user_message = f"题目：{question_content}\n"
            if options:
                user_message += "选项：\n"
                for opt in options:
                    user_message += f"  {opt}\n"
        
        import re
        ai_response = invoke_ai_completion(
            provider_name,
            provider_settings,
            agent_settings,
            api_key,
            system_prompt,
            user_message
        )
        
        ai_response = ai_response.replace('**', '').replace('`', '').strip()
        ai_response = re.sub(r'<([a-zA-Z][a-zA-Z0-9-]*)>', r'&lt;\1&gt;', ai_response)
        ai_response = re.sub(r'</([a-zA-Z][a-zA-Z0-9-]*)>', r'&lt;/\1&gt;', ai_response)
        
        if not ai_response:
            return jsonify({'success': False, 'message': 'AI返回结果为空'}), 500
        
        logger.info(f'管理员 {session.get("username")} 调用AI单题解析，模式={mode}，provider={provider_name}')
        return jsonify({
            'success': True,
            'mode': mode,
            'result': ai_response,
            'provider': provider_name
        })
        
    except Exception as e:
        logger.error(f'AI单题解析失败: {e}')
        return jsonify({'success': False, 'message': f'解析失败: {str(e)}'}), 500

@app.route('/api/admin/question_bank/upload_image', methods=['POST'])
@admin_required
def upload_question_image():
    """上传题目图片"""
    try:
        if 'image' not in request.files:
            return jsonify({'success': False, 'message': '未找到上传文件'}), 400
        
        file = request.files['image']
        if file.filename == '':
            return jsonify({'success': False, 'message': '未选择文件'}), 400
        
        allowed_extensions = {'.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp'}
        _, ext = os.path.splitext(file.filename)
        if ext.lower() not in allowed_extensions:
            return jsonify({'success': False, 'message': f'不支持的文件格式，仅支持: {", ".join(allowed_extensions)}'}), 400
        
        import uuid
        image_dir = os.path.join(BASE_DIR, 'paper_json', 'image', 'editor_uploads')
        os.makedirs(image_dir, exist_ok=True)
        
        new_filename = uuid.uuid4().hex + ext.lower()
        image_path = os.path.join(image_dir, new_filename)
        
        file.save(image_path)
        
        relative_path = os.path.join('image', 'editor_uploads', new_filename)
        
        logger.info(f'管理员 {session.get("username")} 上传题目图片: {new_filename}')
        return jsonify({
            'success': True,
            'image_url': '/api/question_image/' + relative_path.replace(os.sep, '/'),
            'filename': new_filename
        })
        
    except Exception as e:
        logger.error(f'上传题目图片失败: {e}')
        return jsonify({'success': False, 'message': f'上传失败: {str(e)}'}), 500

@app.route('/api/admin/deepseek/stats', methods=['POST'])
@admin_required
def deepseek_stats():
    """获取题库统计信息"""
    try:
        data = request.get_json()
        file_path = validate_file_path_input(data.get('file_path', 'questions.json'))
        
        full_path = werkzeug_safe_join(PAPER_JSON_DIR, file_path)
        if full_path is None:
            return jsonify({'success': False, 'message': '非法文件路径'}), 400
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
        
    except ValueError as e:
        return jsonify({'success': False, 'message': str(e)}), 400
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
            'settings': get_public_settings(settings)
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
        
        settings_input = data.get('settings')
        if settings_input is not None and not isinstance(settings_input, dict):
            return jsonify({'success': False, 'message': '配置格式错误：settings 应为对象'}), 400
        
        existing_settings = load_settings()
        settings = normalize_settings(settings_input if settings_input is not None else data)
        
        key_token = data.get('key_token')
        updated_providers = []
        
        if key_token:
            if not is_key_token_valid(key_token):
                return jsonify({'success': False, 'message': '加密密钥已过期或无效，请重新获取'}), 401
            
            secret_key = get_secret_key(key_token)
            if not secret_key:
                return jsonify({'success': False, 'message': '加密密钥不存在'}), 400
            
            for provider in AI_PROVIDER_NAMES:
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
        
        existing_providers = existing_settings.get('ai_providers', {})
        incoming_providers = settings.get('ai_providers', {})
        for provider in AI_PROVIDER_NAMES:
            if provider not in incoming_providers:
                continue
            encrypted_key_field = f'encrypted_api_key_{provider}'
            incoming_key = str(incoming_providers[provider].get('api_key', '') or '').strip()
            if not incoming_key and not data.get(encrypted_key_field):
                incoming_providers[provider]['api_key'] = existing_providers.get(provider, {}).get('api_key', '')
        settings['ai_providers'] = incoming_providers

        if save_settings(settings):
            if updated_providers:
                logger.info(f'管理员 {session.get("username")} 保存了系统配置，更新了 {", ".join(updated_providers)} 的 API 密钥')
            else:
                logger.info(f'管理员 {session.get("username")} 保存了系统配置')
            return jsonify({
                'success': True,
                'message': '配置保存成功',
                'settings': get_public_settings(settings)
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
    try:
        file_path = validate_file_path_input(data.get('file_path', 'questions.json'))
    except ValueError as e:
        return jsonify({'success': False, 'message': str(e)}), 400
    
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

def _serve_html_with_nonce(filename, static_folder=None):
    nonce = getattr(request, '_csp_nonce', '')
    folder = static_folder or app.static_folder
    filepath = os.path.join(folder, filename)
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            html = f.read()
        html = html.replace('<script ', f'<script nonce="{nonce}" ')
        html = html.replace('<script>', f'<script nonce="{nonce}">')
        return Response(html, content_type='text/html; charset=utf-8')
    except Exception as e:
        logger.error(f'读取{filename}失败: {e}')
        return send_from_directory(folder, filename)

@app.route('/login')
def login_page():
    return _serve_html_with_nonce('index.html')

@app.route('/')
def index():
    """返回主页"""
    logger.info(f'用户访问主页 | IP: {request.remote_addr} | User-Agent: {request.headers.get("User-Agent", "Unknown")}')
    return _serve_html_with_nonce('index.html')

@app.route('/rag')
def rag_page():
    """返回RAG知识库页面"""
    return _serve_html_with_nonce('rag.html')

@app.route('/kb')
def kb_page():
    """返回知识库页面（RAG页面别名）"""
    return _serve_html_with_nonce('rag.html')

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
    """安全地拼接路径，确保不超出FTP_ROOT_DIR，使用werkzeug安全路径验证"""
    if len(paths) < 2:
        return None
    root_path = paths[0]
    user_path = os.path.join(*paths[1:])
    result = werkzeug_safe_join(root_path, user_path)
    return result

@app.route('/ftp')
def serve_ftp_page():
    """提供FTP文件浏览页面"""
    return _serve_html_with_nonce('ftp.html', static_folder=os.path.join(BASE_DIR, 'web'))

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


# ==================== RAG知识库API路由 ====================

# 初始化RAG系统
try:
    rag_db, rag_kb_manager, rag_doc_processor, rag_retriever, rag_chat = create_rag_system()
    logger.info('RAG系统初始化成功')
except Exception as e:
    logger.error(f'RAG系统初始化失败: {e}')
    rag_db = rag_kb_manager = rag_doc_processor = rag_retriever = rag_chat = None

# RAG文件上传配置
RAG_UPLOAD_FOLDER = os.path.join(BASE_DIR, 'data', 'rag_uploads')
RAG_ALLOWED_EXTENSIONS = {'pdf', 'docx', 'txt', 'md'}
RAG_MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB

os.makedirs(RAG_UPLOAD_FOLDER, exist_ok=True)


def allowed_rag_file(filename):
    """检查文件扩展名是否允许"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in RAG_ALLOWED_EXTENSIONS


# 1. 知识库管理API

@app.route('/api/rag/knowledge-bases', methods=['POST'])
@login_required
def create_knowledge_base():
    """创建知识库"""
    try:
        if not rag_kb_manager:
            return jsonify({'success': False, 'message': 'RAG系统未初始化'}), 500

        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'message': '请求数据不能为空'}), 400

        name = data.get('name', '').strip()
        description = data.get('description', '').strip()
        embedding_provider = data.get('embedding_provider', 'deepseek')
        embedding_model = data.get('embedding_model', '')
        api_key = data.get('api_key', '')
        chunk_size = data.get('chunk_size', 500)
        chunk_overlap = data.get('chunk_overlap', 50)

        if not name:
            return jsonify({'success': False, 'message': '知识库名称不能为空'}), 400
        if not embedding_model:
            return jsonify({'success': False, 'message': '嵌入模型不能为空'}), 400

        kb_id = rag_kb_manager.create_knowledge_base(
            name=name,
            description=description,
            embedding_provider=embedding_provider,
            embedding_model=embedding_model,
            api_key=api_key,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap
        )

        if kb_id:
            logger.info(f'用户 {session.get("username")} 创建知识库: {name} (ID: {kb_id})')
            return jsonify({'success': True, 'message': '知识库创建成功', 'data': {'id': kb_id}})
        else:
            return jsonify({'success': False, 'message': '知识库名称已存在或创建失败'}), 400

    except Exception as e:
        logger.error(f'创建知识库失败: {e}')
        return jsonify({'success': False, 'message': f'创建失败: {str(e)}'}), 500


@app.route('/api/rag/knowledge-bases', methods=['GET'])
@login_required
def list_knowledge_bases():
    """列出所有知识库"""
    try:
        if not rag_kb_manager:
            return jsonify({'success': False, 'message': 'RAG系统未初始化'}), 500

        kbs = rag_kb_manager.list_knowledge_bases()
        data = []
        for kb in kbs:
            data.append({
                'id': kb.id,
                'name': kb.name,
                'description': kb.description,
                'embedding_provider': kb.embedding_provider,
                'embedding_model': kb.embedding_model,
                'chunk_size': kb.chunk_size,
                'chunk_overlap': kb.chunk_overlap,
                'created_at': kb.created_at,
                'updated_at': kb.updated_at
            })

        return jsonify({'success': True, 'data': data})

    except Exception as e:
        logger.error(f'获取知识库列表失败: {e}')
        return jsonify({'success': False, 'message': f'获取失败: {str(e)}'}), 500


@app.route('/api/rag/knowledge-bases/<int:kb_id>', methods=['GET'])
@login_required
def get_knowledge_base(kb_id):
    """获取知识库详情"""
    try:
        if not rag_kb_manager:
            return jsonify({'success': False, 'message': 'RAG系统未初始化'}), 500

        kb = rag_kb_manager.get_knowledge_base(kb_id)
        if not kb:
            return jsonify({'success': False, 'message': '知识库不存在'}), 404

        data = {
            'id': kb.id,
            'name': kb.name,
            'description': kb.description,
            'embedding_provider': kb.embedding_provider,
            'embedding_model': kb.embedding_model,
            'chunk_size': kb.chunk_size,
            'chunk_overlap': kb.chunk_overlap,
            'created_at': kb.created_at,
            'updated_at': kb.updated_at
        }

        return jsonify({'success': True, 'data': data})

    except Exception as e:
        logger.error(f'获取知识库详情失败: {e}')
        return jsonify({'success': False, 'message': f'获取失败: {str(e)}'}), 500


@app.route('/api/rag/knowledge-bases/<int:kb_id>', methods=['PUT'])
@login_required
def update_knowledge_base(kb_id):
    """更新知识库"""
    try:
        if not rag_kb_manager:
            return jsonify({'success': False, 'message': 'RAG系统未初始化'}), 500

        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'message': '请求数据不能为空'}), 400

        # 检查知识库是否存在
        kb = rag_kb_manager.get_knowledge_base(kb_id)
        if not kb:
            return jsonify({'success': False, 'message': '知识库不存在'}), 404

        # 允许的更新字段
        allowed_fields = ['name', 'description', 'embedding_model', 'chunk_size', 'chunk_overlap']
        updates = {k: v for k, v in data.items() if k in allowed_fields}

        if not updates:
            return jsonify({'success': False, 'message': '没有可更新的字段'}), 400

        success = rag_kb_manager.update_knowledge_base(kb_id, **updates)

        if success:
            logger.info(f'用户 {session.get("username")} 更新知识库: ID={kb_id}')
            return jsonify({'success': True, 'message': '知识库更新成功'})
        else:
            return jsonify({'success': False, 'message': '更新失败'}), 400

    except Exception as e:
        logger.error(f'更新知识库失败: {e}')
        return jsonify({'success': False, 'message': f'更新失败: {str(e)}'}), 500


@app.route('/api/rag/knowledge-bases/<int:kb_id>', methods=['DELETE'])
@login_required
def delete_knowledge_base(kb_id):
    """删除知识库"""
    try:
        if not rag_kb_manager:
            return jsonify({'success': False, 'message': 'RAG系统未初始化'}), 500

        # 检查知识库是否存在
        kb = rag_kb_manager.get_knowledge_base(kb_id)
        if not kb:
            return jsonify({'success': False, 'message': '知识库不存在'}), 404

        success = rag_kb_manager.delete_knowledge_base(kb_id)

        if success:
            logger.info(f'用户 {session.get("username")} 删除知识库: ID={kb_id}')
            return jsonify({'success': True, 'message': '知识库删除成功'})
        else:
            return jsonify({'success': False, 'message': '删除失败'}), 400

    except Exception as e:
        logger.error(f'删除知识库失败: {e}')
        return jsonify({'success': False, 'message': f'删除失败: {str(e)}'}), 500


# 2. 文档管理API

@app.route('/api/rag/knowledge-bases/<int:kb_id>/documents', methods=['POST'])
@login_required
def upload_document(kb_id):
    """上传文档到知识库"""
    try:
        if not rag_kb_manager or not rag_doc_processor:
            return jsonify({'success': False, 'message': 'RAG系统未初始化'}), 500

        # 检查知识库是否存在
        kb = rag_kb_manager.get_knowledge_base(kb_id)
        if not kb:
            return jsonify({'success': False, 'message': '知识库不存在'}), 404

        if 'file' not in request.files:
            return jsonify({'success': False, 'message': '未找到文件'}), 400

        file = request.files['file']
        if file.filename == '':
            return jsonify({'success': False, 'message': '文件名不能为空'}), 400

        if not allowed_rag_file(file.filename):
            return jsonify({'success': False, 'message': '不支持的文件类型，仅允许: pdf, docx, txt, md'}), 400

        # 检查文件大小
        file.seek(0, os.SEEK_END)
        file_size = file.tell()
        file.seek(0)

        if file_size > RAG_MAX_FILE_SIZE:
            return jsonify({'success': False, 'message': f'文件大小超过限制 (最大 {RAG_MAX_FILE_SIZE // (1024 * 1024)}MB)'}), 400

        # 保存文件
        filename = f"{kb_id}_{int(time.time())}_{file.filename}"
        file_path = os.path.join(RAG_UPLOAD_FOLDER, filename)
        file.save(file_path)

        # 处理文档（异步处理，先返回文档ID）
        doc_id = rag_doc_processor.add_document(kb_id, file_path)

        if doc_id:
            logger.info(f'用户 {session.get("username")} 上传文档到知识库 {kb_id}: {file.filename} (ID: {doc_id})')
            return jsonify({
                'success': True,
                'message': '文档上传成功，正在处理中',
                'data': {'id': doc_id, 'status': 'processing'}
            })
        else:
            # 删除上传的文件
            if os.path.exists(file_path):
                os.remove(file_path)
            return jsonify({'success': False, 'message': '文档处理失败'}), 500

    except Exception as e:
        logger.error(f'上传文档失败: {e}')
        return jsonify({'success': False, 'message': f'上传失败: {str(e)}'}), 500


@app.route('/api/rag/knowledge-bases/<int:kb_id>/documents', methods=['GET'])
@login_required
def list_documents(kb_id):
    """列出知识库的所有文档"""
    try:
        if not rag_kb_manager or not rag_doc_processor:
            return jsonify({'success': False, 'message': 'RAG系统未初始化'}), 500

        # 检查知识库是否存在
        kb = rag_kb_manager.get_knowledge_base(kb_id)
        if not kb:
            return jsonify({'success': False, 'message': '知识库不存在'}), 404

        docs = rag_doc_processor.list_documents(kb_id)
        data = []
        for doc in docs:
            data.append({
                'id': doc.id,
                'kb_id': doc.kb_id,
                'filename': doc.filename,
                'file_type': doc.file_type,
                'file_size': doc.file_size,
                'status': doc.status,
                'error_message': doc.error_message,
                'created_at': doc.created_at,
                'updated_at': doc.updated_at
            })

        return jsonify({'success': True, 'data': data})

    except Exception as e:
        logger.error(f'获取文档列表失败: {e}')
        return jsonify({'success': False, 'message': f'获取失败: {str(e)}'}), 500


@app.route('/api/rag/documents/<int:doc_id>', methods=['GET'])
@login_required
def get_document(doc_id):
    """获取文档详情"""
    try:
        if not rag_doc_processor:
            return jsonify({'success': False, 'message': 'RAG系统未初始化'}), 500

        stats = rag_doc_processor.get_document_stats(doc_id)
        if not stats:
            return jsonify({'success': False, 'message': '文档不存在'}), 404

        doc = stats['document']
        data = {
            'id': doc['id'],
            'kb_id': doc['kb_id'],
            'filename': doc['filename'],
            'file_type': doc['file_type'],
            'file_size': doc['file_size'],
            'status': doc['status'],
            'error_message': doc['error_message'],
            'chunks_count': stats['chunks_count'],
            'total_tokens': stats['total_tokens'],
            'created_at': doc['created_at'],
            'updated_at': doc['updated_at']
        }

        return jsonify({'success': True, 'data': data})

    except Exception as e:
        logger.error(f'获取文档详情失败: {e}')
        return jsonify({'success': False, 'message': f'获取失败: {str(e)}'}), 500


@app.route('/api/rag/documents/<int:doc_id>', methods=['DELETE'])
@login_required
def delete_document(doc_id):
    """删除文档"""
    try:
        if not rag_doc_processor:
            return jsonify({'success': False, 'message': 'RAG系统未初始化'}), 500

        # 检查文档是否存在
        stats = rag_doc_processor.get_document_stats(doc_id)
        if not stats:
            return jsonify({'success': False, 'message': '文档不存在'}), 404

        success = rag_doc_processor.delete_document(doc_id)

        if success:
            logger.info(f'用户 {session.get("username")} 删除文档: ID={doc_id}')
            return jsonify({'success': True, 'message': '文档删除成功'})
        else:
            return jsonify({'success': False, 'message': '删除失败'}), 400

    except Exception as e:
        logger.error(f'删除文档失败: {e}')
        return jsonify({'success': False, 'message': f'删除失败: {str(e)}'}), 500


@app.route('/api/rag/documents/<int:doc_id>/status', methods=['GET'])
@login_required
def get_document_status(doc_id):
    """查询文档处理状态"""
    try:
        if not rag_doc_processor:
            return jsonify({'success': False, 'message': 'RAG系统未初始化'}), 500

        stats = rag_doc_processor.get_document_stats(doc_id)
        if not stats:
            return jsonify({'success': False, 'message': '文档不存在'}), 404

        doc = stats['document']
        data = {
            'id': doc['id'],
            'status': doc['status'],
            'error_message': doc['error_message'],
            'chunks_count': stats['chunks_count'],
            'total_tokens': stats['total_tokens'],
            'updated_at': doc['updated_at']
        }

        return jsonify({'success': True, 'data': data})

    except Exception as e:
        logger.error(f'获取文档状态失败: {e}')
        return jsonify({'success': False, 'message': f'获取失败: {str(e)}'}), 500


# 3. RAG检索与对话API

@app.route('/api/rag/knowledge-bases/<int:kb_id>/search', methods=['POST'])
@login_required
def search_knowledge_base(kb_id):
    """向量检索知识库"""
    try:
        if not rag_kb_manager or not rag_retriever:
            return jsonify({'success': False, 'message': 'RAG系统未初始化'}), 500

        # 检查知识库是否存在
        kb = rag_kb_manager.get_knowledge_base(kb_id)
        if not kb:
            return jsonify({'success': False, 'message': '知识库不存在'}), 404

        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'message': '请求数据不能为空'}), 400

        query = data.get('query', '').strip()
        top_k = data.get('top_k', 5)
        min_score = data.get('min_score', 0.0)

        if not query:
            return jsonify({'success': False, 'message': '查询内容不能为空'}), 400

        # 获取API密钥
        api_key = rag_kb_manager.get_api_key(kb_id)
        if not api_key:
            return jsonify({'success': False, 'message': '知识库未配置API密钥'}), 400

        # 创建嵌入客户端
        embedding_client = EmbeddingClient(
            kb.embedding_provider,
            api_key,
            kb.embedding_model
        )

        # 获取查询向量
        query_embedding = embedding_client.embed_query(query)

        # 执行检索
        results = rag_retriever.retrieve(kb_id, query_embedding, top_k=top_k, min_score=min_score)

        return jsonify({
            'success': True,
            'data': {
                'query': query,
                'results': results,
                'total': len(results)
            }
        })

    except Exception as e:
        logger.error(f'向量检索失败: {e}')
        return jsonify({'success': False, 'message': f'检索失败: {str(e)}'}), 500


@app.route('/api/rag/knowledge-bases/<int:kb_id>/query', methods=['POST'])
@login_required
def query_knowledge_base(kb_id):
    """RAG问答（非流式）"""
    try:
        if not rag_kb_manager or not rag_chat:
            return jsonify({'success': False, 'message': 'RAG系统未初始化'}), 500

        # 检查知识库是否存在
        kb = rag_kb_manager.get_knowledge_base(kb_id)
        if not kb:
            return jsonify({'success': False, 'message': '知识库不存在'}), 404

        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'message': '请求数据不能为空'}), 400

        query = data.get('query', '').strip()
        conversation_history = data.get('conversation_history', [])
        top_k = data.get('top_k', 5)

        if not query:
            return jsonify({'success': False, 'message': '查询内容不能为空'}), 400

        # 执行RAG对话
        answer = rag_chat.chat(
            kb_id=kb_id,
            query=query,
            conversation_history=conversation_history,
            top_k=top_k,
            stream=False
        )

        logger.info(f'用户 {session.get("username")} 在知识库 {kb_id} 执行RAG查询')

        return jsonify({
            'success': True,
            'data': {
                'query': query,
                'answer': answer
            }
        })

    except Exception as e:
        logger.error(f'RAG问答失败: {e}')
        return jsonify({'success': False, 'message': f'问答失败: {str(e)}'}), 500


@app.route('/api/rag/knowledge-bases/<int:kb_id>/query/stream', methods=['POST'])
@login_required
def query_knowledge_base_stream(kb_id):
    """RAG问答（流式SSE）"""
    try:
        if not rag_kb_manager or not rag_chat:
            return jsonify({'success': False, 'message': 'RAG系统未初始化'}), 500

        # 检查知识库是否存在
        kb = rag_kb_manager.get_knowledge_base(kb_id)
        if not kb:
            return jsonify({'success': False, 'message': '知识库不存在'}), 404

        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'message': '请求数据不能为空'}), 400

        query = data.get('query', '').strip()
        conversation_history = data.get('conversation_history', [])
        top_k = data.get('top_k', 5)

        if not query:
            return jsonify({'success': False, 'message': '查询内容不能为空'}), 400

        def generate():
            try:
                for chunk in rag_chat.chat(
                    kb_id=kb_id,
                    query=query,
                    conversation_history=conversation_history,
                    top_k=top_k,
                    stream=True
                ):
                    yield f"data: {json.dumps({'content': chunk})}\n\n"
                yield f"data: {json.dumps({'done': True})}\n\n"
            except Exception as e:
                logger.error(f'流式RAG问答失败: {e}')
                yield f"data: {json.dumps({'error': str(e)})}\n\n"

        logger.info(f'用户 {session.get("username")} 在知识库 {kb_id} 执行流式RAG查询')

        return Response(
            stream_with_context(generate()),
            mimetype='text/event-stream',
            headers={
                'Cache-Control': 'no-cache',
                'X-Accel-Buffering': 'no'
            }
        )

    except Exception as e:
        logger.error(f'流式RAG问答失败: {e}')
        return jsonify({'success': False, 'message': f'问答失败: {str(e)}'}), 500


@app.route('/api/admin/trash', methods=['GET'])
@admin_required
def get_trash_items():
    """获取回收站中的所有项目"""
    try:
        items = file_router.get_trash_items(FilePermission.ADMIN)
        return jsonify({
            'success': True,
            'items': [
                {
                    'trash_id': item.trash_id,
                    'original_path': item.original_path,
                    'deleted_at': item.deleted_at,
                    'expires_at': item.expires_at,
                    'file_size': item.file_size,
                    'deleted_by': item.deleted_by
                }
                for item in items
            ]
        })
    except Exception as e:
        logger.error(f'获取回收站列表失败: {e}')
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/admin/trash/restore', methods=['POST'])
@admin_required
def restore_from_trash():
    """从回收站恢复文件"""
    try:
        data = request.get_json()
        trash_id = data.get('trash_id', '').strip()

        if not trash_id:
            return jsonify({'success': False, 'message': '缺少trash_id参数'}), 400

        username = session.get('username', 'unknown')
        result = file_router.restore_from_trash(
            trash_id,
            FilePermission.ADMIN,
            user_context=username
        )

        if result:
            logger.info(f'管理员 {username} 恢复了文件 (ID: {trash_id})')
            return jsonify({'success': True, 'message': '文件恢复成功'})
        else:
            return jsonify({'success': False, 'message': '文件恢复失败'}), 500

    except Exception as e:
        logger.error(f'恢复文件失败: {e}')
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/admin/trash/clear', methods=['POST'])
@admin_required
def clear_trash():
    """清空回收站（永久删除所有文件）"""
    try:
        trash_manager = create_trash_manager()
        items = trash_manager.get_trash_items()

        deleted_count = 0
        for item in items:
            if trash_manager.permanent_delete(item.trash_id):
                deleted_count += 1

        username = session.get('username', 'unknown')
        logger.info(f'管理员 {username} 清空了回收站，永久删除了 {deleted_count} 个文件')

        return jsonify({
            'success': True,
            'message': f'回收站已清空，共删除 {deleted_count} 个文件'
        })
    except Exception as e:
        logger.error(f'清空回收站失败: {e}')
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/admin/file-audit-logs', methods=['GET'])
@admin_required
def get_file_audit_logs():
    """获取文件操作审计日志"""
    try:
        days = request.args.get('days', 7, type=int)
        audit_logger = get_file_audit_logger()
        logs = audit_logger.get_recent_logs(days=days)

        return jsonify({
            'success': True,
            'logs': logs
        })
    except Exception as e:
        logger.error(f'获取文件审计日志失败: {e}')
        return jsonify({'success': False, 'message': str(e)}), 500


if __name__ == '__main__':
    # 确保web目录存在
    if not os.path.exists(os.path.join(BASE_DIR, 'web')):
        os.makedirs(os.path.join(BASE_DIR, 'web'))

    # 在0.0.0.0上运行，允许局域网访问
    app.run(host='0.0.0.0', port=5000, debug=False)  # 生产环境应关闭debug
