'''
Author: AkiraXie
Date: 2021-01-29 15:02:48
LastEditors: AkiraXie
LastEditTime: 2021-06-09 02:30:07
Description: 
Github: http://github.com/AkiraXie/
'''
from loguru import logger
from io import UnsupportedOperation
from PIL import Image
import os
from nonebot.adapters.onebot.v11.message import MessageSegment
from hoshino import hsn_config
STATIC = os.path.expanduser(hsn_config.static or 'static')

os.makedirs(STATIC, exist_ok=1)


class RHelper(str):
    '''
    资源访问类，但不推荐利用这个类构建对象，推荐使用`hoshino.R`这个全局常量来进行访问。

    `R`本身是一个字符串，并重载了`.`,`+`,`()`,`/`,`//`运算符,但屏蔽了对字符串本身进行修改的一些操作。

    **请不要对`R`进行赋值操作！**

    并且对图片对象进行了取`CQcode`和`open()`的操作。

    e.g：

    `R.img.priconne`,`R.img('priconne')`,`R+"img"+"priconne"`是等效的 '''

    def __init__(self, path: str = None) -> None:
        if not path:
            self.__rpath = STATIC
        else:
            self.__rpath = path

    def __getattr__(self, key):
        path = os.path.join(self.__rpath, key)
        path = os.path.normpath(path)
        if not os.path.isdir(path) and not os.path.isfile(path):
            logger.warning(
                f'{path} is not a directory and a file!\nif {key}.* or *.{key} is file or dir,please use + or () opearator.')
        return __class__(path)

    def __floordiv__(self, key):
        path = os.path.join(self.__rpath, key)
        path = os.path.normpath(path)
        return __class__(path)

    def __truediv__(self, key):
        path = os.path.join(self.__rpath, key)
        path = os.path.normpath(path)
        return __class__(path)

    def __add__(self, key):
        path = os.path.join(self.__rpath, key)
        path = os.path.normpath(path)
        return __class__(path)

    def __setattr__(self, name: str, value) -> None:
        if name != '_RHelper__rpath':
            raise UnsupportedOperation(
                f'unsupported operand type(s) for =: "RHelper" and "{type(value)}"')
        else:
            self.__dict__[name] = value

    def __imul__(self, key):
        raise UnsupportedOperation(
            f'unsupported operand type(s) for *=: "RHelper" and "{type(key)}"')

    def __mul__(self, key):
        raise UnsupportedOperation(
            f'unsupported operand type(s) for *: "RHelper" and "{type(key)}"')

    def __call__(self, path, *paths):
        key = os.path.join(path, *paths)
        path = os.path.join(self.__rpath, key)
        path = os.path.normpath(path)
        return __class__(path)

    @property
    def path(self) -> str:
        return os.path.abspath(self.__rpath)

    def __str__(self) -> str:
        return self.path

    @property
    def exist(self):
        return os.path.exists(self.path)

    def __bool__(self):
        return self.exist

    def open(self) -> Image.Image:
        try:
            return Image.open(self.__rpath)
        except Exception as e:
            logger.exception(e)

    @property
    def CQcode(self) -> MessageSegment:
        try:
            return MessageSegment.image('file:///'+os.path.abspath(self.__rpath))
        except Exception as e:
            logger.exception(e)
            return MessageSegment.text('[图片出错]')
