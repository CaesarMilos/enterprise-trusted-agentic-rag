"""中文：在 Child 精确命中后按证据 Token 预算安全扩展 Parent 上下文。

English: Safely expand parent context after precise child hits under an evidence-token budget.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace

from enterprise_rag.domain.models import Chunk
from enterprise_rag.retrieval.models import RetrievalCandidate


@dataclass(frozen=True, slots=True)
class ParentExpansionResult:
    """中文：保存每个 Child 对应的上下文块、展开 Parent 和最终正文 Token 数。

    English: Store child-to-context mapping, expanded parents, and final body-token usage.
    """

    contexts: Mapping[str, Chunk]
    expanded_parent_ids: tuple[str, ...]
    token_count: int


class ParentExpander:
    """中文：验证父子同租户、同文档、同版本关系后选择完整 Parent 或 Child 回退。

    English: Validate parent ownership/version and choose a full parent or child fallback.
    """

    def __init__(self, max_parent_tokens: int, context_token_budget: int) -> None:
        """中文：保存单 Parent 与整体证据包的硬 Token 上限。

        English: Store hard per-parent and complete evidence-pack token limits.
        """

        if not 1 <= max_parent_tokens <= context_token_budget:
            raise ValueError("parent token limit must fit within the context budget")
        self._max_parent_tokens = max_parent_tokens
        self._context_token_budget = context_token_budget

    def expand(
        self,
        tenant_id: str,
        candidates: tuple[RetrievalCandidate, ...],
        children: Mapping[str, Chunk],
        loader: Callable[[str, Sequence[str]], Sequence[Chunk]],
    ) -> ParentExpansionResult:
        """中文：按候选排名扩展一次 Parent，重复家族复用同一上下文且不重复计费。

        English: Expand each parent family once in rank order and avoid duplicate token charging.
        """

        parent_ids = tuple(
            dict.fromkeys(
                child.parent_chunk_id
                for candidate in candidates
                if (child := children.get(candidate.chunk_id)) is not None
                and child.parent_chunk_id is not None
            )
        )
        # 中文：同批读取 Parent 和相邻 Child，避免大 Parent 回退时只剩一个孤立块。
        # English: Load parents and adjacent children together so oversized parents can fall
        # back to a safe local window instead of one isolated child.
        neighbor_ids = tuple(
            dict.fromkeys(
                neighbor_id
                for candidate in candidates
                if (child := children.get(candidate.chunk_id)) is not None
                for neighbor_id in (child.previous_chunk_id, child.next_chunk_id)
                if neighbor_id is not None
            )
        )
        loaded = {chunk.id: chunk for chunk in loader(tenant_id, (*parent_ids, *neighbor_ids))}
        loaded_parents = {
            chunk_id: chunk for chunk_id, chunk in loaded.items() if chunk.chunk_level == "parent"
        }
        contexts: dict[str, Chunk] = {}
        chosen_parent_ids: list[str] = []
        charged_context_ids: set[str] = set()
        used_tokens = 0
        for candidate in candidates:
            child = children.get(candidate.chunk_id)
            if child is None:
                continue
            selected = child
            parent = loaded_parents.get(child.parent_chunk_id or "")
            if parent is not None and self._valid_parent(child, parent):
                if parent.token_count <= self._max_parent_tokens:
                    projected = used_tokens + (
                        0 if parent.id in charged_context_ids else parent.token_count
                    )
                    if projected <= self._context_token_budget:
                        selected = parent
            if selected is child:
                # 中文：局部窗口只合并同版本、同结构 Parent 和同硬边界的相邻块。
                # English: Local windows include only same-version, same-parent, same-hard-boundary
                # siblings.
                selected = self._local_window(child, loaded)
            charge = 0 if selected.id in charged_context_ids else selected.token_count
            if used_tokens + charge > self._context_token_budget:
                selected = child
                charge = 0 if child.id in charged_context_ids else child.token_count
            if used_tokens + charge > self._context_token_budget:
                continue
            contexts[child.id] = selected
            if selected.chunk_level == "parent" and selected.id not in chosen_parent_ids:
                chosen_parent_ids.append(selected.id)
            charged_context_ids.add(selected.id)
            used_tokens += charge
        return ParentExpansionResult(
            contexts=contexts,
            expanded_parent_ids=tuple(chosen_parent_ids),
            token_count=used_tokens,
        )

    @staticmethod
    def _valid_parent(child: Chunk, parent: Chunk) -> bool:
        """中文：验证 Parent 不会跨租户、资料源、文档或不可变版本扩展。

        English: Ensure parent expansion never crosses tenant, source, document, or version.
        """

        return (
            parent.chunk_level == "parent"
            and parent.tenant_id == child.tenant_id
            and parent.source_id == child.source_id
            and parent.document_id == child.document_id
            and parent.document_version_id == child.document_version_id
        )

    def _local_window(self, child: Chunk, loaded: Mapping[str, Chunk]) -> Chunk:
        """中文：构建“前一同级 + 命中 + 后一同级”的临时上下文块。

        English: Build an ephemeral previous-hit-next sibling context window.
        """

        siblings = [
            candidate
            for identifier in (child.previous_chunk_id, child.id, child.next_chunk_id)
            if (candidate := (child if identifier == child.id else loaded.get(identifier or "")))
            is not None
            and self._valid_sibling(child, candidate)
        ]
        if len(siblings) <= 1:
            return child
        total_tokens = sum(item.token_count for item in siblings)
        if total_tokens > self._max_parent_tokens:
            return child
        return replace(
            child,
            id=f"local-window:{child.id}",
            text="\n\n".join(item.text for item in siblings),
            retrieval_text="\n\n".join(item.search_text for item in siblings),
            token_count=total_tokens,
            page_start=min(
                (item.page_start for item in siblings if item.page_start is not None),
                default=child.page_start,
            ),
            page_end=max(
                (item.page_end for item in siblings if item.page_end is not None),
                default=child.page_end,
            ),
            chunk_level="local_window",
            metadata={
                **child.metadata,
                "local_window_chunk_ids": tuple(item.id for item in siblings),
            },
        )

    @staticmethod
    def _valid_sibling(child: Chunk, sibling: Chunk) -> bool:
        """中文：防止局部窗口跨租户、Source、文档、版本、Parent 或条款硬边界。

        English: Prevent local windows crossing tenant, source, document, version, parent, or
        hard structural boundaries.
        """

        same_identity = (
            sibling.chunk_level == "leaf"
            and sibling.tenant_id == child.tenant_id
            and sibling.source_id == child.source_id
            and sibling.document_id == child.document_id
            and sibling.document_version_id == child.document_version_id
            and sibling.parent_chunk_id == child.parent_chunk_id
        )
        if not same_identity:
            return False
        if child.hard_boundary_key is not None:
            return sibling.hard_boundary_key == child.hard_boundary_key
        return sibling.hard_boundary_key is None
