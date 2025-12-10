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

    # 競争率（視聴者 ÷ 配信者）
    df_all["competition_index"] = df_all["viewers"] / df_all["streamers"].replace(0, 1)

    return df_all, None


def build_summary(df: pd.DataFrame) -> pd.DataFrame:
    """カテゴリごとの累計・平均・最大・最新などまとめたサマリを作る"""

    # 基本集計
    agg = df.groupby("name").agg(
        累計視聴者数=("viewers", "sum"),
        累計配信者数=("streamers", "sum"),
        平均視聴者数=("viewers", "mean"),
        最大視聴者数=("viewers", "max"),
        サンプル数=("viewers", "count"),
        平均競争率=("competition_index", "mean"),
    )

    # 最初と最後のスナップショット
    first = (
        df.sort_values("snapshot")
        .groupby("name")
        .first()[["snapshot", "viewers", "streamers", "rank"]]
        .rename(
            columns={
                "snapshot": "初回取得日時",
                "viewers": "初回視聴者数",
                "streamers": "初回配信者数",
                "rank": "初回ランク",
            }
        )
    )

    last = (
        df.sort_values("snapshot")
        .groupby("name")
        .last()[["snapshot", "viewers", "streamers", "rank"]]
        .rename(
            columns={
                "snapshot": "最新取得日時",
                "viewers": "最新視聴者数",
                "streamers": "最新配信者数",
                "rank": "最新ランク",
            }
        )
    )

    summary = agg.join(first).join(last)

    # 表示用整形
    summary["平均視聴者数"] = summary["平均視聴者数"].round(1)
    summary["平均競争率"] = summary["平均競争率"].round(2)

    summary = summary.reset_index().rename(columns={"name": "カテゴリ"})

    # 累計視聴者数の降順で並べる
    summary = summary.sort_values("累計視聴者数", ascending=False).reset_index(drop=True)

    return summary


def main():
    st.set_page_config(page_title="Twitch カテゴリ分析（累計＋詳細）", layout="wide")
    st.title("📊 Twitch カテゴリ分析ダッシュボード（累計＋詳細）")

    df, error_msg = load_history()

    if error_msg:
        st.error(error_msg)
        st.stop()

    # ---- データ期間情報 ----
    min_snap = df["snapshot"].min()
    max_snap = df["snapshot"].max()
    total_snapshots = df["snapshot"].nunique()
    total_categories = df["name"].nunique()

    st.markdown(
        f"データ期間：**{min_snap.strftime('%Y-%m-%d %H:%M')}**"
        f" ～ **{max_snap.strftime('%Y-%m-%d %H:%M')}**　"
        f"（スナップショット数：{total_snapshots}、カテゴリ数：{total_categories}）"
    )

    # ---- サマリテーブル作成 ----
    summary = build_summary(df)

    # ---- サイドバー設定 ----
    st.sidebar.header("⚙️ 表示設定")

    top_n = st.sidebar.slider("ランキング表示数（上位何カテゴリまで）", 5, 100, 20)

    # カテゴリ選択（詳細表示用）
    default_category = summary.iloc[0]["カテゴリ"]
    selected_category = st.sidebar.selectbox(
        "詳細を見たいカテゴリ",
        summary["カテゴリ"].tolist(),
        index=0,
    )

    # ---- 累計ランキングテーブル ----
    st.subheader("🎉 累計視聴者数ランキング（全期間）")

    show_cols = [
        "カテゴリ",
        "累計視聴者数",
        "累計配信者数",
        "平均視聴者数",
        "最大視聴者数",
        "平均競争率",
        "サンプル数",
        "初回取得日時",
        "最新取得日時",
        "初回ランク",
        "最新ランク",
    ]

    st.dataframe(summary[show_cols].head(top_n), use_container_width=True)

    # ---- 上位カテゴリの累計視聴者数バーグラフ ----
    st.subheader("📈 上位カテゴリの累計視聴者数")

    fig_bar = px.bar(
        summary.head(top_n),
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

    # ---- 選択したカテゴリの詳細 ----
    st.subheader(f"🔍 カテゴリ詳細：{selected_category}")

    df_cat = df[df["name"] == selected_category].sort_values("snapshot")

    # サマリ行を取り出し
    cat_summary = summary[summary["カテゴリ"] == selected_category].iloc[0]

    col1, col2, col3 = st.columns(3)
    col1.metric("最新視聴者数", int(cat_summary["最新視聴者数"]))
    col2.metric("累計視聴者数", int(cat_summary["累計視聴者数"]))
    col3.metric("平均視聴者数", f"{cat_summary['平均視聴者数']:.1f}")

    col4, col5, col6 = st.columns(3)
    col4.metric("最大視聴者数", int(cat_summary["最大視聴者数"]))
    col5.metric("平均競争率", f"{cat_summary['平均競争率']:.2f}")
    col6.metric("データポイント数", int(cat_summary["サンプル数"]))

    st.markdown(
        f"- 初回取得日時：**{cat_summary['初回取得日時']}**"
        f"（ランク: {int(cat_summary['初回ランク'])}）  \n"
        f"- 最新取得日時：**{cat_summary['最新取得日時']}**"
        f"（ランク: {int(cat_summary['最新ランク'])}）"
    )

    # 時系列グラフ：視聴者数の推移
    st.subheader("📉 視聴者数の推移")

    fig_view = px.line(
        df_cat,
        x="snapshot",
        y="viewers",
        markers=True,
        labels={"snapshot": "日時", "viewers": "視聴者数"},
        title=f"{selected_category} の視聴者数推移",
    )
    fig_view.update_layout(height=400)
    st.plotly_chart(fig_view, use_container_width=True)

    # 時系列グラフ：配信者数と競争率の推移
    st.subheader("📡 配信者数・競争率の推移")

    fig_stream = px.line(
        df_cat,
        x="snapshot",
        y=["streamers", "competition_index"],
        markers=True,
        labels={
            "snapshot": "日時",
            "value": "値",
            "variable": "指標",
        },
        title=f"{selected_category} の配信者数・競争率推移",
    )
    fig_stream.update_layout(height=400)
    st.plotly_chart(fig_stream, use_container_width=True)

    # 生データの一部も見せる
    st.subheader("📄 生データ（このカテゴリの全レコード）")
    show_raw = df_cat[["snapshot", "rank", "streamers", "viewers", "competition_index"]]
    show_raw = show_raw.rename(
        columns={
            "snapshot": "日時",
            "rank": "ランク",
            "streamers": "配信者数",
            "viewers": "視聴者数",
            "competition_index": "競争率（視聴÷配信）",
        }
    )
    st.dataframe(show_raw, use_container_width=True)


if __name__ == "__main__":
    main()
