from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker
from sqlalchemy.types import BigInteger, DateTime
import os
from hoshino import db_dir
from datetime import datetime

db_path = os.path.join(db_dir, "black.db")
engine = create_engine(f"sqlite:///{db_path}", echo=False, future=True)
Session = sessionmaker(bind=engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


class black(Base):
    __tablename__ = "black"
    uid: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    due_time: Mapped["datetime"] = mapped_column(DateTime, primary_key=True)


# 初始化数据库
if not os.path.exists(db_path):
    Base.metadata.create_all(engine)
