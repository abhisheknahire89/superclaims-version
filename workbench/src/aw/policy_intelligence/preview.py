"""Controlled supported-rule translation into the SAME deterministic engine, never a decision."""
from copy import deepcopy
from datetime import date, datetime
from zoneinfo import ZoneInfo
import re
from decimal import Decimal
from .. import evaluations
from ..engine import evaluate
from . import registry as r
from .review import valid,SUPPORTED

REQUIREMENTS={
 'member':('issued_policy_evidence','insurer_id','uin','revision_hash','policy_period_start','policy_period_end','wording_effective_date','selected_options','group_variations','endorsement_evidence'),
 'coverage':('status','base_sum_insured','remaining_sum_insured','authoritative_evidence','as_of','reservations','restoration_usage','previous_claims','benefit_utilisation'),
 'tariff':('hospital_id','agreement_id','insurer_or_tpa','effective_from','effective_to','authoritative_evidence','rates','packages','room_limits')}

def readiness(bundle,rule,source_verification,treatment_date):
 tasks=[];states=[]
 for layer,fields in REQUIREMENTS.items():
  for field in fields:
   if bundle.get(layer,{}).get(field) is None or (isinstance(bundle.get(layer,{}).get(field),str) and (not bundle[layer][field].strip() or bundle[layer][field].strip().upper()=='UNKNOWN')):tasks.append({'layer':layer,'field':field,'reason':'authoritative customer/insurer information required; public wording cannot supply this'})
 m=bundle.get('member',{});cov=bundle.get('coverage',{});tar=bundle.get('tariff',{})
 matched=m.get('insurer_id')==rule['insurer'] and m.get('uin')==rule['uin'] and m.get('revision_hash')==rule['revision_hash']
 states.append('POLICY_MATCHED' if matched else 'POLICY_UNVERIFIED')
 if not matched:tasks.append({'layer':'member','field':'product_revision','reason':'issued contract must bind exact insurer/UIN/revision, not newest wording'})
 if any(t['layer']=='member' for t in tasks):states.append('CONTRACT_INCOMPLETE')
 if any(t['layer']=='coverage' for t in tasks):states.append('BENEFITS_UNVERIFIED')
 if any(t['layer']=='tariff' for t in tasks):states.append('TARIFF_UNVERIFIED')
 if not source_verification.get('wording_effective_from') or rule.get('review_required') or not rule.get('effective_from'):tasks.append({'layer':'public_policy','field':'effective_dates','reason':'wording or rule effective period UNKNOWN; applicability requires review'})
 try:
  treatment=date.fromisoformat(treatment_date);start=date.fromisoformat(m['policy_period_start']);end=date.fromisoformat(m['policy_period_end']);word=date.fromisoformat(source_verification['wording_effective_from']);word_end=date.fromisoformat(source_verification['wording_effective_to']) if source_verification.get('wording_effective_to') else None
  if not start<=treatment<=end or start<word or (word_end and start>word_end) or m.get('wording_effective_date')!=source_verification['wording_effective_from']:raise ValueError()
  if treatment<date.fromisoformat(rule['effective_from']) or (rule.get('effective_to') and treatment>date.fromisoformat(rule['effective_to'])):raise ValueError()
  if not date.fromisoformat(tar['effective_from'])<=treatment<=date.fromisoformat(tar['effective_to']):raise ValueError()
 except (ValueError,KeyError,TypeError):tasks.append({'layer':'applicability','field':'distinct_dates','reason':'issued period/wording/treatment/tariff dates missing or conflicting'})
 if cov.get('status')!='ACTIVE':tasks.append({'layer':'coverage','field':'status','reason':'active policy status not verified'})
 option=rule.get('representation',{}).get('selected_option')
 if option and (m.get('selected_options') is None or option not in m['selected_options']):tasks.append({'layer':'member','field':'selected_options','reason':'available add-on is not evidence it was purchased'})
 if rule.get('conditions') or rule.get('exceptions') or m.get('group_variations'):
  tasks.append({'layer':'interpretation','field':'conditions/exceptions/group_variations','reason':'conditional/group translation requires review; no retail-default assumption'})
 try:
  if date.fromisoformat(cov['as_of'])!=datetime.now(ZoneInfo('Asia/Kolkata')).date():raise ValueError()
 except (ValueError,KeyError,TypeError):tasks.append({'layer':'coverage','field':'as_of','reason':'current local-date authoritative coverage snapshot required'})
 try:
  values=[]
  for name in ('base_sum_insured','remaining_sum_insured','reservations','restoration_usage'):
   value=cov[name]
   if not isinstance(value,str) or not re.fullmatch(r'\d+\.\d{2}',value):raise ValueError()
   values.append(Decimal(value))
  base,remaining,reserved,restored=values
  if remaining+reserved>base or restored!=0:raise ValueError()
 except (ValueError,KeyError,TypeError):tasks.append({'layer':'coverage','field':'balance_reconciliation','reason':'exact nonnegative paise amounts and remaining cover net of reservations required; restoration translation unsupported'})
 for dep in rule.get('dependencies',[]):
  if dep not in ('issued_member_schedule','dynamic_remaining_cover','hospital_contract_tariff','selected_options'):
   tasks.append({'layer':'dependency','field':str(dep),'reason':'unsupported rule dependency requires authoritative verification and reviewed translation'})
 if not isinstance(m.get('selected_options'),list) or not isinstance(m.get('group_variations'),dict):tasks.append({'layer':'member','field':'options_and_variations','reason':'explicit structured selections and group variations required'})
 if not isinstance(cov.get('previous_claims'),list) or not isinstance(cov.get('benefit_utilisation'),dict):tasks.append({'layer':'coverage','field':'claim_utilisation','reason':'explicit claim history and benefit utilisation required'})
 if not isinstance(tar.get('rates'),dict) or any(not isinstance(tar.get('rates',{}).get(k),list) for k in ('item_caps','room_rates')) or not isinstance(tar.get('packages'),list) or not isinstance(tar.get('room_limits'),dict):tasks.append({'layer':'tariff','field':'structured_rates','reason':'explicit contracted rates/packages/room limits required; no public price substitutions'})
 for layer,state in (('member','CONTRACT_INCOMPLETE'),('coverage','BENEFITS_UNVERIFIED'),('tariff','TARIFF_UNVERIFIED')):
  if any(t['layer']==layer for t in tasks) and state not in states:states.append(state)
 states.append('FINANCIAL_REVIEW_REQUIRED' if tasks else 'FINANCIAL_INPUTS_VERIFIED');return {'states':states,'verification_tasks':tasks,'unknown_values_preserved':True}

def preview(c,p,ctx,key,claim_id,bundle):
 if not (p.can('config.author') or p.can('config.publish')):p.require('config.author')
 row=c.fetch_one('SELECT * FROM policy_rule_candidate WHERE tenant_id=$1 AND rule_id=$2',p.tenant_id,key)
 if not row or row['state']!='PUBLISHED':r.fail('only four-eyes published shadow rules can be previewed')
 valid(c,p,ctx,row);source,_=r.source(c,p.tenant_id,row['source_id'],ctx,True)
 verifications=c.fetch_all("SELECT body FROM policy_knowledge_record WHERE tenant_id=$1 AND kind='SourceVerification' AND body->>'source_id'=$2 AND body->>'state'='APPROVED_SOURCE'",p.tenant_id,row['source_id'])
 if len(verifications)!=1:r.fail('source applicability approval is ambiguous')
 claim,cfg=evaluations.build_engine_input(c,p.tenant_id,claim_id,'SHADOW_PREVIEW');b=row['body'];ready=readiness(bundle,b,verifications[0]['body'],claim.get('admission_date'))
 histories=c.fetch_all("SELECT body FROM policy_knowledge_record WHERE tenant_id=$1 AND kind='ProductHistory' AND body->>'product_id'=$2 AND body->>'state'='APPROVED'",p.tenant_id,b['insurer']+':'+b['uin'])
 for history in histories:
  h=history['body']
  if h['change']=='WITHDRAWN':
   ready['verification_tasks'].append({'layer':'public_policy','field':'withdrawal_applicability','reason':'withdrawal history requires issued-contract continuation review; no automatic coverage inference'})
 out={**ready,'mode':'SHADOW_ONLY','persisted':False,'verification_scope':'ILLUSTRATIVE_INTERFACE_INPUTS_ONLY; private evidence not independently connected','definitive_payable':None,'applicable_policy_version':{'insurer':b['insurer'],'uin':b['uin'],'revision_hash':b['revision_hash'],'source_id':row['source_id']},'matched_clauses':[{'page':b['page'],'quote':b['quote'],'clause':b['clause_id'],'sha256':b['sha256']}],'draft_deduction_effects':None,'baseline_difference':None}
 if b['representation']['kind'] not in SUPPORTED:out['verification_tasks'].append({'layer':'interpretation','field':'rule_type','reason':'no reviewed translation to existing engine for this type'})
 if out['verification_tasks']:
  out['states']=[x for x in out['states'] if x!='FINANCIAL_INPUTS_VERIFIED']
  if 'FINANCIAL_REVIEW_REQUIRED' not in out['states']:out['states'].append('FINANCIAL_REVIEW_REQUIRED')
  return out
 # This milestone intentionally accepts ONLY clearly labelled synthetic interface bundles.
 if bundle.get('illustrative') is not True:r.fail('private-data interface is not connected; use explicitly illustrative synthetic inputs only')
 coverage=bundle['coverage'];base=Decimal(coverage['base_sum_insured']);remaining=Decimal(coverage['remaining_sum_insured'])
 if not base.is_finite() or not remaining.is_finite() or not 0<=remaining<=base or coverage['restoration_usage']!='0.00':r.fail('unsupported restoration/balance; verification required')
 if bundle['tariff']['hospital_id']!=claim['hospital_id']:r.fail('tariff hospital does not match claim')
 # The legacy engine encodes available cover as base+bonus-ledger debit. This is a
 # transient adapter offset, NOT a statement of previous claims or ledger mutation.
 shadow_claim=deepcopy(claim);shadow_claim['policy'].update(base_sum_insured=str(base),cumulative_bonus='0.00',paid_in_current_year=str(base-remaining))
 policy=deepcopy(cfg['policy']);rep=b['representation'];kind=rep['kind'];rid=SUPPORTED[kind]
 policy['config_id']='SHADOW:'+key;policy['config_version']=b['revision_hash'];policy['clause_refs'][rid]={'doc_id':row['source_id']+'#sha256:'+b['sha256'],'clause':b['clause_id']}
 if kind=='COPAY':policy['co_payment']['rules']=[{'rule_code':'SHADOW-COPAY','condition':{'age_at_admission_gte':0},'percent':rep['percent']}]
 elif kind=='DEDUCTIBLE':policy['deductible']={'amount':rep['amount'],'applies':'PER_CLAIM'}

 # Price data are supplied explicitly, never substituted from public price lists.
 tariff=deepcopy(cfg['tariff']) if cfg['tariff'] else {'tariff_id':'ILLUSTRATIVE-SHADOW-TARIFF','tariff_version':'preview','hospital_id':claim['hospital_id'],'uniform_pricing_across_room_categories':False};tariff['item_caps']=bundle['tariff']['rates']['item_caps'];tariff['room_rates']=bundle['tariff']['rates']['room_rates'];tariff['packages']=bundle['tariff']['packages'];tariff['agreement_doc_id']=bundle['tariff']['authoritative_evidence'];tariff['agreement_clause']=bundle['tariff']['agreement_id']
 before=evaluate(claim,cfg['policy'],cfg['nme'],cfg['tariff']);after=evaluate(shadow_claim,policy,cfg['nme'],tariff)
 out.update(draft_deduction_effects=after['adjustments'],illustrative_shadow_recommendation=after['recommendation'],baseline_difference={'before':before['recommendation']['recommended_payable'],'after':after['recommendation']['recommended_payable'],'note':'synthetic baseline plus one translated clause; not a complete contract calculation'},translation={'engine_rule':rid,'authority':policy['clause_refs'][rid],'source_quote':b['quote'],'ledger_mutated':False});return out
