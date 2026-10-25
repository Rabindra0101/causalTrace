from causaltrace.evidence_graph import build_investigation_graph


def test_graph_does_not_attribute_non_ai_experiments_to_a_model():
    graph = build_investigation_graph(
        {'output': 'failed', 'return_code': 1}, 'commit',
        'Model analysis was not requested.', {'verified': True})
    hypothesis = next(node for node in graph['nodes'] if node['type'] == 'ai_hypothesis')
    assert hypothesis['data']['model'] == 'not_requested'
