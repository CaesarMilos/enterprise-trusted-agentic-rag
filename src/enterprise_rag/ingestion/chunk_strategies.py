"""中文：本模块按资料源内容画像选择并执行可复现的结构感知切块策略。

English: Select and execute reproducible structure-aware chunk strategies by source profile.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Protocol

from enterprise_rag.core.enums import ContentProfile
from enterprise_rag.domain.models import Chunk
from enterprise_rag.ingestion.boundary_analyzer import (
    AdaptiveBoundaryAnalyzer,
    LLMBoundaryJudge,
    SimilarityProvider,
)
from enterprise_rag.ingestion.semantic_chunker import ChunkingContext, DynamicSemanticChunker
from enterprise_rag.ingestion.structure_parser import StructuredUnit


class ChunkStrategy(Protocol):
    """中文：定义所有内容专用切块策略必须实现的稳定接口。

    English: Define the stable interface implemented by every profile-specific strategy.
    """

    strategy_id: str
    version: str
    content_profile: ContentProfile

    def chunk(
        self,
        units: tuple[StructuredUnit, ...],
        context: ChunkingContext,
    ) -> tuple[Chunk, ...]:
        """中文：将有序结构单元转换为可引用、可复现的 Chunk。

        English: Convert ordered structural units into citable deterministic chunks.
        """


@dataclass(frozen=True, slots=True)
class StructuralRule:
    """中文：描述一条将文本单元标记为业务结构类型的确定性规则。

    English: Describe one deterministic rule assigning a business structural role.
    """

    # 中文：匹配成功后写入 StructuredUnit.kind 的结构类型。
    # English: Structural kind written to StructuredUnit.kind after a match.
    kind: str
    # 中文：从单元开头匹配的已编译正则表达式。
    # English: Compiled expression matched from the beginning of a unit.
    pattern: re.Pattern[str]
    # 中文：受保护单元仅在超过硬 Token 上限时允许内部拆分。
    # English: Protected units split internally only when the hard token limit is exceeded.
    protected: bool = False


class ProfileChunkStrategy:
    """中文：使用内容专用结构规则增强单元，再委托确定性核心切块器组合。

    English: Enrich units with profile rules, then delegate assembly to the deterministic core.
    """

    def __init__(
        self,
        *,
        strategy_id: str,
        version: str,
        content_profile: ContentProfile,
        rules: tuple[StructuralRule, ...],
        hard_boundary_kinds: frozenset[str],
        min_tokens: int,
        target_tokens: int,
        max_tokens: int,
        semantic_threshold: float = 0.52,
        ambiguity_margin: float = 0.08,
        similarity_provider: SimilarityProvider | None = None,
        llm_judge: LLMBoundaryJudge | None = None,
        create_parent_chunks: bool = True,
        max_llm_boundaries: int = 8,
    ) -> None:
        """中文：保存不可变策略身份、结构规则与 Token 预算。

        English: Store immutable strategy identity, structural rules, and token budgets.
        """

        self.strategy_id = strategy_id
        self.version = version
        self.content_profile = content_profile
        # 中文：变量 `_rules` 按声明顺序匹配，强结构规则应放在通用规则之前。
        # English: Rules match in declaration order, with stronger signals first.
        self._rules = rules
        # 中文：核心切块器继续负责稳定 ID、邻接关系和硬长度限制。
        # English: Core chunker still owns stable IDs, adjacency, and hard size limits.
        # 中文：关键变量 `boundary_analyzer` 统一执行结构、向量和可选 LLM 边界判定。
        # English: Key variable `boundary_analyzer` unifies structural, embedding, and optional
        # LLM boundary decisions.
        boundary_analyzer = AdaptiveBoundaryAnalyzer(
            min_tokens=min_tokens,
            target_tokens=target_tokens,
            max_tokens=max_tokens,
            hard_boundary_kinds=hard_boundary_kinds,
            semantic_threshold=semantic_threshold,
            ambiguity_margin=ambiguity_margin,
            similarity_provider=similarity_provider,
            llm_judge=llm_judge,
        )
        self._chunker = DynamicSemanticChunker(
            min_tokens=min_tokens,
            target_tokens=target_tokens,
            max_tokens=max_tokens,
            chunker_version=version,
            semantic_threshold=semantic_threshold,
            hard_boundary_kinds=hard_boundary_kinds,
            boundary_analyzer=boundary_analyzer,
            create_parent_chunks=create_parent_chunks,
            max_llm_boundaries=max_llm_boundaries,
        )

    def chunk(
        self,
        units: tuple[StructuredUnit, ...],
        context: ChunkingContext,
    ) -> tuple[Chunk, ...]:
        """中文：分类结构单元并使用当前策略身份生成最终 Chunk。

        English: Classify structural units and create final chunks with this strategy identity.
        """

        # 中文：变量 `profiled_units` 保存结构标注结果，不修改解析器的原始输出。
        # English: Profiled units preserve parser output by creating enriched copies.
        profiled_units = self._profile_units(units)
        strategy_context = ChunkingContext(
            tenant_id=context.tenant_id,
            source_id=context.source_id,
            document_id=context.document_id,
            document_version_id=context.document_version_id,
            content_profile=self.content_profile.value,
            strategy_id=self.strategy_id,
        )
        return self._chunker.chunk(profiled_units, strategy_context)

    def _profile_units(
        self,
        units: tuple[StructuredUnit, ...],
    ) -> tuple[StructuredUnit, ...]:
        """中文：按规则标注标题、步骤、警告、参数或接口等业务结构。

        English: Label business structures such as headings, steps, warnings, parameters, or APIs.
        """

        # 中文：变量 `active_heading_path` 保存最近识别到的专用标题层级。
        # English: Active heading path tracks the most recently recognized profile heading.
        active_heading_path: tuple[str, ...] = ()
        # 中文：关键变量 `active_clause` 让条款后的分项继承同一父结构路径。
        # English: Key variable `active_clause` makes following sub-items inherit one parent path.
        active_clause: str | None = None
        profiled: list[StructuredUnit] = []
        for unit in units:
            matched_rule = next(
                (rule for rule in self._rules if rule.pattern.search(unit.text.strip())),
                None,
            )
            kind = matched_rule.kind if matched_rule is not None else unit.kind
            protected = unit.protected or (
                matched_rule.protected if matched_rule is not None else False
            )
            if kind == "heading":
                # 中文：标题文本限制长度后加入路径，避免整段异常文本污染元数据。
                # English: Bounded heading text prevents malformed long blocks polluting metadata.
                heading = unit.text.strip().replace("\n", " ")[:160]
                active_heading_path = unit.heading_path or (heading,)
                active_clause = None
            if kind == "numbered_clause":
                active_clause = unit.section_number or unit.text.strip()[:80]
            base_heading_path = active_heading_path or unit.heading_path
            heading_path = (
                base_heading_path + (active_clause,)
                if active_clause and active_clause not in base_heading_path
                else base_heading_path
            )
            heading_prefix = " > ".join(heading_path)
            retrieval_text = unit.retrieval_text or unit.text
            if heading_prefix and not retrieval_text.startswith(heading_prefix):
                retrieval_text = f"{heading_prefix}\n{retrieval_text}"
            profiled.append(
                StructuredUnit(
                    text=unit.text,
                    kind=kind,
                    heading_path=heading_path,
                    page_number=unit.page_number,
                    token_count=unit.token_count,
                    protected=protected,
                    section_number=unit.section_number,
                    retrieval_text=retrieval_text,
                    source_start_offset=unit.source_start_offset,
                    source_end_offset=unit.source_end_offset,
                )
            )
        return tuple(profiled)


class ChunkStrategyRegistry:
    """中文：根据 Source.content_profile 或受控覆盖项解析唯一切块策略。

    English: Resolve one chunk strategy from Source.content_profile or a controlled override.
    """

    def __init__(self, strategies: tuple[ChunkStrategy, ...]) -> None:
        """中文：校验策略标识和内容画像均不重复，再构建不可变查找表。

        English: Validate unique strategy/profile keys and build immutable lookup mappings.
        """

        # 中文：变量 `by_id` 支持管理员高级覆盖；`by_profile` 支持正常自动解析。
        # English: by_id supports advanced overrides; by_profile supports normal resolution.
        by_id = {strategy.strategy_id: strategy for strategy in strategies}
        by_profile = {strategy.content_profile: strategy for strategy in strategies}
        if len(by_id) != len(strategies) or len(by_profile) != len(strategies):
            raise ValueError("chunk strategies must have unique ids and content profiles")
        self._by_id = by_id
        self._by_profile = by_profile

    def resolve(
        self,
        content_profile: ContentProfile,
        strategy_override: str | None = None,
    ) -> ChunkStrategy:
        """中文：返回显式覆盖策略，否则返回内容画像的默认策略。

        English: Return the explicit override or the default strategy for the content profile.
        """

        if strategy_override is not None:
            try:
                return self._by_id[strategy_override]
            except KeyError as exc:
                raise ValueError(f"unknown chunk strategy override: {strategy_override}") from exc
        try:
            return self._by_profile[content_profile]
        except KeyError as exc:
            raise ValueError(f"no chunk strategy for profile: {content_profile.value}") from exc


def build_default_strategy_registry(
    min_tokens: int,
    target_tokens: int,
    max_tokens: int,
    similarity_provider: SimilarityProvider | None = None,
    llm_judge: LLMBoundaryJudge | None = None,
    semantic_threshold: float = 0.52,
    ambiguity_margin: float = 0.08,
    create_parent_chunks: bool = True,
    max_llm_boundaries: int = 8,
) -> ChunkStrategyRegistry:
    """中文：构建 V0.3 通用、说明书和技术文档三种自适应结构策略。

    English: Build the V0.3 generic, manual, and technical adaptive structure strategies.
    """

    # 中文：说明书规则保护安全警告、故障块、步骤与参数组。
    # English: Manual rules protect safety warnings, troubleshooting blocks, steps,
    #   and parameters.
    manual_rules = (
        StructuralRule(
            "warning",
            re.compile(r"^(?:警告|危险|注意|重要|WARNING|CAUTION|DANGER)", re.I),
            True,
        ),
        StructuralRule(
            "troubleshooting",
            re.compile(r"^(?:故障|错误|异常|问题|原因|解决方案|排查)"),
            True,
        ),
        StructuralRule(
            "heading",
            re.compile(
                r"^(?:第[一二三四五六七八九十百0-9]+[章节部分]|"
                r"\d+(?:\.\d+)*\s+|#{1,6}\s*)"
            ),
        ),
        StructuralRule(
            "step",
            re.compile(
                r"^(?:步骤\s*[一二三四五六七八九十0-9]+|"
                r"第[一二三四五六七八九十0-9]+步|\d+[.)、])"
            ),
            True,
        ),
        StructuralRule("parameter", re.compile(r"^(?:参数|规格|型号|额定|默认值|取值范围)"), True),
    )
    # 中文：技术文档规则保护接口、配置、代码和警告单元。
    # English: Technical-document rules protect APIs, configuration, code, and warning
    #   units.
    technical_rules = (
        StructuralRule(
            "warning",
            re.compile(r"^(?:警告|危险|注意|重要|WARNING|CAUTION|DANGER|NOTE)", re.I),
            True,
        ),
        StructuralRule(
            "api_section",
            re.compile(
                r"^(?:(?:GET|POST|PUT|PATCH|DELETE)\s+/|接口|API|端点|Endpoint)",
                re.I,
            ),
            True,
        ),
        StructuralRule(
            "heading",
            re.compile(
                r"^(?:#{1,6}\s*|\d+(?:\.\d+)*\s+|"
                r"第[一二三四五六七八九十百0-9]+章)"
            ),
        ),
        StructuralRule("config", re.compile(r"^[A-Za-z_][A-Za-z0-9_.-]*\s*[:=]"), True),
        StructuralRule("parameter", re.compile(r"^(?:参数|返回值|错误码|默认值|类型|必填)"), True),
    )
    strategies: tuple[ChunkStrategy, ...] = (
        ProfileChunkStrategy(
            strategy_id="general-prose",
            version="general-prose-v2",
            content_profile=ContentProfile.GENERAL_PROSE,
            rules=(),
            hard_boundary_kinds=frozenset({"heading", "numbered_clause"}),
            min_tokens=min_tokens,
            target_tokens=target_tokens,
            max_tokens=max_tokens,
            semantic_threshold=semantic_threshold,
            ambiguity_margin=ambiguity_margin,
            similarity_provider=similarity_provider,
            llm_judge=llm_judge,
            create_parent_chunks=create_parent_chunks,
            max_llm_boundaries=max_llm_boundaries,
        ),
        ProfileChunkStrategy(
            strategy_id="manual-structure",
            version="manual-structure-v2",
            content_profile=ContentProfile.MANUAL,
            rules=manual_rules,
            hard_boundary_kinds=frozenset(
                {
                    "heading",
                    "numbered_clause",
                    "warning",
                    "troubleshooting",
                    "step",
                    "parameter",
                }
            ),
            min_tokens=min_tokens,
            target_tokens=target_tokens,
            max_tokens=max_tokens,
            semantic_threshold=semantic_threshold,
            ambiguity_margin=ambiguity_margin,
            similarity_provider=similarity_provider,
            llm_judge=llm_judge,
            create_parent_chunks=create_parent_chunks,
            max_llm_boundaries=max_llm_boundaries,
        ),
        ProfileChunkStrategy(
            strategy_id="technical-document",
            version="technical-document-v2",
            content_profile=ContentProfile.TECHNICAL_DOC,
            rules=technical_rules,
            hard_boundary_kinds=frozenset(
                {
                    "heading",
                    "numbered_clause",
                    "warning",
                    "api_section",
                    "config",
                    "parameter",
                }
            ),
            min_tokens=min_tokens,
            target_tokens=target_tokens,
            max_tokens=max_tokens,
            semantic_threshold=semantic_threshold,
            ambiguity_margin=ambiguity_margin,
            similarity_provider=similarity_provider,
            llm_judge=llm_judge,
            create_parent_chunks=create_parent_chunks,
            max_llm_boundaries=max_llm_boundaries,
        ),
    )
    return ChunkStrategyRegistry(strategies)
