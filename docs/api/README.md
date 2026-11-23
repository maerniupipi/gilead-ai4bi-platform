# 平台服务接口

所有服务请求由服务端持有 Bearer Key：`Authorization: Bearer <key>`。管理中心配置 Key、运行工作流及固定发布版本。调用方提交 `user` 作为不透明用户标识（1–320 字符），无需员工目录或特定邮箱/工号格式。不要把服务 Key 发送给终端浏览器。

## 接口

| 方法 | 路径 | 用途 |
|---|---|---|
| GET | `/api/service/info` | 检查 Key 并取得服务信息 |
| POST | `/api/service/chat-messages` | 启动流式问答 |
| POST | `/api/service/chat-messages/{task_id}/stop` | 停止本用户任务 |
| POST | `/api/service/exports/ppt` | 导出会话 PPT（完整总结、AI 总结或双文件） |
| POST | `/api/service/exports/xlsx` | 按 message_id 与 data_ref 导出完整表格 |
| GET | `/api/service/export-tasks/{task_id}` | 查询文件生成状态 |
| GET | `/api/service/files/{file_id}/download-url` | 获取有时限的签名下载地址 |

GET 任务/文件接口通过查询参数提交 `user`；POST 通过 JSON 提交。文件内容地址由服务签名生成，不需要再附加服务 Key。

```json
{
  "user": "analyst-001",
  "query": "分析本月数据",
  "inputs": {"business_month": "2026-11"},
  "conversation_id": null,
  "response_mode": "streaming"
}
```

首轮 `conversation_id` 为空，续轮使用服务返回的 UUID。SSE 包含 workflow_started、node_started、node_finished、message、workflow_finished 等事件；完整表格保存在平台，预览最多 50 行。history_question 为本会话最近 5 个成功历史问题，并自动传给嵌套工作流与实验室。

`user`、`user_id`、features、会话历史、当前问题别名与运行目标为保留字段，不能经 inputs 覆盖。工作流通过显式输入映射和业务参数传递任意客户扩展值，不查询外部组织目录。

导出 PPT JSON：`user`、`conversation_id`、`summaryType`（ALL/FULL_SUMMARY/AI_SUMMARY），可附 message_ids、idempotency_key。XLSX JSON：`user`、`conversation_id`、`message_id`、`data_ref`，可附 idempotency_key。完整结果、会话归属、任务过期和签名均在服务端校验。AI 总结需先在多模态配置选择模型。

平台管理接口保留 `/api/chatbi/keys`、`/api/chatbi/conversations`、`/api/chatbi/ppt-model` 等，使用平台原有登录身份和 `{code,message,data}` 响应。服务接口返回独立资源 JSON，错误为 `{status,code,message}`。

OpenAPI 和结果 JSON Schema 由 `backend/scripts/export_chatbi_contract.py --output-dir ../docs/api` 生成，属于当前通用服务的接口定义。

对话管理的 keyword 支持完整实验室、根工作流或子工作流 TraceID，可叠加 Key、用户和时间条件。匹配任意轮次时会话只返回一次；未关联服务会话的独立效果测试不会生成会话记录。
