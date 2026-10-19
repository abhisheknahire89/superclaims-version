"""Additional synthetic workflow cases; seed leaves all dispositions undecided."""
from datetime import date
from . import ingest,synthetic
from .matching import normalise_name
from .money import to_paise

CASES=[('CLM-DEMO-PREAUTH','PREAUTH','Synthetic Preauth Person','M','POLCFG-ILL-INDEMNITY-A'),
       ('CLM-DEMO-DISCHARGE','CASHLESS_DISCHARGE','Synthetic Discharge Person','F','POLCFG-ILL-INDEMNITY-A'),
       ('CLM-DEMO-OPD','OPD_REIMBURSEMENT','Synthetic Outpatient Person','F','POLCFG-ILL-OPD-A')]

def documents(workflow,name,total='3000.00',number='SYN-WORKFLOW'):
    title='ESTIMATE BILL - ITEMISED' if workflow in ('PREAUTH','ENHANCEMENT') else 'FINAL BILL - ITEMISED'
    d=synthetic.Doc(title)
    for label,value in [('Patient Name',name),('Gender','Female' if 'Outpatient' in name or 'Discharge' in name else 'Male'),('Bill Number',number),('Bill Date','01/10/2026'),('Admission Date','01/10/2026'),('Grand Total',total)]:d.line(label+': '+value)
    d.table([{'line_id':'L01','description':'Consultant visit','quantity':'1','unit_rate':total,'billed':total,'service_date':'2026-10-01','ward_context':'OPD' if workflow.startswith('OPD') else 'WARD'}])
    bill=d.bytes();dtype='ESTIMATE_BILL' if workflow in ('PREAUTH','ENHANCEMENT') else 'FINAL_BILL_ITEMISED'
    extra=[]
    if workflow in ('PREAUTH','ENHANCEMENT'):
        extra=[('request','PREAUTH_REQUEST',synthetic.simple('PREAUTH REQUEST',[f'Patient Name: {name}','Gender: Male','Admission Date: 01/10/2026','Diagnosis: Synthetic planned treatment']))]
    elif workflow=='CASHLESS_DISCHARGE':
        extra=[('discharge','DISCHARGE_SUMMARY',synthetic.simple('DISCHARGE SUMMARY',[f'Patient Name: {name}','Gender: Female','Admission Date: 01/10/2026','Discharge Date: 02/10/2026','Diagnosis: Synthetic discharge condition']))]
    else:
        extra=[('prescription','PRESCRIPTION',synthetic.simple('PRESCRIPTION',[f'Patient Name: {name}','Gender: Female','Admission Date: 01/10/2026','Diagnosis: Synthetic outpatient condition'])),('receipt','PAYMENT_RECEIPT',synthetic.simple('PAYMENT RECEIPT',[f'Patient Name: {name}','Gender: Female',f'Received Amount: {total}']))]
    return [('bill',dtype,bill)]+extra

def seed_members(conn,tenant):
    for cid,workflow,name,gender,cfg in CASES:
        conn.execute('INSERT INTO member (tenant_id,member_id,full_name,name_normalised,gender,dob) VALUES ($1,$2,$3,$4,$5,$6) ON CONFLICT DO NOTHING',tenant,'MEM-'+cid,name,normalise_name(name),gender,date(1985,1,1))
        conn.execute("INSERT INTO policy (tenant_id,policy_no,product_name,period_start,period_end,config_artifact_id,config_version) VALUES ($1,$2,'Synthetic workflow policy','2026-01-01','2026-12-31',$3,'2026.1.0') ON CONFLICT DO NOTHING",tenant,'POL-'+cid,cfg)
        conn.execute("INSERT INTO policy_member (tenant_id,policy_no,member_id,continuous_cover_since,base_sum_insured_paise,cumulative_bonus_paise) VALUES ($1,$2,$3,'2020-01-01',30000000,0) ON CONFLICT DO NOTHING",tenant,'POL-'+cid,'MEM-'+cid)

def prepare(ctx,worker=None):
    tenant='TENANT-DEMO'
    with ctx.db.tenant_tx(tenant) as conn:seed_members(conn,tenant)
    for cid,workflow,name,gender,cfg in CASES:
        with ctx.db.tenant_tx(tenant) as conn:
            if not ingest.get_claim(conn,tenant,cid):ingest.create_claim(conn,tenant,{'claim_id':cid,'workflow':workflow,'policy_no':'POL-'+cid,'member_id':'MEM-'+cid,'hospital_id':'HOSP-ILL-NN-07','external_ref':'SYN-'+cid},'USER:PROC-07')
            if conn.fetch_val('SELECT count(*) FROM document WHERE tenant_id=$1 AND claim_id=$2',tenant,cid):continue
            for label,dtype,data in documents(workflow,name,number=cid):ingest.add_document(conn,ctx.store,tenant,cid,data,declared_type=dtype,source_channel='API',actor='USER:PROC-07')
    if worker:worker.drain()
