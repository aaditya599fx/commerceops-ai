"""Shopify ingress and read-only GraphQL adapter. Live status requires actual verification."""
import base64, hashlib, hmac, os, re, time
from datetime import datetime, timezone, timedelta
from .providers import ProviderError, request
from .models import Event
from .db import Fact, dump, now

class Shopify:
    _tokens = {}
    def __init__(self,client,db,engine): self.client=client; self.db=db; self.engine=engine
    def verify(self,raw,signature,shop):
        secret=os.getenv('SHOPIFY_WEBHOOK_SECRET',''); expected=os.getenv('SHOPIFY_SHOP','')
        if not secret or not expected or shop!=expected: return False
        digest=base64.b64encode(hmac.new(secret.encode(),raw,hashlib.sha256).digest()).decode()
        return hmac.compare_digest(digest,signature)
    async def graphql(self,query,variables=None):
        shop=os.getenv('SHOPIFY_SHOP',''); token=os.getenv('SHOPIFY_ACCESS_TOKEN','')
        if not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9-]*\.myshopify\.com',shop):
            raise ProviderError('shopify_not_configured')
        if not token:
            client_id=os.getenv('SHOPIFY_CLIENT_ID','');client_secret=os.getenv('SHOPIFY_CLIENT_SECRET','')
            if not client_id or not client_secret:raise ProviderError('shopify_not_configured')
            cache_key=(shop,client_id,hashlib.sha256(client_secret.encode()).hexdigest())
            cached=self._tokens.get(cache_key)
            if cached and cached[1]>time.monotonic()+60:token=cached[0]
            else:
                response=await request(self.client,'POST',f'https://{shop}/admin/oauth/access_token',safe_retry=True,
                    data={'grant_type':'client_credentials','client_id':client_id,'client_secret':client_secret})
                data=response.json();token=data.get('access_token')
                if not token:raise ProviderError('shopify_token_exchange_failed')
                self._tokens[cache_key]=(token,time.monotonic()+int(data.get('expires_in',0)))
        version=os.getenv('SHOPIFY_API_VERSION','2026-10')
        if not re.fullmatch(r'20\d\d-(01|04|07|10)',version): raise ProviderError('invalid_shopify_version')
        r=await request(self.client,'POST',f'https://{shop}/admin/api/{version}/graphql.json',safe_retry=True,
            headers={'X-Shopify-Access-Token':token},json={'query':query,'variables':variables or {}})
        body=r.json()
        if body.get('errors'): raise ProviderError('shopify_graphql_error')
        return body['data']
    async def check(self):
        data=await self.graphql('{ shop { id name myshopifyDomain } }')
        return {'status':'verified_read','shop':data['shop']['myshopifyDomain'],'verified_at':now()}
    async def customer_context(self,id):
        gid=id if id.startswith('gid://') else 'gid://shopify/Customer/'+id
        data=await self.graphql('''query Context($id: ID!) { customer(id: $id) {
          id email emailMarketingConsent { marketingState } lastOrder { createdAt }
        } }''',{'id':gid})
        c=data.get('customer')
        if not c: raise ProviderError('shopify_customer_missing')
        last=c.get('lastOrder'); recent=bool(last and datetime.fromisoformat(last['createdAt'].replace('Z','+00:00'))>datetime.now(timezone.utc)-timedelta(hours=72))
        return {'consent':(c.get('emailMarketingConsent') or {}).get('marketingState')=='SUBSCRIBED','recent_purchase':recent}
    def order_webhook(self,webhook_id,p):
        # A verified order webhook only updates source facts; no LLM or remote writes in request path.
        oid=str(p['id']); currency=p['currency']
        value={'date':p['created_at'][:10],'currency':currency,'total':float(p['total_price']),
            'refunds':sum(float(t.get('amount',0)) for r in p.get('refunds',[]) for t in r.get('transactions',[]))}
        with self.db.session.begin() as s:
            existing=s.get(Fact,'order:'+oid)
            if existing: existing.value=dump(value)
            else: s.add(Fact(key='order:'+oid,kind='order',source='shopify',value=dump(value)))
            c=p.get('customer')
            if c:
                key='customer:'+str(c['id']); f=s.get(Fact,key)
                ctx={'recent_purchase':True,'consent':(c.get('email_marketing_consent') or {}).get('state')=='subscribed'}
                if f: f.value=dump(ctx)
                else: s.add(Fact(key=key,kind='customer',source='shopify',value=dump(ctx)))
            self.db.audit(s,'shopify:'+webhook_id,'shopify_order_recorded',order_id=oid)
        return {'status':'recorded','webhook_id':webhook_id}
    async def poll_abandoned(self):
        if self.engine.settings.mode!='live': raise ProviderError('shopify_poll_requires_live_mode')
        # Bound each poll. Cursor is persisted so large stores don't silently lose pages.
        with self.db.session() as s:
            cursor=s.get(Fact,'cursor:abandoned'); after=json_load(cursor.value).get('after') if cursor else None
        query='''query Abandoned($after: String) { abandonedCheckouts(first: 50, after: $after, query: "recovery_state:not_recovered") {
          pageInfo { hasNextPage endCursor }
          nodes { id createdAt updatedAt completedAt customer { id email emailMarketingConsent { marketingState } }
            lineItems(first: 100) { pageInfo { hasNextPage } nodes { sku title quantity originalUnitPriceSet { shopMoney { amount currencyCode } } } }
          }
        } }'''
        data=await self.graphql(query,{'after':after}); connection=data['abandonedCheckouts']; accepted=[]; skipped=[]
        for c in connection['nodes']:
            customer=c.get('customer')
            if not customer or not customer.get('email') or c['completedAt'] or c['lineItems']['pageInfo']['hasNextPage']:
                skipped.append({'id':c['id'],'reason':'missing_customer_or_completed_or_oversized'}); continue
            age=datetime.now(timezone.utc)-datetime.fromisoformat(c['updatedAt'].replace('Z','+00:00'))
            if age<timedelta(hours=1): continue
            items=[]; currency=None
            for item in c['lineItems']['nodes']:
                money=item['originalUnitPriceSet']['shopMoney']; currency=money['currencyCode']
                items.append({'sku':item['sku'] or 'unspecified','title':item['title'] or 'Selected item','quantity':item['quantity'],'price':float(money['amount'])})
            if not items: continue
            event=Event.model_validate({'event_id':'shopify-cart:'+hashlib.sha256((c['id']+c['updatedAt']).encode()).hexdigest()[:40],
                'type':'cart.abandoned','timestamp':c['updatedAt'],'source':'shopify',
                'payload':{'customer_id':customer['id'].rsplit('/',1)[-1],'cart_id':c['id'],'email':customer['email'],
                    'consent':(customer.get('emailMarketingConsent') or {}).get('marketingState')=='SUBSCRIBED','recent_purchase':False,
                    'items':items,'value':round(sum(x['price']*x['quantity'] for x in items),2),'currency':currency}})
            accepted.append(self.engine.ingest(event))
        page=connection['pageInfo']
        with self.db.session.begin() as s:
            value=dump({'after':page['endCursor'] if page['hasNextPage'] else None})
            cursor=s.get(Fact,'cursor:abandoned')
            if cursor: cursor.value=value
            else:s.add(Fact(key='cursor:abandoned',kind='cursor',source='shopify',value=value))
        return {'accepted':accepted,'skipped':skipped,'more_pages':page['hasNextPage']}

import json
def json_load(value): return json.loads(value)
