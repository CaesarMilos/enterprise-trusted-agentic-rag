"""中文：本模块负责实现“测试领域范围”相关功能。

English: Verify that retrieval authorization is applied as an exact pre-search scope.
"""

from __future__ import annotations

from enterprise_rag.domain.models import RetrievalScope, UserContext


def test_retrieval_scope_requires_tenant_source_and_optional_document_match() -> None:
    """中文：该测试用于验证“检索范围要求租户资料源并且可选文档匹配”相关行为。

    English: Ensure a candidate must satisfy every explicit scope dimension.
    """

    # 中文：变量 `scope` 用于保存“范围”相关数据；其精确定义与约束见下方英文说明。
    # English: Scope permits one document in one source and one tenant.
    scope = RetrievalScope(
        tenant_id="tenant-a",
        source_ids=frozenset({"source-a"}),
        document_ids=frozenset({"document-a"}),
        index_version_id="index-a",
    )

    assert scope.allows("tenant-a", "source-a", "document-a")
    assert not scope.allows("tenant-b", "source-a", "document-a")
    assert not scope.allows("tenant-a", "source-b", "document-a")
    assert not scope.allows("tenant-a", "source-a", "document-b")


def test_user_admin_role_is_explicit() -> None:
    """中文：该测试用于验证“用户管理员角色为`explicit`”相关行为。

    English: Ensure administration is derived only from trusted role membership.
    """

    # 中文：变量 `user` 用于保存“用户”相关数据；其精确定义与约束见下方英文说明。
    # English: Trusted context is expected to be created by the authentication adapter.
    user = UserContext(
        user_id="user-a",
        tenant_id="tenant-a",
        roles=frozenset({"admin"}),
    )

    assert user.is_admin()
