from io import BytesIO
from pathlib import Path

import pandas as pd
import streamlit as st


DATA_DIR = Path(__file__).resolve().parents[1] / "data" / "master"


def load_payment_data():
    claims = pd.read_csv(DATA_DIR / "claims_master.csv")
    era = pd.read_csv(DATA_DIR / "era_payments.csv")
    bank = pd.read_csv(DATA_DIR / "bank_deposits.csv")

    required_claims = {"Claim_ID", "Payer", "Billed_Amount", "Paid_Amount",
                       "Allowed_Amount", "Patient_Responsibility",
                       "Expected_Payer_Payment", "Outstanding_AR"}
    missing = required_claims.difference(claims.columns)
    if missing:
        raise ValueError(f"Claims master is missing columns: {', '.join(sorted(missing))}")

    if not {"Payment_Ref", "Claim_ID", "Payer_Payment"}.issubset(era.columns):
        raise ValueError("ERA file must contain Payment_Ref, Claim_ID and Payer_Payment.")
    if not {"Payment_Ref", "Deposit_Amount"}.issubset(bank.columns):
        raise ValueError("Bank file must contain Payment_Ref and Deposit_Amount.")
    if not claims["Claim_ID"].is_unique:
        raise ValueError("Claim IDs in the master file must be unique.")
    if not era["Claim_ID"].is_unique:
        raise ValueError("This demonstration expects one ERA record per claim.")
    if not era["Payment_Ref"].is_unique or not bank["Payment_Ref"].is_unique:
        raise ValueError("Payment references must be unique in the ERA and bank files.")
    if not era["Claim_ID"].isin(claims["Claim_ID"]).all():
        raise ValueError("An ERA record refers to a claim absent from the claims master.")

    posted = claims.merge(
        era[["Payment_Ref", "Claim_ID", "Payer_Payment"]],
        on="Claim_ID", how="left", validate="one_to_one"
    )
    posted["Payer_Payment"] = posted["Payer_Payment"].fillna(0)
    posted["Match_Status"] = posted["Payment_Ref"].notna().map(
        {True: "Matched to ERA", False: "No ERA record"}
    )
    posted["Contractual_Adjustment"] = (
        posted["Billed_Amount"] - posted["Allowed_Amount"]
    ).clip(lower=0)
    has_era = posted["Payment_Ref"].notna()
    posted["Underpayment"] = float("nan")
    posted["Overpayment"] = float("nan")
    posted.loc[has_era, "Underpayment"] = (
        posted.loc[has_era, "Expected_Payer_Payment"]
        - posted.loc[has_era, "Payer_Payment"]
    ).clip(lower=0)
    posted.loc[has_era, "Overpayment"] = (
        posted.loc[has_era, "Payer_Payment"]
        - posted.loc[has_era, "Expected_Payer_Payment"]
    ).clip(lower=0)
    posted["Remaining_Expected_Payer_Balance"] = posted["Underpayment"]

    reconciliation = bank.merge(
        era[["Payment_Ref", "Claim_ID"]],
        on="Payment_Ref", how="left", indicator=True, validate="one_to_one"
    )
    reconciliation["Reconciliation_Status"] = reconciliation["_merge"].map({
        "both": "Matched", "left_only": "Unidentified Cash"
    })
    return claims, era, bank, posted, reconciliation


def show_payment_reconciliation():
    st.title("Payment Posting & Reconciliation")
    st.caption("Healthcare Payment Operations | Shared synthetic demonstration data")

    try:
        claims, era, bank, df, reconciliation = load_payment_data()
    except Exception as exc:
        st.error(f"Could not load payment data: {exc}")
        return

    matched_deposits = reconciliation.loc[
        reconciliation["_merge"] == "both", "Deposit_Amount"
    ].sum()
    unidentified_cash = reconciliation.loc[
        reconciliation["_merge"] == "left_only", "Deposit_Amount"
    ].sum()
    total_era = era["Payer_Payment"].sum()
    total_deposits = bank["Deposit_Amount"].sum()

    st.subheader("1. Payment Posting Summary")
    c1, c2, c3 = st.columns(3)
    c1.metric("ERA Payments", f"${total_era:,.2f}")
    c2.metric("Bank Deposits", f"${total_deposits:,.2f}")
    c3.metric("Unidentified Cash", f"${unidentified_cash:,.2f}")

    c4, c5, c6 = st.columns(3)
    c4.metric("Contractual Adjustments", f"${df['Contractual_Adjustment'].sum():,.2f}")
    c5.metric("Illustrative Underpayment", f"${df['Underpayment'].sum():,.2f}")
    c6.metric("Outstanding AR (Billed less paid)", f"${claims['Outstanding_AR'].sum():,.2f}")

    st.divider()
    st.subheader("2. ERA/EOB Claim Matching")
    st.dataframe(df[[
        "Claim_ID", "Payer", "Billed_Amount", "Allowed_Amount",
        "Patient_Responsibility", "Expected_Payer_Payment",
        "Payer_Payment", "Match_Status"
    ]], use_container_width=True, hide_index=True)

    st.divider()
    st.subheader("3. Contractual Adjustment Analysis")
    st.bar_chart(df.groupby("Payer")["Contractual_Adjustment"].sum())

    st.divider()
    st.subheader("4. Underpayment & Overpayment Detection")
    underpaid = df[df["Underpayment"] > 0].copy()
    overpaid = df[df["Overpayment"] > 0].copy()
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("**Illustrative underpayments**")
        st.metric("Number of Claims", len(underpaid))
        st.dataframe(underpaid[[
            "Claim_ID", "Payer", "Expected_Payer_Payment",
            "Payer_Payment", "Underpayment"
        ]], use_container_width=True, hide_index=True)
    with col2:
        st.markdown("**Illustrative overpayments**")
        st.metric("Number of Claims", len(overpaid))
        st.dataframe(overpaid[[
            "Claim_ID", "Payer", "Expected_Payer_Payment",
            "Payer_Payment", "Overpayment"
        ]], use_container_width=True, hide_index=True)

    st.divider()
    st.subheader("5. Bank Deposit Reconciliation")
    st.metric("Matched Bank Deposits", f"${matched_deposits:,.2f}")
    st.dataframe(reconciliation.drop(columns=["_merge"]), use_container_width=True, hide_index=True)
    if unidentified_cash > 0:
        st.warning(
            f"${unidentified_cash:,.2f} in deposits could not be matched to an ERA payment reference. "
            "Investigate before posting."
        )

    st.divider()
    st.subheader("6. Download Reconciliation Report")
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="Payment Posting", index=False)
        underpaid.to_excel(writer, sheet_name="Underpayments", index=False)
        overpaid.to_excel(writer, sheet_name="Overpayments", index=False)
        reconciliation.drop(columns=["_merge"]).to_excel(
            writer, sheet_name="Bank Reconciliation", index=False
        )
    st.download_button(
        "Download Excel Reconciliation Report",
        data=output.getvalue(),
        file_name="LedgerLens_Payment_Reconciliation.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    st.caption(
        "Synthetic demonstration data only. Expected payer payment is calculated as allowed amount "
        "less patient responsibility. Underpayment and overpayment flags are illustrative and do not "
        "establish contractual liability. Underpayment/overpayment comparisons are performed only "
        "for claims with a matched ERA record. Outstanding AR is shown as billed charges less posted "
        "payments. No real ERA/EOB or bank feeds are connected."
    )
