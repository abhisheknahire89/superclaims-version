"""Local public/illustrative research backup and restore with byte integrity checks."""
import argparse,hashlib,json,shutil,sqlite3
from pathlib import Path

def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def verify(folder):
 folder=Path(folder);m=json.loads((folder/'manifest.json').read_text());listed=set(m['files']);actual={str(p.relative_to(folder)) for p in folder.rglob('*') if p.is_file() and p.name!='manifest.json'}
 if listed!=actual:raise ValueError('archive file set differs from manifest')
 for name,sha in m['files'].items():
  p=folder/name
  if p.is_symlink() or not p.resolve().is_relative_to(folder.resolve()) or digest(p)!=sha:raise ValueError('archive byte integrity failure')
 return m

def backup(root,destination):
 root=Path(root);dst=Path(destination);dst.mkdir(parents=True,exist_ok=False)
 with sqlite3.connect(root/'registry.sqlite') as db, sqlite3.connect(dst/'registry.sqlite') as target:db.backup(target)
 for name in ('originals','imports'):
  for p in (root/name).glob('*'):
   if not p.is_file() or p.is_symlink():raise ValueError('research backup refuses nonregular source')
   q=dst/name/p.name;q.parent.mkdir(exist_ok=True);shutil.copyfile(p,q)
 files={str(p.relative_to(dst)):digest(p) for p in dst.rglob('*') if p.is_file()};m={'version':1,'scope':'isolated research originals/imports/journal; incomplete downloads restart','files':files}
 (dst/'manifest.json').write_text(json.dumps(m,indent=2));verify(dst);return {'files':len(files),'archive':str(dst.resolve())}

def restore(source,destination):
 m=verify(source);dst=Path(destination)
 if dst.exists():raise ValueError('restore target must be new')
 dst.mkdir(parents=True)
 for name in m['files']:
  q=dst/name;q.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(Path(source)/name,q)
 from .acquisition import Library
 lib=Library(dst)
 try:
  rows=lib.db.execute('SELECT DISTINCT sha256 FROM retrieval').fetchall()
  for row in rows:lib.original(row[0])
  return {'restored_originals':len(rows),'restored_records':len(lib.entries()),'target':str(dst.resolve())}
 finally:lib.close()
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('mode',choices=['backup','restore','verify']);p.add_argument('source',type=Path);p.add_argument('destination',type=Path,nargs='?');a=p.parse_args()
 if a.mode!='verify' and not a.destination:p.error('destination required')
 print(json.dumps(backup(a.source,a.destination) if a.mode=='backup' else restore(a.source,a.destination) if a.mode=='restore' else verify(a.source),indent=2))
