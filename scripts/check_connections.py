"""Read-only connection probes. No messages/tasks/rows are created. Never prints tokens."""
import asyncio,json,os,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import httpx
from backend.config import Settings,ROOT
from backend.db import DB, now
from backend.providers import Providers,ProviderError,request
from backend.engine import Engine
from backend.shopify import Shopify
from backend.integrations import record_check

async def main():
    cfg=Settings();db=DB(cfg.database_url);p=Providers(cfg,db);engine=Engine(cfg,db,p)
    results={}; fields={cfg.llm_provider:[cfg.llm_provider.upper()+'_API_KEY'],'shopify':['SHOPIFY_SHOP'],
        'slack':['SLACK_BOT_TOKEN'],'hubspot':['HUBSPOT_ACCESS_TOKEN'],'sheets':['GOOGLE_SERVICE_ACCOUNT_FILE','GOOGLE_SPREADSHEET_ID']}
    for service,required in fields.items():
        if not all(os.getenv(k) for k in required) or (service=='shopify' and not (os.getenv('SHOPIFY_ACCESS_TOKEN') or (os.getenv('SHOPIFY_CLIENT_ID') and os.getenv('SHOPIFY_CLIENT_SECRET')))):results[service]={'status':'not_configured'};continue
        try:
            if service=='shopify':
                results[service]=await Shopify(p.client,db,engine).check();record_check(service,'read','verified');continue
            if service=='openai':
                r=await request(p.client,'GET','https://api.openai.com/v1/models/'+os.getenv('OPENAI_MODEL','gpt-4.1-mini'),safe_retry=True,headers={'Authorization':'Bearer '+os.getenv('OPENAI_API_KEY')})
            elif service=='gemini':
                r=await request(p.client,'GET','https://generativelanguage.googleapis.com/v1beta/models/'+p.gemini_model(),safe_retry=True,headers={'x-goog-api-key':os.getenv('GEMINI_API_KEY')})
            elif service=='slack':
                r=await request(p.client,'POST','https://slack.com/api/auth.test',safe_retry=True,headers={'Authorization':'Bearer '+os.getenv('SLACK_BOT_TOKEN')})
                if not r.json().get('ok'):raise ProviderError('slack_auth_failed')
            elif service=='hubspot':
                r=await request(p.client,'GET','https://api.hubapi.com/crm/v3/objects/tasks',safe_retry=True,params={'limit':1},headers={'Authorization':'Bearer '+os.getenv('HUBSPOT_ACCESS_TOKEN')})
            else:
                from google.oauth2 import service_account
                from google.auth.transport.requests import Request
                c=service_account.Credentials.from_service_account_file(os.getenv('GOOGLE_SERVICE_ACCOUNT_FILE'),scopes=['https://www.googleapis.com/auth/spreadsheets.readonly'])
                await asyncio.to_thread(c.refresh,Request())
                r=await request(p.client,'GET','https://sheets.googleapis.com/v4/spreadsheets/'+os.getenv('GOOGLE_SPREADSHEET_ID'),safe_retry=True,params={'fields':'spreadsheetId'},headers={'Authorization':'Bearer '+c.token})
            results[service]={'status':'verified_read','verified_at':now(),'note':'Read authentication only; end-to-end workflow unverified'}
            record_check(service,'read','verified')
        except Exception as exc:
            category=exc.category if isinstance(exc,ProviderError) else 'configuration_or_adapter_error'
            results[service]={'status':'failed','category':category};record_check(service,'read','failed',category)
    report={'checked_at':now(),'probes':results,'note':'Read probes do not demonstrate writes or webhook delivery.'}
    (ROOT/'runtime/connections.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2));await p.close()
if __name__=='__main__':asyncio.run(main())
