"""Buyer operations: role isolation, local letters/replies, audited access administration."""
import tempfile
from pathlib import Path
from support import DbTestCase,AsgiClient
import test_api as fixture_api
T=fixture_api.T
from aw import seed,handlers,jobs
from aw.settings import load
from aw.context import AppContext
from aw.storage import LocalWormStore
from aw.extraction.providers import HeuristicProvider
from aw.api.app import create_app
from aw.api.operations import csv_bytes
from aw.local_auth import DEMO_PASSWORD

class Operations(DbTestCase):
 h=fixture_api.ApiFlow.h;idem=fixture_api.ApiFlow.idem;etag=fixture_api.ApiFlow.etag;create_and_upload=fixture_api.ApiFlow.create_and_upload
 @classmethod
 def setUpClass(cls):
  super().setUpClass();seed.seed(cls.owner,cls.db);settings=load();cls.secret=settings.dev_token_secret
  cls.ctx=AppContext(settings,cls.db,cls.worker_db,LocalWormStore(Path(tempfile.mkdtemp())),HeuristicProvider());cls.client=AsgiClient(create_app(cls.ctx));cls.worker=jobs.Worker(cls.worker_db,cls.db,handlers.build(cls.ctx))
  from aw import synthetic
  cls.docs=synthetic.claim_documents()
 def test_assignment_dashboard_exports(self):
  cid=self.create_and_upload('CLM-DEMO-0001','trace-1-straightforward');body={'assignee_user_id':'PROC-11'};path=f'/v1/claims/{cid}:assign'
  for user,status in [('PROC-07',403),('SUP-02',200)]:
   r=self.client.post(path,json_body=body,headers=self.idem(user,**{'If-Match':self.etag(user,cid)}));self.assertEqual(r.status,status,r)
  for user,status in [('PROC-07',403),('SUP-02',200),('ADM-01',200)]:self.assertEqual(self.client.get('/v1/operations',headers=self.h(user)).status,status)
  for mode in ('json','csv'):
   r=self.client.get(f'/v1/claims/{cid}/export?format={mode}',headers=self.h('PROC-07'));self.assertEqual(r.status,200,r);self.assertNotIn(b'Arun',r.body)
  self.assertEqual(self.client.get(f'/v1/claims/{cid}/audit-export',headers=self.h('PROC-07')).status,403)
  self.assertTrue(self.client.get(f'/v1/claims/{cid}/audit-export',headers=self.h('SUP-02')).json()['verification']['verified'])
  self.assertIn(b"'=CMD",csv_bytes(['x'],[['=CMD()']]))
 def test_query_unapproved_export_reply_and_nonresponse(self):
  cid=self.create_and_upload('CLM-DEMO-0003','trace-3a-insufficient-conflicting')
  r=self.client.post(f'/v1/claims/{cid}/queries',json_body={'addressed_to':'HOSPITAL','items':[{'text':'Please provide a readable discharge summary.','requested_document_type':'DISCHARGE_SUMMARY'}]},headers=self.idem('PROC-07'));self.assertEqual(r.status,201,r);qid=r.json()['query_id']
  for mode in ('json','pdf'):self.assertEqual(self.client.get(f'/v1/queries/{qid}/letter?format={mode}',headers=self.h('PROC-07')).status,409)
  r=self.client.post(f'/v1/queries/{qid}:approve',headers=self.idem('PROC-07'));self.assertEqual(r.status,200,r)
  pdf=self.client.get(f'/v1/queries/{qid}/letter?format=pdf',headers=self.h('PROC-07'));self.assertEqual(pdf.body[:5],b'%PDF-')
  with self.db.tenant_tx(T) as c:c.execute("UPDATE query_letter SET due_at=now()-interval '1 day' WHERE tenant_id=$1 AND query_id=$2",T,qid)
  r=self.client.post(f'/v1/queries/{qid}:remind',json_body={},headers=self.idem('PROC-07'));self.assertEqual(r.status,200,r)
  with self.db.tenant_tx(T) as c:
   self.assertEqual(c.fetch_val('SELECT status FROM claim WHERE tenant_id=$1 AND claim_id=$2',T,cid),'AWAITING_RESPONSE')
   did=c.fetch_val("SELECT document_id FROM document WHERE tenant_id=$1 AND claim_id=$2 AND classified_type='DISCHARGE_SUMMARY'",T,cid)
  item=self.client.get(f'/v1/claims/{cid}/queries',headers=self.h('PROC-07')).json()['items'][0]['items'][0]['query_item_id']
  for document,status in [('NOT-HERE',422),(did,200)]:
   r=self.client.post(f'/v1/queries/{qid}:answer',json_body={'query_item_id':item,'document_id':document},headers=self.idem('PROC-07'));self.assertEqual(r.status,status,r)
  self.worker.drain()
  with self.db.tenant_tx(T) as c:self.assertEqual(c.fetch_val("SELECT count(*) FROM processing_job WHERE tenant_id=$1 AND state IN ('FAILED_RETRYABLE','FAILED_FINAL')",T),0)
  self.assertEqual(self.client.get(f'/v1/claims/{cid}/queries',headers=self.h('PROC-07')).json()['items'][0]['status'],'ANSWERED')
 def test_user_admin_last_supervisor_and_audit_rls(self):
  body={'user_id':'LOCAL-NEW','display_name':'Synthetic local reviewer','is_active':True,'roles':['PROCESSOR'],'approval_limit':'5000.00','password':'Synthetic-local-2026!','current_password':DEMO_PASSWORD}
  self.assertEqual(self.client.post('/v1/admin/users',json_body=body,headers=self.idem('PROC-07')).status,403)
  r=self.client.post('/v1/admin/users',json_body=body,headers=self.idem('ADM-01'));self.assertEqual(r.status,200,r)
  users=self.client.get('/v1/admin/users',headers=self.h('ADM-01'));self.assertTrue(any(u['user_id']=='LOCAL-NEW' for u in users.json()['items']))
  r=self.client.post('/v1/admin/users',json_body={**body,'user_id':'SUP-02','is_active':False,'roles':['SUPERVISOR']},headers=self.idem('ADM-01'));self.assertEqual(r.status,422,r)
  with self.db.tenant_tx('OTHER') as c:self.assertEqual(c.fetch_val('SELECT count(*) FROM admin_event'),0)
  with self.db.tenant_tx(T) as c:
   self.assertGreater(c.fetch_val('SELECT count(*) FROM admin_event'),0)
   with self.assertRaises(Exception):c.execute("UPDATE admin_event SET action='FORGED'")
