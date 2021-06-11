# hoshino.nb2

**这是Ice-cirno的HoshinoBot迁移至nonebot2平台的实验性作品，为本人学习练手所写，会有很多不符合生产规范的，也不够优雅的代码，请海涵。**

## 怎么用？
1. 装依赖
2. 复制service_config_sample到service_config, 然后自己改配置
3. python run.py



## 项目笔记
2021/2/22凌晨 从nb2学到了可以让`Service`信息用`loguru`记录的方式，于是对日志进行了封装,并让`Service.logger`得以实现。

同时，实现了对`nonebot.matcher`的封装，并命名为`MatcherWrapper`，`MatcherWrapper`联系了`matcher`和`Service`，记录了`matcher`的更为丰富的信息，而且终于`MatcherWrapper`成为了具体实例对象，梦寐以求的`matcher`**直接装饰函数**得以变相实现(等同于`handle()`)，梦回nb1, 撒花~。

利用nb2的`run_preprocessor`和`run_postprocessor`，结合`MatcherWrapper`, 使日志记录更多事件处理的信息。

这次更新之后，项目的核心架构真正稳定下来(但愿如此)。~~我真的不想折腾了。~~



2021/2/20凌晨 这几天项目进程依然缓慢进行，当然目前大体迁移完毕后已经投入生产使用了。使用过程中发现，对于定时任务的管理或许是可以提上日程的，于是一方面地，学习了APScheduler的[官方文档](https://apscheduler.readthedocs.io/en/latest/userguide.html#), 了解到了scheduler的属性和方法。然后查看本地源码时候傻眼了，它源代码没写类型标注，job不能直接定位到job的定义，scheduler也差不多（此时就感慨之前大佬们嘱托的写好类型标注的重要性，给自己给他人都有很大的方便），学完之后就知道了怎么修改任务的状态和查看任务的属性。

另一方面，我想着将定时任务的运行状态记录下来，所以学习了loguru的[官方文档](https://loguru.readthedocs.io/en/stable/index.html)，了解到了对于颜色的处理，然后就需要对定时任务装饰的函数进行一些处理，在运行前后进行日志的记录。

好吧这就又牵扯到了python的[`装饰器`](https://docs.python.org/zh-cn/3/glossary.html#term-decorator)的问题, 阅读了文档之后感觉还不够，就又去[菜鸟教程](https://www.runoob.com/w3cnote/python-func-decorators.html)复习了装饰器的用法。熟悉之后大概知道了装饰器的含义：`装饰器`是一个**参数是函数，返回值是传入的函数**函数，它的目的就是对于传入的函数进行处理和装饰(装饰器的名字终于理解了)，比较简单的例子就是`staticmethod`和`classmethod`。

由于`@`语法糖装饰函数的时候，参数只有函数对象一个，函数本身的参数并未传入`装饰器`，这造成了如果需要函数正常运行，它会缺少参数，于是聪明的人们想到了一个办法，在`装饰器`内部再设立一个函数，让它与要装饰的函数的参数相同，这样相当于把函数包装成了另一个函数（往往称之为`闭包`），`闭包`会接受到装饰器对函数的装饰效果，装饰器再返回闭包对象就好，当然直接进行闭包会有一些问题，比如函数的__name__会有所改变，参数和函数的参数不一定一致等，所以一般会引用`wraps`来装饰闭包和对闭包进行参数检查：

```python
from functools import wraps
def deco(func):
    @wraps(func)
    def wrapper(*args,**kwargs):
        print('before func')
        res=func(*args,**kwargs)
        print('after func')
        return res
    return wrapper
@deco
def fun(*args,**kwargs):
    print(args)
    print(kwargs)
```

但是有时候`装饰器`需要函数以外的参数来对函数进行处理（比如说，用鉴权参数来检测是否能让函数运行），要怎么办呢？聪明的人们又想到了一个方法，写一个外层函数传递参数，然后让内层的`装饰器`接收到这些参数,  再返回`装饰器`不就好了! 这样的场景很广泛，例子非常多，比如`flask`或者`fastapi`的`app.get`方法就是这样的，对于nb2来说，`matcher.handle`或者`matcher.got`也是这样，对于前面说的`apscheduler`的`scheduler.scheduled_job`也是如此。所以，绝大多数我之前认为的`装饰器`都不是`装饰器`本身，而是返回`装饰器`的函数。

一般见到的装饰器函数有两个情况：大多数都有三层函数的结构，第一层接受`装饰器`需要的参数,第二层是接受函数的`装饰器`;第三层是接受函数的参数，打包函数的`闭包`；当然也有很多就两层结构，第一层接受装饰器的参数,第二层是接受函数的`装饰器`，这个`装饰器`往往只对函数对象**本身**操作。这里拿第一种情况举例：

```python
def return_deco(ab: bool):
    def deco(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            print('before func')
            if ab:
                res = func(*args, **kwargs)
            else:
                print('鉴权不通过，函数不执行')
                res = None
            print('after func')
            return res
        return wrapper
    return deco


@return_deco(True)
def fun(*args, **kwargs):
    print(args)
    print(kwargs)


@return_deco(False)
def fun1(*args, **kwargs):
    print(args)
    print(kwargs)


fun('1234', name='jim')
fun1('1234', name='jim')
```

上面的代码运行之后，会有以下的记录，`装饰器`的参数确实对函数运行造成了影响：

```
before func
('1234',)
{'name': 'jim'}
after func
before func
鉴权不通过，函数不执行
after func
```

~~好吧其实写完这篇笔记之后我大概对装饰器的理解应该比较深的了~~

2021/2/15凌晨 在这段期间，项目进展算是很缓慢的，但是也学习并实践了一些nb2的feature:

1.  对于原先`HoshinoBot`的`anti_abuse`插件， 在这个项目重构为[`black`](hoshino/base/black/__init__.py)，并利用了nb2的钩子函数(新学到的名词)`event_preprocessor`进行处理。

    这个插件的编写让我仔细阅读了nb2的[message.py](https://github.com/nonebot/nonebot2/blob/0428b1dd81263e474d7e18e36745d5bb9d572d14/nonebot/message.py),  并理解了nb2处理事件的周期：

    `上报(以及根据adapter剥离事件的tome)`->`事件预处理`->`匹配响应器`->`运行前处理`->`运行响应器`->`运行后处理`->`事件后处理`

2.  在编写[`poke`](hoshino/modules/interactive/poke.py)的时候，学习到了nb2的`事件处理函数重载`，这个feature会运用魔法，可以让matcher运行的时候按`handler`规定的`typing`来执行`handler`,这个feature能减少rule的编写，可以让一个响应器针对不同的事件作响应。

    这个魔法的源代码在[run_handler](https://github.com/nonebot/nonebot2/blob/0428b1dd81263e474d7e18e36745d5bb9d572d14/nonebot/matcher.py#L458), 粗略来说，它会根据参数名字和参数类型进行检查，如果参数名字和类型对得上的话，才会运行`handler`，否则就会`ignore`。

    当然，这个检查是在`handler`对象有一个`__params__`这样一个类似注释的存在前提下进行的，这个前提的是由[process_handler](https://github.com/nonebot/nonebot2/blob/0428b1dd81263e474d7e18e36745d5bb9d572d14/nonebot/matcher.py#L246)制造的，查看这个代码段时候，大概查看了[`inspect`](https://docs.python.org/zh-cn/3.9/library/inspect.html)模块，学习到了python对于类型检查的处理。


在迁移了[`rsspush`](hoshino\modules\information\rsspush\__init__.py)时，想着能不能将图片输出出来，这个思考直接导致了对网络请求的封装的修改，才注意到对于返回的请求体，一定是有`content`这样一个`bytes`，但是这个`bytes`并不一定能解码为`text`或者`json`，比如图片和文件。



2021/2/03下午 新增`interactive`模块，之后会存放互动的插件；在其中增加机器人最重要的自定义问答功能`QA`；`下载卡面` `下载头像`使用了`nonebot.util.run_sync`功能，将同步函数装饰异步;引用`nonebot2.00a9`的新特性`on_shell_command`。



2021/2/01凌晨  昨天的问题今天下午查阅nb2的[issue#153](https://github.com/nonebot/nonebot2/issues/153)得到了解决，跨插件访问不建议直接引用，可以利用`require()`和`export()`办法来处理，于是就将`chara.Chara`进行导出。

另外，今天新增了`pcr_arena`和`whois`插件，`pcr_arena`的编写让我大概明白了`Matcher`处理事件的流程，于是就试着用了`Matcher.new(state=...,handlers=...)`的办法来初始化响应器，这样省去了大量的重复代码。

`whois`插件的编写让我发现了nb2的一个小[bug](https://github.com/nonebot/nonebot2/issues/180),即在[`_check_matcher()`阶段](https://github.com/nonebot/nonebot2/blob/0428b1dd81263e474d7e18e36745d5bb9d572d14/nonebot/message.py#L102)，如果在[`Rule`处理了`state`](https://github.com/nonebot/nonebot2/blob/0428b1dd81263e474d7e18e36745d5bb9d572d14/nonebot/rule.py#L279)，前一个响应器的`state`被后一个覆盖的情况。目前的权宜之计就是不满足checker时候[直接返回`False`](hoshino/rule.py#L48)，具体的妥善办法就等更新了。

还有就是，用一个笨方法将异步请求给封装了，用[一个类](hoshino/util/aiohttpx.py)来实现类似的`resp.content`操作。

今天之后代码的最核心部分就差不多完成了，之后进行插件的慢慢迁移就可以，这几天写的我有点内耗，现在脑子发昏，读代码和写代码在进行的时候感觉很有干劲，停下来之后就觉得被掏空了；当然最大的原因还是自己基础不够，效率还是太低了。

总之该项目最艰难的阶段结束了，之后就慢慢更新了。



2021/1/31凌晨 新增`gacha`，`chara`，`query`；并遇到一个问题，`gacha`引用`chara`的一个类，但是同时也注册了`chara`的三个`matcher`（通过`nonebot.mathcer.matchers`debug可知，在启动时也会有`WARNING`），可能这是nb2的feature?



2021/1/29晚   重写了原`Hoshinobot`的`R.py`,使之支持更多的表达方式,并写了相关demo。（写代码太累了。。。。）

2021/1/29凌晨 原`HoshinoBot`代码框架核心部分，即`Service`类和控制`Service`的代码已迁移完成。项目启动为时两天，还算顺利（不是）。



## 特别感谢

- [Ice-Cirno / HoshinoBot](https://github.com/Ice-Cirno/HoshinoBot)
- [nonebot / nonebot2](https://github.com/nonebot/nonebot2)
- [Mrs4s / go-cqhttp](https://github.com/Mrs4s/go-cqhttp)

