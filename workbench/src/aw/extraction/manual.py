"""Append-only manual extraction versions, grounded in stored source pages."""
import json
from copy import deepcopy
from jsonschema import Draft202012Validator
from .. import audit, jobs
from ..db import Json
from ..ids import new_id
from ..errors import AppError
from . import grounding, normalise
from .pipeline import load_pages


def confirm(conn, ctx, principal, claim_id, document_id, body):
    body=deepcopy(body)
    principal.require('fact.correct')
    doc=conn.fetch_one('SELECT * FROM document WHERE tenant_id=$1 AND document_id=$2 AND claim_id=$3',principal.tenant_id,document_id,claim_id)
    if not doc or doc['status'] in ('SUPERSEDED','QUARANTINED'):
        raise AppError(404,'document-not-found','active document required')
    raw={'document_id':document_id,'document_type':body.get('document_type',doc['classified_type'] or 'OTHER'),
         'type_confidence':1.0,'fields':body.get('fields',[]),'line_items':body.get('line_items',[]),'warnings':[]}
    schema=json.loads((ctx.schema_dir/'extraction-output.schema.json').read_text())
    if list(Draft202012Validator(schema).iter_errors(raw)):
        raise AppError(422,'invalid-manual-reading','fields and lines must match the extraction schema')
    from ..ingest import OPEN_STATES
    claim=conn.fetch_one('SELECT status FROM claim WHERE tenant_id=$1 AND claim_id=$2 FOR UPDATE',principal.tenant_id,claim_id)
    if claim['status'] not in OPEN_STATES:
        raise AppError(409,'claim-closed','reopen the claim before correcting evidence')
    pages={p.page_no:p for p in load_pages(conn,ctx.store,principal.tenant_id,document_id)}
    values=[]
    for f in raw['fields']+raw['line_items']:
        e=f['evidence'][0];page=pages.get(e['page']);bbox=e.get('bbox')
        human_matches=[ln for ln in page.lines if ln.get('source')=='HUMAN_TRANSCRIPTION' and grounding.check(e['quote'],ln['text'])=='VERIFIED'] if page else []
        if page and bbox and (0<=bbox[0]<bbox[2]<=page.width and 0<=bbox[1]<bbox[3]<=page.height) and body.get('human_confirmed_source') is True:
            from ..ids import sha256_hex
            pg=conn.fetch_one('SELECT image_key FROM document_page WHERE tenant_id=$1 AND document_id=$2 AND page_no=$3',principal.tenant_id,document_id,e['page'])
            image_hash=sha256_hex(ctx.store.get(pg['image_key']))
            if body.get('source_image_sha256')!=image_hash:
                raise AppError(422,'source-image-mismatch','confirm against the current immutable source image')
            tid=new_id('HTX')
            conn.execute('INSERT INTO human_page_transcription (tenant_id,transcription_id,claim_id,document_id,page_no,image_sha256,quote,bbox,confirmed_by,reviewed_complete) VALUES ($1,$2,$3,$4,$5,$6,$7,$8::jsonb,$9,$10)',principal.tenant_id,tid,claim_id,document_id,e['page'],image_hash,e['quote'],Json(bbox),principal.user_id,body.get('human_reviewed_full_page') is True)
            page.text+='\n'+e['quote']
            page.lines.append({'text':e['quote'],'x0':bbox[0],'top':bbox[1],'x1':bbox[2],'bottom':bbox[3],'source':'HUMAN_TRANSCRIPTION','transcription_id':tid})
            e['transcription_id']=tid
            e['source']='HUMAN_TRANSCRIPTION'
        elif human_matches:
            e['source']='HUMAN_TRANSCRIPTION'
            e['transcription_ids']=[ln['transcription_id'] for ln in human_matches]
        if not page or grounding.check(e['quote'],page.text)!='VERIFIED' or not bbox or not (0<=bbox[0]<bbox[2]<=page.width and 0<=bbox[1]<bbox[3]<=page.height):
            raise AppError(422,'ungrounded-manual-reading','quote and bounding box must match a stored source page')
        # A source quote must overlap cited source geometry, and must contain the actual value.
        matching=[ln for ln in page.lines if grounding.check(e['quote'],ln['text'])=='VERIFIED']
        if not any(bbox[0]<=ln['x1'] and bbox[2]>=ln['x0'] and bbox[1]<=ln['bottom'] and bbox[3]>=ln['top'] for ln in matching):
            raise AppError(422,'ungrounded-box','box does not overlap the quoted source line')
        if 'path' in f:
            value=f.get('normalised',f['value']);path=f['path']
            if path.endswith('.date') or path=='patient.dob':
                import re
                dates=[normalise.to_date(t) for t in re.findall(r'\d{1,4}[/.-]\d{1,2}[/.-]\d{1,4}',e['quote'])]
                found=value in dates
            elif path=='bill.total':
                import re
                found=value in [normalise.amount(t) for t in re.findall(r'\d[\d,]*(?:\.\d{1,2})?',e['quote'])]
            elif isinstance(value,bool):
                found=path=='bill.is_itemised' and 'item' in e['quote'].lower()
            else:
                found=normalise.text_for_matching(str(value)) in normalise.text_for_matching(e['quote'])
        else:
            path='bill.line_item';value={k:v for k,v in f.items() if k!='evidence'}
            import re
            numbers=re.findall(r'\d[\d,]*(?:\.\d{1,2})?',e['quote'])
            found=normalise.text_for_matching(f['description']) in normalise.text_for_matching(e['quote']) and f['amount'] in [normalise.amount(t) for t in numbers]
            if f.get('quantity'):
                found=found and f['quantity'] in [normalise.quantity(t) for t in numbers]
            if f.get('unit_rate'):
                found=found and f['unit_rate'] in [normalise.amount(t) for t in numbers]
        if not found:
            raise AppError(422,'value-not-in-quote','manual value is not derivable from source quote')
        values.append((path,value,e))
    if not values:
        raise AppError(422,'empty-manual-reading','provide at least one grounded field or line')
    old=conn.fetch_val('SELECT extraction_run_id FROM extraction_run WHERE tenant_id=$1 AND document_id=$2 ORDER BY started_at DESC LIMIT 1',principal.tenant_id,document_id)
    run=new_id('MAN')
    conn.execute("INSERT INTO extraction_run (tenant_id,extraction_run_id,document_id,pipeline_version,model_ref,outcome,finished_at) VALUES ($1,$2,$3,'manual-1','human','OK',now())",principal.tenant_id,run,document_id)
    paths={v[0] for v in values}
    if old:
        for f in conn.fetch_all('SELECT * FROM extracted_fact WHERE tenant_id=$1 AND extraction_run_id=$2',principal.tenant_id,old):
            if f['field_path'] not in paths or (f['field_path']=='bill.line_item' and f['normalised_value']['line_no'] not in {v[1]['line_no'] for v in values if v[0]=='bill.line_item'}):
                conn.execute('INSERT INTO extracted_fact (tenant_id,fact_id,claim_id,extraction_run_id,field_path,normalised_value,confidence,evidence,grounding_check) VALUES ($1,$2,$3,$4,$5,$6::jsonb,$7,$8::jsonb,$9)',principal.tenant_id,new_id('FCT'),claim_id,run,f['field_path'],Json(f['normalised_value']),f['confidence'],Json(f['evidence']),f['grounding_check'])
    for path,value,e in values:
        conn.execute("INSERT INTO extracted_fact (tenant_id,fact_id,claim_id,extraction_run_id,field_path,normalised_value,confidence,evidence,grounding_check) VALUES ($1,$2,$3,$4,$5,$6::jsonb,1,$7::jsonb,'VERIFIED')",principal.tenant_id,new_id('FCT'),claim_id,run,path,Json(value),Json({'document_id':document_id,**e}))
    conn.execute("UPDATE document SET classified_type=$3, status='EXTRACTED' WHERE tenant_id=$1 AND document_id=$2",principal.tenant_id,document_id,raw['document_type'])
    audit.append(conn,principal.tenant_id,claim_id,principal.actor,'REVIEWER_ACTION_RECORDED',{'document_id':document_id,'extraction_run_id':run,'fields':sorted(paths)})
    from ..ingest import mark_stale
    mark_stale(conn,principal.tenant_id,claim_id,principal.actor,'MANUAL_READING')
    conn.execute('UPDATE claim SET row_version=row_version+1 WHERE tenant_id=$1 AND claim_id=$2',principal.tenant_id,claim_id)
    jobs.enqueue(conn,principal.tenant_id,'RECONCILE',claim_id,f'reconcile:{claim_id}:{run}',{})
    return {'extraction_run_id':run,'confirmed':len(values)}
