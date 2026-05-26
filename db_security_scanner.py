"""
数据库安全扫描工具

用于检测代码中的数据库安全风险，包括：
- 直接sqlite3连接检测
- 危险SQL模式检测
- 权限提升检测
- 硬编码凭据检测

白名单机制：
- 使用注释标记 # db-router-exempt 跳过特定行
- db_router.py 本身豁免检查
"""

import os
import re
import ast
import json
from pathlib import Path
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import List, Dict, Optional, Set, Tuple, Any
from datetime import datetime


class RiskLevel(Enum):
    """风险等级枚举"""
    CRITICAL = "Critical"  # 严重：可能导致数据泄露或系统被入侵
    HIGH = "High"          # 高危：明显的安全漏洞
    MEDIUM = "Medium"      # 中危：潜在的安全风险
    LOW = "Low"            # 低危：建议改进


class ViolationType(Enum):
    """违规类型枚举"""
    DIRECT_SQLITE_CONNECTION = "直接sqlite3连接"
    DANGEROUS_SQL_PATTERN = "危险SQL模式"
    PERMISSION_ESCALATION = "权限提升"
    HARDCODED_CREDENTIAL = "硬编码凭据"


@dataclass
class SecurityViolation:
    """安全违规记录"""
    violation_type: ViolationType
    risk_level: RiskLevel
    file_path: str
    line_number: int
    column: int
    code_snippet: str
    description: str
    recommendation: str
    matched_pattern: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            "violation_type": self.violation_type.value,
            "risk_level": self.risk_level.value,
            "file_path": self.file_path,
            "line_number": self.line_number,
            "column": self.column,
            "code_snippet": self.code_snippet,
            "description": self.description,
            "recommendation": self.recommendation,
            "matched_pattern": self.matched_pattern
        }


@dataclass
class ScanReport:
    """扫描报告"""
    scan_time: str
    total_files: int
    scanned_files: int
    skipped_files: int
    violations: List[SecurityViolation] = field(default_factory=list)
    summary: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            "scan_time": self.scan_time,
            "total_files": self.total_files,
            "scanned_files": self.scanned_files,
            "skipped_files": self.skipped_files,
            "violations": [v.to_dict() for v in self.violations],
            "summary": self.summary
        }

    def to_json(self, indent: int = 2) -> str:
        """转换为JSON字符串"""
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)

    def to_markdown(self) -> str:
        """转换为Markdown格式报告"""
        lines = [
            "# 数据库安全扫描报告",
            "",
            f"**扫描时间**: {self.scan_time}",
            f"**扫描文件总数**: {self.total_files}",
            f"**实际扫描**: {self.scanned_files}",
            f"**跳过文件**: {self.skipped_files}",
            f"**发现问题数**: {len(self.violations)}",
            "",
            "## 风险统计",
            ""
        ]

        # 按风险等级统计
        risk_counts = {}
        for v in self.violations:
            risk_counts[v.risk_level.value] = risk_counts.get(v.risk_level.value, 0) + 1

        for level in ["Critical", "High", "Medium", "Low"]:
            count = risk_counts.get(level, 0)
            emoji = {"Critical": "🔴", "High": "🟠", "Medium": "🟡", "Low": "🟢"}.get(level, "⚪")
            lines.append(f"- {emoji} **{level}**: {count}")

        lines.extend(["", "## 违规类型统计", ""])

        # 按违规类型统计
        type_counts = {}
        for v in self.violations:
            type_counts[v.violation_type.value] = type_counts.get(v.violation_type.value, 0) + 1

        for vtype, count in sorted(type_counts.items(), key=lambda x: -x[1]):
            lines.append(f"- **{vtype}**: {count}")

        if self.violations:
            lines.extend(["", "## 详细违规列表", ""])

            for i, v in enumerate(self.violations, 1):
                emoji = {
                    RiskLevel.CRITICAL: "🔴",
                    RiskLevel.HIGH: "🟠",
                    RiskLevel.MEDIUM: "🟡",
                    RiskLevel.LOW: "🟢"
                }.get(v.risk_level, "⚪")

                lines.extend([
                    f"### {i}. {emoji} [{v.risk_level.value}] {v.violation_type.value}",
                    "",
                    f"- **文件**: `{v.file_path}`",
                    f"- **位置**: 第 {v.line_number} 行, 第 {v.column} 列",
                    f"- **描述**: {v.description}",
                    f"- **修复建议**: {v.recommendation}",
                    "",
                    "**违规代码**:",
                    "```python",
                    v.code_snippet,
                    "```",
                    ""
                ])
        else:
            lines.extend(["", "✅ **未发现安全问题**", ""])

        return "\n".join(lines)


class DBSecurityScanner:
    """数据库安全扫描器

    检测代码中的数据库安全风险，支持白名单机制。
    """

    # 白名单注释标记
    EXEMPT_MARKER = "# db-router-exempt"

    # 豁免的文件名
    EXEMPT_FILES = {"db_router.py", "db_security_scanner.py"}

    # ========== 检测规则 ==========

    # 1. 直接sqlite3连接检测规则
    DIRECT_CONNECTION_PATTERNS = [
        {
            "pattern": re.compile(r'sqlite3\.connect\s*\(', re.IGNORECASE),
            "description": "检测到直接调用 sqlite3.connect()，绕过了数据库路由管理器的安全控制",
            "recommendation": "使用 db_router.DatabaseRouter 获取安全连接代理，禁止直接创建sqlite3连接",
            "risk_level": RiskLevel.CRITICAL
        },
        {
            "pattern": re.compile(r'from\s+sqlite3\s+import.*connect', re.IGNORECASE),
            "description": "检测到从sqlite3导入connect函数",
            "recommendation": "使用 db_router 模块提供的安全连接方式",
            "risk_level": RiskLevel.HIGH
        },
        {
            "pattern": re.compile(r'import\s+sqlite3(?!\.)', re.IGNORECASE),
            "description": "检测到直接导入sqlite3模块",
            "recommendation": "除非必要，否则应通过 db_router 访问数据库",
            "risk_level": RiskLevel.MEDIUM
        }
    ]

    # 2. 危险SQL模式检测规则
    DANGEROUS_SQL_PATTERNS = [
        # f-string SQL构建
        {
            "pattern": re.compile(r'f["\']\s*(SELECT|INSERT|UPDATE|DELETE|DROP|CREATE|ALTER)\s+[^"\']*\{[^}]+\}', re.IGNORECASE),
            "description": "检测到使用f-string构建SQL查询，存在SQL注入风险",
            "recommendation": "使用参数化查询，将变量作为参数传递而不是字符串拼接",
            "risk_level": RiskLevel.CRITICAL
        },
        # .format() SQL构建
        {
            "pattern": re.compile(r'["\']\s*(SELECT|INSERT|UPDATE|DELETE|DROP|CREATE|ALTER)\s+[^"\']*["\']\s*\.\s*format\s*\(', re.IGNORECASE),
            "description": "检测到使用.format()方法构建SQL查询，存在SQL注入风险",
            "recommendation": "使用参数化查询，将变量作为参数传递",
            "risk_level": RiskLevel.CRITICAL
        },
        # % 格式化 SQL构建
        {
            "pattern": re.compile(r'["\']\s*(SELECT|INSERT|UPDATE|DELETE|DROP|CREATE|ALTER)\s+[^"\']*%[sdxf][^"\']*["\']\s*%', re.IGNORECASE),
            "description": "检测到使用%格式化构建SQL查询，存在SQL注入风险",
            "recommendation": "使用参数化查询，将变量作为参数传递",
            "risk_level": RiskLevel.CRITICAL
        },
        # 字符串拼接 SQL
        {
            "pattern": re.compile(r'["\']\s*(SELECT|INSERT|UPDATE|DELETE|DROP|CREATE|ALTER)\s+[^"\']*["\']\s*\+', re.IGNORECASE),
            "description": "检测到使用字符串拼接构建SQL查询，存在SQL注入风险",
            "recommendation": "使用参数化查询，避免字符串拼接",
            "risk_level": RiskLevel.CRITICAL
        },
        # join构建SQL
        {
            "pattern": re.compile(r'["\']\.\s*join\s*\([^)]*(SELECT|INSERT|UPDATE|DELETE)', re.IGNORECASE),
            "description": "检测到使用join方法构建SQL查询",
            "recommendation": "使用参数化查询，避免动态构建SQL",
            "risk_level": RiskLevel.HIGH
        },
        # 动态表名/列名（无参数化）
        {
            "pattern": re.compile(r'(?:FROM|INTO|TABLE|UPDATE)\s+["\']?\s*\+?\s*\w+\s*\+?\s*["\']?', re.IGNORECASE),
            "description": "检测到可能的动态表名/列名使用",
            "recommendation": "表名和列名应使用白名单验证，避免直接使用用户输入",
            "risk_level": RiskLevel.HIGH
        }
    ]

    # 3. 权限提升检测规则
    PERMISSION_ESCALATION_PATTERNS = [
        # 绕过权限检查
        {
            "pattern": re.compile(r'check_same_thread\s*=\s*False', re.IGNORECASE),
            "description": "检测到设置check_same_thread=False，可能用于绕过线程安全检查",
            "recommendation": "使用db_router管理连接，它会正确处理线程安全",
            "risk_level": RiskLevel.HIGH
        },
        # 尝试获取原始连接
        {
            "pattern": re.compile(r'_connection|_conn|raw_connection|underlying', re.IGNORECASE),
            "description": "检测到可能尝试访问私有连接对象",
            "recommendation": "禁止访问底层连接对象，应通过SecureConnectionProxy提供的接口操作",
            "risk_level": RiskLevel.HIGH
        },
        # 直接执行PRAGMA
        {
            "pattern": re.compile(r'PRAGMA\s+(?:key|cipher|password)', re.IGNORECASE),
            "description": "检测到直接执行PRAGMA设置敏感配置",
            "recommendation": "敏感PRAGMA操作应通过db_router的ADMIN权限控制",
            "risk_level": RiskLevel.MEDIUM
        },
        # 尝试修改权限
        {
            "pattern": re.compile(r'permission\s*=\s*(?:ADMIN|READ_WRITE)', re.IGNORECASE),
            "description": "检测到硬编码权限提升",
            "recommendation": "权限应根据实际业务需求动态分配，避免硬编码高权限",
            "risk_level": RiskLevel.MEDIUM
        }
    ]

    # 4. 硬编码凭据检测规则
    HARDCODED_CREDENTIAL_PATTERNS = [
        # 硬编码密码
        {
            "pattern": re.compile(r'(?:password|passwd|pwd)\s*[=:]\s*["\'][^"\']{4,}["\']', re.IGNORECASE),
            "description": "检测到可能的硬编码密码",
            "recommendation": "密码应从配置文件或环境变量读取，禁止硬编码",
            "risk_level": RiskLevel.CRITICAL
        },
        # 硬编码API密钥
        {
            "pattern": re.compile(r'(?:api[_-]?key|apikey|secret[_-]?key)\s*[=:]\s*["\'][a-zA-Z0-9_-]{16,}["\']', re.IGNORECASE),
            "description": "检测到可能的硬编码API密钥",
            "recommendation": "API密钥应从环境变量或密钥管理服务获取",
            "risk_level": RiskLevel.CRITICAL
        },
        # 硬编码Token
        {
            "pattern": re.compile(r'(?:token|access_token|auth_token)\s*[=:]\s*["\'][a-zA-Z0-9_-]{20,}["\']', re.IGNORECASE),
            "description": "检测到可能的硬编码Token",
            "recommendation": "Token应从安全存储获取，禁止硬编码",
            "risk_level": RiskLevel.CRITICAL
        },
        # 数据库连接字符串含密码
        {
            "pattern": re.compile(r'["\']\w+://[^:]+:[^@]+@[^"\']+["\']', re.IGNORECASE),
            "description": "检测到包含密码的数据库连接字符串",
            "recommendation": "使用db_router管理连接，禁止在代码中硬编码连接字符串",
            "risk_level": RiskLevel.CRITICAL
        },
        # 私钥
        {
            "pattern": re.compile(r'(?:private[_-]?key|rsa_key|ssh_key)\s*[=:]\s*["\']', re.IGNORECASE),
            "description": "检测到可能的硬编码私钥",
            "recommendation": "私钥应存储在安全的密钥管理系统中",
            "risk_level": RiskLevel.CRITICAL
        },
        # 简单的弱密码
        {
            "pattern": re.compile(r'["\'](?:password|123456|admin|root|qwerty)["\']', re.IGNORECASE),
            "description": "检测到使用弱密码",
            "recommendation": "使用强密码策略，密码复杂度应符合安全要求",
            "risk_level": RiskLevel.HIGH
        }
    ]

    def __init__(self):
        """初始化安全扫描器"""
        self.violations: List[SecurityViolation] = []
        self.scanned_files: Set[str] = set()
        self.skipped_files: Set[str] = set()

    def _is_exempt_line(self, line: str) -> bool:
        """检查行是否被标记为豁免"""
        return self.EXEMPT_MARKER in line

    def _is_exempt_file(self, file_path: str) -> bool:
        """检查文件是否在豁免列表中"""
        filename = os.path.basename(file_path)
        return filename in self.EXEMPT_FILES

    def _get_line_column(self, content: str, position: int) -> Tuple[int, int]:
        """获取指定位置的行号和列号"""
        lines = content[:position].split('\n')
        line_number = len(lines)
        column = len(lines[-1]) if lines else 0
        return line_number, column

    def _extract_code_snippet(self, lines: List[str], line_number: int, context: int = 2) -> str:
        """提取代码片段（包含上下文）"""
        start = max(0, line_number - context - 1)
        end = min(len(lines), line_number + context)
        snippet_lines = []
        for i in range(start, end):
            prefix = f"{i+1:4d}: " if i + 1 != line_number else f"{i+1:4d}> "
            snippet_lines.append(prefix + lines[i])
        return '\n'.join(snippet_lines)

    def _check_patterns(self, content: str, lines: List[str], file_path: str,
                       patterns: List[Dict], violation_type: ViolationType) -> List[SecurityViolation]:
        """检查一组模式"""
        violations = []

        for rule in patterns:
            pattern = rule["pattern"]
            for match in pattern.finditer(content):
                line_number, column = self._get_line_column(content, match.start())

                # 检查该行是否被豁免
                if 0 <= line_number - 1 < len(lines):
                    line_content = lines[line_number - 1]
                    if self._is_exempt_line(line_content):
                        continue

                code_snippet = self._extract_code_snippet(lines, line_number)

                violation = SecurityViolation(
                    violation_type=violation_type,
                    risk_level=rule["risk_level"],
                    file_path=file_path,
                    line_number=line_number,
                    column=column,
                    code_snippet=code_snippet,
                    description=rule["description"],
                    recommendation=rule["recommendation"],
                    matched_pattern=pattern.pattern[:100] + "..." if len(pattern.pattern) > 100 else pattern.pattern
                )
                violations.append(violation)

        return violations

    def _scan_with_ast(self, content: str, file_path: str) -> List[SecurityViolation]:
        """使用AST进行更深层次的代码分析"""
        violations = []

        try:
            tree = ast.parse(content)
        except SyntaxError:
            return violations

        for node in ast.walk(tree):
            # 检测 sqlite3.connect 调用
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Attribute):
                    # 方法调用，如 sqlite3.connect()
                    if (isinstance(node.func.value, ast.Name) and
                        node.func.value.id == 'sqlite3' and
                        node.func.attr == 'connect'):

                        line_number = getattr(node, 'lineno', 1)
                        column = getattr(node, 'col_offset', 0)

                        lines = content.split('\n')
                        if 0 <= line_number - 1 < len(lines):
                            if self._is_exempt_line(lines[line_number - 1]):
                                continue

                        code_snippet = self._extract_code_snippet(lines, line_number)

                        violation = SecurityViolation(
                            violation_type=ViolationType.DIRECT_SQLITE_CONNECTION,
                            risk_level=RiskLevel.CRITICAL,
                            file_path=file_path,
                            line_number=line_number,
                            column=column,
                            code_snippet=code_snippet,
                            description="通过AST检测到直接调用 sqlite3.connect()",
                            recommendation="使用 db_router.DatabaseRouter 获取安全连接代理"
                        )
                        violations.append(violation)

                elif isinstance(node.func, ast.Name):
                    # 函数调用，如 connect()
                    if node.func.id == 'connect':
                        # 检查上下文是否可能是sqlite3
                        line_number = getattr(node, 'lineno', 1)
                        lines = content.split('\n')
                        if 0 <= line_number - 1 < len(lines):
                            line_content = lines[line_number - 1]
                            if 'sqlite' in line_content.lower():
                                if not self._is_exempt_line(line_content):
                                    code_snippet = self._extract_code_snippet(lines, line_number)
                                    violation = SecurityViolation(
                                        violation_type=ViolationType.DIRECT_SQLITE_CONNECTION,
                                        risk_level=RiskLevel.HIGH,
                                        file_path=file_path,
                                        line_number=line_number,
                                        column=getattr(node, 'col_offset', 0),
                                        code_snippet=code_snippet,
                                        description="检测到可能的直接数据库连接调用",
                                        recommendation="确认是否使用了sqlite3.connect，应通过db_router访问"
                                    )
                                    violations.append(violation)

            # 检测字符串拼接构建SQL
            if isinstance(node, ast.BinOp):
                if isinstance(node.op, ast.Add):
                    line_number = getattr(node, 'lineno', 1)
                    lines = content.split('\n')
                    if 0 <= line_number - 1 < len(lines):
                        line_content = lines[line_number - 1]
                        if any(kw in line_content.upper() for kw in ['SELECT', 'INSERT', 'UPDATE', 'DELETE']):
                            if not self._is_exempt_line(line_content):
                                code_snippet = self._extract_code_snippet(lines, line_number)
                                violation = SecurityViolation(
                                    violation_type=ViolationType.DANGEROUS_SQL_PATTERN,
                                    risk_level=RiskLevel.HIGH,
                                    file_path=file_path,
                                    line_number=line_number,
                                    column=getattr(node, 'col_offset', 0),
                                    code_snippet=code_snippet,
                                    description="检测到使用+运算符拼接SQL语句",
                                    recommendation="使用参数化查询替代字符串拼接"
                                )
                                violations.append(violation)

            # 检测 f-string SQL
            if isinstance(node, ast.JoinedStr):
                line_number = getattr(node, 'lineno', 1)
                lines = content.split('\n')
                if 0 <= line_number - 1 < len(lines):
                    line_content = lines[line_number - 1]
                    if any(kw in line_content.upper() for kw in ['SELECT', 'INSERT', 'UPDATE', 'DELETE']):
                        if not self._is_exempt_line(line_content):
                            code_snippet = self._extract_code_snippet(lines, line_number)
                            violation = SecurityViolation(
                                violation_type=ViolationType.DANGEROUS_SQL_PATTERN,
                                risk_level=RiskLevel.CRITICAL,
                                file_path=file_path,
                                line_number=line_number,
                                column=getattr(node, 'col_offset', 0),
                                code_snippet=code_snippet,
                                description="检测到使用f-string构建SQL语句",
                                recommendation="使用参数化查询，将变量作为参数传递"
                            )
                            violations.append(violation)

        return violations

    def scan_file(self, file_path: str) -> List[SecurityViolation]:
        """扫描单个Python文件

        Args:
            file_path: Python文件路径

        Returns:
            发现的违规列表
        """
        file_path = os.path.abspath(file_path)

        # 检查文件是否豁免
        if self._is_exempt_file(file_path):
            self.skipped_files.add(file_path)
            return []

        # 只扫描Python文件
        if not file_path.endswith('.py'):
            self.skipped_files.add(file_path)
            return []

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
        except (IOError, UnicodeDecodeError) as e:
            print(f"警告: 无法读取文件 {file_path}: {e}")
            self.skipped_files.add(file_path)
            return []

        lines = content.split('\n')
        violations = []

        # 1. 检测直接sqlite3连接
        violations.extend(self._check_patterns(
            content, lines, file_path,
            self.DIRECT_CONNECTION_PATTERNS,
            ViolationType.DIRECT_SQLITE_CONNECTION
        ))

        # 2. 检测危险SQL模式
        violations.extend(self._check_patterns(
            content, lines, file_path,
            self.DANGEROUS_SQL_PATTERNS,
            ViolationType.DANGEROUS_SQL_PATTERN
        ))

        # 3. 检测权限提升
        violations.extend(self._check_patterns(
            content, lines, file_path,
            self.PERMISSION_ESCALATION_PATTERNS,
            ViolationType.PERMISSION_ESCALATION
        ))

        # 4. 检测硬编码凭据
        violations.extend(self._check_patterns(
            content, lines, file_path,
            self.HARDCODED_CREDENTIAL_PATTERNS,
            ViolationType.HARDCODED_CREDENTIAL
        ))

        # 5. AST深度分析
        violations.extend(self._scan_with_ast(content, file_path))

        # 去重（基于文件、行号、类型）
        seen = set()
        unique_violations = []
        for v in violations:
            key = (v.file_path, v.line_number, v.violation_type.value)
            if key not in seen:
                seen.add(key)
                unique_violations.append(v)

        self.violations.extend(unique_violations)
        self.scanned_files.add(file_path)

        return unique_violations

    def scan_directory(self, directory: str, recursive: bool = True) -> List[SecurityViolation]:
        """扫描整个目录

        Args:
            directory: 要扫描的目录路径
            recursive: 是否递归扫描子目录

        Returns:
            发现的所有违规列表
        """
        directory = os.path.abspath(directory)
        all_violations = []

        if recursive:
            for root, dirs, files in os.walk(directory):
                # 跳过隐藏目录和常见非源码目录
                dirs[:] = [d for d in dirs if not d.startswith('.') and d not in {
                    '__pycache__', 'venv', '.venv', 'env', 'node_modules', 'dist', 'build'
                }]

                for filename in files:
                    if filename.endswith('.py'):
                        file_path = os.path.join(root, filename)
                        violations = self.scan_file(file_path)
                        all_violations.extend(violations)
        else:
            for filename in os.listdir(directory):
                if filename.endswith('.py'):
                    file_path = os.path.join(directory, filename)
                    if os.path.isfile(file_path):
                        violations = self.scan_file(file_path)
                        all_violations.extend(violations)

        return all_violations

    def generate_report(self, output_format: str = "markdown") -> ScanReport:
        """生成扫描报告

        Args:
            output_format: 报告格式，支持 "markdown", "json", "dict"

        Returns:
            扫描报告对象
        """
        # 生成统计信息
        risk_counts = {}
        type_counts = {}
        file_violations = {}

        for v in self.violations:
            risk_counts[v.risk_level.value] = risk_counts.get(v.risk_level.value, 0) + 1
            type_counts[v.violation_type.value] = type_counts.get(v.violation_type.value, 0) + 1
            file_violations[v.file_path] = file_violations.get(v.file_path, 0) + 1

        summary = {
            "total_violations": len(self.violations),
            "risk_distribution": risk_counts,
            "violation_types": type_counts,
            "files_with_violations": len(file_violations),
            "top_violated_files": sorted(file_violations.items(), key=lambda x: -x[1])[:5]
        }

        report = ScanReport(
            scan_time=datetime.now().isoformat(),
            total_files=len(self.scanned_files) + len(self.skipped_files),
            scanned_files=len(self.scanned_files),
            skipped_files=len(self.skipped_files),
            violations=sorted(self.violations, key=lambda v: (
                {RiskLevel.CRITICAL: 0, RiskLevel.HIGH: 1, RiskLevel.MEDIUM: 2, RiskLevel.LOW: 3}.get(v.risk_level, 4),
                v.file_path,
                v.line_number
            )),
            summary=summary
        )

        return report

    def clear(self) -> None:
        """清除扫描结果"""
        self.violations.clear()
        self.scanned_files.clear()
        self.skipped_files.clear()

    def get_statistics(self) -> Dict[str, Any]:
        """获取扫描统计信息"""
        return {
            "total_violations": len(self.violations),
            "scanned_files": len(self.scanned_files),
            "skipped_files": len(self.skipped_files),
            "risk_levels": {
                level.value: len([v for v in self.violations if v.risk_level == level])
                for level in RiskLevel
            },
            "violation_types": {
                vtype.value: len([v for v in self.violations if v.violation_type == vtype])
                for vtype in ViolationType
            }
        }


def main():
    """命令行入口"""
    import argparse

    parser = argparse.ArgumentParser(
        description="数据库安全扫描工具 - 检测代码中的数据库安全风险"
    )
    parser.add_argument(
        "path",
        help="要扫描的文件或目录路径"
    )
    parser.add_argument(
        "-r", "--recursive",
        action="store_true",
        default=True,
        help="递归扫描子目录（默认启用）"
    )
    parser.add_argument(
        "-f", "--format",
        choices=["markdown", "json", "console"],
        default="console",
        help="输出格式"
    )
    parser.add_argument(
        "-o", "--output",
        help="输出文件路径（可选）"
    )

    args = parser.parse_args()

    scanner = DBSecurityScanner()

    if os.path.isfile(args.path):
        print(f"扫描文件: {args.path}")
        scanner.scan_file(args.path)
    elif os.path.isdir(args.path):
        print(f"扫描目录: {args.path}")
        scanner.scan_directory(args.path, recursive=args.recursive)
    else:
        print(f"错误: 路径不存在: {args.path}")
        return 1

    report = scanner.generate_report()
    stats = scanner.get_statistics()

    # 输出报告
    if args.format == "json":
        output = report.to_json()
    elif args.format == "markdown":
        output = report.to_markdown()
    else:
        # Console format
        output = f"""
数据库安全扫描结果
==================
扫描时间: {report.scan_time}
扫描文件: {stats['scanned_files']}
跳过文件: {stats['skipped_files']}
发现问题: {stats['total_violations']}

风险分布:
  🔴 Critical: {stats['risk_levels'].get('Critical', 0)}
  🟠 High: {stats['risk_levels'].get('High', 0)}
  🟡 Medium: {stats['risk_levels'].get('Medium', 0)}
  🟢 Low: {stats['risk_levels'].get('Low', 0)}

违规类型:
  直接sqlite3连接: {stats['violation_types'].get('直接sqlite3连接', 0)}
  危险SQL模式: {stats['violation_types'].get('危险SQL模式', 0)}
  权限提升: {stats['violation_types'].get('权限提升', 0)}
  硬编码凭据: {stats['violation_types'].get('硬编码凭据', 0)}
"""
        if report.violations:
            output += "\n详细问题:\n"
            for i, v in enumerate(report.violations[:10], 1):
                emoji = {"Critical": "🔴", "High": "🟠", "Medium": "🟡", "Low": "🟢"}.get(v.risk_level.value, "⚪")
                output += f"\n{i}. {emoji} [{v.risk_level.value}] {v.violation_type.value}\n"
                output += f"   文件: {v.file_path}:{v.line_number}\n"
                output += f"   描述: {v.description}\n"
            if len(report.violations) > 10:
                output += f"\n... 还有 {len(report.violations) - 10} 个问题\n"

    if args.output:
        with open(args.output, 'w', encoding='utf-8') as f:
            f.write(output)
        print(f"报告已保存到: {args.output}")
    else:
        print(output)

    # 返回退出码
    critical_count = stats['risk_levels'].get('Critical', 0)
    high_count = stats['risk_levels'].get('High', 0)
    return 1 if (critical_count > 0 or high_count > 0) else 0


if __name__ == "__main__":
    exit(main())
