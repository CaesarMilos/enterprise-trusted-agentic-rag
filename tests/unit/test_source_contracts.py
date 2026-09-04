"""中文：验证旧画像迁移、显式优先和自动画像保守回退。

English: Verify legacy migration, explicit priority, and conservative auto-profile fallback.
"""

from enterprise_rag.core.enums import (
    CanonicalContentProfile,
    ContentProfile,
    ContractEnforcementMode,
    ProfileMethod,
    ProfileMode,
)
from enterprise_rag.domain.content import (
    ContentProfileAssessment,
    SourceContract,
    canonicalize_legacy_profile,
    default_secondary_structures,
    resolve_profile_decision,
    source_contract_fingerprint,
)


def _contract(mode: ProfileMode = ProfileMode.EXPLICIT) -> SourceContract:
    """中文：创建用于测试的法规型通用内容契约。

    English: Create a generic numbered-rule source contract for tests.
    """

    profile = CanonicalContentProfile.NUMBERED_RULE_DOCUMENT
    return SourceContract(
        schema_version="source-contract-v1",
        primary_profile=profile,
        allowed_secondary_structures=default_secondary_structures(profile),
        profile_mode=mode,
        enforcement_mode=ContractEnforcementMode.WARN,
        language="zh-CN",
    )


def test_legacy_profiles_map_without_document_specific_rules() -> None:
    """中文：迁移只映射通用结构，不引用民法典或任何特定文档。

    English: Migration maps generic structures without referring to a specific document.
    """

    assert canonicalize_legacy_profile(ContentProfile.REGULATION) is (
        CanonicalContentProfile.NUMBERED_RULE_DOCUMENT
    )
    assert canonicalize_legacy_profile(ContentProfile.MANUAL) is (
        CanonicalContentProfile.SECTIONED_TECHNICAL_MANUAL
    )
    assert canonicalize_legacy_profile(ContentProfile.ACADEMIC) is (
        CanonicalContentProfile.GENERAL_EXPOSITORY
    )


def test_explicit_profile_has_no_fake_confidence() -> None:
    """中文：管理员显式配置不得保存伪造的 1.0 置信度。

    English: Explicit administrator configuration may not store fake 1.0 confidence.
    """

    decision = resolve_profile_decision(_contract(), None, 0.70, 0.80)
    assert decision.method is ProfileMethod.SOURCE_EXPLICIT
    assert decision.confidence is None


def test_automatic_low_confidence_falls_back_to_general() -> None:
    """中文：低置信度自动判断必须回退为一般说明文本。

    English: Low-confidence automatic assessment must fall back to general exposition.
    """

    assessment = ContentProfileAssessment(
        CanonicalContentProfile.PROCEDURE_GUIDE,
        0.40,
        "profiler-v1",
        "rules-v1",
        5_000,
    )
    decision = resolve_profile_decision(_contract(ProfileMode.AUTOMATIC), assessment, 0.70, 0.80)
    assert decision.method is ProfileMethod.FALLBACK
    assert decision.selected_profile is CanonicalContentProfile.GENERAL_EXPOSITORY


def test_contract_fingerprint_ignores_set_order() -> None:
    """中文：次级结构集合顺序不得影响内容契约指纹。

    English: Secondary-structure set order must not affect the contract fingerprint.
    """

    left = _contract()
    right = SourceContract(
        schema_version=left.schema_version,
        primary_profile=left.primary_profile,
        allowed_secondary_structures=frozenset(reversed(tuple(left.allowed_secondary_structures))),
        profile_mode=left.profile_mode,
        enforcement_mode=left.enforcement_mode,
        language=left.language,
    )
    assert source_contract_fingerprint(left) == source_contract_fingerprint(right)
