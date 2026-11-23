"""Conservative, read-only inventory of canvas input references for diagnostics."""
import re

_SLOTS = re.compile(r'\{\{\s*([^}]+?)\s*\}\}|\$\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}')
_REF_KEYS = {'ref', 'source_ref', 'source_var', 'context_vars'}


def workflow_input_usage(nodes, inputs):
    declared, references = {}, {}
    dynamic_readers = set()
    user_nodes = {}
    labels = {node.get('id'): (node.get('data') or {}).get('label') or node.get('id') for node in nodes}
    for node in nodes:
        data = node.get('data') or {}
        if data.get('kind') != 'userInput':
            continue
        fields = data.get('fields') or [{'variable': 'input'}]
        keys = {field.get('variable') for field in fields if field.get('variable')}
        for name in (data.get('label') or '用户输入', data.get('var_name')):
            if name:
                user_nodes[name] = keys
        for key in keys:
            declared.setdefault(key, set()).add(labels[node.get('id')])

    def add(reference, label):
        if not isinstance(reference, str):
            return
        reference = reference.strip()
        if reference in inputs:
            references.setdefault(reference, set()).add(label)
        elif reference.startswith('metadata.') and 'metadata' in inputs:
            references.setdefault('metadata', set()).add(label)
        else:
            for name, keys in user_nodes.items():
                if reference.startswith(name + '.'):
                    key = reference[len(name) + 1:].split('.', 1)[0].split('[', 1)[0]
                    if key in keys:
                        references.setdefault(key, set()).add(label)

    def visit(value, label, key=''):
        if isinstance(value, dict):
            # Constant/ref rows must not report their literal text as a binding.
            for child_key, child in value.items():
                if child_key in _REF_KEYS and value.get('source_mode') == 'const':
                    continue
                visit(child, label, child_key)
        elif isinstance(value, list):
            if key == 'source_ref' and len(value) >= 2 and value[0] in {'input', 'session'}:
                add(value[1], label)
            else:
                for child in value:
                    visit(child, label, key)
        elif isinstance(value, str):
            if key in _REF_KEYS:
                add(value, label)
            # Code literals and constants are not prompt templates. Legacy
            # scripts can read params.metadata dynamically; report that separately.
            if key == 'code':
                if re.search(r'\bparams\.metadata\b', value):
                    # params.metadata is synthesized by the script executor,
                    # not a direct alias for inputs.metadata. Its inputs bag
                    # permits dynamic access to any forwarded context field.
                    dynamic_readers.add(label)
                return
            if key not in {'const_value', 'default', 'description', 'label'}:
                for match in _SLOTS.finditer(value):
                    add(match.group(1) or match.group(2), label)

    for node in nodes:
        visit(node.get('data') or {}, labels[node.get('id')])
    return {
        'method': 'static_canvas_references',
        'note': '声明字段和模板/引用候选按当前版本画布分析；对象内部、脚本动态读取和子流程透传仍可能使用其他字段，未发现引用不等于可删除。'
                + (' 动态读取节点：' + '、'.join(sorted(dynamic_readers)) if dynamic_readers else ''),
        'dynamic_readers': sorted(dynamic_readers),
        'fields': [{'name': key, 'declared_by': sorted(declared.get(key, ())),
                    'referenced_by': sorted(references.get(key, ())),
                    'status': 'referenced' if key in references else 'declared' if key in declared else 'possible_context'}
                   for key in inputs],
    }
