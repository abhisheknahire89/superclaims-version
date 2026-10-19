"""Sequential acceptance flows against a fresh seeded app; see README for the reset contract."""
import subprocess,sys
from pathlib import Path
root=Path(__file__).resolve().parents[1]
(root/'evidence/2026-10-12').mkdir(parents=True,exist_ok=True)
out=Path(sys.argv[1] if len(sys.argv)>1 else 'e2e-shots');out.mkdir(parents=True,exist_ok=True)
# Reviewer override changes the same second-approval claim used by smoke. Run it first;
# payable remains85000 so smoke still asserts the original second-approval path.
for name,args in [('reviewer_ui.py',[]),('ui_smoke.py',['http://127.0.0.1:8080',str(out)]),('manual_ui.py',[]),('operations_ui.py',[]),('workflow_ui.py',[]),('config_ui.py',[])]:
 print('Browser flow:',name,flush=True);subprocess.run([sys.executable,str(root/'tests'/name),*args],cwd=root,check=True)
