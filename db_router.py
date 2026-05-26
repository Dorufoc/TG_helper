"""
数据库路由管理器核心模块

提供安全的数据库访问控制，包括权限管理、查询白名单、参数化查询检查、审计日志等功能。
作为所有数据库访问的唯一入口，禁止直接暴露原始sqlite3连接。
"""

import sqlite3
import re
import logging
import hashlib
import time
from enum import Enum, auto
from typing import Optional, List, Dict, Any, Callable, Set, Tuple, Union
from dataclasses import dataclass, field
from contextlib import contextmanager
from functools import wraps
import threading


class DatabasePermission(Enum):
    """数据库访问权限枚举"""
    READ_ONLY = auto()   # 只读权限：仅允许SELECT查询
    READ_WRITE = auto()  # 读写权限：允许SELECT/INSERT/UPDATE/DELETE
    ADMIN = auto()       # 管理员权限：允许所有操作包括DDL


class SecurityError(Exception):
    """安全相关错误基类"""
    pass


class PermissionDeniedError(SecurityError):
    """权限不足错误"""
    pass


class QueryNotAllowedError(SecurityError):
    """查询不在白名单中错误"""
    pass


class NonParameterizedQueryError(SecurityError):
    """非参数化查询错误"""
    pass


@dataclass
class AuditLogEntry:
    """审计日志条目"""
    timestamp: float
    query_hash: str
    permission_level: str
    operation_type: str
    allowed: bool
    reason: Optional[str] = None
    user_context: Optional[str] = None


class QueryWhitelistValidator:
    """查询白名单验证器
    
    支持注册允许的SQL查询模板，通过正则表达式或精确匹配进行验证。
    """
    
    def __init__(self):
        self._exact_patterns: Set[str] = set()
        self._regex_patterns: List[re.Pattern] = []
        self._template_patterns: Dict[str, re.Pattern] = {}
        self._lock = threading.RLock()
    
    def register_exact(self, query: str) -> None:
        """注册精确匹配的查询
        
        Args:
            query: 完整的SQL查询字符串
        """
        with self._lock:
            normalized = self._normalize_query(query)
            self._exact_patterns.add(normalized)
    
    def register_regex(self, pattern: str) -> None:
        """注册正则表达式模式
        
        Args:
            pattern: 正则表达式字符串
        """
        with self._lock:
            try:
                compiled = re.compile(pattern, re.IGNORECASE | re.DOTALL)
                self._regex_patterns.append(compiled)
            except re.error as e:
                raise ValueError(f"无效的正则表达式: {pattern}, 错误: {e}")
    
    def register_template(self, name: str, template: str) -> None:
        """注册命名查询模板
        
        Args:
            name: 模板名称
            template: 包含占位符的SQL模板，如 "SELECT * FROM users WHERE id = ?"
        """
        with self._lock:
            # 将模板转换为正则表达式
            # 将 ? 和 :param 替换为匹配任意值的正则
            escaped = re.escape(template)
            # 还原占位符为通配模式
            pattern = escaped.replace(r'\?', r'.+?').replace(r'\:', r':')
            try:
                compiled = re.compile(pattern, re.IGNORECASE | re.DOTALL)
                self._template_patterns[name] = compiled
            except re.error as e:
                raise ValueError(f"无效的模板: {template}, 错误: {e}")
    
    def validate(self, query: str) -> bool:
        """验证查询是否在白名单中
        
        Args:
            query: 要验证的SQL查询
            
        Returns:
            如果查询在白名单中返回True，否则返回False
        """
        with self._lock:
            normalized = self._normalize_query(query)
            
            # 检查精确匹配
            if normalized in self._exact_patterns:
                return True
            
            # 检查正则匹配
            for pattern in self._regex_patterns:
                if pattern.match(normalized):
                    return True
            
            # 检查模板匹配
            for compiled in self._template_patterns.values():
                if compiled.match(normalized):
                    return True
            
            return False
    
    def unregister(self, name: Optional[str] = None, query: Optional[str] = None) -> bool:
        """注销已注册的查询
        
        Args:
            name: 模板名称（用于注销模板）
            query: 精确查询字符串（用于注销精确匹配）
            
        Returns:
            如果成功注销返回True，否则返回False
        """
        with self._lock:
            if name and name in self._template_patterns:
                del self._template_patterns[name]
                return True
            if query:
                normalized = self._normalize_query(query)
                if normalized in self._exact_patterns:
                    self._exact_patterns.remove(normalized)
                    return True
            return False
    
    def clear(self) -> None:
        """清空所有白名单"""
        with self._lock:
            self._exact_patterns.clear()
            self._regex_patterns.clear()
            self._template_patterns.clear()
    
    @staticmethod
    def _normalize_query(query: str) -> str:
        """标准化查询字符串用于比较"""
        # 移除多余空白，统一大小写
        return ' '.join(query.split()).lower().strip()


class ParameterizedQueryChecker:
    """参数化查询检查器
    
    检测危险的字符串拼接模式，确保使用参数化查询。
    """
    
    # 危险模式：字符串格式化/拼接
    DANGEROUS_PATTERNS = [
        # f-string: f"...{var}..."
        re.compile(r'f["\'][^"\']*\{[^}]+\}[^"\']*["\']', re.IGNORECASE),
        # .format(): "...{}...".format(...)
        re.compile(r'["\'][^"\']*%s[^"\']*["\']\s*\.\s*format\s*\(', re.IGNORECASE),
        re.compile(r'["\'][^"\']*\{[^}]+\}[^"\']*["\']\s*\.\s*format\s*\(', re.IGNORECASE),
        # % 格式化: "...%s..." % (...)
        re.compile(r'["\'][^"\']*%[^"\']*["\']\s*%\s*\(', re.IGNORECASE),
        # + 拼接: "..." + var + "..."
        re.compile(r'["\'][^"\']*["\']\s*\+\s*[^\s]', re.IGNORECASE),
        # 字符串拼接函数
        re.compile(r'concat\s*\(', re.IGNORECASE),
        re.compile(r'join\s*\(', re.IGNORECASE),
    ]
    
    # SQL注入特征模式
    SQL_INJECTION_PATTERNS = [
        # URL编码的单引号
        re.compile(r"%27", re.IGNORECASE),
        # 注释符
        re.compile(r"--\s*$", re.IGNORECASE),  # 行尾注释
        re.compile(r"/\*.*\*/", re.IGNORECASE),  # 块注释
        # OR/AND 注入模式 (如 ' OR '1'='1)
        re.compile(r"'\s+OR\s+'\d+'\s*=\s*'\d+", re.IGNORECASE),
        re.compile(r"'\s+AND\s+'\d+'\s*=\s*'\d+", re.IGNORECASE),
        # UNION 注入
        re.compile(r"UNION\s+SELECT\s+", re.IGNORECASE),
        # 堆叠查询
        re.compile(r";\s*(SELECT|INSERT|UPDATE|DELETE|DROP|CREATE|ALTER)\s+", re.IGNORECASE),
        # 时间延迟注入
        re.compile(r"WAITFOR\s+DELAY", re.IGNORECASE),
        re.compile(r"SLEEP\s*\(\s*\d+\s*\)", re.IGNORECASE),
        # 系统存储过程
        re.compile(r"exec\s*\(\s*@", re.IGNORECASE),
        re.compile(r"xp_\w+", re.IGNORECASE),
        re.compile(r"sp_\w+", re.IGNORECASE),
    ]
    
    def __init__(self):
        self._custom_patterns: List[re.Pattern] = []
    
    def add_pattern(self, pattern: str) -> None:
        """添加自定义危险模式
        
        Args:
            pattern: 正则表达式字符串
        """
        try:
            compiled = re.compile(pattern, re.IGNORECASE)
            self._custom_patterns.append(compiled)
        except re.error as e:
            raise ValueError(f"无效的正则表达式: {pattern}, 错误: {e}")
    
    def check(self, query: str, parameters: Optional[Union[Tuple, Dict]] = None) -> Tuple[bool, Optional[str]]:
        """检查查询是否使用了参数化查询
        
        Args:
            query: SQL查询字符串
            parameters: 查询参数（如果提供）
            
        Returns:
            (是否安全, 不安全原因)
        """
        # 检查是否包含参数占位符
        has_placeholders = self._has_placeholders(query)
        
        # 如果没有参数但有占位符，可能是参数化查询
        if has_placeholders and parameters is None:
            # 可能是预准备语句，需要进一步检查
            pass
        
        # 检查危险模式
        for pattern in self.DANGEROUS_PATTERNS:
            if pattern.search(query):
                return False, f"检测到危险模式: 字符串格式化/拼接"
        
        # 检查SQL注入特征
        for pattern in self.SQL_INJECTION_PATTERNS:
            if pattern.search(query):
                return False, f"检测到潜在的SQL注入特征"
        
        # 检查自定义模式
        for pattern in self._custom_patterns:
            if pattern.search(query):
                return False, f"检测到自定义危险模式"
        
        # 如果没有参数占位符且没有提供参数，可能是硬编码查询
        # 这种情况下需要检查是否包含用户输入
        if not has_placeholders and parameters is None:
            # 检查是否包含可疑的字符串值（简单启发式）
            if self._contains_suspicious_values(query):
                return False, "查询可能包含未参数化的用户输入"
        
        return True, None
    
    def _has_placeholders(self, query: str) -> bool:
        """检查查询是否包含参数占位符"""
        # SQLite 占位符: ?, ?NNN, :VVV, @VVV, $VVV
        placeholder_patterns = [
            r'\?',           # ?
            r':[a-zA-Z_]\w*',  # :name
            r'@[a-zA-Z_]\w*',  # @name
            r'\$[a-zA-Z_]\w*', # $name
        ]
        for pattern in placeholder_patterns:
            if re.search(pattern, query):
                return True
        return False
    
    def _contains_suspicious_values(self, query: str) -> bool:
        """检查查询是否包含可疑的值（简单启发式）"""
        # 检查单引号内的内容是否看起来像是用户输入
        # 这是一个简单的启发式，可能有误报
        suspicious = [
            r"'\s*OR\s*'",
            r"'\s*AND\s*'",
            r"';\s*",
            r"'\s*--",
        ]
        for pattern in suspicious:
            if re.search(pattern, query, re.IGNORECASE):
                return True
        return False


class SensitiveDataMasker:
    """敏感数据脱敏器
    
    对审计日志中的敏感信息进行脱敏处理。
    """
    
    # 敏感字段名称模式
    SENSITIVE_FIELD_PATTERNS = [
        re.compile(r'password', re.IGNORECASE),
        re.compile(r'passwd', re.IGNORECASE),
        re.compile(r'pwd', re.IGNORECASE),
        re.compile(r'secret', re.IGNORECASE),
        re.compile(r'api[_-]?key', re.IGNORECASE),
        re.compile(r'token', re.IGNORECASE),
        re.compile(r'auth', re.IGNORECASE),
        re.compile(r'credential', re.IGNORECASE),
        re.compile(r'private[_-]?key', re.IGNORECASE),
        re.compile(r'credit[_-]?card', re.IGNORECASE),
        re.compile(r'cvv', re.IGNORECASE),
        re.compile(r'ssn', re.IGNORECASE),
    ]
    
    # 敏感值模式（如密码哈希、API密钥格式）
    SENSITIVE_VALUE_PATTERNS = [
        re.compile(r'[a-f0-9]{32,}', re.IGNORECASE),  # MD5/SHA哈希
        re.compile(r'[A-Za-z0-9_-]{20,}'),  # 长随机字符串（可能是API密钥）
    ]
    
    @classmethod
    def mask_query(cls, query: str) -> str:
        """对查询中的敏感数据进行脱敏
        
        Args:
            query: 原始SQL查询
            
        Returns:
            脱敏后的查询
        """
        masked = query
        
        # 对VALUES子句中的值进行脱敏
        masked = cls._mask_values_clause(masked)
        
        # 对SET子句中的值进行脱敏
        masked = cls._mask_set_clause(masked)
        
        # 对WHERE子句中的敏感字段值进行脱敏
        masked = cls._mask_where_clause(masked)
        
        return masked
    
    @classmethod
    def mask_parameters(cls, parameters: Optional[Union[Tuple, Dict, List]]) -> Optional[Union[Tuple, Dict, List]]:
        """对参数中的敏感数据进行脱敏
        
        Args:
            parameters: 查询参数
            
        Returns:
            脱敏后的参数
        """
        if parameters is None:
            return None
        
        if isinstance(parameters, dict):
            return {k: cls._mask_value(k, v) for k, v in parameters.items()}
        elif isinstance(parameters, (list, tuple)):
            return tuple(cls._mask_value_by_value(v) for v in parameters)
        else:
            return parameters
    
    @classmethod
    def _mask_values_clause(cls, query: str) -> str:
        """脱敏VALUES子句中的值"""
        # 匹配 INSERT ... VALUES (...)
        pattern = re.compile(
            r'(INSERT\s+INTO\s+\w+\s*\([^)]*\)\s*VALUES\s*\()([^)]+)(\))',
            re.IGNORECASE
        )
        
        def replace_values(match):
            prefix = match.group(1)
            values = match.group(2)
            suffix = match.group(3)
            # 将所有值替换为 ***
            masked_values = re.sub(r"'[^']*'", "'***'", values)
            masked_values = re.sub(r'\b\d+\b', '***', masked_values)
            return prefix + masked_values + suffix
        
        return pattern.sub(replace_values, query)
    
    @classmethod
    def _mask_set_clause(cls, query: str) -> str:
        """脱敏SET子句中的值"""
        # 匹配 UPDATE ... SET col = value
        pattern = re.compile(
            r'(UPDATE\s+\w+\s+SET\s+)',
            re.IGNORECASE
        )
        
        def replace_set(match):
            # 这是一个简化实现，实际应该更精确地解析
            return match.group(1)
        
        # 更精确的SET子句脱敏
        set_pattern = re.compile(
            r"(SET\s+.*?)\s*=\s*('[^']*'|\d+|[^,\s]+)",
            re.IGNORECASE
        )
        
        def mask_set_value(match):
            prefix = match.group(1)
            value = match.group(2)
            # 检查是否是敏感字段
            for sensitive_pattern in cls.SENSITIVE_FIELD_PATTERNS:
                if sensitive_pattern.search(prefix):
                    return f"{prefix} = '***'"
            # 检查值是否看起来像敏感数据
            if cls._looks_sensitive(value):
                return f"{prefix} = '***'"
            return match.group(0)
        
        return set_pattern.sub(mask_set_value, query)
    
    @classmethod
    def _mask_where_clause(cls, query: str) -> str:
        """脱敏WHERE子句中的敏感字段值"""
        # 这是一个简化实现
        for pattern in cls.SENSITIVE_FIELD_PATTERNS:
            # 查找敏感字段的等值比较
            field_pattern = re.compile(
                rf"({pattern.pattern})\s*=\s*('[^']*'|\d+|[^\s,;)]+)",
                re.IGNORECASE
            )
            query = field_pattern.sub(r"\1 = '***'", query)
        return query
    
    @classmethod
    def _mask_value(cls, key: str, value: Any) -> Any:
        """根据键名脱敏值"""
        for pattern in cls.SENSITIVE_FIELD_PATTERNS:
            if pattern.search(key):
                return '***'
        if cls._looks_sensitive(str(value)):
            return '***'
        return value
    
    @classmethod
    def _mask_value_by_value(cls, value: Any) -> Any:
        """根据值的内容脱敏"""
        str_value = str(value)
        if cls._looks_sensitive(str_value):
            return '***'
        return value
    
    @classmethod
    def _looks_sensitive(cls, value: str) -> bool:
        """检查值是否看起来像是敏感数据"""
        for pattern in cls.SENSITIVE_VALUE_PATTERNS:
            if pattern.search(value):
                return True
        return False


class SecureConnectionProxy:
    """安全连接代理类
    
    包装sqlite3连接并实施安全检查：
    - 验证查询是否在白名单中
    - 强制使用参数化查询（检测字符串格式化）
    - 根据权限级别限制操作类型
    - 记录审计日志
    
    禁止直接暴露原始sqlite3连接。
    """
    
    # SQL操作类型映射
    OPERATION_TYPES = {
        'SELECT': 'READ',
        'INSERT': 'WRITE',
        'UPDATE': 'WRITE',
        'DELETE': 'WRITE',
        'REPLACE': 'WRITE',
        'CREATE': 'DDL',
        'ALTER': 'DDL',
        'DROP': 'DDL',
        'TRUNCATE': 'DDL',
        'PRAGMA': 'PRAGMA',
        'VACUUM': 'MAINTENANCE',
        'ANALYZE': 'MAINTENANCE',
        'REINDEX': 'MAINTENANCE',
    }
    
    # 权限允许的操作类型
    PERMISSION_OPERATIONS = {
        DatabasePermission.READ_ONLY: {'READ', 'PRAGMA'},
        DatabasePermission.READ_WRITE: {'READ', 'WRITE', 'PRAGMA'},
        DatabasePermission.ADMIN: {'READ', 'WRITE', 'DDL', 'PRAGMA', 'MAINTENANCE'},
    }
    
    def __init__(
        self,
        connection: sqlite3.Connection,
        permission: DatabasePermission,
        whitelist_validator: QueryWhitelistValidator,
        query_checker: ParameterizedQueryChecker,
        audit_logger: Optional[logging.Logger] = None,
        user_context: Optional[str] = None
    ):
        """初始化安全连接代理
        
        Args:
            connection: 底层的sqlite3连接
            permission: 访问权限级别
            whitelist_validator: 白名单验证器
            query_checker: 参数化查询检查器
            audit_logger: 审计日志记录器
            user_context: 用户上下文信息（用于审计）
        """
        self._connection = connection
        self._permission = permission
        self._whitelist = whitelist_validator
        self._checker = query_checker
        self._audit_logger = audit_logger
        self._user_context = user_context
        self._closed = False
        self._lock = threading.RLock()
    
    def _get_operation_type(self, query: str) -> str:
        """获取查询的操作类型"""
        # 提取SQL语句的第一个关键字
        match = re.match(r'^\s*(\w+)', query, re.IGNORECASE)
        if match:
            keyword = match.group(1).upper()
            return self.OPERATION_TYPES.get(keyword, 'UNKNOWN')
        return 'UNKNOWN'
    
    def _check_permission(self, operation_type: str) -> bool:
        """检查当前权限是否允许该操作类型"""
        allowed = self.PERMISSION_OPERATIONS.get(self._permission, set())
        return operation_type in allowed
    
    def _log_audit(
        self,
        query: str,
        allowed: bool,
        reason: Optional[str] = None,
        parameters: Optional[Union[Tuple, Dict]] = None
    ) -> None:
        """记录审计日志"""
        if self._audit_logger is None:
            return
        
        # 脱敏处理
        masked_query = SensitiveDataMasker.mask_query(query)
        masked_params = SensitiveDataMasker.mask_parameters(parameters)
        
        # 计算查询哈希（用于识别重复查询）
        query_hash = hashlib.sha256(query.encode()).hexdigest()[:16]
        
        # 获取操作类型
        operation_type = self._get_operation_type(query)
        
        # 创建审计条目
        entry = AuditLogEntry(
            timestamp=time.time(),
            query_hash=query_hash,
            permission_level=self._permission.name,
            operation_type=operation_type,
            allowed=allowed,
            reason=reason,
            user_context=self._user_context
        )
        
        # 记录日志
        log_data = {
            'timestamp': entry.timestamp,
            'query_hash': entry.query_hash,
            'permission': entry.permission_level,
            'operation': entry.operation_type,
            'allowed': entry.allowed,
            'reason': entry.reason,
            'user': entry.user_context,
            'query_preview': masked_query[:100] + '...' if len(masked_query) > 100 else masked_query,
        }
        
        if allowed:
            self._audit_logger.info(f"DB_ACCESS_ALLOWED: {log_data}")
        else:
            self._audit_logger.warning(f"DB_ACCESS_DENIED: {log_data}")
    
    def _validate_query(
        self,
        query: str,
        parameters: Optional[Union[Tuple, Dict]] = None
    ) -> Tuple[bool, Optional[str]]:
        """验证查询的安全性
        
        执行以下检查：
        1. 检查查询是否在白名单中
        2. 检查是否使用了参数化查询
        3. 检查权限是否足够
        
        Returns:
            (是否通过, 失败原因)
        """
        # 1. 检查白名单
        if not self._whitelist.validate(query):
            return False, "查询不在白名单中"
        
        # 2. 检查参数化查询
        is_safe, reason = self._checker.check(query, parameters)
        if not is_safe:
            return False, f"非参数化查询: {reason}"
        
        # 3. 检查权限
        operation_type = self._get_operation_type(query)
        if not self._check_permission(operation_type):
            return False, f"权限不足: 需要{operation_type}权限，当前为{self._permission.name}"
        
        return True, None
    
    def execute(
        self,
        query: str,
        parameters: Optional[Union[Tuple, Dict]] = None
    ) -> sqlite3.Cursor:
        """执行SQL查询（带安全检查）
        
        Args:
            query: SQL查询字符串
            parameters: 查询参数
            
        Returns:
            sqlite3.Cursor对象
            
        Raises:
            PermissionDeniedError: 权限不足
            QueryNotAllowedError: 查询不在白名单中
            NonParameterizedQueryError: 未使用参数化查询
            SecurityError: 其他安全错误
        """
        with self._lock:
            if self._closed:
                raise SecurityError("连接已关闭")
            
            # 验证查询
            is_valid, reason = self._validate_query(query, parameters)
            
            if not is_valid:
                self._log_audit(query, False, reason, parameters)
                
                if "权限不足" in reason:
                    raise PermissionDeniedError(reason)
                elif "白名单" in reason:
                    raise QueryNotAllowedError(reason)
                elif "非参数化" in reason:
                    raise NonParameterizedQueryError(reason)
                else:
                    raise SecurityError(reason)
            
            # 记录成功的审计日志
            self._log_audit(query, True, parameters=parameters)
            
            # 执行查询
            try:
                if parameters is not None:
                    return self._connection.execute(query, parameters)
                else:
                    return self._connection.execute(query)
            except sqlite3.Error as e:
                # 记录执行错误
                self._audit_logger.error(f"Query execution error: {e}") if self._audit_logger else None
                raise
    
    def executemany(
        self,
        query: str,
        parameters_list: List[Union[Tuple, Dict]]
    ) -> sqlite3.Cursor:
        """批量执行SQL查询（带安全检查）
        
        Args:
            query: SQL查询字符串
            parameters_list: 参数列表
            
        Returns:
            sqlite3.Cursor对象
        """
        with self._lock:
            if self._closed:
                raise SecurityError("连接已关闭")
            
            # 验证查询（只验证一次）
            is_valid, reason = self._validate_query(query, parameters_list[0] if parameters_list else None)
            
            if not is_valid:
                self._log_audit(query, False, reason)
                
                if "权限不足" in reason:
                    raise PermissionDeniedError(reason)
                elif "白名单" in reason:
                    raise QueryNotAllowedError(reason)
                elif "非参数化" in reason:
                    raise NonParameterizedQueryError(reason)
                else:
                    raise SecurityError(reason)
            
            # 记录成功的审计日志
            self._log_audit(query, True, parameters=parameters_list[0] if parameters_list else None)
            
            # 执行查询
            try:
                return self._connection.executemany(query, parameters_list)
            except sqlite3.Error as e:
                self._audit_logger.error(f"Query execution error: {e}") if self._audit_logger else None
                raise
    
    def executescript(self, sql_script: str) -> sqlite3.Cursor:
        """执行SQL脚本（带安全检查）
        
        警告：此方法会逐条检查脚本中的每个语句。
        
        Args:
            sql_script: SQL脚本字符串
            
        Returns:
            sqlite3.Cursor对象
        """
        with self._lock:
            if self._closed:
                raise SecurityError("连接已关闭")
            
            # 需要ADMIN权限才能执行脚本
            if self._permission != DatabasePermission.ADMIN:
                raise PermissionDeniedError("执行SQL脚本需要ADMIN权限")
            
            # 解析脚本中的各个语句
            statements = [s.strip() for s in sql_script.split(';') if s.strip()]
            
            for stmt in statements:
                is_valid, reason = self._validate_query(stmt)
                if not is_valid:
                    self._log_audit(stmt, False, reason)
                    raise SecurityError(f"脚本中的语句未通过验证: {reason}")
                self._log_audit(stmt, True)
            
            # 执行脚本
            try:
                return self._connection.executescript(sql_script)
            except sqlite3.Error as e:
                self._audit_logger.error(f"Script execution error: {e}") if self._audit_logger else None
                raise
    
    def commit(self) -> None:
        """提交事务"""
        with self._lock:
            if self._closed:
                raise SecurityError("连接已关闭")
            self._connection.commit()
    
    def rollback(self) -> None:
        """回滚事务"""
        with self._lock:
            if self._closed:
                raise SecurityError("连接已关闭")
            self._connection.rollback()
    
    def close(self) -> None:
        """关闭连接"""
        with self._lock:
            if not self._closed:
                self._connection.close()
                self._closed = True
    
    @property
    def closed(self) -> bool:
        """连接是否已关闭"""
        return self._closed
    
    def __enter__(self):
        """上下文管理器入口"""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """上下文管理器出口"""
        self.close()
        return False


class DatabaseRouter:
    """数据库路由管理器
    
    作为所有数据库访问的唯一入口，管理数据库连接和访问控制。
    """
    
    def __init__(
        self,
        db_path: str,
        audit_logger: Optional[logging.Logger] = None
    ):
        """初始化数据库路由管理器
        
        Args:
            db_path: 数据库文件路径
            audit_logger: 审计日志记录器
        """
        self._db_path = db_path
        self._audit_logger = audit_logger or self._create_default_logger()
        self._whitelist = QueryWhitelistValidator()
        self._checker = ParameterizedQueryChecker()
        self._connections: Dict[int, SecureConnectionProxy] = {}
        self._lock = threading.RLock()
        
        # 注册默认的白名单查询
        self._register_default_whitelist()
    
    def _create_default_logger(self) -> logging.Logger:
        """创建默认的审计日志记录器"""
        logger = logging.getLogger('db_router.audit')
        if not logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
            handler.setFormatter(formatter)
            logger.addHandler(handler)
            logger.setLevel(logging.INFO)
        return logger
    
    def _register_default_whitelist(self) -> None:
        """注册默认的白名单查询模板"""
        # 基本的CRUD操作模板
        templates = [
            # SELECT 模板
            ("select_all", r"^\s*SELECT\s+\*\s+FROM\s+\w+\s*$"),
            ("select_by_id", r"^\s*SELECT\s+.+\s+FROM\s+\w+\s+WHERE\s+\w+\s*=\s*\?\s*$"),
            ("select_where", r"^\s*SELECT\s+.+\s+FROM\s+\w+\s+WHERE\s+.+\s*$"),
            ("select_join", r"^\s*SELECT\s+.+\s+FROM\s+\w+\s+JOIN\s+\w+\s+ON\s+.+\s*$"),

            # INSERT 模板
            ("insert", r"^\s*INSERT\s+INTO\s+\w+\s*\([^)]+\)\s*VALUES\s*\([^)]+\)\s*$"),
            ("insert_or_replace", r"^\s*INSERT\s+OR\s+REPLACE\s+INTO\s+\w+\s*\([^)]+\)\s*VALUES\s*\([^)]+\)\s*$"),

            # UPDATE 模板
            ("update", r"^\s*UPDATE\s+\w+\s+SET\s+.+\s+WHERE\s+.+\s*$"),
            ("update_all", r"^\s*UPDATE\s+\w+\s+SET\s+.+\s*$"),

            # DELETE 模板
            ("delete", r"^\s*DELETE\s+FROM\s+\w+\s+WHERE\s+.+\s*$"),
            ("delete_all", r"^\s*DELETE\s+FROM\s+\w+\s*$"),

            # DDL 模板 (需要ADMIN权限)
            ("create_table", r"^\s*CREATE\s+TABLE\s+\w+\s*\(.+\)\s*$"),
            ("create_table_if_not_exists", r"^\s*CREATE\s+TABLE\s+IF\s+NOT\s+EXISTS\s+\w+\s*\(.+\)\s*$"),
            ("create_index", r"^\s*CREATE\s+INDEX\s+\w+\s+ON\s+\w+\s*\(.+\)\s*$"),
            ("drop_table", r"^\s*DROP\s+TABLE\s+\w+\s*$"),
            ("alter_table", r"^\s*ALTER\s+TABLE\s+\w+\s+.+\s*$"),

            # PRAGMA 模板
            ("pragma", r"^\s*PRAGMA\s+\w+\s*$"),
            ("pragma_value", r"^\s*PRAGMA\s+\w+\s*=\s*.+\s*$"),

            # 事务控制
            ("begin", r"^\s*BEGIN\s*(TRANSACTION)?\s*$"),
            ("commit", r"^\s*COMMIT\s*(TRANSACTION)?\s*$"),
            ("rollback", r"^\s*ROLLBACK\s*(TRANSACTION)?\s*$"),
        ]

        for name, pattern in templates:
            self._whitelist.register_regex(pattern)
    
    def get_connection(
        self,
        permission: DatabasePermission = DatabasePermission.READ_ONLY,
        user_context: Optional[str] = None
    ) -> SecureConnectionProxy:
        """获取安全连接代理
        
        这是获取数据库连接的唯一入口。
        
        Args:
            permission: 访问权限级别
            user_context: 用户上下文信息
            
        Returns:
            SecureConnectionProxy实例
        """
        with self._lock:
            # 创建新的底层连接
            raw_connection = sqlite3.connect(
                self._db_path,
                check_same_thread=False,
                isolation_level=None  # 使用自动提交模式，由代理控制事务
            )
            
            # 启用外键约束
            raw_connection.execute("PRAGMA foreign_keys = ON")
            
            # 设置行工厂为sqlite3.Row以支持列名访问
            raw_connection.row_factory = sqlite3.Row
            
            # 包装为安全代理
            proxy = SecureConnectionProxy(
                connection=raw_connection,
                permission=permission,
                whitelist_validator=self._whitelist,
                query_checker=self._checker,
                audit_logger=self._audit_logger,
                user_context=user_context
            )
            
            # 记录连接
            conn_id = id(proxy)
            self._connections[conn_id] = proxy
            
            return proxy
    
    @contextmanager
    def connection(
        self,
        permission: DatabasePermission = DatabasePermission.READ_ONLY,
        user_context: Optional[str] = None
    ):
        """上下文管理器方式获取连接
        
        使用示例:
            with router.connection(DatabasePermission.READ_WRITE) as conn:
                conn.execute("INSERT INTO users (name) VALUES (?)", ("Alice",))
                conn.commit()
        
        Args:
            permission: 访问权限级别
            user_context: 用户上下文信息
            
        Yields:
            SecureConnectionProxy实例
        """
        conn = None
        try:
            conn = self.get_connection(permission, user_context)
            yield conn
        finally:
            if conn is not None:
                conn.close()
                # 从记录中移除
                with self._lock:
                    conn_id = id(conn)
                    self._connections.pop(conn_id, None)
    
    def register_whitelist_query(self, query: str) -> None:
        """注册白名单查询（精确匹配）
        
        Args:
            query: SQL查询字符串
        """
        self._whitelist.register_exact(query)
    
    def register_whitelist_pattern(self, pattern: str) -> None:
        """注册白名单正则表达式模式
        
        Args:
            pattern: 正则表达式字符串
        """
        self._whitelist.register_regex(pattern)
    
    def register_whitelist_template(self, name: str, template: str) -> None:
        """注册白名单查询模板
        
        Args:
            name: 模板名称
            template: SQL模板字符串
        """
        self._whitelist.register_template(name, template)
    
    def add_dangerous_pattern(self, pattern: str) -> None:
        """添加自定义危险查询模式
        
        Args:
            pattern: 正则表达式字符串
        """
        self._checker.add_pattern(pattern)
    
    def close_all(self) -> None:
        """关闭所有管理的连接"""
        with self._lock:
            for proxy in list(self._connections.values()):
                try:
                    proxy.close()
                except Exception:
                    pass
            self._connections.clear()
    
    def get_stats(self) -> Dict[str, Any]:
        """获取路由管理器统计信息"""
        with self._lock:
            return {
                'db_path': self._db_path,
                'active_connections': len(self._connections),
                'whitelist_patterns': {
                    'exact': len(self._whitelist._exact_patterns),
                    'regex': len(self._whitelist._regex_patterns),
                    'templates': len(self._whitelist._template_patterns),
                }
            }


# 便捷函数
def create_router(db_path: str, audit_log_path: Optional[str] = None) -> DatabaseRouter:
    """创建数据库路由管理器的便捷函数
    
    Args:
        db_path: 数据库文件路径
        audit_log_path: 审计日志文件路径（可选）
        
    Returns:
        DatabaseRouter实例
    """
    audit_logger = None
    if audit_log_path:
        audit_logger = logging.getLogger('db_router.audit')
        audit_logger.handlers = []  # 清除现有处理器
        handler = logging.FileHandler(audit_log_path)
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        handler.setFormatter(formatter)
        audit_logger.addHandler(handler)
        audit_logger.setLevel(logging.INFO)
    
    return DatabaseRouter(db_path, audit_logger)


# 示例用法
if __name__ == "__main__":
    import tempfile
    import os

    # 配置日志
    logging.basicConfig(level=logging.INFO)

    # 创建临时数据库文件（:memory: 每次连接都是新的，所以使用文件数据库）
    temp_db = tempfile.mktemp(suffix='.db')

    try:
        # 创建路由管理器
        router = create_router(temp_db)

        # 使用ADMIN权限创建表
        with router.connection(DatabasePermission.ADMIN) as conn:
            conn.execute("""
                CREATE TABLE users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT NOT NULL,
                    password TEXT NOT NULL
                )
            """)
            conn.commit()

        # 使用读写权限插入数据
        with router.connection(DatabasePermission.READ_WRITE, user_context="admin") as conn:
            conn.execute(
                "INSERT INTO users (username, password) VALUES (?, ?)",
                ("alice", "secret123")
            )
            conn.commit()

        # 使用只读权限查询数据
        with router.connection(DatabasePermission.READ_ONLY, user_context="guest") as conn:
            cursor = conn.execute("SELECT id, username FROM users WHERE username = ?", ("alice",))
            rows = cursor.fetchall()
            print(f"查询结果: {rows}")

        # 尝试执行未在白名单中的查询（会失败）
        # 清除默认白名单，只保留特定表的查询
        router._whitelist.clear()
        router.register_whitelist_pattern(r"^\s*SELECT\s+\*\s+FROM\s+allowed_table\s*$")
        try:
            with router.connection(DatabasePermission.READ_ONLY) as conn:
                conn.execute("SELECT * FROM users")  # 这个不在白名单中
        except QueryNotAllowedError as e:
            print(f"预期的错误（白名单）: {e}")

        # 恢复默认白名单以便后续测试
        router._register_default_whitelist()

        # 尝试使用非参数化查询（会失败）
        # 添加一个危险模式来检测字符串拼接
        router.add_dangerous_pattern(r"username\s*=\s*'[^']*'")
        try:
            with router.connection(DatabasePermission.READ_WRITE) as conn:
                # 这种查询会被检测到（包含硬编码的字符串值）
                conn.execute("SELECT * FROM users WHERE username = 'alice'")
        except NonParameterizedQueryError as e:
            print(f"预期的错误（非参数化）: {e}")

        # 尝试权限不足的操作（会失败）
        try:
            with router.connection(DatabasePermission.READ_ONLY) as conn:
                conn.execute("INSERT INTO users (username, password) VALUES (?, ?)", ("bob", "pass"))
        except PermissionDeniedError as e:
            print(f"预期的错误（权限不足）: {e}")

        print("\n路由管理器统计:")
        print(router.get_stats())

    finally:
        # 清理临时文件
        if os.path.exists(temp_db):
            os.remove(temp_db)
