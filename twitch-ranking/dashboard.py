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
        return None, "data フォルダが見つかりません。ダッシュボードと同じ階層に data/ を置いてください。"

    pattern = os.path.join(DATA_DIR, "twitch_ranking_*.csv")
    files = sorted(glob.glob(pattern))

    if not files:
        return None, "data/ フォルダに twitch_ranking_*.csv がありません。履歴CSVを GitHub にアップしてください。"

    records = []
    for path in files:
        filename = os.path.basename(path)
        tag = filename.replace("twitch_ranking_", "").replace(".csv", "")

        # ファイル名の日時部分を解析（twitch_ranking_YYYY-MM-DD_HH-MM.csv）
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

    return df_all, None


def main():
    st.set_page_config(page_title="Twitch 累計視聴者ランキング", layout="wide")
    st.title("📊 Twitch カテゴリ累計視聴者ランキング")

    df, error_msg = load_history()

    if error_msg:
        st.error(error_msg)
        st.stop()

    # ---- 基本情報 ----
    min_snap = df["snapshot"].min()
    max_snap = df["snapshot"].max()
    total_snapshots = df["snapshot"].nunique()
    total_categories = df["name"].nunique()

    st.markdown(
        f"データ期間：**{min_snap.strftime('%Y-%m-%d %H:%M')}**"
        f" ～ **{max_snap.strftime('%Y-%m-%d %H:%M')}**　"
        f"（スナップショット数：{total_snapshots}、カテゴリ数：{total_categories}）"
    )

    # ---- 累計視聴者数ランキング ----
    st.subheader("🎉 累計視聴者数ランキング（全期間）")

    # カテゴリごとの累計視聴者数を集計
    total_viewers = (
        df.groupby("name")["viewers"]
        .sum()
        .sort_values(ascending=False)
        .reset_index()
        .rename(columns={"name": "カテゴリ", "viewers": "累計視聴者数"})
    )

    # オプション：累計配信者数（参考）
    total_streamers = (
        df.groupby("name")["streamers"]
        .sum()
        .reset_index()
        .rename(columns={"name": "カテゴリ", "streamers": "累計配信者数"})
    )

    summary = pd.merge(total_viewers, total_streamers, on="カテゴリ", how="left")

    # サイドバーで何位まで見るか選択
    st.sidebar.header("⚙️ 表示設定")
    top_n = st.sidebar.slider("表示する順位（上位何カテゴリまで）", 5, 100, 20)

    show_df = summary.head(top_n)

    st.dataframe(show_df, use_container_width=True)

    # ---- バーグラフ（上位カテゴリの累計視聴者数）----
    st.subheader("📈 累計視聴者数（バーグラフ）")

    fig_bar = px.bar(
        show_df,
        x="カテゴリ",
        y="累計視聴者数",
        title=f"上位 {top_n} カテゴリの累計視聴者数",
        labels={"カテゴリ": "カテゴリ", "累計視聴者数": "累計視聴者数"},
    )
    fig_bar.update_layout(xaxis_tickangle=-45, height=500)
    st.plotly_chart(fig_bar, use_container_width=True)

    st.caption(
        "※ 累計視聴者数 = 取得した全スナップショットでの視聴者数の合計です。"
        "長期的にどのカテゴリが強いかを見る指標として使えます。"
    )


if __name__ == "__main__":
    main()
