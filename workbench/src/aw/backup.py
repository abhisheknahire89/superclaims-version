"""Local-only backup and restore into a NEW database. Never overwrite an existing target."""
import argparse,hashlib,json,os,shutil,subprocess,time
from pathlib import Path
from contextlib import closing
from urllib.parse import urlsplit,urlunsplit
from .db import Database
from .settings import load
from . import audit

def hash_file(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def pg_bin():return Path(subprocess.check_output([str(Path(__file__).resolve().parents[2]/'scripts/find_pg.sh')],text=True).strip())
def local_dsn(dsn):
 u=urlsplit(dsn)
 if u.hostname not in ('localhost','127.0.0.1','::1'):raise ValueError('backup/restore is restricted to loopback PostgreSQL')
 return u

def backup(dsn,objects,destination):
 local_dsn(dsn);destination=Path(destination);destination.mkdir(mode=0o700,parents=True,exist_ok=False)
 dump=destination/'database.dump'
 subprocess.run([str(pg_bin()/'pg_dump'),'--format=custom','--file',str(dump),dsn],check=True,capture_output=True)
 os.chmod(dump,0o600)
 target=destination/'objects';target.mkdir()
 for p in Path(objects).rglob('*'):
  if p.is_symlink():raise ValueError('object store symlinks are not permitted')
  if p.is_file() and not p.name.startswith('.aw-write-'):
   dest=target/p.relative_to(objects);dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,dest)
 files={str(p.relative_to(destination)):hash_file(p) for p in destination.rglob('*') if p.is_file()}
 (destination/'manifest.json').write_text(json.dumps({'version':1,'files':files,'synthetic_only':True},indent=2));os.chmod(destination/'manifest.json',0o600)
 return {'backup_dir':str(destination.resolve()),'objects':len(files)-1,'dump_sha256':files['database.dump']}

def restore(dsn,source,new_database,new_objects):
 u=local_dsn(dsn);source=Path(source);new_objects=Path(new_objects)
 import re
 if not re.fullmatch(r'aw_restore_[a-z0-9_]+',new_database):raise ValueError('restore name must be aw_restore_ followed by lowercase letters/digits')
 if new_objects.exists():raise ValueError('restore object target already exists')
 manifest=json.loads((source/'manifest.json').read_text())
 if manifest.get('version')!=1 or 'database.dump' not in manifest.get('files',{}):raise ValueError('invalid backup manifest')
 actual=set()
 for entry in source.rglob('*'):
  if entry.is_symlink():raise ValueError('backup symlinks are not permitted')
  if entry.is_file() and entry.relative_to(source)!=Path('manifest.json'):actual.add(str(entry.relative_to(source)))
 if actual!=set(manifest['files']):raise ValueError('backup file set differs from manifest')
 for key,digest in manifest['files'].items():
  p=source/key
  if not p.resolve().is_relative_to(source.resolve()) or hash_file(p)!=digest:raise ValueError('backup manifest verification failed')
 with closing(Database(dsn,pool_size=1)) as owner:
  with owner.connection() as c:
   if c.fetch_val('SELECT 1 FROM pg_database WHERE datname=$1',new_database):raise ValueError('restore database already exists')
   c.execute('CREATE DATABASE '+new_database)
 restored=urlunsplit(u._replace(path='/'+new_database))
 subprocess.run([str(pg_bin()/'pg_restore'),'--exit-on-error','--dbname',restored,str(source/'database.dump')],check=True,capture_output=True)
 shutil.copytree(source/'objects',new_objects)
 proof=[]
 with closing(Database(restored,pool_size=1)) as owner:
  with owner.connection() as c:
   rows=c.fetch_all('SELECT tenant_id,claim_id FROM claim ORDER BY tenant_id,claim_id')
   for row in rows:
    result=audit.verify_chain(c,row['tenant_id'],row['claim_id'])
    if not result['verified']:raise ValueError('restored audit chain invalid')
    proof.append({'claim_id':row['claim_id'],'events':result['events'],'verified':True})
   from .storage import LocalWormStore
   from . import anchors
   store=LocalWormStore(new_objects);verified_objects=0
   for doc in c.fetch_all('SELECT object_key,sha256 FROM document'):
    if hashlib.sha256(store.get(doc['object_key'])).hexdigest()!=doc['sha256']:raise ValueError('restored original hash differs from database')
    verified_objects+=1
   for page in c.fetch_all('SELECT image_key,text_key FROM document_page'):
    for key in (page['image_key'],page['text_key']):
     if key:store.get(key);verified_objects+=1
   for row in rows:
    if not anchors.verify(c,store,row['tenant_id'],row['claim_id'])['verified']:raise ValueError('restored anchor invalid')
   for export in c.fetch_all("SELECT tenant_id,target_reference FROM export_record WHERE state='ACKNOWLEDGED'"):
    if export['target_reference'] and export['target_reference'].startswith(export['tenant_id']+'/'):store.get(export['target_reference']);verified_objects+=1
   claims=len(rows);documents=c.fetch_val('SELECT count(*) FROM document');decisions=c.fetch_val('SELECT count(*) FROM decision')
 return {'database':new_database,'object_dir':str(new_objects.resolve()),'claims':claims,'documents':documents,'decisions':decisions,'audit_chains':proof,'manifest_verified':True,'verified_referenced_objects':verified_objects}

def main():
 parser=argparse.ArgumentParser();parser.add_argument('mode',choices=['backup','restore']);parser.add_argument('source',nargs='?');parser.add_argument('--database',default='aw_restore_'+str(int(time.time())));parser.add_argument('--objects');args=parser.parse_args()
 dsn=os.environ['AW_OWNER_DSN'];settings=load()
 if args.mode=='backup':out=backup(dsn,settings.object_store_dir,Path('.backups')/str(int(time.time())))
 else:out=restore(dsn,args.source,args.database,args.objects or str(Path(args.source)/'restored-objects'))
 print(json.dumps(out,indent=2))
if __name__=='__main__':main()
