import asyncio
import json

import httpx
import pytest
from sqlalchemy import select

from backend.config import Settings
from backend.db import DB, ModelCall
from backend.integrations import read_checks
from backend.providers import Providers, ProviderError, fixture


def provider(tmp_path,handler):
    settings=Settings(mode='live',llm_provider='gemini',token='isolated-gemini-test-token-123456',
        database_url='sqlite:///'+str(tmp_path/'gemini.db'))
    return Providers(settings,DB(settings.database_url),httpx.AsyncClient(transport=httpx.MockTransport(handler)))


def response(output,finish='STOP'):
    return httpx.Response(200,json={'candidates':[{'finishReason':finish,
        'content':{'parts':[{'text':json.dumps(output)}]}}],
        'usageMetadata':{'promptTokenCount':20,'candidatesTokenCount':10,'thoughtsTokenCount':3}})


def test_gemini_structured_generation_and_usage(tmp_path,monkeypatch):
    monkeypatch.setenv('GEMINI_API_KEY','test-gemini-key');seen=[]
    def handler(req):
        seen.append(req)
        assert req.url.host=='generativelanguage.googleapis.com'
        assert not req.url.query
        assert req.headers['x-goog-api-key']=='test-gemini-key'
        body=json.loads(req.content)
        assert body['generationConfig']['responseMimeType']=='application/json'
        assert body['generationConfig']['responseJsonSchema']['additionalProperties'] is False
        return response({'summary':'Stock is low.','recommendation':'Review stock.'})
    p=provider(tmp_path,handler)
    async def scenario():
        result=await p.generate('gemini-success','inventory.updated',{'available':4})
        assert result['summary']=='Stock is low.'
        with p.db.session() as session:
            call=session.scalar(select(ModelCall))
            assert (call.provider,call.input_tokens,call.output_tokens)==('gemini',20,13)
        assert read_checks()['gemini']['generation']['status']=='verified'
        await p.close()
    asyncio.run(scenario());assert len(seen)==1


@pytest.mark.parametrize('case,error,count',[
    ('invalid','invalid_model_output',2),('safety','model_incomplete_or_refused',1),
    ('truncated','model_incomplete_or_refused',1),('policy','unsafe_draft_held',1),
    ('auth','upstream_403',1),('rate','rate_limit',3)])
def test_gemini_failure_is_held(tmp_path,monkeypatch,case,error,count):
    monkeypatch.setenv('GEMINI_API_KEY','test-gemini-key');seen=[]
    def handler(req):
        seen.append(req)
        if case=='invalid':return response({'wrong':True})
        if case=='safety':return httpx.Response(200,json={'promptFeedback':{'blockReason':'SAFETY'}})
        if case=='truncated':return response({},'MAX_TOKENS')
        if case=='auth':return httpx.Response(403)
        if case=='rate':return httpx.Response(429,headers={'retry-after':'0'})
        draft=fixture('cart.abandoned',{'value':80});draft['message_body']='Buy now for a discount!'
        return response(draft)
    p=provider(tmp_path,handler)
    async def scenario():
        with pytest.raises(ProviderError) as exc:
            await p.generate('gemini-failure','cart.abandoned',{'value':80})
        assert exc.value.category==error
        assert read_checks()['gemini']['generation']['category']==error
        await p.close()
    asyncio.run(scenario());assert len(seen)==count


def test_gemini_missing_key_never_uses_openai(tmp_path,monkeypatch):
    monkeypatch.delenv('GEMINI_API_KEY',raising=False)
    monkeypatch.setenv('OPENAI_API_KEY','available-but-not-selected')
    def handler(req):raise AssertionError('No network call is allowed without the selected key')
    p=provider(tmp_path,handler)
    async def scenario():
        with pytest.raises(ProviderError) as exc:await p.generate('missing','inventory.updated',{})
        assert exc.value.category=='gemini_not_configured'
        await p.close()
    asyncio.run(scenario())
