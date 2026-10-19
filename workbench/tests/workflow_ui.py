from pathlib import Path
from playwright.sync_api import sync_playwright,expect
base='http://127.0.0.1:8080';out=Path('evidence/2026-10-12/workflows');out.mkdir(exist_ok=True)
with sync_playwright() as pw:
 b=pw.chromium.launch();p=b.new_page(viewport={'width':1500,'height':1100});p.goto(base+'/#/login');p.get_by_role('button',name='PROC-07').click();expect(p.locator('#who')).to_contain_text('Processor')
 for label,cid,amount in [('ipd','CLM-DEMO-0001','1,07,591.00'),('preauth','CLM-DEMO-PREAUTH','3,000.00'),('discharge','CLM-DEMO-DISCHARGE','3,000.00'),('opd','CLM-DEMO-OPD','3,000.00')]:
  p.goto(base+'/#/claim/'+cid);expect(p.locator('.proposed')).to_contain_text(amount);p.screenshot(path=str(out/(label+'-review.png')),full_page=True);p.get_by_role('tab',name='Decision').click();p.get_by_role('button',name='Record decision',exact=True).click();expect(p.locator('.banner.final')).to_contain_text(amount);p.screenshot(path=str(out/(label+'-decided.png')),full_page=True)
 p.goto(base+'/#/claim/CLM-DEMO-PREAUTH');expect(p.locator('.banner.final')).to_be_visible();p.get_by_text('Continue cashless case',exact=True).click();p.get_by_label('External claim reference',exact=True).fill('SYN-BROWSER-ENHANCEMENT');p.get_by_label('New claim workflow',exact=True).select_option('ENHANCEMENT')
 with p.expect_response(lambda r:r.url.endswith('/v1/claims') and r.request.method=='POST') as r:p.get_by_role('button',name='Register claim',exact=True).click()
 assert r.value.status==201,r.value.text();assert r.value.json()['parent_claim_id']=='CLM-DEMO-PREAUTH';p.screenshot(path=str(out/'enhancement-registered.png'),full_page=True);b.close();print('4 workflow browser reviews and human decisions passed; linked enhancement registration201;9 screenshots')
