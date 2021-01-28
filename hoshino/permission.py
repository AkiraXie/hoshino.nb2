'''
Author: AkiraXie
Date: 2021-01-28 01:21:39
LastEditors: AkiraXie
LastEditTime: 2021-01-28 20:57:47
Description: 
Github: http://github.com/AkiraXie/
'''
from nonebot.adapters.cqhttp.permission import GROUP, GROUP_ADMIN, GROUP_OWNER
from nonebot.permission import SUPERUSER, Permission
ADMIN = SUPERUSER | GROUP_ADMIN | GROUP_OWNER
OWNER = SUPERUSER | GROUP_OWNER
NORMAL = SUPERUSER | GROUP
