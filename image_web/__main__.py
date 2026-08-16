"""统一启动入口。

用法::

    uv run python -m image_web x            # 启动 X 站点后端 (默认 9997)
    uv run python -m image_web weibo        # 启动微博站点后端 (默认 9998)
    uv run python -m image_web x --port 9000 --reload
"""

import argparse
import sys

import uvicorn

from .registry import PROVIDERS


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="image_web",
        description="启动指定 provider 的图片浏览站点后端。",
    )
    parser.add_argument(
        "provider",
        nargs="?",
        choices=sorted(PROVIDERS),
        help="要启动的站点 provider",
    )
    # 0.0.0.0 为远程开发约定（AGENTS.md §9），默认对所有网卡监听。
    parser.add_argument("--host", default="0.0.0.0", help="监听地址 (默认 0.0.0.0)")  # noqa: S104
    parser.add_argument("--port", type=int, default=None, help="监听端口 (默认取 provider 默认值)")
    parser.add_argument("--reload", action="store_true", help="开发模式热重载")
    args = parser.parse_args(argv)

    if args.provider is None:
        parser.print_help()
        return 1

    spec = PROVIDERS[args.provider]
    port = args.port if args.port is not None else spec.default_port

    uvicorn.run(f"{spec.module}:app", host=args.host, port=port, reload=args.reload)
    return 0


if __name__ == "__main__":
    sys.exit(main())
