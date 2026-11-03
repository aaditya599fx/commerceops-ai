import asyncio, json, time
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from collections import Counter, defaultdict
from sqlalchemy import select, update, func
from sqlalchemy.exc import IntegrityError
from .db import Run, Audit, Effect, ModelCall, Fact, dump, unpack, now
from .models import Event
from .providers import ProviderError

TERMINAL={'completed','blocked','rejected','held','dead_letter','draft_ready'}

class Conflict(Exception): pass

class Engine:
    def __init__(self,settings,db,providers):
        self.settings=settings; self.db=db; self.providers=providers
        self.lock=asyncio.Lock()
    def ingest(self,event:Event):
        if self.settings.mode=='live' and event.source=='synthetic':
            raise Conflict('Synthetic events are disabled in live mode')
        try:
            with self.db.session.begin() as s:
                s.add(Run(id=event.event_id,type=event.type,source=event.source,payload=event.model_dump_json()))
                s.flush()
                self.db.audit(s,event.event_id,'received',source=event.source,workflow=event.type)
            return {'event_id':event.event_id,'status':'queued','duplicate':False}
        except IntegrityError:
            with self.db.session.begin() as s:
                existing=s.get(Run,event.event_id)
                if not existing: raise
                old=Event.model_validate_json(existing.payload)
                if old.model_dump(mode='json')!=event.model_dump(mode='json'):
                    raise Conflict('Event ID already used with different content')
                s.execute(update(Run).where(Run.id==event.event_id).values(duplicates=Run.duplicates+1))
                self.db.audit(s,event.event_id,'duplicate_suppressed')
                return {'event_id':event.event_id,'status':existing.status,'duplicate':True}

    def recover(self):
        # Single active worker. After a crash, language generation may be retried; remote writes may not.
        with self.db.session.begin() as s:
            for r in s.scalars(select(Run).where(Run.status=='processing')):
                r.status='queued'; self.db.audit(s,r.id,'recovered_after_restart')
            for effect in s.scalars(select(Effect).where(Effect.status=='sending')):
                effect.status='uncertain'; effect.error='interrupted_remote_write'
                r=s.get(Run,effect.event_id); r.status='held'; r.error='uncertain_external_write'
                self.db.audit(s,r.id,'remote_write_requires_reconciliation',kind=effect.kind)

    def result(self,id):
        with self.db.session() as s:
            r=s.get(Run,id)
            if not r: return None
            return {k:getattr(r,k) for k in ['id','type','source','status','created','updated','error','attempts','duplicates','latency_ms','approval_at','decision_at','actor','reason']} | {
                'result':unpack(r.result),'event':unpack(r.payload),
                'audit':[{'at':a.at,'action':a.action,'detail':unpack(a.detail)} for a in s.scalars(select(Audit).where(Audit.event_id==id).order_by(Audit.id))],
                'effects':[{'kind':e.kind,'status':e.status,'remote_id':e.remote_id,'error':e.error} for e in s.scalars(select(Effect).where(Effect.event_id==id))]}

    def queue_effect(self,s,r,kind,p):
        if not s.scalar(select(Effect.id).where(Effect.event_id==r.id,Effect.kind==kind)):
            s.add(Effect(event_id=r.id,kind=kind,payload=dump({'event_id':r.id,**p})))

    def eligibility(self,s,p,exclude):
        if not p['consent']: return 'no_marketing_consent'
        if p['recent_purchase']: return 'recent_purchase'
        if p['value']<self.settings.min_cart: return 'below_value_threshold'
        fact=s.get(Fact,'customer:'+p['customer_id'])
        if fact:
            customer=unpack(fact.value)
            if not customer.get('consent',True): return 'consent_revoked'
            if customer.get('recent_purchase'): return 'recent_purchase'
        cutoff=(datetime.now(timezone.utc)-timedelta(hours=self.settings.cooldown_hours)).isoformat()
        for other in s.scalars(select(Run).where(Run.type=='cart.abandoned',Run.id!=exclude,
                Run.status.in_(['awaiting_approval','approved','completed','held']),Run.created>=cutoff)):
            if unpack(other.payload)['payload']['customer_id']==p['customer_id']:
                return 'recovery_cooldown'
        return None

    async def process(self,id):
        async with self.lock:
            start=time.perf_counter()
            with self.db.session.begin() as s:
                claimed=s.execute(update(Run).where(Run.id==id,Run.status=='queued').values(status='processing',attempts=Run.attempts+1,updated=now()))
                if not claimed.rowcount: return
                r=s.get(Run,id); kind=r.type; source=r.source; p=unpack(r.payload)['payload']
                self.db.audit(s,id,'processing_started',attempt=r.attempts)
                if kind=='cart.abandoned':
                    reason=self.eligibility(s,p,id)
                    if reason:
                        r.status='blocked'; r.reason=reason; r.updated=now()
                        r.latency_ms=(time.perf_counter()-start)*1000
                        self.db.audit(s,id,'policy_blocked',reason=reason); return
            try:
                if kind=='cart.abandoned' and source=='shopify':
                    from .shopify import Shopify
                    current=await Shopify(self.providers.client,self.db,self).customer_context(p['customer_id'])
                    with self.db.session.begin() as s:
                        f=s.get(Fact,'customer:'+p['customer_id'])
                        if f: f.value=dump(current)
                        else: s.add(Fact(key='customer:'+p['customer_id'],kind='customer',source='shopify',value=dump(current)))
                        reason=self.eligibility(s,p,id)
                        if reason:
                            r=s.get(Run,id); r.status='blocked'; r.reason=reason; r.updated=now()
                            self.db.audit(s,id,'policy_blocked',reason=reason); return
                context=p
                calculated={} 
                if kind=='inventory.updated':
                    cover=p['available']/p['daily_units'] if p['daily_units'] else None
                    calculated={'days_of_cover':round(cover,2) if cover is not None else None,
                        'low_stock':p['available']==0 or (cover is not None and cover<=p['lead_days']),
                        'reorder_units':max(0,round(p['daily_units']*(p['lead_days']+7)-p['available']))}
                    context={**p,**calculated}
                elif kind=='customer.updated':
                    segment=('dormant' if p['days_since_order']>=180 else 'at_risk' if p['days_since_order']>=90 else
                        'high_spend' if p['currency']==self.settings.high_spend_currency and p['total_spend']>=self.settings.high_spend else 'repeat' if p['orders']>1 else 'first_time')
                    calculated={'segment':segment,'spend_currency':p['currency']}; context={**p,**calculated}
                elif kind=='brief.requested':
                    calculated=self.business_metrics(p['date']); context=calculated
                # Never send contact email, IDs or names to the model.
                context={k:v for k,v in context.items() if k not in ('email','customer_id','cart_id')}
                result=await self.providers.generate(id,kind,context)
                result={**result,**calculated,'provider_mode':self.settings.mode}
                with self.db.session.begin() as s:
                    r=s.get(Run,id); r.result=dump(result); r.updated=now(); r.error=None
                    if kind=='cart.abandoned':
                        r.status='awaiting_approval'; r.approval_at=now()
                        self.queue_effect(s,r,'slack',{'approval':True,'text':f'Cart draft · {id}\n{result["message_subject"]}\n{result["message_body"]}\nRequires an authorized reviewer.'})
                        self.db.audit(s,id,'approval_requested')
                    elif kind=='product.created':
                        r.status='draft_ready'
                        # JSON-LD is assembled from verified input rather than invented model claims.
                        result['json_ld']={'@context':'https://schema.org','@type':'Product','name':p['title'],'description':p['description']}
                        r.result=dump(result); self.db.audit(s,id,'editorial_draft_saved')
                    else:
                        r.status='actions_pending'
                        if (kind=='inventory.updated' and calculated['low_stock']) or (kind=='review.created' and result['urgency']=='high'):
                            self.queue_effect(s,r,'slack',{'approval':False,'text':f'{kind} · {id}\n'+dump(result)[:2500]})
                        if kind=='review.created' and result['urgency']=='high' or kind=='customer.updated':
                            self.queue_effect(s,r,'hubspot',{'timestamp':now(),'subject':f'CommerceOps {kind} [{id}]',
                                'body':dump(result)+'\nSource event: '+id})
                        self.report_effect(s,r)
                        self.db.audit(s,id,'validated_output',workflow=kind)
                    r.latency_ms=(time.perf_counter()-start)*1000
            except ProviderError as exc:
                with self.db.session.begin() as s:
                    r=s.get(Run,id); r.status='dead_letter'; r.error=exc.category; r.updated=now()
                    r.latency_ms=(time.perf_counter()-start)*1000
                    self.db.audit(s,id,'failed_closed',category=exc.category)
            except Exception:
                with self.db.session.begin() as s:
                    r=s.get(Run,id); r.status='dead_letter'; r.error='internal_processing_error'; r.updated=now()
                    self.db.audit(s,id,'failed_closed',category='internal_processing_error')

    def report_effect(self,s,r):
        self.queue_effect(s,r,'sheets',{'row':[r.id,r.type,r.source,r.status,r.created,now(),self.settings.mode,r.error or '']})

    async def decide(self,id,decision,actor,reason):
        async with self.lock:
            with self.db.session.begin() as s:
                r=s.get(Run,id)
                if not r: raise Conflict('Unknown event')
                if r.status!='awaiting_approval':
                    if r.actor and ((decision=='approve' and r.status in ('approved','completed','held')) or (decision=='reject' and r.status=='rejected')):
                        return {'event_id':id,'status':r.status,'duplicate':True}
                    raise Conflict('Event is not awaiting approval')
                p=unpack(r.payload)['payload']
                # Recheck consent and purchase context at decision time.
                blocked=self.eligibility(s,p,id) if decision=='approve' else None
                r.decision_at=now(); r.actor=actor; r.reason=reason; r.updated=now()
                if blocked:
                    r.status='blocked'; r.reason=blocked; self.db.audit(s,id,'approval_blocked',reason=blocked,actor=actor)
                elif decision=='reject':
                    r.status='rejected'; self.db.audit(s,id,'rejected',actor=actor,reason=reason)
                else:
                    r.status='approved'
                    result=unpack(r.result)
                    self.queue_effect(s,r,'hubspot',{'timestamp':now(),'subject':result['message_subject']+f' [{id}]',
                        'body':f'APPROVED DRAFT ONLY. Do not auto-send.\nCustomer: {p["customer_id"]}\n'+result['message_body']})
                    self.db.audit(s,id,'approved',actor=actor,reason=reason)
                self.report_effect(s,r)
                return {'event_id':id,'status':r.status,'duplicate':False}

    async def flush(self):
        async with self.lock:
            with self.db.session() as s:
                ids=list(s.scalars(select(Effect.id).where(Effect.status=='pending').order_by(Effect.id).limit(30)))
            for id in ids:
                with self.db.session.begin() as s:
                    effect=s.get(Effect,id)
                    if effect.status!='pending': continue
                    effect.status='sending'; effect.updated=now()
                    kind=effect.kind; p=unpack(effect.payload); event_id=effect.event_id
                try:
                    if kind=='hubspot':
                        with self.db.session() as s:
                            r=s.get(Run,event_id); payload=unpack(r.payload)['payload']; source=r.source; workflow=r.type
                        if workflow=='cart.abandoned' and source=='shopify':
                            from .shopify import Shopify
                            current=await Shopify(self.providers.client,self.db,self).customer_context(payload['customer_id'])
                            if not current['consent'] or current['recent_purchase']:
                                with self.db.session.begin() as s:
                                    effect=s.get(Effect,id); effect.status='cancelled'
                                    r=s.get(Run,event_id); r.status='blocked'; r.reason='live_consent_or_purchase_changed'
                                    self.db.audit(s,event_id,'approved_action_cancelled',reason=r.reason)
                                continue
                    remote_id=await self.providers.effect(kind,p)
                    with self.db.session.begin() as s:
                        effect=s.get(Effect,id); effect.status='done'; effect.remote_id=remote_id; effect.updated=now()
                        self.db.audit(s,event_id,'effect_recorded',kind=kind,mode=self.settings.mode,remote_id=remote_id)
                except Exception as exc:
                    category=exc.category if isinstance(exc,ProviderError) else 'adapter_error'
                    with self.db.session.begin() as s:
                        effect=s.get(Effect,id); effect.status='uncertain'; effect.error=category; effect.updated=now()
                        r=s.get(Run,event_id); r.status='held'; r.error='external_write:'+category
                        self.db.audit(s,event_id,'external_write_held',kind=kind,category=category)
            with self.db.session.begin() as s:
                for r in s.scalars(select(Run).where(Run.status.in_(['approved','actions_pending']))):
                    unfinished=s.scalar(select(func.count()).select_from(Effect).where(Effect.event_id==r.id,Effect.status!='done'))
                    if not unfinished:
                        r.status='completed'; r.updated=now(); self.db.audit(s,r.id,'completed')

    def replay(self,id):
        with self.db.session.begin() as s:
            r=s.get(Run,id)
            if not r or r.status!='dead_letter': raise Conflict('Only dead-letter events can be replayed; reconcile uncertain writes separately')
            if r.attempts>=3: raise Conflict('Manual replay limit reached')
            r.status='queued'; r.error=None; self.db.audit(s,id,'manual_replay_requested')
        return {'event_id':id,'status':'queued'}

    def business_metrics(self,date):
        totals=defaultdict(lambda:{'orders':0,'gross_sales':Decimal(0),'refunds':Decimal(0)})
        with self.db.session() as s:
            facts=list(s.scalars(select(Fact)))
        sources=[]
        for f in facts:
            p=unpack(f.value)
            if f.kind=='order' and p['date']==date:
                t=totals[p['currency']]; t['orders']+=1; t['gross_sales']+=Decimal(str(p['total'])); t['refunds']+=Decimal(str(p.get('refunds',0))); sources.append(f.key)
        with self.db.session() as s:
            day_runs=[r for r in s.scalars(select(Run).order_by(Run.created)) if unpack(r.payload)['timestamp'][:10]==date]
        sentiment=Counter(); recovery=Counter(); inventory={}; run_refs=[]
        for r in day_runs:
            output=unpack(r.result); payload=unpack(r.payload)['payload']
            if r.type=='cart.abandoned': recovery[r.status]+=1
            if output and r.type=='review.created': sentiment[output['sentiment']]+=1; run_refs.append(r.id)
            if output and r.type=='inventory.updated': inventory[payload['sku']]=output['low_stock']; run_refs.append(r.id)
        return {'low_stock_skus':[sku for sku,low in inventory.items() if low], 'review_sentiment':dict(sentiment),
                'recovery_workflow_counts':dict(recovery),'source_runs':run_refs,'date':date,'by_currency':{c:{'orders':t['orders'],'gross_sales':float(t['gross_sales']),'refunds':float(t['refunds']),
                'average_order_value':float((t['gross_sales']/t['orders']).quantize(Decimal('.01'))) if t['orders'] else 0} for c,t in totals.items()},
                'source_records':sources,'note':'Gross sales and refunds kept separate. No cross-currency totals.'}

    def metrics(self):
        with self.db.session() as s:
            runs=list(s.scalars(select(Run))); calls=list(s.scalars(select(ModelCall))); effects=list(s.scalars(select(Effect)))
        counts=Counter(r.status for r in runs)
        # Policy-blocked and rejected events are not eligible successful runs. Pending work stays in denominator.
        eligible=[r for r in runs if r.status not in ('blocked','rejected')]
        success=sum(r.status in ('completed','draft_ready') for r in eligible)
        latency=[r.latency_ms for r in runs if r.latency_ms is not None]
        decisions=[(datetime.fromisoformat(r.decision_at)-datetime.fromisoformat(r.approval_at)).total_seconds() for r in runs if r.decision_at and r.approval_at]
        live_calls=[c for c in calls if c.provider=='live']
        return {'mode':self.settings.mode,'total_events':len(runs),'statuses':dict(counts),'eligible_runs':len(eligible),'successful_runs':success,
            'workflow_success_rate':success/len(eligible) if eligible else None,
            'duplicate_deliveries_suppressed':sum(r.duplicates for r in runs),
            'recorded_effects':sum(e.status=='done' for e in effects),
            'duplicate_effect_keys':len(effects)-len({(e.event_id,e.kind) for e in effects}),
            'schema_valid_outputs':sum(c.valid for c in calls),'schema_outputs':len(calls),
            'schema_pass_rate':sum(c.valid for c in calls)/len(calls) if calls else None,
            'live_schema_pass_rate':sum(c.valid for c in live_calls)/len(live_calls) if live_calls else None,
            'mean_processing_ms':round(sum(latency)/len(latency),2) if latency else None,
            'mean_approval_seconds':round(sum(decisions)/len(decisions),2) if decisions else None,
            'input_tokens':sum(c.input_tokens for c in live_calls),'output_tokens':sum(c.output_tokens for c in live_calls),
            'measured_cost_usd':None,'classification_quality':None,
            'limitations':'Recorded database effects do not prove exactly-once delivery at third-party APIs. Fixture results do not measure model quality. Cost and business impact are unmeasured.'}
