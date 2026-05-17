import base64
import secrets
import datetime
import gc
import logging
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

_api_key_secrets: Dict[str, Dict[str, Any]] = {}
ENCRYPTION_KEY_EXPIRY = datetime.timedelta(minutes=10)


def decrypt_api_key(encrypted_data: str, secret_key: bytes) -> Optional[str]:
    """
    解密API密钥（XOR + Base64方案）
    
    安全机制：
    - 前端使用publicKey对apiKey进行XOR加密，再Base64编码
    - 后端Base64解码后，每个字节与secretKey对应字节XOR，还原原始字符串
    - 解密后立即销毁密钥，防止内存残留
    
    Args:
        encrypted_data: Base64编码的加密数据
        secret_key: 解密用的密钥字节
    
    Returns:
        解密后的API密钥字符串，失败返回None
    """
    try:
        encrypted_bytes = base64.b64decode(encrypted_data)
        
        decrypted_bytes = bytearray()
        key_len = len(secret_key)
        for i, byte in enumerate(encrypted_bytes):
            decrypted_bytes.append(byte ^ secret_key[i % key_len])
        
        return decrypted_bytes.decode('utf-8')
    except Exception as e:
        logger.error(f"API密钥解密失败: {e}")
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
        logger.info(f"清理过期的加密密钥: {token[:8]}...")


def generate_encryption_key() -> Dict[str, str]:
    """
    生成临时加密密钥对
    
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
    
    logger.info(f"生成加密密钥对: token={key_token[:8]}...")
    
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
