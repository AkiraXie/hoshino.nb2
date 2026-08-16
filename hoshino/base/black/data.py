import os
from datetime import datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker
from sqlalchemy.types import BigInteger, DateTime

from hoshino import db_dir
from hoshino.core.hooks import on_serial_startup

db_path = os.path.join(db_dir, "black.db")
engine = create_engine(f"sqlite:///{db_path}", echo=False, future=True)
Session = sessionmaker(bind=engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


class BlackRecord(Base):
    __tablename__ = "black"
    uid: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    due_time: Mapped["datetime"] = mapped_column(DateTime, primary_key=True)


@on_serial_startup
async def _init_db() -> None:
    """启动串行阶段建表，避免在 import 期执行 DDL。"""
    db_dir.mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(engine)
