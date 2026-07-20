from __future__ import annotations

import json
import os
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from ai_marketing.models import CampaignRequest
from ai_marketing.orchestrator import MarketingDecisionEngine
from ai_marketing.storage import PlanRepository
from ai_marketing.callback import push_to_marketing_agent


BASE_DIR = Path(__file__).resolve().parent
WEB_DIR = BASE_DIR / "web"
DATA_DIR = BASE_DIR / "data"
FEEDBACK_DIR = BASE_DIR / "feedback"
FEEDBACK_DIR.mkdir(exist_ok=True)

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
        if path == "/api/feedback/list":
            self._handle_list_feedbacks()
            return
        if path.startswith("/api/feedback/"):
            feedback_id = path.split("/")[-1]
            self._handle_get_feedback(feedback_id)
            return
        return super().do_GET()

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        if path == "/api/generate":
            self._handle_generate()
            return
        if path == "/api/feedback":
            self._handle_receive_feedback()
            return
        self.send_error(404, "Not found")

    def _handle_generate(self) -> None:
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
            plan_dict = plan.to_dict()
            push_to_marketing_agent(plan_dict)
            self._json_response(plan_dict)
        except Exception as exc:
            self._json_response({"error": str(exc)}, status=500)

    def _handle_receive_feedback(self) -> None:
        try:
            body = self.rfile.read(int(self.headers.get("Content-Length", "0"))).decode("utf-8")
            data = json.loads(body or "{}")

            if not data.get("campaign_id"):
                self._json_response({"code": -1, "message": "campaign_id 必填"}, status=400)
                return

            from datetime import datetime
            feedback_id = f"FBK-{datetime.now().strftime('%Y%m%d%H%M%S')}"
            file_path = FEEDBACK_DIR / f"{feedback_id}.json"

            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

            print(f"策略反馈接收成功: campaign_id={data['campaign_id']}, feedback_id={feedback_id}")

            self._json_response({
                "code": 0,
                "message": "策略反馈数据接收成功",
                "feedback_id": feedback_id,
                "received_at": datetime.now().isoformat()
            })

        except Exception as exc:
            print(f"策略反馈接收失败: {exc}")
            self._json_response({"code": -1, "message": str(exc)}, status=500)

    def _handle_list_feedbacks(self) -> None:
        try:
            feedbacks = []
            for filename in os.listdir(FEEDBACK_DIR):
                if filename.endswith(".json"):
                    file_path = FEEDBACK_DIR / filename
                    with open(file_path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    feedbacks.append({
                        "feedback_id": filename.replace(".json", ""),
                        "campaign_id": data.get("campaign_id", ""),
                        "oneid": data.get("oneid", ""),
                        "timestamp": data.get("timestamp", filename)
                    })
            self._json_response({"feedbacks": feedbacks})
        except Exception as exc:
            self._json_response({"code": -1, "message": str(exc)}, status=500)

    def _handle_get_feedback(self, feedback_id: str) -> None:
        try:
            file_path = FEEDBACK_DIR / f"{feedback_id}.json"
            if not file_path.exists():
                self._json_response({"code": -1, "message": "反馈记录不存在"}, status=404)
                return

            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            self._json_response(data)
        except Exception as exc:
            self._json_response({"code": -1, "message": str(exc)}, status=500)

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
