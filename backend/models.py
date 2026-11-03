from datetime import datetime
from decimal import Decimal
from typing import Literal, Annotated
from pydantic import BaseModel, ConfigDict, Field, AwareDatetime, field_validator, model_validator

class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)

class Item(StrictModel):
    sku: str = Field(min_length=1, max_length=100)
    title: str = Field(min_length=1, max_length=300)
    quantity: int = Field(ge=1, le=10000)
    price: float = Field(ge=0, le=1000000)

class Cart(StrictModel):
    customer_id: str = Field(min_length=1, max_length=100)
    cart_id: str = Field(min_length=1, max_length=100)
    email: str = Field(pattern=r'^[^\s@]+@[^\s@]+\.[^\s@]+$', max_length=254)
    consent: bool
    items: list[Item] = Field(min_length=1, max_length=100)
    value: float = Field(ge=0, le=10000000)
    currency: str = Field(pattern=r'^[A-Z]{3}$')
    recent_purchase: bool = False
    @model_validator(mode='after')
    def total(self):
        total=sum(Decimal(str(x.price))*x.quantity for x in self.items)
        if abs(total-Decimal(str(self.value))) > Decimal('0.01'):
            raise ValueError('Cart value must match item totals')
        return self

class Inventory(StrictModel):
    sku: str = Field(min_length=1, max_length=100)
    available: int = Field(ge=0, le=100000000)
    daily_units: float = Field(ge=0, le=10000000)
    lead_days: int = Field(ge=0, le=365)

class Review(StrictModel):
    product_id: str = Field(min_length=1, max_length=100)
    rating: int = Field(ge=1, le=5)
    text: str = Field(min_length=1, max_length=5000)

class Product(StrictModel):
    product_id: str = Field(min_length=1, max_length=100)
    title: str = Field(min_length=1, max_length=300)
    description: str = Field(min_length=1, max_length=5000)
    attributes: list[str] = Field(max_length=30)
    verified_faqs: list[str] = Field(max_length=30)

class Customer(StrictModel):
    customer_id: str = Field(min_length=1, max_length=100)
    email: str = Field(pattern=r'^[^\s@]+@[^\s@]+\.[^\s@]+$', max_length=254)
    orders: int = Field(ge=0, le=1000000)
    total_spend: float = Field(ge=0, le=100000000)
    currency: str = Field(pattern=r'^[A-Z]{3}$')
    days_since_order: int = Field(ge=0, le=100000)

class Brief(StrictModel):
    date: str = Field(pattern=r'^\d{4}-\d{2}-\d{2}$')

PAYLOADS={'cart.abandoned':Cart,'inventory.updated':Inventory,'review.created':Review,
          'product.created':Product,'customer.updated':Customer,'brief.requested':Brief}

class Event(BaseModel):
    model_config=ConfigDict(extra='forbid')
    event_id: str = Field(pattern=r'^[a-zA-Z0-9][a-zA-Z0-9_.:-]{0,159}$')
    type: Literal['cart.abandoned','inventory.updated','review.created','product.created','customer.updated','brief.requested']
    timestamp: AwareDatetime
    source: Literal['synthetic','shopify','import'] = 'synthetic'
    payload: dict
    @model_validator(mode='after')
    def validate_payload(self):
        self.payload=PAYLOADS[self.type].model_validate(self.payload).model_dump(mode='json')
        return self

class Draft(StrictModel):
    intent: Literal['high_intent','browsing','unknown']
    segment: Literal['first_time_customer','returning_customer','unknown']
    message_subject: str = Field(min_length=1, max_length=100)
    message_body: str = Field(min_length=1, max_length=600)
    recommended_channel: Literal['email']
    risk_flags: list[str] = Field(max_length=10)
    requires_human_approval: Literal[True]

class ReviewResult(StrictModel):
    sentiment: Literal['positive','neutral','negative']
    issue_category: Literal['quality','delivery','sizing','support','packaging','other']
    urgency: Literal['low','medium','high']
    evidence_quote: str = Field(min_length=1, max_length=300)

class Summary(StrictModel):
    summary: str = Field(min_length=1, max_length=1200)
    recommendation: str = Field(min_length=1, max_length=500)

class Growth(StrictModel):
    seo_title: str = Field(min_length=1, max_length=70)
    meta_description: str = Field(min_length=1, max_length=160)
    answer: str = Field(min_length=1, max_length=500)
    faq_candidates: list[str] = Field(max_length=5)

class Decision(StrictModel):
    decision: Literal['approve','reject']
    reason: str = Field(min_length=1, max_length=300)
