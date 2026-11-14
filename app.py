import os
import io
import hashlib
from pathlib import Path
from typing import List, Dict

import streamlit as st
from pypdf import PdfReader
from docx import Document as DocxDocument
from openpyxl import load_workbook

APP_DIR = Path(__file__).parent
DATA_DIR = APP_DIR / "data"
UPLOAD_DIR = DATA_DIR / "uploads"
CHROMA_DIR = DATA_DIR / "chroma"
for folder in (DATA_DIR, UPLOAD_DIR, CHROMA_DIR):
    folder.mkdir(parents=True, exist_ok=True)

st.set_page_config(page_title="LedgerLens | Tax & Accounting RAG", page_icon="📚", layout="wide")

DEFAULT_DOCS = {
    "sample_us_accounting_notes.txt": """LedgerLens sample reference — accounting basics
Source type: illustrative learning note; not authoritative professional guidance.

Accrual accounting recognises revenue when earned and expenses when incurred, subject to the applicable accounting framework. Cash-basis accounting generally records income and expenses when cash is received or paid. Accrual accounting may include accounts receivable, accounts payable, accrued expenses, and deferred revenue.

A common book entry to record periodic depreciation is Debit Depreciation Expense and Credit Accumulated Depreciation. Accumulated depreciation is a contra-asset account. Book depreciation and tax depreciation may differ, and the applicable accounting framework, tax rules, elections, asset class, placed-in-service date, and other facts must be checked.

Under the straight-line method, annual book depreciation is commonly calculated as (asset cost minus estimated residual value) divided by estimated useful life. This is an illustrative accounting formula and does not determine a tax deduction.
""",
    "sample_us_tax_workflow.txt": """LedgerLens sample reference — US tax research workflow
Source type: illustrative workflow note; not legal or tax advice.

For a US federal tax question, identify the taxpayer type, tax year, transaction date, accounting method, relevant facts, and whether the question concerns federal, state, or local tax. Prefer current primary sources such as the Internal Revenue Code, Treasury Regulations, IRS forms and instructions, and IRS publications. Confirm effective dates and whether a source is current for the relevant tax year.

Do not treat an old article or an AI-generated summary as authoritative. If the source set does not answer the question, say that evidence is insufficient and identify what needs to be checked. Keep a record of the source title, URL, publication or revision date, and relevant passage. State assumptions and recommend review by a qualified tax professional for material or uncertain positions.
""",
    "sample_us_itc_note.txt": """LedgerLens sample reference — general indirect tax note
Source type: non-US comparison note; included only as a retrieval test.

Input tax credit is a concept used in several value-added tax and goods-and-services tax systems. Eligibility, restrictions, documentation, reporting, and time limits depend on the specific jurisdiction and current law. Do not apply this concept as a US federal income tax rule. Always identify the tax jurisdiction before answering.
"""
}

def sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()[:16]

def read_uploaded_file(name: str, raw: bytes) -> str:
    suffix = Path(name).suffix.lower()
    if suffix == ".pdf":
        reader = PdfReader(io.BytesIO(raw))
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    if suffix == ".docx":
        doc = DocxDocument(io.BytesIO(raw))
        return "\n".join(p.text for p in doc.paragraphs)
    if suffix in (".txt", ".md", ".csv"):
        return raw.decode("utf-8", errors="replace")
    if suffix in (".xlsx", ".xlsm"):
        wb = load_workbook(io.BytesIO(raw), data_only=True, read_only=True)
        lines = []
        for ws in wb.worksheets:
            lines.append(f"Worksheet: {ws.title}")
            for row in ws.iter_rows(values_only=True):
                vals = [str(v) for v in row if v is not None]
                if vals:
                    lines.append(" | ".join(vals))
        return "\n".join(lines)
    raise ValueError("Unsupported file type. Upload PDF, DOCX, TXT, MD, CSV, XLSX, or XLSM.")

def chunk_text(text: str, chunk_size: int = 1100, overlap: int = 160) -> List[str]:
    clean = "\n".join(line.strip() for line in text.replace("\x00", " ").splitlines() if line.strip())
    if not clean:
        return []
    chunks, start = [], 0
    while start < len(clean):
        end = min(len(clean), start + chunk_size)
        if end < len(clean):
            boundary = clean.rfind(" ", start + int(chunk_size * .7), end)
            if boundary > start:
                end = boundary
        part = clean[start:end].strip()
        if part:
            chunks.append(part)
        if end >= len(clean):
            break
        start = max(end - overlap, start + 1)
    return chunks

@st.cache_resource(show_spinner=False)
def load_engine():
    """Lazy imports keep the app's error message useful if dependencies are missing."""
    from sentence_transformers import SentenceTransformer
    import chromadb
    model_name = os.getenv("LEDGERLENS_EMBED_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
    model = SentenceTransformer(model_name, device="cpu")
    client = chromadb.PersistentClient(path=str(CHROMA_DIR))
    collection = client.get_or_create_collection(
        name="ledgerlens_sources",
        metadata={"hnsw:space": "cosine"}
    )
    return model, collection

def ensure_seed_files():
    for name, content in DEFAULT_DOCS.items():
        path = UPLOAD_DIR / name
        if not path.exists():
            path.write_text(content, encoding="utf-8")

def get_docs() -> List[Path]:
    return sorted([p for p in UPLOAD_DIR.iterdir() if p.is_file() and p.suffix.lower() in
                   {".pdf", ".docx", ".txt", ".md", ".csv", ".xlsx", ".xlsm"}])

def index_file(path: Path, model, collection) -> int:
    raw = path.read_bytes()
    if path.suffix.lower() in (".txt", ".md", ".csv"):
        text = raw.decode("utf-8", errors="replace")
    else:
        text = read_uploaded_file(path.name, raw)
    pieces = chunk_text(text)
    if not pieces:
        return 0
    doc_id = sha(path.name + str(len(raw)) + hashlib.sha256(raw).hexdigest())
    ids = [f"{doc_id}_{i}" for i in range(len(pieces))]
    embeddings = model.encode(pieces, normalize_embeddings=True).tolist()
    metadatas = [{"source": path.name, "chunk": i + 1, "file_hash": doc_id} for i in range(len(pieces))]
    # Replace chunks from a previous version of this file.
    try:
        collection.delete(where={"source": path.name})
    except Exception:
        pass
    collection.add(ids=ids, documents=pieces, embeddings=embeddings, metadatas=metadatas)
    return len(pieces)

def indexed_sources(collection) -> Dict[str, int]:
    data = collection.get(include=["metadatas"])
    counts = {}
    for meta in data.get("metadatas") or []:
        if meta:
            counts[meta.get("source", "Unknown")] = counts.get(meta.get("source", "Unknown"), 0) + 1
    return counts

def retrieve(question: str, model, collection, k: int = 5):
    if collection.count() == 0:
        return []
    qvec = model.encode([question], normalize_embeddings=True).tolist()
    result = collection.query(query_embeddings=qvec, n_results=min(k, collection.count()), include=["documents", "metadatas", "distances"])
    hits = []
    docs = (result.get("documents") or [[]])[0]
    metas = (result.get("metadatas") or [[]])[0]
    dists = (result.get("distances") or [[]])[0]
    for doc, meta, distance in zip(docs, metas, dists):
        hits.append({"text": doc, "source": meta.get("source", "Unknown"), "chunk": meta.get("chunk", "?"),
                     "distance": float(distance) if distance is not None else None})
    return hits

def draft_answer(question: str, hits: List[Dict], api_key: str = "") -> str:
    if not hits:
        return "I could not retrieve a relevant passage from the indexed sources. Add a trusted source or rephrase the question. I will not invent a tax rule."
    if api_key.strip():
        try:
            from openai import OpenAI
            client = OpenAI(api_key=api_key.strip())
            context = "\n\n".join(f"[{i+1}] Source: {h['source']} (chunk {h['chunk']})\n{h['text']}" for i, h in enumerate(hits))
            response = client.responses.create(
                model=os.getenv("LEDGERLENS_OPENAI_MODEL", "gpt-4.1-mini"),
                instructions=("You are LedgerLens, a careful US accounting and tax research assistant. "
                    "Use only the supplied source excerpts for factual claims. If evidence is missing, say so. "
                    "Do not invent statutes, thresholds, citations, effective dates, or tax conclusions. "
                    "Separate accounting treatment from tax treatment, state assumptions, and flag when official current sources are needed. "
                    "This is informational support, not a substitute for professional tax advice. Cite sources as [1], [2], etc."),
                input=f"Question: {question}\n\nRetrieved source excerpts:\n{context}",
            )
            return response.output_text
        except Exception as e:
            return ("The AI API call failed, so I am showing retrieved evidence instead. "
                    f"Technical detail: {type(e).__name__}. Check your API key, network, model access, and package version.")
    return ("**Evidence-only mode (no AI API key configured).** I retrieved the following passages. "
            "Review them and formulate the conclusion only after checking the underlying authority.\n\n" +
            "\n\n".join(f"**[{i+1}] {h['source']} — chunk {h['chunk']}**\n{h['text']}" for i, h in enumerate(hits)))

ensure_seed_files()

st.markdown("""
<style>
.stApp{background:linear-gradient(135deg,#0b1020 0%,#111a2d 65%,#0b1020 100%);color:#edf2ff}
[data-testid="stSidebar"]{background:#10192b}
h1,h2,h3{letter-spacing:-.03em}
div[data-testid="stMetric"]{background:#172238;padding:12px;border-radius:12px;border:1px solid #2a3650}
</style>
""", unsafe_allow_html=True)


from modules.rcm_dashboard import show_rcm_dashboard
from modules.claims_denial import show_claims_denial
from modules.payment_reconciliation import show_payment_reconciliation

st.title("📚 LedgerLens")

st.divider()
workspace = st.selectbox(
    "Choose workspace",
    [
        "Tax & Accounting RAG",
        "RCM Analytics Dashboard",
        "Claims & Denial Management",
        "Payment Posting & Reconciliation"
    ]
)

if workspace == "RCM Analytics Dashboard":
    show_rcm_dashboard()
    st.stop()

if workspace == "Claims & Denial Management":
    show_claims_denial()
    st.stop()

if workspace == "Payment Posting & Reconciliation":
    show_payment_reconciliation()
    st.stop()


st.caption("US accounting & taxation · Local Streamlit RAG workspace")
st.info("Prototype status: this app performs local document ingestion, semantic retrieval, and source display. AI-generated answers are optional and require your own API key. Sample notes are learning examples, not authoritative tax guidance.")

with st.sidebar:
    st.header("Workspace settings")
    api_key = st.text_input("OpenAI API key (optional)", type="password", help="Used only when you submit a question. Do not paste a key into source files or share screenshots containing it.")
    st.caption("Without a key, LedgerLens runs in evidence-only mode.")
    top_k = st.slider("Retrieved passages", 2, 8, 5)
    st.divider()
    st.subheader("Index your documents")
    uploads = st.file_uploader("Upload source files", type=["pdf", "docx", "txt", "md", "csv", "xlsx", "xlsm"], accept_multiple_files=True)
    if st.button("Save uploads to workspace", use_container_width=True):
        if not uploads:
            st.warning("Choose one or more files first.")
        else:
            saved = 0
            for up in uploads:
                safe_name = Path(up.name).name
                (UPLOAD_DIR / safe_name).write_bytes(up.getvalue())
                saved += 1
            st.success(f"Saved {saved} file(s). Click “Build / refresh index” below.")
    index_clicked = st.button("Build / refresh index", type="primary", use_container_width=True)
    st.caption("Files and vector index are stored in this project folder under data/. Do not upload confidential client records to an unreviewed prototype.")
    st.divider()
    if st.button("Clear vector index", use_container_width=True):
        try:
            import chromadb
            client = chromadb.PersistentClient(path=str(CHROMA_DIR))
            try:
                client.delete_collection("ledgerlens_sources")
            except Exception:
                pass
            st.success("Index cleared. Rebuild it to add current files.")
            st.rerun()
        except Exception as e:
            st.error(f"Could not clear index: {e}")

# Engine loads only after dependencies are installed.
try:
    with st.spinner("Loading local embedding model (first launch may download it)…"):
        model, collection = load_engine()
except Exception as e:
    st.error("The retrieval engine could not start. Install requirements from the project folder, then restart Streamlit.")
    st.code("python -m pip install -r requirements.txt\npython -m streamlit run app.py")
    st.exception(e)
    st.stop()

if index_clicked:
    with st.spinner("Reading files and building semantic index…"):
        total = 0
        errors = []
        for path in get_docs():
            try:
                total += index_file(path, model, collection)
            except Exception as e:
                errors.append(f"{path.name}: {type(e).__name__}: {e}")
        if errors:
            st.warning("Some files could not be indexed:\n\n" + "\n".join(errors))
        st.success(f"Index refresh complete: {total} text chunks processed from {len(get_docs())} supported files.")
        st.rerun()

counts = indexed_sources(collection)
c1, c2, c3 = st.columns(3)
c1.metric("Indexed sources", len(counts))
c2.metric("Indexed passages", collection.count())
c3.metric("Answer mode", "AI + RAG" if api_key.strip() else "Evidence-only")

with st.expander("Current workspace files", expanded=False):
    for p in get_docs():
        st.write(f"• {p.name} · {p.stat().st_size:,} bytes")
    st.caption("Sample notes are created automatically on first run. To add sources, upload in the sidebar and save them.")

st.subheader("Ask LedgerLens")
question = st.text_area("Question", placeholder="Example: What facts should I collect before researching depreciation for a US business tax return?", height=90)
q1, q2, q3 = st.columns(3)
if q1.button("US tax research checklist"):
    question = "What facts and source checks should I collect before answering a US federal tax question?"
if q2.button("Book vs tax depreciation"):
    question = "How does book depreciation differ from tax depreciation?"
if q3.button("Cash vs accrual accounting"):
    question = "Explain the difference between cash-basis and accrual accounting."
submitted = st.button("Retrieve evidence and answer", type="primary")

if submitted:
    if not question.strip():
        st.warning("Enter a question first.")
    else:
        with st.spinner("Retrieving relevant source passages…"):
            hits = retrieve(question, model, collection, top_k)
        st.markdown("### Answer")
        st.markdown(draft_answer(question, hits, api_key))
        st.markdown("### Retrieved evidence")
        if not hits:
            st.warning("No relevant evidence retrieved. Add trusted reference material and rebuild the index.")
        for i, hit in enumerate(hits, start=1):
            distance = "n/a" if hit["distance"] is None else f"{hit['distance']:.3f}"
            with st.expander(f"[{i}] {hit['source']} · chunk {hit['chunk']} · distance {distance}", expanded=(i == 1)):
                st.write(hit["text"])
        st.caption("Semantic distance is a retrieval score, not a truth or legal-validity score. Confirm tax conclusions against current official sources.")

st.divider()
st.subheader("Prototype roadmap")
st.markdown("""
- **Implemented in this version:** local uploads (PDF, DOCX, TXT, MD, CSV, XLSX), text extraction, chunking, local sentence-transformer embeddings, persistent ChromaDB semantic retrieval, retrieved-passage display, and optional API-backed answer drafting.
- **Not implemented yet:** automatic verification against live IRS sources, state-tax coverage, authentication, multi-user access, production-grade encryption, audit logging, automated tax return preparation, or legal validation.
- **Next development milestone:** add official IRS source ingestion with source dates and URLs, better document-level citations, tests for retrieval quality, and clear federal/state/year filters.
""")
st.caption("LedgerLens is a learning prototype, not tax, legal, or accounting advice. Verify material decisions against current primary sources and a qualified professional.")
