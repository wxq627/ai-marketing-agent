from __future__ import annotations

import json
import os
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse
from urllib.parse import parse_qs, unquote

from ai_marketing.models import CampaignRequest
from ai_marketing.candidates import StrategyCandidateService
from ai_marketing.historical_model_scoring import HistoricalModelScoreProvider
from ai_marketing.pd_risk_scoring import PDRiskScoreProvider
from ai_marketing.project1_api_data import Project1ApiKnowledgeData
from ai_marketing.llm_adapter import parse_campaign_goal
from ai_marketing.orchestrator import MarketingDecisionEngine
from ai_marketing.personalization import PersonalizedStrategyService
from ai_marketing.storage import PlanRepository
from ai_marketing.feedback_simulator import simulate_strategy_feedback
from ai_marketing.strategy_copilot import answer_follow_up, draft_channel_content, review_strategy
from ai_marketing.strategy_package import build_optimized_strategy_package, build_strategy_package, summarize_feedback
from ai_marketing.strategy_catalog import export_published_strategy_catalog


BASE_DIR = Path(__file__).resolve().parent
WEB_DIR = BASE_DIR / "web"
DATA_DIR = BASE_DIR / "data"
CATALOG_EXPORT_PATH = Path(
    os.getenv(
        "STRATEGY_CATALOG_EXPORT_PATH",
        str(BASE_DIR.parents[1] / "shared" / "published_strategy_catalog.json"),
    )
)

engine = MarketingDecisionEngine()
knowledge_data = Project1ApiKnowledgeData()
repo = PlanRepository(DATA_DIR / "marketing_demo.sqlite3")
personalization = PersonalizedStrategyService(knowledge_data, engine, repo=repo)
historical_model_scores = HistoricalModelScoreProvider()
pd_risk_scores = PDRiskScoreProvider()
candidates = StrategyCandidateService(
    knowledge_data,
    engine,
    model_scores=historical_model_scores,
    pd_risk_scores=pd_risk_scores,
)


class MarketingHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(WEB_DIR), **kwargs)

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path.startswith("/api/strategy/customers/") and path.endswith("/published-context"):
            self._handle_published_strategy_context(path)
            return
        if path.startswith("/api/strategy/customers/") and path.endswith("/recommendations"):
            self._handle_personalized_recommendations(path)
            return
        if path.startswith("/api/strategy/publications/") and path.endswith("/package"):
            self._handle_published_strategy_package(path)
            return
        if path == "/api/strategy/publications":
            self._handle_strategy_publications()
            return
        if path == "/api/strategy/feedback":
            self._handle_strategy_feedback_list()
            return
        if path == "/api/strategy/campaigns":
            self._handle_strategy_campaigns()
            return
        if path == "/api/strategy/integration-status":
            self._json_response({"project1": knowledge_data.check_upstream()})
            return
        if path == "/api/activities":
            self._json_response({"items": repo.list_recent()})
            return
        if path == "/health":
            self._json_response({"status": "ok", "project1": knowledge_data.integration_status})
            return
        return super().do_GET()

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        if path == "/api/strategy/decision":
            self._handle_personalized_decision()
            return
        if path == "/api/strategy/candidates/real-data":
            self._handle_real_data_candidates()
            return
        if path == "/api/strategy/model-scores/real-data":
            self._handle_real_data_model_scores()
            return
        if path == "/api/strategy/optimize/real-data":
            self._handle_real_data_optimization()
            return
        if path == "/api/strategy/publications":
            self._handle_strategy_publish()
            return
        if path == "/api/strategy/publications/archive":
            self._handle_strategy_archive()
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
        if path == "/api/strategy/copilot/review":
            self._handle_copilot_review()
            return
        if path == "/api/strategy/copilot/question":
            self._handle_copilot_question()
            return
        if path == "/api/strategy/copilot/content":
            self._handle_copilot_content()
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
            self._attach_displayable_published_strategy(
                result,
                oneid,
                product=_optional_text(query.get("product", [""])[0]),
                as_of=_optional_text(query.get("as_of", [""])[0]),
                channel=_normalize_c_feedback_channel(str(query.get("channel", [""])[0])),
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
            if result.get("should_recommend"):
                result["published_strategy_context"] = self._published_context_for_oneid(
                    oneid,
                    product=_strategy_product_hint(
                        str(payload.get("product_id", "")),
                        str(payload.get("user_intent", "")),
                        str(payload.get("conversation_summary", "")),
                    ),
                    as_of=_optional_text(payload.get("as_of")),
                    channel=_normalize_c_feedback_channel(str(payload.get("touchpoint", ""))),
                )
            else:
                result["published_strategy_context"] = []
            self._json_response(result)
        except KeyError as exc:
            self._json_response({"error": str(exc)}, status=404)
        except PermissionError as exc:
            self._json_response({"should_recommend": False, "reason": str(exc)}, status=200)
        except (TypeError, ValueError) as exc:
            self._json_response({"error": str(exc)}, status=400)
        except Exception as exc:
            self._json_response({"error": str(exc)}, status=500)

    def _attach_displayable_published_strategy(
        self,
        result: dict[str, Any],
        oneid: str,
        *,
        product: str = "",
        as_of: str = "",
        channel: str = "",
    ) -> None:
        """Attach campaign context only when C is allowed to display a recommendation."""
        can_display = (
            result.get("status") == "success"
            and result.get("eligible_for_personalization") is True
            and result.get("eligible_for_marketing") is True
            and bool(result.get("recommendations"))
        )
        if not can_display:
            result["published_strategy_context"] = []
            result["published_strategy"] = None
            return

        contexts = self._published_context_for_oneid(oneid, product=product, as_of=as_of, channel=channel)
        result["published_strategy_context"] = contexts
        result["published_strategy"] = (
            {
                "campaign_id": contexts[0].get("campaign_id"),
                "strategy_version": contexts[0].get("strategy_version"),
            }
            if contexts
            else None
        )

    def _handle_published_strategy_context(self, path: str) -> None:
        try:
            prefix = "/api/strategy/customers/"
            oneid = unquote(path[len(prefix) : -len("/published-context")]).strip("/")
            query = parse_qs(urlparse(self.path).query)
            contexts = self._published_context_for_oneid(
                oneid,
                product=_optional_text(query.get("product", [""])[0]),
                as_of=_optional_text(query.get("as_of", [""])[0]),
                channel=_normalize_c_feedback_channel(str(query.get("channel", [""])[0])),
            )
            delivery_status = _published_strategy_delivery_status(
                personalization.recommendations(oneid, scene="published_context", limit=1),
                in_published_strategy=bool(contexts),
            )
            for context in contexts:
                context.update(delivery_status)
            self._json_response(
                {
                    "oneid": oneid,
                    **delivery_status,
                    "strategy_context": contexts,
                }
            )
        except KeyError as exc:
            self._json_response({"error": str(exc)}, status=404)
        except (TypeError, ValueError) as exc:
            self._json_response({"error": str(exc)}, status=400)
        except Exception as exc:
            self._json_response({"error": str(exc)}, status=500)

    def _handle_strategy_publications(self) -> None:
        try:
            query = parse_qs(urlparse(self.path).query)
            self._json_response(
                {
                    "items": repo.list_publications(
                        status=_optional_text(query.get("status", [""])[0]),
                        limit=int(query.get("limit", [50])[0]),
                    )
                }
            )
        except (TypeError, ValueError) as exc:
            self._json_response({"error": str(exc)}, status=400)
        except Exception as exc:
            self._json_response({"error": str(exc)}, status=500)

    def _handle_published_strategy_package(self, path: str) -> None:
        try:
            prefix = "/api/strategy/publications/"
            strategy_version = unquote(path[len(prefix) : -len("/package")]).strip("/")
            if not strategy_version:
                self._json_response({"error": "strategy_version is required"}, status=400)
                return
            package = repo.get_published_package(strategy_version)
            publication = repo.get_publication(strategy_version)
            if package is None or publication is None:
                self._json_response({"error": "published_strategy_not_found"}, status=404)
                return
            package["publication"] = publication
            self._json_response(package)
        except Exception as exc:
            self._json_response({"error": str(exc)}, status=500)

    def _handle_strategy_campaigns(self) -> None:
        try:
            self._json_response({"items": candidates.campaign_options()})
        except Exception as exc:
            self._json_response({"error": str(exc)}, status=500)

    def _handle_strategy_publish(self) -> None:
        try:
            payload = self._read_json_body()
            campaign_id = _optional_text(payload.get("campaign_id"))
            if not campaign_id:
                self._json_response({"error": "campaign_id is required"}, status=400)
                return
            publication = repo.publish(
                campaign_id,
                effective_from=_optional_text(payload.get("effective_from")),
                effective_to=_optional_text(payload.get("effective_to")),
            )
            catalog_export = export_published_strategy_catalog(repo, CATALOG_EXPORT_PATH)
            self._json_response({"publication": publication, "catalog_export": catalog_export})
        except KeyError as exc:
            self._json_response({"error": str(exc)}, status=404)
        except ValueError as exc:
            self._json_response({"error": str(exc)}, status=400)
        except Exception as exc:
            self._json_response({"error": str(exc)}, status=500)

    def _handle_strategy_archive(self) -> None:
        try:
            payload = self._read_json_body()
            strategy_version = _optional_text(payload.get("strategy_version"))
            if not strategy_version:
                self._json_response({"error": "strategy_version is required"}, status=400)
                return
            publication = repo.archive(strategy_version)
            catalog_export = export_published_strategy_catalog(repo, CATALOG_EXPORT_PATH)
            self._json_response({"publication": publication, "catalog_export": catalog_export})
        except KeyError as exc:
            self._json_response({"error": str(exc)}, status=404)
        except Exception as exc:
            self._json_response({"error": str(exc)}, status=500)

    def _handle_real_data_candidates(self) -> None:
        try:
            payload = self._read_json_body()
            customer_limit = payload.get("customer_limit")
            result = candidates.generate(
                customer_limit=_optional_int(customer_limit),
                sample_limit=int(payload.get("sample_limit", 100)),
                include_blocked=payload.get("include_blocked") is True,
                campaign_id=_optional_text(payload.get("campaign_id")),
                include_model_scores=payload.get("include_model_scores") is True,
                evaluation_time=_optional_text(payload.get("evaluation_time")),
            )
            self._json_response(result)
        except (TypeError, ValueError) as exc:
            self._json_response({"error": str(exc)}, status=400)
        except Exception as exc:
            self._json_response({"error": str(exc)}, status=500)

    def _handle_real_data_model_scores(self) -> None:
        try:
            payload = self._read_json_body()
            customer_id = _optional_text(payload.get("customer_id"))
            oneid = _optional_text(payload.get("oneid"))
            if not customer_id and oneid:
                customer_id = knowledge_data.customer_id_for_oneid(oneid)
            if not customer_id:
                self._json_response({"error": "customer_id or oneid is required"}, status=400)
                return
            campaign_id = _optional_text(payload.get("campaign_id"))
            if not campaign_id:
                self._json_response({"error": "campaign_id is required"}, status=400)
                return
            channel = _optional_text(payload.get("channel")) or "app_push"
            self._json_response(
                historical_model_scores.score(
                    customer_id=customer_id,
                    campaign_id=campaign_id,
                    channel=channel,
                    touch_time=_optional_text(payload.get("evaluation_time")),
                )
            )
        except KeyError as exc:
            self._json_response({"error": str(exc)}, status=404)
        except (TypeError, ValueError) as exc:
            self._json_response({"error": str(exc)}, status=400)
        except Exception as exc:
            self._json_response({"error": str(exc)}, status=500)

    def _handle_real_data_optimization(self) -> None:
        try:
            payload = self._read_json_body()
            campaign_id = _optional_text(payload.get("campaign_id"))
            if not campaign_id:
                self._json_response({"error": "campaign_id is required"}, status=400)
                return
            budget = float(payload.get("budget", 0))
            if budget <= 0:
                self._json_response({"error": "budget must be positive"}, status=400)
                return
            result = candidates.optimize(
                campaign_id=campaign_id,
                budget=budget,
                customer_limit=_optional_int(payload.get("customer_limit")),
                selected_sample_limit=int(payload.get("selected_sample_limit", 100)),
                evaluation_time=_optional_text(payload.get("evaluation_time")),
                target_segment=str(payload.get("target_segment", "auto")),
                target_segments=_optional_text_list(payload.get("target_segments")) or None,
                operator_filters=_optional_operator_filters(payload.get("operator_filters")),
                channel_mode=str(payload.get("channel_mode", "omni")),
                channel_coverage_trial=bool(payload.get("channel_coverage_trial", False)),
            )
            operator_content = payload.get("operator_content")
            editable_content = operator_content if isinstance(operator_content, dict) else None
            offline_feedback_simulation = simulate_strategy_feedback(
                campaign_id=campaign_id,
                selected_candidates=result["_selected_candidates"],
                operator_content=editable_content,
                benefit_cost_trigger=str(result["campaign_context"].get("benefit_cost_trigger", "conversion")),
            )
            strategy_package = build_optimized_strategy_package(
                result,
                operator_content=editable_content,
                copilot_review=payload.get("copilot_review") if isinstance(payload.get("copilot_review"), dict) else None,
                offline_feedback_simulation=offline_feedback_simulation,
            )
            result.pop("_selected_candidates", None)
            repo.save_optimized_draft(
                campaign_id=campaign_id,
                strategy_package=strategy_package,
                selection_summary=result["selection_summary"],
            )
            repo.save_feedback(
                {
                    "source": "offline_simulation",
                    "event_type": "simulated_abtest_aggregate",
                    "campaign_id": campaign_id,
                    "event_time": _optional_text(payload.get("evaluation_time")) or "",
                    "experiment": offline_feedback_simulation["experiment"],
                    "feedback_metrics": offline_feedback_simulation["feedback_metrics"],
                    "groups": offline_feedback_simulation["groups"],
                    "uplift": offline_feedback_simulation["uplift"],
                }
            )
            result["offline_feedback_simulation"] = offline_feedback_simulation
            result["strategy_draft"] = {
                "campaign_id": campaign_id,
                "status": "draft",
                "publish_endpoint": "/api/strategy/publications",
            }
            self._json_response(result)
        except (TypeError, ValueError) as exc:
            self._json_response({"error": str(exc)}, status=400)
        except RuntimeError as exc:
            self._json_response({"error": str(exc)}, status=503)
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
            package = build_strategy_package(plan)
            repo.save(plan, package)
            self._json_response(
                {
                    "plan": plan.to_dict(),
                    "strategy_package": package,
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
            insight = knowledge_data.build_customer_insight(
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
            insight = knowledge_data.build_customer_insight(
                campaign_id="LOCAL_REAL_DATA",
                target_product=strategy_request.product,
                evaluation_time=payload.get("evaluation_time"),
            )
            plan = engine.generate_plan_from_knowledge_insight(strategy_request, insight)
            package = build_strategy_package(plan)
            repo.save(plan, package)
            self._json_response(
                {
                    "source": insight["source"],
                    "data_version": insight["data_version"],
                    "goal_parsing": goal_parsing,
                    "plan": plan.to_dict(),
                    "strategy_package": package,
                }
            )
        except ValueError as exc:
            self._json_response({"error": str(exc)}, status=400)
        except Exception as exc:
            self._json_response({"error": str(exc)}, status=500)

    def _handle_strategy_parse_goal(self) -> None:
        try:
            request_payload = self._read_json_body()
            defaults = _campaign_request_from_payload(request_payload)
            result = parse_campaign_goal(defaults.goal, defaults)
            campaign_options = candidates.campaign_options()
            payload = result.to_dict()
            payload["suggested_campaign_id"] = _suggest_campaign_id(
                defaults.goal,
                result.campaign_request.product,
                _optional_text(request_payload.get("campaign_id")),
                campaign_options,
            )
            payload["suggested_target_segment"] = _suggest_target_segment(defaults.goal)
            self._json_response(payload)
        except ValueError as exc:
            self._json_response({"error": str(exc)}, status=400)
        except Exception as exc:
            self._json_response({"error": str(exc)}, status=500)

    def _handle_copilot_review(self) -> None:
        try:
            payload = self._read_json_body()
            configuration, channel_metrics = _copilot_context(payload)
            self._json_response(
                review_strategy(
                    goal=str(payload.get("goal", "")),
                    configuration=configuration,
                    channel_metrics=channel_metrics,
                )
            )
        except ValueError as exc:
            self._json_response({"error": str(exc)}, status=400)
        except Exception as exc:
            self._json_response({"error": str(exc)}, status=500)

    def _handle_copilot_question(self) -> None:
        try:
            payload = self._read_json_body()
            configuration, channel_metrics = _copilot_context(payload)
            self._json_response(
                answer_follow_up(
                    question=str(payload.get("question", "")),
                    suggestion=str(payload.get("suggestion", "")),
                    configuration=configuration,
                    channel_metrics=channel_metrics,
                )
            )
        except ValueError as exc:
            self._json_response({"error": str(exc)}, status=400)
        except Exception as exc:
            self._json_response({"error": str(exc)}, status=500)

    def _handle_copilot_content(self) -> None:
        try:
            payload = self._read_json_body()
            configuration, _channel_metrics = _copilot_context(payload)
            channel_mode = str(configuration.get("channel_mode", ""))
            channels = [] if channel_mode == "omni" else channel_mode.split("_")
            self._json_response(draft_channel_content(configuration=configuration, channels=channels))
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
            package = build_strategy_package(plan)
            repo.save(plan, package)
            self._json_response(package)
        except Exception as exc:
            self._json_response({"error": str(exc)}, status=500)

    def _handle_strategy_feedback(self) -> None:
        try:
            payload = self._read_json_body()
            raw_event_type = str(payload.get("event_type", "")).strip()
            event_type = _normalize_c_feedback_event(raw_event_type)
            channel = _normalize_c_feedback_channel(str(payload.get("channel", "")))
            if event_type != raw_event_type:
                payload["raw_event_type"] = raw_event_type
                payload["event_type"] = event_type
            if channel:
                payload["channel"] = channel
            oneid = str(payload.get("oneid", "")).strip()
            campaign_id = str(payload.get("campaign_id", "")).strip()
            if event_type == "unsubscribed" and not (oneid and campaign_id and channel):
                self._json_response(
                    {"error": "oneid, campaign_id, and channel are required for an unsubscribe event"},
                    status=400,
                )
                return
            storage_result = repo.save_feedback(payload)

            if event_type == "unsubscribed":
                repo.suppress_campaign_channel(oneid, campaign_id, channel, event_type)
            delivery_policy = (
                repo.channel_delivery_state(oneid, campaign_id, channel)
                if oneid and campaign_id and channel
                else {"allowed": None, "reason": "missing_delivery_scope"}
            )

            self._json_response(
                {
                    "storage": storage_result,
                    "summary": summarize_feedback(payload),
                    "delivery_policy": delivery_policy,
                }
            )
        except Exception as exc:
            self._json_response({"error": str(exc)}, status=500)

    def _handle_strategy_feedback_list(self) -> None:
        try:
            query = parse_qs(urlparse(self.path).query)
            self._json_response(
                {
                    "items": repo.list_feedback(
                        strategy_version=_optional_text(query.get("strategy_version", [""])[0]),
                        campaign_id=_optional_text(query.get("campaign_id", [""])[0]),
                        limit=int(query.get("limit", [100])[0]),
                    )
                }
            )
        except (TypeError, ValueError) as exc:
            self._json_response({"error": str(exc)}, status=400)
        except Exception as exc:
            self._json_response({"error": str(exc)}, status=500)

    def _read_campaign_request(self) -> CampaignRequest:
        payload = self._read_json_body()
        return _campaign_request_from_payload(payload)

    @staticmethod
    def _published_context_for_oneid(
        oneid: str,
        *,
        product: str | None,
        as_of: str | None,
        channel: str = "",
    ) -> list[dict]:
        customer_id = knowledge_data.customer_id_for_oneid(oneid)
        if customer_id is None:
            raise KeyError("unknown_oneid")
        suppressed_campaigns = repo.get_suppressed_campaigns(oneid)
        contexts = repo.published_context_for_customer(
            customer_id=customer_id,
            product=product,
            as_of=as_of,
        )
        result = []
        for context in contexts:
            campaign_id = str(context.get("campaign_id", ""))
            if campaign_id in suppressed_campaigns:
                continue
            if channel:
                delivery_policy = repo.channel_delivery_state(oneid, campaign_id, channel, as_of=as_of)
                if not delivery_policy["allowed"]:
                    continue
                context = {**context, "delivery_policy": delivery_policy}
            result.append(context)
        return result

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

    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-store")
        super().end_headers()


def _optional_int(value: object) -> int | None:
    if value is None:
        return None
    return int(value)


def _optional_text(value: object) -> str | None:
    text = str(value or "").strip()
    return text or None


def _published_strategy_delivery_status(
    recommendation_result: dict,
    *,
    in_published_strategy: bool,
) -> dict[str, object]:
    """Describe whether a published strategy can be displayed right now.

    A strategy version can still cover a customer after the customer's current
    consent or marketing eligibility has changed. The strategy record remains
    auditable, while the recommendation endpoint remains the final display gate.
    """
    can_display = (
        in_published_strategy
        and recommendation_result.get("status") == "success"
        and recommendation_result.get("eligible_for_personalization") is True
        and recommendation_result.get("eligible_for_marketing") is True
        and bool(recommendation_result.get("recommendations"))
    )
    if can_display:
        block_reason = None
    elif not in_published_strategy:
        block_reason = "no_active_published_strategy"
    else:
        block_reason = recommendation_result.get("reason_code") or "published_strategy_not_deliverable"
    return {
        "in_published_strategy": in_published_strategy,
        "deliverable_now": can_display,
        "block_reason": block_reason,
    }


def _optional_text_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return list(dict.fromkeys(str(item).strip() for item in value if str(item).strip()))


def _optional_operator_filters(value: object) -> dict[str, object] | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError("operator_filters must be an object")
    return value


def _strategy_product_hint(product_id: str, user_intent: str, conversation_summary: str) -> str | None:
    if product_id.strip():
        return product_id
    if "\u5206\u671f" in f"{user_intent}{conversation_summary}":
        return "installment"
    return None


def _normalize_c_feedback_event(event_type: str) -> str:
    """Normalize the current C-side feedback contract: detail, ignore, unsubscribe."""
    normalized = event_type.strip().casefold().replace("-", "_").replace(" ", "_")
    detail_aliases = {
        "detail",
        "details",
        "view_detail",
        "view_details",
        "click",
        "clicked",
        "查看详情",
        "详情",
    }
    ignore_aliases = {
        "ignore",
        "ignored",
        "not_interested",
        "notinterested",
        "不感兴趣",
        "忽略",
    }
    if normalized in detail_aliases:
        return "view_detail"
    if normalized in ignore_aliases:
        return "ignored"
    if normalized in {"unsubscribe", "unsubscribed", "退订"}:
        return "unsubscribed"
    return normalized


def _normalize_c_feedback_channel(channel: str) -> str:
    normalized = channel.strip().casefold().replace("-", "_").replace(" ", "_")
    aliases = {
        "app": "app_push",
        "app_push": "app_push",
        "push": "app_push",
        "短信": "sms",
        "sms": "sms",
        "微信": "wechat",
        "微信公众号": "wechat",
        "wechat": "wechat",
        "邮件": "email",
        "email": "email",
        "电话": "phone",
        "电话外呼": "phone",
        "phone": "phone",
        "in_app": "in_app",
    }
    return aliases.get(normalized, normalized)


def _suggest_campaign_id(
    goal: str,
    product: str,
    default_campaign_id: str | None,
    campaign_options: list[dict[str, str]],
) -> str | None:
    normalized_goal = goal.lower()
    for option in campaign_options:
        campaign_id = str(option.get("campaign_id", ""))
        campaign_name = str(option.get("campaign_name", ""))
        if campaign_id.lower() in normalized_goal or campaign_name.lower() in normalized_goal:
            return campaign_id

    # Explicit activity words are stronger evidence than a broad LLM product label.
    campaign_name_hints = (
        (("618",), ("618",)),
        (("双11", "双十一"), ("双11", "双十一")),
        (("暑期", "夏季", "夏日"), ("暑期", "夏季", "夏日")),
        (("春节", "新春"), ("春节", "新春")),
        (("开学",), ("开学",)),
        (("国庆",), ("国庆",)),
        (("生日",), ("生日",)),
        (("跨境", "境外"), ("跨境", "境外")),
        (("观影", "电影"), ("观影",)),
        (("亲子",), ("亲子",)),
        (("绿色",), ("绿色",)),
        (("云闪付",), ("云闪付",)),
        (("apple pay",), ("apple pay",)),
    )
    for goal_hints, name_hints in campaign_name_hints:
        if not any(hint in normalized_goal for hint in goal_hints):
            continue
        for option in campaign_options:
            campaign_name = str(option.get("campaign_name", "")).lower()
            if any(hint in campaign_name for hint in name_hints):
                return str(option["campaign_id"])

    category_by_product = {
        "installment": "分期",
        "coupon": "消费",
        "travel": "出行",
    }
    expected_category = category_by_product.get(product)
    for option in campaign_options:
        if option.get("benefit_category") == expected_category:
            return str(option["campaign_id"])
    return default_campaign_id or (str(campaign_options[0]["campaign_id"]) if campaign_options else None)


def _suggest_target_segment(goal: str) -> str:
    text = goal.lower()
    if any(word in text for word in ("沉睡", "唤醒", "召回", "低活")):
        return "dormant"
    if any(word in text for word in ("高价值", "高消费", "高净值", "优质")):
        return "high_value"
    if any(word in text for word in ("高意图", "意向", "分期意图", "权益意图")):
        return "high_intent"
    if any(word in text for word in ("高活跃", "活跃客户", "app活跃", "app 活跃")):
        return "high_activity"
    if any(word in text for word in ("消费增长", "增长客户", "消费上升")):
        return "spend_growth"
    if any(word in text for word in ("权益敏感", "优惠敏感", "领券", "优惠券")):
        return "benefit_sensitive"
    if any(word in text for word in ("低风险", "优质低风险")):
        return "low_risk"
    if any(word in text for word in ("年轻", "青年", "校园", "新户")):
        return "young_new"
    return "auto"


def _copilot_context(payload: dict) -> tuple[dict, dict]:
    campaign_id = _optional_text(payload.get("campaign_id")) or ""
    campaign_options = candidates.campaign_options()
    campaign = next(
        (item for item in campaign_options if item.get("campaign_id") == campaign_id),
        {},
    )
    channel_context = knowledge_data.build_customer_insight(limit=1).get("channel_context", {})
    configuration = {
        "campaign_id": campaign_id,
        "campaign_name": campaign.get("campaign_name", campaign_id),
        "budget_wan": payload.get("budget_wan", payload.get("budget", 0)),
        "target_segment": str(payload.get("target_segment", "auto")),
        "target_segments": _optional_text_list(payload.get("target_segments")),
        "operator_filters": _optional_operator_filters(payload.get("operator_filters")) or {},
        "channel_mode": str(payload.get("channel_mode", "omni")),
        "operator_goal": str(payload.get("operator_goal", payload.get("goal", ""))),
        "channel_coverage_trial": payload.get("channel_coverage_trial") is True,
    }
    return configuration, channel_context.get("channel_metrics", {})


def _campaign_request_from_payload(payload: dict) -> CampaignRequest:
    return CampaignRequest(
        goal=str(payload.get("goal", "")),
        product=str(payload.get("product", "installment")),
        product_locked=payload.get("product_locked") is True,
        channel_mode=str(payload.get("channel_mode", "omni")),
        budget_wan=int(payload.get("budget_wan", 80)),
        risk_level=int(payload.get("risk_level", 2)),
        frequency_level=int(payload.get("frequency_level", 2)),
    )


def main() -> None:
    print("Warming historical model features...")
    historical_model_scores.warm_up()
    pd_risk_scores.warm_up()
    port = int(os.getenv("PORT", "8765"))
    server = ThreadingHTTPServer(("0.0.0.0", port), MarketingHandler)
    print(f"AI marketing MVP running at http://127.0.0.1:{port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
