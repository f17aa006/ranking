import glob
import os
from datetime import datetime

import pandas as pd
import streamlit as st
import plotly.express as px

DATA_DIR = "data"


def load_history():
    """
    data/ 以下の Twitch 履歴データをまとめて読み込む。
    何かおかしかったら None を返しつつ画面に詳細を出す。
    """
    st.write("📁 現在の作業ディレクトリ:", os.getcwd())

    # ルートにあるファイルとフォルダ一覧
    st.write("📂 カレントディレクトリの中身:", os.listdir())

    # data フォルダがあるかチェック
    if not os.path.isdir(DATA_DIR):
        st.error(f"data フォルダが見つかりません。期待するパス: '{DATA_DIR}'")
        return None

    st.write("📂 data フォルダの中身:", os.listdir(DATA_DIR))

    pattern = os.path.join(DATA_DIR, "twitch_ranking_*.csv")
    files = sorted(glob.glob(pattern))

    st.write("🔍 マッチしたCSV一覧（pattern =", pattern, "）:", files)

    if not files:
        st.error(
            "data/ フォルダにはありますが、"
            "`twitch_ranking_*.csv` というファイル名のCSVが見つかりません。\n"
            "→ ファイル名が `twitch_ranking_YYYY-MM-DD_HH-MM.csv` 形式になっているか確認してください。"
        )
        return None

    records = []
    try:
        for path in files:
            filename = os.path.basename(path)
            tag = filename.replace("twitch_ranking_", "").replace(".csv", "")
            st.write("⏰ ファイルから日時タグを解析中:", filename, "→", tag)

            snapshot = datetime.strptime(tag, "%Y-%m-%d_%H-%M")

            df = pd.read_csv(path)
            st.write("✅ 読み込んだCSVのカラム:", df.columns.tolist())

            # 必須カラム確認
            required_cols = {"rank", "name", "streamers", "viewers"}
            missing = required_cols - set(df.columns)
            if missing:
                st.error(f"CSV {filename} に必要なカラム {missing} がありません。")
                return None

            df["snapshot"] = snapshot
            records.append(df)

    except Exception as e:
        st.error(f"CSV 読み込み中に例外が発生しました: {e}")
        return None

    try:
        df_all = pd.concat(records, ignore_index=True)
        df_all["snapshot"] = pd.to_datetime(df_all["snapshot"])
        df_all["competition_index"] = df_all["viewers"] / df_all["streamers"].replace(0, 1)
    except Exception as e:
        st.error(f"履歴データ結合・加工中に例外が発生しました: {e}")
        return None

    return df_all


def classify_market(df):
    """カテゴリを『伸び傾向・衰退傾向・飽和状態』などに分類"""
    result = []

    for name, g in df.groupby("name"):
        g = g.sort_values("snapshot")
        first, last = g.iloc[0], g.iloc[-1]

        d_streamers = last["streamers"] - first["streamers"]
        d_viewers = last["viewers"] - first["viewers"]

        # 市場タイプ分類
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
    st.title("📊 Twitch カテゴリ分析ダッシュボード（日本語版・デバッグ表示）")

    df = load_history()

    # ここまででエラーが出ていたら df は None になっている
    if df is None:
        st.stop()

    # ここから先は、df が正しく読み込めた前提
    latest_snap = df["snapshot"].max()
    st.subheader(f"📌 最新データ取得日時： {latest_snap.strftime('%Y-%m-%d %H:%M')}")

    # ---- サイドバー ----
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

    # 最新ランキング（指標順）
    latest = df[df["snapshot"] == latest_snap].sort_values(metric, ascending=False).head(top_n)
    selected = latest["name"].tolist()
    df_view = df[df["name"].isin(selected)]

    # ---- トレンドライン ----
    st.subheader(f"📈 上位 {top_n} カテゴリの推移（{metric}）")
    try:
        trend = df_view.pivot_table(index="snapshot", columns="name", values=metric)
        fig_line = px.line(
            trend,
            markers=True,
            labels={"snapshot": "日時", "value": "値", "variable": "カテゴリ"},
            title="カテゴリ推移グラフ"
        )
        fig_line.update_layout(height=400)
        st.plotly_chart(fig_line, use_container_width=True)
    except Exception as e:
        st.error(f"トレンドグラフ描画中にエラー: {e}")

    # ---- 市場分類 ----
    st.subheader("🧠 市場タイプ分類（伸びやすさ判定）")

    try:
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
    except Exception as e:
        st.error(f"市場分類処理中にエラー: {e}")

    # ---- バブルチャート ----
    st.subheader("🫧 市場ポジションマップ（視聴者×配信者×競争率）")
    try:
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
                "competition_index": "競争率（視聴者 ÷ 配信者）"
            },
            title="カテゴリ分布バブルチャート",
            size_max=60,
            color_continuous_scale="Turbo",
        )
        fig_bubble.update_layout(height=450)
        st.plotly_chart(fig_bubble, use_container_width=True)
    except Exception as e:
        st.error(f"バブルチャート描画中にエラー: {e}")

    # ---- ヒートマップ ----
    st.subheader("🔥 視聴者数ヒートマップ（時間推移）")
    try:
        heatmap = df_view.pivot_table(index="name", columns="snapshot", values="viewers", fill_value=0)
        fig_heatmap = px.imshow(
            heatmap,
            aspect="auto",
            color_continuous_scale="Inferno",
            labels={"color": "視聴者数"},
            title="カテゴリ × 時間 の視聴者数推移"
        )
        st.plotly_chart(fig_heatmap, use_container_width=True)
    except Exception as e:
        st.error(f"ヒートマップ描画中にエラー: {e}")

    st.success("💡『伸びやすいカテゴリ』＝ 💎 狙い目 または 🚀 成長市場 です。")


if __name__ == "__main__":
    main()
