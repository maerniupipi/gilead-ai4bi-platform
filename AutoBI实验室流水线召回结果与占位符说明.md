# AutoBI 实验室流水线召回结果与占位符说明

## 1. 先区分两类占位符

实验室提示词中的 `{{ ... }}` 有两种来源。

### 1.1 流水线内置占位符

这类变量由流水线在运行到对应步骤时自动生成并替换，例如：

```text
{{table_field_prompt_data}}
{{qs_recall}}
{{icl_example_prompt_data}}
{{knowledge_prompt_data}}
{{query}}
```

它们不需要在请求体中传值。

### 1.2 `features` 自定义占位符

请求体中的 `features` 可以替换提示词里的同名自定义变量，例如（`qs_recall` 为流水线保留变量，不能由调用方覆盖）：

```json
{
  "features": {
    "max_year": 2026,
    "max_month": "03",
    "business_rule": "销售金额统一按人民币统计"
  }
}
```

提示词中可以写：

```text
当前最大年份：{{max_year}}
当前最大月份：{{max_month}}
补充业务规则：{{business_rule}}
```

也支持嵌套写法：

```json
{
  "features": {
    "time": {
      "max_year": 2026
    }
  }
}
```

对应：

```text
{{time.max_year}}
```

注意：`features` 只是请求参数替换，不能直接引用流水线某一步的召回结果。

---

## 2. 召回结果与内置占位符对应表

| 步骤 | 流水线能力 | 结果用途 | 最终可用占位符 |
|---|---|---|---|
| 1 | ES 表值召回 | 调试追踪；参与合并候选值 | `{{qs_recall}}` |
| 2 | Elasticsearch alias | 当前跳过 | 无 |
| 3 | ES 知识词召回 | 知识改写、NL2SQL 其他知识点、步骤 9 长查询 | `{{knowledge_words}}`、`{{knowledge_prompt_data}}` |
| 4 | 知识改写 | 生成改写后的用户问题 | 后续步骤中的 `{{query}}`、图表中的 `{{rewrite_query}}` |
| 5 | SQL 样例精准查询 | 当前跳过 | 无 |
| 6 | 表字段召回 | 表、字段和字段说明 | `{{table_field_prompt_data}}` |
| 7 | 表值召回（对应字段） | 候选值及其所属字段 | `{{table_field_prompt_data}}`、`{{qs_recall}}` |
| 8 | SQL 样例召回 | 相似问题及 SQL 示例 | `{{icl_example_prompt_data}}` |
| 9 | ES 表值双次召回 | 原问题扩展检索 + 改写问题检索 | `{{table_field_prompt_data}}`、`{{qs_recall}}` |
| 10 | Elasticsearch alias | 当前跳过 | 无 |
| 11 | 表值召回 | 按步骤 6/7 命中的表进行候选值召回 | `{{table_field_prompt_data}}`、`{{qs_recall}}` |
| 12 | 多列同值召回 | 按步骤 6/7 命中的字段进行多路候选值召回 | `{{table_field_prompt_data}}`、`{{qs_recall}}` |
| 13 | NER 大模型召回 | 实体识别及别名映射 | `{{ner_info}}` |
| 14 | NL2SQL | 生成 SQL | 后续步骤中的 `{{execute_sql}}` |
| 15 | SQL 权限改写 | 对生成的 SQL 做权限改写 | 后续步骤中的 `{{execute_sql}}` |
| 16 | SQL 数据查询 | 返回列、数据行和总行数 | 图表中的 `{{field_mapping}}`、`{{sql_result_json}}`；数据总结由代码直接拼入 |
| 17 | 数据总结 | 生成最终文字回答 | 无后续提示词占位符 |
| 18 | 智能图表配置 | 生成图表类型和坐标轴配置 | 流水线最终输出 `chart_spec` |

---

## 3. 各提示词实际可用变量

### 3.1 知识改写提示词

配置位置：`knowledge_rewrite_config.prompt`

| 占位符 | 内容 |
|---|---|
| `{{rewrite_query}}` | 用户原始问题 |
| `{{knowledge_words}}` | 步骤 3 的知识词召回结果，格式为“知识词 → 扩展说明” |

示例：

```text
用户问题：
{{rewrite_query}}

知识词召回：
{{knowledge_words}}
```

### 3.2 NER 提示词

配置位置：`ner_retrieval_config.prompt`

| 占位符 | 内容 |
|---|---|
| `{{query}}` | 知识改写后的问题；未改写时为原问题 |
| `{{filed}}` | 要抽取的实体类型。代码沿用了 `filed` 拼写，不是 `field` |
| `{{qs_recall}}` | 按表、字段合并去重的候选值，详见第 7 节 |

示例：

```text
实体类型：
{{filed}}

用户问题：
{{query}}
```

### 3.3 NL2SQL 提示词

配置位置：`nl2sql_config.prompt`

| 占位符 | 内容 |
|---|---|
| `{{database_type}}` | 知识库数据库类型 |
| `{{table_field_prompt_data}}` | 步骤 6、7、9，以及步骤 11 或 12 的聚合结果 |
| `{{qs_recall}}` | 步骤 1、7、9，以及实际执行的步骤 11 或 12 的候选值合并去重文本 |
| `{{icl_example_prompt_data}}` | 步骤 8 的 SQL 样例召回结果 |
| `{{knowledge_prompt_data}}` | 步骤 3 的知识词召回结果 |
| `{{ner_info}}` | 步骤 13 的 NER 实体及别名映射说明 |
| `{{query}}` | 知识改写后的问题；未改写时为原问题 |
| `{{table_join_relation_prompt_data}}` | 当前固定替换为空字符串 |
| `{{default_field_prompt_data}}` | 当前固定替换为空字符串 |

推荐模板：

```text
数据库类型：
{{database_type}}

表、字段和候选值：
{{table_field_prompt_data}}

相似问题 SQL：
{{icl_example_prompt_data}}

知识词：
{{knowledge_prompt_data}}

NER 实体映射：
{{ner_info}}

当前问题：
{{query}}
```

`{{table_field_prompt_data}}` 内部会按以下标题组织：

```text
【表字段召回 table-meta】
【表值(对应字段) global-value-meta】
【ES 表值（双次检索合并）】
【表值召回 table-value】
```

开启多列同值召回时，最后一段会替换为：

```text
【多列同值召回 multi-global-value-meta】
```

### 3.4 数据总结提示词

配置位置：`bi_summary_config.prompt`

当前实现不是把所有 SQL 变量逐个替换到原模板中，而是：

1. 先替换模板中的 `{{rewrite_query}}`。
2. 清除模板中剩余的 `{{ ... }}`。
3. 由代码在提示词末尾追加用户原始问题、最终 SQL 和 SQL 执行结果。

因此数据总结模板中稳定可直接使用的内置变量包括：

| 占位符 | 内容 |
|---|---|
| `{{rewrite_query}}` | 当前实现实际传入的是用户原始问题 |
| `{{qs_recall}}` | 已完成的候选值合并去重文本，在清除其余模板变量前由运行时 features 替换 |

`features` 自定义变量会在流水线执行前预先替换，因此仍然可以使用。

### 3.5 智能图表提示词

配置位置：`chart_drawing_config.prompt`

| 占位符 | 内容 |
|---|---|
| `{{original_query}}` | 用户原始问题 |
| `{{rewrite_query}}` | 知识改写后的问题 |
| `{{execute_sql}}` | 步骤 14/15 最终得到的 SQL |
| `{{field_mapping}}` | SQL 结果字段映射，当前格式为 `列名:列名` |
| `{{sql_result_json}}` | SQL 查询结果 JSON，默认最多提供前 80 行 |
| `{{qs_recall}}` | 已完成的候选值合并去重文本 |

---

## 4. 值召回应该写成什么

当前不能写：

```text
值召回：{{abc}}
```

除非请求体 `features` 中真的传了 `abc`。这种写法取得的是自定义参数，不是流水线召回结果。

当前要把全部字段和值召回结果交给 NL2SQL，应写：

```text
表、字段和值召回结果：
{{table_field_prompt_data}}
```

如果需要按表、字段展示合并去重后的候选值，可以写：

```text
候选值召回结果：
{{qs_recall}}
```

`qs_recall` 只汇总本次召回的候选值；完整字段结构仍可通过 `table_field_prompt_data` 提供。

SQL 样例和知识词需要分别写：

```text
SQL 样例召回：
{{icl_example_prompt_data}}

知识词召回：
{{knowledge_prompt_data}}

NER 召回：
{{ner_info}}
```

---

## 5. 步骤 11 与步骤 12 的互斥关系

- 未开启“多列同值召回”时：执行步骤 11，步骤 12 跳过。
- 开启“多列同值召回”时：步骤 11 跳过，执行步骤 12。
- `{{table_field_prompt_data}}` 只会收录步骤 11 或步骤 12 中实际执行的一路。
- 步骤 12 依赖步骤 6/7 返回的 `metadata.field_code`。
- 步骤 11 优先按步骤 6/7 返回的 `metadata.field_table` 分表并行召回。

---

## 6. 当前能力边界

流水线现在会在每一步完成后，额外向本次运行的内部 `features` 写入两类值：

```text
{{<api_key>_result}}
{{<api_key>_nlp}}
```

其中：

- `_result` 是该步骤完整返回参数的 JSON 文本。
- `_nlp` 是将返回参数转换后的自然语言文本，适合直接放入后续 Prompt。
- 变量只能被该步骤之后的 Prompt 使用，不能向前引用尚未执行的步骤。

例如步骤 1 完成后，可以在知识改写、NER、NL2SQL、数据总结或图表 Prompt 中使用：

```text
ES 表值原始结果：
{{elasticsearch-value-retriever_result}}

ES 表值自然语言结果：
{{elasticsearch-value-retriever_nlp}}
```

### 6.1 同名 `api_key` 的处理

步骤 1 和步骤 9 的 `api_key` 都是 `elasticsearch-value-retriever`。因此无步骤号变量表示最近一次执行完成的同名能力：

```text
{{elasticsearch-value-retriever_result}}
{{elasticsearch-value-retriever_nlp}}
```

如需稳定指定某一步，使用系统同时生成的带步骤号变量：

```text
{{step_1_elasticsearch-value-retriever_result}}
{{step_1_elasticsearch-value-retriever_nlp}}

{{step_9_elasticsearch-value-retriever_result}}
{{step_9_elasticsearch-value-retriever_nlp}}
```

所有步骤都遵循相同规则：

```text
{{step_<步骤号>_<api_key>_result}}
{{step_<步骤号>_<api_key>_nlp}}
```

这部分是额外能力，不改变原有的 `{{table_field_prompt_data}}`、`{{icl_example_prompt_data}}`、`{{knowledge_prompt_data}}` 和 `{{ner_info}}` 聚合逻辑。

---

## 7. 合并候选值变量 `{{qs_recall}}`

`qs_recall` 是流水线内置变量，不需要在请求 `features` 中传值；调用方传入同名值不会覆盖它。

- 候选值来源：步骤 1、9 的 ES 表值召回，步骤 7 的向量表值召回，以及实际执行的步骤 11 或 12。
- 生成时机：第 12 步结束后统一生成，包括多列同值关闭、第 12 步跳过的情况；可用于第 13 步 NER、NL2SQL、数据总结和图表 Prompt。
- 去重粒度：`(表名, 字段名, 候选值)`。同一字段的同值无论来源、分数如何，只展示一次；不同字段、不同表的同值分别保留。
- 字段标识：`表&&字段`、`表.字段`、`field_table + 字段裸名` 统一按物理表与字段分组。
- 顺序：按来源步骤顺序、每一步结果的首次出现顺序输出；去掉空值、首尾空白，保留大小写，不合并同义值。
- 中文说明：优先批量读取当前知识库命中表的 `table_alias` 和启用字段的 `field_alias`，以第 6 步表字段说明兜底。缺少说明时保留物理表、字段名，省略说明花括号。
- 第 6 步只补充说明，不把字段描述当作候选值；SQL 样例、知识词、NER 别名也不混入候选值。
- 没有候选值时输出 `（暂无候选值召回结果）`。

示例：

```text
表名："tw_target_cvh"{全渠道月指标(CVH架构)主题表}
字段：
候选值：字段"tw_target_cvh.indication_name"{适应症名称}在数据表中有如下值 ['GC', 'BC', 'GYN', 'LC']
候选值：字段"tw_target_cvh.indication_name12"{适应症名称}在数据表中有如下值 ['GC', 'BC', 'GYN', 'LC']
```

这个变量由代码直接生成，不额外调用大模型，也不会将候选值扩展为数据库整列的完整枚举。
