from pathlib import Path

import pandas as pd
import streamlit as st


DATA_FILE = Path(__file__).resolve().parents[1] / "data" / "master" / "claims_master.csv"


def load_claims():
    if not DATA_FILE.exists():
        raise FileNotFoundError(
            f"Master claims file not found: {DATA_FILE}. "
            "Run data/master/create_master_data.py from the project folder."
        )
    df = pd.read_csv(DATA_FILE)
    required = {"Claim_ID", "Billed_Amount", "Paid_Amount", "Outstanding_AR", "Days_Outstanding", "Status"}
    missing = required.difference(df.columns)
    if missing:
        raise ValueError(f"Master claims file is missing columns: {', '.join(sorted(missing))}")
    return df


def show_rcm_dashboard():
    st.title("LedgerLens - RCM Analytics")
    st.caption("Healthcare Revenue Cycle Management | Shared synthetic claims dataset")

    try:
        df = load_claims()
    except Exception as exc:
        st.error(f"Could not load the shared claims dataset: {exc}")
        return

    total_billed = df["Billed_Amount"].sum()
    total_paid = df["Paid_Amount"].sum()
    total_ar = df["Outstanding_AR"].sum()
    collection_rate = (total_paid / total_billed * 100) if total_billed else 0

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total Claims", f"{len(df):,}")
    col2.metric("Total Billed", f"${total_billed:,.2f}")
    col3.metric("Total Collections", f"${total_paid:,.2f}")
    col4.metric("Outstanding AR", f"${total_ar:,.2f}")

    st.metric("Collection Rate", f"{collection_rate:.1f}%")
    st.divider()
    st.subheader("AR Ageing Analysis")

    if "Ageing_Bucket" not in df.columns:
        def ageing_bucket(days):
            if days <= 30:
                return "0-30 Days"
            if days <= 60:
                return "31-60 Days"
            if days <= 90:
                return "61-90 Days"
            return "90+ Days"
        df["Ageing_Bucket"] = df["Days_Outstanding"].apply(ageing_bucket)

    order = ["0-30 Days", "31-60 Days", "61-90 Days", "90+ Days"]
    ageing = (df.groupby("Ageing_Bucket")["Outstanding_AR"].sum()
                .reindex(order, fill_value=0))
    st.bar_chart(ageing)

    st.subheader("Claims Overview")
    st.dataframe(df, use_container_width=True, hide_index=True)
    st.caption("Synthetic demonstration data only. No real patient information or live payer feeds are used.")
