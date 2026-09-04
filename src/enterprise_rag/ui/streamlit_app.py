"""中文：本模块负责实现“`streamlit`应用”相关功能。

English: Provide a Streamlit client that communicates only through the public FastAPI API.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, cast

import httpx
import streamlit as st
from dotenv import load_dotenv

# 中文：UI 与 API 使用同一项目根 `.env`，显式系统环境变量仍优先。
# English: UI and API load the same project-root `.env`; explicit process variables still win.
_PROJECT_ROOT = Path(__file__).resolve().parents[3]
load_dotenv(_PROJECT_ROOT / ".env", override=False)

# 中文：变量 `API_BASE_URL` 用于保存“接口基础`url`”相关数据；其精确定义与约束见下方英文说明。
# English: API root is configurable for Docker and local development.
API_BASE_URL = os.getenv("ENTERPRISE_RAG_API_URL", "http://127.0.0.1:8000/api/v1").rstrip("/")
# 中文：变量 `DEMO_HEADERS` 用于保存“`demo``headers`”相关数据；
# 其精确定义与约束见下方英文说明。
# English: Demo headers are used only when the backend development profile enables demo
#   authentication.
DEMO_HEADERS = {
    "X-User-ID": os.getenv("ENTERPRISE_RAG_DEMO_USER", "demo-admin"),
    "X-Tenant-ID": os.getenv("ENTERPRISE_RAG_DEMO_TENANT", "demo-tenant"),
    "X-Roles": os.getenv("ENTERPRISE_RAG_DEMO_ROLES", "admin"),
}
# 中文：生产 UI 使用短期 JWT；配置后不再发送任何可伪造的 Demo 身份头。
# English: Production UI uses a short-lived JWT and sends no forgeable demo identity headers.
_ACCESS_TOKEN = os.getenv("ENTERPRISE_RAG_ACCESS_TOKEN", "").strip()
REQUEST_HEADERS = {"Authorization": f"Bearer {_ACCESS_TOKEN}"} if _ACCESS_TOKEN else DEMO_HEADERS


def _request(method: str, path: str, **kwargs: Any) -> dict[str, object] | list[object]:
    """中文：该内部函数负责“请求”相关处理。

    English: Call the backend with bounded timeout and display safe API failures.
    """

    try:
        # 中文：变量 `response` 用于保存“响应”相关数据；其精确定义与约束见下方英文说明。
        # English: Streamlit never imports database, index, or model internals.
        response = httpx.request(
            method,
            f"{API_BASE_URL}{path}",
            headers=REQUEST_HEADERS,
            timeout=90.0,
            **kwargs,
        )
        response.raise_for_status()
        return cast(dict[str, object] | list[object], response.json())
    except httpx.HTTPError as exc:
        st.error(f"Backend request failed: {exc}")
        return {}


def render_chat() -> None:
    """中文：该函数或方法负责“渲染问答”相关处理。

    English: Render evidence-grounded question answering and citation excerpts.
    """

    st.subheader("Trusted knowledge chat")
    # 中文：本步骤涉及查询，具体约束见下方英文说明。
    # English: Query is sent only when the form is submitted.
    with st.form("chat-form"):
        query = st.text_area("Question", height=120)
        submitted = st.form_submit_button("Ask")
    if submitted and query.strip():
        result = _request("POST", "/chat", json={"query": query})
        if isinstance(result, dict) and result.get("status") in {"answered", "partial"}:
            # 中文：关键变量 `answer_status` 区分完整与部分回答，避免 UI 把安全部分回答误报为失败。
            # English: Key variable `answer_status` distinguishes complete from partial output
            # so the UI does not misreport a safe partial answer as failure.
            answer_status = str(result.get("status"))
            st.caption(f"Trace ID: {result.get('trace_id', 'n/a')}")
            if answer_status == "partial":
                st.warning(
                    "Partial answer: one or more requested information needs remain unsupported."
                )
            st.markdown(str(result.get("answer", "")))
            missing_information = result.get("missing_information", [])
            if answer_status == "partial" and isinstance(missing_information, list):
                with st.expander("Missing information", expanded=True):
                    for missing in missing_information:
                        if isinstance(missing, dict):
                            st.write(
                                f"- {missing.get('description', missing.get('need_id'))} "
                                f"({missing.get('reason', 'unsupported')})"
                            )
            with st.expander("Verified citations", expanded=True):
                citations = result.get("citations", [])
                if not isinstance(citations, list):
                    citations = []
                for citation in citations:
                    if isinstance(citation, dict):
                        st.markdown(
                            f"**[{citation.get('citation_id')}] {citation.get('title')}**  \n"
                            f"Page: {citation.get('page_start') or 'n/a'}"
                        )
                        st.caption(str(citation.get("excerpt", "")))
        elif isinstance(result, dict):
            st.caption(f"Trace ID: {result.get('trace_id', 'n/a')}")
            st.warning(str(result.get("message", "The request was not answered.")))


def render_documents() -> None:
    """中文：该函数或方法负责“渲染文档”相关处理。

    English: Render document upload and durable-job acceptance.
    """

    st.subheader("Upload enterprise documents")
    # 中文：变量 `source_payload` 用于保存“资料源载荷”相关数据；
    # 其精确定义与约束见下方英文说明。
    # English: Sources are always discovered through the backend ACL boundary.
    source_payload = _request("GET", "/sources")
    sources = source_payload if isinstance(source_payload, list) else []
    source_names = {
        str(source.get("name")): str(source.get("source_id"))
        for source in sources
        if isinstance(source, dict)
    }
    if not source_names:
        st.info("Create or seed a knowledge source before uploading documents.")
        return
    selected_name = st.selectbox("Knowledge source", tuple(source_names))
    # 中文：V4 接收 PDF、Markdown 和 TXT；缺失文本层的页面必须由后端 OCR 补齐。
    # English: V4 accepts PDF, Markdown, and TXT; pages without text require backend OCR.
    uploaded = st.file_uploader(
        "PDF, Markdown, or TXT (maximum 50 MiB)",
        type=["pdf", "md", "txt"],
    )
    selected_source = next(
        (
            source
            for source in sources
            if isinstance(source, dict) and str(source.get("name")) == selected_name
        ),
        {},
    )
    if isinstance(selected_source, dict):
        st.caption(f"Content profile: {selected_source.get('content_profile', 'general_prose')}")
    if st.button("Upload") and uploaded is not None:
        # 中文：变量 `result` 用于保存“结果”相关数据；其精确定义与约束见下方英文说明。
        # English: Multipart request contains only original bytes and formal source ID.
        result = _request(
            "POST",
            "/documents",
            data={"source_id": source_names[selected_name]},
            files={"file": (uploaded.name, uploaded.getvalue(), uploaded.type)},
        )
        if isinstance(result, dict) and result.get("job_id"):
            st.success(f"Queued durable job {result['job_id']}")
            # 中文：会话状态仅保存最近一次上传标识，正文仍留在后端。
            # English: Session state stores only the latest upload identities; document content
            # remains on the backend.
            st.session_state["latest_document_id"] = str(result.get("document_id", ""))
            st.session_state["latest_job_id"] = str(result.get("job_id", ""))

    latest_document_id = str(st.session_state.get("latest_document_id", ""))
    latest_job_id = str(st.session_state.get("latest_job_id", ""))
    if latest_document_id and latest_job_id:
        st.markdown("#### Latest document processing status")
        if st.button("Refresh document and job status"):
            st.session_state["latest_document_status"] = _request(
                "GET", f"/documents/{latest_document_id}"
            )
            st.session_state["latest_job_status"] = _request(
                "GET", f"/documents/jobs/{latest_job_id}"
            )
        document_status = st.session_state.get("latest_document_status")
        job_status = st.session_state.get("latest_job_status")
        if isinstance(document_status, dict):
            st.write(
                {
                    "document_id": latest_document_id,
                    "document_status": document_status.get("status"),
                    "active_version_id": document_status.get("active_version_id"),
                    "quality_metrics": document_status.get("quality_metrics", {}),
                }
            )
        if isinstance(job_status, dict):
            st.write(
                {
                    "job_id": latest_job_id,
                    "job_type": job_status.get("job_type"),
                    "job_status": job_status.get("status"),
                    "attempt_count": job_status.get("attempt_count"),
                    "error_code": job_status.get("error_code"),
                }
            )
            if job_status.get("status") in {
                "failed",
                "needs_ocr",
                "needs_review",
            } and st.button("Retry latest ingestion"):
                retried = _request("POST", f"/documents/{latest_document_id}/retry")
                if isinstance(retried, dict) and retried.get("job_id"):
                    st.session_state["latest_job_id"] = str(retried["job_id"])
                    st.success(f"Queued retry job {retried['job_id']}")


def render_admin() -> None:
    """中文：该函数或方法负责“渲染管理员”相关处理。

    English: Render immutable index history and manual rebuild controls.
    """

    st.subheader("Source profiles and index administration")
    # 中文：管理员在资料源级显式选择内容画像，避免系统猜测文件业务类型。
    # English: Administrators explicitly choose source profiles instead of guessing content type.
    source_payload = _request("GET", "/sources")
    sources = source_payload if isinstance(source_payload, list) else []
    source_by_name = {
        str(source.get("name")): source for source in sources if isinstance(source, dict)
    }
    if source_by_name:
        with st.form("source-profile-form"):
            selected_name = st.selectbox("Knowledge source", tuple(source_by_name))
            selected_source = source_by_name[selected_name]
            # 中文：变量 `profile_options` 是 V4 正式支持的六种受控内容画像。
            # English: Profile options are the six controlled V4 content profiles.
            profile_options = (
                "general_prose",
                "manual",
                "technical_doc",
                "regulation",
                "academic",
                "narrative",
            )
            current_profile = str(selected_source.get("content_profile", "general_prose"))
            selected_profile = st.selectbox(
                "Content profile",
                profile_options,
                index=profile_options.index(current_profile)
                if current_profile in profile_options
                else 0,
            )
            update_profile = st.form_submit_button("Update content profile")
        if update_profile:
            result = _request(
                "PATCH",
                f"/sources/{selected_source.get('source_id')}/content-profile",
                json={"content_profile": selected_profile},
            )
            if isinstance(result, dict) and result.get("source_id"):
                if result.get("requires_reprocessing"):
                    st.success("Profile updated. Existing documents must be reprocessed.")
                else:
                    st.info("Profile unchanged. No document reprocessing is required.")
    confirm_rebuild = st.checkbox(
        "I understand this publishes a new immutable tenant index snapshot."
    )
    if st.button("Rebuild active index", disabled=not confirm_rebuild):
        result = _request("POST", "/indexes/rebuild")
        if isinstance(result, dict) and result.get("index_version_id"):
            st.success(f"Activated {result['index_version_id']}")
    indexes = _request("GET", "/indexes")
    if isinstance(indexes, list):
        st.dataframe(indexes, use_container_width=True)


def main() -> None:
    """中文：该函数或方法负责“执行当前模块的命令行入口”相关处理。

    English: Configure the page and render user and administrator tabs.
    """

    st.set_page_config(page_title="Enterprise Trusted RAG", layout="wide")
    st.title("Enterprise Trusted Agentic RAG")
    # 中文：本步骤涉及客户端、接口，具体约束见下方英文说明。
    # English: Each tab remains a pure HTTP client of FastAPI.
    chat_tab, documents_tab, admin_tab = st.tabs(["Chat", "Documents", "Admin"])
    with chat_tab:
        render_chat()
    with documents_tab:
        render_documents()
    with admin_tab:
        render_admin()


if __name__ == "__main__":
    main()
