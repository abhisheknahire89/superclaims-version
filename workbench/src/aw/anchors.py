"""Local tamper-evidence anchors; a host administrator can replace both DB and store."""
import json
from . import audit
from .ids import new_id,canonical_json

def anchor(conn,store,tenant,claim):
 proof=audit.verify_chain(conn,tenant,claim)
 if not proof['verified']:raise ValueError('AUDIT_CHAIN_INVALID')
 ident=new_id('ANCH');key=f'{tenant}/audit-anchors/{claim}/{ident}.json'
 body={'tenant_id':tenant,'claim_id':claim,'events':proof['events'],'head':proof['head']}
 store.put_once(key,canonical_json(body))
 conn.execute('INSERT INTO audit_anchor (tenant_id,anchor_id,claim_id,seq,head,object_key) VALUES ($1,$2,$3,$4,$5,$6)',tenant,ident,claim,proof['events'],proof['head'],key)
 return {'anchor_id':ident,**body}

def verify(conn,store,tenant,claim):
 rows=conn.fetch_all('SELECT * FROM audit_anchor WHERE tenant_id=$1 AND claim_id=$2 ORDER BY created_at',tenant,claim)
 for row in rows:
  body=json.loads(store.get(row['object_key']))
  head=conn.fetch_val('SELECT event_hash FROM audit_event WHERE tenant_id=$1 AND claim_id=$2 AND seq=$3',tenant,claim,row['seq'])
  if body['head']!=row['head'] or head!=row['head']:return {'verified':False,'anchors':len(rows)}
 return {'verified':True,'anchors':len(rows)}
