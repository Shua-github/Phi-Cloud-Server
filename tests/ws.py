from typing import Dict, List
from urllib.parse import quote

from fastapi.testclient import TestClient

from phi_cloud_server.main import app

client = TestClient(app)


def extract_routes(openapi_json: Dict) -> List[str]:
    routes = []
    for path, methods in openapi_json.get("paths", {}).items():
        for method in methods:
            method_upper = method.upper()
            route = f"{method_upper}:{path}"
            print(f"route:{route}")
            routes.append(route)
    return routes


def format_route_subscription(routes):
    return ",".join(routes)


def run_ws_client(ws_url):
    with client.websocket_connect(ws_url) as websocket:
        print("[已连接 WebSocket，开始监听事件]\n")
        try:
            while True:
                message = websocket.receive_text()
                print("[事件推送]", message)
        except Exception as e:
            print("[连接已关闭]", str(e))


def main():
    response = client.get("/openapi.json")
    response.raise_for_status()
    openapi_data = response.json()
    del response

    routes = extract_routes(openapi_data)
    route_string = format_route_subscription(routes)
    print("\n[订阅路由]:", route_string)

    ws_url = f"/ws/event?routes={quote(route_string)}"
    print("[连接 WebSocket]:", ws_url)


if __name__ == "__main__":
    main()
