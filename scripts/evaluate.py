"""Measure a fixed synthetic workload in an isolated DB, never inventing business impact."""
import asyncio, json, sys, time
from datetime import datetime, timezone
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backend.config import ROOT, Settings
from backend.db import DB, Fact, dump
from backend.models import Event
from backend.providers import Providers
from backend.engine import Engine

async def main():
    path=ROOT/'runtime/evaluation.db'
    for suffix in ('','-wal','-shm'):
        p=Path(str(path)+suffix)
        if p.exists():p.unlink()
    settings=Settings(mode='fixture',token='isolated-evaluation-token-no-credentials',database_url='sqlite:///'+str(path))
    db=DB(settings.database_url); provider=Providers(settings,db); engine=Engine(settings,db,provider)
    data=json.loads((ROOT/'data/dataset.json').read_text()); stamp=datetime.now(timezone.utc).isoformat(); date=stamp[:10]
    with db.session.begin() as s:
        for order in data['orders']:s.add(Fact(key=order['id'],kind='order',source='synthetic',value=dump(order)))
    events=[]
    for kind,records in [('cart.abandoned',data['carts']),('review.created',data['reviews']),('product.created',data['products']),('customer.updated',data['customers']),
        ('inventory.updated',[{'sku':f'SKU-{i:02d}','available':i*3,'daily_units':float(i%5),'lead_days':7} for i in range(20)]),('brief.requested',[{'date':date}])]:
        for i,p in enumerate(records):events.append(Event.model_validate({'event_id':kind+':'+str(i),'type':kind,'timestamp':stamp,'source':'synthetic','payload':p}))
    start=time.perf_counter()
    for event in events:
        engine.ingest(event);await engine.process(event.event_id)
        if engine.result(event.event_id)['status']=='awaiting_approval':await engine.decide(event.event_id,'approve','synthetic-test-reviewer','Automated test decision, not a human approval measurement')
        await engine.flush()
    for event in events[:10]:
        for _ in range(3):engine.ingest(event);await engine.process(event.event_id);await engine.flush()
    metrics=engine.metrics(); metrics['mean_approval_seconds']=None
    report={'measured_at':stamp,'environment':'single-process local Python, SQLite, deterministic fixture providers',
        'methodology':'161 fictional events across six workflows; 30 duplicate deliveries replayed; no external service calls. Eligible excludes policy-blocked/rejected; pending and failed eligible events remain in denominator.',
        'duration_seconds':round(time.perf_counter()-start,3),'metrics':metrics,
        'assertions':{'no_duplicate_effect_keys':metrics['duplicate_effect_keys']==0,'all_eligible_completed':metrics['successful_runs']==metrics['eligible_runs'],
            'blocked_events_have_no_side_effects':all(not engine.result(ev.event_id)['effects'] for ev in events if engine.result(ev.event_id)['status']=='blocked')},
        'not_measured':['Live API reliability','LLM classification accuracy','Human approval latency','Business impact','Time savings','Dollar cost','Production throughput','Exactly-once delivery at third parties']}
    target=ROOT/'evidence/reliability.json';target.write_text(json.dumps(report,indent=2))
    lines=['# Measured synthetic evaluation','',f'Run: {stamp}', '',report['environment'], '', report['methodology'],'',
        '| Measurement | Result |','|---|---|',f'| Unique events | {metrics["total_events"]} |',f'| Successful / eligible | {metrics["successful_runs"]} / {metrics["eligible_runs"]} |',
        f'| Safely blocked | {metrics["statuses"].get("blocked",0)} |',f'| Duplicate deliveries suppressed | {metrics["duplicate_deliveries_suppressed"]} |',
        f'| Duplicate recorded effect keys | {metrics["duplicate_effect_keys"]} |',f'| Fixture schema-valid outputs | {metrics["schema_valid_outputs"]} / {metrics["schema_outputs"]} |','',
        'These results measure a deterministic local workload. They are not evidence of live integration reliability, model quality, production throughput or business improvement.', '',
        'Fault injection and webhook authentication are covered separately by tests/test_system.py. Raw pytest output is in evidence/pytest.txt.', '',
        'Not measured: '+', '.join(report['not_measured'])+'.']
    (ROOT/'evidence/reliability.md').write_text('\n'.join(lines)+'\n')
    await provider.close(); print(json.dumps({'events':metrics['total_events'],'successful':metrics['successful_runs'],'eligible':metrics['eligible_runs'],'assertions':report['assertions']}))
    if not all(report['assertions'].values()):raise SystemExit(1)
if __name__=='__main__':asyncio.run(main())
