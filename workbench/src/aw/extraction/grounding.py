"""Grounding check (CAP-04 step 4, 07 §4): every extracted value must quote text that actually appears on the
cited page. A fact whose quote is not found is stored with grounding_check = NOT_FOUND and can never be used
by rules. This is the main defence against hallucinated values from any extraction provider."""
from __future__ import annotations

from .normalise import text_for_matching


def check(quote: str, page_text: str) -> str:
    if not quote or not quote.strip():
        return "NOT_FOUND"
    return "VERIFIED" if text_for_matching(quote) in text_for_matching(page_text) else "NOT_FOUND"


def verify_record(record: dict, pages: dict) -> str:
    """Check every quote/box and the value derivation, for all automatic providers."""
    import re
    from . import normalise as n
    for e in record['evidence']:
        page=pages.get(e['page']);box=e.get('bbox')
        if not page or check(e['quote'],page.text)!='VERIFIED' or not box or not (0<=box[0]<box[2]<=page.width and 0<=box[1]<box[3]<=page.height):
            return 'NOT_FOUND'
        matching=[ln for ln in page.lines if check(e['quote'],ln.get('source_quote',ln['text']))=='VERIFIED' or check(ln['text'],e['quote'])=='VERIFIED']
        if not any(box[0]<=ln['x1'] and box[2]>=ln['x0'] and box[1]<=ln['bottom'] and box[3]>=ln['top'] for ln in matching):
            return 'NOT_FOUND'
        quote=e['quote'];numbers=re.findall(r'\d[\d,]*(?:\.\d{1,2})?',quote)
        if 'path' in record:
            path=record['path'];raw=record['value'];value=record.get('normalised',raw)
            if path=='bill.is_itemised':
                tokens=set(re.findall(r'[a-z]+',quote.lower()))
                itemised=bool(tokens & {'itemised','itemized','detailed','itemisation','itemization'})
                if not isinstance(value,bool) or value!=itemised:return 'NOT_FOUND'
            elif path.endswith('.date') or path=='patient.dob':
                if n.to_date(str(raw))!=value or check(str(raw),quote)!='VERIFIED':return 'NOT_FOUND'
            elif path.endswith('.time'):
                if n.time_of_day(str(raw))!=value or check(str(raw),quote)!='VERIFIED':return 'NOT_FOUND'
            elif path=='patient.gender':
                if n.gender(str(raw))!=value or check(str(raw),quote)!='VERIFIED':return 'NOT_FOUND'
            elif path.startswith('bill.') and path in ('bill.total','bill.net_payable','bill.discount','bill.advance_paid'):
                if n.amount(str(raw))!=value or value not in [n.amount(v) for v in numbers]:return 'NOT_FOUND'
            elif path=='patient.age_years':
                if str(value) not in numbers:return 'NOT_FOUND'
            elif check(str(raw),quote)!='VERIFIED' or str(value).strip()!=str(raw).strip():return 'NOT_FOUND'
        else:
            if check(record['description'],quote)!='VERIFIED' or record['amount'] not in [n.amount(v) for v in numbers]:return 'NOT_FOUND'
            if record.get('unit_rate') and record['unit_rate'] not in [n.amount(v) for v in numbers]:return 'NOT_FOUND'
            if record.get('quantity') and record['quantity'] not in [n.quantity(v) for v in numbers]:return 'NOT_FOUND'
            if record.get('service_date') and n.to_date(quote)!=record['service_date']:return 'NOT_FOUND'
    return 'VERIFIED'
