'''
Author: AkiraXie
Date: 2021-02-05 15:18:30
LastEditors: AkiraXie
LastEditTime: 2021-02-05 16:56:03
Description: 
Github: http://github.com/AkiraXie/
'''
import peewee as pw
import os
from hoshino import db_dir


db_path = os.path.join(db_dir, 'black.db')
db = pw.SqliteDatabase(db_path)


class black(pw.Model):
    uid = pw.BigIntegerField()
    due_time = pw.DateTimeField()

    class Meta:
        database = db
        primary_key = pw.CompositeKey('uid','due_date')


if not os.path.exists(db_path):
    db.connect()
    db.create_tables([black])
    db.close()
