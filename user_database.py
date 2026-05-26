import os
import sqlite3
import hashlib
import logging
from datetime import datetime
from typing import Optional, List, Dict, Any
from werkzeug.security import generate_password_hash, check_password_hash

from db_router import DatabaseRouter, DatabasePermission

logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE_FILE = os.path.join(BASE_DIR, 'users.db')


class UserDatabase:
    """用户数据库管理类"""

    def __init__(self, db_path: str = None):
        self.db_path = db_path or DATABASE_FILE
        self._router = DatabaseRouter(self.db_path)
        self._register_whitelist_queries()
        self._init_database()

    def _register_whitelist_queries(self):
        """注册所有需要的查询到白名单"""
        # SELECT 查询
        self._router.register_whitelist_template(
            "select_all_users",
            "SELECT username, password, role, status, invitation_code, created_at, last_login, invited_by FROM users"
        )
        self._router.register_whitelist_template(
            "select_user_by_username",
            "SELECT username, password, role, status, invitation_code, created_at, last_login, invited_by FROM users WHERE username = ?"
        )
        self._router.register_whitelist_template(
            "select_user_by_invitation_code",
            "SELECT username, password, role, status, invitation_code, created_at, last_login, invited_by FROM users WHERE invitation_code = ?"
        )

        # INSERT 查询
        self._router.register_whitelist_template(
            "insert_user",
            "INSERT INTO users (username, password, role, status, invitation_code, created_at, last_login, invited_by) VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
        )
        self._router.register_whitelist_template(
            "insert_or_replace_user",
            "INSERT OR REPLACE INTO users (username, password, role, status, invitation_code, created_at, last_login, invited_by) VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
        )

        # UPDATE 查询 - 动态构建的UPDATE需要注册模板模式
        self._router.register_whitelist_pattern(
            r"^\s*UPDATE\s+users\s+SET\s+\w+\s*=\s*\?\s*(,\s*\w+\s*=\s*\?\s*)*WHERE\s+\w+\s*=\s*\?\s*$"
        )

        # DELETE 查询
        self._router.register_whitelist_template(
            "delete_user",
            "DELETE FROM users WHERE username = ?"
        )
        self._router.register_whitelist_template(
            "delete_all_users",
            "DELETE FROM users"
        )

        # DDL 查询 (ADMIN权限)
        self._router.register_whitelist_template(
            "create_users_table",
            """CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                role TEXT DEFAULT 'user',
                status TEXT DEFAULT 'active',
                invitation_code TEXT UNIQUE,
                created_at TEXT,
                last_login TEXT,
                invited_by TEXT
            )"""
        )
        self._router.register_whitelist_template(
            "create_index_username",
            "CREATE INDEX IF NOT EXISTS idx_username ON users(username)"
        )
        self._router.register_whitelist_template(
            "create_index_invitation_code",
            "CREATE INDEX IF NOT EXISTS idx_invitation_code ON users(invitation_code)"
        )

    def _get_connection(self, permission: DatabasePermission = DatabasePermission.READ_ONLY):
        """获取数据库连接（使用DatabaseRouter）"""
        return self._router.connection(permission)

    def _init_database(self):
        """初始化数据库表结构"""
        with self._get_connection(DatabasePermission.ADMIN) as conn:
            # 创建用户表
            conn.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    password TEXT NOT NULL,
                    role TEXT DEFAULT 'user',
                    status TEXT DEFAULT 'active',
                    invitation_code TEXT UNIQUE,
                    created_at TEXT,
                    last_login TEXT,
                    invited_by TEXT
                )
            ''')

            # 创建索引
            conn.execute('''
                CREATE INDEX IF NOT EXISTS idx_username ON users(username)
            ''')
            conn.execute('''
                CREATE INDEX IF NOT EXISTS idx_invitation_code ON users(invitation_code)
            ''')

            conn.commit()
            logger.info('用户数据库初始化完成')

    def load_users(self) -> List[Dict[str, Any]]:
        """加载所有用户"""
        try:
            with self._get_connection(DatabasePermission.READ_ONLY) as conn:
                cursor = conn.execute('''
                    SELECT username, password, role, status, invitation_code,
                           created_at, last_login, invited_by
                    FROM users
                ''')
                rows = cursor.fetchall()

                users = []
                for row in rows:
                    user = dict(row)
                    # 兼容旧数据：确保字段存在
                    if user.get('last_login') is None:
                        user['last_login'] = '从未登录'
                    users.append(user)

                return users
        except Exception as e:
            logger.error(f"加载用户数据失败: {e}")
            return []

    def get_user_by_username(self, username: str) -> Optional[Dict[str, Any]]:
        """根据用户名获取用户"""
        try:
            with self._get_connection(DatabasePermission.READ_ONLY) as conn:
                cursor = conn.execute('''
                    SELECT username, password, role, status, invitation_code,
                           created_at, last_login, invited_by
                    FROM users WHERE username = ?
                ''', (username,))
                row = cursor.fetchone()

                if row:
                    user = dict(row)
                    if user.get('last_login') is None:
                        user['last_login'] = '从未登录'
                    return user
                return None
        except Exception as e:
            logger.error(f"获取用户失败: {e}")
            return None

    def get_user_by_invitation_code(self, code: str) -> Optional[Dict[str, Any]]:
        """根据邀请码获取用户"""
        try:
            with self._get_connection(DatabasePermission.READ_ONLY) as conn:
                cursor = conn.execute('''
                    SELECT username, password, role, status, invitation_code,
                           created_at, last_login, invited_by
                    FROM users WHERE invitation_code = ?
                ''', (code,))
                row = cursor.fetchone()

                if row:
                    user = dict(row)
                    if user.get('last_login') is None:
                        user['last_login'] = '从未登录'
                    return user
                return None
        except Exception as e:
            logger.error(f"获取用户失败: {e}")
            return None

    def verify_user(self, username: str, password: str) -> bool:
        """验证用户名和密码，支持旧SHA256哈希自动迁移到PBKDF2"""
        user = self.get_user_by_username(username)
        if not user:
            return False

        stored_hash = user.get('password', '')

        if stored_hash.startswith('pbkdf2:'):
            return check_password_hash(stored_hash, password)

        legacy_hash = hashlib.sha256(password.encode('utf-8')).hexdigest()
        if legacy_hash == stored_hash:
            self.update_user(username, {'password': generate_password_hash(password, method='pbkdf2:sha256', salt_length=16)})
            logger.info(f"用户 {username} 密码已从SHA256迁移到PBKDF2")
            return True

        return False

    def create_user(self, user_data: Dict[str, Any]) -> bool:
        """创建新用户"""
        try:
            with self._get_connection(DatabasePermission.READ_WRITE) as conn:
                conn.execute('''
                    INSERT INTO users (username, password, role, status, invitation_code,
                                      created_at, last_login, invited_by)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    user_data.get('username'),
                    user_data.get('password'),
                    user_data.get('role', 'user'),
                    user_data.get('status', 'active'),
                    user_data.get('invitation_code'),
                    user_data.get('created_at', datetime.now().strftime('%Y-%m-%d %H:%M:%S')),
                    user_data.get('last_login'),
                    user_data.get('invited_by')
                ))
                conn.commit()
                logger.info(f"用户 {user_data.get('username')} 创建成功")
                return True
        except sqlite3.IntegrityError as e:
            logger.error(f"创建用户失败，用户名或邀请码已存在: {e}")
            return False
        except Exception as e:
            logger.error(f"创建用户失败: {e}")
            return False

    def update_user(self, username: str, updates: Dict[str, Any]) -> bool:
        """更新用户信息"""
        try:
            # 构建动态更新语句
            allowed_fields = ['password', 'role', 'status', 'invitation_code', 'last_login']
            set_clauses = []
            values = []

            for field in allowed_fields:
                if field in updates:
                    set_clauses.append(f"{field} = ?")
                    values.append(updates[field])

            if not set_clauses:
                return False

            values.append(username)

            with self._get_connection(DatabasePermission.READ_WRITE) as conn:
                query = f"UPDATE users SET {', '.join(set_clauses)} WHERE username = ?"
                cursor = conn.execute(query, values)
                conn.commit()

                if cursor.rowcount > 0:
                    logger.info(f"用户 {username} 更新成功")
                    return True
                return False
        except Exception as e:
            logger.error(f"更新用户失败: {e}")
            return False

    def update_last_login(self, username: str, login_time: str) -> bool:
        """更新用户最后登录时间"""
        return self.update_user(username, {'last_login': login_time})

    def delete_user(self, username: str) -> bool:
        """删除用户"""
        try:
            with self._get_connection(DatabasePermission.READ_WRITE) as conn:
                cursor = conn.execute('DELETE FROM users WHERE username = ?', (username,))
                conn.commit()

                if cursor.rowcount > 0:
                    logger.info(f"用户 {username} 删除成功")
                    return True
                return False
        except Exception as e:
            logger.error(f"删除用户失败: {e}")
            return False

    def user_exists(self, username: str) -> bool:
        """检查用户是否存在"""
        return self.get_user_by_username(username) is not None

    def invitation_code_exists(self, code: str) -> bool:
        """检查邀请码是否存在"""
        return self.get_user_by_invitation_code(code) is not None

    def migrate_from_json(self, json_data: List[Dict[str, Any]]) -> int:
        """从JSON数据迁移用户到数据库"""
        migrated_count = 0

        with self._get_connection(DatabasePermission.READ_WRITE) as conn:
            for user_data in json_data:
                try:
                    conn.execute('''
                        INSERT OR REPLACE INTO users (username, password, role, status, invitation_code,
                                                      created_at, last_login, invited_by)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (
                        user_data.get('username'),
                        user_data.get('password'),
                        user_data.get('role', 'user'),
                        user_data.get('status', 'active'),
                        user_data.get('invitation_code'),
                        user_data.get('created_at', datetime.now().strftime('%Y-%m-%d %H:%M:%S')),
                        user_data.get('last_login'),
                        user_data.get('invited_by')
                    ))
                    migrated_count += 1
                except Exception as e:
                    logger.error(f"迁移用户 {user_data.get('username')} 失败: {e}")

            conn.commit()

        logger.info(f"成功迁移 {migrated_count} 个用户")
        return migrated_count


# 全局数据库实例
_db_instance: Optional[UserDatabase] = None


def get_user_db() -> UserDatabase:
    """获取全局用户数据库实例"""
    global _db_instance
    if _db_instance is None:
        _db_instance = UserDatabase()
    return _db_instance


def load_users() -> List[Dict[str, Any]]:
    """兼容旧接口：加载所有用户"""
    return get_user_db().load_users()


def verify_user(username: str, password: str) -> bool:
    """兼容旧接口：验证用户"""
    return get_user_db().verify_user(username, password)


def save_users(users: List[Dict[str, Any]]) -> bool:
    """兼容旧接口：保存所有用户（批量替换）"""
    db = get_user_db()

    try:
        with db._get_connection(DatabasePermission.READ_WRITE) as conn:
            # 清空表并重新插入
            conn.execute('DELETE FROM users')

            for user_data in users:
                conn.execute('''
                    INSERT INTO users (username, password, role, status, invitation_code,
                                      created_at, last_login, invited_by)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    user_data.get('username'),
                    user_data.get('password'),
                    user_data.get('role', 'user'),
                    user_data.get('status', 'active'),
                    user_data.get('invitation_code'),
                    user_data.get('created_at', datetime.now().strftime('%Y-%m-%d %H:%M:%S')),
                    user_data.get('last_login'),
                    user_data.get('invited_by')
                ))

            conn.commit()
            logger.info(f"批量保存 {len(users)} 个用户成功")
            return True
    except Exception as e:
        logger.error(f"批量保存用户失败: {e}")
        return False
