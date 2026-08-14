"""web 工具共享的网络防护 helper（web_fetch / image_view 复用）。"""

from __future__ import annotations

import ipaddress
import socket


def is_private_host(host: str) -> bool:
    """解析 host 是否指向私有/回环/保留地址；解析失败按私有处理（拒绝）。"""
    try:
        infos = socket.getaddrinfo(host, None)
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
