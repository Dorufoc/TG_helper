import base64
import secrets
import datetime
import gc
import os
import json
import logging
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

# 临时会话密钥存储（用于前端加密传输）
_api_key_secrets: Dict[str, Dict[str, Any]] = {}
ENCRYPTION_KEY_EXPIRY = datetime.timedelta(minutes=10)

# 密钥对存储文件路径
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
KEY_PAIR_FILE = os.path.join(BASE_DIR, 'encryption_keys.json')

# RSA密钥对缓存
_current_key_pair: Dict[str, Optional[str]] = {
    'public_key': None,
    'private_key': None,
    'key_id': None
}


def _generate_rsa_key_pair() -> Dict[str, str]:
    """
    生成RSA密钥对
    
    Returns:
        包含public_key和private_key的字典
    """
    from cryptography.hazmat.primitives.asymmetric import rsa, padding
    from cryptography.hazmat.primitives import serialization, hashes
    
    # 生成2048位RSA密钥对
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
    )
    
    # 私钥PEM编码
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption()
    )
    
    # 公钥PEM编码
    public_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo
    )
    
    return {
        'public_key': public_pem.decode('utf-8'),
        'private_key': private_pem.decode('utf-8')
    }


def _encrypt_with_rsa(plaintext: str, public_key_pem: str) -> str:
    """
    使用RSA公钥加密数据
    
    Args:
        plaintext: 明文字符串
        public_key_pem: PEM格式的公钥
    
    Returns:
        Base64编码的密文
    """
    from cryptography.hazmat.primitives.asymmetric import padding
    from cryptography.hazmat.primitives import serialization, hashes
    
    # 加载公钥
    public_key = serialization.load_pem_public_key(public_key_pem.encode('utf-8'))
    
    # 加密
    ciphertext = public_key.encrypt(
        plaintext.encode('utf-8'),
        padding.OAEP(
            mgf=padding.MGF1(algorithm=hashes.SHA256()),
            algorithm=hashes.SHA256(),
            label=None
        )
    )
    
    return base64.b64encode(ciphertext).decode('utf-8')


def _decrypt_with_rsa(ciphertext_b64: str, private_key_pem: str) -> Optional[str]:
    """
    使用RSA私钥解密数据
    
    Args:
        ciphertext_b64: Base64编码的密文
        private_key_pem: PEM格式的私钥
    
    Returns:
        解密后的明文，失败返回None
    """
    from cryptography.hazmat.primitives.asymmetric import padding
    from cryptography.hazmat.primitives import serialization, hashes
    
    try:
        # 加载私钥
        private_key = serialization.load_pem_private_key(
            private_key_pem.encode('utf-8'),
            password=None
        )
        
        # 解密
        ciphertext = base64.b64decode(ciphertext_b64)
        plaintext = private_key.decrypt(
            ciphertext,
            padding.OAEP(
                mgf=padding.MGF1(algorithm=hashes.SHA256()),
                algorithm=hashes.SHA256(),
                label=None
            )
        )
        
        return plaintext.decode('utf-8')
    except Exception as e:
        logger.error(f"RSA解密失败: {e}")
        return None


def load_key_pair() -> Optional[Dict[str, str]]:
    """
    从文件加载密钥对
    
    Returns:
        密钥对字典或None
    """
    global _current_key_pair
    
    try:
        if os.path.exists(KEY_PAIR_FILE):
            with open(KEY_PAIR_FILE, 'r', encoding='utf-8') as f:
                key_data = json.load(f)
            
            _current_key_pair = {
                'public_key': key_data.get('public_key'),
                'private_key': key_data.get('private_key'),
                'key_id': key_data.get('key_id')
            }
            
            logger.info(f"密钥对加载成功, key_id={_current_key_pair['key_id']}")
            return _current_key_pair
    except Exception as e:
        logger.error(f"加载密钥对失败: {e}")
    
    return None


def save_key_pair(key_pair: Dict[str, str]) -> bool:
    """
    保存密钥对到文件
    
    Args:
        key_pair: 密钥对字典
    
    Returns:
        保存成功返回True
    """
    global _current_key_pair
    
    try:
        key_data = {
            'key_id': key_pair.get('key_id', secrets.token_hex(8)),
            'public_key': key_pair['public_key'],
            'private_key': key_pair['private_key'],
            'created_at': datetime.datetime.now().isoformat()
        }
        
        with open(KEY_PAIR_FILE, 'w', encoding='utf-8') as f:
            json.dump(key_data, f, ensure_ascii=False, indent=2)
        
        _current_key_pair = {
            'public_key': key_pair['public_key'],
            'private_key': key_pair['private_key'],
            'key_id': key_data['key_id']
        }
        
        logger.info(f"密钥对保存成功, key_id={key_data['key_id']}")
        return True
    except Exception as e:
        logger.error(f"保存密钥对失败: {e}")
        return False


def get_current_key_pair() -> Dict[str, Optional[str]]:
    """
    获取当前密钥对
    
    Returns:
        密钥对字典
    """
    if _current_key_pair['public_key'] is None:
        load_key_pair()
    
    return _current_key_pair.copy()


def rotate_key_pair() -> Dict[str, str]:
    """
    轮换密钥对，生成新的密钥对
    
    Returns:
        新的密钥对字典
    """
    new_key_pair = _generate_rsa_key_pair()
    new_key_pair['key_id'] = secrets.token_hex(8)
    
    # 保存新密钥对（会覆盖旧密钥对）
    save_key_pair(new_key_pair)
    
    logger.info(f"密钥对已轮换, 新key_id={new_key_pair['key_id']}")
    return new_key_pair


def encrypt_api_key(plaintext: str, use_public_key: Optional[str] = None) -> Optional[str]:
    """
    使用RSA公钥加密API密钥
    
    Args:
        plaintext: 明文API密钥
        use_public_key: 可选，使用指定的公钥（默认使用当前密钥对中的公钥）
    
    Returns:
        Base64编码的密文，失败返回None
    """
    try:
        if use_public_key:
            public_key = use_public_key
        else:
            key_pair = get_current_key_pair()
            public_key = key_pair.get('public_key')
        
        if not public_key:
            logger.error("无可用公钥进行加密")
            return None
        
        return _encrypt_with_rsa(plaintext, public_key)
    except Exception as e:
        logger.error(f"加密API密钥失败: {e}")
        return None


def decrypt_api_key(encrypted_data: str, use_private_key: Optional[str] = None) -> Optional[str]:
    """
    使用RSA私钥解密API密钥
    
    Args:
        encrypted_data: Base64编码的密文
        use_private_key: 可选，使用指定的私钥（默认使用当前密钥对中的私钥）
    
    Returns:
        解密后的API密钥，失败返回None
    """
    try:
        if use_private_key:
            private_key = use_private_key
        else:
            key_pair = get_current_key_pair()
            private_key = key_pair.get('private_key')
        
        if not private_key:
            logger.error("无可用私钥进行解密")
            return None
        
        return _decrypt_with_rsa(encrypted_data, private_key)
    except Exception as e:
        logger.error(f"解密API密钥失败: {e}")
        return None


def cleanup_expired_secrets() -> None:
    """清理过期的加密密钥，防止内存泄漏"""
    now = datetime.datetime.now()
    expired_tokens = [
        token for token, data in _api_key_secrets.items()
        if now - data['created_at'] > ENCRYPTION_KEY_EXPIRY
    ]
    for token in expired_tokens:
        del _api_key_secrets[token]
        logger.info(f"清理过期的临时密钥: {token[:8]}...")


def generate_encryption_key() -> Dict[str, str]:
    """
    生成临时XOR加密密钥（用于前端加密传输）
    
    安全机制：
    - 生成32字节随机密钥
    - 生成唯一令牌（key_token）
    - 密钥10分钟后自动过期
    
    Returns:
        包含key_token和public_key的字典
    """
    secret_key = secrets.token_bytes(32)
    key_token = secrets.token_hex(16)
    
    _api_key_secrets[key_token] = {
        'secret_key': secret_key,
        'created_at': datetime.datetime.now()
    }
    
    cleanup_expired_secrets()
    
    logger.info(f"生成临时加密密钥: token={key_token[:8]}...")
    
    return {
        'key_token': key_token,
        'public_key': base64.b64encode(secret_key).decode('utf-8')
    }


def get_secret_key(key_token: str) -> Optional[bytes]:
    """
    根据令牌获取对应的解密密钥
    
    Args:
        key_token: 加密令牌
    
    Returns:
        解密密钥字节，如果令牌不存在或已过期则返回None
    """
    if key_token not in _api_key_secrets:
        return None
    return _api_key_secrets[key_token]['secret_key']


def delete_secret_key(key_token: str) -> None:
    """
    删除指定的解密密钥（安全销毁）
    
    Args:
        key_token: 加密令牌
    """
    if key_token in _api_key_secrets:
        del _api_key_secrets[key_token]
        gc.collect()


def is_key_token_valid(key_token: str) -> bool:
    """
    检查加密令牌是否有效
    
    Args:
        key_token: 加密令牌
    
    Returns:
        是否有效
    """
    return key_token in _api_key_secrets
