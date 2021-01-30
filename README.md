# hoshino.nb2

**这是Ice-cirno的HoshinoBot迁移至nonebot2平台的实验性作品，为本人学习练手所写，会有很多不符合生产规范的，也不够优雅的代码，请海涵。**



## 项目笔记

2021/1/31凌晨 新增`gacha`，`chara`，`query`；并遇到一个问题，`gacha`引用`chara`的一个类，但是同时也注册了`chara`的三个`matcher`（通过`nonebot.mathcer.matchers`debug可知，在启动时也会有`WARNING`），可能这是nb2的feature?

2021/1/29晚   重写了原`Hoshinobot`的`R.py`,使之支持更多的表达方式,并写了相关demo。（写代码太累了。。。。）

2021/1/29凌晨 原`HoshinoBot`代码框架核心部分，即`Service`类和控制`Service`的代码已迁移完成。项目启动为时两天，还算顺利（不是）。



## 特别感谢

- [Ice-Cirno / HoshinoBot](https://github.com/Ice-Cirno/HoshinoBot)
- [nonebot / nonebot2](https://github.com/nonebot/nonebot2)
- [Mrs4s / go-cqhttp](https://github.com/Mrs4s/go-cqhttp)

