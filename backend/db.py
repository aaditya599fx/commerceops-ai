import json
from datetime import datetime, timezone
from sqlalchemy import create_engine, event, String, Text, Integer, Float, Boolean, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker
from .config import ROOT

def now(): return datetime.now(timezone.utc).isoformat()
def dump(x): return json.dumps(x, ensure_ascii=False, default=str)
def unpack(x): return json.loads(x) if x else None

class Base(DeclarativeBase): pass
class Run(Base):
    __tablename__='runs'
    id: Mapped[str]=mapped_column(String(160),primary_key=True)
    type: Mapped[str]=mapped_column(String(50))
    source: Mapped[str]=mapped_column(String(30))
    payload: Mapped[str]=mapped_column(Text)
    status: Mapped[str]=mapped_column(String(40),default='queued',index=True)
    result: Mapped[str | None]=mapped_column(Text,nullable=True)
    error: Mapped[str | None]=mapped_column(String(200),nullable=True)
    created: Mapped[str]=mapped_column(String(50),default=now)
    updated: Mapped[str]=mapped_column(String(50),default=now)
    attempts: Mapped[int]=mapped_column(Integer,default=0)
    duplicates: Mapped[int]=mapped_column(Integer,default=0)
    latency_ms: Mapped[float | None]=mapped_column(Float,nullable=True)
    approval_at: Mapped[str | None]=mapped_column(String(50),nullable=True)
    decision_at: Mapped[str | None]=mapped_column(String(50),nullable=True)
    actor: Mapped[str | None]=mapped_column(String(100),nullable=True)
    reason: Mapped[str | None]=mapped_column(String(300),nullable=True)

class Audit(Base):
    __tablename__='audit'
    id: Mapped[int]=mapped_column(Integer,primary_key=True,autoincrement=True)
    event_id: Mapped[str]=mapped_column(String(160),index=True)
    at: Mapped[str]=mapped_column(String(50),default=now)
    action: Mapped[str]=mapped_column(String(80))
    detail: Mapped[str]=mapped_column(Text,default='{}')

class Effect(Base):
    __tablename__='effects'
    __table_args__=(UniqueConstraint('event_id','kind'),)
    id: Mapped[int]=mapped_column(Integer,primary_key=True,autoincrement=True)
    event_id: Mapped[str]=mapped_column(String(160),index=True)
    kind: Mapped[str]=mapped_column(String(40))
    status: Mapped[str]=mapped_column(String(30),default='pending')
    payload: Mapped[str]=mapped_column(Text)
    remote_id: Mapped[str | None]=mapped_column(String(200),nullable=True)
    error: Mapped[str | None]=mapped_column(String(200),nullable=True)
    created: Mapped[str]=mapped_column(String(50),default=now)
    updated: Mapped[str]=mapped_column(String(50),default=now)

class ModelCall(Base):
    __tablename__='model_calls'
    id: Mapped[int]=mapped_column(Integer,primary_key=True,autoincrement=True)
    event_id: Mapped[str]=mapped_column(String(160),index=True)
    provider: Mapped[str]=mapped_column(String(30))
    valid: Mapped[bool]=mapped_column(Boolean)
    input_tokens: Mapped[int]=mapped_column(Integer,default=0)
    output_tokens: Mapped[int]=mapped_column(Integer,default=0)
    at: Mapped[str]=mapped_column(String(50),default=now)

class Fact(Base):
    __tablename__='facts'
    key: Mapped[str]=mapped_column(String(200),primary_key=True)
    kind: Mapped[str]=mapped_column(String(30),index=True)
    value: Mapped[str]=mapped_column(Text)
    source: Mapped[str]=mapped_column(String(30))

class DB:
    def __init__(self,url):
        (ROOT/'runtime').mkdir(exist_ok=True)
        opts={'check_same_thread':False,'timeout':30} if url.startswith('sqlite') else {}
        self.engine=create_engine(url,connect_args=opts)
        if url.startswith('sqlite'):
            @event.listens_for(self.engine,'connect')
            def setup(conn,_):
                conn.execute('PRAGMA journal_mode=WAL')
                conn.execute('PRAGMA foreign_keys=ON')
        Base.metadata.create_all(self.engine)
        self.session=sessionmaker(self.engine,expire_on_commit=False)
    def audit(self,s,event_id,action,**detail):
        s.add(Audit(event_id=event_id,action=action,detail=dump(detail)))
