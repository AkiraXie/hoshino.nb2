import peewee as pw
import os
from hoshino import db_dir


db_path = os.path.join(db_dir, "black.db")
db = pw.SqliteDatabase(db_path)


class black(pw.Model):
    uid = pw.BigIntegerField()
    due_time = pw.DateTimeField()

    class Meta:
        database = db
        primary_key = pw.CompositeKey("uid", "due_time")


if not os.path.exists(db_path):
    db.connect()
    db.create_tables([black])
    db.close()
