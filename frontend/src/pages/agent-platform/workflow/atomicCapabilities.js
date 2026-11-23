const CAPABILITIES = [
  {
    value: 'elasticsearch-value-retriever',
    label: 'ES表值召回',
    inputs: [
      { key: 'knowledge_base_id', label: '知识库', type: 'NUMBER', const_value: '', control: 'knowledgeBase' },
      { key: 'query', label: '查询内容', type: 'STRING', const_value: '', wide: true },
      { key: 'top_k', label: '返回条数', type: 'NUMBER', const_value: '5', advanced: true },
      { key: 'score_threshold', label: '分数阈值', type: 'NUMBER', const_value: 'null', advanced: true }
    ],
    outputs: [
      { key: 'results', type: 'LIST<Object>', description: '召回结果列表' },
      { key: 'total', type: 'NUMBER', description: '结果总数' }
    ]
  },
  {
    value: 'elasticsearch-knowledge-retriever',
    label: 'ES知识词召回',
    inputs: [
      { key: 'knowledge_base_id', label: '知识库', type: 'NUMBER', const_value: '', control: 'knowledgeBase' },
      { key: 'query', label: '查询内容', type: 'STRING', const_value: '', wide: true },
      { key: 'top_k', label: '返回条数', type: 'NUMBER', const_value: '8', advanced: true },
      { key: 'score_threshold', label: '分数阈值', type: 'NUMBER', const_value: 'null', advanced: true }
    ],
    outputs: [
      { key: 'results', type: 'LIST<Object>', description: '召回结果列表' },
      { key: 'total', type: 'NUMBER', description: '结果总数' }
    ]
  },
  {
    value: 'sql-template-retriever',
    label: 'SQL样例召回',
    inputs: [
      { key: 'knowledge_base_id', label: '知识库', type: 'NUMBER', const_value: '', control: 'knowledgeBase' },
      { key: 'query', label: '自然语言问题', type: 'STRING', const_value: '', wide: true },
      { key: 'top_k', label: '返回条数', type: 'NUMBER', const_value: '5', advanced: true },
      { key: 'score_threshold', label: '分数阈值', type: 'NUMBER', const_value: 'null', advanced: true }
    ],
    outputs: [
      { key: 'results', type: 'LIST<Object>', description: '召回结果列表' },
      { key: 'total', type: 'NUMBER', description: '结果总数' }
    ]
  },
  {
    value: 'generate-sql',
    label: '生成SQL',
    inputs: [
      { key: 'knowledge_base_id', label: '知识库', type: 'NUMBER', const_value: '', control: 'knowledgeBase' },
      { key: 'query', label: '用户问题', type: 'STRING', const_value: '', wide: true },
      { key: 'provider_id', label: '模型供应商', type: 'NUMBER', const_value: '', control: 'modelProvider' },
      { key: 'model_name', label: '模型名称', type: 'STRING', const_value: '', control: 'modelName' },
      { key: 'temperature', label: '温度', type: 'NUMBER', const_value: '0.2', advanced: true },
      { key: 'max_tokens', label: '最大Token', type: 'NUMBER', const_value: '2048', advanced: true },
      { key: 'top_p', label: 'Top P', type: 'NUMBER', const_value: '0.9', advanced: true }
    ],
    outputs: [
      { key: 'sql', type: 'STRING', description: '生成的 SQL' },
      { key: 'content', type: 'STRING', description: '模型原始输出' },
      { key: 'prompt_preview', type: 'STRING', description: '提示词预览' }
    ]
  },
  {
    value: 'execute-sql',
    label: '执行SQL',
    inputs: [
      { key: 'knowledge_base_id', label: '知识库', type: 'NUMBER', const_value: '', control: 'knowledgeBase' },
      { key: 'sql', label: 'SQL', type: 'STRING', const_value: '', multiline: true, wide: true }
    ],
    outputs: [
      { key: 'sql', type: 'STRING', description: '执行的 SQL' },
      { key: 'columns', type: 'LIST<String>', description: '结果列名' },
      { key: 'rows', type: 'LIST<Object>', description: '结果行' },
      { key: 'row_count', type: 'NUMBER', description: '返回行数' }
    ]
  },
  {
    value: 'table-meta-retriever',
    label: '表字段召回',
    inputs: [
      { key: 'knowledge_base_id', label: '知识库', type: 'NUMBER', const_value: '', control: 'knowledgeBase' },
      { key: 'query', label: '查询内容', type: 'STRING', const_value: '', wide: true },
      { key: 'top_k', label: '返回条数', type: 'NUMBER', const_value: '15', advanced: true },
      { key: 'score_threshold', label: '分数阈值', type: 'NUMBER', const_value: '0.3', advanced: true }
    ],
    outputs: [
      { key: 'results', type: 'LIST<Object>', description: '召回结果列表' },
      { key: 'total', type: 'NUMBER', description: '结果总数' }
    ]
  },
  {
    value: 'table-value-retriever',
    label: '表值召回',
    inputs: [
      { key: 'knowledge_base_id', label: '知识库', type: 'NUMBER', const_value: '', control: 'knowledgeBase' },
      { key: 'query', label: '查询内容', type: 'STRING', const_value: '', wide: true },
      { key: 'table_name', label: '表名', type: 'STRING', const_value: '' },
      { key: 'top_k', label: '返回条数', type: 'NUMBER', const_value: '6', advanced: true },
      { key: 'score_threshold', label: '分数阈值', type: 'NUMBER', const_value: 'null', advanced: true }
    ],
    outputs: [
      { key: 'results', type: 'LIST<Object>', description: '召回结果列表' },
      { key: 'total', type: 'NUMBER', description: '结果总数' }
    ]
  },
  {
    value: 'global-value-meta-retriever',
    label: '表值召回(对应字段)',
    inputs: [
      { key: 'knowledge_base_id', label: '知识库', type: 'NUMBER', const_value: '', control: 'knowledgeBase' },
      { key: 'query', label: '查询内容', type: 'STRING', const_value: '', wide: true },
      { key: 'table_name', label: '表名/字段', type: 'STRING', const_value: '' },
      { key: 'top_k', label: '返回条数', type: 'NUMBER', const_value: '10', advanced: true },
      { key: 'score_threshold', label: '分数阈值', type: 'NUMBER', const_value: 'null', advanced: true }
    ],
    outputs: [
      { key: 'results', type: 'LIST<Object>', description: '召回结果列表' },
      { key: 'total', type: 'NUMBER', description: '结果总数' }
    ]
  },
  {
    value: 'multi-global-value-meta-retriever',
    label: '多列同值',
    inputs: [
      { key: 'knowledge_base_id', label: '知识库', type: 'NUMBER', const_value: '', control: 'knowledgeBase' },
      { key: 'query', label: '查询内容', type: 'STRING', const_value: '', wide: true },
      { key: 'table_name', label: '表名/字段列表', type: 'LIST<String>', const_value: '[]', multiline: true, wide: true },
      { key: 'top_k', label: '每字段每路返回条数', type: 'NUMBER', const_value: '10', advanced: true },
      { key: 'score_threshold', label: '向量分数阈值', type: 'NUMBER', const_value: 'null', advanced: true },
      { key: 'keyword_score_threshold', label: '关键词分数阈值', type: 'NUMBER', const_value: 'null', advanced: true }
    ],
    outputs: [
      { key: 'results', type: 'LIST<Object>', description: '召回结果列表' },
      { key: 'total', type: 'NUMBER', description: '结果总数' }
    ]
  },
  {
    value: 'ner-retriever',
    label: 'NER',
    inputs: [
      { key: 'knowledge_base_id', label: '知识库', type: 'NUMBER', const_value: '', control: 'knowledgeBase' },
      { key: 'query', label: '用户问题', type: 'STRING', const_value: '', wide: true },
      { key: 'entity', label: '实体列表', type: 'LIST<String>', const_value: '[]', multiline: true, wide: true },
      { key: 'top_k', label: '返回条数', type: 'NUMBER', const_value: '20', advanced: true }
    ],
    outputs: [
      { key: 'results', type: 'LIST<Object>', description: '实体映射结果' },
      { key: 'total', type: 'NUMBER', description: '结果条数' },
      { key: 'narrative', type: 'STRING', description: '自然语言说明' }
    ]
  }
]


/** Request requirements mirror backend/app/schemas/autobi_atomic.py. */
export const ATOMIC_CAPABILITIES = CAPABILITIES.map(capability => ({
  ...capability,
  inputs: capability.inputs.map(input => {
    const required = input.key === 'knowledge_base_id' ? capability.value !== 'generate-sql'
      : input.key === 'query' ? capability.value !== 'ner-retriever'
      : ['sql', 'provider_id', 'model_name', 'entity'].includes(input.key)
        || (input.key === 'table_name' && capability.value === 'multi-global-value-meta-retriever')
    const numericRules = {
      knowledge_base_id: { integer: true, min: 1 },
      provider_id: { integer: true, min: 1 },
      top_k: { integer: true, min: 1, max: capability.value.startsWith('elasticsearch-') ? 200 : ['sql-template-retriever', 'table-meta-retriever'].includes(capability.value) ? 50 : capability.value === 'ner-retriever' ? 500 : 100 },
      temperature: { min: 0, max: 2 },
      max_tokens: { integer: true, min: 1, max: 8192 },
      top_p: { min: 0, max: 1 }
    }
    return { ...input, required, nullable: input.type === 'NUMBER' && !['knowledge_base_id', 'provider_id'].includes(input.key), minItems: required && input.type.startsWith('LIST') ? 1 : undefined, ...(numericRules[input.key] || {}) }
  })
}))

export function buildAtomicInputRows(capability, rows = []) {
  const spec = ATOMIC_CAPABILITIES.find(item => item.value === capability) || ATOMIC_CAPABILITIES[0]
  const saved = new Map(rows.map(row => [row.key, row]))
  return spec.inputs.map(input => {
    const candidate = saved.get(input.key) || {}
    const old = candidate.type && candidate.type !== input.type ? {} : candidate
    const raw = old.const_value ?? input.const_value ?? ''
    return {
      ...input,
      source_mode: old.source_mode || 'const',
      source_ref: old.source_ref || old.ref || '',
      const_value: typeof raw === 'object' ? JSON.stringify(raw) : String(raw),
      advanced: !!input.advanced, wide: !!input.wide, multiline: !!input.multiline
    }
  })
}
