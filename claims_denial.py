from pathlib import Path

import pandas as pd
import streamlit as st


DATA_FILE = Path(__file__).resolve().parents[1] / "data" / "master" / "claims_master.csv"


def show_claims_denial():
    st.title("Claims & Denial Management")
    st.caption("Advanced US Healthcare Revenue Cycle Analytics | Shared synthetic data")

    try:
        df = pd.read_csv(DATA_FILE)
    except Exception as exc:
        st.error(f"Could not load the shared claims dataset: {exc}")
        return

    required = {"Claim_ID", "Payer", "Billed_Amount", "Paid_Amount", "Status",
                "Denial_Reason", "Days_Outstanding", "Outstanding_AR"}
    missing = required.difference(df.columns)
    if missing:
        st.error(f"Master claims file is missing columns: {', '.join(sorted(missing))}")
        return

    denied_df = df[df["Status"] == "Denied"].copy()

    st.subheader("1. Claims Performance")

    total_claims = len(df)
    denied = len(denied_df)
    pending = (df["Status"] == "Pending").sum()
    denial_rate = denied / total_claims * 100
    total_billed = df["Billed_Amount"].sum()
    total_paid = df["Paid_Amount"].sum()
    denied_amount = denied_df["Billed_Amount"].sum()
    reimbursement_rate = total_paid / total_billed * 100

    c1, c2, c3 = st.columns(3)
    c1.metric("Total Claims", total_claims)
    c2.metric("Denied Claims", denied)
    c3.metric("Pending Claims", int(pending))

    c4, c5, c6 = st.columns(3)
    c4.metric("Denial Rate", f"{denial_rate:.1f}%")
    c5.metric("Denied Claim Value", f"${denied_amount:,.2f}")
    c6.metric("Reimbursement Rate", f"{reimbursement_rate:.1f}%")

    st.divider()

    st.subheader("2. Denial Reasons")

    if not denied_df.empty:
        reason_summary = denied_df.groupby("Denial_Reason").agg(
            Denied_Claims=("Claim_ID", "count"),
            Financial_Impact=("Billed_Amount", "sum")
        ).sort_values("Financial_Impact", ascending=False)

        left, right = st.columns(2)

        with left:
            st.caption("Number of denials by reason")
            st.bar_chart(reason_summary["Denied_Claims"])

        with right:
            st.caption("Denied claim value by reason")
            st.bar_chart(reason_summary["Financial_Impact"])

        st.dataframe(reason_summary, use_container_width=True)

    st.divider()

    st.subheader("3. Payer-wise Performance")

    payer_summary = df.groupby("Payer").agg(
        Total_Claims=("Claim_ID", "count"),
        Denied_Claims=("Status", lambda x: (x == "Denied").sum()),
        Total_Billed=("Billed_Amount", "sum"),
        Total_Paid=("Paid_Amount", "sum"),
        Outstanding=("Outstanding_AR", "sum")
    ).reset_index()

    payer_summary["Denial_Rate"] = (
        payer_summary["Denied_Claims"] /
        payer_summary["Total_Claims"] * 100
    ).round(1)

    payer_summary["Collection_Rate"] = (
        payer_summary["Total_Paid"] /
        payer_summary["Total_Billed"] * 100
    ).round(1)

    left, right = st.columns(2)

    with left:
        st.caption("Denial rate by payer (%)")
        st.bar_chart(payer_summary.set_index("Payer")["Denial_Rate"])

    with right:
        st.caption("Outstanding AR by payer ($)")
        st.bar_chart(payer_summary.set_index("Payer")["Outstanding"])

    st.dataframe(payer_summary, use_container_width=True)

    st.divider()

    st.subheader("4. Claims Ageing & Follow-up Priorities")

    def priority(days):
        if days > 90:
            return "Critical"
        elif days > 60:
            return "High"
        elif days > 30:
            return "Medium"
        return "Normal"

    df["Priority"] = df["Days_Outstanding"].apply(priority)

    follow_up = df[
        (df["Outstanding_AR"] > 0) &
        (df["Days_Outstanding"] > 30)
    ].sort_values("Days_Outstanding", ascending=False)

    st.dataframe(
        follow_up[
            ["Claim_ID", "Payer", "Status", "Outstanding_AR",
             "Days_Outstanding", "Priority"]
        ],
        use_container_width=True
    )

    st.divider()

    st.subheader("5. Interactive Claim Filters")

    payer_filter = st.multiselect(
        "Select payer",
        sorted(df["Payer"].unique()),
        default=sorted(df["Payer"].unique())
    )

    status_filter = st.multiselect(
        "Select claim status",
        sorted(df["Status"].unique()),
        default=sorted(df["Status"].unique())
    )

    filtered = df[
        df["Payer"].isin(payer_filter) &
        df["Status"].isin(status_filter)
    ]

    st.metric("Filtered Claims", len(filtered))

    st.dataframe(filtered, use_container_width=True)

    csv = filtered.to_csv(index=False).encode("utf-8")

    st.download_button(
        "Download filtered claims CSV",
        data=csv,
        file_name="ledgerlens_claims_report.csv",
        mime="text/csv"
    )

    st.caption(
        "All records are synthetic. Denial rate is denied claims divided "
        "by total submitted claims. Denied claim value represents original "
        "billed charges, not confirmed collectible revenue. "
        "This is not a live billing system."
    )
