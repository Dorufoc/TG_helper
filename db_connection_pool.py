import sqlite3
import threading
import logging
import time
from datetime import datetime
from typing import Optional, Dict, List, Any, Tuple
from contextlib import contextmanager
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class PermissionLevel(Enum):
    """数据库连接权限级别"""
    READ_ONLY = "read_only"
    READ_WRITE = "read_write"
    ADMIN = "admin"


@dataclass
class PooledConnection:
    """
    连接包装类，包含连接元数据

    Attributes:
        connection: SQLite数据库连接对象
        created_at: 连接创建时间戳
        last_used_at: 连接最后使用时间戳
        thread_id: 创建该连接的线程ID
        permission_level: 连接权限级别
        db_path: 数据库文件路径
        is_active: 连接是否处于活跃状态
        use_count: 连接被使用次数
    """
    connection: sqlite3.Connection
    created_at: float = field(default_factory=time.time)
    last_used_at: float = field(default_factory=time.time)
    thread_id: int = field(default_factory=threading.current_thread)
    permission_level: PermissionLevel = PermissionLevel.READ_WRITE
    db_path: str = ""
    is_active: bool = True
    use_count: int = 0

    def __post_init__(self):
        if isinstance(self.thread_id, threading.Thread):
            self.thread_id = self.thread_id.ident or 0

    def update_last_used(self):
        """更新最后使用时间"""
        self.last_used_at = time.time()
        self.use_count += 1

    def mark_inactive(self):
        """标记连接为非活跃状态"""
        self.is_active = False

    def get_idle_time(self) -> float:
        """获取连接空闲时间（秒）"""
        return time.time() - self.last_used_at

    def get_age(self) -> float:
        """获取连接存活时间（秒）"""
        return time.time() - self.created_at

    def is_valid(self) -> bool:
        """检查连接是否有效"""
        if not self.is_active:
            return False
        try:
            self.connection.execute("SELECT 1")
            return True
        except (sqlite3.Error, AttributeError):
            return False

    def close(self):
        """安全关闭连接"""
        try:
            if self.connection:
                self.connection.close()
        except sqlite3.Error as e:
            logger.warning(f"关闭连接时出错: {e}")
        finally:
            self.is_active = False

    def __repr__(self) -> str:
        return (f"PooledConnection(db={self.db_path}, "
                f"thread={self.thread_id}, "
                f"perm={self.permission_level.value}, "
                f"idle={self.get_idle_time():.1f}s, "
                f"uses={self.use_count})")


class ConnectionPool:
    """
    SQLite数据库连接池管理类

    功能特性：
    1. 线程本地存储实现同线程连接复用
    2. 根据数据库路径和权限级别管理连接
    3. 最大空闲时间自动回收（默认300秒）
    4. 全局最大连接数限制（默认20）
    5. 每数据库最大连接数限制（默认10）
    6. 连接健康检查和自动重建
    """

    _instance: Optional['ConnectionPool'] = None
    _instance_lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(
        self,
        max_connections: int = 20,
        max_connections_per_db: int = 10,
        max_idle_time: float = 300.0,
        cleanup_interval: float = 60.0,
        connection_timeout: float = 30.0
    ):
        if self._initialized:
            return

        self._initialized = True

        # 配置参数
        self._max_connections = max_connections
        self._max_connections_per_db = max_connections_per_db
        self._max_idle_time = max_idle_time
        self._cleanup_interval = cleanup_interval
        self._connection_timeout = connection_timeout

        # 连接存储
        # 结构: {db_path: {permission_level: [PooledConnection, ...]}}
        self._available_connections: Dict[str, Dict[PermissionLevel, List[PooledConnection]]] = {}
        self._in_use_connections: Dict[str, Dict[PermissionLevel, List[PooledConnection]]] = {}

        # 线程本地存储 - 用于同线程连接复用
        self._thread_local = threading.local()

        # 线程锁
        self._pool_lock = threading.RLock()
        self._connection_creation_lock = threading.Lock()

        # 统计信息
        self._stats = {
            'total_created': 0,
            'total_reused': 0,
            'total_closed': 0,
            'health_check_failures': 0,
            'timeout_waits': 0
        }

        # 启动清理线程
        self._cleanup_thread: Optional[threading.Thread] = None
        self._stop_cleanup = threading.Event()
        self._start_cleanup_thread()

        logger.info(f"连接池初始化完成: max={max_connections}, per_db={max_connections_per_db}, "
                    f"idle_timeout={max_idle_time}s")

    def _start_cleanup_thread(self):
        """启动后台清理线程"""
        def cleanup_worker():
            while not self._stop_cleanup.wait(self._cleanup_interval):
                try:
                    self._cleanup_expired_connections()
                except Exception as e:
                    logger.error(f"清理过期连接时出错: {e}")

        self._cleanup_thread = threading.Thread(
            target=cleanup_worker,
            name="ConnectionPool-Cleanup",
            daemon=True
        )
        self._cleanup_thread.start()

    def _get_thread_connections(self) -> Dict[Tuple[str, PermissionLevel], PooledConnection]:
        """获取当前线程的连接字典"""
        if not hasattr(self._thread_local, 'connections'):
            self._thread_local.connections = {}
        return self._thread_local.connections

    def _create_connection(
        self,
        db_path: str,
        permission_level: PermissionLevel
    ) -> PooledConnection:
        """创建新的数据库连接"""
        with self._connection_creation_lock:
            try:
                # 根据权限级别设置连接模式
                if permission_level == PermissionLevel.READ_ONLY:
                    uri = f"file:{db_path}?mode=ro"
                    conn = sqlite3.connect(uri, uri=True, check_same_thread=False)
                else:
                    conn = sqlite3.connect(db_path, check_same_thread=False)
                    conn.row_factory = sqlite3.Row

                # 设置连接优化参数
                conn.execute("PRAGMA foreign_keys = ON")
                conn.execute("PRAGMA journal_mode = WAL")
                conn.execute("PRAGMA synchronous = NORMAL")

                pooled_conn = PooledConnection(
                    connection=conn,
                    permission_level=permission_level,
                    db_path=db_path
                )

                self._stats['total_created'] += 1
                logger.debug(f"创建新连接: {pooled_conn}")
                return pooled_conn

            except sqlite3.Error as e:
                logger.error(f"创建数据库连接失败 {db_path}: {e}")
                raise

    def _get_connection_key(self, db_path: str, permission_level: PermissionLevel) -> Tuple[str, PermissionLevel]:
        """生成连接键"""
        return (db_path, permission_level)

    def _get_db_count(self, db_path: str) -> int:
        """获取指定数据库的连接总数"""
        available = sum(
            len(conns)
            for perm, conns in self._available_connections.get(db_path, {}).items()
        )
        in_use = sum(
            len(conns)
            for perm, conns in self._in_use_connections.get(db_path, {}).items()
        )
        return available + in_use

    def _get_total_count(self) -> int:
        """获取全局连接总数"""
        total = 0
        for db_path in self._available_connections:
            total += self._get_db_count(db_path)
        return total

    def _move_to_available(self, pooled_conn: PooledConnection):
        """将连接移回可用池"""
        db_path = pooled_conn.db_path
        perm_level = pooled_conn.permission_level

        with self._pool_lock:
            # 从使用中移除
            if db_path in self._in_use_connections:
                if perm_level in self._in_use_connections[db_path]:
                    try:
                        self._in_use_connections[db_path][perm_level].remove(pooled_conn)
                    except ValueError:
                        pass

            # 添加到可用池
            if db_path not in self._available_connections:
                self._available_connections[db_path] = {}
            if perm_level not in self._available_connections[db_path]:
                self._available_connections[db_path][perm_level] = []

            self._available_connections[db_path][perm_level].append(pooled_conn)

    def _move_to_in_use(self, pooled_conn: PooledConnection):
        """将连接标记为使用中"""
        db_path = pooled_conn.db_path
        perm_level = pooled_conn.permission_level

        with self._pool_lock:
            if db_path not in self._in_use_connections:
                self._in_use_connections[db_path] = {}
            if perm_level not in self._in_use_connections[db_path]:
                self._in_use_connections[db_path][perm_level] = []

            self._in_use_connections[db_path][perm_level].append(pooled_conn)

    def _find_available_connection(
        self,
        db_path: str,
        permission_level: PermissionLevel
    ) -> Optional[PooledConnection]:
        """在可用池中查找合适的连接"""
        with self._pool_lock:
            if db_path not in self._available_connections:
                return None
            if permission_level not in self._available_connections[db_path]:
                return None

            available_list = self._available_connections[db_path][permission_level]

            # 查找有效的连接
            for conn in available_list[:]:
                if conn.is_valid():
                    available_list.remove(conn)
                    return conn
                else:
                    # 移除无效连接
                    available_list.remove(conn)
                    conn.close()
                    self._stats['health_check_failures'] += 1

            return None

    def get_connection(
        self,
        db_path: str,
        permission_level: PermissionLevel = PermissionLevel.READ_WRITE,
        timeout: Optional[float] = None
    ) -> PooledConnection:
        """
        获取数据库连接

        Args:
            db_path: 数据库文件路径
            permission_level: 权限级别
            timeout: 等待连接的超时时间（秒）

        Returns:
            PooledConnection: 包装后的数据库连接

        Raises:
            TimeoutError: 获取连接超时
            RuntimeError: 连接池已满且无法创建新连接
        """
        timeout = timeout or self._connection_timeout
        start_time = time.time()
        current_thread_id = threading.current_thread().ident or 0

        # 检查线程本地存储中是否有可复用的连接
        thread_connections = self._get_thread_connections()
        conn_key = self._get_connection_key(db_path, permission_level)

        if conn_key in thread_connections:
            pooled_conn = thread_connections[conn_key]
            if pooled_conn.is_valid():
                pooled_conn.update_last_used()
                self._stats['total_reused'] += 1
                logger.debug(f"复用线程本地连接: {pooled_conn}")
                return pooled_conn
            else:
                # 连接已失效，从线程存储中移除
                del thread_connections[conn_key]

        # 尝试从连接池获取
        while time.time() - start_time < timeout:
            # 尝试获取可用连接
            pooled_conn = self._find_available_connection(db_path, permission_level)
            if pooled_conn:
                pooled_conn.update_last_used()
                pooled_conn.thread_id = current_thread_id
                self._move_to_in_use(pooled_conn)
                thread_connections[conn_key] = pooled_conn
                self._stats['total_reused'] += 1
                logger.debug(f"从连接池获取连接: {pooled_conn}")
                return pooled_conn

            # 检查是否可以创建新连接
            with self._pool_lock:
                db_count = self._get_db_count(db_path)
                total_count = self._get_total_count()

                if db_count < self._max_connections_per_db and total_count < self._max_connections:
                    try:
                        pooled_conn = self._create_connection(db_path, permission_level)
                        pooled_conn.thread_id = current_thread_id
                        self._move_to_in_use(pooled_conn)
                        thread_connections[conn_key] = pooled_conn
                        return pooled_conn
                    except sqlite3.Error:
                        raise

            # 等待一段时间后重试
            self._stats['timeout_waits'] += 1
            time.sleep(0.1)

        raise TimeoutError(f"获取数据库连接超时 ({timeout}s): {db_path}")

    def release_connection(self, pooled_conn: PooledConnection, close: bool = False):
        """
        释放连接回连接池

        Args:
            pooled_conn: 要释放的连接
            close: 是否直接关闭连接而不是放回池中
        """
        if pooled_conn is None:
            return

        conn_key = self._get_connection_key(pooled_conn.db_path, pooled_conn.permission_level)

        # 从线程本地存储中移除
        thread_connections = self._get_thread_connections()
        if conn_key in thread_connections:
            del thread_connections[conn_key]

        if close or not pooled_conn.is_valid():
            pooled_conn.close()
            self._stats['total_closed'] += 1

            # 从使用中移除
            with self._pool_lock:
                db_path = pooled_conn.db_path
                perm_level = pooled_conn.permission_level
                if db_path in self._in_use_connections:
                    if perm_level in self._in_use_connections[db_path]:
                        try:
                            self._in_use_connections[db_path][perm_level].remove(pooled_conn)
                        except ValueError:
                            pass
        else:
            pooled_conn.update_last_used()
            self._move_to_available(pooled_conn)
            logger.debug(f"连接释放回池中: {pooled_conn}")

    def _cleanup_expired_connections(self):
        """清理过期连接"""
        expired_connections: List[PooledConnection] = []

        with self._pool_lock:
            for db_path in list(self._available_connections.keys()):
                for perm_level in list(self._available_connections[db_path].keys()):
                    connections = self._available_connections[db_path][perm_level]
                    for conn in connections[:]:
                        if conn.get_idle_time() > self._max_idle_time:
                            connections.remove(conn)
                            expired_connections.append(conn)

        # 关闭过期连接
        for conn in expired_connections:
            conn.close()
            self._stats['total_closed'] += 1
            logger.debug(f"清理过期连接: {conn}")

        if expired_connections:
            logger.info(f"清理了 {len(expired_connections)} 个过期连接")

    def close_all_connections(self, db_path: Optional[str] = None):
        """
        关闭所有连接

        Args:
            db_path: 如果指定，只关闭该数据库的连接
        """
        all_connections: List[PooledConnection] = []

        with self._pool_lock:
            paths_to_close = [db_path] if db_path else list(self._available_connections.keys())

            for path in paths_to_close:
                if path in self._available_connections:
                    for perm_level, connections in self._available_connections[path].items():
                        all_connections.extend(connections)
                    self._available_connections[path] = {}

                if path in self._in_use_connections:
                    for perm_level, connections in self._in_use_connections[path].items():
                        all_connections.extend(connections)
                    self._in_use_connections[path] = {}

        # 关闭所有收集到的连接
        for conn in all_connections:
            conn.close()
            self._stats['total_closed'] += 1

        logger.info(f"关闭了 {len(all_connections)} 个连接")

    def get_stats(self) -> Dict[str, Any]:
        """获取连接池统计信息"""
        with self._pool_lock:
            available_count = sum(
                sum(len(conns) for conns in perms.values())
                for perms in self._available_connections.values()
            )
            in_use_count = sum(
                sum(len(conns) for conns in perms.values())
                for perms in self._in_use_connections.values()
            )

            return {
                'total_connections': available_count + in_use_count,
                'available_connections': available_count,
                'in_use_connections': in_use_count,
                'max_connections': self._max_connections,
                'max_connections_per_db': self._max_connections_per_db,
                'max_idle_time': self._max_idle_time,
                **self._stats
            }

    def shutdown(self):
        """关闭连接池，释放所有资源"""
        logger.info("正在关闭连接池...")
        self._stop_cleanup.set()

        if self._cleanup_thread and self._cleanup_thread.is_alive():
            self._cleanup_thread.join(timeout=5.0)

        self.close_all_connections()
        ConnectionPool._instance = None
        self._initialized = False
        logger.info("连接池已关闭")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.shutdown()


@contextmanager
def get_pooled_connection(
    db_path: str,
    permission_level: PermissionLevel = PermissionLevel.READ_WRITE,
    timeout: Optional[float] = None
):
    """
    上下文管理器，用于获取和自动释放连接

    Usage:
        with get_pooled_connection('users.db') as conn:
            cursor = conn.execute("SELECT * FROM users")
            rows = cursor.fetchall()
    """
    pool = ConnectionPool()
    pooled_conn = None
    try:
        pooled_conn = pool.get_connection(db_path, permission_level, timeout)
        yield pooled_conn.connection
    finally:
        if pooled_conn:
            pool.release_connection(pooled_conn)


def init_connection_pool(
    max_connections: int = 20,
    max_connections_per_db: int = 10,
    max_idle_time: float = 300.0,
    cleanup_interval: float = 60.0
) -> ConnectionPool:
    """
    初始化连接池（单例模式）

    Returns:
        ConnectionPool: 连接池实例
    """
    return ConnectionPool(
        max_connections=max_connections,
        max_connections_per_db=max_connections_per_db,
        max_idle_time=max_idle_time,
        cleanup_interval=cleanup_interval
    )


def get_pool() -> ConnectionPool:
    """获取连接池实例"""
    return ConnectionPool()


def close_pool():
    """关闭连接池"""
    pool = ConnectionPool()
    pool.shutdown()
