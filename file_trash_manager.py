"""
文件回收站管理器模块

提供安全的文件回收站功能，包括文件移入回收站、恢复、永久删除、自动清理等功能。
作为文件删除操作的中间层，防止误删并提供恢复机制。
"""

import os
import json
import shutil
import logging
import threading
import uuid
from datetime import datetime, timedelta
from dataclasses import dataclass, field, asdict
from typing import Optional, List, Dict, Any
from pathlib import Path


class TrashError(Exception):
    """回收站操作错误基类"""
    pass


class TrashItemNotFoundError(TrashError):
    """回收站项目未找到错误"""
    pass


class TrashItemExpiredError(TrashError):
    """回收站项目已过期错误"""
    pass


class TrashRestoreError(TrashError):
    """文件恢复错误"""
    pass


@dataclass
class TrashItem:
    """回收站项目数据类
    
    表示一个被移入回收站的文件记录。
    
    Attributes:
        trash_id: 回收站项目唯一标识符（UUID）
        original_path: 文件原始路径
        trash_path: 文件在回收站中的存储路径
        deleted_at: 删除时间（ISO格式时间戳）
        expires_at: 过期时间（ISO格式时间戳）
        file_size: 文件大小（字节）
        deleted_by: 删除操作执行者（可选）
    """
    trash_id: str
    original_path: str
    trash_path: str
    deleted_at: str
    expires_at: str
    file_size: int
    deleted_by: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """将TrashItem转换为字典
        
        Returns:
            包含所有字段的字典
        """
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'TrashItem':
        """从字典创建TrashItem实例
        
        Args:
            data: 包含TrashItem字段的字典
            
        Returns:
            TrashItem实例
        """
        return cls(
            trash_id=data['trash_id'],
            original_path=data['original_path'],
            trash_path=data['trash_path'],
            deleted_at=data['deleted_at'],
            expires_at=data['expires_at'],
            file_size=data['file_size'],
            deleted_by=data.get('deleted_by')
        )
    
    def is_expired(self) -> bool:
        """检查项目是否已过期
        
        Returns:
            如果已过期返回True，否则返回False
        """
        try:
            expires = datetime.fromisoformat(self.expires_at)
            return datetime.now() > expires
        except ValueError:
            return True


class TrashManager:
    """回收站管理器（单例模式）
    
    管理文件回收站的所有操作，包括移入、恢复、清理等。
    线程安全，支持自动清理机制。
    
    Attributes:
        trash_path: 回收站目录路径
        retention_days: 文件保留天数
        auto_cleanup_interval: 自动清理间隔（秒），None表示不自动清理
    """
    
    _instance: Optional['TrashManager'] = None
    _lock: threading.RLock = threading.RLock()
    
    def __new__(cls, *args, **kwargs) -> 'TrashManager':
        """单例模式实现"""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(
        self,
        trash_path: str = '.trash',
        retention_days: int = 7,
        auto_cleanup_interval: Optional[int] = None,
        logger: Optional[logging.Logger] = None
    ):
        """初始化回收站管理器
        
        Args:
            trash_path: 回收站目录路径（默认 '.trash'）
            retention_days: 文件保留天数（默认7天）
            auto_cleanup_interval: 自动清理间隔（秒），None表示不自动清理
            logger: 日志记录器（可选）
        """
        with self._lock:
            if self._initialized:
                return
            
            self._trash_path = Path(trash_path)
            self._retention_days = retention_days
            self._auto_cleanup_interval = auto_cleanup_interval
            self._logger = logger or self._create_default_logger()
            
            # 索引文件路径
            self._index_file = self._trash_path / 'trash_index.json'
            
            # 内存中的索引缓存
            self._index: Dict[str, TrashItem] = {}
            
            # 自动清理定时器
            self._cleanup_timer: Optional[threading.Timer] = None
            self._stop_cleanup = threading.Event()
            
            # 初始化回收站目录和索引
            self._init_trash_directory()
            self._load_index()
            
            # 启动自动清理（如果配置了间隔）
            if self._auto_cleanup_interval:
                self._start_auto_cleanup()
            
            self._initialized = True
    
    def _create_default_logger(self) -> logging.Logger:
        """创建默认的日志记录器"""
        logger = logging.getLogger('file_trash_manager')
        if not logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
            handler.setFormatter(formatter)
            logger.addHandler(handler)
            logger.setLevel(logging.INFO)
        return logger
    
    def _init_trash_directory(self) -> None:
        """初始化回收站目录结构"""
        try:
            self._trash_path.mkdir(parents=True, exist_ok=True)
            self._logger.debug(f"回收站目录已初始化: {self._trash_path}")
        except OSError as e:
            self._logger.error(f"创建回收站目录失败: {e}")
            raise TrashError(f"无法创建回收站目录: {e}")
    
    def _load_index(self) -> None:
        """从文件加载索引"""
        with self._lock:
            if not self._index_file.exists():
                self._index = {}
                return
            
            try:
                with open(self._index_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                self._index = {
                    item_id: TrashItem.from_dict(item_data)
                    for item_id, item_data in data.items()
                }
                self._logger.debug(f"已加载 {len(self._index)} 个回收站项目")
            except (json.JSONDecodeError, KeyError, TypeError) as e:
                self._logger.error(f"加载回收站索引失败: {e}")
                self._index = {}
    
    def _save_index(self) -> None:
        """保存索引到文件"""
        with self._lock:
            try:
                data = {
                    item_id: item.to_dict()
                    for item_id, item in self._index.items()
                }
                
                # 使用临时文件写入，然后重命名，确保原子性
                temp_file = self._index_file.with_suffix('.tmp')
                with open(temp_file, 'w', encoding='utf-8') as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                
                temp_file.replace(self._index_file)
                self._logger.debug(f"已保存回收站索引: {len(data)} 个项目")
            except OSError as e:
                self._logger.error(f"保存回收站索引失败: {e}")
                raise TrashError(f"无法保存回收站索引: {e}")
    
    def _generate_trash_id(self) -> str:
        """生成唯一的回收站项目ID"""
        return str(uuid.uuid4())
    
    def _calculate_expires_at(self) -> str:
        """计算过期时间"""
        expires = datetime.now() + timedelta(days=self._retention_days)
        return expires.isoformat()
    
    def _get_file_size(self, file_path: Path) -> int:
        """获取文件大小"""
        try:
            return file_path.stat().st_size
        except OSError:
            return 0
    
    def _start_auto_cleanup(self) -> None:
        """启动自动清理定时器"""
        def cleanup_task():
            while not self._stop_cleanup.is_set():
                try:
                    self.cleanup_expired()
                except Exception as e:
                    self._logger.error(f"自动清理失败: {e}")
                
                # 等待下一个周期或停止信号
                self._stop_cleanup.wait(timeout=self._auto_cleanup_interval)
        
        self._cleanup_timer = threading.Thread(target=cleanup_task, daemon=True)
        self._cleanup_timer.start()
        self._logger.info(f"自动清理已启动，间隔: {self._auto_cleanup_interval}秒")
    
    def stop_auto_cleanup(self) -> None:
        """停止自动清理"""
        if self._cleanup_timer and self._cleanup_timer.is_alive():
            self._stop_cleanup.set()
            self._cleanup_timer.join(timeout=5)
            self._logger.info("自动清理已停止")
    
    def move_to_trash(self, file_path: str, deleted_by: Optional[str] = None) -> str:
        """将文件移入回收站
        
        Args:
            file_path: 要删除的文件路径
            deleted_by: 删除操作执行者（可选）
            
        Returns:
            回收站项目ID（trash_id）
            
        Raises:
            TrashError: 文件不存在或移动失败
        """
        with self._lock:
            source_path = Path(file_path).resolve()
            
            # 检查文件是否存在
            if not source_path.exists():
                raise TrashError(f"文件不存在: {file_path}")
            
            if not source_path.is_file():
                raise TrashError(f"路径不是文件: {file_path}")
            
            # 生成回收站项目ID和存储路径
            trash_id = self._generate_trash_id()
            trash_file_name = f"{trash_id}_{source_path.name}"
            trash_file_path = self._trash_path / trash_file_name
            
            # 确保不覆盖已存在的文件
            counter = 1
            original_trash_file_path = trash_file_path
            while trash_file_path.exists():
                trash_file_name = f"{trash_id}_{counter}_{source_path.name}"
                trash_file_path = self._trash_path / trash_file_name
                counter += 1
            
            try:
                # 确保回收站目录存在
                self._trash_path.mkdir(parents=True, exist_ok=True)
                
                # 移动文件到回收站
                shutil.move(str(source_path), str(trash_file_path))
                
                # 创建回收站项目记录
                trash_item = TrashItem(
                    trash_id=trash_id,
                    original_path=str(source_path),
                    trash_path=str(trash_file_path),
                    deleted_at=datetime.now().isoformat(),
                    expires_at=self._calculate_expires_at(),
                    file_size=self._get_file_size(trash_file_path),
                    deleted_by=deleted_by
                )
                
                # 添加到索引
                self._index[trash_id] = trash_item
                self._save_index()
                
                self._logger.info(
                    f"文件已移入回收站: {source_path} -> {trash_file_path} "
                    f"(ID: {trash_id}, 操作者: {deleted_by or 'unknown'})"
                )
                
                return trash_id
                
            except OSError as e:
                self._logger.error(f"移动文件到回收站失败: {e}")
                raise TrashError(f"无法将文件移入回收站: {e}")
    
    def restore_from_trash(self, trash_id: str) -> bool:
        """从回收站恢复文件到原始位置
        
        Args:
            trash_id: 回收站项目ID
            
        Returns:
            恢复成功返回True，失败返回False
            
        Raises:
            TrashItemNotFoundError: 项目不存在
            TrashItemExpiredError: 项目已过期（文件可能已被清理）
            TrashRestoreError: 恢复过程中发生错误
        """
        with self._lock:
            # 查找项目
            if trash_id not in self._index:
                raise TrashItemNotFoundError(f"回收站项目不存在: {trash_id}")
            
            trash_item = self._index[trash_id]
            
            # 检查是否过期
            if trash_item.is_expired():
                raise TrashItemExpiredError(f"回收站项目已过期: {trash_id}")
            
            trash_file_path = Path(trash_item.trash_path)
            original_path = Path(trash_item.original_path)
            
            # 检查回收站中的文件是否存在
            if not trash_file_path.exists():
                raise TrashRestoreError(f"回收站中的文件不存在: {trash_file_path}")
            
            try:
                # 确保原始目录存在
                original_path.parent.mkdir(parents=True, exist_ok=True)
                
                # 如果原始位置已有文件，生成新文件名
                restore_path = original_path
                counter = 1
                while restore_path.exists():
                    stem = original_path.stem
                    suffix = original_path.suffix
                    restore_path = original_path.parent / f"{stem}_restored_{counter}{suffix}"
                    counter += 1
                
                # 移动文件回原始位置
                shutil.move(str(trash_file_path), str(restore_path))
                
                # 从索引中移除
                del self._index[trash_id]
                self._save_index()
                
                self._logger.info(
                    f"文件已恢复: {trash_file_path} -> {restore_path} (ID: {trash_id})"
                )
                
                return True
                
            except OSError as e:
                self._logger.error(f"恢复文件失败: {e}")
                raise TrashRestoreError(f"无法恢复文件: {e}")
    
    def cleanup_expired(self) -> List[str]:
        """清理过期文件
        
        Returns:
            被删除的trash_id列表
        """
        with self._lock:
            expired_ids: List[str] = []
            
            for trash_id, trash_item in list(self._index.items()):
                if trash_item.is_expired():
                    try:
                        trash_file_path = Path(trash_item.trash_path)
                        
                        # 删除文件
                        if trash_file_path.exists():
                            trash_file_path.unlink()
                            self._logger.debug(f"已删除过期文件: {trash_file_path}")
                        
                        # 从索引中移除
                        del self._index[trash_id]
                        expired_ids.append(trash_id)
                        
                    except OSError as e:
                        self._logger.error(f"删除过期文件失败 {trash_id}: {e}")
            
            if expired_ids:
                self._save_index()
                self._logger.info(f"已清理 {len(expired_ids)} 个过期项目")
            
            return expired_ids
    
    def get_trash_items(self) -> List[TrashItem]:
        """获取回收站中的所有项目
        
        Returns:
            TrashItem列表（按删除时间倒序排列）
        """
        with self._lock:
            items = list(self._index.values())
            # 按删除时间倒序排列
            items.sort(key=lambda x: x.deleted_at, reverse=True)
            return items
    
    def get_trash_item(self, trash_id: str) -> Optional[TrashItem]:
        """获取指定的回收站项目
        
        Args:
            trash_id: 回收站项目ID
            
        Returns:
            TrashItem实例，如果不存在则返回None
        """
        with self._lock:
            return self._index.get(trash_id)
    
    def permanent_delete(self, trash_id: str) -> bool:
        """从回收站永久删除文件
        
        Args:
            trash_id: 回收站项目ID
            
        Returns:
            删除成功返回True，失败返回False
            
        Raises:
            TrashItemNotFoundError: 项目不存在
        """
        with self._lock:
            if trash_id not in self._index:
                raise TrashItemNotFoundError(f"回收站项目不存在: {trash_id}")
            
            trash_item = self._index[trash_id]
            trash_file_path = Path(trash_item.trash_path)
            
            try:
                # 删除文件
                if trash_file_path.exists():
                    trash_file_path.unlink()
                
                # 从索引中移除
                del self._index[trash_id]
                self._save_index()
                
                self._logger.info(f"文件已永久删除: {trash_file_path} (ID: {trash_id})")
                
                return True
                
            except OSError as e:
                self._logger.error(f"永久删除文件失败: {e}")
                return False
    
    def get_stats(self) -> Dict[str, Any]:
        """获取回收站统计信息
        
        Returns:
            包含统计信息的字典
        """
        with self._lock:
            items = list(self._index.values())
            total_size = sum(item.file_size for item in items)
            expired_count = sum(1 for item in items if item.is_expired())
            
            return {
                'trash_path': str(self._trash_path),
                'retention_days': self._retention_days,
                'total_items': len(items),
                'expired_items': expired_count,
                'total_size_bytes': total_size,
                'total_size_mb': round(total_size / (1024 * 1024), 2),
                'auto_cleanup_enabled': self._auto_cleanup_interval is not None,
                'auto_cleanup_interval': self._auto_cleanup_interval
            }
    
    def clear_all(self) -> int:
        """清空回收站（谨慎使用）
        
        Returns:
            被删除的项目数量
        """
        with self._lock:
            deleted_count = 0
            
            for trash_id, trash_item in list(self._index.items()):
                try:
                    trash_file_path = Path(trash_item.trash_path)
                    
                    if trash_file_path.exists():
                        trash_file_path.unlink()
                    
                    del self._index[trash_id]
                    deleted_count += 1
                    
                except OSError as e:
                    self._logger.error(f"删除文件失败 {trash_id}: {e}")
            
            if deleted_count > 0:
                self._save_index()
            
            self._logger.warning(f"回收站已清空，删除了 {deleted_count} 个项目")
            
            return deleted_count


# 便捷函数
def create_trash_manager(
    trash_path: str = '.trash',
    retention_days: int = 7,
    auto_cleanup_interval: Optional[int] = None,
    log_path: Optional[str] = None
) -> TrashManager:
    """创建回收站管理器的便捷函数
    
    Args:
        trash_path: 回收站目录路径
        retention_days: 文件保留天数
        auto_cleanup_interval: 自动清理间隔（秒）
        log_path: 日志文件路径（可选）
        
    Returns:
        TrashManager实例
    """
    logger = None
    if log_path:
        logger = logging.getLogger('file_trash_manager')
        logger.handlers = []  # 清除现有处理器
        handler = logging.FileHandler(log_path, encoding='utf-8')
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
    
    return TrashManager(
        trash_path=trash_path,
        retention_days=retention_days,
        auto_cleanup_interval=auto_cleanup_interval,
        logger=logger
    )


# 示例用法
if __name__ == "__main__":
    import tempfile
    
    # 配置日志
    logging.basicConfig(level=logging.INFO)
    
    # 创建临时目录用于测试
    temp_dir = tempfile.mkdtemp()
    trash_dir = os.path.join(temp_dir, 'trash')
    
    try:
        # 创建回收站管理器
        manager = create_trash_manager(
            trash_path=trash_dir,
            retention_days=7
        )
        
        # 创建测试文件
        test_file = os.path.join(temp_dir, 'test_file.txt')
        with open(test_file, 'w') as f:
            f.write("This is a test file for trash manager.")
        
        print(f"创建测试文件: {test_file}")
        print(f"文件存在: {os.path.exists(test_file)}")
        
        # 移入回收站
        trash_id = manager.move_to_trash(test_file, deleted_by="admin")
        print(f"\n文件已移入回收站，ID: {trash_id}")
        print(f"原文件存在: {os.path.exists(test_file)}")
        
        # 查看回收站项目
        item = manager.get_trash_item(trash_id)
        print(f"\n回收站项目信息:")
        print(f"  - 原始路径: {item.original_path}")
        print(f"  - 回收站路径: {item.trash_path}")
        print(f"  - 删除时间: {item.deleted_at}")
        print(f"  - 过期时间: {item.expires_at}")
        print(f"  - 文件大小: {item.file_size} bytes")
        print(f"  - 删除者: {item.deleted_by}")
        
        # 查看统计信息
        stats = manager.get_stats()
        print(f"\n回收站统计:")
        for key, value in stats.items():
            print(f"  - {key}: {value}")
        
        # 获取所有项目
        items = manager.get_trash_items()
        print(f"\n回收站中的所有项目 ({len(items)} 个):")
        for item in items:
            print(f"  - {item.trash_id}: {os.path.basename(item.original_path)}")
        
        # 恢复文件
        restored = manager.restore_from_trash(trash_id)
        print(f"\n文件恢复结果: {restored}")
        print(f"原文件存在: {os.path.exists(test_file)}")
        
        # 再次移入回收站并永久删除
        trash_id = manager.move_to_trash(test_file, deleted_by="admin")
        print(f"\n再次移入回收站，ID: {trash_id}")
        
        deleted = manager.permanent_delete(trash_id)
        print(f"永久删除结果: {deleted}")
        
        # 最终统计
        stats = manager.get_stats()
        print(f"\n最终回收站统计:")
        print(f"  - 总项目数: {stats['total_items']}")
        
    finally:
        # 清理临时目录
        import shutil
        shutil.rmtree(temp_dir, ignore_errors=True)
        print(f"\n清理临时目录: {temp_dir}")
