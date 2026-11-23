/**
 * 实验中心实验室流水线 — 与《autobi实验室接口调用流程.md》顺序一致（18 步）。
 * 跳过步骤使用 apiKey `pipeline-skip`，便于日志与调试面板区分。
 */

const COLORS = [
  '#5B8FF9',
  '#61DDAA',
  '#65789B',
  '#F6BD16',
  '#7262FD',
  '#78D3F8',
  '#9661BC',
  '#F6903D',
  '#008685',
  '#F08BB4',
  '#9AD681',
  '#FF9845',
  '#1E9493',
  '#FF99C3',
  '#BD6EAF',
  '#5AD8A6',
  '#9270CA',
  '#E8684A',
  '#269A99'
]

function step(stepId, title, apiKey) {
  const idx = stepId - 1
  return {
    stepId,
    title,
    apiKey,
    color: COLORS[idx % COLORS.length]
  }
}

/**
 * @type {Array<{ stepId: number, title: string, apiKey: string, color: string }>}
 */
export const AUTOB_LAB_PIPELINE_STEPS = [
  step(1, 'ES表值召回', 'elasticsearch-value-retriever'),
  step(2, 'elasticsearch-alias（跳过）', 'pipeline-skip'),
  step(3, 'ES知识词召回', 'elasticsearch-knowledge-retriever'),
  step(4, '知识改写', 'knowledge-rewrite'),
  step(5, 'SQL样例精准查询（跳过）', 'pipeline-skip'),
  step(6, '表字段召回', 'table-meta-retriever'),
  step(7, '表值召回(对应字段)', 'global-value-meta-retriever'),
  step(8, 'SQL样例召回', 'icl-template-retriever'),
  step(9, 'ES表值召回（双次检索合并）', 'elasticsearch-value-retriever'),
  step(10, 'elasticsearch-alias（跳过）', 'pipeline-skip'),
  step(11, '表值召回', 'table-value-retriever'),
  step(12, '多列同值召回', 'multi-global-value-meta-retriever'),
  step(13, 'NER 大模型召回', 'ner-retrieval'),
  step(14, 'nl2sql', 'nl2sql'),
  step(15, 'SQL改写', 'sql-permission-rewrite'),
  step(16, 'sql-data-retriever', 'sql-data-retriever'),
  step(17, '数据总结', 'bi-data-summary'),
  step(18, '智能图表配置', 'chart-spec')
]

export const BI_DATA_SUMMARY_KEY = 'bi-data-summary'
