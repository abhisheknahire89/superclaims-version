import json,tempfile,threading,time,hashlib
from pathlib import Path
from tests.test_workflow import Seeded
from support import AsgiClient,DbTestCase
from tests.test_foundation import seed_min
from aw import local_auth,jobs,anchors,synthetic,maintenance
from aw.api.app import create_app
from aw.storage import LocalWormStore,ImmutableObjectError

class PasswordSessions(Seeded):
 def test_salt_lockout_cookie_csrf_and_revocation(self):
  self.assertNotEqual(local_auth.password_hash(local_auth.DEMO_PASSWORD),local_auth.password_hash(local_auth.DEMO_PASSWORD))
  client=AsgiClient(create_app(self.ctx));body={'tenant_id':'TENANT-DEMO','user_id':'PROC-11','password':'bad'}
  for _ in range(5):self.assertEqual(client.post('/v1/auth/login',json_body=body).status,401)
  body['password']=local_auth.DEMO_PASSWORD;self.assertEqual(client.post('/v1/auth/login',json_body=body).status,401)
  body['user_id']='PROC-07';response=client.post('/v1/auth/login',json_body=body);self.assertEqual(response.status,200,response)
  cookie=response.headers['set-cookie'];self.assertIn('HttpOnly',cookie);self.assertIn('SameSite=strict',cookie);headers={'Cookie':cookie.split(';')[0]}
  self.assertEqual(client.get('/v1/me',headers=headers).status,200)
  self.assertEqual(client.post('/v1/auth/logout',headers=headers).status,401)
  headers['X-CSRF-Token']=response.json()['csrf_token'];self.assertEqual(client.post('/v1/auth/logout',headers=headers).status,200);self.assertEqual(client.get('/v1/me',headers=headers).status,401)
  with self.db.tenant_tx('OTHER') as c:self.assertEqual(c.fetch_val('SELECT count(*) FROM local_credential'),0);self.assertEqual(c.fetch_val('SELECT count(*) FROM local_session'),0)
 def test_anchor_job_and_deadline_alert(self):
  self.new_claim('CLM-ANCHOR','trace-1-straightforward',synthetic.claim_documents()['CLM-DEMO-0001'])
  with self.db.tenant_tx('TENANT-DEMO') as c:jobs.enqueue(c,'TENANT-DEMO','AUDIT_ANCHOR','CLM-ANCHOR','anchor-test',{})
  self.worker.drain()
  with self.db.tenant_tx('TENANT-DEMO') as c:
   self.assertEqual(anchors.verify(c,self.ctx.store,'TENANT-DEMO','CLM-ANCHOR'),{'verified':True,'anchors':1});c.execute("UPDATE claim SET submitted_at=now()-interval '20 days' WHERE claim_id='CLM-ANCHOR'");maintenance.scan(c,'TENANT-DEMO');self.assertEqual(c.fetch_val("SELECT count(*) FROM deadline_alert WHERE claim_id='CLM-ANCHOR'"),1)

class WorkerFencing(DbTestCase):
 def test_handler_holds_lease_row_and_cannot_run_concurrently(self):
  seed_min(self.owner,'T-LEASE')
  with self.db.tenant_tx('T-LEASE') as c:jid=jobs.enqueue(c,'T-LEASE','EXTRACT','D1','lease',{})
  started=threading.Event();release=threading.Event();seen=[]
  def handler(conn,job):started.set();release.wait(3);seen.append(job['attempts'])
  a=jobs.Worker(self.worker_db,self.db,{'EXTRACT':handler},lease_seconds=0);b=jobs.Worker(self.worker_db,self.db,{'EXTRACT':handler},lease_seconds=0)
  thread=threading.Thread(target=a.run_once);thread.start();self.assertTrue(started.wait(3));self.assertIsNone(b._claim());release.set();thread.join(3);self.assertFalse(thread.is_alive());self.assertEqual(seen,[1])
 def test_expired_owned_attempt_cannot_finish_reclaimed_job(self):
  seed_min(self.owner,'T-FENCE')
  with self.db.tenant_tx('T-FENCE') as c:jid=jobs.enqueue(c,'T-FENCE','EXTRACT','D1','fence',{})
  a=jobs.Worker(self.worker_db,self.db,{});b=jobs.Worker(self.worker_db,self.db,{});old=a._claim()
  with self.db.tenant_tx('T-FENCE') as c:c.execute("UPDATE processing_job SET locked_until=now()-interval '1 second' WHERE job_id=$1",jid)
  new=b._claim();self.assertEqual(new['attempts'],2);a._finish(old,True)
  with self.db.tenant_tx('T-FENCE') as c:self.assertEqual(c.fetch_val('SELECT locked_by FROM processing_job WHERE job_id=$1',jid),b.name)
 def test_atomic_store_race_never_overwrites(self):
  store=LocalWormStore(Path(tempfile.mkdtemp()));barrier=threading.Barrier(2);results=[]
  def write(data):
   barrier.wait()
   try:store.put_once('object',data);results.append('ok')
   except ImmutableObjectError:results.append('rejected')
  threads=[threading.Thread(target=write,args=(v,)) for v in (b'one',b'two')]
  for t in threads:t.start()
  for t in threads:t.join()
  self.assertEqual(sorted(results),['ok','rejected']);self.assertIn(store.get('object'),(b'one',b'two'))
