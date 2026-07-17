from __future__ import annotations

import json
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse
from urllib.parse import parse_qs, unquote

from ai_marketing.models import CampaignRequest
from ai_marketing.local_knowledge_data import LocalKnowledgeData
from ai_marketing.llm_adapter import parse_campaign_goal
from ai_marketing.orchestrator import MarketingDecisionEngine
from ai_marketing.personalization import PersonalizedStrategyService
from ai_marketing.storage import PlanRepository
from ai_marketing.strategy_package import build_strategy_package, summarize_feedback


BASE_DIR = Path(__file__).resolve().parent
WEB_DIR = BASE_DIR / "web"
DATA_DIR = BASE_DIR / "data"

engine = MarketingDecisionEngine()
local_knowledge_data = LocalKnowledgeData()
repo = PlanRepository(DATA_DIR / "marketing_demo.sqlite3")
personalization = PersonalizedStrategyService(local_knowledge_data, engine)


class MarketingHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(WEB_DIR), **kwargs)

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path.startswith("/api/strategy/customers/") and path.endswith("/recommendations"):
            self._handle_personalized_recommendations(path)
            return
        if path == "/api/activities":
            self._json_response({"items": repo.list_recent()})
            return
        if path == "/health":
            self._json_response({"status": "ok"})
            return
        return super().do_GET()

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        if path == "/api/strategy/decision":
            self._handle_personalized_decision()
            return
        if path == "/api/generate":
            self._handle_legacy_generate()
            return
        if path == "/api/strategy/generate":
            self._handle_strategy_generate()
            return
        if path == "/api/strategy/generate-from-insight":
            self._handle_strategy_generate_from_insight()
            return
        if path == "/api/strategy/eligibility":
            self._handle_strategy_eligibility()
            return
        if path == "/api/strategy/eligibility/real-data":
            self._handle_real_data_eligibility()
            return
        if path == "/api/strategy/generate/real-data":
            self._handle_real_data_strategy_generate()
            return
        if path == "/api/strategy/parse-goal":
            self._handle_strategy_parse_goal()
            return
        if path == "/api/strategy/feedback":
            self._handle_strategy_feedback()
            return
        if path == "/api/strategy/package":
            self._handle_strategy_package()
            return
        self.send_error(404, "Not found")

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def _handle_personalized_recommendations(self, path: str) -> None:
        try:
            prefix = "/api/strategy/customers/"
            oneid = unquote(path[len(prefix) : -len("/recommendations")]).strip("/")
            query = parse_qs(urlparse(self.path).query)
            result = personalization.recommendations(
                oneid,
                scene=str(query.get("scene", ["agent_home"])[0]),
                limit=int(query.get("limit", [5])[0]),
            )
            self._json_response(result)
        except KeyError as exc:
            self._json_response({"error": str(exc)}, status=404)
        except PermissionError as exc:
            self._json_response({"error": str(exc), "recommendations": []}, status=200)
        except (TypeError, ValueError) as exc:
            self._json_response({"error": str(exc)}, status=400)
        except Exception as exc:
            self._json_response({"error": str(exc)}, status=500)

    def _handle_personalized_decision(self) -> None:
        try:
            payload = self._read_json_body()
            oneid = str(payload.get("oneid", "")).strip()
            if not oneid:
                self._json_response({"error": "oneid is required"}, status=400)
                return
            result = personalization.decision(
                oneid,
                scene=str(payload.get("scene", "chat")),
                user_intent=str(payload.get("user_intent", "")),
                product_id=str(payload.get("product_id", "")),
                conversation_summary=str(payload.get("conversation_summary", "")),
                touchpoint=str(payload.get("touchpoint", "in_app")),
            )
            self._json_response(result)
        except KeyError as exc:
            self._json_response({"error": str(exc)}, status=404)
        except PermissionError as exc:
            self._json_response({"should_recommend": False, "reason": str(exc)}, status=200)
        except (TypeError, ValueError) as exc:
            self._json_response({"error": str(exc)}, status=400)
        except Exception as exc:
            self._json_response({"error": str(exc)}, status=500)

    def _handle_legacy_generate(self) -> None:
        try:
            request = self._read_campaign_request()
            if not request.goal.strip():
                self._json_response({"error": "goal is required"}, status=400)
                return
            plan = engine.generate_plan(request)
            repo.save(plan)
            self._json_response(plan.to_dict())
        except Exception as exc:
            self._json_response({"error": str(exc)}, status=500)

    def _handle_strategy_generate(self) -> None:
        try:
            request = self._read_campaign_request()
            if not request.goal.strip():
                self._json_response({"error": "goal is required"}, status=400)
                return
            plan = engine.generate_plan(request)
            repo.save(plan)
            self._json_response(
                {
                    "plan": plan.to_dict(),
                    "strategy_package": build_strategy_package(plan),
                }
            )
        except Exception as exc:
            self._json_response({"error": str(exc)}, status=500)

    def _handle_strategy_generate_from_insight(self) -> None:
        try:
            payload = self._read_json_body()
            request_payload = payload.get("campaign_request", {})
            insight_payload = payload.get("customer_insight", {})
            request = CampaignRequest(
                goal=str(request_payload.get("goal", "")),
                product=str(request_payload.get("product", insight_payload.get("target_product", "installment"))),
                channel_mode=str(request_payload.get("channel_mode", "omni")),
                budget_wan=int(request_payload.get("budget_wan", 80)),
                risk_level=int(request_payload.get("risk_level", 2)),
                frequency_level=int(request_payload.get("frequency_level", 2)),
            )
            if not request.goal.strip():
                self._json_response({"error": "goal is required"}, status=400)
                return
            eligibility = engine.assess_knowledge_insight(insight_payload)
            plan = engine.generate_plan_from_knowledge_insight(request, insight_payload)
            repo.save(plan)
            self._json_response(
                {
                    "plan": plan.to_dict(),
                    "strategy_package": build_strategy_package(plan),
                    "eligibility": eligibility.to_dict(),
                    "source": "knowledge_insight",
                }
            )
        except Exception as exc:
            self._json_response({"error": str(exc)}, status=500)

    def _handle_strategy_eligibility(self) -> None:
        try:
            payload = self._read_json_body()
            customer_insight = payload.get("customer_insight", payload)
            report = engine.assess_knowledge_insight(customer_insight)
            self._json_response(report.to_dict())
        except Exception as exc:
            self._json_response({"error": str(exc)}, status=400)

    def _handle_real_data_eligibility(self) -> None:
        try:
            payload = self._read_json_body()
            insight = local_knowledge_data.build_customer_insight(
                campaign_id=str(payload.get("campaign_id", "LOCAL_REAL_DATA")),
                target_product=str(payload.get("target_product", "installment")),
                evaluation_time=payload.get("evaluation_time"),
                limit=_optional_int(payload.get("limit")),
            )
            report = engine.assess_knowledge_insight(insight)
            report_payload = report.to_dict()
            decisions = report_payload.pop("decisions")
            include_decisions = payload.get("include_decisions") is True
            report_payload["decision_sample"] = decisions if include_decisions else decisions[:20]
            report_payload["decision_total"] = len(decisions)
            self._json_response(
                {
                    "source": insight["source"],
                    "data_version": insight["data_version"],
                    "report": report_payload,
                }
            )
        except (TypeError, ValueError) as exc:
            self._json_response({"error": str(exc)}, status=400)
        except Exception as exc:
            self._json_response({"error": str(exc)}, status=500)

    def _handle_real_data_strategy_generate(self) -> None:
        try:
            payload = self._read_json_body()
            request = _campaign_request_from_payload(payload)
            if payload.get("goal_parsed") is True:
                strategy_request = request
                goal_parsing = {
                    "campaign_request": strategy_request.__dict__,
                    "audience_hints": [],
                    "constraints": [],
                    "source": "client",
                    "model": None,
                    "fallback_reason": None,
                }
            else:
                parsed_goal = parse_campaign_goal(request.goal, request)
                strategy_request = parsed_goal.campaign_request
                goal_parsing = parsed_goal.to_dict()
            insight = local_knowledge_data.build_customer_insight(
                campaign_id="LOCAL_REAL_DATA",
                target_product=strategy_request.product,
                evaluation_time=payload.get("evaluation_time"),
            )
            plan = engine.generate_plan_from_knowledge_insight(strategy_request, insight)
            repo.save(plan)
            self._json_response(
                {
                    "source": insight["source"],
                    "data_version": insight["data_version"],
                    "goal_parsing": goal_parsing,
                    "plan": plan.to_dict(),
                    "strategy_package": build_strategy_package(plan),
                }
            )
        except ValueError as exc:
            self._json_response({"error": str(exc)}, status=400)
        except Exception as exc:
            self._json_response({"error": str(exc)}, status=500)

    def _handle_strategy_parse_goal(self) -> None:
        try:
            defaults = self._read_campaign_request()
            result = parse_campaign_goal(defaults.goal, defaults)
            self._json_response(result.to_dict())
        except ValueError as exc:
            self._json_response({"error": str(exc)}, status=400)
        except Exception as exc:
            self._json_response({"error": str(exc)}, status=500)

    def _handle_strategy_package(self) -> None:
        try:
            request = self._read_campaign_request()
            if not request.goal.strip():
                self._json_response({"error": "goal is required"}, status=400)
                return
            plan = engine.generate_plan(request)
            repo.save(plan)
            self._json_response(build_strategy_package(plan))
        except Exception as exc:
            self._json_response({"error": str(exc)}, status=500)

    def _handle_strategy_feedback(self) -> None:
        try:
            payload = self._read_json_body()
            self._json_response(summarize_feedback(payload))
        except Exception as exc:
            self._json_response({"error": str(exc)}, status=500)

    def _read_campaign_request(self) -> CampaignRequest:
        payload = self._read_json_body()
        return _campaign_request_from_payload(payload)

    def _read_json_body(self) -> dict:
        body = self.rfile.read(int(self.headers.get("Content-Length", "0"))).decode("utf-8")
        return json.loads(body or "{}")

    def log_message(self, format: str, *args) -> None:
        return

    def _json_response(self, data: dict, status: int = 200) -> None:
        encoded = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(encoded)


def _optional_int(value: object) -> int | None:
    if value is None:
        return None
    return int(value)


def _campaign_request_from_payload(payload: dict) -> CampaignRequest:
    return CampaignRequest(
        goal=str(payload.get("goal", "")),
        product=str(payload.get("product", "installment")),
        channel_mode=str(payload.get("channel_mode", "omni")),
        budget_wan=int(payload.get("budget_wan", 80)),
        risk_level=int(payload.get("risk_level", 2)),
        frequency_level=int(payload.get("frequency_level", 2)),
    )


def main() -> None:
    server = ThreadingHTTPServer(("127.0.0.1", 8765), MarketingHandler)
    print("AI marketing MVP running at http://127.0.0.1:8765")
    server.serve_forever()


if __name__ == "__main__":
    main()
