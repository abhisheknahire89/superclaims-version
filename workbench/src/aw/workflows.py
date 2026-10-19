"""Separate workflow guards. Every monetary disposition remains a human action."""
from .errors import AppError

REVIEW_STATES={'READY_FOR_REVIEW','IN_REVIEW','MEDICAL_REVIEW','QUERY_RAISED','AWAITING_RESPONSE','PENDING_APPROVAL','ESCALATED_CRC'}
TRANSITIONS={
 'INTAKE':{'DOCS_INCOMPLETE','PROCESSING','WITHDRAWN'},'DOCS_INCOMPLETE':{'PROCESSING','WITHDRAWN'},
 'PROCESSING':{'READY_FOR_REVIEW','DOCS_INCOMPLETE'},'READY_FOR_REVIEW':{'IN_REVIEW','PROCESSING','PENDING_APPROVAL','FINALISED','WITHDRAWN','QUERY_RAISED','MEDICAL_REVIEW','ESCALATED_CRC'},
 'IN_REVIEW':{'PROCESSING','MEDICAL_REVIEW','QUERY_RAISED','PENDING_APPROVAL','ESCALATED_CRC','FINALISED','WITHDRAWN'},
 'MEDICAL_REVIEW':{'IN_REVIEW','PROCESSING','QUERY_RAISED','PENDING_APPROVAL','FINALISED','ESCALATED_CRC'},
 'QUERY_RAISED':{'AWAITING_RESPONSE','PROCESSING','IN_REVIEW'},'AWAITING_RESPONSE':{'PROCESSING','QUERY_RAISED'},
 'PENDING_APPROVAL':{'IN_REVIEW','FINALISED','PROCESSING'},'ESCALATED_CRC':{'IN_REVIEW','FINALISED'},
 'FINALISED':{'EXPORTED','REOPENED'},'EXPORTED':{'REOPENED'},'REOPENED':{'PROCESSING'},'WITHDRAWN':set()}

def assert_transition(workflow,before,after):
    if workflow not in ('IPD_REIMBURSEMENT','PREAUTH','ENHANCEMENT','CASHLESS_DISCHARGE','OPD_REIMBURSEMENT','OPD_CASHLESS') or after not in TRANSITIONS.get(before,set()):
        raise AppError(409,'invalid-workflow-transition','transition is not allowed for this workflow')

def link(conn,tenant,claim,body):
    workflow=body['workflow'];parent_id=body.get('parent_claim_id')
    if workflow=='ENHANCEMENT' and not parent_id:raise AppError(422,'parent-required','enhancement requires the last approved cashless request')
    root=claim['claim_id'] if workflow=='PREAUTH' else None
    if parent_id:
        parent=conn.fetch_one('SELECT * FROM claim WHERE tenant_id=$1 AND claim_id=$2 FOR UPDATE',tenant,parent_id)
        if not parent or workflow not in ('ENHANCEMENT','CASHLESS_DISCHARGE') or parent['workflow'] not in ('PREAUTH','ENHANCEMENT') or parent['status'] not in ('FINALISED','EXPORTED') or any(parent[k]!=claim[k] for k in ('policy_no','member_id','hospital_id')):
            raise AppError(422,'invalid-cashless-parent','parent must be an approved request for the same policy, member and hospital')
        if not conn.fetch_one("SELECT 1 FROM decision WHERE tenant_id=$1 AND claim_id=$2 AND disposition IN ('APPROVED_FULL','APPROVED_PARTIAL')",tenant,parent_id):raise AppError(422,'parent-not-authorised','parent requires a human recorded authorisation')
        if conn.fetch_one("SELECT 1 FROM claim WHERE tenant_id=$1 AND parent_claim_id=$2 AND status<>'WITHDRAWN'",tenant,parent_id):raise AppError(409,'cashless-stage-exists','continue from the most recent stage')
        root=parent['cashless_root_id'] or parent['claim_id']
    conn.execute('UPDATE claim SET parent_claim_id=$3,cashless_root_id=$4 WHERE tenant_id=$1 AND claim_id=$2',tenant,claim['claim_id'],parent_id,root)

def group_claims(conn,tenant,claim):
    root=claim.get('cashless_root_id')
    return [r['claim_id'] for r in conn.fetch_all('SELECT claim_id FROM claim WHERE tenant_id=$1 AND cashless_root_id=$2',tenant,root)] if root else [claim['claim_id']]
