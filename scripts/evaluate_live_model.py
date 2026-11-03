"""Small real-API schema/policy smoke check. Does not dispatch external actions."""
import asyncio,json,sys,os,uuid
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backend.config import ROOT,Settings
from backend.db import DB,now
from backend.providers import Providers
from backend.engine import Engine
from backend.models import Event

async def main():
    sample_id=uuid.uuid4().hex
    settings=Settings(mode='live',external_writes_enabled=False,token='model-smoke-only-isolated-test-token',database_url='sqlite:///'+str(ROOT/f'runtime/model-smoke-{sample_id}.db'))
    db=DB(settings.database_url);provider=Providers(settings,db);engine=Engine(settings,db,provider)
    events=json.loads((ROOT/'data/events.json').read_text());results=[]
    for index in [0,2,3,4,5,6]:
        # Import synthetic records through the actual processor. It calculates stock,
        # segments and briefing context and removes contact fields before model calls.
        event=Event.model_validate({**events[index],'event_id':f'model-smoke-{sample_id}-{index}','source':'import'})
        engine.ingest(event);await engine.process(event.event_id);result=engine.result(event.event_id)
        if result['status'] in ('awaiting_approval','actions_pending','draft_ready'):
            results.append({'workflow':event.type,'status':'schema_and_policy_passed','processor_status':result['status'],'output':result['result']})
        else:results.append({'workflow':event.type,'status':'failed_closed','category':result.get('error') or result.get('reason') or result['status']})
    report={'measured_at':now(),'sample_id':sample_id,'provider':settings.llm_provider,'model':os.getenv(settings.llm_provider.upper()+'_MODEL'),'synthetic_inputs':True,'external_actions_dispatched':0,'results':results,'metrics':{'passed':sum(x['status']=='schema_and_policy_passed' for x in results),'total':len(results)},
        'limits':'Small real-API smoke sample. Does not establish classification quality, factual accuracy of narrative summaries, production reliability or any third-party integration. No customer messages, Slack posts, CRM writes or Sheet appends.'}
    (ROOT/'evidence/live-model-smoke.json').write_text(json.dumps(report,indent=2));await provider.close();print(json.dumps({'passed':report['metrics']['passed'],'total':len(results),'results':[{k:v for k,v in x.items() if k!='output'} for x in results]}))
if __name__=='__main__':asyncio.run(main())
