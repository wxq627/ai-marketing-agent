"""
静态画像构建器 — static_builder.py
====================================
基于 Mock 数据构建每个客户的 T+1 静态画像。

画像五维度:
  1. 人口属性: 年龄/性别/城市/职业/收入/学历
  2. 账户属性: 主卡等级/授信额度/已用额度/持卡数/开户时长
  3. 生命周期: 新户(0-3月)/成长期(3-12月)/成熟期(12-36月)/沉睡期(>36月且90天无交易)
  4. 风险标签: 逾期状态/历史逾期次数/最低还款频率/流失风险分
  5. 价值标签: 近12月消费总额/月均消费/单笔最高/分期贡献/LTV等级
"""

import os, pandas as pd, numpy as np
from datetime import datetime, timedelta
from typing import Dict, Any, Optional

REF_DATE = datetime(2026, 7, 15)

class StaticProfileBuilder:
    """T+1 批处理 — 构建全部客户的静态画像。"""

    def __init__(self, data_dir: str = None):
        if data_dir is None:
            data_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                    "mock_data", "structured")
        self.data_dir = data_dir
        self._cache: Dict[str, Dict] = {}

    def load_data(self):
        """加载所有源数据。"""
        s = self.data_dir
        self.customers   = pd.read_csv(os.path.join(s, "customer_basic.csv"))
        self.cards       = pd.read_csv(os.path.join(s, "credit_card.csv"))
        self.crm         = pd.read_csv(os.path.join(s, "crm_customer.csv"))
        self.txn         = pd.read_csv(os.path.join(s, "transaction_log.csv"))
        self.bills       = pd.read_csv(os.path.join(s, "bill_record.csv"))
        self.consent     = pd.read_csv(os.path.join(s, "customer_consent.csv"))
        self.app         = pd.read_csv(os.path.join(s, "app_events.csv"))
        self.attr        = pd.read_csv(os.path.join(s, "campaign_attribution.csv"))
        self.txn["ts"]   = pd.to_datetime(self.txn["timestamp"])
        self.bills["bm"] = self.bills["bill_month"].apply(lambda x: datetime.strptime(x+"-01","%Y-%m-%d"))
        self.app["ts"]   = pd.to_datetime(self.app["timestamp"])

        # 预建索引
        card_to_cust = dict(zip(self.cards["card_no"], self.cards["cust_id"]))
        self.txn["cust_id"] = self.txn["card_no"].map(card_to_cust)
        self.bills["cust_id"] = self.bills["card_no"].map(card_to_cust)

        # OneID 映射
        mp = pd.read_csv(os.path.join(s, "id_mapping.csv"))
        mp_cust = mp[mp["id_type"] == "cust_id"]
        self.cust_to_oneid = dict(zip(mp_cust["id_value"], mp_cust["oneid"]))
        return self

    # ================================================================
    # 构建单个客户的静态画像
    # ================================================================

    def build_one(self, cust_id: str) -> Dict[str, Any]:
        """为一个客户构建完整静态画像。"""
        if cust_id in self._cache:
            return self._cache[cust_id]

        cust  = self._get_cust(cust_id)
        cards = self._get_cards(cust_id)
        crm   = self._get_crm(cust_id)
        cns   = self._get_consent(cust_id)
        txn   = self._get_txn(cust_id)
        bills = self._get_bills(cust_id)

        oneid = self.cust_to_oneid.get(cust_id, f"UID_{cust_id}")

        profile = {
            "oneid": oneid,
            "cust_id": cust_id,

            # 1. 人口属性
            "demographics": {
                "name": cust.get("name", ""),
                "gender": cust.get("gender", ""),
                "age": int(cust.get("age", 0)),
                "city": cust.get("city", ""),
                "occupation": cust.get("occupation", ""),
                "income_level": cust.get("income_level", ""),
                "education": cust.get("education", ""),
            },

            # 2. 账户属性
            "account": self._build_account(cards, cust),

            # 3. 生命周期
            "lifecycle": self._build_lifecycle(cards, cust, crm, txn),

            # 4. 风险标签
            "risk": self._build_risk(bills, crm, cns),

            # 5. 价值标签
            "value": self._build_value(txn, bills, cns),

            # 元数据
            "generated_at": REF_DATE.strftime("%Y-%m-%d %H:%M:%S"),
            "update_type": "T+1_batch",
        }
        self._cache[cust_id] = profile
        return profile

    def build_all(self) -> pd.DataFrame:
        """构建全部客户静态画像 — 向量化批处理。"""
        self.load_data()
        cids = self.customers["cust_id"].tolist()
        total = len(cids)

        # 预建索引
        crm_idx = self.crm.set_index("cust_id")
        consent_idx = self.consent.set_index("cust_id")
        # 每客户主卡
        primary_cards = self.cards[self.cards["is_primary"] == True].set_index("cust_id")
        # 每客户持卡统计
        card_stats = self.cards.groupby("cust_id").agg(
            total_credit=("credit_amount", "sum"),
            card_count=("card_no", "count"),
            active_cards=("card_status", lambda x: (x == "正常").sum()),
            frozen_cards=("card_status", lambda x: (x == "冻结").sum()),
            closed_cards=("card_status", lambda x: (x == "销卡").sum()),
        )
        # 交易聚合 (近12月)
        y12 = REF_DATE - timedelta(days=365)
        txn12 = self.txn[self.txn["ts"] >= y12]
        cons_txn = txn12[txn12["txn_type"] == "消费"]
        txn_agg = cons_txn.groupby("cust_id").agg(
            annual_consumption=("amount", "sum"),
            txn_count=("amount", "count"),
            max_single=("amount", "max"),
        )
        # 分期贡献
        inst_txn = txn12[txn12["txn_type"] == "分期"]
        inst_agg = inst_txn.groupby("cust_id")["amount"].sum().rename("installment_12m")
        # 账单逾期
        recent6 = self.bills[self.bills["bm"] >= REF_DATE - timedelta(days=180)]
        overdue_agg = recent6.groupby("cust_id").agg(
            overdue_count=("payment_status", lambda x: (x == "逾期").sum()),
            minpay_count=("is_min_payment", lambda x: (x == True).sum()),
        )

        rows = []
        for i, cid in enumerate(cids):
            cust_row = self.customers[self.customers["cust_id"] == cid].iloc[0]
            oneid = self.cust_to_oneid.get(cid, f"UID_{cid}")
            reg_str = cust_row.get("register_date", "2020-01-01")
            reg_dt = datetime.strptime(str(reg_str), "%Y-%m-%d") if reg_str else REF_DATE
            months = max(0, (REF_DATE - reg_dt).days / 30.44)

            # 账户
            pc = primary_cards.loc[cid] if cid in primary_cards.index else None
            cs = card_stats.loc[cid] if cid in card_stats.index else None
            account = {
                "primary_card_level": pc["card_level"] if pc is not None else "未知",
                "total_credit_amount": float(cs["total_credit"]) if cs is not None else 0,
                "card_count": int(cs["card_count"]) if cs is not None else 0,
                "tenure_months": round(months, 1),
                "active_cards": int(cs["active_cards"]) if cs is not None else 0,
                "frozen_cards": int(cs["frozen_cards"]) if cs is not None else 0,
                "closed_cards": int(cs["closed_cards"]) if cs is not None else 0,
            }

            # 生命周期
            has_recent = True
            if cid in txn_agg.index:
                has_recent = (REF_DATE - txn12[txn12["cust_id"]==cid]["ts"].max()).days < 90 if len(txn12[txn12["cust_id"]==cid]) > 0 else False
            if months <= 3: stage = "新户"
            elif months <= 12: stage = "成长期"
            elif months <= 36: stage = "成熟期"
            else: stage = "沉睡期" if not has_recent else "成熟期"

            crm_r = crm_idx.loc[cid] if cid in crm_idx.index else None
            lifecycle = {
                "stage": stage, "months_since_open": round(months, 1),
                "has_recent_transaction_90d": has_recent,
                "vip_tier": crm_r["vip_tier"] if crm_r is not None else "普通",
                "customer_manager": crm_r["customer_manager"] if crm_r is not None else "",
            }

            # 风险
            cn_r = consent_idx.loc[cid] if cid in consent_idx.index else None
            ov = overdue_agg.loc[cid] if cid in overdue_agg.index else None
            oc = int(ov["overdue_count"]) if ov is not None else 0
            if oc >= 3: ol = "M3+"
            elif oc >= 2: ol = "M2"
            elif oc >= 1: ol = "M1"
            else: ol = "M0"
            risk = {
                "overdue_status": ol, "history_overdue_count_6m": oc,
                "min_payment_frequency_6m": int(ov["minpay_count"]) if ov is not None else 0,
                "churn_risk_score": int(crm_r["churn_risk_score"]) if crm_r is not None else 0,
                "risk_level": cn_r["risk_level"] if cn_r is not None else "low",
                "blacklist_flag": bool(cn_r["blacklist_flag"]) if cn_r is not None else False,
                "do_not_contact": bool(cn_r["do_not_contact_signal"]) if cn_r is not None else False,
            }

            # 价值
            ta = txn_agg.loc[cid] if cid in txn_agg.index else None
            inst = inst_agg.loc[cid] if cid in inst_agg.index else 0
            value = {
                "annual_consumption": round(float(ta["annual_consumption"]), 2) if ta is not None else 0,
                "monthly_avg_consumption": round(float(ta["annual_consumption"])/12, 2) if ta is not None else 0,
                "max_single_transaction": round(float(ta["max_single"]), 2) if ta is not None else 0,
                "transaction_count_12m": int(ta["txn_count"]) if ta is not None else 0,
                "installment_contribution_12m": round(float(inst), 2),
                "value_level": cn_r["value_level"] if cn_r is not None else "medium",
            }

            rows.append({
                "oneid": oneid, "cust_id": cid,
                "demographics_name": cust_row.get("name",""),
                "demographics_gender": cust_row.get("gender",""),
                "demographics_age": int(cust_row.get("age",0)),
                "demographics_city": cust_row.get("city",""),
                "demographics_occupation": cust_row.get("occupation",""),
                "demographics_income_level": cust_row.get("income_level",""),
                "demographics_education": cust_row.get("education",""),
                **{f"account_{k}": v for k,v in account.items()},
                **{f"lifecycle_{k}": v for k,v in lifecycle.items()},
                **{f"risk_{k}": v for k,v in risk.items()},
                **{f"value_{k}": v for k,v in value.items()},
                "generated_at": REF_DATE.strftime("%Y-%m-%d %H:%M:%S"),
                "update_type": "T+1_batch",
            })
            if (i+1) % 2000 == 0:
                print(f"  静态画像: {i+1}/{total} ...")
        df = pd.DataFrame(rows)
        return df

    # ================================================================
    # 数据提取 helpers
    # ================================================================

    def _get_cust(self, cid):
        r = self.customers[self.customers["cust_id"] == cid]
        return r.iloc[0].to_dict() if len(r) > 0 else {}

    def _get_cards(self, cid):
        return self.cards[self.cards["cust_id"] == cid]

    def _get_crm(self, cid):
        r = self.crm[self.crm["cust_id"] == cid]
        return r.iloc[0].to_dict() if len(r) > 0 else {}

    def _get_consent(self, cid):
        r = self.consent[self.consent["cust_id"] == cid]
        return r.iloc[0].to_dict() if len(r) > 0 else {}

    def _get_txn(self, cid):
        return self.txn[self.txn["cust_id"] == cid]

    def _get_bills(self, cid):
        return self.bills[self.bills["cust_id"] == cid]

    # ================================================================
    # 子维度构建
    # ================================================================

    def _build_account(self, cards, cust):
        primary = cards[cards["is_primary"] == True]
        total_credit = cards["credit_amount"].sum()
        # 已用额度 ≈ 最近一期账单金额
        return {
            "primary_card_level": primary.iloc[0]["card_level"] if len(primary) > 0 else "未知",
            "total_credit_amount": float(total_credit),
            "card_count": len(cards),
            "tenure_months": self._calc_tenure(cust.get("register_date", "")),
            "active_cards": int((cards["card_status"] == "正常").sum()),
            "frozen_cards": int((cards["card_status"] == "冻结").sum()),
            "closed_cards": int((cards["card_status"] == "销卡").sum()),
        }

    def _build_lifecycle(self, cards, cust, crm, txn):
        reg = cust.get("register_date", "2020-01-01")
        reg_dt = datetime.strptime(reg, "%Y-%m-%d") if isinstance(reg, str) else reg
        months = max(0, (REF_DATE - reg_dt).days / 30.44)
        # 近90天是否有交易
        cutoff = REF_DATE - timedelta(days=90)
        has_recent = len(txn[txn["ts"] >= cutoff]) > 0 if len(txn) > 0 else False

        if months <= 3:
            stage = "新户"
        elif months <= 12:
            stage = "成长期"
        elif months <= 36:
            stage = "成熟期"
        else:
            stage = "沉睡期" if not has_recent else "成熟期"

        return {
            "stage": stage,
            "months_since_open": round(months, 1),
            "has_recent_transaction_90d": has_recent,
            "vip_tier": crm.get("vip_tier", "普通"),
            "customer_manager": crm.get("customer_manager", ""),
        }

    def _build_risk(self, bills, crm, cns):
        # 逾期状态: 检查最近6个月
        recent6 = bills[bills["bm"] >= REF_DATE - timedelta(days=180)]
        overdue_count = int((recent6["payment_status"] == "逾期").sum())
        min_pay_count = int((recent6["is_min_payment"] == True).sum())

        if overdue_count >= 3:
            overdue_level = "M3+"
        elif overdue_count >= 2:
            overdue_level = "M2"
        elif overdue_count >= 1:
            overdue_level = "M1"
        else:
            overdue_level = "M0"

        return {
            "overdue_status": overdue_level,
            "history_overdue_count_6m": overdue_count,
            "min_payment_frequency_6m": min_pay_count,
            "churn_risk_score": int(crm.get("churn_risk_score", 0)),
            "risk_level": cns.get("risk_level", "low"),
            "blacklist_flag": bool(cns.get("blacklist_flag", False)),
            "do_not_contact": bool(cns.get("do_not_contact_signal", False)),
        }

    def _build_value(self, txn, bills, cns):
        # 近12月
        y12 = REF_DATE - timedelta(days=365)
        txn12 = txn[txn["ts"] >= y12] if len(txn) > 0 else txn
        consumption = txn12[txn12["txn_type"] == "消费"]["amount"].sum()
        installment = txn12[txn12["txn_type"] == "分期"]["amount"].sum()
        count = len(txn12[txn12["txn_type"] == "消费"])
        max_single = txn12[txn12["txn_type"] == "消费"]["amount"].max() if count > 0 else 0

        monthly_avg = consumption / 12 if consumption > 0 else 0
        return {
            "annual_consumption": round(float(consumption), 2),
            "monthly_avg_consumption": round(float(monthly_avg), 2),
            "max_single_transaction": round(float(max_single), 2),
            "transaction_count_12m": int(count),
            "installment_contribution_12m": round(float(installment), 2),
            "value_level": cns.get("value_level", "medium"),
        }

    def _calc_tenure(self, reg_str: str) -> float:
        if not reg_str:
            return 0
        try:
            dt = datetime.strptime(reg_str, "%Y-%m-%d")
            return round((REF_DATE - dt).days / 30.44, 1)
        except:
            return 0
