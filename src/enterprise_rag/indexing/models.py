"""中文：本模块负责实现“模型”相关功能。

English: Define one immutable build plan shared by dense, lexical, and catalog indexes.
"""

from __future__ import annotations

from dataclasses import dataclass

from enterprise_rag.core.ids import content_sha256
from enterprise_rag.domain.models import Chunk, Source


@dataclass(frozen=True, slots=True)
class IndexEntry:
    """中文：该类用于表示或实现“索引条目（IndexEntry）”的职责。

    English: Represent one authorized-search metadata row aligned with a chunk.
    """

    # 中文：变量 `chunk_id` 用于保存“文本块标识符”相关数据；其精确定义与约束见下方英文说明。
    # English: Deterministic chunk identifier.
    chunk_id: str
    # 中文：变量 `tenant_id` 用于保存“租户标识符”相关数据；其精确定义与约束见下方英文说明。
    # English: Owning tenant identifier.
    tenant_id: str
    # 中文：变量 `source_id` 用于保存“资料源标识符”相关数据；其精确定义与约束见下方英文说明。
    # English: Parent source identifier.
    source_id: str
    # 中文：变量 `document_id` 用于保存“文档标识符”相关数据；其精确定义与约束见下方英文说明。
    # English: Logical document identifier.
    document_id: str
    # 中文：变量 `document_version_id` 用于保存“文档版本标识符”相关数据；
    # 其精确定义与约束见下方英文说明。
    # English: Immutable document-version identifier.
    document_version_id: str
    # 中文：变量 `text` 用于保存“文本”相关数据；其精确定义与约束见下方英文说明。
    # English: Text embedded and tokenized by index builders.
    text: str
    # 中文：关键变量 `embedding_text` 是专供 Dense 索引的有界正文优先文本。
    # English: Key variable `embedding_text` is bounded body-first input for dense indexing.
    embedding_text: str = ""
    # 中文：关键变量 `lexical_text` 是专供 BM25 的完整结构化文本。
    # English: Key variable `lexical_text` is complete structured input for BM25.
    lexical_text: str = ""
    # 中文：条款编号和硬边界键支持精确锚点检索及审计。
    # English: Section and hard-boundary identifiers support exact anchors and audits.
    section_number: str | None = None
    hard_boundary_key: str | None = None
    # 中文：正文指纹用于识别不同正文产生同一向量的表示塌缩。
    # English: Body fingerprint identifies vector collapse across distinct content.
    content_fingerprint: str = ""

    @property
    def dense_text(self) -> str:
        """中文：返回 Dense 输入，并兼容旧索引条目的单文本字段。

        English: Return dense input with backward compatibility for legacy single-text entries.
        """

        return self.embedding_text or self.text

    @property
    def keyword_text(self) -> str:
        """中文：返回 BM25 输入，并兼容旧索引条目的单文本字段。

        English: Return BM25 input with backward compatibility for legacy single-text entries.
        """

        return self.lexical_text or self.text


@dataclass(frozen=True, slots=True)
class SourceProfile:
    """中文：该类用于表示或实现“资料源资料源画像（SourceProfile）”的职责。

    English: Represent lightweight routable metadata for one knowledge source.
    """

    # 中文：变量 `source_id` 用于保存“资料源标识符”相关数据；其精确定义与约束见下方英文说明。
    # English: Stable source identifier.
    source_id: str
    # 中文：变量 `tenant_id` 用于保存“租户标识符”相关数据；其精确定义与约束见下方英文说明。
    # English: Owning tenant identifier.
    tenant_id: str
    # 中文：变量 `name` 用于保存“`name`”相关数据；其精确定义与约束见下方英文说明。
    # English: Human-readable source name.
    name: str
    # 中文：变量 `description` 用于保存“`description`”相关数据；
    # 其精确定义与约束见下方英文说明。
    # English: Searchable source description.
    description: str
    # 中文：变量 `profile_terms` 用于保存“资料源画像`terms`”相关数据；
    # 其精确定义与约束见下方英文说明。
    # English: Frequent terms derived from active source content.
    profile_terms: tuple[str, ...]
    # 中文：变量 `chunk_count` 用于保存“文本块`count`”相关数据；
    # 其精确定义与约束见下方英文说明。
    # English: Number of active chunks belonging to this source.
    chunk_count: int


@dataclass(frozen=True, slots=True)
class IndexBuildPlan:
    """中文：该类用于表示或实现“索引构建计划（IndexBuildPlan）”的职责。

    English: Freeze the exact content and fingerprints used by every index component.
    """

    # 中文：变量 `index_version_id` 用于保存“索引版本标识符”相关数据；
    # 其精确定义与约束见下方英文说明。
    # English: New immutable index version identifier.
    index_version_id: str
    # 中文：变量 `tenant_id` 用于保存“租户标识符”相关数据；其精确定义与约束见下方英文说明。
    # English: Owning tenant identifier.
    tenant_id: str
    # 中文：变量 `entries` 用于保存“`entries`”相关数据；其精确定义与约束见下方英文说明。
    # English: Chunk-aligned entries in deterministic order.
    entries: tuple[IndexEntry, ...]
    # 中文：变量 `source_profiles` 用于保存“资料源资料源画像”相关数据；
    # 其精确定义与约束见下方英文说明。
    # English: Source profiles derived from the same active content snapshot.
    source_profiles: tuple[SourceProfile, ...]
    # 中文：变量 `chunker_version` 用于保存“切块器版本”相关数据；
    # 其精确定义与约束见下方英文说明。
    # English: Chunker version represented by the entries.
    chunker_version: str
    # 中文：变量 `embedding_fingerprint` 用于保存“向量嵌入指纹”相关数据；
    # 其精确定义与约束见下方英文说明。
    # English: Embedding provider fingerprint.
    embedding_fingerprint: str
    # 中文：变量 `config_fingerprint` 用于保存“配置指纹”相关数据；
    # 其精确定义与约束见下方英文说明。
    # English: Complete reproducibility configuration fingerprint.
    config_fingerprint: str
    # 中文：这些字段是由同一个内存快照生成的审计输入。
    # English: These audit inputs derive from the same in-memory build snapshot.
    schema_version: str = "index-build-plan-v5"
    tokenizer_fingerprint: str = "unicode-codepoint-v1"
    normalizer_fingerprint: str = "query-normalizer-v1"
    chunk_strategy_id: str = "mixed"
    reranker_fingerprint: str = "not-part-of-index"
    content_profiles: tuple[str, ...] = ()
    child_content_hashes: tuple[tuple[str, str], ...] = ()
    parent_child_mapping_fingerprint: str = ""
    build_parameters_fingerprint: str = ""
    source_document_fingerprints: tuple[tuple[str, str], ...] = ()
    # 中文：索引文本策略版本用于阻止新旧文本通道静默混用。
    # English: Index-text strategy version prevents silent mixing of old and new channels.
    index_text_strategy_version: str = "index-text-v5.1"

    @classmethod
    def from_domain(
        cls,
        index_version_id: str,
        tenant_id: str,
        chunks: tuple[Chunk, ...],
        sources: tuple[Source, ...],
        chunker_version: str,
        embedding_fingerprint: str,
        config_fingerprint: str,
        embedding_text_max_tokens: int = 384,
        max_heading_depth: int = 2,
        max_heading_characters: int = 96,
    ) -> IndexBuildPlan:
        """中文：该函数或方法负责“从领域”相关处理。

        English: Create a deterministic plan from one transactionally read active snapshot.
        """

        # 中文：变量 `ordered_chunks` 用于保存“`ordered`文本块”相关数据；
        # 其精确定义与约束见下方英文说明。
        # English: Ordered chunks eliminate repository-order differences across rebuilds.
        # 中文：只有 Child/leaf 进入 BM25 与向量索引；Parent 仅在命中后按需扩展。
        # English: Only child/leaf chunks enter search indexes; parents expand after a hit.
        ordered_chunks = tuple(
            sorted(
                (chunk for chunk in chunks if chunk.chunk_level == "leaf"),
                key=lambda item: item.id,
            )
        )
        # 中文：变量 `entries` 用于保存“`entries`”相关数据；其精确定义与约束见下方英文说明。
        # English: Index entries copy ACL metadata so search can filter before returning
        #   candidates.
        from enterprise_rag.indexing.index_text_builder import IndexTextBuilder

        # 中文：关键变量 `text_builder` 为 Dense 与 BM25 构造不同文本通道。
        # English: Key variable `text_builder` creates distinct text channels for Dense and BM25.
        text_builder = IndexTextBuilder(
            embedding_max_tokens=embedding_text_max_tokens,
            max_heading_depth=max_heading_depth,
            max_heading_characters=max_heading_characters,
        )
        entries_list: list[IndexEntry] = []
        for chunk in ordered_chunks:
            text_payload = text_builder.build(chunk)
            entries_list.append(
                IndexEntry(
                    chunk_id=chunk.id,
                    tenant_id=chunk.tenant_id,
                    source_id=chunk.source_id,
                    document_id=chunk.document_id,
                    document_version_id=chunk.document_version_id,
                    # 中文：`text` 保留可引用正文；索引构建器读取各自专用文本通道。
                    # English: `text` retains citable body while builders read dedicated channels.
                    text=chunk.body_text,
                    embedding_text=text_payload.embedding_text,
                    lexical_text=text_payload.lexical_text,
                    section_number=chunk.section_number,
                    hard_boundary_key=chunk.hard_boundary_key,
                    content_fingerprint=text_payload.content_fingerprint,
                )
            )
        entries = tuple(entries_list)
        # 中文：变量 `text_by_source` 用于保存“文本`by`资料源”相关数据；
        # 其精确定义与约束见下方英文说明。
        # English: Active text by source feeds deterministic lightweight profile terms.
        text_by_source: dict[str, list[str]] = {}
        for entry in entries:
            text_by_source.setdefault(entry.source_id, []).append(entry.keyword_text)
        # 中文：变量 `profiles` 用于保存“资料源画像”相关数据；其精确定义与约束见下方英文说明。
        # English: Source profiles are sorted by identifier for stable manifests.
        profiles = tuple(
            SourceProfile(
                source_id=source.id,
                tenant_id=source.tenant_id,
                name=source.name,
                description=source.description,
                profile_terms=_frequent_terms(text_by_source.get(source.id, [])),
                chunk_count=len(text_by_source.get(source.id, [])),
            )
            for source in sorted(sources, key=lambda item: item.id)
            if source.tenant_id == tenant_id and source.id in text_by_source
        )
        parent_mapping = "\n".join(
            f"{chunk.id}:{chunk.parent_chunk_id or ''}"
            for chunk in sorted(chunks, key=lambda item: item.id)
        )
        # 中文：缺少原始文件字节时，源文档指纹明确由有序 Child 内容哈希派生。
        # English: When original bytes are outside the plan, source-document fingerprints are
        # explicitly derived from ordered child content hashes.
        hashes_by_version: dict[str, list[str]] = {}
        for chunk in ordered_chunks:
            hashes_by_version.setdefault(chunk.document_version_id, []).append(chunk.content_hash)
        return cls(
            index_version_id=index_version_id,
            tenant_id=tenant_id,
            entries=entries,
            source_profiles=profiles,
            chunker_version=chunker_version,
            embedding_fingerprint=embedding_fingerprint,
            config_fingerprint=config_fingerprint,
            chunk_strategy_id=chunker_version,
            content_profiles=tuple(sorted({source.content_profile.value for source in sources})),
            child_content_hashes=tuple((chunk.id, chunk.content_hash) for chunk in ordered_chunks),
            parent_child_mapping_fingerprint=content_sha256(parent_mapping),
            build_parameters_fingerprint=config_fingerprint,
            source_document_fingerprints=tuple(
                (version_id, content_sha256("\n".join(content_hashes)))
                for version_id, content_hashes in sorted(hashes_by_version.items())
            ),
            index_text_strategy_version=text_builder.strategy_version,
        )


def _frequent_terms(texts: list[str], limit: int = 32) -> tuple[str, ...]:
    """中文：该内部函数负责“高频词项”相关处理。

    English: Return deterministic high-frequency lowercase terms for source routing.
    """

    from collections import Counter

    from enterprise_rag.indexing.bm25_index import lexical_tokens

    # 中文：变量 `counts` 用于保存“`counts`”相关数据；其精确定义与约束见下方英文说明。
    # English: Counter spans only active chunks in the source.
    counts = Counter(term for text in texts for term in lexical_tokens(text) if len(term) > 1)
    return tuple(
        term for term, _ in sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:limit]
    )
