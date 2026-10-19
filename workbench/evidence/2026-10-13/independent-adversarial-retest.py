import sys,unittest,json,uuid
sys.path.insert(0,'/Users/abhishekpravinnahire/Desktop/SUperclaims/workbench/tests')
from tests.test_policy_intelligence import RuleLifecycle
from aw.policy_intelligence import registry,preview,review
from aw import synthetic,evaluations
class Adversarial(RuleLifecycle):
 def test_ungrounded_expiry(self):
  sid=self.source_fixture();v=self.verification();v.update(wording_effective_from='2026-01-01',effective_date_quote='Wording effective from 2026-01-01.',wording_effective_to='2099-12-31')
  with self.db.tenant_tx('TENANT-DEMO') as c:
   with self.assertRaises(Exception):registry.verify(c,self.approver,self.ctx,sid,v)
   print('UNGROUNDED_SOURCE_EXPIRY_REJECTED')
  sid,key=self.pipeline()
  with self.db.tenant_tx('TENANT-DEMO') as c:
   review.change(c,self.author,self.ctx,key,'revise_rule',{'effective_to':'2099-12-31'})
   with self.assertRaises(Exception):review.change(c,self.author,self.ctx,key,'validate_rule',{})
   print('UNGROUNDED_RULE_EXPIRY_REJECTED')
 def test_missing_private_proof_stale_coverage_ignored_dependency(self):
  sid,key=self.pipeline()
  with self.db.tenant_tx('TENANT-DEMO') as c:review.change(c,self.author,self.ctx,key,'revise_rule',{'dependencies':['issued_member_schedule','dynamic_remaining_cover','hospital_contract_tariff','remaining_member_disease_sublimit']})
  self.publish(key);cid='CLM-REVIEW-'+uuid.uuid4().hex;self.new_claim(cid,'trace-1-straightforward',synthetic.claim_documents()['CLM-DEMO-0001'])
  with self.db.tenant_tx('TENANT-DEMO') as c:
   claim,cfg=evaluations.build_engine_input(c,'TENANT-DEMO',cid,'TEST');b=c.fetch_one('SELECT body FROM policy_rule_candidate WHERE rule_id=$1',key)['body']
   bundle={'illustrative':True,'member':{'issued_policy_evidence':'','insurer_id':b['insurer'],'uin':b['uin'],'revision_hash':b['revision_hash'],'policy_period_start':'2026-01-01','policy_period_end':'2026-12-31','wording_effective_date':'2026-01-01','selected_options':[],'group_variations':{},'endorsement_evidence':''},'coverage':{'status':'ACTIVE','base_sum_insured':'500000.00','remaining_sum_insured':'500000.00','authoritative_evidence':'','as_of':'1900-01-01','reservations':'499999.00','restoration_usage':'0.00'},'tariff':{'hospital_id':claim['hospital_id'],'agreement_id':'ILLUSTRATIVE','insurer_or_tpa':'ILLUSTRATIVE','effective_from':'2026-01-01','effective_to':'2026-12-31','authoritative_evidence':'','rates':{'item_caps':[],'room_rates':[]},'packages':[],'room_limits':{}}}
   out=preview.preview(c,self.author,self.ctx,key,cid,bundle)
   self.assertIsNone(out['baseline_difference']);self.assertIsNone(out['draft_deduction_effects']);self.assertNotIn('FINANCIAL_INPUTS_VERIFIED',out['states']);self.assertIn('FINANCIAL_REVIEW_REQUIRED',out['states']);fields={x['field'] for x in out['verification_tasks']};self.assertTrue({'issued_policy_evidence','as_of','balance_reconciliation','remaining_member_disease_sublimit'}<=fields)
   print('UNSUPPORTED_PRIVATE_PROOF_BLOCKED',json.dumps({'states':out['states'],'tasks':out['verification_tasks'],'difference':out['baseline_difference'],'definitive_payable':out['definitive_payable']}))

 def test_strict_context_and_database_guards(self):
  sid,key=self.pipeline()
  with self.db.tenant_tx('TENANT-DEMO') as c:
   review.change(c,self.author,self.ctx,key,'revise_rule',{'context_reviewed':'false'})
   with self.assertRaises(Exception):review.change(c,self.author,self.ctx,key,'validate_rule',{})
   review.change(c,self.author,self.ctx,key,'revise_rule',{'context_reviewed':True,'interpretation':'   '})
   with self.assertRaises(Exception):review.change(c,self.author,self.ctx,key,'validate_rule',{})
   review.change(c,self.author,self.ctx,key,'revise_rule',{'interpretation':'Illustrative ten percent copay'})
  self.publish(key)
  from aw.db import PgError
  with self.assertRaises(PgError):
   with self.db.tenant_tx('TENANT-DEMO') as c:c.execute("UPDATE policy_rule_candidate SET body=body || '{\"interpretation\":\"tampered\"}'::jsonb WHERE rule_id=$1",key)
  with self.db.tenant_tx('OTHER-TENANT') as c:
   self.assertEqual(c.fetch_val('SELECT count(*) FROM policy_rule_candidate'),0)
   self.assertEqual(c.fetch_val('SELECT count(*) FROM policy_review_event'),0)
  print('STRICT_REVIEW_TYPES_PUBLISHED_BODY_AND_RLS_GUARDS_PASSED')

suite=unittest.TestSuite(Adversarial(x) for x in ('test_ungrounded_expiry','test_missing_private_proof_stale_coverage_ignored_dependency','test_strict_context_and_database_guards'))
result=unittest.TextTestRunner(verbosity=2).run(suite)
sys.exit(not result.wasSuccessful())
