"""中文：验证格式指令剥离、时间分面和结构锚点加权检索。

English: Verify instruction stripping, temporal facets, and weighted structural-anchor retrieval.
"""

from __future__ import annotations

from pathlib import Path

from enterprise_rag.agent.question_planner import QuestionPlanner
from enterprise_rag.domain.models import RetrievalScope
from enterprise_rag.indexing.bm25_index import BM25IndexBuilder, PersistentBM25Index
from enterprise_rag.indexing.models import IndexBuildPlan, IndexEntry
from enterprise_rag.retrieval.query_features import plan_query_features


def test_named_source_instruction_is_removed_from_core_query() -> None:
    """中文：民法典来源提示应与真正的知识问题分离。

    English: Separate the Civil Code source hint from the actual knowledge question.
    """

    query = "自然人的民事权利能力从何时开始、何时终止？请依据民法典回答并给出引用。"
    features = plan_query_features(query)
    plan = QuestionPlanner().plan(query)

    assert features.core_query == "自然人的民事权利能力从何时开始、何时终止？"
    assert features.source_hint == "民法典"
    assert len(plan.needs) == 2
    assert "开始" in plan.needs[0].retrieval_query
    assert "终止" in plan.needs[1].retrieval_query


def test_exact_article_anchor_outranks_generic_lexical_overlap(tmp_path: Path) -> None:
    """中文：明确询问第八条时，结构命中必须高于大量普通词重叠。

    English: An exact Article 8 anchor must outrank broad ordinary-term overlap.
    """

    entries = (
        IndexEntry(
            "generic",
            "tenant-a",
            "source-a",
            "document-a",
            "version-a",
            "民事主体 民事活动 法律 公序良俗 第九条",
            lexical_text="民事主体 民事活动 法律 公序良俗 第九条",
            section_number="第九条",
        ),
        IndexEntry(
            "article-eight",
            "tenant-a",
            "source-a",
            "document-a",
            "version-a",
            "第八条 不得违背公序良俗",
            lexical_text="第八条 不得违背公序良俗",
            section_number="第八条",
        ),
    )
    plan = IndexBuildPlan(
        index_version_id="index-a",
        tenant_id="tenant-a",
        entries=entries,
        source_profiles=(),
        chunker_version="test-v5",
        embedding_fingerprint="fake",
        config_fingerprint="config",
    )
    BM25IndexBuilder().build(plan, tmp_path)
    index = PersistentBM25Index.load(tmp_path)

    rows = index.search(
        "民法典第八条规定了什么？",
        2,
        RetrievalScope("tenant-a", frozenset({"source-a"}), index_version_id="index-a"),
    )

    assert rows[0][0] == "article-eight"
