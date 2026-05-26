# -*- coding: utf-8 -*-
"""
文件审计日志系统模块

功能：
1. 文件审计日志条目结构 FileAuditLogEntry
2. 文件路径敏感数据脱敏器 FilePathMasker
3. 文件审计日志记录器 FileAuditLogger（单例模式）
4. 日志轮转机制（按日期）
5. 日志清理机制（默认30天）

日志存储路径: logs/file_audit_YYYYMMDD.log
保留期: 30天
"""

import os
import re
import json
import hashlib
import logging
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, Any, List, Union
from dataclasses import dataclass, asdict
from enum import Enum


class FileOperationType(Enum):
    """文件操作类型枚举"""
    READ = "read"
    WRITE = "write"
    DELETE = "delete"
    LIST = "list"
    MOVE = "move"
    COPY = "copy"
    RESTORE = "restore"


class OperationResult(Enum):
    """操作结果枚举"""
    SUCCESS = "SUCCESS"
    FAILURE = "FAILURE"


@dataclass
class FileAuditLogEntry:
    """
    文件审计日志条目结构

    Attributes:
        timestamp: 操作时间戳（ISO格式）
        operation_type: 操作类型（read/write/delete/list/move/copy/restore）
        file_path: 文件路径（脱敏后）
        user_context: 用户上下文信息（可选）
        result: 执行结果（SUCCESS/FAILURE）
        error_message: 错误信息（失败时）
        file_size: 文件大小（字节，可选）
        execution_time_ms: 执行耗时（毫秒）
    """
    timestamp: str
    operation_type: str
    file_path: str
    result: str
    execution_time_ms: float
    user_context: Optional[str] = None
    error_message: Optional[str] = None
    file_size: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return asdict(self)

    def to_json(self) -> str:
        """转换为JSON字符串"""
        return json.dumps(self.to_dict(), ensure_ascii=False, default=str)


class FilePathMasker:
    """
    文件路径敏感数据脱敏器

    支持脱敏的路径类型：
    - 用户目录：包含用户名、home目录等
    - 敏感关键词：password, secret, token, key, private, credential等
    - 系统路径：Windows系统目录、Program Files等
    - 配置文件：包含敏感配置的路径
    """

    # 敏感路径模式（不区分大小写）
    SENSITIVE_PATH_PATTERNS = [
        # 用户相关路径
        r'(?i)(Users|home|Documents and Settings)[/\\][^/\\]+',  # Windows/Linux用户目录
        r'(?i)(AppData|Application Data)[/\\][^/\\]+[/\\][^/\\]+',  # 应用数据
        # 敏感关键词
        r'(?i)(password|passwd|pwd|pass)',
        r'(?i)(secret|private|confidential)',
        r'(?i)(token|api_key|apikey|secret_key|secretkey)',
        r'(?i)(credential|auth|certificate|cert)',
        r'(?i)(ssh|pgp|gpg|ssl)',
        # 配置文件
        r'(?i)\.env',
        r'(?i)config\.',
        r'(?i)credentials\.',
        # 系统敏感路径
        r'(?i)(Windows|System32|SysWOW64)',
        r'(?i)(Program Files|ProgramData)',
    ]

    # 敏感文件扩展名
    SENSITIVE_EXTENSIONS = [
        '.pem', '.key', '.p12', '.pfx', '.crt', '.cer',
        '.env', '.config', '.ini', '.secrets'
    ]

    MASK = "***MASKED***"
    PATH_MASK = "***PATH***"
    HASH_MASK = "***HASH:{}***"

    @classmethod
    def is_sensitive_path(cls, path: str) -> bool:
        """
        检测路径是否包含敏感信息

        Args:
            path: 文件路径

        Returns:
            是否为敏感路径
        """
        if not path:
            return False

        # 检查路径模式
        for pattern in cls.SENSITIVE_PATH_PATTERNS:
            if re.search(pattern, path):
                return True

        # 检查文件扩展名
        path_lower = path.lower()
        for ext in cls.SENSITIVE_EXTENSIONS:
            if path_lower.endswith(ext):
                return True

        return False

    @classmethod
    def mask_path(cls, path: str) -> str:
        """
        脱敏路径中的敏感部分

        Args:
            path: 原始文件路径

        Returns:
            脱敏后的路径
        """
        if not path:
            return path

        masked_path = path

        # 脱敏用户目录（保留结构，隐藏用户名）
        masked_path = re.sub(
            r'(?i)(Users[/\\]|home[/\\]|Documents and Settings[/\\])([^/\\]+)',
            r'\1***USER***',
            masked_path
        )

        # 脱敏AppData路径
        masked_path = re.sub(
            r'(?i)(AppData|Application Data)[/\\]([^/\\]+)[/\\]([^/\\]+)',
            r'\1/***VENDOR***/***APP***',
            masked_path
        )

        # 脱敏包含敏感关键词的文件名
        masked_path = re.sub(
            r'(?i)([^/\\]*)(password|passwd|pwd|secret|token|api_key|credential)([^/\\]*)',
            r'\1***SENSITIVE***\3',
            masked_path
        )

        # 脱敏敏感扩展名文件的内容部分（保留扩展名）
        for ext in cls.SENSITIVE_EXTENSIONS:
            pattern = rf'(?i)([^/\\]+)({re.escape(ext)})'
            masked_path = re.sub(pattern, rf'***FILE***\2', masked_path)

        return masked_path

    @classmethod
    def mask_value(cls, value: Any, use_hash: bool = False) -> str:
        """
        脱敏值

        Args:
            value: 原始值
            use_hash: 是否使用哈希值代替（用于需要追踪但不暴露的场景）

        Returns:
            脱敏后的值
        """
        if value is None:
            return "NULL"

        if isinstance(value, str):
            # 如果是路径，使用路径脱敏
            if os.path.sep in value or '/' in value:
                return cls.mask_path(value)

        if use_hash:
            value_str = str(value)
            hash_value = hashlib.sha256(value_str.encode()).hexdigest()[:16]
            return cls.HASH_MASK.format(hash_value)

        return cls.MASK

    @classmethod
    def mask_dict(cls, data: Dict[str, Any], use_hash: bool = False) -> Dict[str, Any]:
        """
        对字典中的敏感字段进行脱敏

        Args:
            data: 原始字典
            use_hash: 是否使用哈希值

        Returns:
            脱敏后的字典
        """
        if not isinstance(data, dict):
            return data

        masked_data = {}
        for key, value in data.items():
            # 检查键名是否包含敏感信息
            if cls.is_sensitive_path(key):
                masked_data[key] = cls.mask_value(value, use_hash)
            elif isinstance(value, dict):
                masked_data[key] = cls.mask_dict(value, use_hash)
            elif isinstance(value, list):
                masked_data[key] = [
                    cls.mask_dict(item, use_hash) if isinstance(item, dict) else
                    cls.mask_value(item, use_hash) if isinstance(item, str) and cls.is_sensitive_path(item)
                    else item
                    for item in value
                ]
            elif isinstance(value, str) and cls.is_sensitive_path(value):
                masked_data[key] = cls.mask_value(value, use_hash)
            else:
                masked_data[key] = value

        return masked_data


class FileAuditLogger:
    """
    文件审计日志记录器

    功能：
    - 记录文件操作审计日志
    - 自动日志轮转（按日期）
    - 自动清理过期日志（默认30天）
    - JSON格式输出
    - 线程安全
    """

    DEFAULT_LOG_DIR = "logs"
    DEFAULT_RETENTION_DAYS = 30
    DEFAULT_LOG_FORMAT = "%(message)s"

    _instance: Optional['FileAuditLogger'] = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        """单例模式实现"""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(
        self,
        log_dir: str = DEFAULT_LOG_DIR,
        retention_days: int = DEFAULT_RETENTION_DAYS,
        enable_console_output: bool = False
    ):
        """
        初始化文件审计日志记录器

        Args:
            log_dir: 日志存储目录
            retention_days: 日志保留天数
            enable_console_output: 是否同时输出到控制台
        """
        # 避免重复初始化
        if self._initialized:
            return

        self.log_dir = Path(log_dir)
        self.retention_days = retention_days
        self.enable_console_output = enable_console_output
        self._current_date: Optional[str] = None
        self._logger: Optional[logging.Logger] = None
        self._file_handler: Optional[logging.FileHandler] = None
        self._lock = threading.Lock()

        # 创建日志目录
        self._ensure_log_dir()

        # 初始化日志记录器
        self._setup_logger()

        self._initialized = True

    def _ensure_log_dir(self) -> None:
        """确保日志目录存在"""
        try:
            self.log_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            raise RuntimeError(f"无法创建日志目录 {self.log_dir}: {e}")

    def _get_log_file_path(self, date_str: Optional[str] = None) -> Path:
        """
        获取日志文件路径

        Args:
            date_str: 日期字符串（YYYYMMDD），默认为今天

        Returns:
            日志文件路径
        """
        if date_str is None:
            date_str = datetime.now().strftime("%Y%m%d")
        return self.log_dir / f"file_audit_{date_str}.log"

    def _setup_logger(self) -> None:
        """设置日志记录器"""
        self._logger = logging.getLogger("FileAuditLogger")
        self._logger.setLevel(logging.INFO)
        self._logger.propagate = False

        # 清除现有处理器
        self._logger.handlers.clear()

        # 设置文件处理器
        self._rotate_log_file()

        # 可选：控制台输出
        if self.enable_console_output:
            console_handler = logging.StreamHandler()
            console_handler.setLevel(logging.INFO)
            console_formatter = logging.Formatter(
                "[%(asctime)s] %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S"
            )
            console_handler.setFormatter(console_formatter)
            self._logger.addHandler(console_handler)

    def _rotate_log_file(self) -> None:
        """
        轮转日志文件

        按日期分割日志文件，每天一个文件
        """
        current_date = datetime.now().strftime("%Y%m%d")

        # 如果日期未变化，不需要轮转
        if self._current_date == current_date and self._file_handler is not None:
            return

        # 移除旧处理器
        if self._file_handler is not None:
            self._logger.removeHandler(self._file_handler)
            self._file_handler.close()

        # 创建新文件处理器
        log_file = self._get_log_file_path(current_date)
        self._file_handler = logging.FileHandler(
            log_file,
            encoding="utf-8",
            mode="a"
        )
        self._file_handler.setLevel(logging.INFO)

        # 使用JSON格式以便后续分析
        formatter = logging.Formatter(self.DEFAULT_LOG_FORMAT)
        self._file_handler.setFormatter(formatter)

        self._logger.addHandler(self._file_handler)
        self._current_date = current_date

    def _clean_old_logs(self) -> None:
        """
        清理过期日志文件

        删除超过保留期的旧日志文件
        """
        if not self.log_dir.exists():
            return

        cutoff_date = datetime.now() - timedelta(days=self.retention_days)

        try:
            for log_file in self.log_dir.glob("file_audit_*.log"):
                try:
                    # 从文件名提取日期
                    date_match = re.search(r"file_audit_(\d{8})\.log", log_file.name)
                    if date_match:
                        file_date = datetime.strptime(date_match.group(1), "%Y%m%d")
                        if file_date < cutoff_date:
                            log_file.unlink()
                except Exception:
                    # 忽略单个文件处理错误
                    pass
        except Exception as e:
            # 记录清理错误但不影响主流程
            if self.enable_console_output:
                print(f"[FileAuditLogger] 清理旧日志时出错: {e}")

    def _check_rotation(self) -> None:
        """检查并执行日志轮转"""
        current_date = datetime.now().strftime("%Y%m%d")
        if self._current_date != current_date:
            with self._lock:
                if self._current_date != current_date:
                    self._rotate_log_file()
                    self._clean_old_logs()

    def log(
        self,
        operation_type: Union[FileOperationType, str],
        file_path: str,
        result: OperationResult,
        execution_time_ms: float,
        user_context: Optional[str] = None,
        error_message: Optional[str] = None,
        file_size: Optional[int] = None,
        extra_data: Optional[Dict[str, Any]] = None
    ) -> FileAuditLogEntry:
        """
        记录文件审计日志

        Args:
            operation_type: 操作类型
            file_path: 文件路径（会被脱敏）
            result: 执行结果
            execution_time_ms: 执行耗时（毫秒）
            user_context: 用户上下文信息
            error_message: 错误信息
            file_size: 文件大小（字节）
            extra_data: 额外数据（会被脱敏）

        Returns:
            审计日志条目对象
        """
        # 检查并执行日志轮转
        self._check_rotation()

        # 转换操作类型
        if isinstance(operation_type, FileOperationType):
            operation_type_str = operation_type.value
        else:
            operation_type_str = operation_type.lower()

        # 脱敏文件路径
        masked_path = FilePathMasker.mask_path(file_path)

        # 脱敏额外数据
        masked_extra = None
        if extra_data:
            masked_extra = FilePathMasker.mask_dict(extra_data)

        # 创建日志条目
        entry = FileAuditLogEntry(
            timestamp=datetime.now().isoformat(),
            operation_type=operation_type_str,
            file_path=masked_path,
            result=result.value,
            execution_time_ms=execution_time_ms,
            user_context=user_context,
            error_message=error_message,
            file_size=file_size
        )

        # 构建日志内容
        log_data = entry.to_dict()
        if masked_extra:
            log_data["extra"] = masked_extra

        # 写入日志
        log_line = json.dumps(log_data, ensure_ascii=False, default=str)
        self._logger.info(log_line)

        return entry

    def log_success(
        self,
        operation_type: Union[FileOperationType, str],
        file_path: str,
        execution_time_ms: float,
        **kwargs
    ) -> FileAuditLogEntry:
        """
        记录成功的文件操作

        Args:
            operation_type: 操作类型
            file_path: 文件路径
            execution_time_ms: 执行耗时（毫秒）
            **kwargs: 其他可选参数

        Returns:
            审计日志条目对象
        """
        return self.log(
            operation_type=operation_type,
            file_path=file_path,
            result=OperationResult.SUCCESS,
            execution_time_ms=execution_time_ms,
            **kwargs
        )

    def log_failure(
        self,
        operation_type: Union[FileOperationType, str],
        file_path: str,
        execution_time_ms: float,
        error_message: str,
        **kwargs
    ) -> FileAuditLogEntry:
        """
        记录失败的文件操作

        Args:
            operation_type: 操作类型
            file_path: 文件路径
            execution_time_ms: 执行耗时（毫秒）
            error_message: 错误信息
            **kwargs: 其他可选参数

        Returns:
            审计日志条目对象
        """
        return self.log(
            operation_type=operation_type,
            file_path=file_path,
            result=OperationResult.FAILURE,
            execution_time_ms=execution_time_ms,
            error_message=error_message,
            **kwargs
        )

    def get_recent_logs(
        self,
        days: int = 7,
        operation_type: Optional[str] = None,
        result: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        获取最近的审计日志

        Args:
            days: 查询最近几天的日志
            operation_type: 按操作类型过滤
            result: 按结果过滤

        Returns:
            日志条目列表
        """
        logs = []
        cutoff_date = datetime.now() - timedelta(days=days)

        try:
            for log_file in sorted(self.log_dir.glob("file_audit_*.log"), reverse=True):
                try:
                    # 从文件名提取日期
                    date_match = re.search(r"file_audit_(\d{8})\.log", log_file.name)
                    if date_match:
                        file_date = datetime.strptime(date_match.group(1), "%Y%m%d")
                        if file_date < cutoff_date:
                            continue

                    # 读取日志文件
                    with open(log_file, "r", encoding="utf-8") as f:
                        for line in f:
                            line = line.strip()
                            if not line:
                                continue

                            try:
                                entry = json.loads(line)

                                # 应用过滤器
                                if operation_type and entry.get("operation_type") != operation_type:
                                    continue
                                if result and entry.get("result") != result:
                                    continue

                                logs.append(entry)
                            except json.JSONDecodeError:
                                continue

                except Exception:
                    continue

        except Exception as e:
            if self.enable_console_output:
                print(f"[FileAuditLogger] 读取日志时出错: {e}")

        # 按时间戳排序（最新的在前）
        logs.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
        return logs

    def get_log_stats(self, days: int = 7) -> Dict[str, Any]:
        """
        获取日志统计信息

        Args:
            days: 统计最近几天的日志

        Returns:
            统计信息字典
        """
        logs = self.get_recent_logs(days=days)

        stats = {
            "total_operations": len(logs),
            "operation_types": {},
            "results": {"SUCCESS": 0, "FAILURE": 0},
            "avg_execution_time_ms": 0.0,
            "date_range": {"start": None, "end": None},
            "total_bytes_processed": 0
        }

        total_time = 0.0
        total_bytes = 0
        timestamps = []

        for log in logs:
            # 操作类型统计
            op_type = log.get("operation_type", "UNKNOWN")
            stats["operation_types"][op_type] = stats["operation_types"].get(op_type, 0) + 1

            # 结果统计
            result = log.get("result", "UNKNOWN")
            if result in stats["results"]:
                stats["results"][result] += 1

            # 执行时间
            exec_time = log.get("execution_time_ms", 0)
            if exec_time:
                total_time += exec_time

            # 文件大小统计
            file_size = log.get("file_size")
            if file_size:
                total_bytes += file_size

            # 时间戳
            ts = log.get("timestamp")
            if ts:
                timestamps.append(ts)

        # 平均执行时间
        if logs:
            stats["avg_execution_time_ms"] = round(total_time / len(logs), 2)

        # 总字节数
        stats["total_bytes_processed"] = total_bytes

        # 时间范围
        if timestamps:
            stats["date_range"]["start"] = min(timestamps)
            stats["date_range"]["end"] = max(timestamps)

        return stats

    def close(self) -> None:
        """关闭日志记录器"""
        if self._file_handler:
            self._file_handler.close()
            self._logger.removeHandler(self._file_handler)
            self._file_handler = None


# 便捷函数：获取全局文件审计日志记录器实例
def get_file_audit_logger(
    log_dir: str = "logs",
    retention_days: int = 30,
    enable_console_output: bool = False
) -> FileAuditLogger:
    """
    获取文件审计日志记录器实例（单例）

    Args:
        log_dir: 日志存储目录
        retention_days: 日志保留天数
        enable_console_output: 是否同时输出到控制台

    Returns:
        FileAuditLogger实例
    """
    return FileAuditLogger(
        log_dir=log_dir,
        retention_days=retention_days,
        enable_console_output=enable_console_output
    )


# 上下文管理器支持
class FileAuditContext:
    """
    文件审计日志上下文管理器

    用于自动记录文件操作的开始和结束
    """

    def __init__(
        self,
        logger: FileAuditLogger,
        operation_type: Union[FileOperationType, str],
        file_path: str,
        user_context: Optional[str] = None,
        file_size: Optional[int] = None
    ):
        self.logger = logger
        self.operation_type = operation_type
        self.file_path = file_path
        self.user_context = user_context
        self.file_size = file_size
        self.start_time: Optional[datetime] = None
        self.entry: Optional[FileAuditLogEntry] = None

    def __enter__(self) -> 'FileAuditContext':
        """进入上下文，记录开始时间"""
        self.start_time = datetime.now()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """退出上下文，记录日志"""
        if self.start_time is None:
            return

        execution_time_ms = (datetime.now() - self.start_time).total_seconds() * 1000

        if exc_type is None:
            # 成功
            self.entry = self.logger.log_success(
                operation_type=self.operation_type,
                file_path=self.file_path,
                execution_time_ms=execution_time_ms,
                user_context=self.user_context,
                file_size=self.file_size
            )
        else:
            # 失败
            error_msg = str(exc_val) if exc_val else "Unknown error"
            self.entry = self.logger.log_failure(
                operation_type=self.operation_type,
                file_path=self.file_path,
                execution_time_ms=execution_time_ms,
                error_message=error_msg,
                user_context=self.user_context,
                file_size=self.file_size
            )


# 示例用法
if __name__ == "__main__":
    # 创建文件审计日志记录器（启用控制台输出以便测试）
    audit_logger = get_file_audit_logger(enable_console_output=True)

    print("=" * 60)
    print("文件审计日志系统测试")
    print("=" * 60)

    # 测试1：记录成功的读取操作
    print("\n[测试1] 记录成功的文件读取操作")
    audit_logger.log_success(
        operation_type=FileOperationType.READ,
        file_path="E:\\Projects\\data\\report.pdf",
        execution_time_ms=125.5,
        user_context="admin",
        file_size=1024000
    )

    # 测试2：记录包含敏感路径的写入操作
    print("\n[测试2] 记录包含敏感路径的写入操作（自动脱敏）")
    audit_logger.log_success(
        operation_type=FileOperationType.WRITE,
        file_path="C:\\Users\\john_doe\\AppData\\Local\\MyApp\\config\\secret.key",
        execution_time_ms=45.2,
        user_context="admin",
        file_size=2048
    )

    # 测试3：记录删除操作
    print("\n[测试3] 记录文件删除操作")
    audit_logger.log_success(
        operation_type=FileOperationType.DELETE,
        file_path="E:\\Temp\\old_backup.zip",
        execution_time_ms=15.8,
        user_context="admin"
    )

    # 测试4：记录失败的复制操作
    print("\n[测试4] 记录失败的文件复制操作")
    audit_logger.log_failure(
        operation_type=FileOperationType.COPY,
        file_path="E:\\Protected\\restricted.doc",
        execution_time_ms=5.0,
        error_message="Access denied: insufficient permissions",
        user_context="guest"
    )

    # 测试5：使用上下文管理器
    print("\n[测试5] 使用上下文管理器记录操作")
    try:
        with FileAuditContext(
            logger=audit_logger,
            operation_type=FileOperationType.MOVE,
            file_path="E:\\Source\\data.txt",
            user_context="admin",
            file_size=51200
        ):
            # 模拟文件操作
            import time
            time.sleep(0.1)
            print("  模拟文件移动操作完成")
    except Exception as e:
        print(f"  操作失败: {e}")

    # 测试6：测试路径脱敏功能
    print("\n[测试6] 敏感路径脱敏测试")
    test_paths = [
        "C:\\Users\\john_doe\\Documents\\file.txt",
        "/home/alice/.ssh/id_rsa",
        "C:\\ProgramData\\MyApp\\passwords.env",
        "E:\\Projects\\normal_file.txt"
    ]
    for path in test_paths:
        is_sensitive = FilePathMasker.is_sensitive_path(path)
        masked = FilePathMasker.mask_path(path)
        print(f"  原始: {path}")
        print(f"  敏感: {is_sensitive}, 脱敏后: {masked}")
        print()

    # 测试7：获取统计信息
    print("\n[测试7] 获取日志统计信息")
    stats = audit_logger.get_log_stats(days=7)
    print(f"  统计信息: {json.dumps(stats, indent=2, ensure_ascii=False)}")

    # 测试8：获取最近日志
    print("\n[测试8] 获取最近日志条目")
    recent_logs = audit_logger.get_recent_logs(days=7)
    print(f"  最近 {len(recent_logs)} 条日志")
    for i, log in enumerate(recent_logs[:3], 1):
        print(f"  [{i}] {log.get('operation_type')} - {log.get('result')} - {log.get('file_path', '')}")

    print("\n" + "=" * 60)
    print("测试完成！日志文件保存在: logs/file_audit_YYYYMMDD.log")
    print("=" * 60)

    # 关闭日志记录器
    audit_logger.close()
