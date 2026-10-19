import json,re
from playwright.sync_api import sync_playwright,expect
with sync_playwright() as pw:
 b=pw.chromium.launch();p=b.new_page(viewport={'width':1440,'height':1100});p.goto('http://127.0.0.1:8080/#/login');p.get_by_role('button',name='CFG-01').click();expect(p.locator('#who')).to_contain_text('Config admin');p.goto('http://127.0.0.1:8080/#/config')
 select=p.get_by_label('Stored artifact version');expect(select.locator('option')).not_to_have_count(0);select.select_option(json.dumps(['POLCFG-ILL-INDEMNITY-A','2026.1.0'],separators=(',',':')));expect(p.get_by_label('Configuration JSON')).to_have_value(re.compile('.*config_id.*',re.S));p.get_by_label('New version').fill('2026.2.0');p.get_by_label('Effective from').fill('2026-11-01')
 with p.expect_response(lambda r:r.url.endswith('/v1/config-artifacts') and r.request.method=='POST') as r:p.get_by_role('button',name='Create draft',exact=True).click()
 assert r.value.status==201,r.value.text()
 with p.expect_response(lambda r:':validate' in r.url) as r:p.get_by_role('button',name='Validate stored version').click()
 assert r.value.json()['valid']
 with p.expect_response(lambda r:':replay' in r.url) as r:p.get_by_role('button',name='Replay saved claims').click()
 assert r.value.status==202 and r.value.json()['claims']>=3,r.value.text();p.screenshot(path='evidence/2026-10-12/config-replay.png',full_page=True)
 p.get_by_label('Publication password',exact=True).fill('Synthetic-demo-2026!')
 with p.expect_response(lambda r:':publish' in r.url) as r:p.get_by_role('button',name='Publish as second administrator').click()
 assert r.value.status==422,r.value.text()
 p.get_by_role('button',name='Sign out').click();p.get_by_role('button',name='ADM-01').click();expect(p.locator('#who')).to_contain_text('Tenant admin');p.goto('http://127.0.0.1:8080/#/config');select=p.get_by_label('Stored artifact version');expect(select.locator('option')).not_to_have_count(0);select.select_option(json.dumps(['POLCFG-ILL-INDEMNITY-A','2026.2.0'],separators=(',',':')));expect(p.get_by_label('Configuration JSON')).to_have_value(re.compile('.*2026.2.0.*',re.S))
 p.get_by_label('Publication password',exact=True).fill('Synthetic-demo-2026!')
 with p.expect_response(lambda r:':publish' in r.url) as r:p.get_by_role('button',name='Publish as second administrator').click()
 assert r.value.status==200,r.value.text();p.screenshot(path='evidence/2026-10-12/config-published.png',full_page=True);b.close();print('config UI: draft/validate/replay/self-publish blocked/second administrator publish passed')
