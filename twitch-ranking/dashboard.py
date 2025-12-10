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


def classify_growth_type(row) -> str:
    """視聴者増加率・ランク改善・平均競争率から成長タイプをざっくり分類"""
    growth_rate = row["視聴者増加率"]  # 初回→最新の割合
    rank_improve = row["ランク改善量"]  # 正ならランクUP
    avg_comp = row["平均競争率"]

    # かなり強気な伸び
    if growth_rate > 0.8 and rank_improve > 15:
        return "🚀 急成長"
    # しっかり右肩上がり
    if growth_rate > 0.3 and rank_improve > 5:
        return "📈 成長"
    # ほぼ現状維持（微増〜微減）
    if growth_rate > -0.1:
        return "😐 横ばい"
    # 明確に落ちている
    return "📉 下降"


def build_summary(df: pd.DataFrame) -> pd.DataFrame:
    """カテゴリごとの累計・平均・最大・成長情報などまとめたサマリを作る"""

    # 基本集計＋ばらつき
    agg = df.groupby("name").agg(
        累計視聴者数=("viewers", "sum"),
        累計配信者数=("streamers", "sum"),
        平均視聴者数=("viewers", "mean"),
        最大視聴者数=("viewers", "max"),
        サンプル数=("viewers", "count"),
        平均競争率=("competition_index", "mean"),
        視聴者数標準偏差=("viewers", "std"),
    )

    # 初回
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

    # 最新
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

    # ピーク（視聴者数が最大の瞬間）
    peak_idx = df.groupby("name")["viewers"].idxmax()
    peak = (
        df.loc[peak_idx, ["name", "snapshot", "viewers"]]
        .set_index("name")
        .rename(columns={"snapshot": "ピーク日時", "viewers": "ピーク視聴者数"})
    )

    summary = agg.join(first).join(last).join(peak)

    # 派生指標
    summary["視聴者数増加量"] = summary["最新視聴者数"] - summary["初回視聴者数"]
    summary["ランク改善量"] = summary["初回ランク"] - summary["最新ランク"]  # 正数ならランクUP
    summary["視聴者増加率"] = summary["視聴者数増加量"] / summary["初回視聴者数"].replace(0, 1)

    # 成長スコア（ざっくり：増加率＋ランク改善＋競争率を混ぜたもの）
    # 係数は感覚調整用。とりあえず「伸びてて、順位も上がってて、競争率もそこそこ」のものが高く出るようにしてる。
    summary["成長スコア"] = (
        summary["視聴者増加率"] * 50
        + (summary["ランク改善量"] / summary["初回ランク"].replace(0, 1)) * 30
        + summary["平均競争率"] * 2
    )

    # 成長タイプラベル
    summary["成長タイプ"] = summary.apply(classify_growth_type, axis=1)

    # 小数処理
    summary["平均視聴者数"] = summary["平均視聴者数"].round(1)
    summary["平均競争率"] = summary["平均競争率"].round(2)
    summary["視聴者数標準偏差"] = summary["視聴者数標準偏差"].fillna(0).round(1)
    summary["視聴者増加率"] = summary["視聴者増加率"].round(2)
    summary["成長スコア"] = summary["成長スコア"].round(2)

    summary = summary.reset_index().rename(columns={"name": "カテゴリ"})

    return summary


def main():
    st.set_page_config(page_title="Twitch カテゴリ成長分析", layout="wide")
    st.title("📊 Twitch カテゴリ成長分析ダッシュボード")

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

    # ランキング基準（デフォルトは成長スコア）
    ranking_metric = st.sidebar.selectbox(
        "ランキング基準",
        [
            "成長スコア",
            "累計視聴者数",
            "平均視聴者数",
            "最大視聴者数",
            "最新視聴者数",
            "平均競争率",
            "視聴者数増加量",
            "視聴者増加率",
            "ランク改善量",
        ],
        index=0,
    )

    # 最低データ数フィルタ
    max_samples = int(summary["サンプル数"].max())
    min_samples = st.sidebar.slider("最低データ数（スナップショット数）", 1, max_samples, 3)

    # 累計視聴者数フィルタ
    min_total_viewers = st.sidebar.number_input("最低累計視聴者数", value=0, step=1000)

    # カテゴリ名フィルタ（部分一致）
    name_filter = st.sidebar.text_input("カテゴリ名フィルタ（部分一致）", "")

    # ランキング表示数
    top_n = st.sidebar.slider("ランキング表示数（上位何カテゴリまで）", 5, 100, 20)

    # ---- フィルタ適用 ----
    filtered = summary.copy()
    filtered = filtered[filtered["サンプル数"] >= min_samples]
    filtered = filtered[filtered["累計視聴者数"] >= min_total_viewers]

    if name_filter.strip():
        filtered = filtered[filtered["カテゴリ"].str.contains(name_filter, case=False, na=False)]

    if filtered.empty:
        st.warning("条件に合うカテゴリがありません。フィルタ条件を緩めてください。")
        st.stop()

    # ランキング基準でソート（大きいほど良い前提）
    filtered = filtered.sort_values(ranking_metric, ascending=False).reset_index(drop=True)

    # ---- ランキングテーブル ----
    st.subheader(f"🎉 成長ランキング（基準：{ranking_metric}）")

    show_cols = [
        "カテゴリ",
        "成長タイプ",
        "成長スコア",
        "視聴者増加量",
        "視聴者増加率",
        "ランク改善量",
        "最新視聴者数",
        "累計視聴者数",
        "平均視聴者数",
        "最大視聴者数",
        "平均競争率",
        "視聴者数標準偏差",
        "サンプル数",
        "初回取得日時",
        "最新取得日時",
        "初回ランク",
        "最新ランク",
        "ピーク視聴者数",
        "ピーク日時",
    ]

    st.dataframe(filtered[show_cols].head(top_n), use_container_width=True)

    # ---- 上位カテゴリのバーグラフ ----
    st.subheader(f"📈 上位カテゴリ（基準：{ranking_metric}）")

    fig_bar = px.bar(
        filtered.head(top_n),
        x="カテゴリ",
        y=ranking_metric,
        color="成長タイプ",
        title=f"上位 {top_n} カテゴリの {ranking_metric}",
        labels={"カテゴリ": "カテゴリ", ranking_metric: ranking_metric, "成長タイプ": "成長タイプ"},
    )
    fig_bar.update_layout(xaxis_tickangle=-45, height=500)
    st.plotly_chart(fig_bar, use_container_width=True)

    # ---- 成長タイプの説明 ----
    st.markdown(
        """
### 成長タイプの意味

- 🚀 **急成長**：視聴者増加率が大きく、ランクも大きく改善しているカテゴリ  
- 📈 **成長**：視聴者数もランクもじわじわ良くなっているカテゴリ  
- 😐 **横ばい**：大きな増減はなく、ほぼ現状維持のカテゴリ  
- 📉 **下降**：視聴者減・ランク悪化が目立つカテゴリ  
"""
    )

    # ---- 選択したカテゴリの詳細 ----
    st.subheader("🔍 カテゴリ詳細")

    selected_category = st.selectbox(
        "詳細を見たいカテゴリを選択",
        filtered["カテゴリ"].tolist(),
        index=0,
    )

    df_cat = df[df["name"] == selected_category].sort_values("snapshot")
    cat_summary = filtered[filtered["カテゴリ"] == selected_category].iloc[0]

    # 期間（Timedelta）を計算
    start_dt = cat_summary["初回取得日時"]
    end_dt = cat_summary["最新取得日時"]
    duration = end_dt - start_dt
    days = duration.days
    hours = int(duration.total_seconds() // 3600)

    # 上段メトリクス（成長系＋視聴者系）
    col1, col2, col3 = st.columns(3)
    col1.metric("成長タイプ", cat_summary["成長タイプ"])
    col2.metric("成長スコア", f"{cat_summary['成長スコア']:.2f}")
    col3.metric("視聴者増加量", int(cat_summary["視聴者数増加量"]))

    col4, col5, col6 = st.columns(3)
    col4.metric("視聴者増加率", f"{cat_summary['視聴者増加率']:.2f}")
    col5.metric("ランク改善量（+でランクUP）", int(cat_summary["ランク改善量"]))
    col6.metric("視聴者のばらつき（標準偏差）", f"{cat_summary['視聴者数標準偏差']:.1f}")

    # 下段メトリクス（最新・累計・平均・競争率・データ数）
    col7, col8, col9 = st.columns(3)
    col7.metric("最新視聴者数", int(cat_summary["最新視聴者数"]))
    col8.metric("累計視聴者数", int(cat_summary["累計視聴者数"]))
    col9.metric("平均視聴者数", f"{cat_summary['平均視聴者数']:.1f}")

    col10, col11, col12 = st.columns(3)
    col10.metric("最大視聴者数", int(cat_summary["最大視聴者数"]))
    col11.metric("平均競争率", f"{cat_summary['平均競争率']:.2f}")
    col12.metric("データ数（スナップショット数）", int(cat_summary["サンプル数"]))

    # 初回ランク・最新ランク・期間・ピーク情報
    st.markdown(
        f"- 初回取得日時：**{start_dt}**（ランク: {int(cat_summary['初回ランク'])}）  \n"
        f"- 最新取得日時：**{end_dt}**（ランク: {int(cat_summary['最新ランク'])}）  \n"
        f"- 期間：**約 {days} 日（≒ {hours} 時間）**  \n"
        f"- ピーク視聴者数：**{int(cat_summary['ピーク視聴者数'])}**"
        f"（ピーク日時: {cat_summary['ピーク日時']}）"
    )

    # ---- 視聴者数の推移グラフ ----
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

    # ---- 配信者数＆競争率の推移グラフ ----
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

    # ---- 生データ ----
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
