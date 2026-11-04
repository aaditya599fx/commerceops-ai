"""Shopify ingress and read-only GraphQL adapter. Live status requires actual verification."""
import base64, hashlib, hmac, os, re, time
from datetime import datetime, timezone, timedelta
from decimal import Decimal, InvalidOperation
from .providers import ProviderError, request
from .models import Event
from .db import Fact, WebhookReceipt, dump, now

class Shopify:
    _tokens = {}
    def __init__(self,client,db,engine): self.client=client; self.db=db; self.engine=engine
    def verify(self,raw,signature,shop):
        secret=os.getenv('SHOPIFY_WEBHOOK_SECRET',''); expected=os.getenv('SHOPIFY_SHOP','')
        if not secret or not expected or shop!=expected: return False
        # During rotation Shopify signs with the oldest unrevoked app secret.
        # Accept the explicitly configured previous secret during that transition.
        secrets=dict.fromkeys([secret,os.getenv('SHOPIFY_PREVIOUS_WEBHOOK_SECRET','')])
        valid=False
        for candidate in secrets:
            if not candidate:continue
            digest=base64.b64encode(hmac.new(candidate.encode(),raw,hashlib.sha256).digest()).decode()
            valid|=hmac.compare_digest(digest,signature)
        return valid
    async def graphql(self,query,variables=None,*,safe_retry=True):
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
        r=await request(self.client,'POST',f'https://{shop}/admin/api/{version}/graphql.json',safe_retry=safe_retry,
            headers={'X-Shopify-Access-Token':token},json={'query':query,'variables':variables or {}})
        body=r.json()
        if body.get('errors'): raise ProviderError('shopify_graphql_error')
        return body['data']
    async def check(self):
        data=await self.graphql('{ shop { id name myshopifyDomain } }')
        return {'status':'verified_read','shop':data['shop']['myshopifyDomain'],'verified_at':now()}

    async def configure_webhooks(self,base_url,apply=False):
        from urllib.parse import urlparse
        from .integrations import record_check
        parsed=urlparse(base_url)
        if parsed.scheme!='https' or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ProviderError('public_https_callback_required')
        callback=base_url.rstrip('/')+'/webhooks/shopify'
        # Order callbacks contain no customer/contact fields. Missing refund details remain unknown.
        topics={'ORDERS_CREATE':['id','created_at','updated_at','currency','total_price'],
                'ORDERS_UPDATED':['id','created_at','updated_at','currency','total_price'],
                'PRODUCTS_CREATE':['id','title','body_html','created_at']}
        data=await self.graphql('{ webhookSubscriptions(first:100) { nodes { id topic uri } pageInfo { hasNextPage } } }')
        if data['webhookSubscriptions']['pageInfo']['hasNextPage']:raise ProviderError('webhook_subscription_review_required')
        existing=data['webhookSubscriptions']['nodes'];results=[]
        for topic,fields in topics.items():
            matching=[w for w in existing if w['topic']==topic]
            if any(w['uri']!=callback for w in matching):raise ProviderError('existing_callback_requires_review')
            if matching:
                results.append({'topic':topic,'status':'already_configured','id':matching[0]['id']});continue
            if not apply:
                results.append({'topic':topic,'status':'planned','include_fields':fields});continue
            # A creation timeout is ambiguous. Inspect subscriptions before any subsequent attempt.
            data=await self.graphql('''mutation Configure($topic: WebhookSubscriptionTopic!, $input: WebhookSubscriptionInput!) {
              webhookSubscriptionCreate(topic:$topic,webhookSubscription:$input) {
                webhookSubscription { id topic uri } userErrors { field message }
              }
            }''',{'topic':topic,'input':{'uri':callback,'format':'JSON','includeFields':fields}},safe_retry=False)
            response=data['webhookSubscriptionCreate']
            if response['userErrors'] or not response['webhookSubscription']:raise ProviderError('webhook_configuration_rejected')
            results.append({'topic':topic,'status':'configured','id':response['webhookSubscription']['id']})
        if apply:record_check('shopify','webhook_configuration','verified')
        return {'callback':callback,'subscriptions':results,'delivery_verified':False}
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
        updated_at=p.get('updated_at') or p['created_at']
        if not re.fullmatch(r'\d+',oid) or not re.fullmatch(r'[A-Z]{3}',currency):raise ValueError('Invalid order identifiers')
        for stamp in (p['created_at'],updated_at):
            if datetime.fromisoformat(stamp.replace('Z','+00:00')).tzinfo is None:raise ValueError('Order timestamps require a timezone')
        try:amount=Decimal(str(p['total_price']))
        except InvalidOperation:raise ValueError('Invalid order total') from None
        if not amount.is_finite() or amount<0:raise ValueError('Invalid order total')
        value={'date':p['created_at'][:10],'currency':currency,'total':float(p['total_price']),'updated_at':updated_at,'refunds_known':'refunds' in p,
            'refunds':sum(float(t.get('amount',0)) for r in p.get('refunds',[]) for t in r.get('transactions',[]))}
        digest=hashlib.sha256(json.dumps(p,sort_keys=True,separators=(',',':')).encode()).hexdigest()
        with self.db.session.begin() as s:
            receipt=s.get(WebhookReceipt,webhook_id)
            if receipt:
                if receipt.digest!=digest or receipt.topic!='orders':
                    from .engine import Conflict
                    raise Conflict('Webhook ID reused with different content')
                return {'status':'recorded','webhook_id':webhook_id,'duplicate':True}
            s.add(WebhookReceipt(id=webhook_id,topic='orders',digest=digest))
            existing=s.get(Fact,'order:'+oid)
            if existing:
                old=json_load(existing.value).get('updated_at')
                if old and datetime.fromisoformat(old.replace('Z','+00:00'))>datetime.fromisoformat(updated_at.replace('Z','+00:00')):
                    self.db.audit(s,'shopify:'+webhook_id,'stale_order_update_ignored',order_id=oid)
                    return {'status':'ignored','reason':'stale_order_update','webhook_id':webhook_id}
            if existing: existing.value=dump(value)
            else: s.add(Fact(key='order:'+oid,kind='order',source='shopify',value=dump(value)))
            c=p.get('customer')
            if c:
                key='customer:'+str(c['id']); f=s.get(Fact,key)
                ctx={'recent_purchase':True,'consent':(c.get('email_marketing_consent') or {}).get('state')=='subscribed'}
                if f: f.value=dump(ctx)
                else: s.add(Fact(key=key,kind='customer',source='shopify',value=dump(ctx)))
            self.db.audit(s,'shopify:'+webhook_id,'shopify_order_recorded',order_id=oid)
        return {'status':'recorded','webhook_id':webhook_id,'duplicate':False}
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
