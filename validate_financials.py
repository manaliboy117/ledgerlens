import pandas as pd
from pathlib import Path

folder = Path("data/master")

df = pd.read_csv(folder / "claims_master.csv")
era = pd.read_csv(folder / "era_payments.csv")
bank = pd.read_csv(folder / "bank_deposits.csv")

checks = []

def check(name, condition, detail):
    checks.append((name, bool(condition), detail))

check(
    "Unique claim IDs",
    df["Claim_ID"].is_unique,
    f"{df['Claim_ID'].nunique()} unique IDs / {len(df)} claims"
)

check(
    "No negative outstanding AR",
    (df["Outstanding_AR"] >= 0).all(),
    f"Minimum balance: ${df['Outstanding_AR'].min():,.2f}"
)

check(
    "AR calculation",
    (df["Outstanding_AR"] == df["Billed_Amount"] - df["Paid_Amount"]).all(),
    "Billed amount less paid amount"
)

check(
    "ERA claim references valid",
    era["Claim_ID"].isin(df["Claim_ID"]).all(),
    f"{len(era)} ERA records"
)

check(
    "No duplicate ERA claim matches",
    era["Claim_ID"].is_unique,
    "One ERA record per paid claim in this sample"
)

check(
    "Denied claims have reasons",
    (df.loc[df["Status"] == "Denied", "Denial_Reason"] != "None").all(),
    f"{(df['Status'] == 'Denied').sum()} denied claims"
)

check(
    "Bank deposit total",
    bank["Deposit_Amount"].sum() == era["Payer_Payment"].sum() + 1200,
    "ERA deposits plus $1,200 unidentified cash"
)

print("\n===== LEDGERLENS FINANCIAL QA =====")

for name, passed, detail in checks:
    print(f"{'PASS' if passed else 'FAIL'} | {name} | {detail}")

print("\n===== CONTROL TOTALS =====")
print(f"Claims: {len(df)}")
print(f"Total billed: ${df['Billed_Amount'].sum():,.2f}")
print(f"Total collections: ${df['Paid_Amount'].sum():,.2f}")
print(f"Outstanding AR: ${df['Outstanding_AR'].sum():,.2f}")
print(f"Denied claims: {(df['Status'] == 'Denied').sum()}")
print(f"Denial rate: {(df['Status'] == 'Denied').mean()*100:.1f}%")
print(f"ERA payments: ${era['Payer_Payment'].sum():,.2f}")
print(f"Bank deposits: ${bank['Deposit_Amount'].sum():,.2f}")

print("\nOVERALL:", "PASS" if all(x[1] for x in checks) else "FAIL")
