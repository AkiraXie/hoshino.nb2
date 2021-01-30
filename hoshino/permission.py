'''
Author: AkiraXie
Date: 2021-01-28 01:21:39
LastEditors: AkiraXie
LastEditTime: 2021-01-31 02:39:55
Description: 
Github: http://github.com/AkiraXie/
'''
from nonebot.adapters.cqhttp.permission import GROUP, GROUP_ADMIN, GROUP_OWNER,PRIVATE
from nonebot.permission import SUPERUSER, Permission
ADMIN = SUPERUSER | GROUP_ADMIN | GROUP_OWNER 
PADMIN =SUPERUSER | GROUP_ADMIN | GROUP_OWNER | PRIVATE
OWNER = SUPERUSER | GROUP_OWNER
POWNER =SUPERUSER | GROUP_ADMIN | GROUP_OWNER | PRIVATE
NORMAL = SUPERUSER | GROUP | PRIVATE
