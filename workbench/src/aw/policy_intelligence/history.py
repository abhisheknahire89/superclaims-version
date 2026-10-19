"""Evidence-reviewed names/status and quarantine remediation; never financial authority."""
from datetime import date
from . import registry as r
from .extraction import grounded
from .acquisition import Library

def propose(c,p,ctx,product,data):
 p.require('config.author')
 row=c.fetch_one("SELECT body FROM policy_knowledge_record WHERE tenant_id=$1 AND record_id=$2 AND kind='InsuranceProduct'",p.tenant_id,product)
 if not row:r.fail('product identity not found')
 if data.get('change') not in ('RENAME','WITHDRAWN','ACTIVE'):r.fail('explicit product history change required')
 if data.get('context_reviewed') is not True or not isinstance(data.get('interpretation'),str) or not data['interpretation'].strip():r.fail('explicit reviewed history interpretation required')
 evidence=data.get('evidence')
 if not isinstance(evidence,list) or not evidence:r.fail('original document evidence required')
 if data['change']=='RENAME' and (not isinstance(data.get('names'),list) or len(set(data['names']))<2):r.fail('old and new names required')
 supported_names=set(row['body']['marketing_names']);canonical=[]
 for e in evidence:
  source,path=r.source(c,p.tenant_id,e.get('source_id'),ctx);identity=source['body']['identity']
  verification=c.fetch_one("SELECT body FROM policy_knowledge_record WHERE tenant_id=$1 AND kind='SourceVerification' AND body->>'source_id'=$2 AND (body->>'state'='APPROVED_SOURCE' OR body->>'identity_match_verified'='true') ORDER BY created_at DESC LIMIT 1",p.tenant_id,e.get('source_id'))
  if not verification:r.fail('independently reviewed source identity required')
  supported_names.update((identity['product_name'],verification['body']['product_title_quote']))
  if e.get('sha256') and e['sha256']!=source['body']['sha256']:r.fail('history evidence hash conflicts with original')
  canonical.append({**e,'sha256':source['body']['sha256']})
  if identity['insurer']!=row['body']['insurer_id'] or identity['uin']!=row['body']['uin']:r.fail('product history conflicts with exact insurer/UIN')
  grounded(path,e)
 if data['change']=='WITHDRAWN' and not any('withdraw' in e['quote'].lower() for e in evidence):r.fail('withdrawal needs explicit original evidence')
 if data['change']=='ACTIVE' and not any('active' in e['quote'].lower() for e in evidence):r.fail('active status needs explicit original evidence')
 if data['change']=='RENAME' and (not set(data['names']).intersection(row['body']['marketing_names']) or not set(data['names']).issubset(supported_names)):r.fail('rename must bind an existing marketing identity and independently verified source titles')
 evidence=canonical
 if data['change']=='RENAME' and any(not isinstance(n,str) or not n.strip() or not any(n in e['quote'] for e in evidence) for n in data['names']):r.fail('every name must have original evidence')
 if data.get('effective_from'):
  date.fromisoformat(data['effective_from'])
  if not any(data['effective_from'] in e['quote'] for e in evidence):r.fail('history effective date requires quoted evidence')
 elif data.get('review_required') is not True:r.fail('unknown product status/name date requires review')
 body={'product_id':product,'state':'DRAFT','author':p.user_id,'change':data['change'],'names':data.get('names',[]),'evidence':evidence,'effective_from':data.get('effective_from'),'interpretation':data['interpretation'],'context_reviewed':True,'review_required':not bool(data.get('effective_from'))}
 key=r.record(c,p.tenant_id,'ProductHistory',body,p.user_id);r.event(c,p,key,'PRODUCT_HISTORY_PROPOSED',body);return {'proposal_id':key,'state':'DRAFT'}

def approve(c,p,ctx,key):
 p.require('config.publish');row=c.fetch_one("SELECT * FROM policy_knowledge_record WHERE tenant_id=$1 AND record_id=$2 AND kind='ProductHistory'",p.tenant_id,key)
 if not row or row['body']['state']!='DRAFT':r.fail('draft product history required')
 b=row['body']
 if b['author']==p.user_id:r.fail('product author and approver must differ')
 if c.fetch_one("SELECT record_id FROM policy_knowledge_record WHERE tenant_id=$1 AND kind='ProductHistory' AND body->>'proposal_id'=$2",p.tenant_id,key):r.fail('history already approved')
 # Recheck source originals/approval/evidence at publication, not just draft entry.
 for e in b['evidence']:
  source,path=r.source(c,p.tenant_id,e['source_id'],ctx);grounded(path,e)
  if e['sha256']!=source['body']['sha256']:r.fail('history original changed')
 out={**b,'state':'APPROVED','proposal_id':key,'approver':p.user_id};identifier=r.record(c,p.tenant_id,'ProductHistory',out,p.user_id);r.event(c,p,key,'PRODUCT_HISTORY_APPROVED',out);return {'history_id':identifier,**out}

def remediate(c,p,ctx,key,data,reject=False):
 p.require('config.publish');repository=data.get('repository','public');lib=Library(r.root(ctx,repository))
 try:
  entry=next((e for e in lib.entries() if e['id']==key),None)
  if not entry:r.fail('research entry not found')
  overlay=c.fetch_one("SELECT body FROM policy_knowledge_record WHERE tenant_id=$1 AND kind='ResearchRemediation' AND body->>'research_id'=$2 AND body->>'repository'=$3 ORDER BY created_at DESC,record_id DESC LIMIT 1",p.tenant_id,key,repository)
  latest=lib.db.execute('SELECT sha256 FROM retrieval WHERE discovery_id=? ORDER BY id DESC LIMIT 1',(key,)).fetchone()
  if overlay and (overlay['body']['state']=='REJECTED' or (latest and overlay['body'].get('sha256')==latest['sha256'])):entry={**entry,'state':overlay['body']['state']}
  reason=data.get('reason')
  if not isinstance(reason,str) or len(reason.strip())<12:r.fail('explicit remediation reason required')
  if reject:
   latest=lib.db.execute('SELECT sha256 FROM retrieval WHERE discovery_id=? ORDER BY id DESC LIMIT 1',(key,)).fetchone()
   if latest and c.fetch_one("SELECT record_id FROM policy_knowledge_record WHERE tenant_id=$1 AND kind='SourceVerification' AND body->>'state'='APPROVED_SOURCE' AND body->>'sha256'=$2",p.tenant_id,latest['sha256']):r.fail('approved source requires reviewed history; research rejection cannot revoke it silently')
   state='REJECTED'
  else:
   if entry['state']=='REJECTED':r.fail('rejected entry requires a corrected new import')
   sid=data.get('source_id');source,_=r.source(c,p.tenant_id,sid,ctx,True);body=entry['body'];m=source['body'];i=m['identity']
   latest=lib.db.execute('SELECT sha256 FROM retrieval WHERE discovery_id=? ORDER BY id DESC LIMIT 1',(key,)).fetchone()
   if m.get('repository','public')!=repository or not latest or latest['sha256']!=m['sha256'] or body['insurer']!=i['insurer'] or body['uin']!=i['uin']:r.fail('resolution requires same original hash and approved exact identity')
   approved_names={i['product_name']}
   for row in c.fetch_all("SELECT body FROM policy_knowledge_record WHERE tenant_id=$1 AND kind='ProductHistory' AND body->>'product_id'=$2 AND body->>'state'='APPROVED'",p.tenant_id,i['insurer']+':'+i['uin']):
    if row['body']['change']=='RENAME':approved_names.update(row['body']['names'])
   if body['product_name'] not in approved_names:r.fail('conflicting marketing identity needs evidence-reviewed rename history')
   # Incorrect URLs, malformed rows or UINs cannot be repaired by a rename decision.
   if any('UIN reused' not in x for x in entry['reasons']) and entry['state']=='METADATA_CONFLICT':r.fail('non-name conflict requires corrected import')
   state='CONTENT_VERIFIED'
  r.record(c,p.tenant_id,'ResearchRemediation',{'research_id':key,'repository':repository,'reason':reason,'state':state,'source_id':data.get('source_id'),'actor':p.user_id,'sha256':latest['sha256'] if latest else None},p.user_id)
  r.event(c,p,key,'RESEARCH_REJECTED' if reject else 'RESEARCH_RESOLVED',{'repository':repository,'reason':reason,'state':state,'source_id':data.get('source_id')});return {'research_id':key,'state':state}
 finally:lib.close()
