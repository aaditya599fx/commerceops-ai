import base64
import hashlib
import hmac

import pytest

from backend.shopify import Shopify

RAW=b'{"id":1,"title":"Synthetic verification product"}'
def signature(secret,raw=RAW):
    return base64.b64encode(hmac.new(secret.encode(),raw,hashlib.sha256).digest()).decode()


@pytest.mark.parametrize('signing_key',['fixture-current-secret','fixture-previous-secret'])
def test_active_rotation_keys_validate_exact_raw_body(monkeypatch,signing_key):
    monkeypatch.setenv('SHOPIFY_SHOP','configured.myshopify.com')
    monkeypatch.setenv('SHOPIFY_WEBHOOK_SECRET','fixture-current-secret')
    monkeypatch.setenv('SHOPIFY_PREVIOUS_WEBHOOK_SECRET','fixture-previous-secret')
    adapter=Shopify(None,None,None)
    signed=signature(signing_key)
    assert adapter.verify(RAW,signed,'configured.myshopify.com')
    assert not adapter.verify(RAW+b' ',signed,'configured.myshopify.com')
    assert not adapter.verify(RAW,signed,'other.myshopify.com')
    assert not adapter.verify(RAW,'','configured.myshopify.com')


def test_removed_previous_secret_stops_verifying(monkeypatch):
    monkeypatch.setenv('SHOPIFY_SHOP','configured.myshopify.com')
    monkeypatch.setenv('SHOPIFY_WEBHOOK_SECRET','fixture-current-secret')
    monkeypatch.delenv('SHOPIFY_PREVIOUS_WEBHOOK_SECRET',raising=False)
    adapter=Shopify(None,None,None)
    assert not adapter.verify(RAW,signature('fixture-previous-secret'),'configured.myshopify.com')
    assert adapter.verify(RAW,signature('fixture-current-secret'),'configured.myshopify.com')


def test_previous_secret_does_not_mask_missing_primary_configuration(monkeypatch):
    monkeypatch.setenv('SHOPIFY_SHOP','configured.myshopify.com')
    monkeypatch.delenv('SHOPIFY_WEBHOOK_SECRET',raising=False)
    monkeypatch.setenv('SHOPIFY_PREVIOUS_WEBHOOK_SECRET','fixture-previous-secret')
    assert not Shopify(None,None,None).verify(RAW,signature('fixture-previous-secret'),'configured.myshopify.com')
