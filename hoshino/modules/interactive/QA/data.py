from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker
from sqlalchemy.types import Text, Integer
from hoshino import db_dir

db_path = db_dir / "QA.db"
engine = create_engine(f"sqlite:///{db_path}", echo=False, future=True)
Session = sessionmaker(bind=engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


class Question(Base):
    __tablename__ = "question"
    question: Mapped[str] = mapped_column(Text, primary_key=True)
    answer: Mapped[str] = mapped_column(Text, nullable=False)
    group: Mapped[int] = mapped_column(Integer, primary_key=True)
    user: Mapped[int] = mapped_column(Integer, primary_key=True, default=0)


# 初始化数据库
if not db_path.exists():
    Base.metadata.create_all(engine)
