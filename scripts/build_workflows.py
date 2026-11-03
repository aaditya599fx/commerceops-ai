"""Build import candidates. workflows/ is populated only by n8n's real export command."""
import json, uuid
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
creds={'httpHeaderAuth':{'id':'commerceops-local-auth','name':'CommerceOps API bearer'}}

def node(name,type,position,parameters,version=1,**kw):
    return {'id':str(uuid.uuid5(uuid.NAMESPACE_URL,'commerceops:'+name)), 'name':name,'type':'n8n-nodes-base.'+type,
        'typeVersion':version,'position':position,'parameters':parameters,**kw}

def http(name,path,pos,body=None):
    p={'method':'POST','url':'={{ $env.COMMERCEOPS_API_URL + '+json.dumps(path)+' }}','authentication':'genericCredentialType','genericAuthType':'httpHeaderAuth',
        'options':{'timeout':120000}}
    if body is not None:p.update({'sendBody':True,'specifyBody':'json','jsonBody':body})
    return node(name,'httpRequest',pos,p,4.2,credentials=creds)

def workflow(slug,name,kind):
    nodes=[node('Incoming event','webhook',[0,0],{'httpMethod':'POST','path':'commerceops/'+slug,'authentication':'headerAuth','responseMode':'responseNode','options':{}},2,webhookId='commerceops-'+slug,credentials=creds),
        http('Validate and deduplicate','/api/events',[240,0],'={{ JSON.stringify($json.body) }}'),
        node('Acknowledge durable receipt','respondToWebhook',[480,0],{'respondWith':'json','responseBody':'={{ JSON.stringify($json) }}','options':{'responseCode':202}},1.4),
        node('New delivery?','if',[720,0],{'conditions':{'options':{'caseSensitive':True,'leftValue':'','typeValidation':'strict','version':2},
            'conditions':[{'id':'unique','leftValue':'={{ $json.duplicate }}','rightValue':False,'operator':{'type':'boolean','operation':'false','singleValue':True}}],'combinator':'and'},'options':{}},2.2),
        node('Process bounded workflow','httpRequest',[960,-100],{'method':'POST','url':'={{ $env.COMMERCEOPS_API_URL + "/api/runs/" + encodeURIComponent($json.event_id) + "/process" }}',
            'authentication':'genericCredentialType','genericAuthType':'httpHeaderAuth','options':{'timeout':120000}},4.2,credentials=creds),
        node('Output passed validation?','if',[1200,-100],{'conditions':{'options':{'caseSensitive':True,'leftValue':'','typeValidation':'strict','version':2},
            'conditions':[{'id':'safe','leftValue':'={{ $json.status }}','rightValue':'dead_letter','operator':{'type':'string','operation':'notEquals'}}],'combinator':'and'},'options':{}},2.2),
        http('Dispatch approved outbox','/api/actions/dispatch',[1440,-200]),
        node('Held for manual replay','noOp',[1440,0],{}),node('Duplicate safely stopped','noOp',[960,170],{}),
        node('Workflow notes','stickyNote',[0,-300],{'content':f'## {name}\nExpected event type: `{kind}`.\nBearer-authenticated webhook. Backend validates and durably stores before acknowledgement.\nConsent, calculations, model schemas and approvals are enforced by Python.\nSlack callback: /webhooks/slack/actions. No email is automatically sent.','width':680,'height':220})]
    c={}
    def connect(a,b,index=0):
        c.setdefault(a,{'main':[]})
        while len(c[a]['main'])<=index:c[a]['main'].append([])
        c[a]['main'][index].append({'node':b,'type':'main','index':0})
    for a,b in [('Incoming event','Validate and deduplicate'),('Validate and deduplicate','Acknowledge durable receipt'),('Acknowledge durable receipt','New delivery?'),('New delivery?','Process bounded workflow'),('Process bounded workflow','Output passed validation?'),('Output passed validation?','Dispatch approved outbox')]:connect(a,b)
    connect('New delivery?','Duplicate safely stopped',1);connect('Output passed validation?','Held for manual replay',1)
    return {'id':'commerceops-'+slug,'name':'CommerceOps · '+name,'nodes':nodes,'connections':c,'active':False,'settings':{'executionOrder':'v1','timezone':'Asia/Kolkata','saveDataErrorExecution':'all','saveDataSuccessExecution':'all','saveManualExecutions':True},'pinData':{},'versionId':str(uuid.uuid4())}

workflows=[]
for slug,name,kind in [('cart','Cart recovery','cart.abandoned'),('inventory','Inventory watch','inventory.updated'),('review','Review intelligence','review.created'),
    ('product','Product growth drafts','product.created'),('customer','Customer intelligence','customer.updated'),('brief','Executive brief','brief.requested')]:
    workflows.append(workflow(slug,name,kind))
for slug,name,path,rule in [('dispatcher','Durable queue dispatcher','/api/worker/tick',{'field':'minutes','minutesInterval':1}),
    ('shopify-poll','Shopify abandoned checkout poll','/api/integrations/shopify/poll',{'field':'minutes','minutesInterval':30}),
    ('daily','Daily executive brief','/api/schedules/brief',{'field':'cronExpression','expression':'0 9 * * *'})]:
    trigger=node('Schedule','scheduleTrigger',[0,0],{'rule':{'interval':[rule]}},1.2)
    action=http(name,path,[280,0]); workflows.append({'id':'commerceops-'+slug,'name':'CommerceOps · '+name,'nodes':[trigger,action],
        'connections':{'Schedule':{'main':[[{'node':name,'type':'main','index':0}]]}},'active':False,
        'settings':{'executionOrder':'v1','timezone':'Asia/Kolkata'},'versionId':str(uuid.uuid4())})
path=ROOT/'runtime/import';path.mkdir(parents=True,exist_ok=True)
for w in workflows:(path/(w['id']+'.json')).write_text(json.dumps(w,indent=2))
print(f'Prepared {len(workflows)} import candidates in runtime/import. Export from n8n after verification.')
