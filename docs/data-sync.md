# 可配置数据同步

管理中心的数据同步保留计划、排队、互斥领取、租约、进度事件和运行历史。默认 `DATA_SYNC_TASKS={}`，无预置业务接口或任务。任务由受控部署配置定义，凭证仅从环境变量读取。

示例（环境变量 DATA_SYNC_TASKS 的 JSON 值）：

```json
{
  "catalog": {
    "name": "产品目录",
    "base_url": "https://source.example.com/products",
    "target_table": "public.products",
    "database_url_env": "DATA_SYNC_DATABASE_URL",
    "headers_env": "CATALOG_HEADERS",
    "method": "GET",
    "records_path": "data.items",
    "page_param": "page",
    "page_size_param": "page_size",
    "page_size": 5000,
    "min_rows": 1
  }
}
```

`DATA_SYNC_DATABASE_URL` 使用 PostgreSQL psycopg2 URL。`CATALOG_HEADERS` 是请求头 JSON（例如 Authorization），不写入任务列表、状态或日志。DATA_SYNC_TASKS 中的任务 ID 为 1–16 位字母/数字/下划线/短横线；没有硬编码的源地址、数据表或接口编号。

支持 GET 查询参数或 POST JSON 的页码分页，从第 1 页开始；`request_params` 可提供其他参数。默认 records_path=data，空字符串表示顶层数组；点号路径可读取嵌套对象。响应记录必须为对象数组，短页结束，不使用上游 totalCount 推断完成。max_pages 防止无穷分页。默认串行，可配置 max_workers。

目标表必须预先存在。记录先按 column_case（lower 或 none）处理列名，完成字段和类型校验后写 TSV 暂存，通过最小行数门禁才 COPY 到 stage，最终在事务内通过 DELETE + INSERT 替换正式表，并设置 5 秒锁等待上限。MVCC 读取可继续读取旧的已提交快照；不会在整个复制阶段持有 TRUNCATE 的排他锁。没有业务日期或组织过滤，源数据按配置原样同步。失败不替换正式表；成功清理本次分片，失败分片留待排查。

Cron、时区和启停可在页面修改。新任务计划默认关闭。一个任务同一时刻只允许一个活动运行；目标表另有 PostgreSQL 会话 advisory lock 防止多个任务并发替换同表。租约过期标记中断，不自动重发。任务从配置移除时关闭其计划并保留历史。

后台同步源的有限 HTTP 重试与问答模型调用分开配置。未提供凭证或记录路径错误会停止同步，不落回其他数据源。多实例需要共享目标库与分片持久存储。
