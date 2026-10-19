"""Reviewed interpretations and four-eyes shadow publishing; no runtime config mutation."""
from datetime import date
from decimal import Decimal
from ..db import Json
from . import registry as r
from .extraction import grounded
SUPPORTED={'COPAY':'R-CLAIM-COPAY','DEDUCTIBLE':'R-CLAIM-DEDUCTIBLE'}

def get(c,p,key):
 row=c.fetch_one('SELECT * FROM policy_rule_candidate WHERE tenant_id=$1 AND rule_id=$2 FOR UPDATE',p.tenant_id,key)
 if not row:r.fail('rule not found')
 return row

def valid(c,p,ctx,row):
 source,path=r.source(c,p.tenant_id,row['source_id'],ctx,True);b=row['body'];identity=source['body']['identity']
 if b.get('sha256')!=source['body']['sha256'] or b.get('revision_hash')!=b.get('sha256') or b.get('uin')!=identity['uin'] or b.get('insurer')!=identity['insurer']:r.fail('candidate identity or document hash conflicts')
 grounded(path,b)
 if not isinstance(b.get('interpretation'),str) or not b['interpretation'].strip() or b.get('context_reviewed') is not True or b.get('ambiguities')!=[]:r.fail('explicit contextual interpretation and resolution of ambiguities required')
 if not isinstance(b.get('conditions'),list) or not isinstance(b.get('exceptions'),list) or not isinstance(b.get('dependencies'),list):r.fail('conditions/exceptions/dependencies must be explicitly reviewed')
 if not b.get('effective_from') and not b.get('review_required'):r.fail('unknown dates require review flag')
 if b.get('effective_from'):
  date.fromisoformat(b['effective_from'])
  if not b.get('effective_date_quote') or b['effective_from'] not in b['effective_date_quote']:r.fail('effective date must have source evidence')
  grounded(path,{'page':b.get('effective_date_page'),'quote':b['effective_date_quote']})
 if b.get('effective_to'):
  date.fromisoformat(b['effective_to'])
  if not b.get('effective_end_quote') or b['effective_to'] not in b['effective_end_quote']:r.fail('effective end date must have source evidence')
  grounded(path,{'page':b.get('effective_end_page'),'quote':b['effective_end_quote']})
  if not b.get('effective_from') or b['effective_to']<b['effective_from']:r.fail('invalid effective interval')
 rep=b.get('representation',{});kind=rep.get('kind')
 if kind in SUPPORTED:
  name='percent' if kind=='COPAY' else 'amount';value=rep.get(name)
  if not isinstance(value,str):r.fail('exact decimal string required')
  try:n=Decimal(value)
  except Exception:r.fail('invalid exact amount')
  if not n.is_finite() or n<0 or (kind=='COPAY' and n>100) or (kind!='COPAY' and n.as_tuple().exponent<-2):r.fail('invalid financial parameter')
  # Numbers alone are not semantics; human contextual interpretation remains mandatory.
  import re
  quoted=[Decimal(x.replace(',','')) for x in re.findall(r'(?<![\w.])\d[\d,]*(?:\.\d+)?',b['quote'])]
  if n not in quoted:r.fail('interpreted numeric parameter not supported by quotation')
  if kind=='COPAY' and ('%' not in b['quote'] and 'percent' not in b['quote'].lower()):r.fail('copay percentage evidence required')
  if rep.get('selected_option') and 'selected_options' not in b['dependencies']:r.fail('optional benefit needs member-selection dependency')
 return {'valid':True,'translation_supported':kind in SUPPORTED,'review_required':bool(b.get('review_required'))}

def change(c,p,ctx,key,action,body):
 row=get(c,p,key);old=row['state'];b=row['body']
 if action=='revise_rule':
  p.require('config.author')
  if old in ('APPROVED','PUBLISHED'):r.fail('approved rule immutable; extract/create a new candidate')
  # Evidence identity cannot be edited into a different source.
  allowed=('interpretation','representation','conditions','exceptions','dependencies','ambiguities','context_reviewed','effective_from','effective_to','effective_date_quote','effective_date_page','effective_end_quote','effective_end_page','review_required')
  if set(body)-set(allowed):r.fail('unknown or immutable interpretation field')
  b={**b,**body};c.execute("UPDATE policy_rule_candidate SET body=$3::jsonb,state='DRAFT',authored_by=$4,reviewed_by=NULL,approved_by=NULL,row_version=row_version+1 WHERE tenant_id=$1 AND rule_id=$2",p.tenant_id,key,Json(b),p.user_id);new='DRAFT'
 else:
  if action in ('validate_rule','review_rule'):p.require('config.author')
  else:p.require('config.publish')
  expected={'validate_rule':('DRAFT','VALIDATED'),'review_rule':('VALIDATED','HUMAN_REVIEWED'),'approve_rule':('HUMAN_REVIEWED','APPROVED'),'publish_rule':('APPROVED','PUBLISHED')}
  if action not in expected:r.fail('unknown lifecycle action')
  before,new=expected[action]
  if old!=before:r.fail('rule lifecycle must advance in order')
  valid(c,p,ctx,row)
  if action in ('approve_rule','publish_rule') and row['authored_by']==p.user_id:r.fail('author and approver/publisher must differ')
  reviewed=p.user_id if action=='review_rule' else row['reviewed_by'];approved=p.user_id if action=='approve_rule' else row['approved_by']
  c.execute('UPDATE policy_rule_candidate SET state=$3,reviewed_by=$4,approved_by=$5,row_version=row_version+1 WHERE tenant_id=$1 AND rule_id=$2',p.tenant_id,key,new,reviewed,approved)
  if new=='APPROVED':r.record(c,p.tenant_id,'RuleApproval',{'rule_id':key,'author':row['authored_by'],'reviewer':reviewed,'approver':approved,'interpretation':b['interpretation'],'sha256':b['sha256']},p.user_id)
  if new=='PUBLISHED':r.record(c,p.tenant_id,'PolicyRuleMapping',{'rule_id':key,'engine_rule_id':SUPPORTED.get(b['representation']['kind']),'mode':'SHADOW_ONLY','executable':False,'review_required':b.get('review_required',True)},p.user_id)
 r.event(c,p,key,action,{'before':old,'after':new,'body':b});return {'rule_id':key,'state':new,'mode':'SHADOW_ONLY'}
