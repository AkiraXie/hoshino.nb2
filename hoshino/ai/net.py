"""AI 网络防护 helper（SSRF）：与 tools 包解耦，避免 media↔tools 循环。"""

from __future__ import annotations

import asyncio
import ipaddress
import socket


async def is_private_host(host: str) -> bool:
    """解析 host 是否指向私有/回环/保留地址；解析失败按私有处理（拒绝）。

    DNS 解析（``socket.getaddrinfo``）是阻塞调用，放线程池执行，避免卡住事件循环。
    """
    try:
        infos = await asyncio.to_thread(socket.getaddrinfo, host, None)
        ip = infos[0][4][0] if infos else None
    except OSError:
        return True
    if ip is None:
        return True
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return True
    return (
        addr.is_private
        or addr.is_loopback
        or addr.is_link_local
        or addr.is_reserved
        or addr.is_multicast
    )
