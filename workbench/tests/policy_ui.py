"""Executed synthetic human-review simulation; public sources remain unapproved."""
import json,re,sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
from playwright.sync_api import sync_playwright,expect
out=Path('evidence/2026-10-13');out.mkdir(parents=True,exist_ok=True)
url=sys.argv[1] if len(sys.argv)>1 else 'http://127.0.0.1:8080'
report={'scope':'ILLUSTRATIVE review simulation; no automatic approval of public rules','actions':[]}
with sync_playwright() as pw:
 browser=pw.chromium.launch();p=browser.new_page(viewport={'width':1440,'height':1100})
 p.on('pageerror',lambda e:print('PAGE ERROR',str(e),flush=True))
 def login(user):
  p.goto(url+'/#/login')
  if p.get_by_role('button',name='Sign out').count():p.get_by_role('button',name='Sign out').click()
  p.get_by_role('button',name=user).click();expect(p.locator('#who')).to_contain_text('Config admin' if user=='CFG-01' else 'Tenant admin');p.goto(url+'/#/policy');expect(p.get_by_label('Downloaded research candidate').locator('option')).not_to_have_count(0)
 def act(button,expected=200):
  with p.expect_response(lambda r:r.url.endswith('/v1/policy-intelligence/actions') and r.request.method=='POST',timeout=30000) as response:p.get_by_role('button',name=button,exact=True).click()
  r=response.value;print(button,r.status,flush=True);assert r.status==expected,(button,r.status,r.text());data=r.json();report['actions'].append({'button':button,'status':r.status,'result':data});return data
 def choose(label,contains):
  sel=p.get_by_label(label);opts=sel.locator('option');expect(opts).not_to_have_count(0)
  target=next(o.get_attribute('value') for o in opts.all() if contains in o.inner_text());sel.select_option(target)
 login('CFG-01');choose('Downloaded research candidate','public · NIVA · ReAssure');result=act('Intake candidate');public_sid=result['source_id'];p.get_by_label('Policy source').select_option(public_sid)
 p.get_by_role('button',name='Show source page',exact=True).click();expect(p.get_by_label('Original policy evidence')).to_contain_text('Original SHA256',timeout=30000);p.screenshot(path=str(out/'policy-public-source.png'),full_page=True)
 assert act('Extract draft candidates',422)
 choose('Downloaded research candidate','illustrative · STAR');result=act('Intake candidate');sid=result['source_id'];p.get_by_label('Policy source').select_option(sid)
 login('ADM-01');p.get_by_label('Policy source').select_option(sid)
 verification={'insurer':'STAR','uin':'SYNHLIP26001V012026','identity_quote':'SYNHLIP26001V012026','product_title_quote':'Star Health Illustrative Demo','legal_name_quote':'Star Health and Allied Insurance Company Limited','revision_label':'ILLUSTRATIVE synthetic v1','wording_effective_from':'2026-01-01','wording_effective_to':None,'effective_date_quote':'Wording effective from 2026-01-01.'}
 p.get_by_label('Source verification JSON').fill(json.dumps(verification));p.get_by_label('Policy approval password').fill('Synthetic-demo-2026!');act('Approve source as second reviewer')
 login('CFG-01');p.get_by_label('Policy source').select_option(sid);result=act('Extract draft candidates');key=result['rule_ids'][0];p.get_by_label('Policy rule').select_option(key);expect(p.get_by_label('Rule interpretation JSON')).to_have_value(re.compile('.*UNINTERPRETED.*',re.S))
 fields={'interpretation':'ILLUSTRATIVE ONLY: unconditional ten percent copay on admissible amount, full synthetic clause reviewed.','representation':{'kind':'COPAY','percent':'10.00'},'conditions':[],'exceptions':[],'dependencies':['issued_member_schedule','dynamic_remaining_cover','hospital_contract_tariff'],'ambiguities':[],'context_reviewed':True,'effective_from':'2026-01-01','effective_to':None,'effective_date_quote':'Wording effective from 2026-01-01.','effective_date_page':1,'review_required':False}
 p.get_by_label('Rule interpretation JSON').fill(json.dumps(fields));act('Save interpretation');act('validate rule');act('review rule');p.get_by_label('Policy approval password').fill('Synthetic-demo-2026!');act('approve rule',422);p.screenshot(path=str(out/'policy-reviewed-evidence.png'),full_page=True)
 login('ADM-01');p.get_by_label('Policy rule').select_option(key);p.get_by_label('Policy approval password').fill('Synthetic-demo-2026!');act('approve rule');act('publish rule');blocked=act('Preview without changing runtime');assert blocked['draft_deduction_effects'] is None and blocked['definitive_payable'] is None;assert 'FINANCIAL_REVIEW_REQUIRED' in blocked['states'];p.screenshot(path=str(out/'policy-blocked-inputs.png'),full_page=True)
 # The exact document hash is fetched from the rendered source evidence, not invented.
 evidence=p.get_by_label('Original policy evidence').inner_text();sha=re.search(r'Original SHA256 ([0-9a-f]{64})',evidence).group(1)
 inputs={'illustrative':True,'member':{'issued_policy_evidence':'ILLUSTRATIVE-SCHEDULE','insurer_id':'STAR','uin':'SYNHLIP26001V012026','revision_hash':sha,'policy_period_start':'2026-01-01','policy_period_end':'2026-12-31','wording_effective_date':'2026-01-01','selected_options':[],'group_variations':{},'endorsement_evidence':'ILLUSTRATIVE-NO-ENDORSEMENTS'},'coverage':{'status':'ACTIVE','base_sum_insured':'500000.00','remaining_sum_insured':'500000.00','authoritative_evidence':'ILLUSTRATIVE-COVERAGE','as_of':datetime.now(ZoneInfo('Asia/Kolkata')).date().isoformat(),'reservations':'0.00','restoration_usage':'0.00','previous_claims':[],'benefit_utilisation':{}},'tariff':{'hospital_id':'HOSP-ILL-NN-07','agreement_id':'ILLUSTRATIVE-AGREEMENT','insurer_or_tpa':'ILLUSTRATIVE-INSURER','effective_from':'2026-01-01','effective_to':'2026-12-31','authoritative_evidence':'ILLUSTRATIVE-TARIFF','rates':{'item_caps':[],'room_rates':[]},'packages':[],'room_limits':{}}}
 p.get_by_label('Private input verification JSON').fill(json.dumps(inputs));result=act('Preview without changing runtime');assert result['definitive_payable'] is None;assert result['baseline_difference']['after']=='96831.00',result;p.screenshot(path=str(out/'policy-shadow-preview.png'),full_page=True)
 # Product history is also an illustrative, separately approved review simulation.
 login('CFG-01');p.get_by_label('History product identity').select_option('STAR:SYNHLIP26001V012026')
 history={'change':'RENAME','names':['Illustrative Demo','Star Health Illustrative Demo'],'evidence':[{'source_id':sid,'sha256':sha,'page':1,'quote':'Star Health Illustrative Demo'}],'interpretation':'ILLUSTRATIVE title alias only; no changed benefit or guessed effective date.','context_reviewed':True,'effective_from':None,'review_required':True}
 p.get_by_label('Product history JSON').fill(json.dumps(history));proposal=act('Propose product history')['proposal_id'];p.get_by_label('History proposal',exact=True).select_option(proposal);p.get_by_label('Policy approval password').fill('Synthetic-demo-2026!');act('Approve product history as second reviewer',422)
 login('ADM-01');p.get_by_label('History proposal',exact=True).select_option(proposal);p.get_by_label('Policy approval password').fill('Synthetic-demo-2026!');act('Approve product history as second reviewer');expect(p.get_by_label('Approved product history')).to_contain_text('ILLUSTRATIVE title alias');p.screenshot(path=str(out/'policy-product-history.png'),full_page=True)
 choose('Quarantined research record','illustrative-conflict');p.get_by_label('Policy source',exact=True).select_option(sid);p.get_by_label('Research remediation reason').fill('ILLUSTRATIVE exact identity/hash matched to reviewed source');act('Resolve against approved source')
 choose('Quarantined research record','exact UIN missing/invalid/placeholder');p.get_by_label('Research remediation reason').fill('ILLUSTRATIVE admin test: placeholder UIN requires corrected export');act('Reject research entry');p.screenshot(path=str(out/'policy-quarantine-review.png'),full_page=True)
 report.update(public_source=public_sid,illustrative_source=sid,rule_id=key,source_sha256=sha);browser.close()
(out/'policy-browser-proof.json').write_text(json.dumps(report,indent=2));print('policy browser: public-source gate, original page, illustrative four-eyes lifecycle, missing inputs, exact same-engine shadow preview passed')
