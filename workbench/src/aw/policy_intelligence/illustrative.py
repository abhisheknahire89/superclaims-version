"""Generate an isolated illustrative derivative for the review demonstration, no network."""
import io,json,argparse
from pathlib import Path
from reportlab.pdfgen import canvas
from .acquisition import Library

def generate(root):
 buf=io.BytesIO();pdf=canvas.Canvas(buf);pdf.setTitle('ILLUSTRATIVE SYNTHETIC POLICY — NOT AN INSURANCE CONTRACT');t=pdf.beginText(50,770)
 lines=['ILLUSTRATIVE SYNTHETIC POLICY - NOT AN INSURANCE CONTRACT','Star Health Illustrative Demo','Star Health and Allied Insurance Company Limited','SYNHLIP26001V012026','1. Co-payment is 10% of admissible claim amount.','Wording effective from 2026-01-01.','No real member entitlement. Synthetic review workflow demonstration only.']
 for line in lines:t.textLine(line)
 pdf.drawText(t);pdf.showPage();pdf.save();lib=Library(root)
 try:
  key='illustrative-demo-v1';identity={'insurer':'STAR','product_name':'Illustrative Demo','uin':'SYNHLIP26001V012026','url':'illustrative://generated-local/demo-v1','declared_revision':'illustrative v1'}
  lib.record(key,identity,'DISCOVERED',['generated illustrative derivative; not a downloaded public policy']);metadata=lib.preserve(key,buf.getvalue(),{'illustrative':True,'retrieval_method':'GENERATED_ILLUSTRATIVE_NO_NETWORK','retrieved_at':None})
  return {'repository':'illustrative','id':key,'sha256':metadata['sha256'],'notice':lines[0]}
 finally:lib.close()
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);a=p.parse_args();print(json.dumps(generate(a.root),indent=2))
