#!/usr/bin/env python3
"""
用户数据迁移脚本：将 users.json 迁移到 SQLite 数据库
"""

import os
import json
import sys
from user_database import get_user_db

def migrate_users():
    """从 users.json 迁移用户数据到 SQLite 数据库"""

    base_dir = os.path.dirname(os.path.abspath(__file__))
    users_json_path = os.path.join(base_dir, 'users.json')

    # 检查 JSON 文件是否存在
    if not os.path.exists(users_json_path):
        print(f"错误: 找不到 users.json 文件: {users_json_path}")
        print("请确保 users.json 存在于项目根目录")
        return False

    # 读取 JSON 文件
    try:
        with open(users_json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            users = data.get('users', [])
    except Exception as e:
        print(f"读取 users.json 失败: {e}")
        return False

    if not users:
        print("警告: users.json 中没有用户数据")
        return False

    print(f"从 users.json 读取到 {len(users)} 个用户")

    # 获取数据库实例
    db = get_user_db()

    # 检查是否已有数据
    existing_users = db.load_users()
    if existing_users:
        print(f"警告: 数据库中已有 {len(existing_users)} 个用户")
        response = input("是否继续迁移并覆盖现有数据? (y/N): ")
        if response.lower() != 'y':
            print("迁移已取消")
            return False

    # 执行迁移
    migrated_count = db.migrate_from_json(users)

    if migrated_count > 0:
        print(f"\n迁移成功! 共迁移 {migrated_count} 个用户")

        # 验证迁移结果
        verify_users = db.load_users()
        print(f"数据库中现有 {len(verify_users)} 个用户")

        # 显示用户列表
        print("\n用户列表:")
        for user in verify_users:
            print(f"  - {user['username']} ({user['role']}) - 状态: {user['status']}")

        # 备份原 JSON 文件
        backup_path = users_json_path + '.backup'
        try:
            os.rename(users_json_path, backup_path)
            print(f"\n原文件已备份到: {backup_path}")
        except Exception as e:
            print(f"\n备份原文件失败: {e}")
            print("建议手动备份或删除 users.json")

        return True
    else:
        print("迁移失败，没有用户被迁移")
        return False


def main():
    """主函数"""
    print("=" * 50)
    print("用户数据迁移工具")
    print("从 users.json 迁移到 SQLite 数据库")
    print("=" * 50)
    print()

    success = migrate_users()

    if success:
        print("\n迁移完成! 现在可以使用 SQLite 数据库管理用户了")
        sys.exit(0)
    else:
        print("\n迁移失败或已取消")
        sys.exit(1)


if __name__ == '__main__':
    main()
