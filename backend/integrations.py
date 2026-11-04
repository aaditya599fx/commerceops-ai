"""Private, credential-bound connection evidence, separate from fixture run metrics."""
import fcntl
import hashlib
import json
import os
import tempfile
from datetime import datetime, timezone, timedelta
from pathlib import Path
from .config import ROOT

CHECK_PATH=ROOT/'runtime/integration-checks.json'
FIELDS={
    'openai':['OPENAI_API_KEY','OPENAI_MODEL'],
    'gemini':['GEMINI_API_KEY','GEMINI_MODEL'],
    'shopify':['SHOPIFY_SHOP','SHOPIFY_ACCESS_TOKEN','SHOPIFY_CLIENT_ID','SHOPIFY_CLIENT_SECRET','SHOPIFY_WEBHOOK_SECRET','SHOPIFY_PREVIOUS_WEBHOOK_SECRET','PUBLIC_BASE_URL'],
    'slack':['SLACK_BOT_TOKEN','SLACK_CHANNEL_ID','SLACK_SIGNING_SECRET','SLACK_APPROVER_IDS','PUBLIC_BASE_URL'],
    'hubspot':['HUBSPOT_ACCESS_TOKEN'],
    'sheets':['GOOGLE_SERVICE_ACCOUNT_FILE','GOOGLE_SPREADSHEET_ID','GOOGLE_SHEET_RANGE'],
}

def binding(service):
    values=[os.getenv(k,'') for k in FIELDS[service]]
    if service=='sheets':
        path=os.getenv('GOOGLE_SERVICE_ACCOUNT_FILE','')
        if path and Path(path).is_file():values.append(hashlib.sha256(Path(path).read_bytes()).hexdigest())
    return hashlib.sha256(json.dumps(values).encode()).hexdigest()

def record_check(service,phase,status,category=None):
    CHECK_PATH.parent.mkdir(parents=True,exist_ok=True)
    with open(str(CHECK_PATH)+'.lock','a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        try:data=json.loads(CHECK_PATH.read_text()) if CHECK_PATH.exists() else {}
        except ValueError:data={}
        entry=data.setdefault(service,{})
        fingerprint=binding(service)
        if entry.get('binding')!=fingerprint:entry.clear()
        entry['binding']=fingerprint
        entry[phase]={'status':status,'category':category,'checked_at':datetime.now(timezone.utc).isoformat()}
        with tempfile.NamedTemporaryFile('w',dir=CHECK_PATH.parent,delete=False) as stream:
            json.dump(data,stream,indent=2);temp=Path(stream.name)
        temp.chmod(0o600);os.replace(temp,CHECK_PATH)

def read_checks():
    try:data=json.loads(CHECK_PATH.read_text())
    except (OSError,ValueError):return {}
    result={};cutoff=datetime.now(timezone.utc)-timedelta(hours=24)
    for service,entry in data.items():
        if service not in FIELDS or entry.get('binding')!=binding(service):continue
        phases={}
        for phase,value in entry.items():
            if phase=='binding':continue
            try:fresh=datetime.fromisoformat(value['checked_at'])>=cutoff
            except (KeyError,ValueError,TypeError):fresh=False
            if fresh:phases[phase]=value
        if phases:result[service]=phases
    return result
