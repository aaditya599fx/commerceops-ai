import asyncio, hashlib, hmac, json, os, time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from urllib.parse import parse_qs
from pathlib import Path
from fastapi import FastAPI, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy import select, func
from .config import Settings, ROOT
from .db import DB, Run, Fact, Audit, Effect, dump, unpack, now
from .models import Event, Decision
from .providers import Providers, ProviderError
from .engine import Engine, Conflict
from .shopify import Shopify

bearer=HTTPBearer(auto_error=False)

def create_app(settings=None,providers=None):
    settings=settings or Settings()
    db=DB(settings.database_url); provider=providers or Providers(settings,db)
    engine=Engine(settings,db,provider); shopify=Shopify(provider.client,db,engine)

    async def tick():
        with db.session() as s:
            ids=list(s.scalars(select(Run.id).where(Run.status=='queued').order_by(Run.created).limit(20)))
        for id in ids: await engine.process(id)
        await engine.flush()
        return {'processed':len(ids)}

    @asynccontextmanager
    async def lifespan(app):
        engine.recover()
        # Optional single-process worker. In n8n mode, the exported scheduled dispatcher calls /worker/tick.
        async def work():
            while True:
                try: await tick()
                except Exception: pass  # durable events remain inspectable; health reports queue depth
                await asyncio.sleep(0.5)
        task=asyncio.create_task(work()) if os.getenv('WORKER_ENABLED','true')=='true' else None
        yield
        if task:
            task.cancel()
            try: await task
            except asyncio.CancelledError: pass
        await provider.close()
    app=FastAPI(title='CommerceOps AI',version='0.1.0',lifespan=lifespan)
    app.state.engine=engine; app.state.db=db; app.state.providers=provider; app.state.tick=tick

    def auth(credentials:HTTPAuthorizationCredentials|None=Depends(bearer)):
        if not credentials or not hmac.compare_digest(credentials.credentials,settings.token):
            raise HTTPException(401,'Valid bearer token required')
        return 'local_operator'

    @app.exception_handler(Conflict)
    async def conflict(_,exc): return JSONResponse({'detail':str(exc)},status_code=409)
    @app.exception_handler(ProviderError)
    async def provider_error(_,exc): return JSONResponse({'detail':exc.category},status_code=503)

    @app.middleware('http')
    async def safety(request,call_next):
        length=request.headers.get('content-length','0')
        if length.isdigit() and int(length)>1000000: return JSONResponse({'detail':'Payload too large'},413)
        response=await call_next(request)
        response.headers['Cache-Control']='no-store'
        response.headers['X-Content-Type-Options']='nosniff'
        response.headers['Referrer-Policy']='no-referrer'
        response.headers['X-Frame-Options']='DENY'
        return response

    @app.get('/',response_class=HTMLResponse)
    async def dashboard(): return (ROOT/'backend/dashboard.html').read_text()
    @app.get('/health')
    async def health():
        with db.session() as s: s.scalar(select(func.count()).select_from(Run))
        return {'status':'ok','mode':settings.mode,'version':'0.1.0'}
    @app.get('/api/status',dependencies=[Depends(auth)])
    async def status():
        fields={'openai':['OPENAI_API_KEY'],'shopify':['SHOPIFY_SHOP','SHOPIFY_WEBHOOK_SECRET'],
            'slack':['SLACK_BOT_TOKEN','SLACK_SIGNING_SECRET','SLACK_CHANNEL_ID','SLACK_APPROVER_IDS'],
            'hubspot':['HUBSPOT_ACCESS_TOKEN'],'sheets':['GOOGLE_SERVICE_ACCOUNT_FILE','GOOGLE_SPREADSHEET_ID']}
        return {'mode':settings.mode,'demo_transport':'n8n' if os.getenv('USE_N8N_FOR_DEMO','false')=='true' else 'python','integrations':{k:{'configured':all(os.getenv(x) for x in v) and (k!='shopify' or bool(os.getenv('SHOPIFY_ACCESS_TOKEN') or (os.getenv('SHOPIFY_CLIENT_ID') and os.getenv('SHOPIFY_CLIENT_SECRET')))),'verified':False} for k,v in fields.items()},
            'note':'Configured means fields present. Verification requires a live API probe and a completed workflow.'}
    @app.get('/api/metrics',dependencies=[Depends(auth)])
    async def metrics(): return engine.metrics()
    @app.get('/api/runs',dependencies=[Depends(auth)])
    async def runs():
        with db.session() as s:
            return [{'id':r.id,'type':r.type,'source':r.source,'status':r.status,'created':r.created,'reason':r.reason,'error':r.error}
                    for r in s.scalars(select(Run).order_by(Run.created.desc()).limit(200))]
    @app.get('/api/runs/{id}',dependencies=[Depends(auth)])
    async def run(id:str):
        result=engine.result(id)
        if not result: raise HTTPException(404,'Event not found')
        return result
    @app.post('/api/demo/events',status_code=202,dependencies=[Depends(auth)])
    async def demo_via_n8n(event:Event):
        if settings.mode!='fixture' or event.source!='synthetic': raise HTTPException(403,'Only fixture events are allowed here')
        from .providers import request as provider_request
        slug={'cart.abandoned':'cart','inventory.updated':'inventory','review.created':'review','product.created':'product','customer.updated':'customer','brief.requested':'brief'}[event.type]
        url=os.getenv('N8N_BASE_URL','http://localhost:5678').rstrip('/')+'/webhook/commerceops/'+slug
        response=await provider_request(provider.client,'POST',url,headers={'Authorization':'Bearer '+settings.token},json=event.model_dump(mode='json'))
        return response.json()
    @app.post('/api/events',status_code=202,dependencies=[Depends(auth)])
    async def ingest(event:Event):
        if event.source=='shopify': raise HTTPException(403,'Shopify source requires verified webhook ingress')
        return engine.ingest(event)
    @app.post('/api/runs/{id}/process',dependencies=[Depends(auth)])
    async def process(id:str):
        await engine.process(id)
        result=engine.result(id)
        if not result: raise HTTPException(404,'Event not found')
        return result
    @app.post('/api/actions/dispatch',dependencies=[Depends(auth)])
    async def flush(): await engine.flush(); return {'status':'dispatched'}
    @app.post('/api/worker/tick',dependencies=[Depends(auth)])
    async def worker(): return await tick()
    @app.post('/api/runs/{id}/decision')
    async def decide(id:str,decision:Decision,actor=Depends(auth)):
        return await engine.decide(id,decision.decision,actor,decision.reason)
    @app.post('/api/runs/{id}/replay',dependencies=[Depends(auth)])
    async def replay(id:str): return engine.replay(id)
    @app.post('/api/seed',dependencies=[Depends(auth)])
    async def seed():
        if settings.mode!='fixture': raise HTTPException(403,'Synthetic seed is disabled in live mode')
        dataset=json.loads((ROOT/'data/dataset.json').read_text())
        with db.session.begin() as s:
            for p in dataset['orders']:
                key='order:'+p['id']
                if not s.get(Fact,key): s.add(Fact(key=key,kind='order',value=dump(p),source='synthetic'))
        return {'orders':len(dataset['orders']),'source':'synthetic'}
    @app.get('/api/samples',dependencies=[Depends(auth)])
    async def samples(): return json.loads((ROOT/'data/events.json').read_text())
    @app.post('/api/schedules/brief',dependencies=[Depends(auth)])
    async def scheduled_brief():
        from zoneinfo import ZoneInfo
        date=datetime.now(ZoneInfo('Asia/Kolkata')).date().isoformat()
        source='synthetic' if settings.mode=='fixture' else 'import'
        event=Event.model_validate({'event_id':'daily-brief:'+date,'type':'brief.requested','timestamp':date+'T03:30:00Z',
            'source':source,'payload':{'date':date}})
        accepted=engine.ingest(event)
        await engine.process(event.event_id); await engine.flush()
        return accepted
    @app.post('/api/integrations/shopify/probe',dependencies=[Depends(auth)])
    async def probe(): return await shopify.check()

    @app.post('/api/integrations/shopify/poll',dependencies=[Depends(auth)])
    async def poll(): return await shopify.poll_abandoned()

    @app.post('/webhooks/shopify')
    async def shopify_webhook(request:Request):
        raw=await request.body()
        if len(raw)>1000000: raise HTTPException(413,'Payload too large')
        if not shopify.verify(raw,request.headers.get('x-shopify-hmac-sha256',''),request.headers.get('x-shopify-shop-domain','')):
            raise HTTPException(401,'Invalid Shopify signature or store')
        topic=request.headers.get('x-shopify-topic'); id=request.headers.get('x-shopify-webhook-id','')
        if not id: raise HTTPException(400,'Missing Shopify webhook ID')
        try: p=json.loads(raw)
        except ValueError: raise HTTPException(400,'Invalid JSON')
        if topic in ('orders/create','orders/updated'):
            try: return shopify.order_webhook(id,p)
            except (KeyError,ValueError,TypeError): raise HTTPException(422,'Invalid order payload')
        if topic=='products/create':
            event=Event.model_validate({'event_id':'shopify:'+id,'type':'product.created','timestamp':p['created_at'],'source':'shopify',
                'payload':{'product_id':str(p['id']),'title':p['title'],'description':p.get('body_html') or p['title'],'attributes':[],'verified_faqs':[]}})
            return engine.ingest(event)
        # Inventory levels lack sales velocity/lead time. Require explicit enriched import; never invent values.
        return {'status':'ignored','reason':'unsupported_topic_or_requires_enrichment'}

    @app.post('/webhooks/slack/actions')
    async def slack_actions(request:Request):
        raw=await request.body(); timestamp=request.headers.get('x-slack-request-timestamp','')
        secret=os.getenv('SLACK_SIGNING_SECRET','')
        try: fresh=abs(time.time()-int(timestamp))<=300
        except ValueError: fresh=False
        expected='v0='+hmac.new(secret.encode(),b'v0:'+timestamp.encode()+b':'+raw,hashlib.sha256).hexdigest()
        if not secret or not fresh or not hmac.compare_digest(expected,request.headers.get('x-slack-signature','')):
            raise HTTPException(401,'Invalid or expired Slack signature')
        try:
            p=json.loads(parse_qs(raw.decode())['payload'][0]); actor=p['user']['id']; action=p['actions'][0]
        except (KeyError,ValueError,IndexError): raise HTTPException(422,'Invalid Slack action')
        allowed={x.strip() for x in os.getenv('SLACK_APPROVER_IDS','').split(',') if x.strip()}
        if actor not in allowed: raise HTTPException(403,'Reviewer is not authorized')
        if action['action_id'] not in ('approve','reject'): raise HTTPException(422,'Unknown action')
        # No network requests in acknowledgement path; outbox worker performs follow-up writes.
        result=await engine.decide(action['value'],action['action_id'],'slack:'+actor,'Slack button decision')
        return {'text':'Decision recorded: '+result['status'],'replace_original':False}
    return app

app=create_app()
