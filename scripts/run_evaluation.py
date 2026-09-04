"""中文：本模块负责实现“运行评估”相关功能。

English: Run the fixed evaluation suite against one pinned configured application.
"""

from __future__ import annotations

import argparse
import json

from enterprise_rag import __version__
from enterprise_rag.agent.prompts import PROMPT_VERSION
from enterprise_rag.api.dependencies import build_container
from enterprise_rag.core.ids import content_sha256
from enterprise_rag.domain.models import UserContext
from enterprise_rag.domain.requests import ChatCommand
from enterprise_rag.evaluation.dataset import load_dataset
from enterprise_rag.evaluation.runner import EvaluationPrediction, EvaluationRunner


def main() -> None:
    """中文：该函数或方法负责“执行当前模块的命令行入口”相关处理。

    English: Load a versioned dataset, run formal chat, and write reproducible reports.
    """

    # 中文：变量 `parser` 用于保存“解析器”相关数据；其精确定义与约束见下方英文说明。
    # English: CLI permits explicit dataset, output, tenant, and user scope.
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=str, default=None)
    parser.add_argument("--output-dir", type=str, default=None)
    parser.add_argument("--tenant-id", required=True)
    parser.add_argument("--source-ids", default="")
    # 中文：变量 `arguments` 用于保存“`arguments`”相关数据；其精确定义与约束见下方英文说明。
    # English: Parsed values are normalized into immutable evaluation configuration.
    arguments = parser.parse_args()
    container = build_container()
    settings = container.settings
    from pathlib import Path

    dataset_path = Path(arguments.dataset or settings.evaluation.dataset_path)
    output_dir = Path(arguments.output_dir or settings.evaluation.output_dir)
    dataset = load_dataset(dataset_path)
    user = UserContext(
        user_id="evaluation-runner",
        tenant_id=arguments.tenant_id,
        roles=frozenset({"admin"}),
        allowed_source_ids=frozenset(
            item.strip() for item in arguments.source_ids.split(",") if item.strip()
        ),
    )

    def predict(query: str) -> EvaluationPrediction:
        """中文：该函数或方法负责“预测”相关处理。

        English: Run formal chat and normalize selected citations for evaluation metrics.
        """

        result = container.chat.chat(ChatCommand(user=user, query=query))
        # 中文：即使最终拒答，也从内部 Trace 读取真实 Router 和排名输出。
        # English: Real router and ranking outputs remain available even when the final result
        # is a refusal.
        trace = result.retrieval_trace
        if trace is None:
            return EvaluationPrediction(result, (), ())
        return EvaluationPrediction(
            result=result,
            routed_source_ids=trace.routed_source_ids,
            retrieved_chunk_ids=tuple(item.chunk_id for item in trace.reranked),
            dense_chunk_ids=tuple(item.chunk_id for item in trace.dense),
            bm25_chunk_ids=tuple(item.chunk_id for item in trace.bm25),
            fused_chunk_ids=tuple(item.chunk_id for item in trace.fused),
            reranked_chunk_ids=tuple(item.chunk_id for item in trace.reranked),
        )

    # 中文：变量 `config_fingerprint` 用于保存“配置指纹”相关数据；
    # 其精确定义与约束见下方英文说明。
    # English: Configuration fingerprint excludes secret environment values by using
    #   validated settings.
    config_fingerprint = content_sha256(
        json.dumps(settings.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
    )
    runner = EvaluationRunner(
        predict,
        fingerprints={
            "config": config_fingerprint,
            "chunker": settings.ingestion.chunker_version,
            "embedding": settings.embedding.model,
            "llm": settings.llm.model,
            "prompt": PROMPT_VERSION,
            "code": __version__,
        },
        random_seed=settings.evaluation.random_seed,
    )
    report = runner.run(dataset, output_dir)
    print(
        f"Evaluated {len(dataset.examples)} example(s); "
        f"report={output_dir / 'evaluation_report.json'} "
        f"metrics={len(report['metrics'])}"
    )


if __name__ == "__main__":
    main()
