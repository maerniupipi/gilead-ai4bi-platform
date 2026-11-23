# Implementation progress — docs/batch-runner-plan.md

- 用户批准 docs/batch-runner-design.md，执行方式为当前会话自行实现。
- Pre-flight: workbook 与 runner 使用同一 RowResult；client 向 runner 提供顺序 SSEFrame；API 只通过 service/runner 获取状态。
- Ruling: 上传采用 application/octet-stream 和单独文件名头，避免新增 multipart 依赖；保留原页面上传体验。
- Ruling: 本任务不创建工作树、Git 提交或清理目录，遵循用户边界。
- Ruling: 显式执行新测试模块，避免扫描/读取已有其他测试。
- Ruling: Python 使用 -B，测试输出只保留于 runtime 下随机目录，不自动删除。
- Task 1: complete. 构造数据测试先确认缺失，再实现并通过 11 项核心测试。
- Task 2: complete. 10 项执行测试通过；审查后新增 3 项异常断流与超长恢复回归，先失败再修复。
- Task 3: complete. 5 项服务层直接调用测试通过；前端 5 项纯逻辑测试通过，包含两项乱序响应回归；脚本语法通过。
- Task 4: complete. 2026-10-15 最终验证：29 项 Python 测试、5 项 Node 测试全部通过；两个前端脚本语法、9 个 Python 模块 AST、项目 TOML 与启动 CLI --help 检查通过。
- Verification boundary: 未安装依赖、未启动本地服务、未访问真实或本地接口、未读取真实工作簿、未进行浏览器端到端验收。
- Review: 3 项 P2 已修复：未分帧尾部丢失、恢复后的超限标记、前端筛选响应乱序。
- Review rulings: 不扩大复杂 Excel 对象兼容性、不取消在途远端请求、不新增重试或续跑，均符合已确认设计；多实例共用 runtime 不支持，README 已明确单进程运行。
- Tooling: Node 测试运行器因沙箱不允许创建子进程，经用户批准在沙箱外运行纯离线测试；不启动网络服务。

## 上传进度修复与逐题 XLSX 保存
- 根因：上传与预览数据包含 total，但没有 finished；直接相除产生 NaN，HTMLProgressElement.value 拒绝非有限数值。
- 修复：缺失 finished 视为 0，拒绝非有限统计值，进度钳制在 0 至 100；补充上传、预览、空数据与非有限值回归。
- 行为更新：每个问题结束保存行 JSON 后，立即原子更新 runtime/jobs/<job_id>/result.xlsx；异步写入锁与后台线程防止并发覆盖并减少对流读取的阻塞；运行中可下载已保存工作簿。
- 故障边界：工作簿写入失败停止派发并明确提示，保留上一版结果及日志；重启根据已保存行重建，不调用接口；取消时等待已启动的写入线程结束。
- 验证：34 项 Python 测试、6 项 Node 测试通过；两个前端脚本语法通过。覆盖逐题写入、原子失败保护、并发结果完整、保存时取消和历史重建。未访问任何接口或读取用户真实工作簿。
- 文档：agents.md、设计文档和 README 同步更新；现有服务需用户重启，浏览器需刷新。

## H 列整理与接口配置记忆
- 用户批准：有用内容在 H 单元格内固定分段，并保存 URL、app_id、version_id 供后续选择。
- 新增 app/report.py：合并增量正文；问题理解、阶段、SQL、查询数据、图表、统计与执行信息分段；累计 rewriteQuestion 不重复写入；相同图表数据引用查询数据。未知结构与异常保留补充段，原始帧在整理前完整写入 JSONL。
- 执行与恢复共用整理器，取消在途执行时先标记中断再保存报告；继续使用每题原子更新 XLSX 的机制，已有完成任务不批量改写。
- 前端支持命名保存、多接口/版本选择、执行时自动保存、刷新恢复；只允许名称与三个接口字段进入 localStorage。切换配置清空请求头，配置存储失败不影响当前执行；界面说明浏览器、地址和端口的保存范围。
- 只读审查修复两项 P2：非字符串消息 type 导致整理异常并丢原始帧；localStorage 写失败导致下拉选择与实际配置不一致。均有先失败后通过的回归。
- 2026-10-15 验证：40 项 Python 测试、9 项 Node 测试全部通过；app.js、view.js 语法检查通过。覆盖报告内容、SQL/数据保留、重复快照省略、未知事件、原始 JSONL、取消/恢复、XLSX 逐题保存、配置恢复/切换、认证排除与存储故障。
- 验证边界：仅构造数据、内存 MockTransport 和模拟 DOM；未启动服务、未访问任何接口、未读取真实工作簿、未进行真实浏览器端到端验收。

## 源文件逐题回写与 SQL/回答分列
- 设计已获批：docs/batch-runner-design.md「本轮变更：源文件逐题回写与 SQL/回答分列」一节，取代历史设计中单列 H、上传副本与源文件不覆盖的语义。
- 后端与测试：后端行为——页面默认输入原始 .xlsx 本地绝对路径加载（保留上传接口兼容）；新任务 output_format=split，H=完整 SQL（多条顺序编号）、I=text 增量拼接的最终回答；H/I 任一已有内容默认整行跳过，勾选覆盖则覆盖原文件两列；SQL 与回答分别独立检查 32767 UTF-16 容量。
- 回写机制：source.xlsx 为运行前备份、result.xlsx 为结果副本；每题结束立即回写原文件；writeback.json 记录路径与 SHA256，外部修改即停止回写；同目录随机临时文件 + fsync + os.replace 原子替换，失败临时文件保留。
- 前端完成：index.html/app.js/view.js/style.css 新增「打开原文件 / 上传文件」双模式切换，原路径为默认模式并接入 POST /api/workbooks/open；详情弹窗按 output_format 分列展示 SQL、最终回答与完整过程（历史 trace 行保持单段）；副标题、流程图、表头、覆盖勾选与提示文案更新为 H/I 分列语义。view.js 新增 openRequest、detailSections、writebackLabel 纯函数，test_view.cjs 补 3 项回归（路径校验、分段展示、两种模式文案）。
- 文档同步：README.md 按新语义更新简介、操作步骤、覆盖/回写规则、H/I 分列与日志说明；batch-runner-plan.md 追加 Task 5 条目；历史设计中单列 H 语义由 design 文档新节声明取代，design 文档本身未改动。
- 2026-10-15 验证：46 项 Python 测试、12 项 Node 测试全部通过；app.js、view.js 语法检查通过。覆盖原路径回写、加载后源文件变更拒绝、执行中外部修改停止回写、H/I 两列独立容量、分段展示与配置记忆等。
- 验证边界：仅构造数据、内存 MockTransport 与模拟 DOM；未启动服务、未访问任何接口、未读取真实工作簿、未进行真实浏览器端到端验收。
- 页面收敛为单一路径加载：删除「打开原文件 / 上传文件」双模式切换与上传面板，不再回显或记录用户输入的路径（含执行后副标题中的路径回显）；后端 POST /api/uploads 接口仍保留用于离线测试与旧调用兼容，但页面不再提供上传操作。
- 页头删除 G→SSE→H·I 流程图；详情弹窗新增点击外部区域关闭；新增常驻 sticky 主操作条（路径、加载、起始行、并发、预览/开始执行集中在页首），加载与选择 sheet 后自动预览，复用乱序防护。
- 2026-10-15 统一验证：46 项 Python 测试、14 项 Node 测试全部通过；app.js、view.js 语法检查通过；残留自查（mode-toggle、upload-panel、source-info、writebackLabel、页头流程图）0 处。
- 验证边界：仅构造数据与模拟 DOM；未启动服务、未访问任何接口、未读取真实工作簿、未进行真实浏览器端到端验收。

## 界面细节修正
- 用户反馈两处样式问题：顶部操作条控件高度/基线不齐；保存接口配置时提示框变化引起「配置名称」输入区位移。
- 修复：新增 --control-h 统一输入框/下拉/操作条按钮高度（38px）；路径提示行移出输入组、独占整行，第一行控件底部对齐；#save-profile 补间距并固定高度，#profile-hint 预留两行高度，三态文案切换不再引起重排。仅 index.html 与 style.css 改动。
- 2026-10-16 验证：46 项 Python 测试、14 项 Node 测试全部通过；app.js、view.js 语法检查通过。未做真实浏览器截图比对，控件高度为 CSS 推导结果。

## 分发说明
- README 启动示例改为通用占位 `cd <项目目录>`（3 处）；新增「分发给他人」小节：打包清单（必带 app/、pyproject.toml、README.md；可选 tests/、docs/；不带 runtime/、.venv/、缓存与真实工作簿）、压缩命令、离线 wheels 安装与可编辑安装说明。
- 仅文档改动，未改代码；可打包文件已核对不含本机绝对路径（runtime 数据内的历史路径属运行记录，不参与分发）。
