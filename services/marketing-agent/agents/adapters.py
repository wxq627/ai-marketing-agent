"""
agents\adapters.py
功能描述: 适配器模块，提供客户画像和知识库的数据访问
支持真实API和Mock双模式，API不可用时自动回退到Mock
"""

import json
import requests
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta

from common import logger, ke_config, sa_strategy_config


class ProfileMockAdapter:
    _mock_profiles: Dict[str, Dict[str, Any]] = {}
    
    _base_profile = {
        "oneid": "UID000001",
        "cust_id": "C000001",
        "demographics": {
            "name": "王丹",
            "gender": "女",
            "age": 39,
            "city": "西安",
            "occupation": "金融/保险",
            "income_level": "M",
            "education": "大专"
        },
        "account": {
            "primary_card_level": "金卡",
            "product_name": "XX银行YOUNG卡（青年版）",
            "total_credit_amount": 109600.0,
            "used_amount": 41747.2,
            "usage_rate": 0.3809,
            "card_count": 4,
            "active_cards": 4,
            "tenure_months": 64.9
        },
        "lifecycle": {
            "stage": "成熟期",
            "months_since_open": 64.9,
            "vip_tier": "普通",
            "customer_manager": "吴芳"
        },
        "risk": {
            "overdue_status": "M1",
            "history_overdue_count_6m": 1,
            "min_payment_frequency_6m": 0,
            "cash_advance_risk_score": 4,
            "churn_risk_score": 0,
            "risk_level": "low",
            "blacklist_flag": False,
            "do_not_contact": False
        },
        "value": {
            "annual_consumption": 61039.39,
            "monthly_avg_consumption": 5086.62,
            "max_single_transaction": 2611.17,
            "transaction_count_12m": 46,
            "installment_contribution_12m": 5133.43,
            "value_level": "medium"
        },
        "consumption": {
            "long_term_90d_total": 17799.97,
            "long_term_90d_txn_count": 11,
            "long_term_90d_active_days": 6,
            "long_term_90d_activity_score": 16,
            "long_term_90d_dormancy_risk": "high",
            "mid_term_30d_total": 4437.94,
            "mid_term_30d_txn_count": 3,
            "mid_term_30d_active_days": 2,
            "mid_term_30d_trend": "down",
            "mid_term_30d_trend_change_pct": -22.0,
            "short_term_7d_total": 1330.79,
            "short_term_7d_txn_count": 0,
            "short_term_7d_active_days": 0
        },
        "preferences": {
            "browse_preferences": "新手指引(19%), 还款页面(20%), 分期计算器(1%), 额度管理(60%)",
            "top_search_keywords": "账单分期×3, 注销×3, 固定额度×2",
            "avg_daily_spend": 190.11
        },
        "consent": {
            "marketing_consent": True,
            "sms_consent": True,
            "push_consent": True,
            "wechat_consent": True
        },
        "billing": {
            "bill_amount": 3850.00,
            "bill_date": "每月5日",
            "due_date": "每月25日",
            "minimum_payment": 385.00
        }
    }

    def __init__(self):
        self._mock_profiles["UID000001"] = self._base_profile
        self._mock_profiles["user001"] = self._base_profile

    def get_profile(self, oneid: str) -> Optional[Dict[str, Any]]:
        profile = self._mock_profiles.get(oneid)
        if profile:
            logger.info(f"[Mock] 获取客户画像: oneid={oneid}, name={profile['demographics']['name']}")
        else:
            logger.warning(f"[Mock] 客户画像不存在: oneid={oneid}")
        return profile

    def get_field(self, oneid: str, field_path: str) -> Optional[Any]:
        profile = self.get_profile(oneid)
        if not profile:
            return None
        
        fields = field_path.split('.')
        value = profile
        for field in fields:
            if isinstance(value, dict) and field in value:
                value = value[field]
            else:
                return None
        return value

    def get_billing_info(self, oneid: str) -> Optional[Dict[str, Any]]:
        profile = self.get_profile(oneid)
        if profile and 'billing' in profile:
            return profile['billing']
        return None

    def get_account_info(self, oneid: str) -> Optional[Dict[str, Any]]:
        profile = self.get_profile(oneid)
        if profile and 'account' in profile:
            return profile['account']
        return None

    def get_demographics(self, oneid: str) -> Optional[Dict[str, Any]]:
        profile = self.get_profile(oneid)
        if profile and 'demographics' in profile:
            return profile['demographics']
        return None


class KnowledgeMockAdapter:
    _mock_knowledge: Dict[str, List[Dict[str, Any]]] = {
        "benefit_catalog": [
            {"id": "BEN001", "name": "机场贵宾厅", "description": "全年60次机场贵宾厅服务", "product": "白金卡"},
            {"id": "BEN002", "name": "接送机服务", "description": "全年12次免费接送机服务", "product": "白金卡"},
            {"id": "BEN003", "name": "航班延误险", "description": "最高2000元航班延误赔偿", "product": "白金卡"},
            {"id": "BEN004", "name": "积分兑换", "description": "积分可兑换航空里程、酒店住宿等", "product": "金卡"},
            {"id": "BEN005", "name": "分期手续费优惠", "description": "账单分期手续费低至0.45%/期", "product": "金卡"},
            {"id": "BEN006", "name": "生日双倍积分", "description": "生日当天消费享受双倍积分", "product": "普卡"}
        ],
        "product_catalog": [
            {"id": "PROD001", "name": "白金卡", "description": "高端信用卡，享受全方位贵宾服务", "annual_fee": 1800},
            {"id": "PROD002", "name": "金卡", "description": "中端信用卡，享受丰富权益", "annual_fee": 300},
            {"id": "PROD003", "name": "普卡", "description": "入门级信用卡，满足日常消费需求", "annual_fee": 0},
            {"id": "PROD004", "name": "YOUNG卡", "description": "青年专属信用卡，灵活分期", "annual_fee": 0}
        ],
        "activity_rules": [
            {"id": "ACT001", "name": "分期手续费折扣", "description": "活动期间办理账单分期享手续费8折优惠", "valid_period": "2026-07-01至2026-07-31"},
            {"id": "ACT002", "name": "新户开卡礼", "description": "新客户开卡首月消费满3笔送100元刷卡金", "valid_period": "长期有效"},
            {"id": "ACT003", "name": "周末消费双倍积分", "description": "周六周日消费享受双倍积分", "valid_period": "2026-07-01至2026-08-31"}
        ],
        "faq": [
            {"question": "如何办理账单分期？", "answer": "登录手机银行APP，进入\"分期\"页面，选择账单分期，按照提示操作即可完成办理。"},
            {"question": "信用卡年费如何收取？", "answer": "白金卡年费1800元/年，金卡年费300元/年，普卡免年费。年费在卡片激活后首个账单日收取。"},
            {"question": "如何提升信用额度？", "answer": "使用信用卡满6个月后，可通过手机银行APP申请调额，系统会根据您的用卡情况综合评估。"},
            {"question": "忘记还款怎么办？", "answer": "请尽快通过手机银行或柜台还款。逾期会产生利息和滞纳金，建议开启自动还款功能避免忘记还款。"},
            {"question": "如何申请临时额度？", "answer": "登录手机银行APP，进入\"额度管理\"页面，选择\"临时额度\"，按照提示提交申请即可。"}
        ]
    }

    def search(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        results = []
        
        for category, items in self._mock_knowledge.items():
            for item in items:
                score = 0
                text = f"{item.get('name', '')} {item.get('description', '')} {item.get('question', '')} {item.get('answer', '')}"
                for word in query.split():
                    if word in text:
                        score += 1
                
                if score > 0:
                    results.append({
                        "category": category,
                        "score": score,
                        **item
                    })
        
        results.sort(key=lambda x: x["score"], reverse=True)
        logger.info(f"[Mock] 知识库检索: query={query}, 命中{len(results)}条结果")
        return results[:top_k]

    def search_benefits(self, query: str, top_k: int = 3) -> List[Dict[str, Any]]:
        return self._search_by_category("benefit_catalog", query, top_k)

    def search_products(self, query: str, top_k: int = 3) -> List[Dict[str, Any]]:
        return self._search_by_category("product_catalog", query, top_k)

    def search_faq(self, query: str, top_k: int = 3) -> List[Dict[str, Any]]:
        return self._search_by_category("faq", query, top_k)

    def _search_by_category(self, category: str, query: str, top_k: int) -> List[Dict[str, Any]]:
        items = self._mock_knowledge.get(category, [])
        results = []
        
        for item in items:
            text = f"{item.get('name', '')} {item.get('description', '')} {item.get('question', '')} {item.get('answer', '')}"
            score = sum(1 for word in query.split() if word in text)
            
            if score > 0:
                results.append({
                    "category": category,
                    "score": score,
                    **item
                })
        
        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:top_k]


class ProfileAPIAdapter:
    def __init__(self):
        self.api_base = ke_config.KE_API_BASE
        self.timeout = ke_config.KE_API_TIMEOUT
        self.fallback_to_mock = ke_config.KE_FALLBACK_TO_MOCK
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._cache_time: Dict[str, datetime] = {}
        self._mock_adapter = ProfileMockAdapter()

    def _convert_profile(self, api_data: Dict) -> Dict:
        customers = api_data.get("customers", [])
        if not customers:
            return None
        customer = customers[0]
        if not customer:
            return None
        
        return {
            "oneid": customer.get("oneid", ""),
            "cust_id": customer.get("cust_id", ""),
            "demographics": {
                "name": customer.get("profile", {}).get("name", "") or customer.get("profile", {}).get("vip_tier", "客户"),
                "gender": customer.get("profile", {}).get("gender", ""),
                "age": customer.get("profile", {}).get("age", 0),
                "city": customer.get("profile", {}).get("city", ""),
                "occupation": customer.get("profile", {}).get("occupation", ""),
                "income_level": customer.get("profile", {}).get("income_level", ""),
                "education": customer.get("profile", {}).get("education", "")
            },
            "account": {
                "primary_card_level": customer.get("account", {}).get("card_level", ""),
                "product_name": customer.get("account", {}).get("product_name", ""),
                "total_credit_amount": float(customer.get("account", {}).get("total_credit_amount", 0)),
                "used_amount": float(customer.get("account", {}).get("total_credit_amount", 0)) * float(customer.get("account", {}).get("usage_rate", 0)),
                "usage_rate": float(customer.get("account", {}).get("usage_rate", 0)),
                "card_count": int(customer.get("account", {}).get("card_count", 0)),
                "active_cards": int(customer.get("account", {}).get("card_count", 0)),
                "tenure_months": 0
            },
            "lifecycle": {
                "stage": customer.get("profile", {}).get("lifecycle_stage", ""),
                "months_since_open": 0,
                "vip_tier": customer.get("profile", {}).get("vip_tier", ""),
                "customer_manager": ""
            },
            "risk": {
                "overdue_status": customer.get("risk", {}).get("overdue_status", ""),
                "history_overdue_count_6m": 0,
                "min_payment_frequency_6m": 0,
                "cash_advance_risk_score": 0,
                "churn_risk_score": int(customer.get("risk", {}).get("churn_risk_score", 0)),
                "risk_level": customer.get("risk", {}).get("risk_level", ""),
                "blacklist_flag": bool(customer.get("consent", {}).get("blacklist_flag", False)),
                "do_not_contact": bool(customer.get("consent", {}).get("do_not_contact", False))
            },
            "value": {
                "annual_consumption": float(customer.get("consumption", {}).get("annual", 0)),
                "monthly_avg_consumption": float(customer.get("consumption", {}).get("monthly_avg", 0)),
                "max_single_transaction": 0,
                "transaction_count_12m": 0,
                "installment_contribution_12m": 0,
                "value_level": customer.get("tags", {}).get("value_level", "")
            },
            "consumption": {
                "long_term_90d_total": float(customer.get("consumption", {}).get("cons_90d", 0)),
                "long_term_90d_txn_count": 0,
                "long_term_90d_active_days": int(customer.get("consumption", {}).get("active_days_90d", 0)),
                "long_term_90d_activity_score": int(customer.get("consumption", {}).get("activity_score", 0)),
                "long_term_90d_dormancy_risk": customer.get("risk", {}).get("dormancy_risk", ""),
                "mid_term_30d_total": float(customer.get("consumption", {}).get("cons_30d", 0)),
                "mid_term_30d_txn_count": 0,
                "mid_term_30d_active_days": 0,
                "mid_term_30d_trend": customer.get("consumption", {}).get("trend", ""),
                "mid_term_30d_trend_change_pct": 0,
                "short_term_7d_total": float(customer.get("consumption", {}).get("cons_7d", 0)),
                "short_term_7d_txn_count": 0,
                "short_term_7d_active_days": 0
            },
            "preferences": {
                "browse_preferences": customer.get("tags", {}).get("significant_signals", ""),
                "top_search_keywords": customer.get("tags", {}).get("search_keywords_7d", ""),
                "avg_daily_spend": 0
            },
            "consent": {
                "marketing_consent": bool(customer.get("consent", {}).get("marketing_consent", False)),
                "sms_consent": bool(customer.get("consent", {}).get("sms_consent", False)),
                "push_consent": bool(customer.get("consent", {}).get("push_consent", False)),
                "wechat_consent": bool(customer.get("consent", {}).get("wechat_consent", False))
            },
            "billing": {
                "bill_amount": float(customer.get("account", {}).get("total_credit_amount", 0)) * float(customer.get("account", {}).get("usage_rate", 0)) * 0.3,
                "bill_date": "每月5日",
                "due_date": "每月25日",
                "minimum_payment": 0
            }
        }

    def _normalize_oneid(self, oneid: str) -> str:
        if oneid.startswith("user"):
            return "UID" + oneid[4:].zfill(6)
        if oneid.startswith("cust"):
            return "C" + oneid[4:].zfill(6)
        return oneid

    def _get_from_api(self, oneid: str) -> Optional[Dict]:
        try:
            normalized_oneid = self._normalize_oneid(oneid)
            url = f"{self.api_base}/api/v1/customer/search"
            
            if normalized_oneid.startswith("C"):
                payload = {"cust_ids": [normalized_oneid], "page_size": 1}
            else:
                payload = {"oneids": [normalized_oneid], "page_size": 1}
            
            response = requests.post(url, json=payload, timeout=self.timeout)
            if response.status_code == 200:
                data = response.json()
                converted = self._convert_profile(data)
                if converted:
                    converted["oneid"] = oneid
                return converted
        except Exception as e:
            logger.warning(f"[KE API] 获取客户画像失败: {e}")
        return None

    def get_profile(self, oneid: str) -> Optional[Dict[str, Any]]:
        now = datetime.now()
        
        if oneid in self._cache:
            cache_time = self._cache_time.get(oneid, now)
            if (now - cache_time) < timedelta(seconds=ke_config.KE_CACHE_TTL):
                logger.info(f"[KE Cache] 获取客户画像: oneid={oneid}")
                return self._cache[oneid]
        
        api_result = self._get_from_api(oneid)
        
        if api_result:
            self._cache[oneid] = api_result
            self._cache_time[oneid] = now
            logger.info(f"[KE API] 获取客户画像成功: oneid={oneid}")
            return api_result
        
        if self.fallback_to_mock:
            logger.info(f"[KE Fallback] 使用Mock数据: oneid={oneid}")
            return self._mock_adapter.get_profile(oneid)
        
        return None

    def get_field(self, oneid: str, field_path: str) -> Optional[Any]:
        profile = self.get_profile(oneid)
        if not profile:
            return None
        
        fields = field_path.split('.')
        value = profile
        for field in fields:
            if isinstance(value, dict) and field in value:
                value = value[field]
            else:
                return None
        return value

    def get_billing_info(self, oneid: str) -> Optional[Dict[str, Any]]:
        profile = self.get_profile(oneid)
        if profile and 'billing' in profile:
            return profile['billing']
        return None

    def get_account_info(self, oneid: str) -> Optional[Dict[str, Any]]:
        profile = self.get_profile(oneid)
        if profile and 'account' in profile:
            return profile['account']
        return None

    def get_demographics(self, oneid: str) -> Optional[Dict[str, Any]]:
        profile = self.get_profile(oneid)
        if profile and 'demographics' in profile:
            return profile['demographics']
        return None


class KnowledgeAPIAdapter:
    def __init__(self):
        self.api_base = ke_config.KE_API_BASE
        self.timeout = ke_config.KE_API_TIMEOUT
        self.fallback_to_mock = ke_config.KE_FALLBACK_TO_MOCK
        self._mock_adapter = KnowledgeMockAdapter()

    def _convert_knowledge(self, api_results: List) -> List[Dict]:
        results = []
        for item in api_results:
            source_type = item.get("source_type", "")
            content = item.get("content", "")
            entity_type = item.get("entity_type", "")
            
            if source_type == "graph":
                name = content.split("(")[0].strip() if content else "知识实体"
                category = "product_catalog" if "product" in entity_type else \
                           "benefit_catalog" if "benefit" in entity_type else \
                           "activity_rules" if "campaign" in entity_type else "faq"
                results.append({
                    "category": category,
                    "score": item.get("relevance_score", item.get("final_score", 0)),
                    "name": name,
                    "description": content,
                })
            elif source_type == "vector":
                results.append({
                    "category": "faq",
                    "score": item.get("relevance_score", item.get("final_score", 0)),
                    "name": "知识文档",
                    "description": content[:300] if content else "",
                })
            elif source_type == "compliance":
                results.append({
                    "category": "activity_rules",
                    "score": item.get("relevance_score", item.get("final_score", 0)),
                    "name": "合规提示",
                    "description": content,
                })
        
        return results

    def _get_from_api(self, query: str, top_k: int) -> List[Dict]:
        try:
            url = f"{self.api_base}/api/v1/search"
            payload = {"query": query, "top_k": top_k}
            response = requests.post(url, json=payload, timeout=self.timeout)
            if response.status_code == 200:
                data = response.json()
                return self._convert_knowledge(data.get("results", []))
        except Exception as e:
            logger.warning(f"[KE API] 知识库检索失败: {e}")
        return []

    def search(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        api_results = self._get_from_api(query, top_k)
        
        if api_results:
            logger.info(f"[KE API] 知识库检索成功: query={query}, 命中{len(api_results)}条结果")
            return api_results
        
        if self.fallback_to_mock:
            logger.info(f"[KE Fallback] 使用Mock知识库: query={query}")
            return self._mock_adapter.search(query, top_k)
        
        return []

    def search_benefits(self, query: str, top_k: int = 3) -> List[Dict[str, Any]]:
        api_results = self._get_from_api(query, top_k)
        if api_results:
            return [r for r in api_results if r.get("category") in ("benefit_catalog", "activity_rules")][:top_k]
        return self._mock_adapter.search_benefits(query, top_k)

    def search_products(self, query: str, top_k: int = 3) -> List[Dict[str, Any]]:
        api_results = self._get_from_api(query, top_k)
        if api_results:
            return [r for r in api_results if r.get("category") == "product_catalog"][:top_k]
        return self._mock_adapter.search_products(query, top_k)

    def search_faq(self, query: str, top_k: int = 3) -> List[Dict[str, Any]]:
        api_results = self._get_from_api(query, top_k)
        if api_results:
            return [r for r in api_results if r.get("category") == "faq"][:top_k]
        return self._mock_adapter.search_faq(query, top_k)


class IntentAPIAdapter:
    def __init__(self):
        self.api_base = ke_config.KE_API_BASE
        self.timeout = ke_config.KE_API_TIMEOUT
        self.fallback_to_mock = ke_config.KE_FALLBACK_TO_MOCK

    def _normalize_oneid(self, oneid: str) -> str:
        if oneid.startswith("user"):
            return "UID" + oneid[4:].zfill(6)
        if oneid.startswith("cust"):
            return "C" + oneid[4:].zfill(6)
        return oneid

    def get_intent(self, oneid: str) -> Dict:
        try:
            normalized_oneid = self._normalize_oneid(oneid)
            url = f"{self.api_base}/api/v1/customer/{normalized_oneid}/intent"
            response = requests.get(url, timeout=self.timeout)
            if response.status_code == 200:
                data = response.json()
                data["oneid"] = oneid
                logger.info(f"[KE API] 获取意图向量成功: oneid={oneid}, primary={data.get('primary_intent','')}")
                return data
        except Exception as e:
            logger.warning(f"[KE API] 获取意图向量失败: {e}")
        
        if self.fallback_to_mock:
            logger.info(f"[KE Fallback] 使用Mock意图数据: oneid={oneid}")
            return {
                "oneid": oneid,
                "primary_intent": "分期/借贷需求",
                "intents": [
                    {"type": "分期/借贷需求", "score": 60, "confidence": "medium", "trend": "stable"},
                    {"type": "跨境/出行需求", "score": 20, "confidence": "low", "trend": "stable"},
                    {"type": "额度/升级需求", "score": 15, "confidence": "low", "trend": "stable"},
                    {"type": "权益/优惠需求", "score": 30, "confidence": "low", "trend": "stable"},
                    {"type": "沉睡/流失风险", "score": 10, "confidence": "low", "trend": "stable"},
                    {"type": "新户/激活引导", "score": 5, "confidence": "low", "trend": "stable"},
                ],
                "sentiment": {
                    "overall": "neutral",
                    "confidence": 0.75,
                    "anxiety_score": 30,
                    "satisfaction_score": 60,
                    "key_evidence": "基于画像数据的综合评估",
                },
            }
        
        return {"oneid": oneid, "primary_intent": "", "intents": [], "sentiment": {}}

    def classify_text(self, conversation_text: str, oneid: str = None) -> Dict:
        try:
            url = f"{self.api_base}/api/v1/intent/classify"
            payload = {"conversation_text": conversation_text, "oneid": oneid}
            response = requests.post(url, json=payload, timeout=self.timeout)
            if response.status_code == 200:
                data = response.json()
                logger.info(f"[KE API] 意图分类成功: text={conversation_text[:30]}, primary={data.get('primary_intent','')}")
                return data
        except Exception as e:
            logger.warning(f"[KE API] 意图分类失败: {e}")
        
        if self.fallback_to_mock:
            logger.info(f"[KE Fallback] 使用Mock意图分类")
            keywords_map = {
                "分期": "分期/借贷需求",
                "额度": "额度/升级需求",
                "权益": "权益/优惠需求",
                "境外": "跨境/出行需求",
                "注销": "沉睡/流失风险",
                "开卡": "新户/激活引导",
            }
            primary_intent = "分期/借贷需求"
            intent_score = 50
            for kw, intent in keywords_map.items():
                if kw in conversation_text:
                    primary_intent = intent
                    intent_score = min(50 + conversation_text.count(kw) * 20, 90)
                    break
            
            sentiment_keywords = {
                "焦虑": ["压力", "还不上", "担心"],
                "不满": ["投诉", "太差", "骗人"],
                "满意": ["谢谢", "好的", "不错"],
                "好奇": ["什么", "怎么", "多少钱"],
            }
            sentiment = "中性"
            for sent, kws in sentiment_keywords.items():
                if any(kw in conversation_text for kw in kws):
                    sentiment = sent
                    break
            
            return {
                "primary_intent": primary_intent,
                "intent_score": intent_score,
                "all_intents": {
                    "分期/借贷需求": intent_score if "分期" in conversation_text else 20,
                    "跨境/出行需求": 30 if "境外" in conversation_text else 10,
                    "额度/升级需求": 40 if "额度" in conversation_text else 15,
                    "权益/优惠需求": 35 if "权益" in conversation_text else 25,
                    "沉睡/流失风险": 25 if "注销" in conversation_text else 5,
                    "新户/激活引导": 30 if "开卡" in conversation_text else 5,
                },
                "sentiment": {
                    "overall": sentiment,
                    "confidence": 0.8,
                    "anxiety_score": 20,
                    "satisfaction_score": 60,
                    "key_evidence": "基于关键词匹配",
                },
                "urgency": "中",
                "key_phrases": [kw for kw in keywords_map.keys() if kw in conversation_text],
            }
        
        return {"primary_intent": "", "intent_score": 0, "sentiment": {}}


class FrequencyAPIAdapter:
    def __init__(self):
        self.api_base = ke_config.KE_API_BASE
        self.timeout = ke_config.KE_API_TIMEOUT
        self.fallback_to_mock = ke_config.KE_FALLBACK_TO_MOCK

    def _normalize_oneid(self, oneid: str) -> str:
        if oneid.startswith("user"):
            return "C" + oneid[4:].zfill(6)
        if oneid.startswith("UID"):
            return "C" + oneid[3:].zfill(6)
        if oneid.startswith("cust"):
            return "C" + oneid[4:].zfill(6)
        return oneid

    def check_frequency(self, oneid: str, planned_channel: str = "") -> Dict:
        try:
            normalized_oneid = self._normalize_oneid(oneid)
            url = f"{self.api_base}/api/v1/customer/frequency-check"
            payload = {"cust_ids": [normalized_oneid], "planned_channel": planned_channel}
            response = requests.post(url, json=payload, timeout=self.timeout)
            if response.status_code == 200:
                data = response.json()
                result = data.get("results", [{}])[0]
                logger.info(f"[KE API] 频控检查成功: oneid={oneid}, can_send={result.get('can_send', False)}")
                return result
        except Exception as e:
            logger.warning(f"[KE API] 频控检查失败: {e}")
        
        if self.fallback_to_mock:
            logger.info(f"[KE Fallback] 使用Mock频控数据: oneid={oneid}")
            return {
                "cust_id": oneid,
                "can_send": True,
                "available_channels": ["APP Push", "短信", "微信公众号"],
                "blocked_channels": [],
                "contact_count": {"1d": 0, "7d": 2, "30d": 5},
                "limits": {"global_max_per_day": 5, "global_max_per_week": 15},
            }
        
        return {
            "cust_id": oneid,
            "can_send": True,
            "available_channels": [],
            "blocked_channels": [],
            "contact_count": {},
            "limits": {},
        }


profile_adapter = ProfileAPIAdapter()
knowledge_adapter = KnowledgeAPIAdapter()
intent_adapter = IntentAPIAdapter()
frequency_adapter = FrequencyAPIAdapter()


# ==================== 产品/渠道映射常量 ====================

_PRODUCT_NAME_MAP = {
    "installment": "credit_card_installment",
    "coupon": "consumption_coupon",
    "travel": "travel_benefit",
}

_BENEFIT_TYPE_MAP = {
    "installment": "installment_fee_coupon",
    "coupon": "consumption_coupon_package",
    "travel": "travel_benefit_package",
}

_BENEFIT_NAME_MAP = {
    "installment": "分期手续费折扣券",
    "coupon": "消费券包",
    "travel": "商旅权益包",
}

# strategy_agent 渠道名 → marketing_agent 渠道名
_CHANNEL_NAME_MAP = {
    "app弹窗": "app_push",
    "app首页": "app_push",
    "push": "app_push",
    "短信": "sms",
    "企微": "wechat",
}


class StrategyAgentAdapter:
    """
    对接 strategy_agent 服务，将 MarketingPlan 转换为 StrategyPackage。
    支持：
    1. 调用 strategy_agent /api/generate 生成策略
    2. MarketingPlan → StrategyPackage 格式转换
    3. 缓存最新策略（TTL 可配置）
    4. 失败时回退到 mock 文件
    """

    def __init__(self):
        self.api_base = sa_strategy_config.SA_API_BASE
        self.timeout = sa_strategy_config.SA_API_TIMEOUT
        self.fallback_to_mock = sa_strategy_config.SA_FALLBACK_TO_MOCK
        self._cache_ttl = sa_strategy_config.SA_CACHE_TTL
        self._cached_strategy: Optional[Dict[str, Any]] = None
        self._cache_time: Optional[datetime] = None
        self._last_raw_plan: Optional[Dict[str, Any]] = None

    # ---------- 对外主接口 ----------

    def generate_strategy(self, request_params: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        调用 strategy_agent 生成策略包并转换为 StrategyPackage 格式。
        request_params: {goal, product, channel_mode, budget_wan, risk_level, frequency_level}
        返回：StrategyPackage 字典；失败时返回 None
        """
        marketing_plan = self._call_generate_api(request_params)
        if not marketing_plan:
            if self.fallback_to_mock:
                logger.info("[SA Fallback] strategy_agent 不可用，回退到 mock 文件")
                return None
            return None

        self._last_raw_plan = marketing_plan
        strategy_package = self.convert_to_strategy_package(marketing_plan)
        if strategy_package:
            self._cached_strategy = strategy_package
            self._cache_time = datetime.now()
            logger.info(
                f"[SA API] 策略生成并转换成功: campaign_id={strategy_package.get('campaign_metadata', {}).get('campaign_id')}"
            )
        return strategy_package

    def get_cached_strategy(self) -> Optional[Dict[str, Any]]:
        """获取最近缓存的策略包（未过期才返回）"""
        if not self._cached_strategy or not self._cache_time:
            return None
        if (datetime.now() - self._cache_time).total_seconds() > self._cache_ttl:
            logger.info("[SA Cache] 缓存已过期")
            return None
        return self._cached_strategy

    def get_last_raw_plan(self) -> Optional[Dict[str, Any]]:
        """获取最近一次从 strategy_agent 拿到的原始 MarketingPlan"""
        return self._last_raw_plan

    # ---------- HTTP 调用 ----------

    def _call_generate_api(self, request_params: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        url = f"{self.api_base}/api/generate"
        try:
            response = requests.post(url, json=request_params, timeout=self.timeout)
            if response.status_code == 200:
                data = response.json()
                logger.info(
                    f"[SA API] 调用成功: campaign_id={data.get('campaign_id')}, "
                    f"audience_size={data.get('audience_size')}"
                )
                return data
            logger.warning(f"[SA API] 调用失败: status={response.status_code}, body={response.text[:200]}")
        except Exception as e:
            logger.warning(f"[SA API] 调用 strategy_agent 异常: {e}")
        return None

    # ---------- 格式转换：MarketingPlan → StrategyPackage ----------

    def convert_to_strategy_package(self, plan: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """将 strategy_agent 输出的 MarketingPlan 转换为 StrategyPackage 字典格式"""
        try:
            campaign_id = plan.get("campaign_id", "")
            request_data = plan.get("request", {}) or {}
            intent_data = plan.get("intent", {}) or {}
            segments_data = plan.get("segments", []) or []
            channels_data = plan.get("channels", []) or []
            content_data = plan.get("content", {}) or {}
            compliance_data = plan.get("compliance", []) or []
            experiment_data = plan.get("experiment", {}) or {}

            product_key = intent_data.get("product", request_data.get("product", "installment"))
            budget_wan = request_data.get("budget_wan", 80)

            # 1. campaign_metadata
            campaign_metadata = {
                "campaign_id": campaign_id,
                "objective": intent_data.get("objective", "提升转化与ROI"),
                "product": _PRODUCT_NAME_MAP.get(product_key, product_key),
                "budget": float(budget_wan) * 10000.0,
                "start_time": None,
                "end_time": None,
            }

            # 2. audience_segments
            audience_segments = self._convert_segments(segments_data, plan.get("predicted_roi", 0.0))

            # 3. benefit_rule
            benefit_rule = self._convert_benefit_rule(product_key, intent_data, content_data)

            # 4. channel_routing
            channel_routing = self._convert_channel_routing(channels_data)

            # 5. content_brief
            content_brief = self._convert_content_brief(content_data, intent_data)

            # 6. compliance_guard
            compliance_guard = self._convert_compliance_guard(compliance_data, request_data)

            # 7. experiment_plan
            experiment_plan = self._convert_experiment_plan(experiment_data)

            # 8. callback_config
            callback_config = {
                "feedback_url": "/api/v3/strategy/feedback",
                "report_interval": "hourly",
            }

            return {
                "campaign_metadata": campaign_metadata,
                "audience_segments": audience_segments,
                "benefit_rule": benefit_rule,
                "channel_routing": channel_routing,
                "content_brief": content_brief,
                "compliance_guard": compliance_guard,
                "experiment_plan": experiment_plan,
                "callback_config": callback_config,
            }
        except Exception as e:
            logger.error(f"[SA Adapter] 格式转换失败: {e}")
            return None

    # ---------- 各字段转换子方法 ----------

    def _convert_segments(self, segments_data: List[Dict], predicted_roi: float) -> List[Dict[str, Any]]:
        """转换为 audience_segments，按 expected_value_wan 归一化得到 priority"""
        if not segments_data:
            return [
                {
                    "segment_id": "SEG001",
                    "segment_name": "目标客群",
                    "size": 0,
                    "priority": 0.5,
                    "features": [],
                    "expected_conversion_rate": 0.0,
                    "expected_roi": predicted_roi,
                }
            ]

        total_value = sum(float(seg.get("expected_value_wan", 0)) for seg in segments_data) or 1.0
        result = []
        for idx, seg in enumerate(segments_data, 1):
            value_wan = float(seg.get("expected_value_wan", 0))
            priority = round(value_wan / total_value, 4) if total_value > 0 else 0.5
            conversion_rate = float(seg.get("conversion_rate", 0)) / 100.0
            result.append({
                "segment_id": f"SEG{idx:03d}",
                "segment_name": seg.get("name", f"客群{idx}"),
                "size": int(seg.get("size", 0)),
                "priority": priority,
                "features": seg.get("reasons", []) or [],
                "expected_conversion_rate": round(conversion_rate, 4),
                "expected_roi": predicted_roi,
            })
        return result

    def _convert_benefit_rule(self, product_key: str, intent_data: Dict, content_data: Dict) -> Dict[str, Any]:
        """转换为 benefit_rule"""
        benefit_name = _BENEFIT_NAME_MAP.get(product_key, "专属权益")
        benefit_type = _BENEFIT_TYPE_MAP.get(product_key, product_key)

        # 从 intent.constraints 中提取准入条件
        constraints = intent_data.get("constraints", []) or []
        eligibility = [c for c in constraints if "授权" in c or "频控" in c or "风险" in c or "合规" in c]
        if not eligibility:
            eligibility = ["marketing_consent=true", "risk_level != high"]

        # 限制默认值
        limit = "每客户最多领取1次"

        return {
            "benefit_type": benefit_type,
            "benefit_name": benefit_name,
            "eligibility": eligibility,
            "limit": limit,
        }

    def _convert_channel_routing(self, channels_data: List[Dict]) -> List[Dict[str, Any]]:
        """转换为 channel_routing，按 budget_share 降序编号"""
        if not channels_data:
            return [
                {"channel": "app_push", "budget_ratio": 1.0, "contact_order": 1, "retry_rule": "无"}
            ]

        sorted_channels = sorted(channels_data, key=lambda c: float(c.get("budget_share", 0)), reverse=True)
        result = []
        total_share = sum(float(c.get("budget_share", 0)) for c in sorted_channels) or 1.0

        for idx, ch in enumerate(sorted_channels, 1):
            raw_channel = ch.get("channel", "")
            channel_name = _CHANNEL_NAME_MAP.get(raw_channel.lower(), raw_channel)
            budget_ratio = float(ch.get("budget_share", 0)) / total_share if total_share > 0 else 0.0
            role = ch.get("role", "")
            retry_rule = self._build_retry_rule(role, channel_name)
            result.append({
                "channel": channel_name,
                "budget_ratio": round(budget_ratio, 4),
                "contact_order": idx,
                "retry_rule": retry_rule,
            })

        # 归一化处理（确保总和=1.0）
        total = sum(r["budget_ratio"] for r in result)
        if total > 0 and abs(total - 1.0) > 0.001:
            for r in result:
                r["budget_ratio"] = round(r["budget_ratio"] / total, 4)
        return result

    def _build_retry_rule(self, role: str, channel_name: str) -> str:
        """根据角色和渠道生成重试规则"""
        if channel_name == "app_push":
            return "24小时未点击后切换短信"
        if channel_name == "sms":
            return "命中频控则跳过"
        if channel_name == "wechat":
            return "仅高价值客户触达"
        return role or "无"

    def _convert_content_brief(self, content_data: Dict, intent_data: Dict) -> Dict[str, Any]:
        """转换为 content_brief"""
        explain = content_data.get("explain", "")
        # 从 explain 文案中提取核心信息：文案依据：xxx；重点客群：xxx；合规处理：xxx
        core_message = intent_data.get("objective", "提升转化与ROI")
        if "文案依据：" in explain:
            parts = explain.split("；")
            for part in parts:
                if part.startswith("文案依据："):
                    core_message = part.replace("文案依据：", "").strip()
                    break

        # 默认披露项
        required_disclosure = ["活动规则以页面展示为准", "短信需包含退订方式"]
        if "合规处理：" in explain:
            compliance_part = ""
            parts = explain.split("；")
            for part in parts:
                if part.startswith("合规处理："):
                    compliance_part = part.replace("合规处理：", "").strip()
                    break
            if compliance_part:
                # 把合规处理项加入披露
                for item in compliance_part.split("、"):
                    item = item.strip()
                    if item and item not in required_disclosure:
                        required_disclosure.append(item)

        return {
            "core_message": core_message,
            "tone": "专业、克制、合规",
            "personalization_fields": ["customer_name", "available_benefit", "valid_period"],
            "required_disclosure": required_disclosure,
        }

    def _convert_compliance_guard(self, compliance_data: List[Dict], request_data: Dict) -> Dict[str, Any]:
        """转换为 compliance_guard"""
        blocked_words = ["稳赚", "保证", "无条件", "最高收益", "无条件通过"]
        must_not_claim = ["承诺一定省钱", "承诺审批通过"]

        # 频率限制：从 frequency_level 推断
        freq_level = int(request_data.get("frequency_level", 2))
        freq_map = {1: "7天最多触达1次", 2: "7天最多触达2次", 3: "7天最多触达3次", 4: "3天最多触达2次"}
        frequency_limit = freq_map.get(freq_level, "7天最多触达2次")

        # 扫描 compliance 列表中是否有"拦截"的内容合规项，提取命中词
        for item in compliance_data:
            if isinstance(item, dict) and item.get("item") == "内容合规" and item.get("status") == "拦截":
                detail = item.get("detail", "")
                if "命中：" in detail:
                    words_str = detail.replace("命中：", "").strip()
                    for w in words_str.split(","):
                        w = w.strip()
                        if w and w not in blocked_words:
                            blocked_words.append(w)

        return {
            "blocked_words": blocked_words,
            "must_not_claim": must_not_claim,
            "frequency_limit": frequency_limit,
            "age_restriction": 18,
        }

    def _convert_experiment_plan(self, experiment_data: Dict) -> Dict[str, Any]:
        """转换为 experiment_plan"""
        control_str = experiment_data.get("control_group", "10%")
        try:
            control_ratio = float(control_str.replace("%", "").strip()) / 100.0
        except (ValueError, AttributeError):
            control_ratio = 0.1
        test_ratio = round(1.0 - control_ratio, 4)
        success_metrics = experiment_data.get("success_metrics", ["conversion_rate", "roi", "complaint_rate"])
        return {
            "control_group_ratio": round(control_ratio, 4),
            "test_group_ratio": test_ratio,
            "success_metrics": success_metrics,
        }


strategy_agent_adapter = StrategyAgentAdapter()