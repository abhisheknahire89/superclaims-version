"""Local high-recall clause candidates. Keyword match is never a contractual interpretation."""
import re
from ..db import Json
from .pages import read_pdf
from . import registry as r
CATEGORIES={
 'ROOM_RENT':['room rent','room charges','room category'],'ICU':['intensive care','icu'],
 'PROPORTIONATE':['proportionate','proportional'],'COPAY':['co-payment','copayment','co-pay'],
 'DEDUCTIBLE':['deductible'],'SUBLIMIT':['sub-limit','sublimit','cataract'],
 'WAITING_PERIOD':['waiting period'],'EXCLUSION':['exclusion','excluded'],
 'PRE_POST':['pre-hospital','post-hospital'],'DAY_CARE':['day care','day-care'],
 'RESTORATION':['restore','restoration','reassure'],'NON_MEDICAL':['non-medical','non medical'],
 'PACKAGE':['package'],'NETWORK':['network provider','network hospital']}

def grounded(path,body,pages=None):
 pages=pages if pages is not None else read_pdf(path.read_bytes());page=body.get('page');quote=body.get('quote','')
 if not isinstance(page,int) or not 1<=page<=len(pages) or not quote or len(quote)>500 or quote not in pages[page-1].text:r.fail('quote is not found verbatim on original page')
 bbox=body.get('bbox')
 if bbox:
  pg=pages[page-1]
  if not isinstance(bbox,list) or len(bbox)!=4 or not all(isinstance(x,(int,float)) for x in bbox) or not (0<=bbox[0]<bbox[2]<=pg.width and 0<=bbox[1]<bbox[3]<=pg.height):r.fail('invalid evidence bounding box')
  found=[ln for ln in pg.lines if quote in ln['text']]
  if not any(abs(ln['x0']-bbox[0])<=1 and abs(ln['top']-bbox[1])<=1 and abs(ln['x1']-bbox[2])<=1 and abs(ln['bottom']-bbox[3])<=1 for ln in found):r.fail('quote and bounding box do not match source line')
 return pages[page-1]

def scan_document(path,m):
 """Offline draft proposals, never approval. Caller must retain source-review status."""
 identity=m['identity'];proposals=[];pages=read_pdf(path.read_bytes())
 for page in pages:
  for index,line in enumerate(page.lines):
   text=line['text'];cats=[k for k,v in CATEGORIES.items() if any(s in text.lower() for s in v)]
   if not cats or len(text)>500:continue
   clause={'sha256':m['sha256'],'page':page.page_no,'clause_id':f'p{page.page_no}:line{index+1}','quote':text,'bbox':[line['x0'],line['top'],line['x1'],line['bottom']]}
   grounded(path,clause,pages)
   proposals.append({**clause,'insurer':identity['insurer'],'uin':identity['uin'],'revision_hash':m['sha256'],'categories':cats,'representation':{'kind':'UNINTERPRETED'},'conditions':[],'exceptions':[],'dependencies':['issued_member_schedule','dynamic_remaining_cover','hospital_contract_tariff'],'confidence':None,'confidence_meaning':'UNMEASURED keyword proposals; no calibrated confidence','interpretation':None,'effective_from':None,'effective_to':None,'review_required':True,'ambiguities':['definitions/conditions/exceptions require human contextual interpretation'],'context':page.text[max(0,page.text.find(text)-250):page.text.find(text)+len(text)+500]})
   if len(proposals)>=300:return proposals
 return proposals

def extract(c,p,ctx,sid):
 p.require('config.author');row,path=r.source(c,p.tenant_id,sid,ctx,True);created=[]
 for body in scan_document(path,row['body']):
  key=r.uid('RULE');clause={k:body[k] for k in ('sha256','page','clause_id','quote','bbox')}
  r.record(c,p.tenant_id,'Clause',clause,p.user_id)
  c.execute('INSERT INTO policy_rule_candidate(tenant_id,rule_id,source_id,body,authored_by) VALUES($1,$2,$3,$4::jsonb,$5)',p.tenant_id,key,sid,Json(body),p.user_id);created.append(key)
 r.event(c,p,sid,'CANDIDATES_EXTRACTED',{'rules':created,'method':'local-keywords-v1','automatic_publication':False});return {'rule_ids':created,'count':len(created)}

if __name__=='__main__':
 import argparse,json
 from pathlib import Path
 from .acquisition import Library
 parser=argparse.ArgumentParser();parser.add_argument('--root',type=Path,required=True);parser.add_argument('discovery_id');a=parser.parse_args();lib=Library(a.root)
 try:
  d=lib.db.execute('SELECT state FROM discovery WHERE id=?',(a.discovery_id,)).fetchone()
  if not d or d['state']!='CONTENT_VERIFIED':r.fail('unique content match required for offline draft proposals')
  row=lib.db.execute('SELECT * FROM retrieval WHERE discovery_id=? ORDER BY id DESC LIMIT 1',(a.discovery_id,)).fetchone();m=json.loads(row['metadata'])
  print(json.dumps({'source':m,'source_review':'NEEDS_HUMAN_REVIEW','executable':False,'candidates':scan_document(lib.original(row['sha256']),m)},indent=2))
 finally:lib.close()
