"""Distinct public identities and private-input interfaces; null always means UNKNOWN."""
from dataclasses import dataclass,field
from typing import Literal
@dataclass(frozen=True)
class Insurer:
 insurer_id:str;legal_name:str;official_domains:tuple[str,...];registration_number:str|None=None
@dataclass(frozen=True)
class InsuranceProduct:
 insurer_id:str;uin:str;marketing_names:tuple[str,...];status:str='UNKNOWN'
@dataclass(frozen=True)
class ProductRevision:
 insurer_id:str;uin:str;revision_hash:str;revision_label:str|None=None;wording_effective_from:str|None=None;wording_effective_to:str|None=None;review_required:bool=True
@dataclass(frozen=True)
class PolicyDocument:
 document_id:str;insurer_id:str;uin:str;kind:str
@dataclass(frozen=True)
class DocumentVersion:
 document_id:str;sha256:str;page_count:int;retrieved_at:str;url:str
@dataclass(frozen=True)
class SourceVerification:
 source_id:str;state:str;actor:str;identity_quote:str;revision_hash:str
@dataclass(frozen=True)
class Clause:
 source_id:str;sha256:str;page:int;identifier:str;quote:str;bbox:list|None=None
@dataclass(frozen=True)
class RuleCandidate:
 rule_id:str;clause:Clause;representation:dict;conditions:list;exceptions:list;dependencies:list;confidence:str;status:str='DRAFT'
@dataclass(frozen=True)
class RuleApproval:
 rule_id:str;author:str;reviewer:str;approver:str;interpretation:str
@dataclass(frozen=True)
class PolicyRuleMapping:
 rule_id:str;engine_rule_id:str;configuration_path:str;mode:str='SHADOW_ONLY'
@dataclass(frozen=True)
class MemberDataRequirement:
 issued_policy_evidence:str|None=None;insurer_id:str|None=None;uin:str|None=None;revision_hash:str|None=None;policy_period_start:str|None=None;policy_period_end:str|None=None;wording_effective_date:str|None=None;endorsement_effective_date:str|None=None;selected_options:list|None=None;group_variations:dict|None=None;endorsement_evidence:str|None=None
@dataclass(frozen=True)
class DynamicCoverageInformation:
 status:str|None=None;base_sum_insured:str|None=None;remaining_sum_insured:str|None=None;previous_claims:list|None=None;reservations:str|None=None;restoration_usage:str|None=None;benefit_utilisation:dict|None=None;authoritative_evidence:str|None=None;as_of:str|None=None
@dataclass(frozen=True)
class TariffDataRequirement:
 hospital_id:str|None=None;agreement_id:str|None=None;insurer_or_tpa:str|None=None;effective_from:str|None=None;effective_to:str|None=None;rates:dict|None=None;packages:list|None=None;room_limits:dict|None=None;authoritative_evidence:str|None=None
VERIFICATION_STATES=('POLICY_UNVERIFIED','POLICY_MATCHED','CONTRACT_INCOMPLETE','BENEFITS_UNVERIFIED','TARIFF_UNVERIFIED','FINANCIAL_REVIEW_REQUIRED','FINANCIAL_INPUTS_VERIFIED')
