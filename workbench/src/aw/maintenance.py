"""Tenant-scoped local maintenance scheduling; notifications remain inside the workbench."""
import logging,time
from datetime import date
from . import jobs,configs,tat,audit,anchors

def scan(conn,tenant):
 cfg=configs.effective(conn,tenant,'WORKFLOW_CONFIG',date.today()) or {}
 count=0
 for claim in conn.fetch_all("SELECT * FROM claim WHERE tenant_id=$1 AND status NOT IN ('FINALISED','EXPORTED','WITHDRAWN')",tenant):
  if tat.breached(claim,cfg):
   conn.execute('INSERT INTO deadline_alert (tenant_id,claim_id,due_at) VALUES ($1,$2,$3) ON CONFLICT DO NOTHING',tenant,claim['claim_id'],tat.deadline(claim,cfg));count+=1
 return count

def schedule(ctx):
 # Poll role sees queued jobs; tenant enumeration is derived from jobs, never clinical records.
 with ctx.worker_db.system_tx() as c:tenants=[r['tenant_id'] for r in c.fetch_all('SELECT DISTINCT tenant_id FROM processing_job')]
 for tenant in tenants:
  with ctx.db.tenant_tx(tenant) as c:
   scan(c,tenant)
   for claim in c.fetch_all('SELECT claim_id FROM claim WHERE tenant_id=$1',tenant):
    proof=audit.verify_chain(c,tenant,claim['claim_id'])
    if proof['verified'] and proof['events']:jobs.enqueue(c,tenant,'AUDIT_ANCHOR',claim['claim_id'],f"anchor:{claim['claim_id']}:{proof['head']}",{})

def forever(ctx):
 while True:
  try:schedule(ctx)
  except Exception as e:logging.getLogger('aw.maintenance').warning('maintenance error_code=%s',type(e).__name__)
  time.sleep(60)
