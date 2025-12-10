import csv
import os
import time
from datetime import datetime

import requests
import matplotlib.pyplot as plt

# ===== 設定 =====
BASE_URL = "https://api.twitch.tv/helix"
TOKEN_URL = "https://id.twitch.tv/oauth2/token"

TOP_GAME_COUNT = 50  # 上位何カテゴリ取るか
OUTPUT_DIR = "data"

LATEST_CSV_NAME = "twitch_category_ranking_latest.csv"
LATEST_PNG_NAME = "twitch_top_categories_latest.png"


def get_app_access_token(client_id: str, client_secret: str) -> str:
    resp = requests.post(
        TOKEN_URL,
        params={
            "client_id": client_id,
            "client_secret": client_secret,
            "grant_type": "client_credentials",
        },
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


def build_headers(client_id: str, access_token: str):
    return {
        "Client-ID": client_id,
        "Authorization": f"Bearer {access_token}",
    }


def get_top_games(headers, limit=TOP_GAME_COUNT):
    url = f"{BASE_URL}/games/top"
    params = {"first": min(limit, 100)}
    games = []

    while len(games) < limit:
        res = requests.get(url, headers=headers, params=params, timeout=10)
        res.raise_for_status()
        data = res.json()

        games.extend(data["data"])
        cursor = data.get("pagination", {}).get("cursor")

        if not cursor or len(games) >= limit:
            break

        params["after"] = cursor
        time.sleep(0.2)

    return games[:limit]


def collect_stream_data(headers, game_id):
    """ゲームIDの配信者数と視聴者合計を返す"""
    url = f"{BASE_URL}/streams"
    params = {"game_id": game_id, "first": 100}

    total_streams = 0
    total_viewers = 0

    while True:
        response = requests.get(url, headers=headers, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()

        streams = data.get("data", [])
        total_streams += len(streams)

        # viewer_count 合計
        for stream in streams:
            total_viewers += stream.get("viewer_count", 0)

        cursor = data.get("pagination", {}).get("cursor")

        if not cursor or not streams:
            break

        params["after"] = cursor
        time.sleep(0.2)

    return total_streams, total_viewers


def build_ranking(headers):
    print(f"カテゴリ取得中…（TOP {TOP_GAME_COUNT}）")
    games = get_top_games(headers)

    ranking = []

    for i, game in enumerate(games, 1):
        print(f"[{i}/{TOP_GAME_COUNT}] {game['name']} → 取得中…", end="")
        streams, viewers = collect_stream_data(headers, game["id"])
        print(f" 配信: {streams} | 視聴者: {viewers}")

        ranking.append({
            "name": game["name"],
            "game_id": game["id"],
            "streamers": streams,
            "viewers": viewers,
        })

    # 視聴者多い順でソート
    ranking.sort(key=lambda x: x["viewers"], reverse=True)

    return ranking


def ensure_dir():
    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)


def write_csv(ranking, snapshot_tag):
    ensure_dir()

    dated = f"{OUTPUT_DIR}/twitch_ranking_{snapshot_tag}.csv"
    latest = f"{OUTPUT_DIR}/{LATEST_CSV_NAME}"

    fields = ["rank", "name", "streamers", "viewers", "avg_viewers_per_stream"]

    def write(path):
        with open(path, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fields)
            writer.writeheader()

            for i, r in enumerate(ranking, start=1):
                writer.writerow({
                    "rank": i,
                    "name": r["name"],
                    "streamers": r["streamers"],
                    "viewers": r["viewers"],
                    "avg_viewers_per_stream": round(r["viewers"] / r["streamers"], 2) if r["streamers"] else 0
                })

    write(dated)
    write(latest)

    print(f"📁 CSV保存 → {dated}")
    print(f"📁 最新CSV更新 → {latest}")


def plot_graph(ranking, snapshot_tag, top_n=10):
    ensure_dir()

    top = ranking[:top_n]

    names = [x["name"] for x in top]
    viewer_counts = [x["viewers"] for x in top]

    plt.figure(figsize=(14, 6))
    plt.bar(range(top_n), viewer_counts, color="#6441A5")
    plt.xticks(range(top_n), names, rotation=45, ha="right")
    plt.ylabel("Total Viewers")
    plt.title(f"Twitch Top {top_n} Categories by Viewers ({snapshot_tag})")

    plt.tight_layout()

    dated = f"{OUTPUT_DIR}/twitch_top_categories_{snapshot_tag}.png"
    latest = f"{OUTPUT_DIR}/{LATEST_PNG_NAME}"

    plt.savefig(dated)
    plt.savefig(latest)
    plt.close()

    print(f"📊 グラフ保存 → {dated}")
    print(f"📊 最新グラフ更新 → {latest}")


def main():
    cid = os.getenv("TWITCH_CLIENT_ID")
    secret = os.getenv("TWITCH_CLIENT_SECRET")

    if not cid or not secret:
        raise RuntimeError("環境変数 TWITCH_CLIENT_ID / TWITCH_CLIENT_SECRET がありません")

    ts = datetime.now().strftime("%Y-%m-%d_%H-%M")

    print(f"🕒 {ts} → データ取得開始")

    token = get_app_access_token(cid, secret)
    headers = build_headers(cid, token)

    ranking = build_ranking(headers)

    write_csv(ranking, ts)
    plot_graph(ranking, ts)

    print("\n🎉 完了")


if __name__ == "__main__":
    main()
