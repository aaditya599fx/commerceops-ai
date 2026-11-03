"""Validate exported graph structure and absence of embedded credential values."""
import json,re
from pathlib import Path
root=Path(__file__).resolve().parents[1];paths=sorted((root/'workflows').glob('*.json'))
assert len(paths)==9,'Expected nine exported workflows'
for path in paths:
    workflow=json.loads(path.read_text());names={n['name'] for n in workflow['nodes']}
    for source,outputs in workflow['connections'].items():
        assert source in names
        for branches in outputs.values():
            for branch in branches:
                for connection in branch:assert connection['node'] in names
    assert not re.search(r'(?i)(sk-[a-zA-Z0-9_-]{20,}|xoxb-[a-zA-Z0-9-]+|Bearer [a-zA-Z0-9_-]{24,})',path.read_text()),path
    assert 'credentials' not in workflow or not workflow['credentials']
print('Nine exported workflow graphs validated; no embedded token values detected.')
