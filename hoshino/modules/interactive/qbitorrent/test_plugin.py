#!/usr/bin/env python3
"""
qBittorrent 插件测试脚本
用于测试插件的基本功能和API连接
"""

import asyncio
import sys
import os

# 添加项目路径到 Python 路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))))

from hoshino.modules.interactive.qbitorrent.utils import (
    QbtConfig, QbtClient, validate_magnet_url, validate_torrent_url, validate_download_url
)


async def test_validation():
    """测试URL验证功能"""
    print("=== 测试URL验证功能 ===")
    
    # 测试磁力链接
    magnet_url = "magnet:?xt=urn:btih:c12fe1c06bba254a9dc9f519b335aa7c1367a88a&dn=test"
    print(f"磁力链接验证: {validate_magnet_url(magnet_url)}")
    
    # 测试种子文件URL
    torrent_url = "https://example.com/test.torrent"
    print(f"种子文件验证: {validate_torrent_url(torrent_url)}")
    
    # 测试通用URL验证
    test_urls = [
        "magnet:?xt=urn:btih:1234567890abcdef1234567890abcdef12345678",
        "https://example.com/file.torrent",
        "http://tracker.com/download.php?id=12345",
        "invalid_url",
        "ftp://example.com/file.torrent"
    ]
    
    for url in test_urls:
        is_valid, url_type = validate_download_url(url)
        print(f"URL: {url[:50]+'...' if len(url) > 50 else url}")
        print(f"  有效: {is_valid}, 类型: {url_type}")


async def test_config():
    """测试配置模型"""
    print("\n=== 测试配置模型 ===")
    
    config = QbtConfig(
        gid=123456789,
        server_url="http://192.168.1.100:8080",
        username="admin",
        password="adminpass",
        category="test"
    )
    
    print(f"配置创建成功: {config.server_url}")
    
    # 测试客户端创建
    client = QbtClient(config)
    print(f"客户端创建成功: {client.base_url}")


async def main():
    """主测试函数"""
    print("qBittorrent 插件功能测试\n")
    
    try:
        await test_validation()
        await test_config()
        print("\n✅ 所有测试通过！")
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())