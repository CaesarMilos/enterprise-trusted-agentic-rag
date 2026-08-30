"""中文：本模块将结构单元组装为自适应、分层、可引用且可复现的文本块。

English: Assemble structured units into adaptive, hierarchical, citable, and reproducible
chunks.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace

from enterprise_rag.core.ids import content_sha256, stable_chunk_id
from enterprise_rag.domain.models import Chunk
from enterprise_rag.ingestion.boundary_analyzer import (
    AdaptiveBoundaryAnalyzer,
    BoundaryDecision,
    BoundaryReviewBudget,
)
from enterprise_rag.ingestion.structure_parser import StructuredUnit, estimate_tokens

# 中文：切分超长单元时保留中英文词、数字与标点的原始字符跨度。
# English: Oversized-unit splitting preserves original spans for CJK, words, numbers, and marks.
_TOKEN_SPAN_PATTERN = re.compile(r"[\u3400-\u9fff]|[A-Za-z0-9_]+|[^\s]")


@dataclass(frozen=True, slots=True)
class ChunkingContext:
    """中文：冻结生成可引用 Chunk 所需的文档身份与资料源策略上下文。

    English: Freeze document identity and source-strategy context required for citable chunks.
    """

    # 中文：关键变量 `tenant_id` 是所有持久化和检索 ACL 的租户边界。
    # English: Key variable `tenant_id` is the tenant boundary for persistence and retrieval ACLs.
    tenant_id: str
    # 中文：关键变量 `source_id` 标识 Chunk 所属资料源。
    # English: Key variable `source_id` identifies the owning knowledge source.
    source_id: str
    # 中文：关键变量 `document_id` 标识跨版本稳定的逻辑文档。
    # English: Key variable `document_id` identifies the version-stable logical document.
    document_id: str
    # 中文：关键变量 `document_version_id` 标识本次不可变处理版本。
    # English: Key variable `document_version_id` identifies this immutable processing version.
    document_version_id: str
    # 中文：变量 `content_profile` 保存管理员选择的内容画像快照。
    # English: `content_profile` stores the administrator-selected profile snapshot.
    content_profile: str = "general_prose"
    # 中文：变量 `strategy_id` 保存实际执行的切块策略标识。
    # English: `strategy_id` stores the chunk strategy actually executed.
    strategy_id: str = "general-prose"


@dataclass(frozen=True, slots=True)
class _ChunkDraft:
    """中文：在稳定 ID 与邻接关系生成前保存一个完整 Chunk 草稿。

    English: Hold one complete chunk draft before stable IDs and adjacency are generated.
    """

    text: str
    retrieval_text: str
    token_count: int
    page_start: int | None
    page_end: int | None
    heading_path: tuple[str, ...]
    boundary_reason: str
    boundary_method: str
    boundary_confidence: float
    llm_attempted: bool
    fallback_reason: str | None
    similarity: float | None
    llm_calls_used: int
    unit_types: tuple[str, ...]
    section_number: str | None
    source_start_offset: int
    source_end_offset: int
    boundary_score: float | None = None
    boundary_threshold: float | None = None
    boundary_features: dict[str, float] | None = None
    overlap_text: str = ""
    chunk_level: str = "leaf"
    child_leaf_indexes: tuple[int, ...] = ()

    @property
    def parent_key(self) -> tuple[str, ...] | None:
        """中文：返回用于生成父块的稳定结构分组键。

        English: Return the stable structural grouping key used to create parent chunks.
        """

        if self.heading_path:
            return self.heading_path
        if self.section_number:
            return (self.section_number,)
        return None


class DynamicSemanticChunker:
    """中文：用自适应边界分析和父子层级生成可解释的确定性 Chunk。

    English: Create explainable deterministic chunks with adaptive boundary analysis and
    parent-child hierarchy.
    """

    def __init__(
        self,
        min_tokens: int,
        target_tokens: int,
        max_tokens: int,
        chunker_version: str,
        semantic_threshold: float = 0.52,
        hard_boundary_kinds: frozenset[str] = frozenset(),
        boundary_analyzer: AdaptiveBoundaryAnalyzer | None = None,
        create_parent_chunks: bool = True,
        max_llm_boundaries: int = 8,
    ) -> None:
        """中文：保存 Token 预算、算法版本和可注入的自适应边界分析器。

        English: Store token budgets, algorithm version, and an injectable adaptive analyzer.
        """

        if not 1 <= min_tokens <= target_tokens <= max_tokens:
            raise ValueError("chunk bounds must satisfy 1 <= min <= target <= max")
        if max_llm_boundaries < 0:
            raise ValueError("maximum LLM boundary calls cannot be negative")
        self._min_tokens = min_tokens
        self._target_tokens = target_tokens
        self._max_tokens = max_tokens
        self._chunker_version = chunker_version
        self._create_parent_chunks = create_parent_chunks
        # 中文：变量 `_max_llm_boundaries` 限制单文档模糊边界复核成本与延迟。
        # English: `_max_llm_boundaries` bounds ambiguous-boundary review cost per document.
        self._max_llm_boundaries = max_llm_boundaries
        # 中文：缺省分析器仍执行结构与词频语义判定，便于离线测试和降级。
        # English: The default analyzer retains structural and lexical-semantic behavior for
        # offline tests and graceful degradation.
        self._boundary_analyzer = boundary_analyzer or AdaptiveBoundaryAnalyzer(
            min_tokens=min_tokens,
            target_tokens=target_tokens,
            max_tokens=max_tokens,
            hard_boundary_kinds=hard_boundary_kinds,
            semantic_threshold=semantic_threshold,
        )

    def chunk(
        self,
        units: tuple[StructuredUnit, ...],
        context: ChunkingContext,
    ) -> tuple[Chunk, ...]:
        """中文：生成叶子块、可选父块、稳定 ID、邻接链与完整边界审计元数据。

        English: Generate leaves, optional parents, stable IDs, adjacency, and complete
        boundary-audit metadata.
        """

        bounded_units = tuple(
            split_unit for unit in units for split_unit in self._split_oversized_unit(unit)
        )
        # 中文：向量在循环前按文档批量生成并缓存，候选边界不再逐次调用提供方。
        # English: Vectors are batch-generated and cached before candidate-boundary iteration.
        self._boundary_analyzer.prepare(bounded_units)
        leaf_drafts: list[_ChunkDraft] = []
        buffer: list[StructuredUnit] = []
        buffer_tokens = 0
        # 中文：累积当前块内部发生的所有降级原因，避免 document_end 覆盖审计信息。
        # English: Accumulate in-chunk degradations so document_end cannot erase audit evidence.
        pending_fallbacks: list[str] = []
        # 中文：关键变量 `review_budget` 在真实请求前计数，坏 JSON 与异常无法绕过上限。
        # English: Key variable `review_budget` counts before provider calls, so invalid JSON
        # and failures cannot bypass the cap.
        review_budget = BoundaryReviewBudget(self._max_llm_boundaries)
        for unit in bounded_units:
            decision = self._boundary_analyzer.decide(
                buffer,
                buffer_tokens,
                unit,
                review_budget=review_budget,
            )
            if decision.fallback_reason and decision.fallback_reason not in pending_fallbacks:
                pending_fallbacks.append(decision.fallback_reason)
            if buffer and decision.should_split:
                leaf_drafts.append(
                    self._draft(
                        buffer,
                        replace(
                            decision,
                            fallback_reason=",".join(pending_fallbacks) or None,
                        ),
                    )
                )
                buffer = []
                buffer_tokens = 0
                pending_fallbacks = []
            buffer.append(unit)
            buffer_tokens += unit.token_count
        if buffer:
            leaf_drafts.append(
                self._draft(
                    buffer,
                    BoundaryDecision(
                        True,
                        "document_end",
                        1.0,
                        fallback_reason=",".join(pending_fallbacks) or None,
                        llm_calls_used=review_budget.used_calls,
                    ),
                )
            )

        # 中文：后处理只在同一父结构内合并微块，并以完整句子补充检索重叠。
        # English: Post-processing merges micro-chunks only within one parent and adds
        # sentence overlap.
        leaf_drafts = self._merge_short_drafts(leaf_drafts)
        leaf_drafts = self._apply_adaptive_overlap(leaf_drafts)

        parent_drafts = (
            self._build_parent_drafts(leaf_drafts) if self._create_parent_chunks else []
        )
        # 中文：叶子块保持源文顺序，父块追加在后，避免父块破坏相邻引用导航。
        # English: Leaves retain source order and parents append afterward so adjacency remains
        # citation-friendly.
        drafts = [*leaf_drafts, *parent_drafts]
        chunk_ids = tuple(
            stable_chunk_id(
                tenant_id=context.tenant_id,
                document_version_id=context.document_version_id,
                ordinal=ordinal,
                content_hash=content_sha256(draft.text),
                chunker_version=self._chunker_version,
            )
            for ordinal, draft in enumerate(drafts)
        )
        # 中文：叶子序号到父块 ID 的映射允许检索阶段按需扩展上下文。
        # English: Leaf-index-to-parent-ID mapping enables retrieval-time context expansion.
        parent_id_by_leaf: dict[int, str] = {}
        for parent_offset, parent in enumerate(parent_drafts, start=len(leaf_drafts)):
            for leaf_index in parent.child_leaf_indexes:
                parent_id_by_leaf[leaf_index] = chunk_ids[parent_offset]

        chunks: list[Chunk] = []
        for ordinal, draft in enumerate(drafts):
            is_leaf = draft.chunk_level == "leaf"
            unit_type = next(
                (kind for kind in draft.unit_types if kind not in {"prose", "heading"}),
                draft.unit_types[0] if draft.unit_types else "prose",
            )
            chunks.append(
                Chunk(
                    id=chunk_ids[ordinal],
                    tenant_id=context.tenant_id,
                    source_id=context.source_id,
                    document_id=context.document_id,
                    document_version_id=context.document_version_id,
                    ordinal=ordinal,
                    text=draft.text,
                    token_count=draft.token_count,
                    page_start=draft.page_start,
                    page_end=draft.page_end,
                    heading_path=draft.heading_path,
                    previous_chunk_id=(
                        chunk_ids[ordinal - 1] if is_leaf and ordinal > 0 else None
                    ),
                    next_chunk_id=(
                        chunk_ids[ordinal + 1]
                        if is_leaf and ordinal + 1 < len(leaf_drafts)
                        else None
                    ),
                    boundary_reason=draft.boundary_reason,
                    chunker_version=self._chunker_version,
                    content_hash=content_sha256(draft.text),
                    retrieval_text=draft.retrieval_text,
                    parent_chunk_id=parent_id_by_leaf.get(ordinal) if is_leaf else None,
                    chunk_level=draft.chunk_level,
                    unit_type=unit_type,
                    section_number=draft.section_number,
                    source_start_offset=draft.source_start_offset,
                    source_end_offset=draft.source_end_offset,
                    boundary_method=draft.boundary_method,
                    boundary_confidence=draft.boundary_confidence,
                    metadata={
                        "content_profile": context.content_profile,
                        "strategy_id": context.strategy_id,
                        "unit_types": list(draft.unit_types),
                        "child_leaf_indexes": list(draft.child_leaf_indexes),
                        "child_chunk_ids": [
                            chunk_ids[index] for index in draft.child_leaf_indexes
                        ],
                        "llm_attempted": draft.llm_attempted,
                        "llm_calls_used": draft.llm_calls_used,
                        "fallback_reason": draft.fallback_reason,
                        "boundary_similarity": draft.similarity,
                        "boundary_score": draft.boundary_score,
                        "boundary_threshold": draft.boundary_threshold,
                        "boundary_features": draft.boundary_features or {},
                        "overlap_text": draft.overlap_text,
                    },
                )
            )
        return tuple(chunks)

    def _merge_short_drafts(self, drafts: list[_ChunkDraft]) -> list[_ChunkDraft]:
        """中文：把过短块向右吸附；硬边界、父结构或角色不一致时保持独立。

        English: Attach short chunks rightward unless a hard boundary, parent, or role differs.
        """

        merged: list[_ChunkDraft] = []
        index = 0
        while index < len(drafts):
            current = drafts[index]
            if (
                current.token_count < self._min_tokens
                and index + 1 < len(drafts)
                and self._can_merge(current, drafts[index + 1])
            ):
                merged.append(self._merge_pair(current, drafts[index + 1]))
                index += 2
                continue
            if (
                current.token_count < self._min_tokens
                and merged
                and self._can_merge(merged[-1], current)
            ):
                merged[-1] = self._merge_pair(merged[-1], current)
            else:
                merged.append(current)
            index += 1
        return merged

    def _can_merge(self, left: _ChunkDraft, right: _ChunkDraft) -> bool:
        """中文：验证合并不会越过硬结构边界且不会超过 Token 硬上限。

        English: Verify merging crosses no hard boundary and remains below the token maximum.
        """

        hard_methods = {"structural_boundary", "heading_change", "max_tokens"}
        protected_roles = {"warning", "table", "code", "api_section"}
        left_roles = set(left.unit_types) & protected_roles
        right_roles = set(right.unit_types) & protected_roles
        return (
            left.boundary_method not in hard_methods
            and left.parent_key == right.parent_key
            and (not left_roles and not right_roles or left_roles == right_roles)
            and left.token_count + right.token_count <= self._max_tokens
        )

    @staticmethod
    def _merge_pair(left: _ChunkDraft, right: _ChunkDraft) -> _ChunkDraft:
        """中文：确定性拼接相邻草稿并继承右侧最终边界审计信息。

        English: Deterministically join adjacent drafts and inherit the right terminal boundary.
        """

        start_pages = [page for page in (left.page_start, right.page_start) if page is not None]
        end_pages = [page for page in (left.page_end, right.page_end) if page is not None]
        text = f"{left.text}\n\n{right.text}"
        return _ChunkDraft(
            text=text,
            retrieval_text=f"{left.retrieval_text}\n\n{right.retrieval_text}",
            token_count=estimate_tokens(text),
            page_start=min(start_pages) if start_pages else None,
            page_end=max(end_pages) if end_pages else None,
            heading_path=right.heading_path or left.heading_path,
            boundary_reason="short_chunk_merge",
            boundary_method=right.boundary_method,
            boundary_confidence=right.boundary_confidence,
            llm_attempted=left.llm_attempted or right.llm_attempted,
            fallback_reason=right.fallback_reason or left.fallback_reason,
            similarity=right.similarity,
            llm_calls_used=max(left.llm_calls_used, right.llm_calls_used),
            unit_types=tuple(dict.fromkeys((*left.unit_types, *right.unit_types))),
            section_number=right.section_number or left.section_number,
            source_start_offset=min(left.source_start_offset, right.source_start_offset),
            source_end_offset=max(left.source_end_offset, right.source_end_offset),
            boundary_score=right.boundary_score,
            boundary_threshold=right.boundary_threshold,
            boundary_features=right.boundary_features,
        )

    @staticmethod
    def _apply_adaptive_overlap(drafts: list[_ChunkDraft]) -> list[_ChunkDraft]:
        """中文：正文不重复，仅向下一块检索文本加入同父结构的上一完整句。

        English: Keep body text unique and add one prior complete sentence only to search text.
        """

        if len(drafts) < 2:
            return drafts
        result = [drafts[0]]
        for previous, current in zip(drafts, drafts[1:], strict=False):
            overlap = ""
            if (
                previous.parent_key == current.parent_key
                and previous.section_number == current.section_number
                and previous.boundary_method
                not in {"structural_boundary", "heading_change", "max_tokens"}
            ):
                sentences = tuple(
                    part.strip()
                    for part in re.split(r"(?<=[。！？!?；;])", previous.text)
                    if part.strip()
                )
                overlap = (sentences[-1] if sentences else previous.text)[-180:]
            result.append(
                replace(
                    current,
                    retrieval_text=(
                        f"上下文 / Previous context: {overlap}\n{current.retrieval_text}"
                        if overlap
                        else current.retrieval_text
                    ),
                    overlap_text=overlap,
                )
            )
        return result

    def _split_oversized_unit(self, unit: StructuredUnit) -> tuple[StructuredUnit, ...]:
        """中文：按原文跨度拆分超大单元，同时保留编号、标题、页码与位置元数据。

        English: Split an oversized unit by source spans while preserving identifiers,
        headings, pages, and offsets.
        """

        if unit.token_count <= self._max_tokens:
            return (unit,)
        matches = tuple(_TOKEN_SPAN_PATTERN.finditer(unit.text))
        if not matches:
            return (unit,)
        windows: list[StructuredUnit] = []
        for start in range(0, len(matches), self._max_tokens):
            selected = matches[start : start + self._max_tokens]
            local_start = selected[0].start()
            local_end = selected[-1].end()
            window = unit.text[local_start:local_end].strip()
            if not window:
                continue
            heading_prefix = " > ".join(unit.heading_path)
            retrieval_text = f"{heading_prefix}\n{window}" if heading_prefix else window
            windows.append(
                StructuredUnit(
                    text=window,
                    kind=unit.kind,
                    heading_path=unit.heading_path,
                    page_number=unit.page_number,
                    token_count=estimate_tokens(window),
                    protected=unit.protected,
                    section_number=unit.section_number,
                    retrieval_text=retrieval_text,
                    source_start_offset=unit.source_start_offset + local_start,
                    source_end_offset=unit.source_start_offset + local_end,
                )
            )
        return tuple(windows)

    @staticmethod
    def _draft(units: list[StructuredUnit], decision: BoundaryDecision) -> _ChunkDraft:
        """中文：把非空结构单元缓冲区转换成携带检索文本和来源位置的叶子草稿。

        English: Convert a non-empty structured-unit buffer into a leaf draft with retrieval
        text and source positions.
        """

        text = "\n\n".join(unit.text for unit in units)
        pages = [unit.page_number for unit in units if unit.page_number is not None]
        heading_path = max(
            (unit.heading_path for unit in units if unit.heading_path),
            key=len,
            default=(),
        )
        heading_prefix = " > ".join(heading_path)
        retrieval_body = "\n\n".join(unit.retrieval_text or unit.text for unit in units)
        retrieval_text = (
            retrieval_body
            if not heading_prefix or retrieval_body.startswith(heading_prefix)
            else f"{heading_prefix}\n{retrieval_body}"
        )
        unit_types = tuple(dict.fromkeys(unit.kind for unit in units))
        section_number = next(
            (
                unit.section_number
                for unit in units
                if unit.section_number and unit.kind == "numbered_clause"
            ),
            None,
        )
        if section_number is None:
            section_number = next(
                (unit.section_number for unit in units if unit.section_number),
                None,
            )
        return _ChunkDraft(
            text=text,
            retrieval_text=retrieval_text,
            token_count=estimate_tokens(text),
            page_start=min(pages) if pages else None,
            page_end=max(pages) if pages else None,
            heading_path=heading_path,
            boundary_reason=decision.method,
            boundary_method=decision.method,
            boundary_confidence=decision.confidence,
            llm_attempted=decision.llm_attempted,
            fallback_reason=decision.fallback_reason,
            similarity=decision.similarity,
            llm_calls_used=decision.llm_calls_used,
            unit_types=unit_types,
            section_number=section_number,
            source_start_offset=min(unit.source_start_offset for unit in units),
            source_end_offset=max(unit.source_end_offset for unit in units),
            boundary_score=decision.score,
            boundary_threshold=decision.threshold,
            boundary_features=decision.features,
        )

    def _build_parent_drafts(self, leaves: list[_ChunkDraft]) -> list[_ChunkDraft]:
        """中文：把同一结构路径下的连续叶子块合并为受 Token 上限约束的父上下文块。

        English: Merge consecutive leaves under one structural path into token-bounded parent
        context chunks.
        """

        parents: list[_ChunkDraft] = []
        group: list[tuple[int, _ChunkDraft]] = []
        group_key: tuple[str, ...] | None = None

        def flush() -> None:
            """中文：提交当前分组；单叶分组无需重复创建父块。

            English: Commit the current group; a single leaf does not need a duplicate parent.
            """

            nonlocal group
            if len(group) < 2:
                group = []
                return
            indexes = tuple(index for index, _draft in group)
            drafts = tuple(draft for _index, draft in group)
            parent_text = "\n\n".join(draft.text for draft in drafts)
            parent_retrieval = "\n\n".join(draft.retrieval_text for draft in drafts)
            start_pages = [draft.page_start for draft in drafts if draft.page_start is not None]
            end_pages = [draft.page_end for draft in drafts if draft.page_end is not None]
            parents.append(
                _ChunkDraft(
                    text=parent_text,
                    retrieval_text=parent_retrieval,
                    token_count=estimate_tokens(parent_text),
                    page_start=min(start_pages) if start_pages else None,
                    page_end=max(end_pages) if end_pages else None,
                    heading_path=drafts[0].heading_path,
                    boundary_reason="parent_aggregation",
                    boundary_method="parent_aggregation",
                    boundary_confidence=1.0,
                    llm_attempted=False,
                    fallback_reason=None,
                    similarity=None,
                    llm_calls_used=0,
                    unit_types=tuple(
                        dict.fromkeys(kind for draft in drafts for kind in draft.unit_types)
                    ),
                    section_number=drafts[0].section_number,
                    source_start_offset=min(draft.source_start_offset for draft in drafts),
                    source_end_offset=max(draft.source_end_offset for draft in drafts),
                    chunk_level="parent",
                    child_leaf_indexes=indexes,
                )
            )
            group = []

        for index, leaf in enumerate(leaves):
            next_key = leaf.parent_key
            projected_tokens = sum(draft.token_count for _idx, draft in group) + leaf.token_count
            if group and (next_key != group_key or projected_tokens > self._max_tokens):
                flush()
            if next_key is None:
                flush()
                group_key = None
                continue
            if not group:
                group_key = next_key
            group.append((index, leaf))
        flush()
        return parents
