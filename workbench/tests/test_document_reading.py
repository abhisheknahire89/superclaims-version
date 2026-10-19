"""Native and local OCR ingestion, safe bundles, financial confidence gating."""
import io
import zipfile
import unittest
from reportlab.pdfgen import canvas
from PIL import Image
from aw.extraction.pages import read_pdf, render_png
from aw.extraction.ocr import read_image
from aw.extraction.providers import HeuristicProvider
from aw.bundles import unpack
from tests.test_engine_equivalence import PACK
from aw.engine import evaluate
import json


def document():
    buf=io.BytesIO(); c=canvas.Canvas(buf)
    for y,text in [(780,'SYNTHETIC ONLY - Final Bill Itemised'),(750,'Patient Name: TEST PERSON'),
                   (720,'Grand Total: 1234.50'),(690,'No Description Qty Rate Amount'),
                   (660,'1 Pharmacy 1 1234.50 1234.50')]:
        c.drawString(50,y,text)
    c.save(); return buf.getvalue()

class LocalReading(unittest.TestCase):
    def test_native_pdf_and_png_jpg_ocr_have_grounded_boxes(self):
        pdf=document(); native=read_pdf(pdf)
        self.assertIn('TEST PERSON',native[0].text)
        png=render_png(pdf,1,220)
        for payload in (png, self.jpg(png)):
            page=read_image(payload)
            self.assertEqual(page.text_layer,'OCR')
            self.assertIn('1234.50',page.text)
            self.assertTrue(page.words)
            self.assertTrue(all(0 <= w['x0'] <= w['x1'] <= page.width for w in page.words))
    @staticmethod
    def jpg(png):
        buf=io.BytesIO(); Image.open(io.BytesIO(png)).convert('RGB').save(buf,'JPEG');return buf.getvalue()
    def test_scanned_pdf_uses_local_ocr(self):
        image=Image.open(io.BytesIO(render_png(document(),1,220))).convert('RGB')
        buf=io.BytesIO();image.save(buf,'PDF',resolution=220)
        pages=read_pdf(buf.getvalue());self.assertEqual(pages[0].text_layer,'OCR')
        self.assertIn('TEST PERSON',pages[0].text)
    def test_zip_rejects_traversal_and_nested_unallowed_files(self):
        for name,content in [('../bill.pdf',document()),('x.zip',b'PKxx')]:
            buf=io.BytesIO()
            with zipfile.ZipFile(buf,'w') as z:z.writestr(name,content)
            with self.assertRaises(ValueError):unpack(buf.getvalue())
    def test_safe_zip_returns_documents_without_writing_paths(self):
        buf=io.BytesIO()
        with zipfile.ZipFile(buf,'w') as z:z.writestr('ward/bill.pdf',document())
        self.assertEqual(unpack(buf.getvalue())[0][0],'bill.pdf')

class FinancialReadingGate(unittest.TestCase):
    def test_low_confidence_blocks_money_even_if_other_sources_agree(self):
        from tests.test_engine_equivalence import load_json,CFG
        fx=load_json(PACK/'fixtures/claims/trace-1-straightforward.input.json')
        fx['document_reading_blocks']=['critical-ocr-unconfirmed']
        out=evaluate(fx,load_json(CFG/'policy-ILL-INDEMNITY-A.v2026.1.0.json'),load_json(CFG/'nme-list-ILL-A.v2026.1.0.json'),None,load_json(CFG/'checklist-IPD-REIMB.v2026.1.0.json'))
        self.assertIsNone(out['recommendation']['recommended_payable'])
        self.assertIn('ALL_FINANCIAL',out['recommendation']['blocked_scopes'])

from tests.test_workflow import Seeded
from aw import synthetic
from aw.extraction.manual import confirm
from aw.extraction.pipeline import load_pages
from aw.errors import AppError

class ManualReading(Seeded):
    def test_manual_confirmation_preserves_source_and_rejects_fake_values(self):
        ids=self.new_claim('CLM-MANUAL','trace-1-straightforward',synthetic.claim_documents()['CLM-DEMO-0001'])
        with self.db.tenant_tx('TENANT-DEMO') as c:
            d=c.fetch_one("SELECT document_id FROM document WHERE claim_id='CLM-MANUAL' AND classified_type='FINAL_BILL_ITEMISED'")
            pages=load_pages(c,self.ctx.store,'TENANT-DEMO',d['document_id'])
            ln=next(l for p in pages for l in p.lines if 'GRAND TOTAL' in l['text'])
            pg=next(p.page_no for p in pages if ln in p.lines)
            evidence=[{'page':pg,'quote':ln['text'],'bbox':[ln['x0'],ln['top'],ln['x1'],ln['bottom']]}]
            p=self.p('PROC-07')
            bad={'fields':[{'path':'bill.total','value':'999.00','normalised':'999.00','confidence':1,'evidence':evidence}]}
            with self.assertRaises(AppError):confirm(c,self.ctx,p,'CLM-MANUAL',d['document_id'],bad)
            good={'fields':[{'path':'bill.total','value':'109360.50','normalised':'109360.50','confidence':1,'evidence':evidence}]}
            out=confirm(c,self.ctx,p,'CLM-MANUAL',d['document_id'],good)
            self.assertEqual(out['confirmed'],1)
        self.worker.drain()
        self.assertEqual(self.current('CLM-MANUAL')['recommended_payable_paise'],10759100)

class GenericLayouts(unittest.TestCase):
    def test_reordered_title_multiple_columns_and_stacked_fields(self):
        from aw.extraction.pages import PageText
        from aw.extraction.providers import classify
        from aw.extraction.grounding import check
        from tests.support import load_json
        text=['Final Bill Itemized','Patient Name: Test Person Gender: Female','Bill Number:', 'SYN-123', 'Net Total: 1234.50']
        lines=[dict(text=t,x0=20,top=20+i*18,x1=400,bottom=33+i*18) for i,t in enumerate(text)]
        page=PageText(1,600,800,'\n'.join(text),lines,[],'NATIVE')
        dtype,_,_=classify([page],load_json(PACK/'config/classifier-map-ILL-A.v2026.1.0.json'))
        self.assertEqual(dtype,'FINAL_BILL_ITEMISED')
        out=HeuristicProvider().extract(dtype,[page]);fields={f['path']:f.get('normalised') for f in out['fields']}
        self.assertEqual(fields['patient.name'],'Test Person');self.assertEqual(fields['patient.gender'],'F')
        self.assertEqual(fields['bill.number'],'SYN-123');self.assertEqual(fields['bill.total'],'1234.50')
        self.assertTrue(all(check(f['evidence'][0]['quote'],page.text)=='VERIFIED' for f in out['fields']))
    def test_within_document_contradictory_totals_are_not_silently_dropped(self):
        from aw.extraction.pages import PageText
        texts=['Final Bill Itemised','Bill Total: 100.00','Grand Total: 200.00']
        page=PageText(1,600,800,'\n'.join(texts),[dict(text=t,x0=1,top=20+i*20,x1=400,bottom=35+i*20) for i,t in enumerate(texts)],[],'NATIVE')
        out=HeuristicProvider().extract('FINAL_BILL_ITEMISED',[page])
        self.assertEqual(len([f for f in out['fields'] if f['path']=='bill.total']),2)

class MissingCriticalReading(Seeded):
    def test_unreadable_continuation_page_blocks_otherwise_valid_claim(self):
        self.new_claim('CLM-UNREADABLE-CONTINUATION','trace-1-straightforward',synthetic.claim_documents()['CLM-DEMO-0001'])
        with self.db.tenant_tx('TENANT-DEMO') as c:
            c.execute("UPDATE document_page SET text_layer='NONE' WHERE tenant_id='TENANT-DEMO' AND document_id IN (SELECT document_id FROM document WHERE claim_id='CLM-UNREADABLE-CONTINUATION' AND classified_type='FINAL_BILL_ITEMISED') AND page_no=2")
            ei,_=__import__('aw.evaluations',fromlist=['build_engine_input']).build_engine_input(c,'TENANT-DEMO','CLM-UNREADABLE-CONTINUATION','TEST')
            self.assertTrue(ei['document_reading_blocks'])
    def test_bill_missing_patient_identity_abstains_despite_matching_other_documents(self):
        docs=synthetic.claim_documents()['CLM-DEMO-0001']
        docs=[d for d in docs if d[1]!='FINAL_BILL_ITEMISED']+[
            ('missing-name','FINAL_BILL_ITEMISED',synthetic.simple('FINAL BILL - ITEMISED',['Grand Total: 109360.50','Bill No: SYN-MISSING']))]
        self.new_claim('CLM-MISSING-IDENTITY','trace-1-straightforward',docs)
        ev=self.current('CLM-MISSING-IDENTITY');self.assertIsNone(ev['recommended_payable_paise']);self.assertIn('ALL_FINANCIAL',ev['blocked_scopes'])

class ReadingResourceSafety(unittest.TestCase):
    def test_stacked_low_confidence_value_remains_low_confidence(self):
        from aw.extraction.pages import PageText
        lines=[dict(text='Bill Total:',x0=1,x1=100,top=10,bottom=20,confidence=.99),dict(text='100.00',x0=1,x1=100,top=25,bottom=35,confidence=.40)]
        page=PageText(1,600,800,'Bill Total:\n100.00',lines,[],'OCR')
        fields=HeuristicProvider().extract('FINAL_BILL_ITEMISED',[page])['fields']
        self.assertEqual(next(f for f in fields if f['path']=='bill.total')['confidence'],.40)
    def test_oversized_pdf_page_rejected_before_render(self):
        buf=io.BytesIO();c=canvas.Canvas(buf,pagesize=(9000,9000));c.drawString(10,10,'SYNTHETIC ONLY');c.save()
        with self.assertRaisesRegex(ValueError,'PDF_.*RASTER_LIMIT'):read_pdf(buf.getvalue())

class HumanTranscription(Seeded):
    def test_visual_transcription_is_image_bound_audited_and_append_only(self):
        from aw.ids import sha256_hex
        from aw.db import PgError
        ids=self.new_claim('CLM-TRANSCRIPT','trace-1-straightforward',synthetic.claim_documents()['CLM-DEMO-0001'])
        with self.db.tenant_tx('TENANT-DEMO') as c:
            d=c.fetch_one("SELECT document_id FROM document WHERE claim_id='CLM-TRANSCRIPT' AND classified_type='FINAL_BILL_ITEMISED'")
            pages=load_pages(c,self.ctx.store,'TENANT-DEMO',d['document_id']);p=next(p for p in pages if 'GRAND TOTAL' in p.text);ln=next(l for l in p.lines if 'GRAND TOTAL' in l['text'])
            # Simulate an OCR omission while keeping the immutable original image untouched.
            original=c.fetch_one('SELECT * FROM document_page WHERE tenant_id=$1 AND document_id=$2 AND page_no=$3','TENANT-DEMO',d['document_id'],p.page_no)
            image_hash=sha256_hex(self.ctx.store.get(original['image_key']))
            key=original['text_key']+'.omission';empty=p.to_json();empty['text']='';empty['lines']=[];empty['words']=[];empty['text_layer']='NONE';self.ctx.store.put_once(key,json.dumps(empty).encode())
            c.execute("UPDATE document_page SET text_key=$3,text_layer='NONE' WHERE tenant_id=$1 AND document_id=$2 AND page_no=$4",'TENANT-DEMO',d['document_id'],key,p.page_no)
            body={'fields':[{'path':'bill.total','value':'109360.50','normalised':'109360.50','confidence':1,'evidence':[{'page':p.page_no,'quote':ln['text'],'bbox':[ln['x0'],ln['top'],ln['x1'],ln['bottom']]}]}], 'human_confirmed_source':True,'human_reviewed_full_page':True,'source_image_sha256':'0'*64}
            with self.assertRaises(AppError):confirm(c,self.ctx,self.p('PROC-07'),'CLM-TRANSCRIPT',d['document_id'],body)
            body['source_image_sha256']=image_hash;out=confirm(c,self.ctx,self.p('PROC-07'),'CLM-TRANSCRIPT',d['document_id'],body)
            fact=c.fetch_one('SELECT evidence FROM extracted_fact WHERE extraction_run_id=$1 AND field_path=$2',out['extraction_run_id'],'bill.total')
            self.assertEqual(fact['evidence']['source'],'HUMAN_TRANSCRIPTION')
            transcript=c.fetch_one('SELECT * FROM human_page_transcription WHERE transcription_id=$1',fact['evidence']['transcription_id'])
            self.assertEqual(transcript['image_sha256'],image_hash);self.assertEqual(transcript['confirmed_by'],'PROC-07')
            body.pop('human_confirmed_source')
            repeated=confirm(c,self.ctx,self.p('PROC-07'),'CLM-TRANSCRIPT',d['document_id'],body)
            again=c.fetch_one('SELECT evidence FROM extracted_fact WHERE extraction_run_id=$1 AND field_path=$2',repeated['extraction_run_id'],'bill.total')['evidence']
            self.assertEqual(again['source'],'HUMAN_TRANSCRIPTION')
            self.assertIn(transcript['transcription_id'],again['transcription_ids'])
            body['human_confirmed_source']=True
            reviewed=confirm(c,self.ctx,self.p('PROC-07'),'CLM-TRANSCRIPT',d['document_id'],body)
            self.assertEqual(c.fetch_val('SELECT count(*) FROM human_page_transcription WHERE document_id=$1 AND reviewed_complete',d['document_id']),2)
            # New evidence is immutable and invisible to another tenant.
        with self.db.tenant_tx('OTHER-TENANT') as c:self.assertEqual(c.fetch_val('SELECT count(*) FROM human_page_transcription'),0)
        with self.assertRaises(PgError):
            with self.db.tenant_tx('TENANT-DEMO') as c:c.execute("UPDATE human_page_transcription SET quote='fake'")
        with self.db.tenant_tx('TENANT-DEMO') as c:
            page=next(p for p in load_pages(c,self.ctx.store,'TENANT-DEMO',d['document_id']) if p.page_no==original['page_no']);self.assertIn(ln['text'],page.text)

class AutomaticGrounding(unittest.TestCase):
    def test_true_quote_cannot_ground_false_amount_or_impossible_box(self):
        from aw.extraction.pages import PageText
        from aw.extraction.grounding import verify_record
        page=PageText(1,600,800,'Grand Total: 100.00',[dict(text='Grand Total: 100.00',x0=1,x1=100,top=10,bottom=20)],[],'NATIVE')
        record={'path':'bill.total','value':'200.00','normalised':'200.00','evidence':[{'page':1,'quote':page.text,'bbox':[1,10,100,20]}]}
        self.assertEqual(verify_record(record,{1:page}),'NOT_FOUND')
        record['value']=record['normalised']='100.00';record['evidence'][0]['bbox']=[-1,10,100,20]
        self.assertEqual(verify_record(record,{1:page}),'NOT_FOUND')
        record['evidence'][0]['bbox']=[1,10,100,20];self.assertEqual(verify_record(record,{1:page}),'VERIFIED')

class UploadLimits(Seeded):
    def test_oversize_signed_upload_is_rejected_before_storing(self):
        from aw.api.app import create_app
        from tests.support import AsgiClient
        app=create_app(self.ctx);client=AsgiClient(app);upload='TEST-LIMIT'
        self.ctx.store.put_once(f'staging/TENANT-DEMO/{upload}.json',json.dumps({'size_bytes':3,'sha256':'0'*64}).encode())
        signed=app.state.api.sign(f'/v1/uploads/{upload}','TENANT-DEMO')
        response=client.request('PUT',signed,body=b'1234')
        self.assertEqual(response.status,413)
        self.assertFalse(self.ctx.store.exists(f'staging/TENANT-DEMO/bytes/{upload}'))
        self.assertEqual(client.request('PUT',signed,body=b'12').status,422)
        self.assertEqual(client.request('PUT',signed,body=b'123').status,422)
        self.assertFalse(self.ctx.store.exists(f'staging/TENANT-DEMO/bytes/{upload}'))
