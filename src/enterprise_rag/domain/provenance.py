"""中文：定义从原始文件到规范化、切块和索引的可追溯处理记录。

English: Define traceable processing records from original files through indexing.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from enterprise_rag.core.ids import content_sha256


@dataclass(frozen=True, slots=True)
class DocumentProvenance:
    """中文：冻结文档版本的原始哈希和全部处理组件指纹。

    English: Freeze original hashes and all processing-component fingerprints for a version.
    """

    source_document_hash: str
    loader_fingerprint: str
    parser_fingerprint: str
    ocr_fingerprint: str | None
    normalizer_fingerprint: str
    structure_adapter_fingerprint: str
    chunk_strategy_fingerprint: str
    tokenizer_fingerprint: str
    embedding_fingerprint: str

    def __post_init__(self) -> None:
        """中文：要求所有必需处理阶段都有可审计指纹。

        English: Require auditable fingerprints for every mandatory processing stage.
        """

        required = (
            self.source_document_hash,
            self.loader_fingerprint,
            self.parser_fingerprint,
            self.normalizer_fingerprint,
            self.structure_adapter_fingerprint,
            self.chunk_strategy_fingerprint,
            self.tokenizer_fingerprint,
            self.embedding_fingerprint,
        )
        if any(not value for value in required):
            raise ValueError("document provenance requires all mandatory fingerprints")


def provenance_fingerprint(provenance: DocumentProvenance) -> str:
    """中文：计算处理来源记录的确定性 SHA-256 指纹。

    English: Compute a deterministic SHA-256 fingerprint for processing provenance.
    """

    payload = {field: getattr(provenance, field) for field in provenance.__dataclass_fields__}
    canonical = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return content_sha256(canonical)
