# -*- coding: utf-8 -*-
"""
数据库审计日志系统模块

功能：
1. 审计日志记录器类 DBAuditLogger
2. 敏感数据脱敏函数
3. 审计日志条目结构
4. 日志轮转机制
5. 日志清理机制

日志存储路径: logs/db_audit_YYYYMMDD.log
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


class OperationType(Enum):
    """数据库操作类型枚举"""
    SELECT = "SELECT"
    INSERT = "INSERT"
    UPDATE = "UPDATE"
    DELETE = "DELETE"
    DDL = "DDL"  # CREATE, ALTER, DROP等
    OTHER = "OTHER"


class OperationResult(Enum):
    """操作结果枚举"""
    SUCCESS = "SUCCESS"
    FAILURE = "FAILURE"


@dataclass
class AuditLogEntry:
    """
    审计日志条目结构

    Attributes:
        timestamp: 操作时间戳（ISO格式）
        operation_type: 操作类型
        target_database: 目标数据库名称
        query_summary: 查询摘要（脱敏后）
        result: 执行结果
        execution_time_ms: 执行耗时（毫秒）
        user_id: 操作用户ID（可选）
        client_ip: 客户端IP（可选）
        session_id: 会话ID（可选）
        rows_affected: 影响行数（可选）
        error_message: 错误信息（失败时）
    """
    timestamp: str
    operation_type: str
    target_database: str
    query_summary: str
    result: str
    execution_time_ms: float
    user_id: Optional[str] = None
    client_ip: Optional[str] = None
    session_id: Optional[str] = None
    rows_affected: Optional[int] = None
    error_message: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return asdict(self)

    def to_json(self) -> str:
        """转换为JSON字符串"""
        return json.dumps(self.to_dict(), ensure_ascii=False, default=str)


class DataMasker:
    """
    敏感数据脱敏器

    支持脱敏的字段类型：
    - 密码字段：password, passwd, pwd等
    - API密钥：api_key, secret_key, token等
    - 加密数据：encrypted_开头的字段
    """

    # 敏感字段名模式（不区分大小写）
    SENSITIVE_PATTERNS = [
        # 密码相关
        r'(?i)(password|passwd|pwd|pass|user_password|user_pwd)',
        # API密钥相关
        r'(?i)(api_key|apikey|secret_key|secretkey|auth_token|access_token|refresh_token|token|secret|api_secret)',
        # 加密数据（以encrypted_开头）
        r'(?i)^encrypted_.*',
        # 其他敏感信息
        r'(?i)(private_key|public_key|certificate|cert|credential|auth)',
    ]

    # SQL中的敏感值模式
    SQL_SENSITIVE_PATTERNS = [
        # 密码赋值
        r"(?i)(password|passwd|pwd)\s*=\s*['\"][^'\"]*['\"]",
        # VALUES中的敏感值（简单匹配）
        r"(?i)VALUES\s*\([^)]*\)",
    ]

    MASK = "***MASKED***"
    HASH_MASK = "***HASH:{}***"

    @classmethod
    def is_sensitive_field(cls, field_name: str) -> bool:
        """
        检查字段名是否为敏感字段

        Args:
            field_name: 字段名称

        Returns:
            是否为敏感字段
        """
        for pattern in cls.SENSITIVE_PATTERNS:
            if re.match(pattern, field_name):
                return True
        return False

    @classmethod
    def mask_value(cls, value: Any, use_hash: bool = False) -> str:
        """
        脱敏单个值

        Args:
            value: 原始值
            use_hash: 是否使用哈希值代替（用于需要追踪但不暴露的场景）

        Returns:
            脱敏后的值
        """
        if value is None:
            return "NULL"

        if use_hash:
            value_str = str(value)
            hash_value = hashlib.sha256(value_str.encode()).hexdigest()[:16]
            return cls.HASH_MASK.format(hash_value)

        return cls.MASK

    @classmethod
    def mask_sql_query(cls, query: str) -> str:
        """
        对SQL查询进行脱敏处理

        Args:
            query: 原始SQL查询

        Returns:
            脱敏后的SQL查询
        """
        if not query:
            return query

        masked_query = query

        # 脱敏密码赋值：password = 'xxx' -> password = '***MASKED***'
        masked_query = re.sub(
            r"(?i)(password|passwd|pwd)\s*=\s*['\"][^'\"]*['\"]",
            r"\1 = '***MASKED***'",
            masked_query
        )

        # 脱敏INSERT语句中的敏感列值
        # 匹配 INSERT INTO table (col1, col2) VALUES (val1, val2)
        def mask_insert_values(match):
            """处理INSERT语句中的VALUES部分"""
            values_part = match.group(0)
            # 简单的值脱敏：将所有字符串值脱敏
            # 保留数字和NULL
            masked = re.sub(
                r"'[^']*'",
                "'***MASKED***'",
                values_part
            )
            return masked

        masked_query = re.sub(
            r"(?i)VALUES\s*\([^)]+\)",
            mask_insert_values,
            masked_query
        )

        # 脱敏UPDATE语句中的SET部分
        def mask_update_set(match):
            """处理UPDATE语句中的SET部分"""
            set_part = match.group(0)
            # 检查是否包含敏感字段
            for pattern in cls.SENSITIVE_PATTERNS:
                if re.search(pattern, set_part, re.IGNORECASE):
                    # 脱敏该字段的值
                    set_part = re.sub(
                        r"(?i)(\w*pass\w*|\w*pwd\w*|\w*secret\w*|\w*token\w*|\w*key\w*)\s*=\s*['\"][^'\"]*['\"]",
                        r"\1 = '***MASKED***'",
                        set_part
                    )
            return set_part

        masked_query = re.sub(
            r"(?i)SET\s+.+?(?=WHERE|$)",
            mask_update_set,
            masked_query
        )

        return masked_query

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
            if cls.is_sensitive_field(key):
                masked_data[key] = cls.mask_value(value, use_hash)
            elif isinstance(value, dict):
                masked_data[key] = cls.mask_dict(value, use_hash)
            elif isinstance(value, list):
                masked_data[key] = [
                    cls.mask_dict(item, use_hash) if isinstance(item, dict) else item
                    for item in value
                ]
            else:
                masked_data[key] = value

        return masked_data


class DBAuditLogger:
    """
    数据库审计日志记录器

    功能：
    - 记录数据库操作审计日志
    - 自动日志轮转（按日期）
    - 自动清理过期日志
    - 敏感数据脱敏
    """

    DEFAULT_LOG_DIR = "logs"
    DEFAULT_RETENTION_DAYS = 30
    DEFAULT_LOG_FORMAT = "%(message)s"

    _instance: Optional['DBAuditLogger'] = None
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
        初始化审计日志记录器

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
        return self.log_dir / f"db_audit_{date_str}.log"

    def _setup_logger(self) -> None:
        """设置日志记录器"""
        self._logger = logging.getLogger("DBAuditLogger")
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
            for log_file in self.log_dir.glob("db_audit_*.log"):
                try:
                    # 从文件名提取日期
                    date_match = re.search(r"db_audit_(\d{8})\.log", log_file.name)
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
                print(f"[DBAuditLogger] 清理旧日志时出错: {e}")

    def _check_rotation(self) -> None:
        """检查并执行日志轮转"""
        current_date = datetime.now().strftime("%Y%m%d")
        if self._current_date != current_date:
            with self._lock:
                if self._current_date != current_date:
                    self._rotate_log_file()
                    self._clean_old_logs()

    def _detect_operation_type(self, query: str) -> OperationType:
        """
        自动检测SQL操作类型

        Args:
            query: SQL查询语句

        Returns:
            操作类型枚举
        """
        if not query:
            return OperationType.OTHER

        query_upper = query.strip().upper()

        if query_upper.startswith("SELECT"):
            return OperationType.SELECT
        elif query_upper.startswith("INSERT"):
            return OperationType.INSERT
        elif query_upper.startswith("UPDATE"):
            return OperationType.UPDATE
        elif query_upper.startswith("DELETE"):
            return OperationType.DELETE
        elif any(query_upper.startswith(cmd) for cmd in [
            "CREATE", "ALTER", "DROP", "TRUNCATE", "GRANT", "REVOKE"
        ]):
            return OperationType.DDL
        else:
            return OperationType.OTHER

    def log(
        self,
        query: str,
        target_database: str,
        result: OperationResult,
        execution_time_ms: float,
        operation_type: Optional[Union[OperationType, str]] = None,
        user_id: Optional[str] = None,
        client_ip: Optional[str] = None,
        session_id: Optional[str] = None,
        rows_affected: Optional[int] = None,
        error_message: Optional[str] = None,
        extra_data: Optional[Dict[str, Any]] = None
    ) -> AuditLogEntry:
        """
        记录审计日志

        Args:
            query: SQL查询语句（会被脱敏）
            target_database: 目标数据库名称
            result: 执行结果
            execution_time_ms: 执行耗时（毫秒）
            operation_type: 操作类型（自动检测或手动指定）
            user_id: 操作用户ID
            client_ip: 客户端IP
            session_id: 会话ID
            rows_affected: 影响行数
            error_message: 错误信息
            extra_data: 额外数据（会被脱敏）

        Returns:
            审计日志条目对象
        """
        # 检查并执行日志轮转
        self._check_rotation()

        # 自动检测操作类型
        if operation_type is None:
            operation_type = self._detect_operation_type(query)
        elif isinstance(operation_type, str):
            operation_type = OperationType(operation_type.upper())

        # 脱敏查询
        query_summary = DataMasker.mask_sql_query(query)

        # 脱敏额外数据
        masked_extra = None
        if extra_data:
            masked_extra = DataMasker.mask_dict(extra_data)

        # 创建日志条目
        entry = AuditLogEntry(
            timestamp=datetime.now().isoformat(),
            operation_type=operation_type.value,
            target_database=target_database,
            query_summary=query_summary,
            result=result.value,
            execution_time_ms=execution_time_ms,
            user_id=user_id,
            client_ip=client_ip,
            session_id=session_id,
            rows_affected=rows_affected,
            error_message=error_message
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
        query: str,
        target_database: str,
        execution_time_ms: float,
        **kwargs
    ) -> AuditLogEntry:
        """
        记录成功的操作

        Args:
            query: SQL查询语句
            target_database: 目标数据库名称
            execution_time_ms: 执行耗时（毫秒）
            **kwargs: 其他可选参数

        Returns:
            审计日志条目对象
        """
        return self.log(
            query=query,
            target_database=target_database,
            result=OperationResult.SUCCESS,
            execution_time_ms=execution_time_ms,
            **kwargs
        )

    def log_failure(
        self,
        query: str,
        target_database: str,
        execution_time_ms: float,
        error_message: str,
        **kwargs
    ) -> AuditLogEntry:
        """
        记录失败的操作

        Args:
            query: SQL查询语句
            target_database: 目标数据库名称
            execution_time_ms: 执行耗时（毫秒）
            error_message: 错误信息
            **kwargs: 其他可选参数

        Returns:
            审计日志条目对象
        """
        return self.log(
            query=query,
            target_database=target_database,
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
            for log_file in sorted(self.log_dir.glob("db_audit_*.log"), reverse=True):
                try:
                    # 从文件名提取日期
                    date_match = re.search(r"db_audit_(\d{8})\.log", log_file.name)
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
                print(f"[DBAuditLogger] 读取日志时出错: {e}")

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
            "databases": {},
            "avg_execution_time_ms": 0.0,
            "date_range": {"start": None, "end": None}
        }

        total_time = 0.0
        timestamps = []

        for log in logs:
            # 操作类型统计
            op_type = log.get("operation_type", "UNKNOWN")
            stats["operation_types"][op_type] = stats["operation_types"].get(op_type, 0) + 1

            # 结果统计
            result = log.get("result", "UNKNOWN")
            if result in stats["results"]:
                stats["results"][result] += 1

            # 数据库统计
            db = log.get("target_database", "UNKNOWN")
            stats["databases"][db] = stats["databases"].get(db, 0) + 1

            # 执行时间
            exec_time = log.get("execution_time_ms", 0)
            if exec_time:
                total_time += exec_time

            # 时间戳
            ts = log.get("timestamp")
            if ts:
                timestamps.append(ts)

        # 平均执行时间
        if logs:
            stats["avg_execution_time_ms"] = round(total_time / len(logs), 2)

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


# 便捷函数：获取全局审计日志记录器实例
def get_audit_logger(
    log_dir: str = "logs",
    retention_days: int = 30,
    enable_console_output: bool = False
) -> DBAuditLogger:
    """
    获取审计日志记录器实例（单例）

    Args:
        log_dir: 日志存储目录
        retention_days: 日志保留天数
        enable_console_output: 是否同时输出到控制台

    Returns:
        DBAuditLogger实例
    """
    return DBAuditLogger(
        log_dir=log_dir,
        retention_days=retention_days,
        enable_console_output=enable_console_output
    )


# 上下文管理器支持
class AuditContext:
    """
    审计日志上下文管理器

    用于自动记录数据库操作的开始和结束
    """

    def __init__(
        self,
        logger: DBAuditLogger,
        query: str,
        target_database: str,
        operation_type: Optional[Union[OperationType, str]] = None,
        user_id: Optional[str] = None,
        client_ip: Optional[str] = None,
        session_id: Optional[str] = None
    ):
        self.logger = logger
        self.query = query
        self.target_database = target_database
        self.operation_type = operation_type
        self.user_id = user_id
        self.client_ip = client_ip
        self.session_id = session_id
        self.start_time: Optional[datetime] = None
        self.entry: Optional[AuditLogEntry] = None

    def __enter__(self) -> 'AuditContext':
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
                query=self.query,
                target_database=self.target_database,
                execution_time_ms=execution_time_ms,
                operation_type=self.operation_type,
                user_id=self.user_id,
                client_ip=self.client_ip,
                session_id=self.session_id
            )
        else:
            # 失败
            error_msg = str(exc_val) if exc_val else "Unknown error"
            self.entry = self.logger.log_failure(
                query=self.query,
                target_database=self.target_database,
                execution_time_ms=execution_time_ms,
                error_message=error_msg,
                operation_type=self.operation_type,
                user_id=self.user_id,
                client_ip=self.client_ip,
                session_id=self.session_id
            )


# 示例用法
if __name__ == "__main__":
    # 创建审计日志记录器（启用控制台输出以便测试）
    audit_logger = get_audit_logger(enable_console_output=True)

    print("=" * 60)
    print("数据库审计日志系统测试")
    print("=" * 60)

    # 测试1：记录成功的SELECT操作
    print("\n[测试1] 记录成功的SELECT操作")
    audit_logger.log_success(
        query="SELECT id, username, email FROM users WHERE status = 'active'",
        target_database="production_db",
        execution_time_ms=45.5,
        operation_type=OperationType.SELECT,
        user_id="admin",
        client_ip="192.168.1.100",
        rows_affected=10
    )

    # 测试2：记录包含敏感数据的INSERT操作
    print("\n[测试2] 记录包含敏感数据的INSERT操作（自动脱敏）")
    audit_logger.log_success(
        query="INSERT INTO users (username, password, email, api_key) VALUES ('john', 'secret123', 'john@example.com', 'sk-abc123xyz')",
        target_database="production_db",
        execution_time_ms=23.8,
        operation_type=OperationType.INSERT,
        user_id="admin",
        rows_affected=1
    )

    # 测试3：记录UPDATE操作（含敏感字段）
    print("\n[测试3] 记录UPDATE操作（含敏感字段，自动脱敏）")
    audit_logger.log_success(
        query="UPDATE users SET password = 'newpass456', secret_key = 'newsecret' WHERE id = 1",
        target_database="production_db",
        execution_time_ms=15.2,
        operation_type=OperationType.UPDATE,
        user_id="admin",
        rows_affected=1
    )

    # 测试4：记录失败的操作
    print("\n[测试4] 记录失败的操作")
    audit_logger.log_failure(
        query="DELETE FROM users WHERE id = 999",
        target_database="production_db",
        execution_time_ms=5.0,
        error_message="Foreign key constraint violation",
        operation_type=OperationType.DELETE,
        user_id="admin"
    )

    # 测试5：使用上下文管理器
    print("\n[测试5] 使用上下文管理器记录操作")
    try:
        with AuditContext(
            logger=audit_logger,
            query="SELECT * FROM sensitive_data WHERE encrypted_field = 'secret'",
            target_database="production_db",
            operation_type=OperationType.SELECT,
            user_id="admin"
        ):
            # 模拟数据库操作
            import time
            time.sleep(0.1)
            print("  模拟操作执行完成")
    except Exception as e:
        print(f"  操作失败: {e}")

    # 测试6：测试脱敏功能
    print("\n[测试6] 敏感数据脱敏测试")
    test_data = {
        "username": "john_doe",
        "password": "super_secret_password",
        "api_key": "sk-live-abc123",
        "secret_key": "very_secret",
        "encrypted_data": "some encrypted content",
        "normal_field": "this is normal",
        "nested": {
            "token": "nested_token_value",
            "public_info": "everyone can see this"
        }
    }
    masked = DataMasker.mask_dict(test_data)
    print(f"  原始数据: {json.dumps(test_data, indent=2)}")
    print(f"  脱敏后: {json.dumps(masked, indent=2)}")

    # 测试7：获取统计信息
    print("\n[测试7] 获取日志统计信息")
    stats = audit_logger.get_log_stats(days=7)
    print(f"  统计信息: {json.dumps(stats, indent=2, ensure_ascii=False)}")

    # 测试8：获取最近日志
    print("\n[测试8] 获取最近日志条目")
    recent_logs = audit_logger.get_recent_logs(days=7)
    print(f"  最近 {len(recent_logs)} 条日志")
    for i, log in enumerate(recent_logs[:3], 1):
        print(f"  [{i}] {log.get('operation_type')} - {log.get('result')} - {log.get('query_summary', '')[:50]}...")

    print("\n" + "=" * 60)
    print("测试完成！日志文件保存在: logs/db_audit_YYYYMMDD.log")
    print("=" * 60)

    # 关闭日志记录器
    audit_logger.close()
