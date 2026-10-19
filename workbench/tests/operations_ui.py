"""Local buyer screens, keyboard assignment, query exports/replies and administration."""
from playwright.sync_api import sync_playwright,expect
with sync_playwright() as pw:
 b=pw.chromium.launch();p=b.new_page(viewport={'width':1500,'height':1100});errors=[];p.on('pageerror',lambda e:errors.append(str(e)))
 p.goto('http://127.0.0.1:8080/#/login');p.get_by_role('button',name='SUP-02').click();expect(p.locator('#who')).to_contain_text('Supervisor')
 p.goto('http://127.0.0.1:8080/#/claim/CLM-DEMO-0003');expect(p.get_by_label('Assign reviewer')).to_be_visible();p.get_by_label('Assign reviewer').select_option('PROC-07')
 with p.expect_response(lambda r:':assign' in r.url) as r:p.get_by_role('button',name='Assign claim',exact=True).click()
 assert r.value.status==200,r.value.text()
 p.goto('http://127.0.0.1:8080/#/queue');p.get_by_label('Workflow filter').select_option('OPD_REIMBURSEMENT');expect(p.locator('tr.qrow')).to_have_count(1)
 p.get_by_label('Workflow filter').select_option('');p.get_by_label('Assignment filter').select_option('UNASSIGNED');p.screenshot(path='evidence/2026-10-12/queue-filters.png',full_page=True)
 p.goto('http://127.0.0.1:8080/#/operations');expect(p.get_by_role('heading',name='Operations dashboard')).to_be_visible();expect(p.get_by_text('Pending second approvals',exact=True)).to_be_visible();p.screenshot(path='evidence/2026-10-12/operations.png',full_page=True)
 p.goto('http://127.0.0.1:8080/#/claim/CLM-DEMO-0003');p.get_by_role('tab',name='Queries').click();expect(p.get_by_role('button',name='Approve and send').first).to_be_visible()
 with p.expect_response(lambda r:':approve' in r.url and '/queries/' in r.url) as r:p.get_by_role('button',name='Approve and send').first.click()
 assert r.value.status==200,r.value.text();expect(p.get_by_role('button',name='Export approved letter PDF').first).to_be_visible()
 with p.expect_download() as download:p.get_by_role('button',name='Export approved letter PDF').first.click()
 download.value.save_as('evidence/2026-10-12/query-letter.pdf');path=download.value.path();assert open(path,'rb').read(5)==b'%PDF-'
 with p.expect_response(lambda r:':answer' in r.url) as r:p.get_by_role('button',name='Record evidence reply').first.click()
 assert r.value.status==200,r.value.text();p.screenshot(path='evidence/2026-10-12/query-reply.png',full_page=True)
 p.get_by_role('button',name='Sign out').click();p.get_by_role('button',name='ADM-01').click();expect(p.locator('#who')).to_contain_text('Tenant admin');p.goto('http://127.0.0.1:8080/#/users');expect(p.get_by_role('heading',name='Local users and roles')).to_be_visible()
 p.get_by_label('User ID',exact=True).fill('BUYER-DEMO');p.get_by_label('Display name',exact=True).fill('Synthetic buyer reviewer');p.get_by_label('PROCESSOR',exact=True).check();p.get_by_label('Approval limit',exact=True).fill('5000.00');p.get_by_label('New user password',exact=True).fill('Synthetic-buyer-2026!');p.get_by_label('Administrator password',exact=True).fill('Synthetic-demo-2026!')
 with p.expect_response(lambda r:r.url.endswith('/v1/admin/users') and r.request.method=='POST') as r:p.get_by_role('button',name='Save user',exact=True).click()
 assert r.value.status==200,r.value.text();expect(p.get_by_role('button',name='Edit BUYER-DEMO',exact=True)).to_be_visible();p.screenshot(path='evidence/2026-10-12/users.png',full_page=True)
 assert not errors,errors;b.close();print('operations UI: assignment, filters, KPIs, approved PDF download, evidence reply, audited user creation;0 page errors')
