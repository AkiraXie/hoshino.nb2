'''
Author: AkiraXie
Date: 2021-01-29 15:02:48
LastEditors: AkiraXie
LastEditTime: 2021-01-29 18:05:33
Description: 
Github: http://github.com/AkiraXie/
'''
from loguru import logger
from io import UnsupportedOperation
from PIL import Image
import os
from nonebot.adapters.cqhttp.message import MessageSegment
from hoshino import hsn_config
STATIC = os.path.expanduser(hsn_config.static or 'data/static')

os.makedirs(STATIC, exist_ok=1)


class rhelper(str):
    '''
    资源访问类，但不推荐利用这个类构建对象，推荐使用`hoshino.R`这个全局常量来进行访问。
    '''
    def __init__(self,path=None) -> None:
        if not path:
            self.rpath=STATIC
        else:
            self.rpath=path
    def __getattr__(self,key):
        path=os.path.join(self.rpath,key)
        path=os.path.normpath(path)
        if not os.path.isdir(path) and not os.path.isfile(path):
            raise FileNotFoundError(f'{path} is not a directory and a file!\nif {key}.* or *.{key} is file or dir,please use + or () opearator.')
        return rhelper(path)
    def __add__(self,key):
        path=os.path.join(self.rpath,key)
        path=os.path.normpath(path)
        if not os.path.isdir(path) and not os.path.isfile(path):
            raise FileNotFoundError(f'{path} is not a directory and a file!')
        return rhelper(path)
    def __iadd__(self,key):
        raise UnsupportedOperation(f'unsupported operand type(s) for +=: "rhelper" and "{type(key)}"')
    def __imul__(self,key):
        raise UnsupportedOperation(f'unsupported operand type(s) for *: "rhelper" and "{type(key)}"')
    def __mul__(self,key):
        raise UnsupportedOperation(f'unsupported operand type(s) for *: "rhelper" and "{type(key)}"')
    def __call__(self, path,*paths) :
        key= os.path.join(path, *paths)
        path=os.path.join(self.rpath,key)
        path=os.path.normpath(path)
        if not os.path.isdir(path) and not os.path.isfile(path):
            raise FileNotFoundError(f'{path} is not a directory and a file!')
        return rhelper(path)
    @property
    def path(self)->str:
        return os.path.normpath(self.rpath)
    def __str__(self) -> str:
        return self.path
    
    def open(self) -> Image.Image:
        return Image.open(self.path)
    @property
    def CQcode(self) -> MessageSegment:
        try:
            return MessageSegment.image('file:///'+os.path.abspath(self.path))
        except Exception as e:
            logger.exception(e)
            return MessageSegment.text('[图片出错]')





        
