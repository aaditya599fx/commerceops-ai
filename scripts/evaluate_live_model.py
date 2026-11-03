"""Small real-API schema/policy smoke check. Does not dispatch external actions."""
import asyncio,json,sys,os
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backend.config import ROOT,Settings
from backend.db import DB,now
from backend.providers import Providers,ProviderError

async def main():
    settings=Settings(mode='live',token='model-smoke-only-isolated-test-token',database_url='sqlite:///'+str(ROOT/'runtime/live-model-smoke.db'))
    db=DB(settings.database_url);provider=Providers(settings,db);events=json.loads((ROOT/'data/events.json').read_text());results=[]
    for index in [0,2,3,4,5,6]:
        event=events[index];payload={k:v for k,v in event['payload'].items() if k not in ('email','customer_id','cart_id')}
        if index==2:payload.update({'days_of_cover':2.0,'low_stock':True,'reorder_units':48})
        if index==5:payload.update({'segment':'first_time'})
        if index==6:payload={'date':event['payload']['date'],'by_currency':{},'source_records':[]}
        try:
            output=await provider.generate('live-model-'+str(index),event['type'],payload)
            results.append({'workflow':event['type'],'status':'schema_and_policy_passed','output':output})
        except ProviderError as exc:results.append({'workflow':event['type'],'status':'failed_closed','category':exc.category})
    report={'measured_at':now(),'provider':settings.llm_provider,'model':os.getenv(settings.llm_provider.upper()+'_MODEL'),'synthetic_inputs':True,'results':results,'metrics':{'passed':sum(x['status']=='schema_and_policy_passed' for x in results),'total':len(results)},
        'limits':'Small real-API smoke sample. Does not establish classification quality, factual accuracy of narrative summaries, production reliability or any third-party integration. No customer messages, Slack posts, CRM writes or Sheet appends.'}
    (ROOT/'evidence/live-model-smoke.json').write_text(json.dumps(report,indent=2));await provider.close();print(json.dumps({'passed':report['metrics']['passed'],'total':len(results),'results':[{k:v for k,v in x.items() if k!='output'} for x in results]}))
if __name__=='__main__':asyncio.run(main())
