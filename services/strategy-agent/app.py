from __future__ import annotations

import json
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from ai_marketing.models import CampaignRequest
from ai_marketing.orchestrator import MarketingDecisionEngine
from ai_marketing.storage import PlanRepository


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
        if path != "/api/generate":
            self.send_error(404, "Not found")
            return

        try:
            body = self.rfile.read(int(self.headers.get("Content-Length", "0"))).decode("utf-8")
            payload = json.loads(body or "{}")
            request = CampaignRequest(
                goal=str(payload.get("goal", "")),
                product=str(payload.get("product", "installment")),
                channel_mode=str(payload.get("channel_mode", "omni")),
                budget_wan=int(payload.get("budget_wan", 80)),
                risk_level=int(payload.get("risk_level", 2)),
                frequency_level=int(payload.get("frequency_level", 2)),
            )
            if not request.goal.strip():
                self._json_response({"error": "goal is required"}, status=400)
                return
            plan = engine.generate_plan(request)
            repo.save(plan)
            self._json_response(plan.to_dict())
        except Exception as exc:
            self._json_response({"error": str(exc)}, status=500)

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
