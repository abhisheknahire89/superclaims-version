"""Public research transport only. Nothing here publishes operational configuration."""
from __future__ import annotations
import argparse,csv,io,hashlib,ipaddress,json,os,re,socket,sqlite3,time,urllib.error,urllib.request,urllib.robotparser
from datetime import datetime,timezone
from pathlib import Path
from urllib.parse import urlsplit

STATES=('DISCOVERED','URL_VERIFIED','DOCUMENT_DOWNLOADED','CONTENT_VERIFIED','METADATA_CONFLICT','NEEDS_HUMAN_REVIEW','APPROVED_SOURCE','REJECTED')
UIN=re.compile(r'\b[A-Z]{3,10}\d{5}V\d{2}\d{4}\b')
HOSTS={'STAR':('starhealth.in',),'HDFC':('hdfcergo.com',),'CARE':('careinsurance.com',),'NIVA':('nivabupa.com',)}
MAX_BYTES=30*1024*1024

def now():return datetime.now(timezone.utc).isoformat()
def insurer(value):
 s=value.lower()
 for k,aliases in {'STAR':['star health'],'HDFC':['hdfc ergo'],'CARE':['care health'],'NIVA':['niva bupa','max bupa','maxbupa']}.items():
  if any(x in s for x in aliases):return k
 return None

def check_url(url,company,referrer=None):
 u=urlsplit(url)
 if u.scheme!='https' or not u.hostname or u.username or u.password or u.port not in (None,443) or u.fragment:raise ValueError('HTTPS public URL without credentials/fragment required')
 host=u.hostname.lower();official=any(host==h or host.endswith('.'+h) for h in HOSTS.get(company,()))
 # Star CDN is accepted only with a subsequently inspected official referring page.
 if not official and not (company=='STAR' and host=='d28c6jni2fmamz.cloudfront.net' and referrer and urlsplit(referrer).hostname in ('www.starhealth.in','starhealth.in')):raise ValueError('non-official or unsubstantiated CDN source')
 return u

def public_address(host):
 addresses=socket.getaddrinfo(host,443,type=socket.SOCK_STREAM)
 if not addresses or any(not ipaddress.ip_address(a[4][0]).is_global for a in addresses):raise ValueError('non-public destination refused')

class NoRedirect(urllib.request.HTTPRedirectHandler):
 def redirect_request(self,*args,**kwargs):raise ValueError('redirect requires new explicit source review')

class Library:
 def __init__(self,root:Path):
  self.root=Path(root);self.root.mkdir(parents=True,exist_ok=True)
  for n in ('originals','partial','imports'): (self.root/n).mkdir(exist_ok=True)
  self.db=sqlite3.connect(self.root/'registry.sqlite',timeout=30);self.db.row_factory=sqlite3.Row
  self.db.executescript('''CREATE TABLE IF NOT EXISTS discovery(id TEXT PRIMARY KEY, body TEXT NOT NULL,state TEXT NOT NULL,reasons TEXT NOT NULL);
   CREATE TABLE IF NOT EXISTS retrieval(id INTEGER PRIMARY KEY,discovery_id TEXT NOT NULL,sha256 TEXT NOT NULL,metadata TEXT NOT NULL,retrieved_at TEXT NOT NULL);
   CREATE TABLE IF NOT EXISTS verification(id INTEGER PRIMARY KEY,discovery_id TEXT NOT NULL,state TEXT NOT NULL,reason TEXT NOT NULL,at TEXT NOT NULL);
   CREATE TRIGGER IF NOT EXISTS immutable_retrieval_update BEFORE UPDATE ON retrieval BEGIN SELECT RAISE(ABORT,'append-only'); END;
   CREATE TRIGGER IF NOT EXISTS immutable_retrieval_delete BEFORE DELETE ON retrieval BEGIN SELECT RAISE(ABORT,'append-only'); END;
   CREATE TRIGGER IF NOT EXISTS immutable_verification_update BEFORE UPDATE ON verification BEGIN SELECT RAISE(ABORT,'append-only'); END;
   CREATE TRIGGER IF NOT EXISTS immutable_verification_delete BEFORE DELETE ON verification BEGIN SELECT RAISE(ABORT,'append-only'); END;''')
 def close(self):self.db.close()
 def record(self,key,body,state,reasons):
  self.db.execute('INSERT OR REPLACE INTO discovery VALUES (?,?,?,?)',(key,json.dumps(body),state,json.dumps(reasons)))
  self.db.execute('INSERT INTO verification(discovery_id,state,reason,at) VALUES (?,?,?,?)',(key,state,json.dumps(reasons),now()));self.db.commit()
 def entries(self):return [{**dict(r),'body':json.loads(r['body']),'reasons':json.loads(r['reasons'])} for r in self.db.execute('SELECT * FROM discovery ORDER BY id')]
 def import_csv(self,path):
  raw=Path(path).read_bytes();digest=hashlib.sha256(raw).hexdigest();target=self.root/'imports'/f'{digest}.csv'
  if not target.exists():target.write_bytes(raw)
  rows=list(csv.reader(raw.decode('utf-8-sig').splitlines()));head=rows[0] if rows else [];batch=[]
  if len(head)!=len(set(head)):raise ValueError('duplicate CSV headers')
  for line,values in enumerate(rows[1:],2):
   data=dict(zip(head,values));co=insurer(data.get('insurer_name',data.get('insurer_legal_name','')));uin=data.get('product_uin',data.get('uin','')).strip();url=data.get('policy_wording_url',data.get('url',''));reasons=[]
   if len(values)!=len(head):reasons.append('malformed CSV column count')
   if not co:reasons.append('unsupported or unidentified insurer')
   if not UIN.fullmatch(uin):reasons.append('exact UIN missing/invalid/placeholder')
   if not data.get('product_name'):reasons.append('product identity missing')
   if data.get('document_type','POLICY_WORDING') not in ('POLICY_WORDING','CIS','RIDER','ENDORSEMENT'):reasons.append('unsupported document type')
   try:check_url(url,co,data.get('referrer_url'))
   except Exception as e:reasons.append(str(e))
   if not urlsplit(url).path.lower().endswith('.pdf'):reasons.append('webpage is not a direct PDF candidate')
   body={'insurer':co,'product_name':data.get('product_name'),'uin':uin,'url':url,'referrer_url':data.get('referrer_url'),'document_type':data.get('document_type','POLICY_WORDING'),'declared_revision':data.get('revision') or None,'wording_effective_from':data.get('wording_effective_from') or None,'wording_effective_to':data.get('wording_effective_to') or None,'research_claim':data.get('verification_status'),'import_sha256':digest,'line':line,'raw':data,'raw_cells':values}
   batch.append((digest+':'+str(line),body,reasons))
  known={}
  for r in self.entries():
   b=r['body'];known.setdefault((b['insurer'],b['uin']),set()).add(b['product_name'])
  for _,b,_ in batch:known.setdefault((b['insurer'],b['uin']),set()).add(b['product_name'])
  conflicts={k for k,v in known.items() if UIN.fullmatch(k[1]) and len(v)>1}
  for key,b,reasons in batch:
   if (b['insurer'],b['uin']) in conflicts:reasons.append('UIN reused across conflicting product identities')
   self.record(key,b,'METADATA_CONFLICT' if reasons else 'DISCOVERED',reasons)
  # A later import cannot leave a formerly discovered conflicting identity usable.
  for r in self.entries():
   if (r['body']['insurer'],r['body']['uin']) in conflicts and r['state']!='METADATA_CONFLICT':self.record(r['id'],r['body'],'METADATA_CONFLICT',['UIN reused across conflicting imports'])
  return {'input_sha256':digest,'rows':len(batch),'discovered':sum(not r for _,_,r in batch),'quarantined':sum(bool(r) for _,_,r in batch)}
 def original(self,sha):
  if not re.fullmatch('[0-9a-f]{64}',sha):raise ValueError('invalid SHA256')
  p=self.root/'originals'/f'{sha}.pdf'
  if p.is_symlink() or hashlib.sha256(p.read_bytes()).hexdigest()!=sha:raise ValueError('original integrity failure')
  return p
 def metadata(self,data):
  if not data.startswith(b'%PDF-'):raise ValueError('HTML/non-PDF rejected')
  import pdfplumber
  with pdfplumber.open(io.BytesIO(data)) as d:
   if not 0<len(d.pages)<=100:raise ValueError('oversized page count')
   pages=[p.extract_text() or '' for p in d.pages];text='\n'.join(pages)
   return {'page_count':len(d.pages),'title_metadata':d.metadata.get('Title') or None,'first_page_title_lines':pages[0].splitlines()[:12],'identified_uins':sorted(set(UIN.findall(text))),'text_available':bool(text.strip())}
 def preserve(self,key,data,transport):
  row=self.db.execute('SELECT * FROM discovery WHERE id=?',(key,)).fetchone()
  if not row:raise ValueError('discovery not found')
  body=json.loads(row['body']);metadata=self.metadata(data);sha=hashlib.sha256(data).hexdigest();p=self.root/'originals'/f'{sha}.pdf'
  if p.exists():self.original(sha)
  else:
   # Exclusive creation; a crash never silently overwrites old content.
   temp=self.root/'partial'/f'{sha}.complete';temp.write_bytes(data)
   with temp.open('rb') as f:os.fsync(f.fileno())
   try:os.link(temp,p)
   except FileExistsError:self.original(sha)
   temp.unlink()
  previous={r['sha256'] for r in self.db.execute('SELECT sha256,metadata FROM retrieval') if json.loads(r['metadata']).get('identity',{}).get('url')==body['url']};duplicate=self.db.execute('SELECT 1 FROM retrieval WHERE sha256=?',(sha,)).fetchone() is not None
  metadata.update(transport);metadata.update({'sha256':sha,'duplicate':duplicate,'changed_at_url':bool(previous and sha not in previous),'identity':body,'revision_hash':sha,'effective_dates':'UNKNOWN unless separately verified'})
  self.db.execute('INSERT INTO retrieval(discovery_id,sha256,metadata,retrieved_at) VALUES (?,?,?,?)',(key,sha,json.dumps(metadata),now()));self.db.commit()
  self.record(key,body,'DOCUMENT_DOWNLOADED',[])
  if metadata['identified_uins']!=[body['uin']]:self.record(key,body,'METADATA_CONFLICT',['actual document UIN does not uniquely match declared UIN'])
  elif metadata.get('identity_conflict_pending'):self.record(key,body,'METADATA_CONFLICT',['UIN reused across conflicting product identities; downloaded for review only'])
  elif not metadata['text_available']:self.record(key,body,'NEEDS_HUMAN_REVIEW',['local OCR/manual identity verification required'])
  else:self.record(key,body,'CONTENT_VERIFIED',['machine UIN match only; human source/product/revision verification still required'])
  return metadata
 def download(self,key,*,opener=None,respect_robots=True,quarantine_evidence=False):
  row=self.db.execute('SELECT * FROM discovery WHERE id=?',(key,)).fetchone()
  permitted_conflict=bool(row and quarantine_evidence and row['state']=='METADATA_CONFLICT' and all('UIN reused' in x for x in json.loads(row['reasons'])))
  if not row or (row['state'] in ('METADATA_CONFLICT','REJECTED') and not permitted_conflict):raise ValueError('quarantined discovery cannot download')
  b=json.loads(row['body'])
  if permitted_conflict:b['identity_conflict_pending']=True
  u=check_url(b['url'],b['insurer'],b.get('referrer_url'));open_url=opener or urllib.request.build_opener(NoRedirect()).open
  part=self.root/'partial'/f'{hashlib.sha256(key.encode()).hexdigest()}.part';info=part.with_suffix('.json')
  try:
   if part.is_symlink() or info.is_symlink():raise ValueError('symlink partial refused')
   if opener is None:public_address(u.hostname)
   if respect_robots:
    robots=urllib.robotparser.RobotFileParser();robots.set_url(f'https://{u.netloc}/robots.txt')
    try:
     time.sleep(.25)
     with open_url(urllib.request.Request(robots.url,headers={'User-Agent':'AW-PublicPolicyResearch/1.0'}),timeout=15) as r:robots.parse(r.read(1024*1024).decode(errors='replace').splitlines())
    except urllib.error.HTTPError as e:
     if e.code!=404:raise ValueError(f'robots permission unavailable (HTTP {e.code})')
     robots.parse([])
    if not robots.can_fetch('AW-PublicPolicyResearch',b['url']):raise ValueError('robots disallows access')
   if b.get('referrer_url'):
    check_url(b['referrer_url'],b['insurer'])
    time.sleep(.25)
    with open_url(b['referrer_url'],timeout=20) as r:html=r.read(5*1024*1024).decode(errors='replace')
    if b['url'] not in html:raise ValueError('official referrer does not link exact CDN URL')
   headers={'User-Agent':'AW-PublicPolicyResearch/1.0','Accept':'application/pdf','Accept-Encoding':'identity'};offset=part.stat().st_size if part.exists() else 0;old=json.loads(info.read_text()) if info.exists() else {}
   if offset and old.get('etag') and not old['etag'].startswith('W/'):
    headers.update({'Range':f'bytes={offset}-','If-Range':old['etag']})
   else:offset=0
   time.sleep(.25) # Sequential worker: bounded concurrency1, at most4 requests/sec.
   with open_url(urllib.request.Request(b['url'],headers=headers),timeout=30) as r:
    code=r.status;etag=r.headers.get('ETag');ctype=r.headers.get('Content-Type','').lower()
    if code not in (200,206) or 'text/html' in ctype:raise ValueError('HTML/non-PDF response rejected')
    range_match=re.fullmatch(r'bytes (\d+)-(\d+)/(\d+)',r.headers.get('Content-Range',''))
    resume=code==206 and offset>0 and etag==old.get('etag') and r.headers.get('Content-Range','').startswith(f'bytes {offset}-')
    if code==206 and (not range_match or int(range_match[1])!=offset or int(range_match[2])+1!=int(range_match[3]) or int(range_match[3])>MAX_BYTES):raise ValueError('incomplete or invalid range response')
    if code==206 and not resume:raise ValueError('unsafe partial response')
    if code==200:offset=0
    length=r.headers.get('Content-Length');expected=int(length) if length else None
    if code==206 and (expected is None or expected!=int(range_match[3])-offset):raise ValueError('range length mismatch')
    if expected is not None and expected+offset>MAX_BYTES:raise ValueError('download size limit')
    info.write_text(json.dumps({'etag':etag,'url':b['url']}));written=0
    self.record(key,b,'URL_VERIFIED',['HTTP response only; not source approval'])
    with part.open('ab' if resume else 'wb') as f:
     while True:
      chunk=r.read(65536)
      if not chunk:break
      written+=len(chunk)
      if offset+written>MAX_BYTES:raise ValueError('download size limit')
      f.write(chunk)
     f.flush();os.fsync(f.fileno())
    if expected is not None and written!=expected:raise ValueError('interrupted download; retained partial')
   result=self.preserve(key,part.read_bytes(),{'identity_conflict_pending':bool(permitted_conflict or b.get('identity_conflict_pending')),'url':b['url'],'referrer_url':b.get('referrer_url'),'etag':etag,'http_status':code,'content_type':ctype,'retrieved_at':now(),'resumed_bytes':offset});part.unlink();info.unlink(missing_ok=True);return result
  except Exception as e:
   self.record(key,b,'NEEDS_HUMAN_REVIEW',[f'acquisition failed: {type(e).__name__}: {str(e)[:180]}']);raise
 def report(self):
  return {'records':self.entries(),'retrievals':[{**dict(r),'metadata':json.loads(r['metadata'])} for r in self.db.execute('SELECT * FROM retrieval ORDER BY id')],'states':{s:self.db.execute('SELECT count(*) FROM discovery WHERE state=?',(s,)).fetchone()[0] for s in STATES}}

def main():
 p=argparse.ArgumentParser();p.add_argument('--root',type=Path,default=Path('.policy-research'));s=p.add_subparsers(dest='command',required=True)
 s.add_parser('import').add_argument('csv',type=Path);s.add_parser('report');download=s.add_parser('download');download.add_argument('id');download.add_argument('--quarantine-evidence',action='store_true');a=p.parse_args();lib=Library(a.root)
 try:result=lib.import_csv(a.csv) if a.command=='import' else lib.download(a.id,quarantine_evidence=a.quarantine_evidence) if a.command=='download' else lib.report();print(json.dumps(result,indent=2))
 finally:lib.close()
if __name__=='__main__':main()
