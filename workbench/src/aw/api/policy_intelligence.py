"""Local policy review and shadow preview; acquisition remains a separate CLI."""
import base64
from ..policy_intelligence import registry as r,extraction,review,preview,history
from ..policy_intelligence.acquisition import Library
from .core import Problem

def register(api):
 ctx=api.ctx
 def permission(p):
  if not (p.can('config.author') or p.can('config.publish')):p.require('config.author')
 def confirm(c,p,data):
  from ..local_auth import matches
  credential=c.fetch_val('SELECT password_hash FROM local_credential WHERE tenant_id=$1 AND user_id=$2',p.tenant_id,p.user_id)
  if not credential or not matches(data.get('current_password',''),credential):raise Problem(401,'reauthentication-required','confirm password for source approval or rule approval/publication')
 @api.op('listPolicyIntelligence','/v1/policy-intelligence','GET')
 def listing(c,p,req,body):
  permission(p);research={'records':[],'retrievals':[]}
  for repository in ('public','illustrative'):
   lib=Library(r.root(ctx,repository))
   try:
    report=lib.report();research['records'] += [{**x,'repository':repository} for x in report['records']];research['retrievals'] += [{**x,'repository':repository} for x in report['retrievals']]
   finally:lib.close()
  records=c.fetch_all('SELECT * FROM policy_knowledge_record WHERE tenant_id=$1 ORDER BY created_at',p.tenant_id)
  latest_hash={(x['repository'],x['discovery_id']):x['sha256'] for x in research['retrievals']}
  for record in records:
   if record['kind']=='ResearchRemediation':
    b=record['body']
    for entry in research['records']:
     if entry['id']==b['research_id'] and entry['repository']==b['repository'] and (b['state']=='REJECTED' or b.get('sha256')==latest_hash.get((b['repository'],b['research_id']))):entry.update(state=b['state'],tenant_review_reason=b['reason'])
  return 200,{'research':research,'records':records,'rules':c.fetch_all('SELECT * FROM policy_rule_candidate WHERE tenant_id=$1 ORDER BY rule_id',p.tenant_id),'events':c.fetch_all('SELECT * FROM policy_review_event WHERE tenant_id=$1 ORDER BY occurred_at',p.tenant_id),'mode':'SHADOW_ONLY'},None
 @api.op('actPolicyIntelligence','/v1/policy-intelligence/actions','POST')
 def action(c,p,req,body):
  permission(p);action=body['action'];target=body['target'];data=body.get('data',{})
  if action in ('verify_source','approve_rule','publish_rule','approve_product_history','reject_research','resolve_research'):p.require('config.publish');confirm(c,p,data)
  if action=='intake_source':out=r.intake(c,p,ctx,target,data.get('repository','public'))
  elif action=='verify_source':out=r.verify(c,p,ctx,target,{k:v for k,v in data.items() if k!='current_password'})
  elif action=='extract_rules':out=extraction.extract(c,p,ctx,target)
  elif action=='propose_product_history':out=history.propose(c,p,ctx,target,data)
  elif action=='approve_product_history':out=history.approve(c,p,ctx,target)
  elif action in ('reject_research','resolve_research'):out=history.remediate(c,p,ctx,target,data,action=='reject_research')
  elif action=='preview':out=preview.preview(c,p,ctx,target,data['claim_id'],data.get('inputs',{}))
  else:out=review.change(c,p,ctx,target,action,{k:v for k,v in data.items() if k!='current_password'})
  return 200,out,None
 @api.op('getPolicySourcePage','/v1/policy-intelligence/sources/{source_id}/pages/{page_no}','GET')
 def page(c,p,req,body):
  permission(p);row,path=r.source(c,p.tenant_id,req.path_params['source_id'],ctx)
  try:number=int(req.path_params['page_no'])
  except ValueError:raise Problem(422,'page-invalid','integer page required')
  if not 1<=number<=row['body']['page_count']:raise Problem(422,'page-invalid','page outside original document')
  from ..extraction.pages import render_png
  from ..policy_intelligence.pages import read_pdf
  text=read_pdf(path.read_bytes())[number-1].text
  return 200,{'sha256':row['body']['sha256'],'page':number,'text':text,'image_base64':base64.b64encode(render_png(path.read_bytes(),number)).decode()},None
