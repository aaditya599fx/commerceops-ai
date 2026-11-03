import asyncio, base64, copy, hashlib, hmac, json, time
from pathlib import Path
from urllib.parse import urlencode
import httpx, pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, func
from backend.config import Settings, ROOT
from backend.db import DB, Run, Effect, Fact, dump
from backend.engine import Engine, Conflict
from backend.models import Event
from backend.providers import Providers, ProviderError, fixture, policy, request
from backend.app import create_app

TOKEN='test-only-token-not-a-real-secret-123456789'

def make(tmp_path,mode='fixture',client=None):
    cfg=Settings(mode=mode,llm_provider='openai',token=TOKEN,database_url='sqlite:///'+str(tmp_path/'test.db'))
    db=DB(cfg.database_url); p=Providers(cfg,db,client)
    return cfg,db,p,Engine(cfg,db,p)

def sample(index=0,id='test-1'):
    e=json.loads((ROOT/'data/events.json').read_text())[index]; e['event_id']=id
    return Event.model_validate(e)

def run(coro): return asyncio.run(coro)

def test_duplicate_does_not_repeat_side_effect(tmp_path):
    _,db,p,e=make(tmp_path)
    async def scenario():
        event=sample(); e.ingest(event); await e.process(event.event_id); await e.flush()
        assert e.result(event.event_id)['status']=='awaiting_approval'
        assert [x.kind for x in get_effects(db)]==['slack']
        await e.decide(event.event_id,'approve','tester','Reviewed'); await e.flush()
        assert e.result(event.event_id)['status']=='completed'
        assert e.ingest(event)['duplicate']
        await e.process(event.event_id); await e.decide(event.event_id,'approve','tester','Repeated click'); await e.flush()
        assert len([x for x in get_effects(db) if x.kind=='hubspot'])==1
        assert e.metrics()['duplicate_effect_keys']==0
        await p.close()
    run(scenario())

def get_effects(db):
    with db.session() as s:return list(s.scalars(select(Effect)))

@pytest.mark.parametrize('change,reason',[({'consent':False},'no_marketing_consent'),({'recent_purchase':True},'recent_purchase'),
    ({'value':20.0,'items':[{'sku':'x','title':'Tote','price':20.0,'quantity':1}]},'below_value_threshold')])
def test_policy_blocks_before_model(tmp_path,change,reason):
    _,db,p,e=make(tmp_path); event=sample(); event.payload.update(change)
    async def scenario():
        e.ingest(event); await e.process(event.event_id); await e.flush()
        r=e.result(event.event_id); assert r['status']=='blocked'; assert r['reason']==reason
        assert not get_effects(db); assert e.metrics()['schema_outputs']==0
        await p.close()
    run(scenario())

def test_reject_and_cooldown(tmp_path):
    _,db,p,e=make(tmp_path)
    async def scenario():
        first=sample(); e.ingest(first); await e.process(first.event_id)
        second=sample(id='second'); e.ingest(second); await e.process(second.event_id)
        assert e.result('second')['reason']=='recovery_cooldown'
        await e.decide(first.event_id,'reject','tester','Not suitable'); await e.flush()
        assert e.result(first.event_id)['status']=='rejected'
        assert not [x for x in get_effects(db) if x.kind=='hubspot']
        await p.close()
    run(scenario())

def test_conflicting_payload_same_id(tmp_path):
    _,_,_,e=make(tmp_path); event=sample(); e.ingest(event)
    changed=event.model_copy(deep=True); changed.payload['consent']=False
    with pytest.raises(Conflict): e.ingest(changed)

def test_consent_revocation_at_approval(tmp_path):
    _,db,p,e=make(tmp_path)
    async def scenario():
        event=sample(); e.ingest(event); await e.process(event.event_id)
        with db.session.begin() as s: s.add(Fact(key='customer:'+event.payload['customer_id'],kind='customer',source='import',value=dump({'consent':False})))
        await e.decide(event.event_id,'approve','tester','Reviewed'); await e.flush()
        assert e.result(event.event_id)['status']=='blocked'
        assert not [x for x in get_effects(db) if x.kind=='hubspot']
        await p.close()
    run(scenario())

@pytest.mark.parametrize('index,status',[(2,'completed'),(3,'completed'),(4,'draft_ready'),(5,'completed'),(6,'completed')])
def test_other_workflows(tmp_path,index,status):
    _,_,p,e=make(tmp_path)
    async def scenario():
        event=sample(index); e.ingest(event); await e.process(event.event_id); await e.flush()
        r=e.result(event.event_id); assert r['status']==status
        if index==2: assert r['result']['days_of_cover']==2; assert r['result']['low_stock']
        if index==3: assert r['result']['sentiment']=='negative'; assert r['result']['urgency']=='high'
        if index==4: assert r['result']['json_ld']['name']==event.payload['title']
        await p.close()
    run(scenario())

def test_zero_sales_velocity(tmp_path):
    _,_,p,e=make(tmp_path); event=sample(2); event.payload['daily_units']=0.0
    async def scenario():
        e.ingest(event); await e.process(event.event_id); assert e.result(event.event_id)['result']['days_of_cover'] is None; await p.close()
    run(scenario())

def test_currency_totals(tmp_path):
    _,db,p,e=make(tmp_path)
    with db.session.begin() as s:
        for i,(currency,total) in enumerate([('USD',10.0),('USD',30.0),('INR',800.0)]):
            s.add(Fact(key=str(i),kind='order',source='synthetic',value=dump({'date':'2026-11-03','currency':currency,'total':total,'refunds':0})))
    m=e.business_metrics('2026-11-03'); assert m['by_currency']['USD']['average_order_value']==20
    assert m['by_currency']['INR']['order_value_total']==800; assert len(m['source_records'])==3
    run(p.close())

@pytest.mark.parametrize('bad',[{'message_body':'Buy now for 50% discount!'}, {'requires_human_approval':False}, {'risk_flags':['invented_claim']}])
def test_unsafe_or_invalid_draft(tmp_path,bad,monkeypatch):
    _,_,p,e=make(tmp_path); original=fixture('cart.abandoned',sample().payload); original.update(bad)
    monkeypatch.setattr('backend.providers.fixture',lambda *_:original)
    async def scenario():
        event=sample(); e.ingest(event); await e.process(event.event_id)
        assert e.result(event.event_id)['status']=='dead_letter'
        assert not get_effects(e.db)
        await p.close()
    run(scenario())

def test_model_invalid_retry_once(tmp_path,monkeypatch):
    monkeypatch.setenv('OPENAI_API_KEY','test-key')
    calls=[]
    def handler(req):
        calls.append(req)
        body=json.loads(req.content); assert body['text']['format']['strict'] is True
        assert 'email' not in json.loads(body['input'])['data']
        return httpx.Response(200,json={'status':'completed','output':[{'content':[{'type':'output_text','text':'{"wrong":true}'}]}]})
    _,_,p,e=make(tmp_path,'live',httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    async def scenario():
        ev=sample(); ev.source='import'; e.ingest(ev); await e.process(ev.event_id)
        assert len(calls)==2; assert e.result(ev.event_id)['error']=='invalid_model_output'
        assert e.metrics()['schema_pass_rate']==0; await p.close()
    run(scenario())

@pytest.mark.parametrize('status',[429,503,401])
def test_read_retry_budget(status):
    calls=[]
    def handler(req): calls.append(req); return httpx.Response(status,headers={'retry-after':'0'})
    async def scenario():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            with pytest.raises(ProviderError): await request(client,'GET','https://example.test',safe_retry=True)
    run(scenario()); assert len(calls)==(1 if status==401 else 3)

def test_ambiguous_write_is_not_retried(tmp_path):
    calls=[]
    def handler(req): calls.append(req); raise httpx.ReadTimeout('test timeout')
    async def scenario():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            with pytest.raises(ProviderError): await request(client,'POST','https://example.test',json={})
    run(scenario()); assert len(calls)==1

def test_outbox_failure_is_held_and_not_replayed(tmp_path,monkeypatch):
    _,db,p,e=make(tmp_path); calls=[]
    async def fail(kind,data): calls.append(kind); raise ProviderError('network_or_timeout')
    monkeypatch.setattr(p,'effect',fail)
    async def scenario():
        ev=sample(); e.ingest(ev); await e.process(ev.event_id); await e.flush(); await e.flush()
        assert e.result(ev.event_id)['status']=='held'; assert calls==['slack']
        with pytest.raises(Conflict): e.replay(ev.event_id)
        await p.close()
    run(scenario())

def test_restart_recovery(tmp_path):
    _,db,p,e=make(tmp_path); event=sample(); e.ingest(event)
    with db.session.begin() as s:
        s.get(Run,event.event_id).status='processing'
        s.add(Effect(event_id=event.event_id,kind='slack',status='sending',payload='{}'))
    e.recover(); r=e.result(event.event_id)
    assert r['status']=='held'; assert r['effects'][0]['status']=='uncertain'; run(p.close())

def test_api_auth_validation_and_source_protection(tmp_path,monkeypatch):
    monkeypatch.setenv('WORKER_ENABLED','false'); cfg,_,_,_=make(tmp_path)
    with TestClient(create_app(cfg)) as c:
        assert c.get('/api/runs').status_code==401
        h={'Authorization':'Bearer '+TOKEN}; ev=sample().model_dump(mode='json')
        assert c.post('/api/events',headers=h,json={}).status_code==422
        ev['payload']['consent']='true'; assert c.post('/api/events',headers=h,json=ev).status_code==422
        ev=sample().model_dump(mode='json'); ev['source']='shopify'
        assert c.post('/api/events',headers=h,json=ev).status_code==403
        assert c.post('/webhooks/shopify',json={}).status_code==401
        assert c.post('/webhooks/slack/actions',data={}).status_code==401

def test_signed_shopify_order(tmp_path,monkeypatch):
    monkeypatch.setenv('WORKER_ENABLED','false'); monkeypatch.setenv('SHOPIFY_WEBHOOK_SECRET','fixture-secret'); monkeypatch.setenv('SHOPIFY_SHOP','fixture.myshopify.com')
    cfg,_,_,_=make(tmp_path)
    with TestClient(create_app(cfg)) as c:
        raw=json.dumps({'id':123,'created_at':'2026-11-03T00:00:00Z','total_price':'80.00','currency':'USD'}).encode()
        sig=base64.b64encode(hmac.new(b'fixture-secret',raw,hashlib.sha256).digest()).decode()
        h={'X-Shopify-Hmac-Sha256':sig,'X-Shopify-Shop-Domain':'fixture.myshopify.com','X-Shopify-Topic':'orders/create','X-Shopify-Webhook-Id':'123'}
        assert c.post('/webhooks/shopify',headers=h,content=raw).status_code==200
        assert c.post('/webhooks/shopify',headers=h,content=raw+b' ').status_code==401

def test_slack_authorization_and_replay_timestamp(tmp_path,monkeypatch):
    monkeypatch.setenv('WORKER_ENABLED','false'); monkeypatch.setenv('SLACK_SIGNING_SECRET','fixture-secret'); monkeypatch.setenv('SLACK_APPROVER_IDS','U123')
    cfg,_,_,_=make(tmp_path)
    with TestClient(create_app(cfg)) as c:
        headers={'Authorization':'Bearer '+TOKEN}; ev=sample().model_dump(mode='json')
        c.post('/api/events',headers=headers,json=ev); c.post('/api/runs/test-1/process',headers=headers)
        def submit(actor,ts):
            raw=urlencode({'payload':json.dumps({'user':{'id':actor},'actions':[{'action_id':'approve','value':'test-1'}]})}).encode()
            sig='v0='+hmac.new(b'fixture-secret',b'v0:'+ts.encode()+b':'+raw,hashlib.sha256).hexdigest()
            return c.post('/webhooks/slack/actions',content=raw,headers={'X-Slack-Signature':sig,'X-Slack-Request-Timestamp':ts})
        assert submit('BAD',str(int(time.time()))).status_code==403
        assert submit('U123','100').status_code==401
        assert submit('U123',str(int(time.time()))).status_code==200
        assert submit('U123',str(int(time.time()))).status_code==200

def test_concurrent_approvals_create_one_crm_action(tmp_path):
    _,db,p,e=make(tmp_path)
    async def scenario():
        event=sample();e.ingest(event);await e.process(event.event_id)
        results=await asyncio.gather(e.decide(event.event_id,'approve','reviewer-1','Checked'),e.decide(event.event_id,'approve','reviewer-2','Checked'))
        await e.flush();assert sum(not r['duplicate'] for r in results)==1
        assert len([x for x in get_effects(db) if x.kind=='hubspot'])==1
        await p.close()
    run(scenario())

def test_manual_replay_limit(tmp_path,monkeypatch):
    _,_,p,e=make(tmp_path)
    async def fail(*_):raise ProviderError('model_unavailable')
    monkeypatch.setattr(p,'generate',fail)
    async def scenario():
        event=sample();e.ingest(event)
        for i in range(3):
            await e.process(event.event_id)
            assert e.result(event.event_id)['status']=='dead_letter'
            if i<2:e.replay(event.event_id)
        with pytest.raises(Conflict):e.replay(event.event_id)
        assert e.result(event.event_id)['attempts']==3
        await p.close()
    run(scenario())

def test_live_mode_does_not_silently_use_fixtures(tmp_path,monkeypatch):
    monkeypatch.delenv('OPENAI_API_KEY',raising=False)
    _,_,p,e=make(tmp_path,'live')
    async def scenario():
        event=sample()
        with pytest.raises(Conflict):e.ingest(event)
        event.source='import';e.ingest(event);await e.process(event.event_id)
        assert e.result(event.event_id)['error']=='openai_not_configured'
        assert not get_effects(e.db)
        await p.close()
    run(scenario())

def test_customer_currency_is_not_converted_implicitly(tmp_path):
    _,_,p,e=make(tmp_path);event=sample(5);event.payload.update({'currency':'INR','total_spend':1000.0,'orders':2,'days_since_order':3})
    async def scenario():
        e.ingest(event);await e.process(event.event_id)
        assert e.result(event.event_id)['result']['segment']=='repeat';await p.close()
    run(scenario())

def test_daily_brief_schedule_is_idempotent(tmp_path,monkeypatch):
    monkeypatch.setenv('WORKER_ENABLED','false');cfg,_,_,_=make(tmp_path)
    with TestClient(create_app(cfg)) as c:
        h={'Authorization':'Bearer '+TOKEN}
        first=c.post('/api/schedules/brief',headers=h);second=c.post('/api/schedules/brief',headers=h)
        assert first.status_code==200;assert second.status_code==200;assert second.json()['duplicate']

def test_shopify_client_credentials_exchange_and_cache(tmp_path,monkeypatch):
    from backend.shopify import Shopify
    monkeypatch.setenv('SHOPIFY_SHOP','own-test.myshopify.com');monkeypatch.setenv('SHOPIFY_CLIENT_ID','fixture-client');monkeypatch.setenv('SHOPIFY_CLIENT_SECRET','fixture-client-secret');monkeypatch.delenv('SHOPIFY_ACCESS_TOKEN',raising=False)
    Shopify._tokens.clear();seen=[]
    def handler(req):
        seen.append(req.url.path)
        if req.url.path.endswith('/oauth/access_token'):
            assert b'grant_type=client_credentials' in req.content
            return httpx.Response(200,json={'access_token':'fixture-temporary-token','expires_in':86399})
        assert req.headers['X-Shopify-Access-Token']=='fixture-temporary-token'
        return httpx.Response(200,json={'data':{'shop':{'id':'test','name':'Test','myshopifyDomain':'own-test.myshopify.com'}}})
    cfg,db,p,e=make(tmp_path,client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    async def scenario():
        first=await Shopify(p.client,db,e).check();second=await Shopify(p.client,db,e).check()
        assert first['status']=='verified_read';assert second['status']=='verified_read'
        assert seen.count('/admin/oauth/access_token')==1
        await p.close()
    run(scenario());Shopify._tokens.clear()

def test_slack_ack_does_not_wait_for_processing_lock(tmp_path,monkeypatch):
    monkeypatch.setenv('WORKER_ENABLED','false');monkeypatch.setenv('SLACK_SIGNING_SECRET','fixture-secret');monkeypatch.setenv('SLACK_APPROVER_IDS','U123')
    cfg,_,_,_=make(tmp_path)
    with TestClient(create_app(cfg)) as c:
        h={'Authorization':'Bearer '+TOKEN};ev=sample().model_dump(mode='json')
        c.post('/api/events',headers=h,json=ev);c.post('/api/runs/test-1/process',headers=h)
        engine=c.app.state.engine
        run(engine.lock.acquire())
        try:
            raw=urlencode({'payload':json.dumps({'user':{'id':'U123'},'actions':[{'action_id':'approve','value':'test-1'}]})}).encode()
            ts=str(int(time.time()));sig='v0='+hmac.new(b'fixture-secret',b'v0:'+ts.encode()+b':'+raw,hashlib.sha256).hexdigest()
            start=time.perf_counter();response=c.post('/webhooks/slack/actions',content=raw,headers={'X-Slack-Signature':sig,'X-Slack-Request-Timestamp':ts})
            assert response.status_code==200;assert time.perf_counter()-start<1
            assert engine.result('test-1')['status']=='awaiting_approval'
        finally:engine.lock.release()
        c.post('/api/worker/tick',headers=h)
        assert engine.result('test-1')['status']=='completed'
        assert len([x for x in get_effects(engine.db) if x.kind=='hubspot'])==1

def test_queued_slack_decision_survives_restart_and_blocks_conflict(tmp_path):
    cfg,db,p,e=make(tmp_path)
    async def scenario():
        ev=sample();e.ingest(ev);await e.process(ev.event_id)
        assert not e.queue_decision(ev.event_id,'approve','slack:U123','Checked')['duplicate']
        assert e.queue_decision(ev.event_id,'approve','slack:U123','Repeated')['duplicate']
        with pytest.raises(Conflict):e.queue_decision(ev.event_id,'reject','slack:U123','Changed mind')
        other=Engine(cfg,db,p);other.recover();await other.drain_decisions();await other.flush()
        assert other.result(ev.event_id)['status']=='completed';await p.close()
    run(scenario())

def test_live_outbox_waits_for_explicit_enablement(tmp_path,monkeypatch):
    cfg,db,p,e=make(tmp_path,'live');calls=[]
    with db.session.begin() as s:
        s.add(Effect(event_id='test',kind='slack',payload='{}'))
    async def effect(*args):calls.append(args);return 'remote-id'
    monkeypatch.setattr(p,'effect',effect)
    async def scenario():
        await e.flush();assert not calls;assert get_effects(db)[0].status=='pending';await p.close()
    run(scenario())

def test_webhook_replay_and_stale_update(tmp_path):
    from backend.shopify import Shopify
    _,db,p,e=make(tmp_path);shop=Shopify(p.client,db,e)
    order={'id':1,'currency':'USD','created_at':'2026-11-03T00:00:00Z','updated_at':'2026-11-03T02:00:00Z','total_price':'80.00'}
    assert shop.order_webhook('delivery-1',order)['duplicate'] is False
    assert shop.order_webhook('delivery-1',order)['duplicate'] is True
    with pytest.raises(Conflict):shop.order_webhook('delivery-1',{**order,'total_price':'20.00'})
    stale={**order,'updated_at':'2026-11-03T01:00:00Z','total_price':'10.00'}
    assert shop.order_webhook('delivery-old',stale)['reason']=='stale_order_update'
    with db.session() as s:assert json.loads(s.get(Fact,'order:1').value)['total']==80
    run(p.close())

def test_connection_evidence_invalidated_after_key_change(monkeypatch):
    from backend.integrations import record_check,read_checks
    monkeypatch.setenv('OPENAI_API_KEY','fixture-key-a');record_check('openai','read','verified')
    assert read_checks()['openai']['read']['status']=='verified'
    monkeypatch.setenv('OPENAI_API_KEY','fixture-key-b');assert 'openai' not in read_checks()

def test_minimal_order_payload_does_not_invent_refunds(tmp_path):
    from backend.shopify import Shopify
    _,db,p,e=make(tmp_path);shop=Shopify(p.client,db,e)
    shop.order_webhook('minimal-order',{'id':7,'currency':'USD','created_at':'2026-11-03T00:00:00Z','total_price':'80.00'})
    metrics=e.business_metrics('2026-11-03')['by_currency']['USD']
    assert metrics['refunds'] is None;assert metrics['orders_without_refund_details']==1
    assert metrics['order_value_total']==80.0;run(p.close())

def test_webhook_setup_is_minimal_and_does_not_retry_creation(tmp_path,monkeypatch):
    from backend.shopify import Shopify
    _,db,p,e=make(tmp_path);shop=Shopify(p.client,db,e);calls=[]
    async def graphql(query,variables=None,**options):
        calls.append((query,variables,options))
        if 'webhookSubscriptions' in query:return {'webhookSubscriptions':{'nodes':[],'pageInfo':{'hasNextPage':False}}}
        assert options['safe_retry'] is False
        assert 'customer' not in variables['input']['includeFields']
        return {'webhookSubscriptionCreate':{'webhookSubscription':{'id':'id-'+variables['topic']},'userErrors':[]}}
    monkeypatch.setattr(shop,'graphql',graphql)
    async def scenario():
        plan=await shop.configure_webhooks('https://example.test');assert all(x['status']=='planned' for x in plan['subscriptions'])
        assert len(calls)==1
        result=await shop.configure_webhooks('https://example.test',apply=True)
        assert len(result['subscriptions'])==3;assert result['delivery_verified'] is False
        await p.close()
    run(scenario())

def test_approval_latency_uses_click_receipt_not_worker_time(tmp_path):
    from backend.db import DecisionJob
    _,db,p,e=make(tmp_path)
    async def scenario():
        ev=sample();e.ingest(ev);await e.process(ev.event_id);e.queue_decision(ev.event_id,'approve','slack:U123','Reviewed')
        with db.session.begin() as s:s.get(DecisionJob,ev.event_id).created='2026-11-03T01:00:00+00:00'
        await e.drain_decisions()
        assert e.result(ev.event_id)['decision_at']=='2026-11-03T01:00:00+00:00';await p.close()
    run(scenario())

def test_pending_slack_rejection_cannot_be_overridden_by_dashboard(tmp_path):
    _,_,p,e=make(tmp_path)
    async def scenario():
        ev=sample();e.ingest(ev);await e.process(ev.event_id);e.queue_decision(ev.event_id,'reject','slack:U123','Not approved')
        with pytest.raises(Conflict):await e.decide(ev.event_id,'approve','local_operator','Different reviewer')
        await e.drain_decisions();assert e.result(ev.event_id)['status']=='rejected';await p.close()
    run(scenario())

@pytest.mark.parametrize('amount',['NaN','Infinity','-1'])
def test_order_callback_rejects_invalid_money(tmp_path,amount):
    from backend.shopify import Shopify
    _,db,p,e=make(tmp_path);shop=Shopify(p.client,db,e)
    with pytest.raises(ValueError):shop.order_webhook('invalid-money',{'id':1,'currency':'USD','created_at':'2026-11-03T00:00:00Z','total_price':amount})
    with db.session() as s:assert s.get(Fact,'order:1') is None
    run(p.close())
