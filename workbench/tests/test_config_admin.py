import base64,copy,io,json,unittest
from pathlib import Path
from openpyxl import Workbook
from aw import config_admin,configs,seed
from aw.engine import evaluate,ConfigurationError
from tests.test_workflow import Seeded
from tests.support import PACK,AsgiClient
from aw.api.app import create_app
from aw import auth

class PatchImports(unittest.TestCase):
    def test_csv_xlsx_exact_money_and_formula_rejection(self):
        csv=b'path,value_json\n/deductible/amount,"""100.01"""\n'
        out=config_admin.import_patch({'deductible':{'amount':'0.00'}},'patch.csv',base64.b64encode(csv).decode())
        self.assertEqual(out['deductible']['amount'],'100.01')
        wb=Workbook();ws=wb.active;ws.append(['path','value_json']);ws.append(['/deductible/amount','"100.01"']);buf=io.BytesIO();wb.save(buf)
        self.assertEqual(config_admin.import_patch({'deductible':{}},'patch.xlsx',base64.b64encode(buf.getvalue()).decode())['deductible']['amount'],'100.01')
        ws['B2']='=1+1';buf=io.BytesIO();wb.save(buf)
        with self.assertRaises(ValueError):config_admin.import_patch({},'patch.xlsx',base64.b64encode(buf.getvalue()).decode())

class OrderingAndCatalogue(unittest.TestCase):
    def setup_data(self):
        self.c=seed._fixture('trace-2-interacting-adjustments');self.p=json.loads((PACK/'config/policy-ILL-INDEMNITY-A.v2026.1.0.json').read_text());self.n=json.loads((PACK/'config/nme-list-ILL-A.v2026.1.0.json').read_text());self.t=json.loads((PACK/'config/tariff-ILL-HOSP-NW-01.v2026.07.json').read_text())
    def test_unsafe_order_fails_and_safe_order_is_used(self):
        self.setup_data();o=self.p['calculation_order'];a=o.index('R-CLAIM-COPAY');b=o.index('R-CLAIM-SI-CAP');o[a],o[b]=o[b],o[a]
        with self.assertRaises(ConfigurationError):evaluate(self.c,self.p,self.n,self.t)
        self.setup_data();o=self.p['calculation_order'];a=o.index('R-CLAIM-SUBLIMIT');b=o.index('R-CLAIM-DEDUCTIBLE');o[a],o[b]=o[b],o[a]
        out=evaluate(self.c,self.p,self.n,self.t);ids=[e['rule_id'] for e in out['rule_executions']];self.assertLess(ids.index('R-CLAIM-DEDUCTIBLE'),ids.index('R-CLAIM-SUBLIMIT'));self.assertEqual(out['recommendation']['recommended_payable'],'85000.00')
    def test_review_catalogue_never_automatically_denies(self):
        self.setup_data();self.p.update(exclusions=[{'code':'SYN-EXCLUSION','keywords_any':['appendicitis']}],implant_invoice_required=True,length_of_stay_norms=[{'procedure_code':self.c['procedure_codes'][0],'min_days':0,'max_days':0}]);self.c['clinical_observations']=[{'text':'appendicitis','evidence':self.c['bill_lines'][0]['evidence']}];self.c['overlapping_claims']=[{'claim_id':'SYN-OTHER'}];self.c['tat_breached']=True
        out=evaluate(self.c,self.p,self.n,self.t);kinds={f['kind'] for f in out['findings']};self.assertTrue({'EXCLUSION_REQUIRES_REVIEW','LOS_REQUIRES_REVIEW','POSSIBLE_DUPLICATE_CLAIM','DEADLINE_BREACHED'}<=kinds);self.assertTrue(out['recommendation']['human_decision_required'])
    def test_package_consumes_components_without_tariff_double_deduction(self):
        self.setup_data();self.t['packages']=[{'package_code':'SYN-PACK','amount':'100.00','procedure_codes':self.c['procedure_codes'],'inclusions':['DIAGNOSTICS']}]
        out=evaluate(self.c,self.p,self.n,self.t);package=[a for a in out['adjustments'] if a['rule_id']=='R-LINE-PACKAGE'];self.assertTrue(package)
        consumed={a['line_id'] for a in package};self.assertFalse(any(a['line_id'] in consumed and a['rule_id'] in ('R-LINE-TARIFF','R-LINE-PROPORTIONATE') for a in out['adjustments']));self.assertTrue(all(a['authority']['doc_id'] for a in package))
        del self.t['agreement_clause']
        with self.assertRaises(ConfigurationError):evaluate(self.c,self.p,self.n,self.t)
    def test_implant_invoice_and_prepost_outlier_abstain(self):
        self.setup_data();self.p['implant_invoice_required']=True;self.c['bill_lines'][0]['category']='IMPLANTS'
        out=evaluate(self.c,self.p,self.n,self.t);self.assertIsNone(out['recommendation']['recommended_payable']);self.assertTrue(any(f['kind']=='IMPLANT_INVOICE_MISSING' for f in out['findings']))
        self.setup_data();self.p['review_prepost_service_dates']=True;self.c['bill_lines'][0]['service_date']='2025-01-01'
        out=evaluate(self.c,self.p,self.n,self.t);self.assertIsNone(out['recommendation']['recommended_payable']);self.assertTrue(any(f['kind']=='SERVICE_DATE_OUTSIDE_WINDOW' for f in out['findings']))

class ConfigReplay(Seeded):
    def test_draft_validate_replay_four_eyes_publish_and_reevaluate(self):
        import uuid
        from aw import synthetic
        self.new_claim('CLM-CONFIG-PUBLISH','trace-1-straightforward',synthetic.claim_documents()['CLM-DEMO-0001'])
        client=AsgiClient(create_app(self.ctx))
        def headers(user):return {'Authorization':'Bearer '+auth.issue_dev_token(self.ctx.settings.dev_token_secret,user,seed.TENANT),'Idempotency-Key':str(uuid.uuid4())}
        body=json.loads((PACK/'config/policy-ILL-INDEMNITY-A.v2026.1.0.json').read_text());body['config_version']='2026.4.0';body['deductible']['amount']='100.00'
        r=client.post('/v1/config-artifacts',headers=headers('CFG-01'),json_body={'artifact_id':body['config_id'],'version':body['config_version'],'kind':'POLICY_CONFIG','effective_from':body['effective_from'],'body':body,'source_documents':[]});self.assertEqual(r.status,201,r)
        path='/v1/config-artifacts/'+body['config_id']+'/versions/'+body['config_version']
        self.assertTrue(client.post(path+':validate',headers=headers('CFG-01')).json()['valid'])
        preview=client.post(path+':replay',headers=headers('CFG-01'),json_body={'claim_ids':['CLM-CONFIG-PUBLISH']});self.assertEqual(preview.status,202,preview);self.assertEqual(preview.json()['results'][0]['payable_after'],'107491.00')
        self.assertEqual(client.post(path+':publish',headers=headers('CFG-01'),json_body={'current_password':'Synthetic-demo-2026!'}).status,422)
        self.assertEqual(client.post(path+':publish',headers=headers('PROC-07'),json_body={}).status,403)
        result=client.post(path+':publish',headers=headers('ADM-01'),json_body={'retroactive_to_open_claims':True,'current_password':'Synthetic-demo-2026!'});self.assertEqual(result.status,200,result);self.assertGreaterEqual(result.json()['reevaluations_queued'],1)
        self.worker.drain();self.assertEqual(self.current('CLM-CONFIG-PUBLISH')['recommended_payable_paise'],10749100)
    def test_all_kinds_replay_without_persistence(self):
        from aw import synthetic
        self.new_claim('CLM-CONFIG-REPLAY','trace-2-interacting-adjustments',synthetic.claim_documents()['CLM-DEMO-0002'])
        with self.db.tenant_tx(seed.TENANT) as c:
            before=c.fetch_val('SELECT count(*) FROM evaluation')
            for row in c.fetch_all("SELECT * FROM config_artifact WHERE artifact_id IN ('POLCFG-ILL-INDEMNITY-A','NMELIST-ILL-A','TARIFF-ILL-HOSP-NW-01','CHECKLIST-IPD-REIMB','WFCFG-TENANT-DEMO','CLASSMAP-ILL-A') AND version IN ('2026.1.0','2026.07')"):
                out=config_admin.replay(c,seed.TENANT,row,['CLM-CONFIG-REPLAY'],self.ctx.store);self.assertEqual(out['claims'],1,row['artifact_kind']);self.assertFalse(out['persisted'])
            self.assertEqual(c.fetch_val('SELECT count(*) FROM evaluation'),before)
