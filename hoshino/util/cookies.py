"""Persistent named cookie storage."""

import asyncio
from time import time

from sqlalchemy import Float, Text, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from hoshino import db_dir


class Base(DeclarativeBase):
    pass


class Cookies(Base):
    __tablename__ = "cookies"

    name: Mapped[str] = mapped_column(Text, primary_key=True)
    cookie: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[float] = mapped_column(Float, nullable=False)


db_dir.mkdir(parents=True, exist_ok=True)
db_path = db_dir / "cookies.db"
engine = create_engine(f"sqlite:///{db_path}", echo=False, future=True)
Session = sessionmaker(bind=engine, expire_on_commit=False)

if not db_path.exists():
    Base.metadata.create_all(engine)

cookiejar: dict[str, str] = {}
_cookies_lock = asyncio.Lock()


async def save_cookies(name: str, cookies: str | dict) -> None:
    if isinstance(cookies, dict):
        cookies = "; ".join(f"{key}={value}" for key, value in cookies.items())
    cookiejar[name] = cookies
    async with _cookies_lock:
        with Session() as session:
            obj: Cookies | None = session.get(Cookies, name)
            if obj:
                obj.cookie = cookies
                obj.created_at = time()
            else:
                session.add(Cookies(name=name, cookie=cookies, created_at=time()))
            session.commit()


async def delete_cookies(name: str) -> str | None:
    result = cookiejar.pop(name, None)
    async with _cookies_lock:
        with Session() as session:
            obj: Cookies | None = session.get(Cookies, name)
            if obj:
                session.delete(obj)
                session.commit()
    return result


def check_cookies(name: str) -> bool:
    with Session() as session:
        row = session.execute(
            select(Cookies).where(Cookies.name == name)
        ).scalar_one_or_none()
        if not row or not row.created_at or time() - row.created_at > 86400 * 7:
            return False
        cookiejar[name] = row.cookie
        return True


def check_all_cookies() -> dict[str, bool]:
    result = {}
    with Session() as session:
        rows = session.execute(select(Cookies)).scalars().all()
        for row in rows:
            if not row.created_at or time() - row.created_at > 86400 * 7:
                session.delete(row)
                result[row.name] = False
                cookiejar.pop(row.name, None)
            else:
                result[row.name] = True
                cookiejar[row.name] = row.cookie
        session.commit()
    return result


def _parse_cookie_string(cookies: str) -> dict[str, str]:
    return dict(item.split("=", 1) for item in cookies.split("; "))


async def get_cookies_with_ts(name: str) -> tuple[dict[str, str], float]:
    try:
        if name in cookiejar:
            cookies = cookiejar[name]
            with Session() as session:
                row = session.get(Cookies, name)
                timestamp = row.created_at if row else 0
        else:
            with Session() as session:
                row = session.get(Cookies, name)
                if not row:
                    return {}, 0
                cookies = row.cookie
                timestamp = row.created_at
        return (_parse_cookie_string(cookies), timestamp) if cookies else ({}, 0)
    except (AttributeError, ValueError):
        return {}, 0


async def get_cookies(name: str) -> dict[str, str]:
    try:
        if name in cookiejar:
            cookies = cookiejar[name]
        else:
            with Session() as session:
                row = session.get(Cookies, name)
                if not row:
                    return {}
                if time() - row.created_at > 86400 * 7:
                    session.delete(row)
                    session.commit()
                    return {}
                cookies = row.cookie
                cookiejar[name] = cookies
        return _parse_cookie_string(cookies) if cookies else {}
    except (AttributeError, ValueError):
        return {}


__all__ = [
    "check_all_cookies",
    "check_cookies",
    "delete_cookies",
    "get_cookies",
    "get_cookies_with_ts",
    "save_cookies",
]
