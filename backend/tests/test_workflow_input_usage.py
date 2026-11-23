from copy import deepcopy

from app.services.agent_app.input_usage import workflow_input_usage


def test_inventory_distinguishes_declared_referenced_and_possible_inputs_without_mutating_canvas():
    nodes = [
        {'id': 'i', 'data': {'kind': 'userInput', 'label': '用户输入', 'fields': [{'variable': 'input'}, {'variable': 'features'}]}},
        {'id': 's', 'data': {'kind': 'script', 'label': '旧脚本', 'script_config': {
            'code': 'def execute_history(params):\n    return params.metadata.get("messages")',
            'input_vars': [{'name': 'arg1', 'ref': '用户输入.input'}]}}},
        {'id': 'm', 'data': {'kind': 'llm', 'label': '模型', 'llm_config': {
            'system_prompt': '历史 {{history_question}}；角色 {{ metadata.qa_role }}',
            'param_bindings': {'business': {'source_mode': 'const', 'ref': 'not_used'}}}}},
    ]
    original = deepcopy(nodes)
    result = workflow_input_usage(nodes, {'input': '问题', 'features': {}, 'history_question': '上题',
                                          'metadata': {}, 'user_id': '123', 'not_used': 'literal'})
    fields = {row['name']: row for row in result['fields']}
    assert fields['input']['status'] == 'referenced' and fields['input']['referenced_by'] == ['旧脚本']
    assert fields['features']['status'] == 'declared'
    assert fields['history_question']['referenced_by'] == ['模型']
    assert fields['metadata']['referenced_by'] == ['模型']
    assert result['dynamic_readers'] == ['旧脚本']
    assert fields['user_id']['status'] == fields['not_used']['status'] == 'possible_context'
    assert nodes == original
