# LedgerLens — Accounting & Tax RAG + RCM Analytics

LedgerLens is a Streamlit learning prototype with four workspaces:
1. Tax & Accounting RAG
2. RCM Analytics Dashboard
3. Claims & Denial Management
4. Payment Posting & Reconciliation

All RCM workspaces read from one shared synthetic dataset in `data/master/`. The records are fictional and contain no patient identifiers.

## Run locally

Python 3.11 is recommended.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

Open the local URL printed by Streamlit, usually `http://localhost:8501`.

## Validate the synthetic financial data

From the project root:

```bash
python data/master/validate_financials.py
```

To regenerate the sample data:

```bash
python data/master/create_master_data.py
python data/master/validate_financials.py
```

Expected control totals for the included sample: 20 claims, $136,500 billed, $73,000 paid, $63,500 outstanding AR, 6 denied claims, $73,000 ERA payments, and $74,200 bank deposits including $1,200 unidentified cash.

## Test the RAG workspace

1. Select **Tax & Accounting RAG**.
2. In the sidebar, click **Build / refresh index**.
3. Wait for indexing to finish.
4. Ask a question covered by the sample notes, such as `How does book depreciation differ from tax depreciation?`
5. Inspect the retrieved source passages. Sample notes are educational examples, not authoritative tax sources.
6. Optional: supply an OpenAI API key in the sidebar to enable answer drafting. Do not hard-code or commit API keys.

## Deploy to Streamlit Community Cloud

1. Create a GitHub repository and upload the project files.
2. Ensure `requirements.txt`, `runtime.txt`, `app.py`, `modules/`, and `data/master/` are committed.
3. Do **not** commit `.venv/`, `.env`, API keys, confidential uploads, or a local Chroma database.
4. In Streamlit Community Cloud, create an app from the repository, select `app.py` as the main file, and deploy.
5. If using the optional OpenAI answer feature, add the key through Streamlit app secrets or use the password field in the app. Never place it in source code.

## Deployment limitations and security

- The first deployment may take several minutes because the local embedding model must be downloaded. Resource limits on a free hosted instance may affect model startup or responsiveness; successful deployment must be verified in the hosted environment.
- Hosted local files and the Chroma vector index may be ephemeral and can be lost when the instance restarts or is rebuilt. Re-upload source documents and rebuild the index as needed. The RCM demo CSVs are included in the repository and are read-only sample inputs.
- This is not a production healthcare or tax application. It has no authentication, role-based access, audit trail, HIPAA compliance assessment, encryption architecture, live payer/ERA/bank feeds, live IRS verification, or automated tax filing.
- Do not upload protected health information, confidential client tax records, or other sensitive data.
- Underpayment and overpayment comparisons use illustrative expected payer amounts from the synthetic sample and do not establish contractual liability.
- RAG retrieval scores are not measures of truth or legal validity. Verify material tax conclusions against current primary sources and a qualified professional.
