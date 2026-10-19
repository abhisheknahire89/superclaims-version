import sys,unittest,json
sys.path.insert(0,'/Users/abhishekpravinnahire/Desktop/SUperclaims/workbench/tests')
from tests.test_policy_intelligence import ProductHistoryReview
from aw.policy_intelligence import registry,history
from aw import auth
class Probe(ProductHistoryReview):
 def test_cross_tenant_global_rejection(self):
  sid=self.source_fixture();entry=self.lib.entries()[0];body=dict(entry['body'],line=2,import_sha256='a'*64)
  data=self.lib.original(self.lib.report()['retrievals'][0]['sha256']).read_bytes();self.lib.record('real-shaped',body,'DISCOVERED',[]);self.lib.preserve('real-shaped',data,{})
  with self.db.tenant_tx('TENANT-DEMO') as c:
   sid=registry.intake(c,self.author,self.ctx,'real-shaped')['source_id'];registry.verify(c,self.approver,self.ctx,sid,self.verification())
  with self.owner.connection() as c:c.execute("INSERT INTO tenant(tenant_id,legal_name,tenant_kind) VALUES('TENANT-B','Synthetic B','INSURER')")
  other=auth.Principal('B-ADMIN','TENANT-B',{'TENANT_ADMIN'})
  with self.db.tenant_tx('TENANT-B') as c:
   out=history.remediate(c,other,self.ctx,'real-shaped',{'reason':'Other tenant rejects shared source'},True)
  self.assertEqual(self.lib.db.execute("SELECT state FROM discovery WHERE id='real-shaped'").fetchone()[0],'CONTENT_VERIFIED')
  with self.db.tenant_tx('TENANT-DEMO') as c:
   self.assertEqual(c.fetch_val("SELECT count(*) FROM policy_knowledge_record WHERE kind='ResearchRemediation'"),0)
   registry.source(c,'TENANT-DEMO',sid,self.ctx,True)
   with self.assertRaises(Exception):history.remediate(c,self.approver,self.ctx,'real-shaped',{'reason':'Cannot silently revoke approved source'},True)
  print('CROSS_TENANT_GLOBAL_JOURNAL_AND_APPROVED_SOURCE_UNCHANGED')
 def test_sqlite_mutation_survives_postgres_rollback(self):
  self.lib.record('bad',{'insurer':'STAR','uin':'XXX','product_name':'x'},'METADATA_CONFLICT',['bad UIN'])
  with self.db.tenant_tx('TENANT-DEMO') as c:before=c.fetch_val('SELECT count(*) FROM policy_review_event')
  try:
   with self.db.tenant_tx('TENANT-DEMO') as c:
    history.remediate(c,self.approver,self.ctx,'bad',{'reason':'Reviewed invalid research entry'},True)
    raise RuntimeError('request transaction failure')
  except RuntimeError:pass
  with self.db.tenant_tx('TENANT-DEMO') as c:after=c.fetch_val('SELECT count(*) FROM policy_review_event')
  self.assertEqual(self.lib.db.execute("SELECT state FROM discovery WHERE id='bad'").fetchone()[0],'METADATA_CONFLICT');self.assertEqual(before,after)
  with self.db.tenant_tx('TENANT-DEMO') as c:self.assertEqual(c.fetch_val("SELECT count(*) FROM policy_knowledge_record WHERE kind='ResearchRemediation'"),0)
  print('REMEDIATION_RECORD_AND_EVENT_ROLLBACK_ATOMIC_SHARED_JOURNAL_UNCHANGED')
 def test_unrelated_names_and_wrong_evidence_hash(self):
  sid=self.source_fixture()
  with self.db.tenant_tx('TENANT-DEMO') as c:
   registry.verify(c,self.approver,self.ctx,sid,self.verification())
   data={'change':'RENAME','names':['Co-payment','Wording'],'evidence':[{'source_id':sid,'page':1,'quote':'1. Co-payment is 10% of admissible claim amount.','sha256':'f'*64},{'source_id':sid,'page':1,'quote':'Wording effective from 2026-01-01.'}],'interpretation':'Propose unrelated quoted words as product names','context_reviewed':True,'review_required':True}
   with self.assertRaises(Exception):history.propose(c,self.author,self.ctx,'STAR:SHAHLIP21025V052021',data)
   data['names']=['One','Star Health One'];data['evidence']=[{'source_id':sid,'page':1,'quote':'Star Health One','sha256':'f'*64}]
   with self.assertRaises(Exception):history.propose(c,self.author,self.ctx,'STAR:SHAHLIP21025V052021',data)
   del data['evidence'][0]['sha256'];proposal=history.propose(c,self.author,self.ctx,'STAR:SHAHLIP21025V052021',data)
   with self.assertRaises(Exception):history.approve(c,self.author,self.ctx,proposal['proposal_id'])
   result=history.approve(c,self.approver,self.ctx,proposal['proposal_id'])
   source,_=registry.source(c,'TENANT-DEMO',sid,self.ctx,True);self.assertEqual(result['evidence'][0]['sha256'],source['body']['sha256'])
  print('UNRELATED_NAMES_AND_FAKE_HASH_REJECTED_VALID_FOUR_EYES_RENAME_CANONICAL_HASH_PASSED')

 def test_pending_identity_cannot_extract_until_rename_approved(self):
  from aw.policy_intelligence import extraction
  sid=self.source_fixture();entry=self.lib.entries()[0];body=dict(entry['body'],product_name='Star Health One')
  original=self.lib.original(self.lib.report()['retrievals'][0]['sha256']).read_bytes()
  with self.db.tenant_tx('TENANT-DEMO') as c:registry.verify(c,self.approver,self.ctx,sid,self.verification())
  self.lib.record('alias',body,'DISCOVERED',[]);self.lib.preserve('alias',original,{})
  self.lib.record('alias',body,'METADATA_CONFLICT',['UIN reused across conflicting product identities'])
  with self.db.tenant_tx('TENANT-DEMO') as c:
   alias=registry.intake(c,self.author,self.ctx,'alias')['source_id'];pending=registry.verify(c,self.approver,self.ctx,alias,self.verification())
   self.assertEqual(pending['state'],'NEEDS_HUMAN_REVIEW')
   with self.assertRaises(Exception):extraction.extract(c,self.author,self.ctx,alias)
   data={'change':'RENAME','names':['One','Star Health One'],'evidence':[{'source_id':alias,'page':1,'quote':'Star Health One'}],'interpretation':'Illustrative full-title alias evidence','context_reviewed':True,'review_required':True}
   proposal=history.propose(c,self.author,self.ctx,'STAR:SHAHLIP21025V052021',data);history.approve(c,self.approver,self.ctx,proposal['proposal_id'])
   approved=registry.verify(c,self.approver,self.ctx,alias,self.verification());self.assertEqual(approved['state'],'APPROVED_SOURCE')
   output=extraction.extract(c,self.author,self.ctx,alias);self.assertGreater(output['count'],0)
   self.assertEqual(c.fetch_val("SELECT count(*) FROM policy_rule_candidate WHERE state<>'DRAFT'"),0)
  print('PENDING_IDENTITY_EXTRACTION_BLOCKED_UNTIL_TWO_PERSON_RENAME_AND_SOURCE_REVIEW_ONLY_DRAFT_RULES')


 def test_api_role_and_password_guards(self):
  from aw.api.app import create_app
  from tests.support import AsgiClient
  import uuid
  self.lib.record('bad',{'insurer':'STAR','uin':'XXX','product_name':'x'},'METADATA_CONFLICT',['bad UIN'])
  client=AsgiClient(create_app(self.ctx));body={'action':'reject_research','target':'bad','data':{'reason':'Reject invalid source safely'}}
  h={'Authorization':'Bearer '+auth.issue_dev_token(self.ctx.settings.dev_token_secret,'PROC-07','TENANT-DEMO'),'Idempotency-Key':str(uuid.uuid4())}
  self.assertEqual(client.post('/v1/policy-intelligence/actions',headers=h,json_body=body).status,403)
  h={'Authorization':'Bearer '+auth.issue_dev_token(self.ctx.settings.dev_token_secret,'ADM-01','TENANT-DEMO'),'Idempotency-Key':str(uuid.uuid4())}
  self.assertEqual(client.post('/v1/policy-intelligence/actions',headers=h,json_body=body).status,401)
  h['Idempotency-Key']=str(uuid.uuid4());body['data']['current_password']='incorrect'
  self.assertEqual(client.post('/v1/policy-intelligence/actions',headers=h,json_body=body).status,401)
  with self.db.tenant_tx('TENANT-DEMO') as c:self.assertEqual(c.fetch_val("SELECT count(*) FROM policy_knowledge_record WHERE kind='ResearchRemediation' AND body->>'research_id'='bad'"),0)
  print('API_PROCESSOR403_ADMIN_NO_OR_WRONG_PASSWORD401_NO_REMEDIATION')

suite=unittest.TestSuite(Probe(x) for x in ('test_pending_identity_cannot_extract_until_rename_approved','test_cross_tenant_global_rejection','test_sqlite_mutation_survives_postgres_rollback','test_unrelated_names_and_wrong_evidence_hash','test_api_role_and_password_guards'))
result=unittest.TextTestRunner(verbosity=2).run(suite);sys.exit(not result.wasSuccessful())
