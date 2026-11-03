"""Real HTTP adapters. Fixture responses are explicit and never used as live fallback."""
import asyncio, json, os, re, time
from pathlib import Path
import httpx
from pydantic import ValidationError
from .config import ROOT
from .models import Draft, ReviewResult, Summary, Growth
from .db import ModelCall
from .integrations import record_check

class ProviderError(Exception):
    def __init__(self,category): self.category=category; super().__init__(category)

async def request(client,method,url,*,safe_retry=False,**kw):
    for attempt in range(3 if safe_retry else 1):
        try:
            response=await client.request(method,url,**kw)
        except (httpx.TimeoutException,httpx.NetworkError):
            if safe_retry and attempt < 2:
                await asyncio.sleep(0.25*2**attempt); continue
            raise ProviderError('network_or_timeout') from None
        if response.status_code==429:
            try: code=response.json().get('error',{}).get('code')
            except (ValueError,AttributeError): code=None
            if code in ('insufficient_quota','credit_balance_exhausted'): raise ProviderError('quota_exhausted')
        if response.status_code==429 or response.status_code>=500:
            if safe_retry and attempt < 2:
                try: delay=min(float(response.headers.get('retry-after','0.25')),3)
                except ValueError: delay=0.25
                await asyncio.sleep(max(0.1,delay)*2**attempt); continue
            raise ProviderError('rate_limit' if response.status_code==429 else 'upstream_5xx')
        if response.status_code>=400:
            raise ProviderError('upstream_'+str(response.status_code))
        return response

SCHEMAS={'cart.abandoned':Draft,'review.created':ReviewResult,'product.created':Growth}

def fixture(kind,p):
    if kind=='cart.abandoned':
        return dict(intent='high_intent' if p['value']>=75 else 'browsing',segment='unknown',
            message_subject='Your cart is here when you are ready',message_body='You left a few items in your cart. You can return to review your selection whenever you are ready.',
            recommended_channel='email',risk_flags=[],requires_human_approval=True)
    if kind=='review.created':
        text=p['text'].lower(); category=next((c for word,c in [('broken','quality'),('late','delivery'),('size','sizing'),('support','support'),('packaging','packaging')] if word in text),'other')
        return dict(sentiment='negative' if p['rating']<=2 else 'positive' if p['rating']>=4 else 'neutral',issue_category=category,
            urgency='high' if p['rating']==1 else 'medium' if p['rating']==2 else 'low',evidence_quote=p['text'][:200])
    if kind=='product.created':
        return dict(seo_title=p['title'][:70],meta_description=p['description'][:160],answer=p['description'][:500],faq_candidates=p['verified_faqs'][:5])
    return dict(summary='Verified operational data is ready for review.',recommendation='Review the source records before taking action.')

def policy(kind,result,p):
    if kind=='cart.abandoned':
        body=result['message_subject']+' '+result['message_body']
        # Restrict customer-facing text to a neutral vocabulary, including after model generation.
        allowed=set('your cart is here when you are ready you left a few items in can return to review selection whenever still thinking it over hello hi we saved the selected at any time thanks thank for visiting our store and have been whenever want'.split())
        words=set(re.findall(r"[a-z]+",body.lower()))
        if words-allowed or result['risk_flags']:
            raise ProviderError('unsafe_draft_held')
    if kind=='review.created' and result['evidence_quote'] not in p['text']:
        raise ProviderError('ungrounded_evidence')
    if kind=='product.created':
        sources=[p['title'],p['description'],*p['attributes'],*p['verified_faqs']]
        for value in [result['seo_title'],result['meta_description'],result['answer'],*result['faq_candidates']]:
            if not any(value in source for source in sources): raise ProviderError('ungrounded_product_claim')

class Providers:
    def __init__(self,settings,db,client=None):
        self.settings=settings; self.db=db
        self.client=client or httpx.AsyncClient(timeout=settings.api_timeout,follow_redirects=False)
    async def close(self): await self.client.aclose()
    def gemini_model(self):
        model=os.getenv('GEMINI_MODEL','gemini-3.5-flash-lite')
        if not re.fullmatch(r'gemini-[a-zA-Z0-9._-]+',model):raise ProviderError('invalid_gemini_model')
        return model

    async def gemini_generate(self,kind,p,schema):
        key=os.getenv('GEMINI_API_KEY')
        if not key:raise ProviderError('gemini_not_configured')
        response=await request(self.client,'POST',
            'https://generativelanguage.googleapis.com/v1beta/models/'+self.gemini_model()+':generateContent',
            safe_retry=True,timeout=30,headers={'x-goog-api-key':key},json={
                'systemInstruction':{'parts':[{'text':(ROOT/'prompts/system-v1.txt').read_text()}]},
                'contents':[{'role':'user','parts':[{'text':json.dumps({'workflow':kind,'data':p})}]}],
                'generationConfig':{'responseMimeType':'application/json','responseJsonSchema':schema.model_json_schema(),
                    'maxOutputTokens':1600}})
        data=response.json();metadata=data.get('usageMetadata',{})
        usage={'input_tokens':metadata.get('promptTokenCount',0),
            'output_tokens':metadata.get('candidatesTokenCount',0)+metadata.get('thoughtsTokenCount',0)}
        candidates=data.get('candidates',[])
        if data.get('promptFeedback',{}).get('blockReason') or len(candidates)!=1 or candidates[0].get('finishReason')!='STOP':
            raise ProviderError('model_incomplete_or_refused')
        parts=candidates[0].get('content',{}).get('parts',[])
        text=''.join(part['text'] for part in parts if 'text' in part and not part.get('thought'))
        return json.loads(text),usage

    async def generate(self,event_id,kind,p):
        schema=SCHEMAS.get(kind,Summary)
        for attempt in range(2):
            usage={}; output=None
            try:
                if self.settings.mode=='fixture': output=fixture(kind,p)
                elif self.settings.llm_provider=='gemini':output,usage=await self.gemini_generate(kind,p,schema)
                else:
                    key=os.getenv('OPENAI_API_KEY')
                    if not key: raise ProviderError('openai_not_configured')
                    r=await request(self.client,'POST','https://api.openai.com/v1/responses',safe_retry=True,
                        headers={'Authorization':'Bearer '+key},json={
                        'model':os.getenv('OPENAI_MODEL','gpt-4.1-mini'),'store':False,
                        'instructions':(ROOT/'prompts/system-v1.txt').read_text(),
                        'input':json.dumps({'workflow':kind,'data':p}),
                        'text':{'format':{'type':'json_schema','name':'commerce_result','strict':True,'schema':schema.model_json_schema()}},
                        'max_output_tokens':1600})
                    data=r.json(); usage=data.get('usage',{})
                    if data.get('status')!='completed': raise ProviderError('model_incomplete_or_refused')
                    parts=[c['text'] for o in data.get('output',[]) for c in o.get('content',[]) if c.get('type')=='output_text']
                    output=json.loads(''.join(parts))
                result=schema.model_validate(output).model_dump()
            except (ValidationError,ValueError,KeyError,TypeError):
                self.record(event_id,False,usage)
                if attempt==0: continue
                if self.settings.mode=='live':record_check(self.settings.llm_provider,'generation','failed','invalid_model_output')
                raise ProviderError('invalid_model_output') from None
            except ProviderError as exc:
                if self.settings.mode=='live':record_check(self.settings.llm_provider,'generation','failed',exc.category)
                raise
            self.record(event_id,True,usage)
            try:policy(kind,result,p)
            except ProviderError as exc:
                if self.settings.mode=='live':record_check(self.settings.llm_provider,'generation','failed',exc.category)
                raise
            if self.settings.mode=='live':record_check(self.settings.llm_provider,'generation','verified')
            return result
    def record(self,event_id,valid,usage):
        with self.db.session.begin() as s:
            s.add(ModelCall(event_id=event_id,provider='fixture' if self.settings.mode=='fixture' else self.settings.llm_provider,valid=valid,
                input_tokens=usage.get('input_tokens',0),output_tokens=usage.get('output_tokens',0)))

    async def effect(self,kind,p):
        if self.settings.mode=='fixture': return 'fixture:'+p['event_id']+':'+kind
        if kind=='slack':
            token=os.getenv('SLACK_BOT_TOKEN'); channel=os.getenv('SLACK_CHANNEL_ID')
            if not token or not channel: raise ProviderError('slack_not_configured')
            blocks=[{'type':'section','text':{'type':'plain_text','text':p['text'][:2900]}}]
            if p.get('approval'):
                blocks.append({'type':'actions','elements':[
                    {'type':'button','text':{'type':'plain_text','text':verb.title()},'action_id':verb,'value':p['event_id'],**({'style':'primary'} if verb=='approve' else {})}
                    for verb in ['approve','reject']]})
            r=await request(self.client,'POST','https://slack.com/api/chat.postMessage',headers={'Authorization':'Bearer '+token},
                json={'channel':channel,'text':p['text'][:2900],'blocks':blocks})
            data=r.json()
            if not data.get('ok'): raise ProviderError('slack_rejected')
            return data['ts']
        if kind=='hubspot':
            token=os.getenv('HUBSPOT_ACCESS_TOKEN')
            if not token: raise ProviderError('hubspot_not_configured')
            props={'hs_timestamp':p['timestamp'],'hs_task_subject':p['subject'][:200],
                'hs_task_body':p['body'][:5000],'hs_task_status':'NOT_STARTED','hs_task_priority':'MEDIUM','hs_task_type':'TODO'}
            if os.getenv('HUBSPOT_OWNER_ID'): props['hubspot_owner_id']=os.getenv('HUBSPOT_OWNER_ID')
            r=await request(self.client,'POST','https://api.hubapi.com/crm/v3/objects/tasks',
                headers={'Authorization':'Bearer '+token},json={'properties':props})
            return r.json()['id']
        if kind=='sheets':
            path=os.getenv('GOOGLE_SERVICE_ACCOUNT_FILE'); sheet=os.getenv('GOOGLE_SPREADSHEET_ID')
            if not path or not sheet: raise ProviderError('sheets_not_configured')
            import google.auth.transport.requests
            from google.oauth2 import service_account
            credentials=service_account.Credentials.from_service_account_file(path,scopes=['https://www.googleapis.com/auth/spreadsheets'])
            await asyncio.to_thread(credentials.refresh,google.auth.transport.requests.Request())
            from urllib.parse import quote
            cell_range=quote(os.getenv('GOOGLE_SHEET_RANGE','Events!A:H'),safe='')
            r=await request(self.client,'POST',f'https://sheets.googleapis.com/v4/spreadsheets/{sheet}/values/{cell_range}:append',
                params={'valueInputOption':'RAW','insertDataOption':'INSERT_ROWS'},headers={'Authorization':'Bearer '+credentials.token},
                json={'values':[p['row']]})
            return r.json().get('updates',{}).get('updatedRange','appended')
        raise ProviderError('unknown_effect')
