"""Tenant-scoped immutable public knowledge; no operational config writes."""
import hashlib,json,uuid
from datetime import date
from pathlib import Path
from ..db import Json
from ..errors import AppError
from .acquisition import Library,UIN,insurer,HOSTS

def root(ctx,repository='public'):
 if repository not in ('public','illustrative'):fail('unknown source repository')
 return Path(ctx.settings.pack_dir)/('workbench/.policy-research' if repository=='public' else 'workbench/.policy-illustrative')
def fail(message):raise AppError(422,'policy-intelligence-invalid',message)
def uid(prefix):return prefix+'-'+uuid.uuid4().hex

def record(c,tenant,kind,body,actor,identifier=None):
 key=identifier or uid(kind)
 c.execute('INSERT INTO policy_knowledge_record(tenant_id,record_id,kind,body,created_by) VALUES($1,$2,$3,$4::jsonb,$5)',tenant,key,kind,Json(body),actor)
 return key

def event(c,p,subject,action,details):c.execute('INSERT INTO policy_review_event(tenant_id,event_id,subject_id,actor_user_id,action,details) VALUES($1,$2,$3,$4,$5,$6::jsonb)',p.tenant_id,uid('EV'),subject,p.user_id,action,Json(details))
def source(c,tenant,key,ctx,approved=False):
 row=c.fetch_one("SELECT * FROM policy_knowledge_record WHERE tenant_id=$1 AND record_id=$2 AND kind='DocumentVersion'",tenant,key)
 if not row:fail('source version not found')
 lib=Library(root(ctx,row['body'].get('repository','public')))
 try:
  path=lib.original(row['body']['sha256']);m=lib.metadata(path.read_bytes())
  if m['identified_uins']!=[row['body']['identity']['uin']]:fail('original source UIN conflicts with registry')
 finally:lib.close()
 if approved and not c.fetch_one("SELECT record_id FROM policy_knowledge_record WHERE tenant_id=$1 AND kind='SourceVerification' AND body->>'source_id'=$2 AND body->>'state'='APPROVED_SOURCE'",tenant,key):fail('source identity has not been approved by a human')
 return row,path

def intake(c,p,ctx,key,repository='public'):
 p.require('config.author');lib=Library(root(ctx,repository))
 try:
  d=lib.db.execute('SELECT * FROM discovery WHERE id=?',(key,)).fetchone();r=lib.db.execute('SELECT * FROM retrieval WHERE discovery_id=? ORDER BY id DESC LIMIT 1',(key,)).fetchone()
  review=c.fetch_one("SELECT body FROM policy_knowledge_record WHERE tenant_id=$1 AND kind='ResearchRemediation' AND body->>'research_id'=$2 AND body->>'repository'=$3 ORDER BY created_at DESC,record_id DESC LIMIT 1",p.tenant_id,key,repository)
  applicable_review=bool(review and (review['body']['state']=='REJECTED' or (r and review['body'].get('sha256')==r['sha256'])))
  state=review['body']['state'] if applicable_review else d['state'] if d else None
  pending=bool(d and r and state=='METADATA_CONFLICT' and all('UIN reused' in x for x in json.loads(d['reasons'])) and json.loads(r['metadata']).get('identified_uins')==[json.loads(d['body'])['uin']])
  if not d or (state!='CONTENT_VERIFIED' and not pending) or not r:fail('only uniquely content-matched downloaded candidates may enter review')
  b=json.loads(r['metadata']);b['repository']=repository;b['identity_conflict_pending']=pending;lib.original(r['sha256']);identity=b['identity'];product=identity['insurer']+':'+identity['uin']
  if not c.fetch_one('SELECT record_id FROM policy_knowledge_record WHERE tenant_id=$1 AND record_id=$2',p.tenant_id,product):
   record(c,p.tenant_id,'InsuranceProduct',{'insurer_id':identity['insurer'],'uin':identity['uin'],'marketing_names':[identity['product_name']],'status':'UNKNOWN'},p.user_id,product)
  sid=uid('DOCV');record(c,p.tenant_id,'PolicyDocument',{'product_id':product,'kind':identity.get('document_type','POLICY_WORDING'),'source_discovery_id':key},p.user_id)
  record(c,p.tenant_id,'ProductRevision',{'product_id':product,'revision_hash':r['sha256'],'revision_label':identity.get('declared_revision'),'wording_effective_from':None,'wording_effective_to':None,'review_required':True},p.user_id)
  record(c,p.tenant_id,'DocumentVersion',b,p.user_id,sid);event(c,p,sid,'SOURCE_INTAKE',{'sha256':r['sha256'],'research_state':d['state']});return {'source_id':sid,'state':'CONTENT_VERIFIED'}
 finally:lib.close()

def verify(c,p,ctx,sid,body):
 p.require('config.publish');row,path=source(c,p.tenant_id,sid,ctx);b=row['body'];identity=b['identity']
 if row['created_by']==p.user_id:fail('source importer and verifier must differ')
 from .pages import read_pdf
 pages=read_pdf(path.read_bytes());quote=body.get('identity_quote','');title=body.get('product_title_quote','');legal=body.get('legal_name_quote','')
 first='\n'.join(pg.text for pg in pages[:3])
 if not quote or identity['uin'] not in quote or quote not in first:fail('exact source identity quotation required on first three pages')
 if not title or title not in first or identity['product_name'].lower() not in title.lower():fail('actual product title must support declared marketing identity')
 if not legal or legal not in '\n'.join(pg.text for pg in pages) or insurer(legal)!=identity['insurer']:fail('exact matching insurer legal-name quotation required')
 if body.get('uin')!=identity['uin'] or body.get('insurer')!=identity['insurer']:fail('conflicting product identifiers')
 if not body.get('revision_label'):fail('explicit revision label or hash label required')
 for field in ('wording_effective_from','wording_effective_to'):
  if body.get(field):date.fromisoformat(body[field])
 if body.get('wording_effective_from') and (not body.get('effective_date_quote') or body['effective_date_quote'] not in '\n'.join(pg.text for pg in pages) or body['wording_effective_from'] not in body['effective_date_quote']):fail('effective date needs exact source evidence; otherwise leave UNKNOWN')
 if body.get('wording_effective_to') and (not body.get('effective_end_quote') or body['wording_effective_to'] not in body['effective_end_quote'] or body['effective_end_quote'] not in '\n'.join(pg.text for pg in pages)):fail('effective end date needs exact source evidence; otherwise leave UNKNOWN')
 if body.get('wording_effective_from') and body.get('wording_effective_to') and body['wording_effective_from']>body['wording_effective_to']:fail('inverted wording period')
 pending=b.get('identity_conflict_pending',False)
 if pending:
  aliases=c.fetch_all("SELECT body FROM policy_knowledge_record WHERE tenant_id=$1 AND kind='ProductHistory' AND body->>'product_id'=$2 AND body->>'state'='APPROVED' AND body->>'change'='RENAME'",p.tenant_id,identity['insurer']+':'+identity['uin'])
  pending=not any(identity['product_name'] in a['body']['names'] for a in aliases)
 out={**body,'identity_match_verified':True,'source_id':sid,'sha256':b['sha256'],'state':'NEEDS_HUMAN_REVIEW' if pending else 'APPROVED_SOURCE','identity_conflict_pending':pending,'review_required':not bool(body.get('wording_effective_from'))}
 record(c,p.tenant_id,'Insurer',{'insurer_id':identity['insurer'],'legal_name':legal,'official_domains':HOSTS[identity['insurer']],'source_id':sid},p.user_id)
 record(c,p.tenant_id,'SourceVerification',out,p.user_id);event(c,p,sid,'SOURCE_IDENTITY_PENDING' if pending else 'SOURCE_APPROVED',out);return out
