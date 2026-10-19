"""Workflow clocks are local, explicit and never automatically dispose a claim."""
from datetime import timedelta,datetime,timezone

def deadline(claim,cfg):
    rule=cfg.get('tat',{}).get(claim['workflow'],{})
    start=claim.get('submitted_at')
    if not start:return None
    if rule.get('due_minutes'):return start+timedelta(minutes=rule['due_minutes'])
    if rule.get('due_days'):return start+timedelta(days=rule['due_days'])
    return None

def breached(claim,cfg,now=None):
    due=deadline(claim,cfg)
    return bool(due and due<(now or datetime.now(timezone.utc)) and claim['status'] not in ('FINALISED','EXPORTED','WITHDRAWN'))
