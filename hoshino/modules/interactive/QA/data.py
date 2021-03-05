'''
Author: AkiraXie
Date: 2021-02-03 00:10:02
LastEditors: AkiraXie
LastEditTime: 2021-03-05 13:55:14
Description: 
Github: http://github.com/AkiraXie/
'''
import peewee as pw
from hoshino import db_dir
import os
db_path = os.path.join(db_dir, 'QA.db')
db = pw.SqliteDatabase(db_path)


class Question(pw.Model):
    question = pw.TextField()
    answer = pw.TextField()
    group = pw.BigIntegerField()
    user = pw.BigIntegerField(default=0)

    class Meta:
        database = db
        primary_key = pw.CompositeKey('question', 'group', 'user')


if not os.path.exists(db_path):
    db.connect()
    db.create_tables([Question])
    db.close()
