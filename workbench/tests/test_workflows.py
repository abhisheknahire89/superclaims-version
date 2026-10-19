from datetime import datetime,timezone,timedelta
from aw import ingest,decisions,workflow_demo,workflows,tat,configs,synthetic
from aw.errors import AppError
from tests.test_workflow import Seeded

class FourWorkflows(Seeded):
 def make_case(self,cid,workflow,parent=None,total='3000.00',index=0):
  reference=workflow_demo.CASES[index];name=reference[2]
  with self.db.tenant_tx('TENANT-DEMO') as c:
   ingest.create_claim(c,'TENANT-DEMO',{'claim_id':cid,'external_ref':cid,'workflow':workflow,'policy_no':'POL-'+reference[0],'member_id':'MEM-'+reference[0],'hospital_id':'HOSP-ILL-NN-07','parent_claim_id':parent},'USER:PROC-07')
   for _,dtype,data in workflow_demo.documents(workflow,name,total,number=cid):ingest.add_document(c,self.ctx.store,'TENANT-DEMO',cid,data,declared_type=dtype,source_channel='API',actor='USER:PROC-07')
  self.worker.drain();return self.current(cid)
 def approve(self,cid):
  ev=self.current(cid);value=ev['result']['recommendation']['recommended_payable']
  with self.db.tenant_tx('TENANT-DEMO') as c:return decisions.decide(c,self.p('PROC-07'),self.ctx.schema_dir,cid,{'evaluation_id':ev['evaluation_id'],'disposition':'APPROVED_FULL' if value==ev['result']['recommendation']['billed_total'] else 'APPROVED_PARTIAL','approved_payable':value})
 def test_preauth_enhancement_discharge_reservation_carry_forward(self):
  e=self.make_case('CLM-FLOW-PRE','PREAUTH');self.assertEqual(e['recommended_payable_paise'],300000);self.approve('CLM-FLOW-PRE')
  e=self.make_case('CLM-FLOW-ENH','ENHANCEMENT','CLM-FLOW-PRE','4000.00');self.assertEqual(e['recommended_payable_paise'],400000);self.approve('CLM-FLOW-ENH')
  ref=workflow_demo.CASES[0];name=ref[2]
  with self.db.tenant_tx('TENANT-DEMO') as c:
   ingest.create_claim(c,'TENANT-DEMO',{'claim_id':'CLM-FLOW-FINAL','workflow':'CASHLESS_DISCHARGE','policy_no':'POL-'+ref[0],'member_id':'MEM-'+ref[0],'hospital_id':'HOSP-ILL-NN-07','parent_claim_id':'CLM-FLOW-ENH'},'USER:PROC-07')
   bill=synthetic.Doc('FINAL BILL - ITEMISED');bill.line('Patient Name: '+name);bill.line('Gender: Male');bill.line('Bill Number: SYN-FINAL');bill.line('Grand Total: 3500.00');bill.table([{'line_id':'L01','description':'Consultant visit','quantity':'1','unit_rate':'3500.00','billed':'3500.00'}])
   data=synthetic.simple('DISCHARGE SUMMARY',[f'Patient Name: {name}','Gender: Male','Admission Date: 01/10/2026','Discharge Date: 02/10/2026','Diagnosis: Synthetic discharge condition'])
   for dtype,payload in [('FINAL_BILL_ITEMISED',bill.bytes()),('DISCHARGE_SUMMARY',data)]:ingest.add_document(c,self.ctx.store,'TENANT-DEMO','CLM-FLOW-FINAL',payload,declared_type=dtype,source_channel='API',actor='USER:PROC-07')
  self.worker.drain();self.assertEqual(self.current('CLM-FLOW-FINAL')['recommended_payable_paise'],350000);self.approve('CLM-FLOW-FINAL')
  with self.db.tenant_tx('TENANT-DEMO') as c:self.assertEqual(c.fetch_val("SELECT sum(CASE WHEN entry_kind='RESERVED' THEN amount_paise WHEN entry_kind='RELEASED' THEN -amount_paise ELSE 0 END) FROM si_ledger_entry WHERE policy_no=$1",'POL-'+ref[0]),350000)
 def test_opd_benefit_cap(self):
  e=self.make_case('CLM-FLOW-OPD','OPD_REIMBURSEMENT',total='7000.00',index=2);self.assertEqual(e['recommended_payable_paise'],500000);self.approve('CLM-FLOW-OPD')
 def test_workflow_clock_and_invalid_parent_guards(self):
  now=datetime.now(timezone.utc)
  with self.db.tenant_tx('TENANT-DEMO') as c:cfg=configs.effective(c,'TENANT-DEMO','WORKFLOW_CONFIG',now.date())
  for wf,minutes in [('PREAUTH',60),('ENHANCEMENT',60),('CASHLESS_DISCHARGE',180),('OPD_REIMBURSEMENT',21600),('IPD_REIMBURSEMENT',21600)]:
   claim={'workflow':wf,'status':'INTAKE','submitted_at':now};self.assertEqual(tat.deadline(claim,cfg),now+timedelta(minutes=minutes));self.assertTrue(tat.breached(claim,cfg,now+timedelta(minutes=minutes+1)))
   with self.assertRaises(AppError):workflows.assert_transition(wf,'INTAKE','FINALISED')
  with self.assertRaises(AppError):self.make_case('CLM-ORPHAN','ENHANCEMENT')
  self.make_case('CLM-UNAPPROVED','PREAUTH')
  with self.assertRaises(AppError):self.make_case('CLM-BAD-PARENT','ENHANCEMENT','CLM-UNAPPROVED')
