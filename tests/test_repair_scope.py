import json
from unittest.mock import patch
import pytest
from causaltrace import build_doctor


@pytest.mark.parametrize('include_source', [True, False])
def test_model_receives_only_permitted_replacement_paths_but_tests_remain_evidence(include_source):
    files = [build_doctor.SourceFile(path='test_users.py', content='from users import normalize_user'),
             build_doctor.SourceFile(path='package.json', content='{}')]
    if include_source:
        files.append(build_doctor.SourceFile(path='users.py', content='def normalize_username(): pass'))
    request = build_doctor.BuildRequest(log='ImportError: normalize_user', files=files)
    response = json.dumps({'category':'import', 'summary':'Public import contract changed',
                           'evidence':['ImportError'], 'recommended_steps':['Restore the public name'],
                           'replacements':[]})
    with patch.object(build_doctor, 'complete', return_value=(response, 'mock')) as complete:
        build_doctor.investigate(request)
    messages = complete.call_args.kwargs['messages']
    schema = json.loads(messages[0]['content'].split('Return ONLY a JSON object matching this schema: ', 1)[1])
    if include_source:
        assert schema['$defs']['Replacement']['properties']['path']['enum'] == ['users.py']
    else:
        assert schema['properties']['replacements']['maxItems'] == 0
    evidence = json.loads(messages[1]['content'])['files']
    assert any(file['path'] == 'test_users.py' for file in evidence)
