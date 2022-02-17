"""
Author: AkiraXie
Date: 2021-01-30 21:55:38
LastEditors: AkiraXie
LastEditTime: 2021-01-31 02:50:06
Description: 
Github: http://github.com/AkiraXie/
"""
import peewee as pw
import os
from hoshino import db_dir


db_path = os.path.join(db_dir, "gacha.db")
db = pw.SqliteDatabase(db_path)


class usercollection(pw.Model):
    id = pw.BigIntegerField()
    chara = pw.IntegerField()

    class Meta:
        database = db
        primary_key = pw.CompositeKey("id", "chara")


class grouppool(pw.Model):
    id = pw.BigIntegerField()
    pool = pw.TextField()

    class Meta:
        database = db
        primary_key = pw.CompositeKey("id")


def get_pool(gid: int) -> str:
    ret, _ = grouppool.get_or_create(id=gid, defaults={"pool": "MIX"})
    return ret.pool


def set_pool(gid: int, pool: str):
    grouppool.replace(id=gid, pool=pool).execute()


def select_collection(uid: int) -> list:
    ret = usercollection.select(usercollection.chara).where(usercollection.id == uid)
    retl = []
    for r in ret:
        retl.append(r.chara)
    return retl


def set_collection(uid: int, chara: int):
    usercollection.replace(id=uid, chara=chara).execute()


if not os.path.exists(db_path):
    db.connect()
    db.create_tables([usercollection, grouppool])
    db.close()
