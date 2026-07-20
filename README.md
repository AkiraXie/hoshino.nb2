# hoshino.nb2

**这是Ice-cirno的HoshinoBot迁移至nonebot2平台的实验性作品，为本人学习练手所写，会有很多不符合生产规范的，也不够优雅的代码，请海涵。**

## 怎么用？
1. 装依赖
2. 复制 service_config_sample 到 service_config, 然后自己改配置
3. 复制 env.prod.example 到 env.example
4. python run.py

项目会同时注册 OneBot V11、Telegram 和 Milky adapter。Telegram token 通过
`telegram_bots=[{"token":"..."}]` 配置；Milky 协议端通过 `milky_clients`
或 `milky_webhook` 配置。平台边界与兼容性见
[`docs/telegram.md`](docs/telegram.md) 和 [`docs/milky.md`](docs/milky.md)。

## 特别感谢

- [Ice-Cirno / HoshinoBot](https://github.com/Ice-Cirno/HoshinoBot)
- [nonebot / nonebot2](https://github.com/nonebot/nonebot2)
- [Mrs4s / go-cqhttp](https://github.com/Mrs4s/go-cqhttp)
