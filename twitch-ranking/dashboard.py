import glob
import os
from datetime import datetime

import pandas as pd
import streamlit as st
import plotly.express as px

# このファイル(dashboard.py)が置いてあるフォルダを基準に data を見る
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")


def load_history():
    """data/ 以下の Twitch 履歴データをまとめて読み込む"""

    if not os.path.isdir(DATA_DIR):
        # data がそもそも存在しない場合
        return None, "data フォルダが見つかりません。ダッシュボードと同じ階層に data/ を置いてください。"

    pattern = os.path.join(DATA_DIR, "twitch_ranking_*.csv")
    files = sorted(glob.glob(pattern))

    if not files:
        # data/ はあるが、CSV が無い
        return None, "data/ フォルダに twitch_ranking_*.csv がありません。履歴CSVをGitHubにアップしてください。"

    records = []
    for path in files:
        filename = os.path.basename(path)
        tag = filename.replace("twitch_ranking_", "").replace(".csv", "")

        # ファイル名の日時部分を解析
        try:
            snapshot = datetime.strptime(tag, "%Y-%m-%d_%H-%M")
        except ValueError:
            return None, f"ファイル名 {filename} の日時部分が想定外です。（twitch_ranking_YYYY-MM-DD_HH-MM.csv の形式にしてください）"

        df = pd.read_csv(path)

        # 必須カラムチェック
        required_cols = {"rank", "name", "streamers", "viewers"}
        missing = required_cols - set(df.columns)
        if missing:
            return None, f"CSV {filename} に必要なカラム {missing} がありません。収集スクリプト側の出力形式を確認してください。"

        df["snapshot"] = snapshot
        records.append(df)

    df_all = pd.concat(records, ignore_index=True)
    df_all["snapshot"] = pd.to_datetime(df_all["snapshot"])
    df_all["competition_index"] = df_all["viewers"] / df_all["streamers"].replace(0, 1)

    return df_all, None


def classify_market(df: pd.DataFrame) -> pd.DataFrame:
    """カテゴリを市場タイプ（成長・衰退・飽和など）に分類"""
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

        result.append(
            {
                "カテゴリ": name,
                "市場タイプ": status,
                "配信者推移": d_streamers,
                "視聴者推移": d_viewers,
                "最新視聴者数": last["viewers"],
                "最新配信者数": last["streamers"],
                "競争率（視聴÷配信）": round(
                    last["viewers"] / max(last["streamers"], 1), 2
                ),
            }
        )

    return pd.DataFrame(result).sort_values("最新視聴者数", ascending=False)


def main():
    st.set_page_config(page_title="Twitch カテゴリ分析ダッシュボード", layout="wide")
    st.title("📊 Twitch カテゴリ分析ダッシュボード")

    df, error_msg = load_history()

    if error_msg:
        st.error(error_msg)
        st.stop()

    latest_snap = df["snapshot"].max()
    st.subheader(f"📌 最新データ取得日時： {latest_snap.strftime('%Y-%m-%d %H:%M')}")

    # サイドバー
    st.sidebar.header("⚙️ 表示設定")
    metric = st.sidebar.selectbox(
        "表示する指標",
        ["viewers", "streamers", "competition_index"],
        format_func=lambda m: {
            "viewers": "👀 視聴者数",
            "streamers": "🎤 配信者数",
            "competition_index": "⚔ 競争率（視聴者 ÷ 配信者）",
        }[m],
    )
    top_n = st.sidebar.slider("表示カテゴリ数", 5, 50, 20)

    # 最新スナップショットで上位カテゴリ抽出
    latest = (
        df[df["snapshot"] == latest_snap]
        .sort_values(metric, ascending=False)
        .head(top_n)
    )
    selected = latest["name"].tolist()
    df_view = df[df["name"].isin(selected)]

    # トレンドグラフ
    st.subheader(f"📈 上位 {top_n} カテゴリの推移（{metric}）")
    trend = df_view.pivot_table(index="snapshot", columns="name", values=metric)
    fig_line = px.line(
        trend,
        markers=True,
        labels={"snapshot": "日時", "value": "値", "variable": "カテゴリ"},
        title="カテゴリ推移グラフ",
    )
    fig_line.update_layout(height=400)
    st.plotly_chart(fig_line, use_container_width=True)

    # 市場分類
    st.subheader("🧠 市場タイプ分類（伸びやすさ判定）")
    market_df = classify_market(df)

    section_list = [
        ("💎 狙い目（需要 > 供給）", "💎"),
        ("🚀 成長市場（視聴者↑ 配信者↑）", "🚀"),
        ("⚠ 過剰供給（飽和状態）", "⚠"),
        ("📉 衰退市場（視聴者↓ 配信者↓）", "📉"),
        ("😐 安定市場（横ばい）", "😐"),
    ]

    for section, key in section_list:
        subset = market_df[market_df["市場タイプ"].str.startswith(key)]
        if not subset.empty:
            st.markdown(f"### {section}")
            st.dataframe(subset.reset_index(drop=True))

    # バブルチャート
    st.subheader("🫧 市場ポジションマップ（視聴者×配信者×競争率）")
    fig_bubble = px.scatter(
        latest,
        x="streamers",
        y="viewers",
        size="competition_index",
        color="competition_index",
        hover_name="name",
        labels={
            "streamers": "配信者数",
            "viewers": "視聴者数",
            "competition_index": "競争率（視聴者 ÷ 配信者）",
        },
        title="カテゴリ分布バブルチャート",
        size_max=60,
        color_continuous_scale="Turbo",
    )
    fig_bubble.update_layout(height=450)
    st.plotly_chart(fig_bubble, use_container_width=True)

    # ヒートマップ
    st.subheader("🔥 視聴者数ヒートマップ（時間推移）")
    heatmap = df_view.pivot_table(
        index="name", columns="snapshot", values="viewers", fill_value=0
    )
    fig_heatmap = px.imshow(
        heatmap,
        aspect="auto",
        color_continuous_scale="Inferno",
        labels={"color": "視聴者数"},
        title="カテゴリ × 時間 の視聴者数推移",
    )
    st.plotly_chart(fig_heatmap, use_container_width=True)

    st.success("💡『伸びやすいカテゴリ』の目安 → 💎 狙い目 ＋ 🚀 成長市場 あたり。")


if __name__ == "__main__":
    main()
