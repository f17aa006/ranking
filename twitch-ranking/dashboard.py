import glob
import os
from datetime import datetime

import pandas as pd
import streamlit as st
import plotly.express as px

# ★ dashboard.py があるフォルダを基準にする
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")


def load_history():
    """data/ 以下の Twitch 履歴データをまとめて読み込む"""
    st.write("📁 BASE_DIR:", BASE_DIR)
    st.write("📁 DATA_DIR:", DATA_DIR)

    if not os.path.isdir(DATA_DIR):
        st.error(f"DATA_DIR が見つかりません: {DATA_DIR}")
        return None

    st.write("📂 DATA_DIR の中身:", os.listdir(DATA_DIR))

    pattern = os.path.join(DATA_DIR, "twitch_ranking_*.csv")
    files = sorted(glob.glob(pattern))
    st.write("🔍 マッチしたCSV:", files)

    if not files:
        st.error("data/ に twitch_ranking_*.csv がありません。GitHub 上に CSV が上がっているか確認してください。")
        return None

    records = []
    for path in files:
        filename = os.path.basename(path)
        tag = filename.replace("twitch_ranking_", "").replace(".csv", "")
        st.write("⏰ 解析中ファイル:", filename, " → tag:", tag)

        snapshot = datetime.strptime(tag, "%Y-%m-%d_%H-%M")
        df = pd.read_csv(path)
        st.write("✅ カラム:", df.columns.tolist())

        # 必須カラムチェック
        required = {"rank", "name", "streamers", "viewers"}
        missing = required - set(df.columns)
        if missing:
            st.error(f"{filename} に必須カラム {missing} がありません。")
            return None

        df["snapshot"] = snapshot
        records.append(df)

    df_all = pd.concat(records, ignore_index=True)
    df_all["snapshot"] = pd.to_datetime(df_all["snapshot"])
    df_all["competition_index"] = df_all["viewers"] / df_all["streamers"].replace(0, 1)
    return df_all


def classify_market(df):
    result = []
    for name, g in df.groupby("name"):
        g = g.sort_values("snapshot")
        first, last = g.iloc[0], g.iloc[-1]

        d_streamers = last["streamers"] - first["streamers"]
        d_viewers = last["viewers"] - first["viewers"]

        if d_viewers > 0 and d_streamers < 0:
            status = "💎 狙い目（需要 > 供給）"
        elif d_viewers > 0 and d_streamers > 0:
            status = "🚀 成長市場（視聴者↑ 配信者↑）"
        elif d_viewers < 0 and d_streamers > 0:
            status = "⚠ 過剰供給（視聴者↓ 配信者↑）"
        elif d_viewers < 0 and d_streamers < 0:
            status = "📉 衰退市場（視聴者↓ 配信者↓）"
        else:
            status = "😐 安定（大きな変化なし）"

        result.append({
            "カテゴリ": name,
            "市場タイプ": status,
            "配信者推移": d_streamers,
            "視聴者推移": d_viewers,
            "最新視聴者数": last["viewers"],
            "最新配信者数": last["streamers"],
            "競争率（視聴÷配信）": round(last["viewers"] / max(last["streamers"], 1), 2),
        })

    return pd.DataFrame(result).sort_values("最新視聴者数", ascending=False)


def main():
    st.set_page_config(page_title="Twitch カテゴリ分析ダッシュボード", layout="wide")
    st.title("📊 Twitch カテゴリ分析ダッシュボード（日本語版・パスデバッグ付き）")

    df = load_history()
    if df is None:
        st.stop()

    latest_snap = df["snapshot"].max()
    st.subheader(f"📌 最新データ取得日時： {latest_snap.strftime('%Y-%m-%d %H:%M')}")

    st.sidebar.header("⚙️ 表示設定")
    metric = st.sidebar.selectbox(
        "表示する指標",
        ["viewers", "streamers", "competition_index"],
        format_func=lambda m: {
            "viewers": "👀 視聴者数",
            "streamers": "🎤 配信者数",
            "competition_index": "⚔ 競争率（視聴者 ÷ 配信者）"
        }[m],
    )
    top_n = st.sidebar.slider("表示カテゴリ数", 5, 50, 20)

    latest = df[df["snapshot"] == latest_snap].sort_values(metric, ascending=False).head(top_n)
    selected = latest["name"].tolist()
    df_view = df[df["name"].isin(selected)]

    # トレンド
    st.subheader(f"📈 上位 {top_n} カテゴリの推移（{metric}）")
    trend = df_view.pivot_table(index="snapshot", columns="name", values=metric)
    fig_line = px.line(trend, markers=True)
    st.plotly_chart(fig_line, use_container_width=True)

    # 市場分類
    st.subheader("🧠 市場タイプ分類")
    market_df = classify_market(df)
    st.dataframe(market_df)


if __name__ == "__main__":
    main()
