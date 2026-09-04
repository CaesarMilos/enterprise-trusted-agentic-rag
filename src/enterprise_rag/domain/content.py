"""中文：定义跨文档类型复用的资料源内容契约与画像决策。

English: Define source content contracts and profile decisions reusable across document types.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from enterprise_rag.core.enums import (
    AuthorityPolicyMode,
    CanonicalContentProfile,
    ContentProfile,
    ContractEnforcementMode,
    ProfileMethod,
    ProfileMode,
    StructureType,
)
from enterprise_rag.core.ids import content_sha256


@dataclass(frozen=True, slots=True)
class AuthorityPolicy:
    """中文：限定系统可以采用的显式文档权威顺序。

    English: Restrict document authority ordering to explicitly configured policies.
    """

    mode: AuthorityPolicyMode = AuthorityPolicyMode.NONE
    explicit_priority: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        """中文：拒绝不完整或含重复值的权威顺序配置。

        English: Reject incomplete authority policies or duplicate priority entries.
        """

        if self.mode is AuthorityPolicyMode.NONE and self.explicit_priority:
            raise ValueError("authority priority requires explicit_priority mode")
        if self.mode is AuthorityPolicyMode.EXPLICIT_PRIORITY and not self.explicit_priority:
            raise ValueError("explicit authority policy requires at least one priority key")
        if len(set(self.explicit_priority)) != len(self.explicit_priority):
            raise ValueError("authority priority keys must be unique")


@dataclass(frozen=True, slots=True)
class SourceContract:
    """中文：保存资料源默认结构、画像模式与不匹配处置规则。

    English: Store a source's default structure, profile mode, and mismatch enforcement.
    """

    schema_version: str
    primary_profile: CanonicalContentProfile
    allowed_secondary_structures: frozenset[StructureType]
    profile_mode: ProfileMode
    enforcement_mode: ContractEnforcementMode
    language: str | None = None
    authority_policy: AuthorityPolicy = AuthorityPolicy()

    def __post_init__(self) -> None:
        """中文：校验内容契约的稳定字段和长度边界。

        English: Validate stable content-contract fields and bounded language metadata.
        """

        if not self.schema_version.strip():
            raise ValueError("source contract schema_version cannot be empty")
        if self.language is not None and (not self.language.strip() or len(self.language) > 32):
            raise ValueError("source contract language must contain 1-32 characters")


@dataclass(frozen=True, slots=True)
class ContentProfileAssessment:
    """中文：记录画像器产生的启发式结构判断，而非统计概率。

    English: Record a profiler's heuristic structural assessment rather than a probability.
    """

    predicted_profile: CanonicalContentProfile
    confidence: float
    profiler_version: str
    rule_fingerprint: str
    sample_characters: int
    detected_structures: frozenset[StructureType] = frozenset()
    reasons: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        """中文：校验启发式分数、样本数量和可复现指纹。

        English: Validate heuristic score, sample size, and reproducibility fingerprints.
        """

        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("profile confidence must be within [0, 1]")
        if self.sample_characters < 0:
            raise ValueError("profile sample size cannot be negative")
        if not self.profiler_version or not self.rule_fingerprint:
            raise ValueError("profile assessment requires profiler and rule fingerprints")


@dataclass(frozen=True, slots=True)
class ProfileDecision:
    """中文：冻结文档版本最终采用的画像及其可审计来源。

    English: Freeze the final profile selected for a version and its auditable origin.
    """

    selected_profile: CanonicalContentProfile
    method: ProfileMethod
    confidence: float | None
    mismatch: bool
    enforcement_mode: ContractEnforcementMode
    decision_reason: str
    assessment: ContentProfileAssessment | None = None

    def __post_init__(self) -> None:
        """中文：禁止把显式管理员配置伪装成模型高置信度判断。

        English: Prevent explicit administrator configuration from impersonating model confidence.
        """

        if self.method is ProfileMethod.CONTENT_PROFILER:
            if self.confidence is None or not 0.0 <= self.confidence <= 1.0:
                raise ValueError("content-profiler decisions require a valid confidence")
        elif self.confidence is not None:
            raise ValueError("only content-profiler decisions may carry confidence")
        if not self.decision_reason.strip():
            raise ValueError("profile decision reason cannot be empty")


def canonicalize_legacy_profile(
    legacy_profile: ContentProfile,
    explicit_subtype: CanonicalContentProfile | None = None,
) -> CanonicalContentProfile:
    """中文：以确定性规则将 V4 六类画像映射到 V5 通用结构画像。

    English: Deterministically map six V4 profiles to the generic V5 structural profiles.
    """

    if explicit_subtype is not None:
        if legacy_profile is not ContentProfile.MANUAL:
            raise ValueError("explicit profile subtype is only valid for legacy manual sources")
        if explicit_subtype not in {
            CanonicalContentProfile.SECTIONED_TECHNICAL_MANUAL,
            CanonicalContentProfile.PROCEDURE_GUIDE,
        }:
            raise ValueError("legacy manual subtype must be technical manual or procedure guide")
        return explicit_subtype
    if legacy_profile is ContentProfile.REGULATION:
        return CanonicalContentProfile.NUMBERED_RULE_DOCUMENT
    if legacy_profile in {ContentProfile.MANUAL, ContentProfile.TECHNICAL_DOC}:
        return CanonicalContentProfile.SECTIONED_TECHNICAL_MANUAL
    return CanonicalContentProfile.GENERAL_EXPOSITORY


def default_secondary_structures(
    profile: CanonicalContentProfile,
) -> frozenset[StructureType]:
    """中文：返回每个主画像允许出现的受控次级结构集合。

    English: Return the controlled secondary structures allowed for a primary profile.
    """

    mapping = {
        CanonicalContentProfile.NUMBERED_RULE_DOCUMENT: frozenset(
            {StructureType.DEFINITION, StructureType.EXCEPTION, StructureType.APPENDIX}
        ),
        CanonicalContentProfile.SECTIONED_TECHNICAL_MANUAL: frozenset(
            {
                StructureType.WARNING,
                StructureType.PARAMETER_TABLE,
                StructureType.TROUBLESHOOTING_ENTRY,
                StructureType.PROCEDURE_STEP,
                StructureType.APPENDIX,
            }
        ),
        CanonicalContentProfile.PROCEDURE_GUIDE: frozenset(
            {
                StructureType.PREREQUISITE,
                StructureType.PROCEDURE_STEP,
                StructureType.WARNING,
                StructureType.TROUBLESHOOTING_ENTRY,
            }
        ),
        CanonicalContentProfile.GENERAL_EXPOSITORY: frozenset(
            {StructureType.DEFINITION, StructureType.APPENDIX}
        ),
    }
    return mapping[profile]


def resolve_profile_decision(
    contract: SourceContract,
    assessment: ContentProfileAssessment | None,
    automatic_min_confidence: float,
    mismatch_confidence: float,
) -> ProfileDecision:
    """中文：按显式优先、自动阈值和保守回退规则解析最终画像。

    English: Resolve the final profile using explicit priority, thresholds, and safe fallback.
    """

    if not 0.0 <= automatic_min_confidence <= mismatch_confidence <= 1.0:
        raise ValueError("profile thresholds must satisfy 0 <= automatic <= mismatch <= 1")
    if contract.profile_mode is ProfileMode.EXPLICIT:
        mismatch = bool(
            assessment is not None
            and assessment.predicted_profile is not contract.primary_profile
            and assessment.confidence >= mismatch_confidence
        )
        return ProfileDecision(
            selected_profile=contract.primary_profile,
            method=ProfileMethod.SOURCE_EXPLICIT,
            confidence=None,
            mismatch=mismatch,
            enforcement_mode=contract.enforcement_mode,
            decision_reason=(
                "explicit_profile_mismatch" if mismatch else "source_explicit_profile"
            ),
            assessment=assessment,
        )
    if assessment is None or assessment.confidence < automatic_min_confidence:
        return ProfileDecision(
            selected_profile=CanonicalContentProfile.GENERAL_EXPOSITORY,
            method=ProfileMethod.FALLBACK,
            confidence=None,
            mismatch=False,
            enforcement_mode=contract.enforcement_mode,
            decision_reason="automatic_profile_low_confidence_fallback",
            assessment=assessment,
        )
    return ProfileDecision(
        selected_profile=assessment.predicted_profile,
        method=ProfileMethod.CONTENT_PROFILER,
        confidence=assessment.confidence,
        mismatch=False,
        enforcement_mode=contract.enforcement_mode,
        decision_reason="automatic_profile_selected",
        assessment=assessment,
    )


def source_contract_fingerprint(contract: SourceContract) -> str:
    """中文：对内容契约生成顺序无关、可复现的 SHA-256 指纹。

    English: Create an order-independent reproducible SHA-256 fingerprint for a contract.
    """

    # 中文：规范载荷排除创建时间等非确定性字段，只保留契约语义。
    # English: Canonical payload excludes timestamps and retains contract semantics only.
    payload = {
        "allowed_secondary_structures": sorted(
            structure.value for structure in contract.allowed_secondary_structures
        ),
        "authority_policy": {
            "explicit_priority": list(contract.authority_policy.explicit_priority),
            "mode": contract.authority_policy.mode.value,
        },
        "enforcement_mode": contract.enforcement_mode.value,
        "language": contract.language,
        "primary_profile": contract.primary_profile.value,
        "profile_mode": contract.profile_mode.value,
        "schema_version": contract.schema_version,
    }
    canonical = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return content_sha256(canonical)
