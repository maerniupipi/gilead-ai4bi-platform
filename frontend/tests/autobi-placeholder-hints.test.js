import assert from 'node:assert/strict'
import test from 'node:test'
import { listPlaceholderKeysFromConfig } from '../src/utils/autobiPlaceholderHints.js'

test('qs_recall is an internal recall variable rather than a caller feature hint', () => {
  const config = { request: { advanced_config: {
    nl2sql_config: { prompt: '{{qs_recall}} {{ max_year }} {{max_month}} {{ max_year }}' },
    ner_retrieval_config: { prompt: '{{ qs_recall }} {{business_rule}}' }
  } } }
  assert.deepEqual(listPlaceholderKeysFromConfig(config), ['business_rule', 'max_month', 'max_year'])
})
