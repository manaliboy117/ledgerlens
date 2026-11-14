import pandas as pd
from pathlib import Path

records = [
    ("CL001","Medicare",5000,4500,"Paid","None",15),
    ("CL002","Medicaid",8000,0,"Denied","Eligibility",45),
    ("CL003","Aetna",6000,6000,"Paid","None",20),
    ("CL004","UnitedHealthcare",10000,7000,"Partial","None",60),
    ("CL005","Medicare",4000,0,"Denied","Coding",75),
    ("CL006","Aetna",7000,5000,"Partial","None",35),
    ("CL007","Cigna",5500,0,"Denied","Authorization",90),
    ("CL008","Medicaid",9000,0,"Pending","None",25),
    ("CL009","UnitedHealthcare",6500,6000,"Partial","None",40),
    ("CL010","Medicare",7500,7500,"Paid","None",10),
    ("CL011","Aetna",4500,0,"Denied","Duplicate Claim",65),
    ("CL012","Cigna",8000,7000,"Partial","None",30),
    ("CL013","Medicaid",6000,4500,"Partial","None",50),
    ("CL014","UnitedHealthcare",9500,0,"Denied","Eligibility",100),
    ("CL015","Medicare",5000,4000,"Partial","None",55),
    ("CL016","Aetna",7000,0,"Pending","None",20),
    ("CL017","Cigna",8500,8500,"Paid","None",12),
    ("CL018","Medicaid",4000,0,"Denied","Coding",85),
    ("CL019","UnitedHealthcare",6500,5000,"Partial","None",45),
    ("CL020","Medicare",9000,8000,"Paid","None",18)
]

df = pd.DataFrame(records, columns=[
    "Claim_ID", "Payer", "Billed_Amount", "Paid_Amount",
    "Status", "Denial_Reason", "Days_Outstanding"
])

# Shared financial fields
df["Outstanding_AR"] = df["Billed_Amount"] - df["Paid_Amount"]
df["Allowed_Amount"] = (df["Billed_Amount"] * 0.80).round(2)
df["Patient_Responsibility"] = (df["Allowed_Amount"] * 0.10).round(2)
df["Expected_Payer_Payment"] = (
    df["Allowed_Amount"] - df["Patient_Responsibility"]
).round(2)

def ageing(days):
    if days <= 30:
        return "0-30 Days"
    if days <= 60:
        return "31-60 Days"
    if days <= 90:
        return "61-90 Days"
    return "90+ Days"

df["Ageing_Bucket"] = df["Days_Outstanding"].apply(ageing)

path = Path("data/master/claims_master.csv")
df.to_csv(path, index=False)

# Synthetic payment records linked to claim IDs
era = df.loc[df["Paid_Amount"] > 0, ["Claim_ID", "Payer", "Paid_Amount"]].copy()
era.insert(0, "Payment_Ref", [f"EFT-{i:03d}" for i in range(1, len(era)+1)])
era.rename(columns={"Paid_Amount": "Payer_Payment"}, inplace=True)
era.to_csv("data/master/era_payments.csv", index=False)

# Synthetic bank deposits: matching ERA payments plus one unidentified deposit
bank = era[["Payment_Ref", "Payer_Payment"]].copy()
bank.reset_index(drop=True, inplace=True)
bank.rename(columns={"Payer_Payment": "Deposit_Amount"}, inplace=True)
bank.loc[len(bank)] = ["BANK-999", 1200]
bank.to_csv("data/master/bank_deposits.csv", index=False)

print("Master dataset created.")
print("Claims:", len(df))
print("ERA records:", len(era))
print("Bank deposit records:", len(bank))
print("Files saved under data/master/")
