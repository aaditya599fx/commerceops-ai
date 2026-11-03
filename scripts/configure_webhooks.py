"""Plan/apply minimal Shopify subscriptions. No orders/products are modified."""
import argparse,asyncio,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backend.config import ROOT,Settings
from backend.db import DB
from backend.providers import Providers,ProviderError
from backend.engine import Engine
from backend.shopify import Shopify

async def main(apply):
    cfg=Settings();db=DB(cfg.database_url);p=Providers(cfg,db)
    try:
        result=await Shopify(p.client,db,Engine(cfg,db,p)).configure_webhooks(cfg.base_url,apply=apply)
        (ROOT/'runtime/webhook-configuration.json').write_text(json.dumps(result,indent=2)+'\n')
        print(json.dumps(result,indent=2))
    except ProviderError as e:
        print(json.dumps({'status':'failed','category':e.category}));raise SystemExit(1)
    finally:await p.close()
if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--apply',action='store_true');args=parser.parse_args()
    asyncio.run(main(args.apply))
