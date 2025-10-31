from nonebot import logger


class LoggerWrapper:
    def __init__(self, name: str) -> None:
        self.name = name

    def exception(self, message: str, exception=True, color=True):
        return logger.opt(colors=color, exception=exception).exception(
            f"<r><ly>{self.name}</> | {message}</>"
        )

    def error(self, message: str, exception=True, color=True):
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
