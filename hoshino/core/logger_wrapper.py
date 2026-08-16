from nonebot import logger


class LoggerWrapper:
    def __init__(self, name: str) -> None:
        self.name = name

    def exception(self, message: str, exception: bool = False, color: bool = True):
        # loguru 的 .exception() 会强制附加 traceback；非 except 上下文会输出
        # "NoneType: None" 噪音，因此默认走 .error()，需要 traceback 时显式传 True。
        text = f"<r><ly>{self.name}</> | {message}</>"
        if exception:
            return logger.opt(colors=color, exception=True).exception(text)
        return logger.opt(colors=color).error(text)

    def error(self, message: str, exception: bool = False, color: bool = True):
        return logger.opt(colors=color, exception=exception).error(
            f"<r><ly>{self.name}</> | {message}</>"
        )

    def critical(self, message: str):
        return logger.opt(colors=True).critical(f"<ly>{self.name}</> | {message}")

    def warning(self, message: str):
        return logger.opt(colors=True).warning(f"<ly>{self.name}</> | {message}")

    def success(self, message: str):
        return logger.opt(colors=True).success(f"<ly>{self.name}</> | {message}")

    def info(self, message: str):
        return logger.opt(colors=True).info(f"<ly>{self.name}</> | {message}")

    def debug(self, message: str):
        return logger.opt(colors=True).debug(f"<ly>{self.name}</> | {message}")
