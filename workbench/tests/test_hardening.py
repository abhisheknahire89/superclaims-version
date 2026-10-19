"""Named acceptance cases and route/RBAC/security regression proof."""
import os,sys,time,tempfile,subprocess,unittest,re,json
from pathlib import Path
from support import DbTestCase,AsgiClient
import test_api as fixture_api
from aw import seed,handlers,jobs,auth,synthetic,review,evaluations,audit
from aw.settings import load
from aw.context import AppContext
from aw.storage import LocalWormStore
from aw.extraction.providers import HeuristicProvider
from aw.api.app import create_app
from aw.api.contract import Contract
from aw.backup import restore
T=seed.TENANT

class Hardening(DbTestCase):
 h=fixture_api.ApiFlow.h;idem=fixture_api.ApiFlow.idem;etag=fixture_api.ApiFlow.etag;create_and_upload=fixture_api.ApiFlow.create_and_upload
 @classmethod
 def setUpClass(cls):
  super().setUpClass();seed.seed(cls.owner,cls.db);settings=load();cls.secret=settings.dev_token_secret
  cls.ctx=AppContext(settings,cls.db,cls.worker_db,LocalWormStore(Path(tempfile.mkdtemp())),HeuristicProvider());cls.client=AsgiClient(create_app(cls.ctx));cls.worker=jobs.Worker(cls.worker_db,cls.db,handlers.build(cls.ctx));cls.docs=synthetic.claim_documents()
 def test_TC_REV_01_override_comment_and_stale_target(self):
  with self.db.tenant_tx(T) as c:cid=c.fetch_val("SELECT claim_id FROM claim WHERE tenant_id=$1 AND external_ref='API-CLM-DEMO-0002'",T)
  if cid is None:cid=self.create_and_upload('CLM-DEMO-0002','trace-2-interacting-adjustments')
  ev=self.client.get(f'/v1/claims/{cid}/evaluations/current',headers=self.h('PROC-11')).json();adj=next(a for a in ev['adjustments'] if a.get('line_id')=='L14')
  body={'action':'OVERRIDE_ADJUSTMENT','target':{'type':'adjustment','id':adj['adjustment_id']},'after_value':{'amount':'0.00'},'reason_code':'TARIFF_ITEM_NOT_APPLICABLE','evaluation_id':ev['evaluation_id']}
  r=self.client.post(f'/v1/claims/{cid}/reviewer-actions',json_body=body,headers=self.idem('PROC-11',**{'If-Match':self.etag('PROC-11',cid)}));self.assertEqual(r.status,422,r)
  r=self.client.post(f'/v1/claims/{cid}/reviewer-actions',json_body={**body,'comment':'Synthetic CT performed outside the package.'},headers=self.idem('PROC-11',**{'If-Match':self.etag('PROC-11',cid)}));self.assertEqual(r.status,201,r);self.worker.drain()
  ev2=self.client.get(f'/v1/claims/{cid}/evaluations/current',headers=self.h('PROC-11')).json();self.assertEqual(ev2['recommendation']['recommended_payable'],'85000.00')
  self.assertEqual(next(a for a in ev2['adjustments'] if a.get('line_id')=='L14')['amount'],'0.00')
  r=self.client.post(f'/v1/claims/{cid}/reviewer-actions',json_body={**body,'comment':'Old evaluation'},headers=self.idem('PROC-11',**{'If-Match':self.etag('PROC-11',cid)}));self.assertEqual(r.status,409,r)
 def test_TC_SEC_02_full_role_permissions_and_http(self):
  # Expected role sets transcribed from 03 section4, separate from implementation map.
  r={'PROCESSOR','MEDICAL_OFFICER','SUPERVISOR'};v=r|{'AUDITOR','FWA_ANALYST','READ_ONLY'}
  expected={'claim.view':v,'claim.create':{'PROCESSOR','SUPERVISOR'},'claim.assign':{'SUPERVISOR'},'claim.withdraw':{'SUPERVISOR'},'claim.reopen':{'SUPERVISOR'},'document.upload':r,'fact.correct':r,'line.reclassify':r,'adjustment.override':r,'finding.resolve_clinical':{'MEDICAL_OFFICER'},'finding.resolve':r,'finding.dismiss_high_anomaly':{'SUPERVISOR','FWA_ANALYST'},'claim.hold':{'SUPERVISOR','FWA_ANALYST'},'query.draft':r,'query.approve':r,'decision.approve':r,'decision.repudiate':{'SUPERVISOR'},'decision.close_duplicate':{'SUPERVISOR'},'decision.second_approve':{'SUPERVISOR'},'audit.export':{'AUDITOR','SUPERVISOR'},'config.author':{'CONFIG_ADMIN'},'config.publish':{'CONFIG_ADMIN','TENANT_ADMIN'},'admin.users':{'TENANT_ADMIN'}}
  self.assertEqual(set(expected),set(auth.PERMISSIONS))
  cid=self.create_and_upload('CLM-DEMO-0003','trace-3a-insufficient-conflicting')
  for uid,_,roles,_ in seed.USERS:
   role=roles[0];principal=auth.Principal(uid,T,{role})
   for action,allowed in expected.items():
    with self.subTest(role=role,action=action):
     if role in allowed:principal.require(action)
     else:
      with self.assertRaises(auth.Forbidden):principal.require(action)
   for path,allowed in [(f'/v1/claims/{cid}',v),('/v1/admin/users',{'TENANT_ADMIN'}),('/v1/operations',{'SUPERVISOR','TENANT_ADMIN'}),(f'/v1/claims/{cid}/audit-export',{'SUPERVISOR','AUDITOR'})]:
    response=self.client.get(path,headers=self.h(uid));self.assertEqual(response.status,200 if role in allowed else 403,(uid,path,response))
  with self.db.tenant_tx(T) as c:fid=c.fetch_val("SELECT finding_id FROM finding WHERE tenant_id=$1 AND claim_id=$2 AND category='CLINICAL' LIMIT 1",T,cid)
  self.assertIsNotNone(fid)
  body={'action':'RESOLVE_FINDING','target':{'type':'finding','id':fid},'after_value':{'outcome':'NO_FINANCIAL_EFFECT'},'reason_code':'MEDICAL_REVIEW_COMPLETED','comment':'Synthetic review'}
  self.assertEqual(self.client.post(f'/v1/claims/{cid}/reviewer-actions',json_body=body,headers=self.idem('SUP-02',**{'If-Match':self.etag('SUP-02',cid)})).status,403)
 def test_contract_routes_synchronized_both_directions(self):
  contract=Contract(self.ctx.settings.pack_dir);app=create_app(self.ctx)
  raw={'devLogin','index','health','readiness','getPageImage','getPageWords','putUpload'}
  actual={route.name:(re.sub(r':int','',route.path),next(iter(route.methods))) for route in app.routes if getattr(route,'methods',None) and route.name not in raw|{'openapi_doc'}}
  expected={name:('/v1'+op['path'],op['method']) for name,op in contract.ops.items()}
  self.assertEqual(actual,expected)
 def test_TC_REL_04_actual_worker_kill_rolls_back_and_recovers(self):
  cid=self.create_and_upload('CLM-DEMO-0002','trace-2-interacting-adjustments')
  with self.db.tenant_tx(T) as c:
   p=auth.load_principal(c,T,'PROC-11');ev=evaluations.current(c,T,cid);adj=c.fetch_val("SELECT a.adjustment_id FROM adjustment a JOIN bill_line b ON b.tenant_id=a.tenant_id AND b.bill_line_id=a.bill_line_id WHERE a.tenant_id=$1 AND a.evaluation_id=$2 AND b.line_no='L14'",T,ev['evaluation_id'])
   review.record(c,p,cid,{'action':'OVERRIDE_ADJUSTMENT','target':{'type':'adjustment','id':adj},'after_value':{'amount':'0.00'},'reason_code':'TARIFF_ITEM_NOT_APPLICABLE','comment':'Synthetic crash test'})
   before=c.fetch_val('SELECT count(*) FROM evaluation WHERE tenant_id=$1 AND claim_id=$2',T,cid)
  ready=Path(tempfile.mkdtemp())/'ready';env={**os.environ,'AW_DATABASE_URL':self.db.dsn,'AW_WORKER_DSN':self.worker_db.dsn,'AW_ENV':'test','AW_OBJECT_STORE_DIR':str(self.ctx.store.root),'AW_CRASH_READY':str(ready)}
  script="""import os,time
from pathlib import Path
from aw.context import build
from aw.settings import load
from aw import handlers,jobs
ctx=build(load());normal=handlers.build(ctx)['EVALUATE']
def crash(c,j):
 normal(c,j)
 Path(os.environ['AW_CRASH_READY']).write_text('evaluation written before commit')
 while True:time.sleep(1)
jobs.Worker(ctx.worker_db,ctx.db,{'EVALUATE':crash}).run_once()
"""
  process=subprocess.Popen([sys.executable,'-c',script],env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
  try:
   deadline=time.monotonic()+10
   while not ready.exists() and process.poll() is None and time.monotonic()<deadline:time.sleep(.05)
   self.assertTrue(ready.exists(),'worker did not reach evaluation writes');process.kill();process.wait(5)
  finally:
   if process.poll() is None:process.kill();process.wait(5)
  with self.db.tenant_tx(T) as c:
   self.assertEqual(c.fetch_val('SELECT count(*) FROM evaluation WHERE tenant_id=$1 AND claim_id=$2',T,cid),before)
   c.execute("UPDATE processing_job SET locked_until=now()-interval '1 second' WHERE tenant_id=$1 AND subject_id=$2 AND state='RUNNING'",T,cid)
  self.worker.drain()
  with self.db.tenant_tx(T) as c:
   self.assertEqual(c.fetch_val('SELECT count(*) FROM evaluation WHERE tenant_id=$1 AND claim_id=$2',T,cid),before+1)
   self.assertEqual(c.fetch_val("SELECT count(*) FROM processing_job WHERE tenant_id=$1 AND subject_id=$2 AND state='RUNNING'",T,cid),0)
   self.assertTrue(audit.verify_chain(c,T,cid)['verified']);self.assertEqual(evaluations.current(c,T,cid)['recommended_payable_paise'],8500000)
 def test_restore_rejects_tamper_before_creation(self):
  root=Path(tempfile.mkdtemp());(root/'database.dump').write_bytes(b'bad');(root/'objects').mkdir();(root/'manifest.json').write_text(json.dumps({'version':1,'files':{'database.dump':'0'*64}}))
  with self.assertRaises(ValueError):restore(self.owner.dsn,root,'aw_restore_never_created',root/'new')
  with self.owner.connection() as c:self.assertFalse(c.fetch_val("SELECT 1 FROM pg_database WHERE datname='aw_restore_never_created'"))
 def test_independent_review_idempotency_does_not_grant_authority(self):
  import uuid
  f=seed._fixture('trace-1-straightforward');body={'external_ref':'SEC-IDEM','workflow':'IPD_REIMBURSEMENT','policy_no':f['policy']['policy_no'],'member_id':f['member']['member_id'],'hospital_id':f['hospital_id']};key=str(uuid.uuid4());headers=self.h('PROC-07',**{'Idempotency-Key':key})
  response=self.client.post('/v1/claims',json_body=body,headers=headers);self.assertEqual(response.status,201,response)
  self.assertEqual(self.client.post('/v1/claims',json_body=body,headers=headers).status,201)
  cross=self.client.post('/v1/claims',json_body=body,headers=self.h('CFG-01',**{'Idempotency-Key':key}));self.assertEqual(cross.status,409,cross);self.assertNotIn(b'patient',cross.body)
  with self.db.tenant_tx(T) as c:c.execute("UPDATE role_assignment SET valid_to=now() WHERE tenant_id=$1 AND user_id='PROC-07' AND valid_to IS NULL",T)
  try:self.assertEqual(self.client.post('/v1/claims',json_body=body,headers=headers).status,409)
  finally:
   with self.db.tenant_tx(T) as c:c.execute("UPDATE role_assignment SET valid_to=NULL WHERE tenant_id=$1 AND user_id='PROC-07'",T)
 def test_independent_review_second_approver_missing_limit_fails_closed(self):
  from aw.decisions import approve_request,request_approval
  cid=self.create_and_upload('CLM-DEMO-0001','trace-1-straightforward')
  with self.db.tenant_tx(T) as c:
   p=auth.load_principal(c,T,'PROC-07');ev=evaluations.current(c,T,cid);ar=request_approval(c,p,cid,{'evaluation_id':ev['evaluation_id'],'proposed_disposition':'APPROVED_PARTIAL','proposed_payable':'107591.00','approver_user_id':'SUP-02'})
  with self.db.tenant_tx(T) as c:
   supervisor=auth.Principal('SUP-02',T,{'SUPERVISOR'},None)
   with self.assertRaises(auth.Forbidden):approve_request(c,supervisor,self.ctx.schema_dir,ar['approval_request_id'])
 def test_independent_review_closed_queries_rejected(self):
  with self.db.tenant_tx(T) as c:cid=c.fetch_val("SELECT claim_id FROM claim WHERE tenant_id=$1 AND external_ref='API-CLM-DEMO-0003'",T)
  if cid is None:cid=self.create_and_upload('CLM-DEMO-0003','trace-3a-insufficient-conflicting')
  body={'addressed_to':'HOSPITAL','items':[{'text':'Synthetic readable copy.'}]}
  draft=self.client.post(f'/v1/claims/{cid}/queries',json_body=body,headers=self.idem('PROC-11'));self.assertEqual(draft.status,201,draft)
  with self.db.tenant_tx(T) as c:c.execute("UPDATE claim SET status='FINALISED' WHERE tenant_id=$1 AND claim_id=$2",T,cid)
  self.assertEqual(self.client.post(f'/v1/claims/{cid}/queries',json_body=body,headers=self.idem('PROC-11')).status,409)
  self.assertEqual(self.client.post(f"/v1/queries/{draft.json()['query_id']}:approve",headers=self.idem('PROC-11')).status,409)
 def test_restore_rejects_unlisted_file_and_symlink(self):
  import hashlib
  root=Path(tempfile.mkdtemp());(root/'database.dump').write_bytes(b'synthetic');(root/'objects').mkdir();(root/'objects'/'unlisted').write_bytes(b'ignored corruption')
  (root/'manifest.json').write_text(json.dumps({'version':1,'files':{'database.dump':hashlib.sha256(b'synthetic').hexdigest()}}))
  with self.assertRaisesRegex(ValueError,'file set'):restore(self.owner.dsn,root,'aw_restore_omission_rejected',root/'new')
  (root/'objects'/'unlisted').unlink();(root/'objects'/'link').symlink_to(root/'database.dump')
  with self.assertRaisesRegex(ValueError,'symlinks'):restore(self.owner.dsn,root,'aw_restore_symlink_rejected',root/'new')
 def test_inherited_receiver_platform_rbac(self):
  body={'event_id':'SYNTHETIC-SECURITY','event_type':'CLAIM_WITHDRAWN','external_ref':'SEC-IDEM'}
  for uid in ('RO-01','CFG-01','PROC-07'):
   response=self.client.post('/v1/integrations/tms/events',json_body=body,headers=self.idem(uid));self.assertEqual(response.status,403,response)

 def test_interrupted_object_publication_recovers_identical_bytes_only(self):
  from aw.storage import ImmutableObjectError
  root=Path(tempfile.mkdtemp());store=LocalWormStore(root);(root/'original').write_bytes(b'synthetic immutable original')
  with self.assertRaises(ImmutableObjectError):store.get('original')
  store.put_once('original',b'synthetic immutable original');self.assertEqual(store.get('original'),b'synthetic immutable original')
  with self.assertRaises(ImmutableObjectError):store.put_once('original',b'different')
  (root/'corrupt').write_bytes(b'same');(root/'corrupt.sha256').write_text('bad')
  with self.assertRaises(ImmutableObjectError):store.put_once('corrupt',b'same')
