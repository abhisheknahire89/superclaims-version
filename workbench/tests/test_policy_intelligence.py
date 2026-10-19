import csv,io,json,tempfile,unittest
from pathlib import Path
from aw.policy_intelligence.acquisition import Library
class ResearchValidation(unittest.TestCase):
 def setUp(self):self.temp=tempfile.TemporaryDirectory();self.lib=Library(Path(self.temp.name));self.addCleanup(self.lib.close);self.addCleanup(self.temp.cleanup)
 def import_rows(self,rows):
  p=Path(self.temp.name)/'input.csv';f=io.StringIO();w=csv.writer(f);w.writerow(['insurer_name','product_name','uin','url','verification_status']);w.writerows(rows);p.write_text(f.getvalue());return self.lib.import_csv(p)
 def test_placeholders_malformed_conflicting_uin_are_quarantined(self):
  report=self.import_rows([['Star Health','One','XXX','https://www.starhealth.in/a.pdf','VERIFIED'],['Star Health','One','SHAHLIP21025V052021','https://www.starhealth.in/a.pdf','VERIFIED'],['Star Health','Two','SHAHLIP21025V052021','https://www.starhealth.in/b.pdf','VERIFIED'],['Care Health','x']]);self.assertEqual(report['quarantined'],4);self.assertTrue(all(r['reasons'] for r in self.lib.entries()))
 def test_verified_label_does_not_promote_or_guess_effective_dates(self):
  self.import_rows([['Star Health','One','SHAHLIP21025V052021','https://www.starhealth.in/a.pdf','VERIFIED']]);r=self.lib.entries()[0];self.assertEqual(r['state'],'DISCOVERED');self.assertIsNone(r['body']['wording_effective_from'])
 def test_unofficial_and_webpage_urls_fail(self):
  out=self.import_rows([['Care Health','One','CHIHLIP21025V052021','https://example.com/x.pdf','VERIFIED'],['Niva Bupa','One','MAXHLIP21060V012021','https://www.nivabupa.com/downloads','VERIFIED']]);self.assertEqual(out['quarantined'],2)
class AcquisitionIntegrity(unittest.TestCase):
 setUp=ResearchValidation.setUp
 import_rows=ResearchValidation.import_rows
 def pdf(self,extra='',uin='SHAHLIP21025V052021'):
  from reportlab.pdfgen import canvas
  buf=io.BytesIO();d=canvas.Canvas(buf);d.setTitle('ILLUSTRATIVE SYNTHETIC POLICY');text=d.beginText(60,750)
  for line in ['ILLUSTRATIVE SYNTHETIC POLICY','Star Health One',uin,'Room rent '+extra]:text.textLine(line)
  d.drawText(text);d.showPage();d.save();return buf.getvalue()
 def entry(self):
  self.import_rows([['Star Health','One','SHAHLIP21025V052021','https://www.starhealth.in/a.pdf','VERIFIED']]);return self.lib.entries()[0]['id']
 def test_html_and_wrong_document_uin_rejected_or_quarantined(self):
  key=self.entry()
  with self.assertRaises(ValueError):self.lib.preserve(key,b'<html>captcha</html>',{})
  self.lib.preserve(key,self.pdf(uin='SHAHLIP21025V052022'),{});self.assertEqual(self.lib.entries()[0]['state'],'METADATA_CONFLICT')
  self.lib.preserve(key,self.pdf(),{})
  self.assertEqual(self.lib.entries()[0]['state'],'CONTENT_VERIFIED');self.assertNotEqual(self.lib.entries()[0]['state'],'APPROVED_SOURCE')
 def test_duplicate_and_changed_content_preserve_historical_bytes(self):
  key=self.entry();a=self.lib.preserve(key,self.pdf('old'),{});b=self.lib.preserve(key,self.pdf('new'),{});c=self.lib.preserve(key,self.lib.original(a['sha256']).read_bytes(),{})
  self.assertTrue(b['changed_at_url']);self.assertTrue(c['duplicate']);self.assertNotEqual(a['sha256'],b['sha256']);self.assertTrue(self.lib.original(a['sha256']).exists());self.assertEqual(len(self.lib.report()['retrievals']),3)
 def test_name_conflict_evidence_download_stays_quarantined(self):
  self.import_rows([['Star Health','One','SHAHLIP21025V052021','https://www.starhealth.in/a.pdf','DISCOVERED'],['Star Health','Two','SHAHLIP21025V052021','https://www.starhealth.in/b.pdf','DISCOVERED']]);key=self.lib.entries()[0]['id'];data=self.pdf()
  class Response:
   status=200;headers={'Content-Type':'application/pdf','Content-Length':str(len(data)),'ETag':'"v1"'}
   def __enter__(self):self.used=False;return self
   def __exit__(self,*args):pass
   def read(self,n):
    if self.used:return b''
    self.used=True;return data
  with self.assertRaises(ValueError):self.lib.download(key,opener=lambda *a,**k:Response(),respect_robots=False)
  result=self.lib.download(key,opener=lambda *a,**k:Response(),respect_robots=False,quarantine_evidence=True);self.assertTrue(result['identity_conflict_pending']);self.assertEqual(next(e for e in self.lib.entries() if e['id']==key)['state'],'METADATA_CONFLICT')
 def test_corrected_import_detects_changed_url_without_overwriting(self):
  key=self.entry();old=self.lib.preserve(key,self.pdf('old'),{})
  self.import_rows([['Star Health','One','SHAHLIP21025V052021','https://www.starhealth.in/a.pdf','CORRECTED']]);key2=next(r['id'] for r in self.lib.entries() if r['id']!=key)
  updated=self.lib.preserve(key2,self.pdf('new'),{});self.assertTrue(updated['changed_at_url']);self.assertTrue(self.lib.original(old['sha256']).exists())
 def test_failed_and_interrupted_download_resume_with_strong_etag(self):
  key=self.entry();data=self.pdf();seen=[]
  class Response:
   def __init__(self,attempt):self.status=200 if attempt==0 else 206;self.headers={'ETag':'"v1"','Content-Length':str(len(data) if attempt==0 else len(data)-128),'Content-Type':'application/pdf'};self.attempt=attempt;self.calls=0
   def __enter__(self):return self
   def __exit__(self,*args):pass
   def read(self,n):
    self.calls+=1
    if self.attempt==0:
     if self.calls==1:return data[:128]
     raise OSError('interrupted')
    return data[128:] if self.calls==1 else b''
  def opener(req,**kwargs):
   seen.append(dict(req.header_items()));r=Response(len(seen)-1)
   if len(seen)>1:r.headers['Content-Range']=f'bytes 128-{len(data)-1}/{len(data)}'
   return r
  with self.assertRaises(OSError):self.lib.download(key,opener=opener,respect_robots=False)
  result=self.lib.download(key,opener=opener,respect_robots=False);self.assertEqual(result['resumed_bytes'],128);self.assertEqual(seen[1]['Range'],'bytes=128-');self.assertEqual(self.lib.original(result['sha256']).read_bytes(),data)
from tests.test_workflow import Seeded
from aw import auth
from aw.policy_intelligence import registry
from unittest.mock import patch
class RegistryIdentity(Seeded):
 def setUp(self):
  Seeded.setUp(self);self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.lib=Library(Path(self.temp.name));self.addCleanup(self.lib.close);self.patch=patch.object(registry,'root',return_value=Path(self.temp.name));self.patch.start();self.addCleanup(self.patch.stop)
  self.author=auth.Principal('CFG-01','TENANT-DEMO',{'CONFIG_ADMIN'});self.approver=auth.Principal('ADM-01','TENANT-DEMO',{'TENANT_ADMIN'})
 def source_fixture(self):
  from reportlab.pdfgen import canvas
  buf=io.BytesIO();d=canvas.Canvas(buf);t=d.beginText(60,750)
  for line in ['ILLUSTRATIVE SYNTHETIC POLICY','Star Health One','Star Health and Allied Insurance Company Limited','SHAHLIP21025V052021','1. Co-payment is 10% of admissible claim amount.','Wording effective from 2026-01-01.','Product withdrawn from 2026-12-31.']:t.textLine(line)
  d.drawText(t);d.showPage();d.save();b={'insurer':'STAR','product_name':'One','uin':'SHAHLIP21025V052021','url':'https://www.starhealth.in/illustrative.pdf','declared_revision':None}
  self.lib.record('illustrative',b,'DISCOVERED',[]);self.lib.preserve('illustrative',buf.getvalue(),{'retrieved_at':'2026-10-13T00:00:00Z','url':b['url'],'illustrative':True})
  with self.db.tenant_tx('TENANT-DEMO') as c:return registry.intake(c,self.author,self.ctx,'illustrative')['source_id']
 def verification(self):return {'identity_quote':'SHAHLIP21025V052021','product_title_quote':'Star Health One','legal_name_quote':'Star Health and Allied Insurance Company Limited','uin':'SHAHLIP21025V052021','insurer':'STAR','revision_label':'illustrative v1','wording_effective_from':None}
 def test_source_identity_conflict_and_four_eyes_block(self):
  sid=self.source_fixture();v=self.verification()
  with self.db.tenant_tx('TENANT-DEMO') as c:
   with self.assertRaises(Exception):registry.verify(c,self.author,self.ctx,sid,v)
   v['uin']='SHAHLIP21025V052022'
   with self.assertRaises(Exception):registry.verify(c,self.approver,self.ctx,sid,v)
 def test_source_unknown_dates_retained_and_original_evidence_required(self):
  sid=self.source_fixture();v=self.verification()
  with self.db.tenant_tx('TENANT-DEMO') as c:
   v['product_title_quote']='invented';
   with self.assertRaises(Exception):registry.verify(c,self.approver,self.ctx,sid,v)
   out=registry.verify(c,self.approver,self.ctx,sid,self.verification());self.assertTrue(out['review_required']);self.assertIsNone(out['wording_effective_from'])
 def test_registry_rls_and_append_only_history(self):
  sid=self.source_fixture()
  with self.db.tenant_tx('OTHER-TENANT') as c:self.assertEqual(c.fetch_val('SELECT count(*) FROM policy_knowledge_record'),0);self.assertEqual(c.fetch_val('SELECT count(*) FROM policy_review_event'),0)
  from aw.db import PgError
  with self.assertRaises(PgError):
   with self.db.tenant_tx('TENANT-DEMO') as c:c.execute("UPDATE policy_knowledge_record SET body='{}'")
class ClauseGrounding(Seeded):
 setUp=RegistryIdentity.setUp
 source_fixture=RegistryIdentity.source_fixture
 verification=RegistryIdentity.verification
 def test_candidates_only_from_approved_sources_and_unsupported_quotes_reject(self):
  from aw.policy_intelligence import extraction
  sid=self.source_fixture()
  with self.db.tenant_tx('TENANT-DEMO') as c:
   with self.assertRaises(Exception):extraction.extract(c,self.author,self.ctx,sid)
   before=c.fetch_val("SELECT count(*) FROM config_artifact WHERE status='PUBLISHED'")
   registry.verify(c,self.approver,self.ctx,sid,self.verification());out=extraction.extract(c,self.author,self.ctx,sid);self.assertGreater(out['count'],0)
   row,path=registry.source(c,'TENANT-DEMO',sid,self.ctx,True)
   rule=c.fetch_one('SELECT * FROM policy_rule_candidate WHERE tenant_id=$1 AND rule_id=$2','TENANT-DEMO',out['rule_ids'][0]);self.assertEqual(rule['state'],'DRAFT');extraction.grounded(path,rule['body'])
   bad=dict(rule['body'],quote='unsubstantiated price deduction')
   with self.assertRaises(Exception):extraction.grounded(path,bad)
   self.assertEqual(c.fetch_val("SELECT count(*) FROM config_artifact WHERE status='PUBLISHED'"),before)
class RuleLifecycle(Seeded):
 setUp=RegistryIdentity.setUp
 source_fixture=RegistryIdentity.source_fixture
 verification=RegistryIdentity.verification
 def pipeline(self,known_dates=True):
  from aw.policy_intelligence import extraction,review
  sid=self.source_fixture();v=self.verification()
  if known_dates:v.update(wording_effective_from='2026-01-01',effective_date_quote='Wording effective from 2026-01-01.')
  with self.db.tenant_tx('TENANT-DEMO') as c:
   registry.verify(c,self.approver,self.ctx,sid,v);ids=extraction.extract(c,self.author,self.ctx,sid)['rule_ids'];key=ids[0]
   fields={'interpretation':'Illustrative unconditional ten percent copay on admissible amount; reviewer read the full synthetic clause.','representation':{'kind':'COPAY','percent':'10.00'},'conditions':[],'exceptions':[],'dependencies':['issued_member_schedule','dynamic_remaining_cover','hospital_contract_tariff'],'ambiguities':[],'context_reviewed':True,'effective_from':'2026-01-01' if known_dates else None,'effective_date_quote':'Wording effective from 2026-01-01.','effective_date_page':1,'review_required':not known_dates}
   review.change(c,self.author,self.ctx,key,'revise_rule',fields)
  return sid,key
 def publish(self,key):
  from aw.policy_intelligence import review
  with self.db.tenant_tx('TENANT-DEMO') as c:
   for step in ('validate_rule','review_rule'):review.change(c,self.author,self.ctx,key,step,{})
   for step in ('approve_rule','publish_rule'):review.change(c,self.approver,self.ctx,key,step,{})
 def test_four_eyes_order_immutable_rule_and_role_guards(self):
  from aw.policy_intelligence import review
  from aw.api.app import create_app
  from tests.support import AsgiClient
  import uuid
  sid,key=self.pipeline()
  with self.db.tenant_tx('TENANT-DEMO') as c:
   with self.assertRaises(Exception):review.change(c,self.approver,self.ctx,key,'approve_rule',{})
   review.change(c,self.author,self.ctx,key,'validate_rule',{});review.change(c,self.author,self.ctx,key,'review_rule',{})
   with self.assertRaises(Exception):review.change(c,self.author,self.ctx,key,'approve_rule',{})
   review.change(c,self.approver,self.ctx,key,'approve_rule',{});review.change(c,self.approver,self.ctx,key,'publish_rule',{})
   with self.assertRaises(Exception):review.change(c,self.author,self.ctx,key,'revise_rule',{'representation':{'kind':'COPAY','percent':'50'}})
  client=AsgiClient(create_app(self.ctx));h={'Authorization':'Bearer '+auth.issue_dev_token(self.ctx.settings.dev_token_secret,'PROC-07','TENANT-DEMO'),'Idempotency-Key':str(uuid.uuid4())}
  self.assertEqual(client.post('/v1/policy-intelligence/actions',headers=h,json_body={'action':'publish_rule','target':key}).status,403)
 def test_shadow_engine_effect_and_runtime_configs_unchanged(self):
  from aw.policy_intelligence import preview
  from aw import synthetic,evaluations
  import uuid
  sid,key=self.pipeline();self.publish(key);cid='CLM-SHADOW-'+uuid.uuid4().hex;self.new_claim(cid,'trace-1-straightforward',synthetic.claim_documents()['CLM-DEMO-0001'])
  with self.db.tenant_tx('TENANT-DEMO') as c:
   claim,cfg=evaluations.build_engine_input(c,'TENANT-DEMO',cid,'TEST');b=c.fetch_one('SELECT body FROM policy_rule_candidate WHERE rule_id=$1',key)['body'];before=c.fetch_all('SELECT artifact_id,version,body_sha256,status FROM config_artifact ORDER BY artifact_id,version');n=c.fetch_val('SELECT count(*) FROM evaluation')
   inputs={'illustrative':True,'member':{'issued_policy_evidence':'ILLUSTRATIVE-SCHEDULE','insurer_id':b['insurer'],'uin':b['uin'],'revision_hash':b['revision_hash'],'policy_period_start':'2026-01-01','policy_period_end':'2026-12-31','wording_effective_date':'2026-01-01','selected_options':[],'group_variations':{},'endorsement_evidence':'ILLUSTRATIVE-NO-ENDORSEMENTS'},'coverage':{'status':'ACTIVE','base_sum_insured':'500000.00','remaining_sum_insured':'500000.00','authoritative_evidence':'ILLUSTRATIVE-COVERAGE','as_of':__import__('datetime').datetime.now(__import__('zoneinfo').ZoneInfo('Asia/Kolkata')).date().isoformat(),'reservations':'0.00','restoration_usage':'0.00','previous_claims':[],'benefit_utilisation':{}},'tariff':{'hospital_id':claim['hospital_id'],'agreement_id':'ILLUSTRATIVE-AGREEMENT','insurer_or_tpa':'ILLUSTRATIVE-INSURER','effective_from':'2026-01-01','effective_to':'2026-12-31','authoritative_evidence':'ILLUSTRATIVE-TARIFF','rates':{'item_caps':[],'room_rates':[]},'packages':[],'room_limits':{}}}
   result=preview.preview(c,self.author,self.ctx,key,cid,inputs);self.assertIsNone(result['definitive_payable']);self.assertTrue(result['draft_deduction_effects']);self.assertEqual(result['baseline_difference']['before'],'107591.00');self.assertEqual(result['baseline_difference']['after'],'96831.00')
   self.assertTrue(any('sha256:'+b['sha256'] in a['authority']['doc_id'] for a in result['draft_deduction_effects'] if a['rule_id']=='R-CLAIM-COPAY'));self.assertEqual(c.fetch_val('SELECT count(*) FROM evaluation'),n);self.assertEqual(c.fetch_all('SELECT artifact_id,version,body_sha256,status FROM config_artifact ORDER BY artifact_id,version'),before)
   inputs['coverage']['remaining_sum_insured']=None;out=preview.preview(c,self.author,self.ctx,key,cid,inputs);self.assertIsNone(out['draft_deduction_effects']);self.assertTrue(any(x['field']=='remaining_sum_insured' for x in out['verification_tasks']))
   inputs['coverage']['remaining_sum_insured']='500000.00';inputs['tariff']['rates']=None;out=preview.preview(c,self.author,self.ctx,key,cid,inputs);self.assertIsNone(out['draft_deduction_effects']);self.assertIn('TARIFF_UNVERIFIED',out['states'])
 def test_optional_membership_and_unknown_effective_dates_block(self):
  from aw.policy_intelligence.preview import readiness
  rule={'insurer':'STAR','uin':'SHAHLIP21025V052021','revision_hash':'abc','representation':{'kind':'COPAY','selected_option':'OPTIONAL-WAIVER'},'conditions':[],'exceptions':[],'review_required':True,'effective_from':None}
  out=readiness({'member':{'selected_options':None},'coverage':{'base_sum_insured':'500000.00'},'tariff':{}},rule,{},'2026-08-10');self.assertTrue(any(x['field']=='selected_options' for x in out['verification_tasks']));self.assertTrue(any(x['field']=='effective_dates' for x in out['verification_tasks']));self.assertIn('FINANCIAL_REVIEW_REQUIRED',out['states'])

class PolicyHardening(Seeded):
 setUp=RegistryIdentity.setUp
 source_fixture=RegistryIdentity.source_fixture
 verification=RegistryIdentity.verification
 pipeline=RuleLifecycle.pipeline
 publish=RuleLifecycle.publish
 def test_unguarded_dates_and_truthy_context_are_rejected(self):
  from aw.policy_intelligence import review
  sid=self.source_fixture();v=self.verification();v['wording_effective_to']='2099-12-31'
  with self.db.tenant_tx('TENANT-DEMO') as c:
   with self.assertRaises(Exception):registry.verify(c,self.approver,self.ctx,sid,v)
  sid,key=self.pipeline()
  with self.db.tenant_tx('TENANT-DEMO') as c:
   review.change(c,self.author,self.ctx,key,'revise_rule',{'effective_to':'2099-12-31'})
   with self.assertRaises(Exception):review.change(c,self.author,self.ctx,key,'validate_rule',{})
   review.change(c,self.author,self.ctx,key,'revise_rule',{'effective_to':None,'context_reviewed':'false'})
   with self.assertRaises(Exception):review.change(c,self.author,self.ctx,key,'validate_rule',{})
 def test_private_proofs_freshness_reservations_and_dependencies_block(self):
  from aw.policy_intelligence.preview import readiness
  from datetime import datetime
  from zoneinfo import ZoneInfo
  import copy
  rule={'insurer':'STAR','uin':'SHAHLIP21025V052021','revision_hash':'x','representation':{'kind':'COPAY'},'effective_from':'2026-01-01','review_required':False,'conditions':[],'exceptions':[],'dependencies':[]}
  member={k:'evidence' for k in ('issued_policy_evidence','endorsement_evidence')};member.update(insurer_id='STAR',uin=rule['uin'],revision_hash='x',policy_period_start='2026-01-01',policy_period_end='2026-12-31',wording_effective_date='2026-01-01',selected_options=[],group_variations={})
  cov=dict(status='ACTIVE',base_sum_insured='500000.00',remaining_sum_insured='500000.00',authoritative_evidence='synthetic evidence',as_of=datetime.now(ZoneInfo('Asia/Kolkata')).date().isoformat(),reservations='0.00',restoration_usage='0.00',previous_claims=[],benefit_utilisation={})
  tar=dict(hospital_id='h',agreement_id='a',insurer_or_tpa='i',effective_from='2026-01-01',effective_to='2026-12-31',authoritative_evidence='synthetic',rates={'item_caps':[],'room_rates':[]},packages=[],room_limits={})
  bundle=dict(member=member,coverage=cov,tariff=tar);verification={'wording_effective_from':'2026-01-01'}
  for layer,field,value in [('member','issued_policy_evidence','  '),('coverage','as_of','1900-01-01'),('coverage','reservations','499999.00'),('tariff','authoritative_evidence','')]:
   bad=copy.deepcopy(bundle);bad[layer][field]=value;out=readiness(bad,rule,verification,'2026-08-10');self.assertIn('FINANCIAL_REVIEW_REQUIRED',out['states']);self.assertNotIn('FINANCIAL_INPUTS_VERIFIED',out['states'])
  bad_rule={**rule,'dependencies':['remaining_member_disease_sublimit']};self.assertTrue(any(t['layer']=='dependency' for t in readiness(bundle,bad_rule,verification,'2026-08-10')['verification_tasks']))
 def test_direct_insert_published_candidate_cannot_bypass_lifecycle(self):
  from aw.db import Json,PgError
  sid=self.source_fixture()
  with self.assertRaises(PgError):
   with self.db.tenant_tx('TENANT-DEMO') as c:c.execute("INSERT INTO policy_rule_candidate(tenant_id,rule_id,source_id,state,body,authored_by,reviewed_by,approved_by) VALUES($1,'FORGED',$2,'PUBLISHED',$3::jsonb,'CFG-01','CFG-01','ADM-01')",'TENANT-DEMO',sid,Json({}))

class ResearchArchive(unittest.TestCase):
 setUp=ResearchValidation.setUp
 import_rows=ResearchValidation.import_rows
 entry=AcquisitionIntegrity.entry
 pdf=AcquisitionIntegrity.pdf
 def test_restore_keeps_originals_and_corruption_is_rejected(self):
  from aw.policy_intelligence import archive
  key=self.entry();result=self.lib.preserve(key,self.pdf(),{})
  with tempfile.TemporaryDirectory() as target:
   backup=Path(target)/'backup';restored=Path(target)/'restore';archive.backup(self.lib.root,backup);report=archive.restore(backup,restored);self.assertEqual(report['restored_originals'],1)
   lib=Library(restored)
   try:self.assertEqual(lib.original(result['sha256']).read_bytes(),self.pdf_original(result))
   finally:lib.close()
   (backup/'originals'/f"{result['sha256']}.pdf").write_bytes(b'corrupt')
   with self.assertRaises(ValueError):archive.restore(backup,Path(target)/'bad')
 def pdf_original(self,result):return self.lib.original(result['sha256']).read_bytes()

class ProductHistoryReview(Seeded):
 setUp=RegistryIdentity.setUp
 source_fixture=RegistryIdentity.source_fixture
 verification=RegistryIdentity.verification
 def test_history_names_dates_and_four_eyes_require_actual_evidence(self):
  from aw.policy_intelligence import history
  sid=self.source_fixture()
  with self.db.tenant_tx('TENANT-DEMO') as c:
   registry.verify(c,self.approver,self.ctx,sid,self.verification())
   data={'change':'RENAME','names':['One','Star Health One'],'evidence':[{'source_id':sid,'page':1,'quote':'Star Health One'}],'interpretation':'Illustrative title alias only, not a new benefit.','context_reviewed':True,'review_required':True}
   proposal=history.propose(c,self.author,self.ctx,'STAR:SHAHLIP21025V052021',data)
   with self.assertRaises(Exception):history.approve(c,self.author,self.ctx,proposal['proposal_id'])
   approved=history.approve(c,self.approver,self.ctx,proposal['proposal_id']);self.assertIsNone(approved['effective_from']);self.assertTrue(approved['review_required'])
   with self.assertRaises(Exception):history.propose(c,self.author,self.ctx,'STAR:SHAHLIP21025V052021',{**data,'names':['Invented','Star Health One']})
   with self.assertRaises(Exception):history.propose(c,self.author,self.ctx,'STAR:SHAHLIP21025V052021',{**data,'effective_from':'2099-12-31'})
   with self.assertRaises(Exception):history.propose(c,self.author,self.ctx,'STAR:SHAHLIP21025V052021',{**data,'change':'WITHDRAWN'})
   with self.assertRaises(Exception):history.propose(c,self.author,self.ctx,'STAR:SHAHLIP21025V052021',{**data,'names':['Co-payment','Wording'],'evidence':[{'source_id':sid,'page':1,'quote':'1. Co-payment is 10% of admissible claim amount.'},{'source_id':sid,'page':1,'quote':'Wording effective from 2026-01-01.'}]})
   with self.assertRaises(Exception):history.propose(c,self.author,self.ctx,'STAR:SHAHLIP21025V052021',{**data,'evidence':[{'source_id':sid,'page':1,'quote':'Star Health One','sha256':'f'*64}]})
 def test_quarantine_resolution_requires_approved_same_original_and_role(self):
  from aw.policy_intelligence import history
  sid=self.source_fixture();entry=self.lib.entries()[0];self.lib.record('illustrative',entry['body'],'METADATA_CONFLICT',['UIN reused across conflicting product identities'])
  with self.db.tenant_tx('TENANT-DEMO') as c:
   with self.assertRaises(Exception):history.remediate(c,self.approver,self.ctx,'illustrative',{'reason':'Source reviewed against original','source_id':sid})
   registry.verify(c,self.approver,self.ctx,sid,self.verification());out=history.remediate(c,self.approver,self.ctx,'illustrative',{'reason':'Exact approved source verified','source_id':sid});self.assertEqual(out['state'],'CONTENT_VERIFIED')
   self.lib.record('bad',{'insurer':'STAR','uin':'XXX','product_name':'unverified','url':'unknown'},'METADATA_CONFLICT',['invalid UIN'])
   with self.assertRaises(Exception):history.remediate(c,auth.Principal('PROC-07','TENANT-DEMO',{'PROCESSOR'}),self.ctx,'bad',{'reason':'Invalid product source rejected'},True)
   self.assertEqual(history.remediate(c,self.approver,self.ctx,'bad',{'reason':'Invalid product source rejected'},True)['state'],'REJECTED')
  self.assertEqual(next(e for e in self.lib.entries() if e['id']=='bad')['state'],'METADATA_CONFLICT')
  with self.db.tenant_tx('OTHER-TENANT') as c:self.assertEqual(c.fetch_val("SELECT count(*) FROM policy_knowledge_record WHERE kind='ResearchRemediation'"),0)

 def test_remediation_rolls_back_without_touching_shared_journal(self):
  from aw.policy_intelligence import history
  self.lib.record('bad',{'insurer':'STAR','uin':'XXX','product_name':'unverified','url':'unknown'},'METADATA_CONFLICT',['invalid UIN'])
  with self.db.tenant_tx('TENANT-DEMO') as c:before=c.fetch_val("SELECT count(*) FROM policy_knowledge_record WHERE kind='ResearchRemediation'")
  with self.assertRaises(ValueError):
   with self.db.tenant_tx('TENANT-DEMO') as c:
    history.remediate(c,self.approver,self.ctx,'bad',{'reason':'Invalid product source rejected'},True);raise ValueError('rollback')
  with self.db.tenant_tx('TENANT-DEMO') as c:self.assertEqual(c.fetch_val("SELECT count(*) FROM policy_knowledge_record WHERE kind='ResearchRemediation'"),before)
  self.assertEqual(self.lib.entries()[0]['state'],'METADATA_CONFLICT')
 def test_conflicting_names_stay_nonfinancial_until_reviewed_alias_resolution(self):
  from aw.policy_intelligence import history,extraction
  self.source_fixture();entry=self.lib.entries()[0];self.lib.record('illustrative',entry['body'],'METADATA_CONFLICT',['UIN reused across conflicting product identities'])
  with self.db.tenant_tx('TENANT-DEMO') as c:
   sid=registry.intake(c,self.author,self.ctx,'illustrative')['source_id'];out=registry.verify(c,self.approver,self.ctx,sid,self.verification());self.assertEqual(out['state'],'NEEDS_HUMAN_REVIEW')
   with self.assertRaises(Exception):extraction.extract(c,self.author,self.ctx,sid)
   data={'change':'RENAME','names':['One','Star Health One'],'evidence':[{'source_id':sid,'page':1,'quote':'Star Health One'}],'interpretation':'Illustrative title alias independently checked.','context_reviewed':True,'review_required':True}
   key=history.propose(c,self.author,self.ctx,'STAR:SHAHLIP21025V052021',data)['proposal_id'];history.approve(c,self.approver,self.ctx,key)
   self.assertEqual(registry.verify(c,self.approver,self.ctx,sid,self.verification())['state'],'APPROVED_SOURCE');self.assertGreater(extraction.extract(c,self.author,self.ctx,sid)['count'],0)

 def test_withdrawal_history_keeps_historical_original_and_unknowns(self):
  from aw.policy_intelligence import history
  sid=self.source_fixture()
  with self.db.tenant_tx('TENANT-DEMO') as c:
   registry.verify(c,self.approver,self.ctx,sid,self.verification())
   data={'change':'WITHDRAWN','evidence':[{'source_id':sid,'page':1,'quote':'Product withdrawn from 2026-12-31.'}],'interpretation':'ILLUSTRATIVE explicit future withdrawal; existing issued contracts require separate continuation review.','context_reviewed':True,'effective_from':'2026-12-31'}
   key=history.propose(c,self.author,self.ctx,'STAR:SHAHLIP21025V052021',data)['proposal_id'];out=history.approve(c,self.approver,self.ctx,key);self.assertEqual(out['change'],'WITHDRAWN');self.assertEqual(out['effective_from'],'2026-12-31');self.assertTrue(registry.source(c,'TENANT-DEMO',sid,self.ctx,True)[1].exists())
