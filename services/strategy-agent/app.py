from __future__ import annotations

import json
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from ai_marketing.models import CampaignRequest
from ai_marketing.orchestrator import MarketingDecisionEngine
from ai_marketing.storage import PlanRepository
from ai_marketing.strategy_package import build_strategy_package, summarize_feedback


BASE_DIR = Path(__file__).resolve().parent
WEB_DIR = BASE_DIR / "web"
DATA_DIR = BASE_DIR / "data"

engine = MarketingDecisionEngine()
repo = PlanRepository(DATA_DIR / "marketing_demo.sqlite3")


class MarketingHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(WEB_DIR), **kwargs)

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/api/activities":
            self._json_response({"items": repo.list_recent()})
            return
        if path == "/health":
            self._json_response({"status": "ok"})
            return
        return super().do_GET()

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        if path == "/api/generate":
            self._handle_legacy_generate()
            return
        if path == "/api/strategy/generate":
            self._handle_strategy_generate()
            return
        if path == "/api/strategy/generate-from-insight":
            self._handle_strategy_generate_from_insight()
            return
        if path == "/api/strategy/feedback":
            self._handle_strategy_feedback()
            return
        if path == "/api/strategy/package":
            self._handle_strategy_package()
            return
        self.send_error(404, "Not found")

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
            plan = engine.generate_plan_from_knowledge_insight(request, insight_payload)
            repo.save(plan)
            self._json_response(
                {
                    "plan": plan.to_dict(),
                    "strategy_package": build_strategy_package(plan),
                    "source": "knowledge_insight",
                }
            )
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
        return CampaignRequest(
            goal=str(payload.get("goal", "")),
            product=str(payload.get("product", "installment")),
            channel_mode=str(payload.get("channel_mode", "omni")),
            budget_wan=int(payload.get("budget_wan", 80)),
            risk_level=int(payload.get("risk_level", 2)),
            frequency_level=int(payload.get("frequency_level", 2)),
        )

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
        self.end_headers()
        self.wfile.write(encoded)


def main() -> None:
    server = ThreadingHTTPServer(("127.0.0.1", 8765), MarketingHandler)
    print("AI marketing MVP running at http://127.0.0.1:8765")
    server.serve_forever()


if __name__ == "__main__":
    main()
