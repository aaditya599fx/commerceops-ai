import asyncio,copy
import httpx

import pytest

from backend.config import Settings
from backend.providers import ProviderError
import scripts.renew_callback_urls as renewal

OLD='https://old-owned.example'
NEW='https://new-owned.example'

def setup(tmp_path,monkeypatch,extra_field=False,uncertain=False,healthy=True):
    state=[
        {'id':'1','topic':'ORDERS_CREATE','uri':OLD+'/webhooks/shopify','includeFields':['id','created_at','updated_at','currency','total_price']},
        {'id':'2','topic':'ORDERS_UPDATED','uri':OLD+'/webhooks/shopify','includeFields':['id','created_at','updated_at','currency','total_price']},
        {'id':'3','topic':'PRODUCTS_CREATE','uri':OLD+'/webhooks/shopify','includeFields':['id','title','body_html','created_at']}]
    if extra_field:state[-1]['includeFields'].append('email')
    writes=[]
    def health_probe(req):
        assert str(req.url)==NEW+'/health'
        assert 'authorization' not in req.headers
        return httpx.Response(200,json={'status':'ok','version':'0.1.0'} if healthy else {'status':'unavailable'})
    class Providers:
        def __init__(self,cfg,db):
            self.db=db
            self.client=httpx.AsyncClient(transport=httpx.MockTransport(health_probe))
        async def close(self):await self.client.aclose()
    class API:
        def __init__(self,*args):pass
        async def graphql(self,query,variables=None,*,safe_retry=True):
            if variables is None:return {'webhookSubscriptions':{'nodes':copy.deepcopy(state),'pageInfo':{'hasNextPage':False}}}
            assert set(variables['input'])=={'uri'}
            assert safe_retry is False
            writes.append(variables['id'])
            node=next(item for item in state if item['id']==variables['id'])
            node['uri']=variables['input']['uri']
            if uncertain and len(writes)==1:raise ProviderError('network_or_timeout')
            return {'webhookSubscriptionUpdate':{'userErrors':[],'webhookSubscription':copy.deepcopy(node)}}
    monkeypatch.setattr(renewal,'Shopify',API)
    monkeypatch.setattr(renewal,'Providers',Providers)
    monkeypatch.setattr(renewal,'Settings',lambda:Settings(token='isolated-callback-renewal-test-token',database_url='sqlite:///'+str(tmp_path/'test.db')))
    monkeypatch.setattr(renewal,'ROOT',tmp_path)
    return state,writes


def test_renewal_dry_run_does_not_write(tmp_path,monkeypatch):
    state,writes=setup(tmp_path,monkeypatch)
    report=asyncio.run(renewal.main(OLD,NEW))
    assert not writes and all(node['uri']==OLD+'/webhooks/shopify' for node in state)
    assert all(node['status']=='planned' for node in report['subscriptions'])


def test_renewal_preserves_payload_and_is_idempotent(tmp_path,monkeypatch):
    state,writes=setup(tmp_path,monkeypatch);fields=copy.deepcopy([node['includeFields'] for node in state])
    asyncio.run(renewal.main(OLD,NEW,True))
    report=asyncio.run(renewal.main(OLD,NEW,True))
    assert writes==['1','2','3']
    assert [node['includeFields'] for node in state]==fields
    assert all(node['status']=='already_updated' for node in report['subscriptions'])


def test_unexpected_payload_stops_all_mutations(tmp_path,monkeypatch):
    _,writes=setup(tmp_path,monkeypatch,extra_field=True)
    with pytest.raises(ValueError,match='Unexpected payload fields'):
        asyncio.run(renewal.main(OLD,NEW,True))
    assert writes==[]


def test_unhealthy_destination_stops_all_mutations(tmp_path,monkeypatch):
    state,writes=setup(tmp_path,monkeypatch,healthy=False)
    with pytest.raises(ValueError,match='healthy CommerceOps endpoint'):
        asyncio.run(renewal.main(OLD,NEW,True))
    assert writes==[]
    assert all(node['uri']==OLD+'/webhooks/shopify' for node in state)


def test_uncertain_update_is_reconciled_without_repeating_it(tmp_path,monkeypatch):
    _,writes=setup(tmp_path,monkeypatch,uncertain=True)
    with pytest.raises(ProviderError):asyncio.run(renewal.main(OLD,NEW,True))
    assert writes==['1']
    report=asyncio.run(renewal.main(OLD,NEW,True))
    assert writes==['1','2','3']
    assert report['subscriptions'][0]['status']=='already_updated'


@pytest.mark.parametrize('url',['http://insecure.example','https://user:password@owned.example'])
def test_renewal_rejects_insecure_or_credential_bearing_destination(url):
    with pytest.raises(ValueError):renewal.validate_base(url)
