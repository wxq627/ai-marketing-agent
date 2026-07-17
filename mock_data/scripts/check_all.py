"""全面检查 mock_data 所有文件完整性和一致性"""
import os, json, glob, sys, pandas as pd

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
errors = []

print("=" * 60)
print("1. DIRECTORY STRUCTURE")
print("=" * 60)
for d in ["structured", "unstructured", "scripts",
          "unstructured/asr_transcripts", "unstructured/product_docs", "unstructured/posters"]:
    ok = os.path.isdir(os.path.join(BASE, d))
    print(f"  {'OK' if ok else 'MISSING'}: {d}/")
    if not ok:
        errors.append(f"Missing dir: {d}")

print("\n" + "=" * 60)
print("2. STRUCTURED DATA FILES")
print("=" * 60)
expected = {
    "customer_basic.csv": ["cust_id","name","gender","age","city","occupation","income_level","education","id_card","phone","register_date"],
    "credit_card.csv": ["card_no","cust_id","card_level","credit_amount","open_date","card_status","product_id","is_primary"],
    "transaction_log.csv": ["txn_id","card_no","txn_type","amount","currency","merchant_category","merchant_name","is_cross_border","txn_channel","timestamp"],
    "bill_record.csv": ["bill_id","card_no","bill_month","bill_amount","min_payment","is_min_payment","due_date","payment_status"],
    "crm_customer.csv": ["crm_id","cust_id","lifecycle_stage","customer_manager","vip_tier","churn_risk_score","last_contact_date","contact_preference"],
    "app_events.csv": ["event_id","device_id","open_id","event_type","page_name","search_keyword","duration_sec","timestamp","app_version"],
    "product_catalog.csv": ["product_id","product_name","card_level","annual_fee","annual_fee_waiver","target_income","key_selling_points"],
    "benefit_catalog.csv": ["benefit_id","benefit_name","benefit_category","benefit_desc"],
    "product_benefit_mapping.csv": ["product_id","benefit_id"],
    "campaign_catalog.csv": ["campaign_id","campaign_name","start_date","end_date","target_segment","rules","budget","expected_reach","campaign_poster_path"],
    "channel_config.csv": ["channel_code","channel_name","channel_type","cost_per_send","availability","daily_capacity","monthly_capacity","requires_consent","supported_content_types","avg_open_rate","avg_click_rate","typical_response_time_sec","status"],
    "customer_consent.csv": ["cust_id","marketing_consent","personalization_consent","data_sharing_consent","sms_consent","phone_consent","email_consent","push_consent","wechat_consent","consent_updated_date","dnc_list"],
}

for fname, cols in expected.items():
    path = os.path.join(BASE, "structured", fname)
    if not os.path.exists(path):
        errors.append(f"Missing: structured/{fname}")
        print(f"  MISSING: {fname}")
        continue
    df = pd.read_csv(path, nrows=1)
    actual = df.columns.tolist()
    missing = [c for c in cols if c not in actual]
    ok = len(missing) == 0
    print(f"  {'OK' if ok else 'COL MISMATCH'}: {fname} ({len(actual)} cols, {len(df)} rows via partial read)")
    if missing:
        errors.append(f"{fname}: missing cols {missing}")

# Full row counts
print("\n  --- Full row counts ---")
for fname in expected:
    path = os.path.join(BASE, "structured", fname)
    if os.path.exists(path):
        df = pd.read_csv(path)
        print(f"  {fname}: {len(df)} rows")

print("\n" + "=" * 60)
print("3. UNSTRUCTURED DATA")
print("=" * 60)
asr = glob.glob(os.path.join(BASE, "unstructured/asr_transcripts/ASR_*.json"))
print(f"  ASR transcripts: {len(asr)} files")

docs_idx = os.path.join(BASE, "unstructured/product_docs/_index.json")
txts = glob.glob(os.path.join(BASE, "unstructured/product_docs/doc_*.txt"))
if os.path.exists(docs_idx):
    with open(docs_idx, "r", encoding="utf-8") as f:
        idx = json.load(f)
    print(f"  Product docs: {len(idx)} index entries, {len(txts)} txt files")
else:
    errors.append("Missing _index.json")

posters = glob.glob(os.path.join(BASE, "unstructured/posters/*.json"))
print(f"  Posters: {len(posters)} JSON files")

for rf in ["frequency_rules.json", "compliance_rules.json"]:
    rp = os.path.join(BASE, "unstructured", rf)
    ok = os.path.exists(rp)
    print(f"  {rf}: {'EXISTS' if ok else 'MISSING'}")
    if not ok:
        errors.append(f"Missing {rf}")

print("\n" + "=" * 60)
print("4. SCRIPTS")
print("=" * 60)
scripts = ["config.py","generate_products.py","generate_customers.py","generate_transactions.py",
           "generate_crm.py","generate_app_events.py","generate_asr.py","generate_docs.py",
           "run_all.py","migrate_to_demo_bank.py","sync_names.py"]
for s in scripts:
    ok = os.path.exists(os.path.join(BASE, "scripts", s))
    print(f"  {'OK' if ok else 'MISSING'}: {s}")
    if not ok:
        errors.append(f"Missing script: {s}")

print("\n" + "=" * 60)
print("5. REFERENTIAL INTEGRITY")
print("=" * 60)

df_card = pd.read_csv(os.path.join(BASE, "structured/credit_card.csv"))
df_prod = pd.read_csv(os.path.join(BASE, "structured/product_catalog.csv"))
orphan_pids = set(df_card["product_id"].unique()) - set(df_prod["product_id"])
print(f"  Product IDs: {len(set(df_card['product_id'].unique()))} in cards, {len(orphan_pids)} orphan")
if orphan_pids: errors.append(f"Orphan product_ids: {orphan_pids}")

pid_to_lvl = dict(zip(df_prod["product_id"], df_prod["card_level"]))
df_card["expected"] = df_card["product_id"].map(pid_to_lvl)
mm = (df_card["card_level"] != df_card["expected"]).sum()
print(f"  Card level mismatches: {mm}")
if mm > 0: errors.append(f"{mm} card_level mismatches")

df_map = pd.read_csv(os.path.join(BASE, "structured/product_benefit_mapping.csv"))
df_ben = pd.read_csv(os.path.join(BASE, "structured/benefit_catalog.csv"))
ob = set(df_map["benefit_id"]) - set(df_ben["benefit_id"])
op = set(df_map["product_id"]) - set(df_prod["product_id"])
print(f"  Mapping orphans: {len(ob)} benefits, {len(op)} products")
if ob: errors.append(f"Orphan benefits: {ob}")
if op: errors.append(f"Orphan products in mapping: {op}")

df_con = pd.read_csv(os.path.join(BASE, "structured/customer_consent.csv"))
df_cus = pd.read_csv(os.path.join(BASE, "structured/customer_basic.csv"))
print(f"  Consent coverage: {len(df_con)}/{len(df_cus)} customers")

df_crm = pd.read_csv(os.path.join(BASE, "structured/crm_customer.csv"))
print(f"  CRM coverage: {len(df_crm)}/{len(df_cus)} customers")

print("\n" + "=" * 60)
if errors:
    print(f"FAILED: {len(errors)} errors")
    for e in errors:
        print(f"  [ERROR] {e}")
    sys.exit(1)
else:
    print("ALL CHECKS PASSED")
    sys.exit(0)
