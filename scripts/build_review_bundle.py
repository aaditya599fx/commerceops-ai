"""Build an offline reviewer site from actual isolated fixture runs and recorded evidence.

No live API calls, credentials, databases or .env files enter this bundle.
"""
import argparse,asyncio,copy,json,shutil,sys,tempfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backend.config import ROOT,Settings
from backend.db import DB,Fact,dump,now
from backend.engine import Engine
from backend.models import Event
from backend.providers import Providers

async def snapshot():
    with tempfile.TemporaryDirectory(prefix='reviewer-',dir=ROOT/'runtime') as tmp:
        cfg=Settings(mode='fixture',token='isolated-reviewer-fixture-only-token',database_url='sqlite:///'+str(Path(tmp)/'review.db'))
        db=DB(cfg.database_url);provider=Providers(cfg,db);engine=Engine(cfg,db,provider)
        try:
            data=json.loads((ROOT/'data/dataset.json').read_text())
            with db.session.begin() as session:
                for order in data['orders']:
                    session.add(Fact(key='order:'+order['id'],kind='order',source='synthetic',value=dump(order)))
            examples=json.loads((ROOT/'data/events.json').read_text());runs=[]
            for index in [0,2,3,4,5,6]:
                original=copy.deepcopy(examples[index]);original['event_id']='reviewer-'+original['type'];event=Event.model_validate(original)
                engine.ingest(event);await engine.process(event.event_id);await engine.flush()
                before=engine.result(event.event_id)
                if before['status']=='awaiting_approval':
                    await engine.decide(event.event_id,'approve','fixture-demo-operator','Automated fixture demonstration; not a measured human approval')
                    await engine.flush()
                after=engine.result(event.event_id)
                assert after['status'] in ('completed','draft_ready')
                assert all((effect['remote_id'] or '').startswith('fixture:') for effect in after['effects'])
                runs.append({'type':event.type,'input':event.payload,'before':before,'after':after})
            blocked=Event.model_validate({**examples[1],'event_id':'reviewer-no-consent'})
            engine.ingest(blocked);await engine.process(blocked.event_id);await engine.flush()
            failure=engine.result(blocked.event_id);assert failure['status']=='blocked' and not failure['effects']
            replay=Event.model_validate({**examples[0],'event_id':'reviewer-cart.abandoned'})
            receipts_before=engine.result(replay.event_id)['effects'];ack=engine.ingest(replay);await engine.process(replay.event_id);await engine.flush()
            receipts_after=engine.result(replay.event_id)['effects'];assert ack['duplicate'] and receipts_before==receipts_after
            metrics=engine.metrics();metrics['mean_approval_seconds']=None
            return {'built_at':now(),'mode':'fixture','external_api_calls':0,'method':'Actual local Engine execution, deterministic fixture providers, isolated temporary database. Recorded snapshots; browser interactions do not execute the backend. Fixture approval was automated, not a human-latency measurement.',
                'workflows':runs,'failure':failure,'duplicate':{'ack':ack,'recorded_effects_before':len(receipts_before),'recorded_effects_after':len(receipts_after)},
                'fixture_metrics':metrics,
                'reliability':json.loads((ROOT/'evidence/reliability.json').read_text()),
                'live_model':json.loads((ROOT/'evidence/live-model-smoke.json').read_text()),
                'live_product':json.loads((ROOT/'evidence/shopify-live-delivery.json').read_text())}
        finally:
            await provider.close();db.engine.dispose()

def main(output):
    (ROOT/'runtime').mkdir(exist_ok=True)
    output=Path(output).resolve();output.mkdir(parents=True,exist_ok=True)
    data=asyncio.run(snapshot())
    for file in (ROOT/'review').iterdir():
        if file.is_file() and file.suffix in ('.html','.css','.js'):shutil.copyfile(file,output/file.name)
    (output/'snapshot.json').write_text(json.dumps(data,indent=2)+'\n')
    assets=output/'assets';assets.mkdir(exist_ok=True)
    for name in ['live-demo.mp4','dashboard.png','n8n-cart.jpg','shopify-delivery-200.jpg','shopify-live-result.jpg','live-action-receipts.jpg']:
        shutil.copyfile(ROOT/'evidence'/name,assets/name)
    walkthrough=ROOT/'evidence/reviewer-walkthrough.mp4'
    if walkthrough.exists():shutil.copyfile(walkthrough,assets/walkthrough.name)
    print(json.dumps({'output':str(output),'workflows':len(data['workflows']),'fixture_external_api_calls':0,'blocked_without_effects':True,'duplicate_receipts_unchanged':True}))

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',default=str(ROOT/'runtime/reviewer-site'));main(parser.parse_args().output)
