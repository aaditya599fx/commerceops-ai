import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

import pytest

@pytest.fixture(autouse=True)
def isolate_connection_evidence(tmp_path,monkeypatch):
    import backend.integrations
    monkeypatch.setattr(backend.integrations,'CHECK_PATH',tmp_path/'checks.json')
