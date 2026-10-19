"""TC-UX-02: real deduction-to-highlight latency and submitted override in headless Chromium."""
import json,time
from pathlib import Path
from playwright.sync_api import sync_playwright,expect
with sync_playwright() as pw:
 b=pw.chromium.launch();p=b.new_page(viewport={'width':1500,'height':1100});errors=[];p.on('pageerror',lambda e:errors.append(str(e)))
 p.goto('http://127.0.0.1:8080/#/login');p.get_by_role('button',name='PROC-11').click();expect(p.locator('#who')).to_contain_text('Processor 11');p.goto('http://127.0.0.1:8080/#/claim/CLM-DEMO-0002')
 deduction=p.locator('tr.line').filter(has=p.get_by_text('L14',exact=True)).locator('button.ded').first
 # The loaded evidence image is warmed once, matching the spec's "after load" condition.
 deduction.click();expect(p.locator('.viewer .box')).to_be_visible();expect(p.get_by_label('Highlighted text')).not_to_be_empty()
 samples=[]
 for _ in range(10):
  p.evaluate("() => {window.awEvidenceStart=null;document.addEventListener('click',()=>window.awEvidenceStart=performance.now(),{once:true,capture:true});window.awEvidenceDone=new Promise(resolve=>{const observer=new MutationObserver(()=>{const box=document.querySelector('.viewer .box');if(window.awEvidenceStart!==null&&box&&box.getBoundingClientRect().width>0){observer.disconnect();resolve(performance.now()-window.awEvidenceStart);}});observer.observe(document.querySelector('#app'),{childList:true,subtree:true});setTimeout(()=>{observer.disconnect();resolve(5000);},5000);});}")
  deduction.click();samples.append(p.evaluate('window.awEvidenceDone'))
 assert max(samples)<=300,{'TC-UX-02_ms':samples}
 p.get_by_label('Override amount',exact=True).fill('0.00');p.get_by_label('Override reason',exact=True).fill('TARIFF_ITEM_NOT_APPLICABLE');p.get_by_label('Override comment',exact=True).fill('Synthetic CT performed outside the tariff package; reviewed quoted source.')
 with p.expect_response(lambda r:'/reviewer-actions' in r.url and r.request.method=='POST') as r:p.get_by_role('button',name='Override',exact=True).click()
 assert r.value.status==201,r.value.text();expect(p.get_by_text('(override)',exact=False).first).to_be_visible(timeout=15000)
 row=p.locator('tr.line').filter(has=p.get_by_text('L14',exact=True));expect(row).to_contain_text('0.00');expect(p.locator('.ws-head')).to_contain_text('85,000.00');p.screenshot(path='evidence/2026-10-12/reviewer-override.png',full_page=True)
 p.get_by_role('tab',name='Audit',exact=True).click();expect(p.get_by_text('Hash chain verified',exact=False)).to_be_visible();p.screenshot(path='evidence/2026-10-12/override-audit.png',full_page=True)
 result={'case':'TC-UX-02','synthetic_only':True,'condition':'same loaded page, warm browser cache, localhost Chromium','samples_ms':samples,'max_ms':max(samples),'mean_ms':sum(samples)/len(samples),'override_status':201,'page_errors':errors};Path('evidence/2026-10-12/reviewer-ui-benchmark.json').write_text(json.dumps(result,indent=2));assert not errors,errors;b.close();print(json.dumps(result))
