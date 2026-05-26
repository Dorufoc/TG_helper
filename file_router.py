# -*- coding: utf-8 -*-
"""
文件路由核心模块

提供安全的文件访问控制，作为所有文件操作的唯一入口。
功能包括：
- 权限管理（READ_ONLY, READ_WRITE, ADMIN）
- 路径安全验证（防止路径遍历攻击）
- 文件类型验证
- 文件锁管理（线程安全）
- 回收站功能
- 审计日志记录

禁止直接暴露原始文件系统操作，所有文件访问必须通过此路由。
"""

import os
import re
import time
import shutil
import threading
from enum import Enum, auto
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any, Set, Union, Tuple
from contextlib import contextmanager
from datetime import datetime

from werkzeug.security import safe_join
from werkzeug.utils import secure_filename

from file_audit_logger import (
    get_file_audit_logger,
    FileAuditLogEntry,
    FileOperationType,
    OperationResult
)
from file_trash_manager import (
    TrashManager,
    create_trash_manager,
    TrashItem,
    TrashError,
    TrashItemNotFoundError,
    TrashRestoreError
)


class FilePermission(Enum):
    """文件访问权限枚举
    
    - READ_ONLY: 只允许读取操作（read, list_dir, exists, stat）
    - READ_WRITE: 允许读写删操作（read, write, delete, list_dir, exists, stat, move, copy）
    - ADMIN: 允许所有操作（包括永久删除、回收站管理等）
    """
    READ_ONLY = auto()   # 只允许读取
    READ_WRITE = auto()  # 允许读写删
    ADMIN = auto()       # 允许所有操作


@dataclass
class FileRouterConfig:
    """文件路由配置类
    
    Attributes:
        allowed_base_dirs: 允许访问的基础目录列表
        trash_enabled: 是否启用回收站功能
        trash_path: 回收站目录路径
        trash_retention_days: 回收站文件保留天数
        audit_enabled: 是否启用审计日志
        audit_log_dir: 审计日志目录
        max_file_size_mb: 最大允许的文件大小（MB）
        allowed_extensions: 允许的文件扩展名列表（None表示允许所有）
    """
    allowed_base_dirs: List[str] = field(default_factory=list)
    trash_enabled: bool = True
    trash_path: str = ".trash"
    trash_retention_days: int = 7
    audit_enabled: bool = True
    audit_log_dir: str = "logs/file_audit"
    max_file_size_mb: int = 100
    allowed_extensions: Optional[List[str]] = None


# ============================================================================
# 异常类层次
# ============================================================================

class FileRouterError(Exception):
    """文件路由错误基类"""
    pass


class PermissionDeniedError(FileRouterError):
    """权限不足错误
    
    当用户尝试执行超出其权限级别的操作时抛出。
    """
    pass


class PathNotAllowedError(FileRouterError):
    """路径不允许错误
    
    当请求的路径不在允许的基础目录范围内时抛出。
    """
    pass


class PathTraversalError(FileRouterError):
    """路径遍历攻击错误
    
    当检测到潜在的路径遍历攻击（如 ../../../etc/passwd）时抛出。
    """
    pass


class FileNotFoundError(FileRouterError):
    """文件不存在错误
    
    当请求的文件或目录不存在时抛出。
    """
    pass


class FileSizeExceededError(FileRouterError):
    """文件大小超出限制错误
    
    当文件大小超过配置的最大限制时抛出。
    """
    pass


class FileTypeNotAllowedError(FileRouterError):
    """文件类型不允许错误
    
    当文件扩展名不在允许的列表中时抛出。
    """
    pass


# ============================================================================
# PathValidator 路径验证器
# ============================================================================

class PathValidator:
    """路径验证器
    
    负责验证文件路径的安全性，防止路径遍历攻击和访问未授权目录。
    """
    
    # Windows 保留设备名（大小写不敏感）
    WINDOWS_DEVICE_NAMES = {
        'CON', 'PRN', 'AUX', 'NUL',
        'COM1', 'COM2', 'COM3', 'COM4', 'COM5', 'COM6', 'COM7', 'COM8', 'COM9',
        'LPT1', 'LPT2', 'LPT3', 'LPT4', 'LPT5', 'LPT6', 'LPT7', 'LPT8', 'LPT9'
    }
    
    def __init__(self, allowed_base_dirs: List[str]):
        """初始化路径验证器
        
        Args:
            allowed_base_dirs: 允许访问的基础目录列表
        """
        self._allowed_base_dirs = [os.path.abspath(d) for d in allowed_base_dirs]
        self._lock = threading.RLock()
    
    def validate_path(self, path: str, allowed_base_dirs: Optional[List[str]] = None) -> str:
        """验证路径安全性
        
        使用 werkzeug.security.safe_join 规范化路径，
        验证路径在允许的基础目录内，检测路径遍历攻击。
        
        Args:
            path: 要验证的文件路径
            allowed_base_dirs: 可选的临时允许目录列表（覆盖默认配置）
            
        Returns:
            规范化后的绝对路径
            
        Raises:
            PathTraversalError: 检测到路径遍历攻击
            PathNotAllowedError: 路径不在允许的目录范围内
        """
        with self._lock:
            base_dirs = allowed_base_dirs or self._allowed_base_dirs
            base_dirs = [os.path.abspath(d) for d in base_dirs]
            
            if not base_dirs:
                raise PathNotAllowedError("未配置允许访问的基础目录")
            
            # 规范化输入路径
            path = os.path.normpath(path)
            
            # 如果是绝对路径，直接使用；否则尝试与每个基础目录拼接
            if os.path.isabs(path):
                full_path = os.path.abspath(path)
            else:
                # 尝试与每个基础目录拼接，找到第一个匹配的
                for base_dir in base_dirs:
                    joined = safe_join(base_dir, path)
                    if joined:
                        full_path = os.path.abspath(joined)
                        break
                else:
                    raise PathTraversalError(f"路径无法安全拼接: {path}")
            
            # 验证路径是否在允许的基础目录内
            is_allowed = any(
                self._is_path_under_base(full_path, base_dir)
                for base_dir in base_dirs
            )
            
            if not is_allowed:
                raise PathNotAllowedError(
                    f"路径不在允许的目录范围内: {path}"
                )
            
            return full_path
    
    def validate_filename(self, filename: str) -> str:
        """验证文件名
        
        使用 werkzeug.utils.secure_filename 规范化文件名，
        阻止 Windows 设备名（CON, PRN, AUX等）。
        
        Args:
            filename: 要验证的文件名
            
        Returns:
            规范化后的文件名
            
        Raises:
            FileRouterError: 文件名无效或为Windows设备名
        """
        with self._lock:
            # 使用 werkzeug 的安全文件名函数
            safe_name = secure_filename(filename)
            
            if not safe_name:
                raise FileRouterError(f"文件名无效: {filename}")
            
            # 检查 Windows 设备名
            name_without_ext = safe_name.split('.')[0].upper()
            if name_without_ext in self.WINDOWS_DEVICE_NAMES:
                raise FileRouterError(
                    f"文件名不能使用 Windows 保留设备名: {filename}"
                )
            
            return safe_name
    
    def _is_path_under_base(self, path: str, base_dir: str) -> bool:
        """检查路径是否在基础目录下
        
        Args:
            path: 要检查的路径
            base_dir: 基础目录
            
        Returns:
            如果 path 在 base_dir 下（或是 base_dir 本身）返回 True
        """
        try:
            # 使用 Path 的 relative_to 方法检查
            Path(path).relative_to(Path(base_dir))
            return True
        except ValueError:
            return False


# ============================================================================
# FileTypeValidator 文件类型验证器
# ============================================================================

class FileTypeValidator:
    """文件类型验证器
    
    负责验证文件扩展名和文件大小。
    """
    
    def __init__(
        self,
        allowed_extensions: Optional[List[str]] = None,
        max_file_size_mb: int = 100
    ):
        """初始化文件类型验证器
        
        Args:
            allowed_extensions: 允许的文件扩展名列表（如 ['.txt', '.pdf']）
            max_file_size_mb: 最大允许的文件大小（MB）
        """
        self._allowed_extensions = allowed_extensions
        self._max_file_size_bytes = max_file_size_mb * 1024 * 1024
        self._lock = threading.RLock()
    
    def validate_extension(self, filename: str, allowed_extensions: Optional[List[str]] = None) -> bool:
        """验证文件扩展名
        
        Args:
            filename: 文件名
            allowed_extensions: 可选的临时允许扩展名列表（覆盖默认配置）
            
        Returns:
            如果扩展名允许返回 True，否则返回 False
        """
        with self._lock:
            extensions = allowed_extensions or self._allowed_extensions
            
            # 如果没有配置允许列表，则允许所有
            if extensions is None:
                return True
            
            # 规范化扩展名列表
            normalized_extensions = [ext.lower() if ext.startswith('.') else f'.{ext.lower()}' 
                                     for ext in extensions]
            
            # 获取文件扩展名
            _, ext = os.path.splitext(filename.lower())
            
            return ext in normalized_extensions
    
    def get_file_size(self, file_path: str) -> int:
        """获取文件大小
        
        Args:
            file_path: 文件路径
            
        Returns:
            文件大小（字节），如果文件不存在返回 -1
        """
        try:
            return os.path.getsize(file_path)
        except OSError:
            return -1
    
    def validate_file_size(self, file_path: str, max_size_mb: Optional[int] = None) -> bool:
        """验证文件大小
        
        Args:
            file_path: 文件路径
            max_size_mb: 可选的临时最大大小限制（MB）
            
        Returns:
            如果文件大小在限制内返回 True
        """
        with self._lock:
            max_bytes = (max_size_mb or self._max_file_size_bytes) * 1024 * 1024 \
                        if max_size_mb else self._max_file_size_bytes
            
            size = self.get_file_size(file_path)
            if size < 0:
                return True  # 文件不存在，不检查大小
            
            return size <= max_bytes


# ============================================================================
# FileLockManager 文件锁管理器
# ============================================================================

class FileLockManager:
    """文件锁管理器
    
    使用 threading.RLock 实现线程级锁，支持读锁（共享）和写锁（独占）。
    
    注意：这是一个进程内的线程锁，不适用于多进程场景。
    """
    
    def __init__(self):
        """初始化文件锁管理器"""
        self._read_locks: Dict[str, threading.RLock] = {}
        self._write_locks: Dict[str, threading.RLock] = {}
        self._read_counters: Dict[str, int] = {}
        self._lock = threading.RLock()
    
    def acquire_read_lock(self, file_path: str) -> None:
        """获取读锁（共享）
        
        多个线程可以同时获取同一文件的读锁。
        
        Args:
            file_path: 文件路径
        """
        with self._lock:
            if file_path not in self._read_locks:
                self._read_locks[file_path] = threading.RLock()
                self._read_counters[file_path] = 0
            
            self._read_counters[file_path] += 1
            self._read_locks[file_path].acquire()
    
    def release_read_lock(self, file_path: str) -> None:
        """释放读锁
        
        Args:
            file_path: 文件路径
        """
        with self._lock:
            if file_path in self._read_locks:
                self._read_locks[file_path].release()
                self._read_counters[file_path] -= 1
                
                # 清理不再使用的锁
                if self._read_counters[file_path] <= 0:
                    del self._read_counters[file_path]
                    del self._read_locks[file_path]
    
    def acquire_write_lock(self, file_path: str) -> None:
        """获取写锁（独占）
        
        写锁是独占的，同一时间只有一个线程可以获取写锁。
        
        Args:
            file_path: 文件路径
        """
        with self._lock:
            if file_path not in self._write_locks:
                self._write_locks[file_path] = threading.RLock()
            
            self._write_locks[file_path].acquire()
    
    def release_write_lock(self, file_path: str) -> None:
        """释放写锁
        
        Args:
            file_path: 文件路径
        """
        with self._lock:
            if file_path in self._write_locks:
                self._write_locks[file_path].release()
    
    def release_lock(self, file_path: str, is_write: bool = False) -> None:
        """释放锁（通用方法）
        
        Args:
            file_path: 文件路径
            is_write: 是否是写锁
        """
        if is_write:
            self.release_write_lock(file_path)
        else:
            self.release_read_lock(file_path)


# ============================================================================
# FileInfo 数据类
# ============================================================================

@dataclass
class FileInfo:
    """文件信息数据类
    
    Attributes:
        name: 文件名
        path: 完整路径
        is_dir: 是否是目录
        size: 文件大小（字节）
        modified_time: 最后修改时间（时间戳）
        created_time: 创建时间（时间戳）
    """
    name: str
    path: str
    is_dir: bool
    size: int
    modified_time: float
    created_time: float


# ============================================================================
# FileRouter 核心类
# ============================================================================

class FileRouter:
    """文件路由核心类（单例模式）
    
    作为所有文件操作的唯一入口，提供安全的文件访问控制。
    
    功能：
    - 路径安全验证
    - 权限控制
    - 文件锁管理
    - 回收站功能
    - 审计日志记录
    
    使用示例:
        config = FileRouterConfig(
            allowed_base_dirs=['/data/files'],
            max_file_size_mb=50
        )
        router = create_file_router(config)
        
        # 读取文件
        content = router.read('/data/files/doc.txt', FilePermission.READ_ONLY)
        
        # 写入文件
        router.write('/data/files/doc.txt', b'content', FilePermission.READ_WRITE)
    """
    
    _instance: Optional['FileRouter'] = None
    _lock = threading.RLock()
    
    # 权限允许的操作映射
    PERMISSION_OPERATIONS = {
        FilePermission.READ_ONLY: {'read', 'list', 'exists', 'stat'},
        FilePermission.READ_WRITE: {'read', 'write', 'delete', 'list', 'exists', 'stat', 'move', 'copy'},
        FilePermission.ADMIN: {'read', 'write', 'delete', 'list', 'exists', 'stat', 'move', 'copy', 
                               'restore', 'permanent_delete', 'trash_manage'}
    }
    
    def __new__(cls, *args, **kwargs) -> 'FileRouter':
        """单例模式实现"""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self, config: Optional[FileRouterConfig] = None):
        """初始化文件路由
        
        Args:
            config: 文件路由配置，如果为None则使用默认配置
        """
        with self._lock:
            if self._initialized:
                return
            
            self._config = config or FileRouterConfig()
            
            # 初始化审计日志记录器
            if self._config.audit_enabled:
                self._audit_logger = get_file_audit_logger(
                    log_dir=self._config.audit_log_dir,
                    retention_days=30
                )
            else:
                self._audit_logger = None
            
            # 初始化回收站管理器
            if self._config.trash_enabled:
                self._trash_manager = create_trash_manager(
                    trash_path=self._config.trash_path,
                    retention_days=self._config.trash_retention_days
                )
            else:
                self._trash_manager = None
            
            # 初始化验证器和锁管理器
            self._path_validator = PathValidator(self._config.allowed_base_dirs)
            self._type_validator = FileTypeValidator(
                allowed_extensions=self._config.allowed_extensions,
                max_file_size_mb=self._config.max_file_size_mb
            )
            self._lock_manager = FileLockManager()
            
            self._initialized = True
    
    def _check_permission(self, operation: str, permission: FilePermission) -> None:
        """检查权限
        
        Args:
            operation: 操作类型
            permission: 用户权限
            
        Raises:
            PermissionDeniedError: 权限不足
        """
        allowed_ops = self.PERMISSION_OPERATIONS.get(permission, set())
        if operation not in allowed_ops:
            raise PermissionDeniedError(
                f"权限不足: 操作 '{operation}' 需要更高权限，当前权限为 {permission.name}"
            )
    
    def _log_operation(
        self,
        operation_type: FileOperationType,
        file_path: str,
        result: OperationResult,
        execution_time_ms: float,
        user_context: Optional[str] = None,
        error_message: Optional[str] = None,
        file_size: Optional[int] = None
    ) -> None:
        """记录审计日志
        
        Args:
            operation_type: 操作类型
            file_path: 文件路径
            result: 操作结果
            execution_time_ms: 执行时间（毫秒）
            user_context: 用户上下文
            error_message: 错误信息
            file_size: 文件大小
        """
        if self._audit_logger:
            self._audit_logger.log(
                operation_type=operation_type,
                file_path=file_path,
                result=result,
                execution_time_ms=execution_time_ms,
                user_context=user_context,
                error_message=error_message,
                file_size=file_size
            )
    
    def read(
        self,
        path: str,
        permission: FilePermission,
        user_context: Optional[str] = None
    ) -> bytes:
        """读取文件内容
        
        Args:
            path: 文件路径
            permission: 访问权限
            user_context: 用户上下文信息（用于审计）
            
        Returns:
            文件内容（字节）
            
        Raises:
            PermissionDeniedError: 权限不足
            PathNotAllowedError: 路径不在允许范围内
            FileNotFoundError: 文件不存在
        """
        start_time = time.time()
        
        try:
            # 1. 验证权限
            self._check_permission('read', permission)
            
            # 2. 验证路径安全性
            full_path = self._path_validator.validate_path(path)
            
            # 3. 检查文件是否存在
            if not os.path.exists(full_path):
                raise FileNotFoundError(f"文件不存在: {path}")
            
            if not os.path.isfile(full_path):
                raise FileRouterError(f"路径不是文件: {path}")
            
            # 4. 获取读锁并读取文件
            self._lock_manager.acquire_read_lock(full_path)
            try:
                with open(full_path, 'rb') as f:
                    content = f.read()
                
                file_size = len(content)
                execution_time_ms = (time.time() - start_time) * 1000
                
                # 5. 记录审计日志
                self._log_operation(
                    operation_type=FileOperationType.READ,
                    file_path=full_path,
                    result=OperationResult.SUCCESS,
                    execution_time_ms=execution_time_ms,
                    user_context=user_context,
                    file_size=file_size
                )
                
                return content
            finally:
                self._lock_manager.release_read_lock(full_path)
                
        except Exception as e:
            execution_time_ms = (time.time() - start_time) * 1000
            self._log_operation(
                operation_type=FileOperationType.READ,
                file_path=path,
                result=OperationResult.FAILURE,
                execution_time_ms=execution_time_ms,
                user_context=user_context,
                error_message=str(e)
            )
            raise
    
    def write(
        self,
        path: str,
        content: bytes,
        permission: FilePermission,
        user_context: Optional[str] = None
    ) -> bool:
        """写入文件内容
        
        Args:
            path: 文件路径
            content: 文件内容（字节）
            permission: 访问权限
            user_context: 用户上下文信息（用于审计）
            
        Returns:
            写入成功返回 True
            
        Raises:
            PermissionDeniedError: 权限不足
            PathNotAllowedError: 路径不在允许范围内
            FileTypeNotAllowedError: 文件类型不允许
            FileSizeExceededError: 文件大小超出限制
        """
        start_time = time.time()
        
        try:
            # 1. 验证权限
            self._check_permission('write', permission)
            
            # 2. 验证路径安全性
            full_path = self._path_validator.validate_path(path)
            
            # 3. 验证文件名
            filename = os.path.basename(full_path)
            self._path_validator.validate_filename(filename)
            
            # 4. 验证文件类型
            if not self._type_validator.validate_extension(filename):
                raise FileTypeNotAllowedError(f"文件类型不允许: {filename}")
            
            # 5. 验证文件大小
            content_size = len(content)
            max_size_bytes = self._config.max_file_size_mb * 1024 * 1024
            if content_size > max_size_bytes:
                raise FileSizeExceededError(
                    f"文件大小 {content_size} 字节超出限制 {max_size_bytes} 字节"
                )
            
            # 6. 确保目录存在
            parent_dir = os.path.dirname(full_path)
            if parent_dir and not os.path.exists(parent_dir):
                os.makedirs(parent_dir, exist_ok=True)
            
            # 7. 获取写锁并写入文件
            self._lock_manager.acquire_write_lock(full_path)
            try:
                with open(full_path, 'wb') as f:
                    f.write(content)
                
                execution_time_ms = (time.time() - start_time) * 1000
                
                # 8. 记录审计日志
                self._log_operation(
                    operation_type=FileOperationType.WRITE,
                    file_path=full_path,
                    result=OperationResult.SUCCESS,
                    execution_time_ms=execution_time_ms,
                    user_context=user_context,
                    file_size=content_size
                )
                
                return True
            finally:
                self._lock_manager.release_write_lock(full_path)
                
        except Exception as e:
            execution_time_ms = (time.time() - start_time) * 1000
            self._log_operation(
                operation_type=FileOperationType.WRITE,
                file_path=path,
                result=OperationResult.FAILURE,
                execution_time_ms=execution_time_ms,
                user_context=user_context,
                error_message=str(e)
            )
            raise
    
    def delete(
        self,
        path: str,
        permission: FilePermission,
        immediate: bool = False,
        user_context: Optional[str] = None
    ) -> bool:
        """删除文件
        
        Args:
            path: 文件路径
            permission: 访问权限
            immediate: 是否立即永久删除（不放入回收站）
            user_context: 用户上下文信息（用于审计）
            
        Returns:
            删除成功返回 True
            
        Raises:
            PermissionDeniedError: 权限不足
            FileNotFoundError: 文件不存在
        """
        start_time = time.time()
        
        try:
            # 1. 验证权限
            self._check_permission('delete', permission)
            
            # 2. 验证路径安全性
            full_path = self._path_validator.validate_path(path)
            
            # 3. 检查文件是否存在
            if not os.path.exists(full_path):
                raise FileNotFoundError(f"文件不存在: {path}")
            
            # 4. 获取写锁
            self._lock_manager.acquire_write_lock(full_path)
            try:
                if immediate:
                    # 需要 ADMIN 权限才能立即永久删除
                    if permission != FilePermission.ADMIN:
                        raise PermissionDeniedError("立即永久删除需要 ADMIN 权限")
                    os.remove(full_path)
                else:
                    # 移入回收站
                    if self._trash_manager:
                        self._trash_manager.move_to_trash(full_path, deleted_by=user_context)
                    else:
                        # 回收站未启用，直接删除
                        os.remove(full_path)
                
                execution_time_ms = (time.time() - start_time) * 1000
                
                # 5. 记录审计日志
                self._log_operation(
                    operation_type=FileOperationType.DELETE,
                    file_path=full_path,
                    result=OperationResult.SUCCESS,
                    execution_time_ms=execution_time_ms,
                    user_context=user_context
                )
                
                return True
            finally:
                self._lock_manager.release_write_lock(full_path)
                
        except Exception as e:
            execution_time_ms = (time.time() - start_time) * 1000
            self._log_operation(
                operation_type=FileOperationType.DELETE,
                file_path=path,
                result=OperationResult.FAILURE,
                execution_time_ms=execution_time_ms,
                user_context=user_context,
                error_message=str(e)
            )
            raise
    
    def list_dir(
        self,
        path: str,
        permission: FilePermission,
        user_context: Optional[str] = None
    ) -> List[FileInfo]:
        """列出目录内容
        
        Args:
            path: 目录路径
            permission: 访问权限
            user_context: 用户上下文信息（用于审计）
            
        Returns:
            FileInfo 对象列表
            
        Raises:
            PermissionDeniedError: 权限不足
            FileNotFoundError: 目录不存在
        """
        start_time = time.time()
        
        try:
            # 1. 验证权限
            self._check_permission('list', permission)
            
            # 2. 验证路径安全性
            full_path = self._path_validator.validate_path(path)
            
            # 3. 检查目录是否存在
            if not os.path.exists(full_path):
                raise FileNotFoundError(f"目录不存在: {path}")
            
            if not os.path.isdir(full_path):
                raise FileRouterError(f"路径不是目录: {path}")
            
            # 4. 获取读锁并列出目录
            self._lock_manager.acquire_read_lock(full_path)
            try:
                items = []
                for entry in os.scandir(full_path):
                    stat_info = entry.stat()
                    items.append(FileInfo(
                        name=entry.name,
                        path=entry.path,
                        is_dir=entry.is_dir(),
                        size=stat_info.st_size,
                        modified_time=stat_info.st_mtime,
                        created_time=stat_info.st_ctime
                    ))
                
                execution_time_ms = (time.time() - start_time) * 1000
                
                # 5. 记录审计日志
                self._log_operation(
                    operation_type=FileOperationType.LIST,
                    file_path=full_path,
                    result=OperationResult.SUCCESS,
                    execution_time_ms=execution_time_ms,
                    user_context=user_context
                )
                
                return items
            finally:
                self._lock_manager.release_read_lock(full_path)
                
        except Exception as e:
            execution_time_ms = (time.time() - start_time) * 1000
            self._log_operation(
                operation_type=FileOperationType.LIST,
                file_path=path,
                result=OperationResult.FAILURE,
                execution_time_ms=execution_time_ms,
                user_context=user_context,
                error_message=str(e)
            )
            raise
    
    def exists(self, path: str, permission: FilePermission) -> bool:
        """检查文件或目录是否存在
        
        Args:
            path: 路径
            permission: 访问权限
            
        Returns:
            如果存在返回 True，否则返回 False
        """
        try:
            # 验证权限
            self._check_permission('exists', permission)
            
            # 验证路径安全性
            full_path = self._path_validator.validate_path(path)
            
            return os.path.exists(full_path)
        except (PathNotAllowedError, PathTraversalError):
            return False
    
    def stat(self, path: str, permission: FilePermission) -> Dict[str, Any]:
        """获取文件或目录的统计信息
        
        Args:
            path: 路径
            permission: 访问权限
            
        Returns:
            包含统计信息的字典
            
        Raises:
            PermissionDeniedError: 权限不足
            FileNotFoundError: 文件或目录不存在
        """
        # 验证权限
        self._check_permission('stat', permission)
        
        # 验证路径安全性
        full_path = self._path_validator.validate_path(path)
        
        # 检查文件是否存在
        if not os.path.exists(full_path):
            raise FileNotFoundError(f"文件或目录不存在: {path}")
        
        stat_info = os.stat(full_path)
        
        return {
            'path': full_path,
            'size': stat_info.st_size,
            'modified_time': stat_info.st_mtime,
            'created_time': stat_info.st_ctime,
            'accessed_time': stat_info.st_atime,
            'is_file': os.path.isfile(full_path),
            'is_dir': os.path.isdir(full_path),
            'permissions': oct(stat_info.st_mode)[-3:]
        }
    
    def move(
        self,
        src: str,
        dst: str,
        permission: FilePermission,
        user_context: Optional[str] = None
    ) -> bool:
        """移动文件或目录
        
        Args:
            src: 源路径
            dst: 目标路径
            permission: 访问权限
            user_context: 用户上下文信息（用于审计）
            
        Returns:
            移动成功返回 True
        """
        start_time = time.time()
        
        try:
            # 1. 验证权限
            self._check_permission('move', permission)
            
            # 2. 验证路径安全性
            src_path = self._path_validator.validate_path(src)
            dst_path = self._path_validator.validate_path(dst)
            
            # 3. 检查源文件是否存在
            if not os.path.exists(src_path):
                raise FileNotFoundError(f"源文件不存在: {src}")
            
            # 4. 验证目标文件名
            dst_filename = os.path.basename(dst_path)
            self._path_validator.validate_filename(dst_filename)
            
            # 5. 确保目标目录存在
            dst_dir = os.path.dirname(dst_path)
            if dst_dir and not os.path.exists(dst_dir):
                os.makedirs(dst_dir, exist_ok=True)
            
            # 6. 获取写锁并移动
            self._lock_manager.acquire_write_lock(src_path)
            self._lock_manager.acquire_write_lock(dst_path)
            try:
                shutil.move(src_path, dst_path)
                
                execution_time_ms = (time.time() - start_time) * 1000
                
                # 7. 记录审计日志
                self._log_operation(
                    operation_type=FileOperationType.MOVE,
                    file_path=f"{src_path} -> {dst_path}",
                    result=OperationResult.SUCCESS,
                    execution_time_ms=execution_time_ms,
                    user_context=user_context
                )
                
                return True
            finally:
                self._lock_manager.release_write_lock(dst_path)
                self._lock_manager.release_write_lock(src_path)
                
        except Exception as e:
            execution_time_ms = (time.time() - start_time) * 1000
            self._log_operation(
                operation_type=FileOperationType.MOVE,
                file_path=f"{src} -> {dst}",
                result=OperationResult.FAILURE,
                execution_time_ms=execution_time_ms,
                user_context=user_context,
                error_message=str(e)
            )
            raise
    
    def copy(
        self,
        src: str,
        dst: str,
        permission: FilePermission,
        user_context: Optional[str] = None
    ) -> bool:
        """复制文件或目录
        
        Args:
            src: 源路径
            dst: 目标路径
            permission: 访问权限
            user_context: 用户上下文信息（用于审计）
            
        Returns:
            复制成功返回 True
        """
        start_time = time.time()
        
        try:
            # 1. 验证权限
            self._check_permission('copy', permission)
            
            # 2. 验证路径安全性
            src_path = self._path_validator.validate_path(src)
            dst_path = self._path_validator.validate_path(dst)
            
            # 3. 检查源文件是否存在
            if not os.path.exists(src_path):
                raise FileNotFoundError(f"源文件不存在: {src}")
            
            # 4. 验证目标文件名
            dst_filename = os.path.basename(dst_path)
            self._path_validator.validate_filename(dst_filename)
            
            # 5. 确保目标目录存在
            dst_dir = os.path.dirname(dst_path)
            if dst_dir and not os.path.exists(dst_dir):
                os.makedirs(dst_dir, exist_ok=True)
            
            # 6. 获取锁并复制
            self._lock_manager.acquire_read_lock(src_path)
            self._lock_manager.acquire_write_lock(dst_path)
            try:
                if os.path.isdir(src_path):
                    shutil.copytree(src_path, dst_path)
                else:
                    shutil.copy2(src_path, dst_path)
                
                execution_time_ms = (time.time() - start_time) * 1000
                
                # 7. 记录审计日志
                self._log_operation(
                    operation_type=FileOperationType.COPY,
                    file_path=f"{src_path} -> {dst_path}",
                    result=OperationResult.SUCCESS,
                    execution_time_ms=execution_time_ms,
                    user_context=user_context
                )
                
                return True
            finally:
                self._lock_manager.release_write_lock(dst_path)
                self._lock_manager.release_read_lock(src_path)
                
        except Exception as e:
            execution_time_ms = (time.time() - start_time) * 1000
            self._log_operation(
                operation_type=FileOperationType.COPY,
                file_path=f"{src} -> {dst}",
                result=OperationResult.FAILURE,
                execution_time_ms=execution_time_ms,
                user_context=user_context,
                error_message=str(e)
            )
            raise
    
    def restore_from_trash(
        self,
        trash_id: str,
        permission: FilePermission,
        user_context: Optional[str] = None
    ) -> bool:
        """从回收站恢复文件
        
        Args:
            trash_id: 回收站项目ID
            permission: 访问权限（需要 ADMIN）
            user_context: 用户上下文信息（用于审计）
            
        Returns:
            恢复成功返回 True
            
        Raises:
            PermissionDeniedError: 权限不足
            TrashItemNotFoundError: 回收站项目不存在
        """
        start_time = time.time()
        
        try:
            # 1. 验证权限
            self._check_permission('restore', permission)
            
            if not self._trash_manager:
                raise FileRouterError("回收站功能未启用")
            
            # 2. 恢复文件
            result = self._trash_manager.restore_from_trash(trash_id)
            
            execution_time_ms = (time.time() - start_time) * 1000
            
            # 3. 记录审计日志
            self._log_operation(
                operation_type=FileOperationType.RESTORE,
                file_path=f"trash_id:{trash_id}",
                result=OperationResult.SUCCESS,
                execution_time_ms=execution_time_ms,
                user_context=user_context
            )
            
            return result
            
        except Exception as e:
            execution_time_ms = (time.time() - start_time) * 1000
            self._log_operation(
                operation_type=FileOperationType.RESTORE,
                file_path=f"trash_id:{trash_id}",
                result=OperationResult.FAILURE,
                execution_time_ms=execution_time_ms,
                user_context=user_context,
                error_message=str(e)
            )
            raise
    
    def get_trash_items(self, permission: FilePermission) -> List[TrashItem]:
        """获取回收站中的所有项目
        
        Args:
            permission: 访问权限（需要 ADMIN）
            
        Returns:
            TrashItem 列表
            
        Raises:
            PermissionDeniedError: 权限不足
        """
        # 验证权限
        self._check_permission('trash_manage', permission)
        
        if not self._trash_manager:
            return []
        
        return self._trash_manager.get_trash_items()
    
    def force_delete_permanent(
        self,
        path: str,
        permission: FilePermission,
        user_context: Optional[str] = None
    ) -> bool:
        """强制永久删除文件（不经过回收站）
        
        Args:
            path: 文件路径
            permission: 访问权限（需要 ADMIN）
            user_context: 用户上下文信息（用于审计）
            
        Returns:
            删除成功返回 True
            
        Raises:
            PermissionDeniedError: 权限不足
        """
        return self.delete(path, permission, immediate=True, user_context=user_context)
    
    @contextmanager
    def open_file(
        self,
        path: str,
        mode: str,
        permission: FilePermission,
        user_context: Optional[str] = None
    ):
        """上下文管理器方式打开文件
        
        Args:
            path: 文件路径
            mode: 打开模式（'r', 'rb', 'w', 'wb', 'a', 'ab'等）
            permission: 访问权限
            user_context: 用户上下文信息（用于审计）
            
        Yields:
            文件对象
            
        Example:
            with router.open_file('/path/to/file.txt', 'rb', FilePermission.READ_ONLY) as f:
                content = f.read()
        """
        full_path = None
        start_time = time.time()
        is_write = 'w' in mode or 'a' in mode
        
        try:
            # 验证权限
            if is_write:
                self._check_permission('write', permission)
                op_type = FileOperationType.WRITE
            else:
                self._check_permission('read', permission)
                op_type = FileOperationType.READ
            
            # 验证路径
            full_path = self._path_validator.validate_path(path)
            
            # 获取锁
            if is_write:
                self._lock_manager.acquire_write_lock(full_path)
            else:
                self._lock_manager.acquire_read_lock(full_path)
            
            # 打开文件
            f = open(full_path, mode)
            
            try:
                yield f
            finally:
                f.close()
                
                # 记录成功日志
                execution_time_ms = (time.time() - start_time) * 1000
                self._log_operation(
                    operation_type=op_type,
                    file_path=full_path,
                    result=OperationResult.SUCCESS,
                    execution_time_ms=execution_time_ms,
                    user_context=user_context
                )
                
                # 释放锁
                if is_write:
                    self._lock_manager.release_write_lock(full_path)
                else:
                    self._lock_manager.release_read_lock(full_path)
                    
        except Exception as e:
            execution_time_ms = (time.time() - start_time) * 1000
            self._log_operation(
                operation_type=FileOperationType.READ if not is_write else FileOperationType.WRITE,
                file_path=path if full_path is None else full_path,
                result=OperationResult.FAILURE,
                execution_time_ms=execution_time_ms,
                user_context=user_context,
                error_message=str(e)
            )
            
            # 确保释放锁
            if full_path:
                if is_write:
                    self._lock_manager.release_write_lock(full_path)
                else:
                    self._lock_manager.release_read_lock(full_path)
            
            raise


# ============================================================================
# 便捷函数
# ============================================================================

def create_file_router(config: Optional[FileRouterConfig] = None) -> FileRouter:
    """创建文件路由的便捷函数
    
    创建并返回 FileRouter 的单例实例。
    
    Args:
        config: 文件路由配置，如果为None则使用默认配置
        
    Returns:
        FileRouter 实例
        
    Example:
        config = FileRouterConfig(
            allowed_base_dirs=['/data/files', '/tmp/uploads'],
            max_file_size_mb=50,
            allowed_extensions=['.txt', '.pdf', '.jpg']
        )
        router = create_file_router(config)
    """
    return FileRouter(config)


# ============================================================================
# 示例用法
# ============================================================================

if __name__ == "__main__":
    import tempfile
    import shutil
    
    # 创建临时目录用于测试
    temp_dir = tempfile.mkdtemp()
    
    try:
        print("=" * 60)
        print("文件路由核心模块测试")
        print("=" * 60)
        
        # 创建配置
        config = FileRouterConfig(
            allowed_base_dirs=[temp_dir],
            trash_enabled=True,
            trash_path=os.path.join(temp_dir, '.trash'),
            audit_enabled=True,
            max_file_size_mb=10,
            allowed_extensions=['.txt', '.log']
        )
        
        # 创建文件路由
        router = create_file_router(config)
        
        # 测试1: 写入文件
        print("\n[测试1] 写入文件")
        test_file = os.path.join(temp_dir, 'test.txt')
        try:
            result = router.write(
                test_file,
                b"Hello, World!\nThis is a test file.",
                FilePermission.READ_WRITE,
                user_context="admin"
            )
            print(f"  写入结果: {result}")
        except Exception as e:
            print(f"  写入失败: {e}")
        
        # 测试2: 读取文件
        print("\n[测试2] 读取文件")
        try:
            content = router.read(test_file, FilePermission.READ_ONLY, user_context="guest")
            print(f"  读取内容: {content.decode('utf-8')[:50]}...")
        except Exception as e:
            print(f"  读取失败: {e}")
        
        # 测试3: 列出目录
        print("\n[测试3] 列出目录")
        try:
            items = router.list_dir(temp_dir, FilePermission.READ_ONLY)
            print(f"  目录内容 ({len(items)} 项):")
            for item in items:
                item_type = "目录" if item.is_dir else "文件"
                print(f"    - {item.name} ({item_type}, {item.size} bytes)")
        except Exception as e:
            print(f"  列出目录失败: {e}")
        
        # 测试4: 检查文件存在
        print("\n[测试4] 检查文件存在")
        exists = router.exists(test_file, FilePermission.READ_ONLY)
        print(f"  文件存在: {exists}")
        
        # 测试5: 获取文件统计信息
        print("\n[测试5] 获取文件统计信息")
        try:
            stat_info = router.stat(test_file, FilePermission.READ_ONLY)
            print(f"  文件大小: {stat_info['size']} bytes")
            print(f"  是否文件: {stat_info['is_file']}")
            print(f"  修改时间: {datetime.fromtimestamp(stat_info['modified_time'])}")
        except Exception as e:
            print(f"  获取统计信息失败: {e}")
        
        # 测试6: 复制文件
        print("\n[测试6] 复制文件")
        copy_file = os.path.join(temp_dir, 'test_copy.txt')
        try:
            result = router.copy(test_file, copy_file, FilePermission.READ_WRITE, user_context="admin")
            print(f"  复制结果: {result}")
            print(f"  复制后文件存在: {os.path.exists(copy_file)}")
        except Exception as e:
            print(f"  复制失败: {e}")
        
        # 测试7: 移动文件
        print("\n[测试7] 移动文件")
        moved_file = os.path.join(temp_dir, 'test_moved.txt')
        try:
            result = router.move(copy_file, moved_file, FilePermission.READ_WRITE, user_context="admin")
            print(f"  移动结果: {result}")
            print(f"  原文件存在: {os.path.exists(copy_file)}")
            print(f"  新文件存在: {os.path.exists(moved_file)}")
        except Exception as e:
            print(f"  移动失败: {e}")
        
        # 测试8: 使用上下文管理器
        print("\n[测试8] 使用上下文管理器读取文件")
        try:
            with router.open_file(test_file, 'rb', FilePermission.READ_ONLY) as f:
                content = f.read()
                print(f"  读取内容长度: {len(content)} bytes")
        except Exception as e:
            print(f"  上下文管理器读取失败: {e}")
        
        # 测试9: 删除文件（移入回收站）
        print("\n[测试9] 删除文件（移入回收站）")
        try:
            result = router.delete(moved_file, FilePermission.READ_WRITE, user_context="admin")
            print(f"  删除结果: {result}")
            print(f"  文件存在: {os.path.exists(moved_file)}")
        except Exception as e:
            print(f"  删除失败: {e}")
        
        # 测试10: 权限不足测试
        print("\n[测试10] 权限不足测试（只读权限尝试写入）")
        try:
            router.write(
                os.path.join(temp_dir, 'forbidden.txt'),
                b"should not be written",
                FilePermission.READ_ONLY
            )
            print("  错误: 应该抛出权限错误")
        except PermissionDeniedError as e:
            print(f"  预期的权限错误: {e}")
        
        # 测试11: 路径遍历攻击防护
        print("\n[测试11] 路径遍历攻击防护")
        try:
            router.read(os.path.join(temp_dir, '../../../etc/passwd'), FilePermission.READ_ONLY)
            print("  错误: 应该抛出路径错误")
        except (PathNotAllowedError, PathTraversalError) as e:
            print(f"  预期的路径错误: {e}")
        
        # 测试12: 文件类型验证
        print("\n[测试12] 文件类型验证")
        try:
            router.write(
                os.path.join(temp_dir, 'test.exe'),
                b"malicious content",
                FilePermission.READ_WRITE
            )
            print("  错误: 应该抛出文件类型错误")
        except FileTypeNotAllowedError as e:
            print(f"  预期的文件类型错误: {e}")
        
        print("\n" + "=" * 60)
        print("测试完成！")
        print("=" * 60)
        
    finally:
        # 清理临时目录
        shutil.rmtree(temp_dir, ignore_errors=True)
        print(f"\n清理临时目录: {temp_dir}")
