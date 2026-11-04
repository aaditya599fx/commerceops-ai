"""Review-first replacement of the three existing minimal Shopify callback URIs."""
import argparse,asyncio,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from backend.config import Settings
from backend.db import DB,now
from backend.providers import Providers
from backend.providers import request
from backend.shopify import Shopify

FIELDS={'ORDERS_CREATE':['id','created_at','updated_at','currency','total_price'],
 'ORDERS_UPDATED':['id','created_at','updated_at','currency','total_price'],
 'PRODUCTS_CREATE':['id','title','body_html','created_at']}

def validate_base(value):
    from urllib.parse import urlparse
    parsed=urlparse(value)
    if parsed.scheme!='https' or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in ('','/'):
        raise ValueError('Use a public HTTPS base URL without credentials, path, query or fragment')
    return value.rstrip('/')

async def main(old_base,new_base,apply=False,additional_old_bases=()):
    OLD=validate_base(old_base);NEW=validate_base(new_base)
    previous=[validate_base(value) for value in additional_old_bases]
    allowed_callbacks={base+'/webhooks/shopify' for base in [OLD,NEW,*previous]}
    cfg=Settings();provider=Providers(cfg,DB(cfg.database_url));api=Shopify(provider.client,provider.db,None)
    try:
        result=await api.graphql('{webhookSubscriptions(first:100){nodes{id topic uri includeFields}pageInfo{hasNextPage}}}')
        if result['webhookSubscriptions']['pageInfo']['hasNextPage']:raise ValueError('Review paginated subscriptions first')
        nodes=result['webhookSubscriptions']['nodes'];selected=[]
        for topic,fields in FIELDS.items():
            matches=[node for node in nodes if node['topic']==topic]
            if len(matches)!=1:raise ValueError('Expected exactly one existing subscription per topic')
            node=matches[0]
            if node['uri'] not in allowed_callbacks:raise ValueError('Unexpected current callback')
            if set(node['includeFields'])!=set(fields):raise ValueError('Unexpected payload fields; no changes applied')
            selected.append(node)
        if apply:
            # Public anonymous probe only: never forward APP_TOKEN or provider credentials.
            health=await request(provider.client,'GET',NEW+'/health',safe_retry=True)
            if health.json().get('status')!='ok' or health.json().get('version')!='0.1.0':
                raise ValueError('Destination is not a healthy CommerceOps endpoint; no changes applied')
        report={'prepared_at':now(),'old_base_url':OLD,'new_base_url':NEW,'apply':apply,'subscriptions':[]}
        if previous:report['additional_old_base_urls']=previous
        for node in selected:
            status='already_updated' if node['uri']==NEW+'/webhooks/shopify' else 'planned'
            if apply and status!='already_updated':
                # No mutation retry. Re-read subscription state after any ambiguous failure.
                data=await api.graphql('''mutation Move($id:ID!,$input:WebhookSubscriptionInput!){webhookSubscriptionUpdate(id:$id,webhookSubscription:$input){webhookSubscription{id topic uri includeFields}userErrors{field message}}}''',
                    {'id':node['id'],'input':{'uri':NEW+'/webhooks/shopify'}},safe_retry=False)
                changed=data['webhookSubscriptionUpdate']
                if changed['userErrors'] or not changed['webhookSubscription']:raise ValueError('Update rejected')
                actual=changed['webhookSubscription']
                if actual['uri']!=NEW+'/webhooks/shopify' or set(actual['includeFields'])!=set(FIELDS[node['topic']]):raise ValueError('Updated callback needs review before retrying')
                status='updated'
            report['subscriptions'].append({'id':node['id'],'topic':node['topic'],'status':status,'include_fields':node['includeFields']})
        path=ROOT/'runtime'/('callback-renewal-result.json' if apply else 'callback-renewal-plan.json')
        path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2));return report
    finally:await provider.close()

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--old-base-url',required=True);parser.add_argument('--new-base-url',required=True);parser.add_argument('--previous-base-url',action='append',default=[]);parser.add_argument('--apply',action='store_true');args=parser.parse_args()
    asyncio.run(main(args.old_base_url,args.new_base_url,args.apply,args.previous_base_url))
