"""Local reviewer operations, letter release and tenant administration. No external delivery."""
import csv,io,json,textwrap
from datetime import datetime,timezone,date
from starlette.responses import Response
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from .. import auth,audit,configs,jobs,ingest
from ..db import Json
from ..ids import new_id
from ..money import fmt,to_paise
from ..local_auth import create_credentials,password_hash,matches
from .core import Problem,json_default
from .claims import claim_view


def csv_bytes(headers,rows):
    out=io.StringIO();w=csv.writer(out);w.writerow(headers)
    for row in rows:w.writerow([("'"+str(v)) if str(v).lstrip().startswith(('=','+','-','@')) else ('' if v is None else v) for v in row])
    return out.getvalue().encode('utf-8-sig')


def letter(conn,tenant,qid):
    q=conn.fetch_one('SELECT * FROM query_letter WHERE tenant_id=$1 AND query_id=$2',tenant,qid)
    if not q:raise Problem(404,'query-not-found','query not found')
    q['items']=conn.fetch_all('SELECT query_item_id,text,status,requested_document_type,answered_by_document_id FROM query_item WHERE tenant_id=$1 AND query_id=$2 ORDER BY query_item_id',tenant,qid)
    return q


def letter_pdf(q):
    buf=io.BytesIO();c=canvas.Canvas(buf,pagesize=A4,invariant=1);y=800
    for text in ['SYNTHETIC QUERY LETTER',f"Reference: {q['query_id']} / {q['claim_id']}",f"To: {q['addressed_to']}",f"Response due: {q['due_at']}",'Please provide the following evidence for human review:']+[f"{i+1}. {it['text']}" for i,it in enumerate(q['items'])]+['This request is not a claim disposition. Upload replies in the workbench.']:
        for part in textwrap.wrap(text,95):
            if y<60:c.showPage();y=800
            c.setFont('Helvetica',10);c.drawString(40,y,part);y-=15
        y-=8
    c.save();return buf.getvalue()


def register(api):
    @api.op('listAssignableUsers','/v1/reviewers','GET')
    def reviewers(c,p,req,b):
        p.require('claim.view')
        return 200,{'items':c.fetch_all("SELECT u.user_id,u.display_name,array_agg(r.role) AS roles FROM app_user u JOIN role_assignment r ON r.tenant_id=u.tenant_id AND r.user_id=u.user_id WHERE u.tenant_id=$1 AND u.is_active AND r.valid_from<=now() AND (r.valid_to IS NULL OR r.valid_to>now()) AND r.role IN ('PROCESSOR','MEDICAL_OFFICER','SUPERVISOR') GROUP BY u.user_id,u.display_name ORDER BY u.user_id",p.tenant_id)},None

    @api.op('getOperations','/v1/operations','GET')
    def metrics(c,p,req,b):
        if not p.roles & {'SUPERVISOR','TENANT_ADMIN'}:raise auth.Forbidden('operations require supervisor or tenant admin')
        rows=c.fetch_all('SELECT status,count(*) AS claims FROM claim WHERE tenant_id=$1 GROUP BY status',p.tenant_id)
        total=sum(r['claims'] for r in rows)
        dec=c.fetch_one("SELECT count(*) AS n,count(*) FILTER (WHERE d.approved_payable_paise=e.recommended_payable_paise) AS agrees FROM decision d JOIN evaluation e ON e.tenant_id=d.tenant_id AND e.evaluation_id=d.evaluation_id WHERE d.tenant_id=$1",p.tenant_id)
        return 200,{'as_of':datetime.now(timezone.utc),'claims':total,'by_status':rows,'pending_approvals':c.fetch_val("SELECT count(*) FROM approval_request WHERE tenant_id=$1 AND state='PENDING'",p.tenant_id),'overdue_queries':c.fetch_val("SELECT count(*) FROM query_letter WHERE tenant_id=$1 AND status IN ('SENT','PARTIALLY_ANSWERED') AND due_at<now()",p.tenant_id),'deadline_alerts':c.fetch_val('SELECT count(*) FROM deadline_alert WHERE tenant_id=$1',p.tenant_id),'failed_jobs':c.fetch_val("SELECT count(*) FROM processing_job WHERE tenant_id=$1 AND state='FAILED_FINAL'",p.tenant_id),'decisions':dec['n'],'agreeing_decisions':dec['agrees'],'corrections_by_field':c.fetch_all("SELECT target_ref->>'id' AS field,count(*) AS actions FROM reviewer_action WHERE tenant_id=$1 AND action IN ('CORRECT_FACT','RESOLVE_CONFLICT') GROUP BY 1",p.tenant_id),'overrides_by_rule':c.fetch_all("SELECT x.rule_id,count(*) AS actions FROM reviewer_action r JOIN adjustment a ON a.tenant_id=r.tenant_id AND a.adjustment_id=r.target_ref->>'id' JOIN rule_execution x ON x.tenant_id=a.tenant_id AND x.rule_execution_id=a.rule_execution_id WHERE r.tenant_id=$1 AND r.action='OVERRIDE_ADJUSTMENT' GROUP BY x.rule_id",p.tenant_id),'application_service_cost':'0.00'},None

    @api.op('exportClaim','/v1/claims/{claim_id}/export','GET')
    def export(c,p,req,b):
        p.require('claim.view');cid=req.path_params['claim_id'];data=claim_view(c,p,cid)
        # Export names are masked even for a full workspace viewer.
        data['patient']={'display':data['patient_display']};data.pop('member_id',None)
        mode=req.query_params.get('format','json')
        if mode=='csv':return 200,Response(csv_bytes(['claim','workflow','status','recommended_payable','assignee','due'],[[cid,data['workflow'],data['status'],data['recommended_payable'],data['assigned_to'],data['sla_due_at']]]),media_type='text/csv',headers={'Content-Disposition':'attachment; filename="claim.csv"'}),None
        return 200,data,None

    @api.op('exportAudit','/v1/claims/{claim_id}/audit-export','GET')
    def audit_export(c,p,req,b):
        p.require('audit.export');cid=req.path_params['claim_id'];claim_view(c,p,cid)
        return 200,{'verification':audit.verify_chain(c,p.tenant_id,cid),'events':c.fetch_all('SELECT seq,occurred_at,actor_kind,actor_id,event_type,prev_hash,event_hash FROM audit_event WHERE tenant_id=$1 AND claim_id=$2 ORDER BY seq',p.tenant_id,cid)},None

    @api.op('listQueryLetters','/v1/claims/{claim_id}/queries','GET')
    def query_list(c,p,req,b):
        p.require('claim.view');cid=req.path_params['claim_id'];claim_view(c,p,cid)
        return 200,{'items':[letter(c,p.tenant_id,r['query_id']) for r in c.fetch_all('SELECT query_id FROM query_letter WHERE tenant_id=$1 AND claim_id=$2 ORDER BY due_at',p.tenant_id,cid)]},None

    @api.op('exportQueryLetter','/v1/queries/{query_id}/letter','GET')
    def query_export(c,p,req,b):
        p.require('claim.view');q=letter(c,p.tenant_id,req.path_params['query_id'])
        if not q['approved_by'] or q['status'] in ('DRAFT','CANCELLED'):raise Problem(409,'query-not-approved','a person must approve the letter before export')
        if req.query_params.get('format')=='pdf':return 200,Response(letter_pdf(q),media_type='application/pdf',headers={'Content-Disposition':'attachment; filename="query.pdf"'}),None
        return 200,q,None

    @api.op('answerQuery','/v1/queries/{query_id}:answer','POST')
    def answer(c,p,req,b):
        p.require('document.upload');q=letter(c,p.tenant_id,req.path_params['query_id'])
        # Lock claim before query, matching approval/audit lock order.
        claim=c.fetch_one('SELECT status FROM claim WHERE tenant_id=$1 AND claim_id=$2 FOR UPDATE',p.tenant_id,q['claim_id'])
        c.fetch_one('SELECT query_id FROM query_letter WHERE tenant_id=$1 AND query_id=$2 FOR UPDATE',p.tenant_id,q['query_id'])
        q=letter(c,p.tenant_id,q['query_id'])
        if q['status'] not in ('SENT','PARTIALLY_ANSWERED'):raise Problem(409,'query-not-awaiting','query is not awaiting evidence')
        if claim['status'] in ('FINALISED','EXPORTED','WITHDRAWN'):raise Problem(409,'claim-closed','claim must be reopened first')
        doc=c.fetch_one("SELECT document_id FROM document WHERE tenant_id=$1 AND claim_id=$2 AND document_id=$3 AND status NOT IN ('QUARANTINED','SUPERSEDED')",p.tenant_id,q['claim_id'],b['document_id'])
        if not doc:raise Problem(422,'reply-evidence-required','reply must link an active document in this claim')
        if not any(i['query_item_id']==b['query_item_id'] and i['status']=='OPEN' for i in q['items']):raise Problem(422,'query-item-not-open','open query item required')
        c.execute("UPDATE query_item SET status='ANSWERED',answered_by_document_id=$3 WHERE tenant_id=$1 AND query_item_id=$2",p.tenant_id,b['query_item_id'],b['document_id'])
        remaining=c.fetch_val("SELECT count(*) FROM query_item WHERE tenant_id=$1 AND query_id=$2 AND status='OPEN'",p.tenant_id,q['query_id'])
        c.execute('UPDATE query_letter SET status=$3::query_status WHERE tenant_id=$1 AND query_id=$2',p.tenant_id,q['query_id'],'PARTIALLY_ANSWERED' if remaining else 'ANSWERED')
        ingest.mark_stale(c,p.tenant_id,q['claim_id'],p.actor,'QUERY_REPLY')
        c.execute("UPDATE claim SET status='PROCESSING' WHERE tenant_id=$1 AND claim_id=$2",p.tenant_id,q['claim_id'])
        jobs.enqueue(c,p.tenant_id,'RECONCILE',q['claim_id'],f"reply:{q['query_id']}:{b['query_item_id']}",{'force_evaluation':True})
        audit.append(c,p.tenant_id,q['claim_id'],p.actor,'QUERY_ANSWERED',{'query_id':q['query_id'],'query_item_id':b['query_item_id'],'document_id':b['document_id']})
        return 200,{'status':'PARTIALLY_ANSWERED' if remaining else 'ANSWERED'},None

    @api.op('remindQuery','/v1/queries/{query_id}:remind','POST')
    def remind(c,p,req,b):
        p.require('query.approve');q=letter(c,p.tenant_id,req.path_params['query_id'])
        if q['status'] not in ('SENT','PARTIALLY_ANSWERED') or not q['due_at'] or q['due_at']>datetime.now(timezone.utc):raise Problem(409,'not-overdue','only unanswered overdue queries can be reminded')
        c.execute('UPDATE query_letter SET reminder_count=reminder_count+1 WHERE tenant_id=$1 AND query_id=$2',p.tenant_id,q['query_id'])
        audit.append(c,p.tenant_id,q['claim_id'],p.actor,'QUERY_SENT',{'query_id':q['query_id'],'channel':'LOCAL_REMINDER','reminder':True})
        return 200,{'status':q['status'],'reminder_count':q['reminder_count']+1,'delivery':'LOCAL_ONLY'},None

    @api.op('listLocalUsers','/v1/admin/users','GET')
    def users(c,p,req,b):
        p.require('admin.users')
        return 200,{'items':c.fetch_all("SELECT u.user_id,u.display_name,u.is_active,coalesce(array_agg(r.role) FILTER(WHERE r.role IS NOT NULL),'{}') AS roles,max(r.approval_limit_paise) AS approval_limit_paise FROM app_user u LEFT JOIN role_assignment r ON r.tenant_id=u.tenant_id AND r.user_id=u.user_id AND r.valid_from<=now() AND (r.valid_to IS NULL OR r.valid_to>now()) WHERE u.tenant_id=$1 GROUP BY u.user_id,u.display_name,u.is_active ORDER BY u.user_id",p.tenant_id),'events':c.fetch_all('SELECT actor_user_id,subject_user_id,action,occurred_at FROM admin_event WHERE tenant_id=$1 ORDER BY occurred_at DESC LIMIT 50',p.tenant_id)},None

    @api.op('saveLocalUser','/v1/admin/users','POST')
    def save_user(c,p,req,b):
        p.require('admin.users');credential=c.fetch_val('SELECT password_hash FROM local_credential WHERE tenant_id=$1 AND user_id=$2',p.tenant_id,p.user_id)
        if not credential or not matches(b['current_password'],credential):raise Problem(401,'reauthentication-required','confirm administrator password')
        c.execute('SELECT pg_advisory_xact_lock(hashtext($1))','admin:'+p.tenant_id)
        uid=b['user_id'];existing=c.fetch_one('SELECT user_id FROM app_user WHERE tenant_id=$1 AND user_id=$2',p.tenant_id,uid)
        if uid==p.user_id and (not b['is_active'] or 'TENANT_ADMIN' not in b['roles']):raise Problem(422,'self-lockout','keep your own administrator access')
        other_sup=c.fetch_val("SELECT count(*) FROM app_user u JOIN role_assignment r ON r.tenant_id=u.tenant_id AND r.user_id=u.user_id WHERE u.tenant_id=$1 AND u.user_id<>$2 AND u.is_active AND r.role='SUPERVISOR' AND r.valid_from<=now() AND (r.valid_to IS NULL OR r.valid_to>now())",p.tenant_id,uid)
        if not other_sup and (not b['is_active'] or 'SUPERVISOR' not in b['roles']):raise Problem(422,'last-supervisor','at least one active supervisor required')
        if not existing and not b.get('password'):raise Problem(422,'password-required','new local user requires a password')
        if existing:c.execute('UPDATE app_user SET display_name=$3,is_active=$4 WHERE tenant_id=$1 AND user_id=$2',p.tenant_id,uid,b['display_name'],b['is_active'])
        else:c.execute('INSERT INTO app_user (tenant_id,user_id,idp_subject,display_name,is_active) VALUES ($1,$2,$3,$4,$5)',p.tenant_id,uid,'local:'+uid,b['display_name'],b['is_active'])
        c.execute('UPDATE role_assignment SET valid_to=now() WHERE tenant_id=$1 AND user_id=$2 AND valid_to IS NULL',p.tenant_id,uid)
        limit=to_paise(b['approval_limit']) if b.get('approval_limit') is not None else None
        for role in b['roles']:c.execute('INSERT INTO role_assignment (tenant_id,user_id,role,approval_limit_paise) VALUES ($1,$2,$3,$4)',p.tenant_id,uid,role,limit if role in ('PROCESSOR','MEDICAL_OFFICER','SUPERVISOR') else None)
        if b.get('password'):
            hashed=password_hash(b['password']);c.execute('INSERT INTO local_credential (tenant_id,user_id,password_hash) VALUES ($1,$2,$3) ON CONFLICT (tenant_id,user_id) DO UPDATE SET password_hash=excluded.password_hash,failed_attempts=0,locked_until=NULL',p.tenant_id,uid,hashed)
        c.execute('UPDATE local_session SET revoked=true WHERE tenant_id=$1 AND user_id=$2',p.tenant_id,uid)
        c.execute('INSERT INTO admin_event (tenant_id,event_id,actor_user_id,subject_user_id,action,details) VALUES ($1,$2,$3,$4,$5,$6::jsonb)',p.tenant_id,new_id('ADM'),p.user_id,uid,'USER_UPDATED' if existing else 'USER_CREATED',Json({'roles':b['roles'],'is_active':b['is_active'],'password_reset':bool(b.get('password'))}))
        return 200,{'user_id':uid,'roles':b['roles'],'is_active':b['is_active']},None
