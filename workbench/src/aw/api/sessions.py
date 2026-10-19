from starlette.requests import Request
from starlette.concurrency import run_in_threadpool
from .. import local_auth,auth
from .core import jresp,problem_response,Problem

def register(api):
 ctx=api.ctx
 @api.raw('/v1/auth/login','POST','localLogin')
 async def login(request:Request):
  if ctx.settings.auth_mode!='local':return problem_response(Problem(503,'oidc-not-configured','OIDC interface requires a configured provider'),request.url.path)
  if request.headers.get("origin") and request.headers["origin"]!=str(request.base_url).rstrip("/"):return problem_response(Problem(403,"invalid-origin","same-origin login required"),request.url.path)
  import json
  raw=bytearray()
  async for chunk in request.stream():
   if len(raw)+len(chunk)>4096:return problem_response(Problem(413,'request-too-large','login limit4KB'),request.url.path)
   raw.extend(chunk)
  try:
   body=json.loads(raw);tenant=body['tenant_id'];user=body['user_id'];password=body['password']
   if not all(isinstance(v,str) and len(v)<=128 for v in (tenant,user,password)):raise ValueError()
  except Exception:return problem_response(Problem(422,'invalid-login','tenant, user and password are required'),request.url.path)
  def run():
   with ctx.db.tenant_tx(tenant) as c:return local_auth.login(c,tenant,user,password)
  try:out=await run_in_threadpool(run)
  except auth.AuthError:out=None
  if not out:return problem_response(Problem(401,'invalid-login','invalid credentials or account locked'),request.url.path)
  response=jresp({'csrf_token':out['csrf'],'user_id':out['user_id']});response.set_cookie('aw_session',out['token'],httponly=True,secure=request.url.scheme=='https' or ctx.settings.environment=='prod',samesite='strict',max_age=28800,path='/');response.headers['Cache-Control']='no-store';return response
 @api.raw('/v1/auth/logout','POST','localLogout')
 async def logout(request:Request):
  try:p=await run_in_threadpool(auth.authenticate,ctx,request)
  except auth.AuthError:return problem_response(Problem(401,'unauthenticated','session required'),request.url.path)
  token=request.cookies.get('aw_session')
  if token:
   def revoke():
    with ctx.db.tenant_tx(p.tenant_id) as c:c.execute('UPDATE local_session SET revoked=true WHERE tenant_id=$1 AND session_hash=$2',p.tenant_id,local_auth.digest(token))
   await run_in_threadpool(revoke)
  response=jresp({'signed_out':True});response.delete_cookie('aw_session',path='/');return response
