"""Exact field and line scoring with explicit denominators; extractor never reads labels."""
import json,sys,time
from pathlib import Path
from collections import defaultdict
from decimal import Decimal
from aw.extraction.pages import read_pdf
from aw.extraction.ocr import read_image
from aw.extraction.providers import HeuristicProvider,classify


def measure(directory):
    directory=Path(directory);manifest=json.loads((directory/'manifest.json').read_text());groups=defaultdict(lambda:dict(documents=0,fields_correct=0,fields_total=0,lines_correct=0,lines_total=0,total_reconciled=0,bills=0,abstained=0,must_abstain=0,correct_abstention=0,seconds=0))
    cmap=json.loads((Path(__file__).resolve().parents[4]/'config/classifier-map-ILL-A.v2026.1.0.json').read_text())
    detail=[]
    for row in manifest['documents']:
        start=time.monotonic();data=(directory/row['file']).read_bytes();pages=read_pdf(data) if data[:5]==b'%PDF-' else [read_image(data)]
        dtype,_,_=classify(pages,cmap);out=HeuristicProvider().extract(dtype,pages)
        got={f['path']:f.get('normalised',f['value']) for f in out['fields']}
        fields=row['fields'];items=row.get('line_items',[])
        fc=sum(got.get(k)==v for k,v in fields.items());lc=sum(any(i['amount']==g['amount'] and i['description']==g['description'] for g in out['line_items']) for i in items)
        reconciliation=bool(out['line_items']) and sum(Decimal(i['amount']) for i in out['line_items'])==Decimal(str(got.get('bill.total',0)))
        abstain=any(f['confidence']<.95 for f in out['fields']+out['line_items']) or (dtype.endswith('ITEMISED') and not reconciliation) or 'EMBEDDED_INSTRUCTIONS_IGNORED' in out['warnings'] or not out['fields']
        key=(row.get('heldback',False),row['document_type'],row['quality']);g=groups[key];g['documents']+=1;g['fields_total']+=len(fields);g['fields_correct']+=fc;g['lines_total']+=len(items);g['lines_correct']+=lc;g['bills']+=row['document_type']=='FINAL_BILL_ITEMISED';g['total_reconciled']+=reconciliation;g['abstained']+=abstain;g['must_abstain']+=bool(row.get('must_abstain'));g['correct_abstention']+=bool(row.get('must_abstain')) and abstain;g['seconds']+=time.monotonic()-start
        detail.append({'file':row['file'],'classified_type':dtype,'field_correct':fc,'field_total':len(fields),'line_correct':lc,'line_total':len(items),'reconciles':reconciliation,'abstains':abstain})
    result={'synthetic_only':True,'groups':[{'heldback':k[0],'document_type':k[1],'quality':k[2],**v} for k,v in groups.items()],'documents':detail}
    (directory/'metrics.json').write_text(json.dumps(result,indent=2));print(json.dumps(result['groups'],indent=2));return result

if __name__=='__main__':measure(sys.argv[1] if len(sys.argv)>1 else 'corpus/out')
