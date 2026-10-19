"""Read the actual restored application using its restricted role and local login."""
import sys,json,os
from dataclasses import replace
from urllib.parse import urlsplit,urlunsplit
from pathlib import Path
from support import AsgiClient
from aw.context import build
from aw.settings import load
from aw.api.app import create_app
settings=load();database=sys.argv[1];objects=Path(sys.argv[2]);change=lambda d:urlunsplit(urlsplit(d)._replace(path='/'+database))
ctx=build(replace(settings,database_url=change(settings.database_url),worker_dsn=change(settings.worker_dsn),object_store_dir=objects));client=AsgiClient(create_app(ctx))
r=client.post('/v1/auth/login',json_body={'tenant_id':'TENANT-DEMO','user_id':'PROC-07','password':'Synthetic-demo-2026!'});assert r.status==200,r
headers={'Cookie':r.headers['set-cookie'].split(';')[0]};r=client.get('/v1/claims/CLM-DEMO-OPD',headers=headers);assert r.status==200,r
with ctx.db.tenant_tx('TENANT-DEMO') as c:count=c.fetch_val('SELECT count(*) FROM claim')
with ctx.db.tenant_tx('OTHER-TENANT') as c:other=c.fetch_val('SELECT count(*) FROM claim');assert other==0
print(json.dumps({'restored_database':database,'login':200,'claim_read':200,'claims':count,'other_tenant_visible':other,'role':'aw_app'}));ctx.db.close();ctx.worker_db.close()
