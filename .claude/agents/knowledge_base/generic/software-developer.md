# 开发通用经验（随套件分发，人工维护）

## 改动范围
- 修改既有文件只做最小改动；提交前对比改动前后的函数/方法名集合，确认没有丢逻辑：
  `git diff -- <file> | grep -oE '(function|const|class|def)\s+\w+' | sort -u`
- 改文件用 Edit/Write，不用 shell 脚本批量替换，便于审计与回溯。

## 迁移
- 已上线的迁移不得修改，只能新增；字段重命名用框架的 rename 操作（自动生成器常产出 add+remove，会丢数据）；带索引字段先删索引再加。
- 并行开发易撞迁移编号，合并前核对编号连续、依赖指向最新。

## 后端
- 【适用：SSE / WebSocket 流式接口】出异常时也必须发送结束标记（如 `done:true` + error），否则前端永远"生成中"。
- 【适用：异步任务队列，如 Celery / RQ / Sidekiq】设置软超时并在捕获后把记录置为 error；批量计算显式指定 batch_size 控制内存峰值；`max_retries` 与失败状态写入要配合，避免重试覆盖错误状态。
- 【适用：异步任务队列】任务路由的默认队列名必须与 worker 监听的队列一致，否则任务永远不被消费。
- 【适用：有限流 / 节流中间件的 Web 框架】测试环境要关闭限流类中间件/节流，否则共享缓存跨用例累积导致 429。

## 前端
- 【适用：前端 JWT / refresh token 轮换】Token 刷新必须用单个共享 Promise 做互斥：并发 401 各自刷新会在 refresh token 轮换时把用户踢下线。轮换模式下必须保存新的 refresh token。
- 组件库升级注意 API 变化，按升级后版本的文档写属性（【适用：Vue + Element Plus】例：radio 用 `value` 而非 `label`）。
