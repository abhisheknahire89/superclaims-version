from playwright.sync_api import sync_playwright,expect
import json
import time
with sync_playwright() as pw:
    b=pw.chromium.launch();p=b.new_page(viewport={'width':1440,'height':960});p.goto('http://127.0.0.1:8080/#/login');p.get_by_role('button',name='PROC-07').click();expect(p.locator('#who')).to_contain_text('Processor');p.goto('http://127.0.0.1:8080/#/claim/CLM-DEMO-0001');expect(p.locator('.proposed')).to_be_visible()
    p.get_by_text('Manual reading',exact=True).click()
    token=p.evaluate('sessionStorage.getItem("aw.token")')
    if token and token.startswith('"'):token=json.loads(token)
    headers={} if token=='cookie' else {'Authorization':'Bearer '+token};base='http://127.0.0.1:8080'
    docs=p.request.get(base+'/v1/claims/CLM-DEMO-0001/documents',headers=headers).json()['items'];d=next(d for d in docs if d['classified_type']=='CLAIM_FORM')
    pg=p.request.get(base+f'/v1/claims/CLM-DEMO-0001/documents/{d["document_id"]}/pages/1',headers=headers).json()
    source=p.request.get(base+pg['words_url']).json();ln=next(l for l in source['lines'] if l['text'].startswith('Patient Name:'))
    p.get_by_label('Correct document type',exact=True).select_option('CLAIM_FORM');p.get_by_label('Field',exact=True).select_option('patient.name');p.get_by_label('Source document',exact=True).select_option(d['document_id']);p.get_by_label('Value or line description',exact=True).fill(ln['text'].split(':',1)[1].strip());p.get_by_label('Exact source quote',exact=True).fill(ln['text'])
    with p.expect_response(lambda r:'reading-confirmations' in r.url and r.request.method=='POST') as response:p.get_by_role('button',name='Save grounded reading').click()
    assert response.value.status==201,response.value.text()
    expect(p.locator('.proposed')).to_be_visible();time.sleep(1);p.reload();expect(p.locator('.proposed')).to_be_visible();p.get_by_text('Manual reading',exact=True).click();p.screenshot(path='evidence/2026-10-12/manual-reading.png',full_page=True)
    p.get_by_label('Source document',exact=True).select_option(d['document_id']);p.get_by_label('Field',exact=True).select_option('patient.name');p.get_by_label('Value or line description',exact=True).fill(ln['text'].split(':',1)[1].strip());p.get_by_label('Exact source quote',exact=True).fill(ln['text']);p.get_by_label('I confirm this quote on the source image',exact=True).check();expect(p.get_by_alt_text('Immutable source page for human transcription')).to_be_visible();p.get_by_label('I reviewed the whole page for critical conflicts',exact=True).check()
    with p.expect_response(lambda r:'reading-confirmations' in r.url and r.request.method=='POST') as response:p.get_by_role('button',name='Save grounded reading').click()
    assert response.value.status==201,response.value.text()
    expect(p.locator('.proposed')).to_be_visible();print('manual reading UI: grounded source and explicit human whole-page attestation saved (201)');b.close()
