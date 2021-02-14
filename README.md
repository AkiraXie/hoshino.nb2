# hoshino.nb2

**这是Ice-cirno的HoshinoBot迁移至nonebot2平台的实验性作品，为本人学习练手所写，会有很多不符合生产规范的，也不够优雅的代码，请海涵。**



## 项目笔记

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

