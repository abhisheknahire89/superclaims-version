"""Local salted scrypt passwords and revocable opaque sessions. No hosted IdP calls."""
import hashlib,hmac,secrets,json,base64
from datetime import datetime,timedelta,timezone
from .auth import AuthError,load_principal
DEMO_PASSWORD='Synthetic-demo-2026!'

def password_hash(password):
 if len(password)<12 or len(password)>128:raise ValueError('password length must be12–128')
 salt=secrets.token_bytes(16);digest=hashlib.scrypt(password.encode(),salt=salt,n=16384,r=8,p=1)
 return 'scrypt16384$'+salt.hex()+'$'+digest.hex()

DUMMY_HASH=password_hash("Synthetic-unknown-account!")

def matches(password,stored):
 try:
  _,salt,wanted=stored.split('$');actual=hashlib.scrypt(password.encode(),salt=bytes.fromhex(salt),n=16384,r=8,p=1).hex();return hmac.compare_digest(actual,wanted)
 except (ValueError,TypeError):return False

def digest(value):return hashlib.sha256(value.encode()).hexdigest()

def create_credentials(conn,tenant,user,password):
 conn.execute('INSERT INTO local_credential (tenant_id,user_id,password_hash) VALUES ($1,$2,$3) ON CONFLICT DO NOTHING',tenant,user,password_hash(password))

def login(conn,tenant,user,password):
 row=conn.fetch_one('SELECT * FROM local_credential WHERE tenant_id=$1 AND user_id=$2 FOR UPDATE',tenant,user);now=datetime.now(timezone.utc)
 if row and row['locked_until'] and row['locked_until']>now:return None
 if not row:
  matches(password,DUMMY_HASH);return None
 if not matches(password,row['password_hash']):
  if row:
   conn.execute("UPDATE local_credential SET failed_attempts=failed_attempts+1,locked_until=CASE WHEN failed_attempts+1>=5 THEN now()+interval '15 minutes' ELSE locked_until END WHERE tenant_id=$1 AND user_id=$2",tenant,user)
  return None
 principal=load_principal(conn,tenant,user)
 conn.execute('UPDATE local_credential SET failed_attempts=0,locked_until=NULL WHERE tenant_id=$1 AND user_id=$2',tenant,user)
 token=base64.urlsafe_b64encode(tenant.encode()).decode().rstrip('=')+'.'+secrets.token_urlsafe(32);csrf=secrets.token_urlsafe(32)
 conn.execute("INSERT INTO local_session (tenant_id,session_hash,user_id,csrf_hash,expires_at) VALUES ($1,$2,$3,$4,$5)",tenant,digest(token),user,digest(csrf),now+timedelta(hours=8))
 return {'token':token,'csrf':csrf,'user_id':user}

def tenant_of(token):
 try:return base64.urlsafe_b64decode(token.split('.')[0]+'='*(-len(token.split('.')[0])%4)).decode()
 except Exception:raise AuthError('invalid session')

def session_principal(ctx,request):
 token=request.cookies.get('aw_session')
 if not token:raise AuthError('session required')
 tenant=tenant_of(token)
 with ctx.db.tenant_tx(tenant) as c:
  row=c.fetch_one('SELECT * FROM local_session WHERE tenant_id=$1 AND session_hash=$2 AND NOT revoked AND expires_at>now()',tenant,digest(token))
  if not row:raise AuthError('session expired or revoked')
  if request.method not in ('GET','HEAD','OPTIONS') and not hmac.compare_digest(row['csrf_hash'],digest(request.headers.get('X-CSRF-Token',''))):raise AuthError('CSRF token required')
  return load_principal(c,tenant,row['user_id'])

class OidcInterface:
 """Future boundary; deliberately no remote adapter or issuer trust configured."""
 def authenticate(self,request):raise AuthError('OIDC provider is not configured')
