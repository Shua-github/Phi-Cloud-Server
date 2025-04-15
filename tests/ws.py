import asyncio
import requests
import websockets
from urllib.parse import quote


BASE_URL = "http://localhost:443"
WS_BASE_URL = "ws://localhost:443"


def extract_routes(openapi_json: dict) -> list[str]:
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


async def run_ws_client(ws_url):
    print(f"[连接 WebSocket]: {ws_url}")
    async with websockets.connect(ws_url) as websocket:
        print("[已连接 WebSocket，开始监听事件]\n")
        try:
            while True:
                message = await websocket.recv()
                print("[事件推送]", message)
        except Exception as e:
            print("[连接已关闭]", str(e))


def main():
    response = requests.get(f"{BASE_URL}/openapi.json")
    response.raise_for_status()
    openapi_data = response.json()

    routes = extract_routes(openapi_data)
    route_string = format_route_subscription(routes)
    print("\n[订阅路由]:", route_string)

    ws_path = f"/ws/event?routes={quote(route_string)}"
    ws_url = f"{WS_BASE_URL}{ws_path}"

    asyncio.run(run_ws_client(ws_url))


if __name__ == "__main__":
    main()
