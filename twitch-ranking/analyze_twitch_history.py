import glob
import os
from datetime import datetime

import matplotlib.pyplot as plt
import pandas as pd

DATA_DIR = r"C:\Users\user\Documents\GitHub\ranking\twitch-ranking\data"



def load_history(data_dir=DATA_DIR):
    """
    data/ 配下の twitch_ranking_*.csv を全部読み込んで
    1つの DataFrame にまとめる
    """
    pattern = os.path.join(data_dir, "twitch_ranking_*.csv")
    files = sorted(glob.glob(pattern))

    records = []

    for path in files:
        filename = os.path.basename(path)
        # twitch_ranking_YYYY-MM-DD_HH-MM.csv から日時部分を抜く
        tag = filename.replace("twitch_ranking_", "").replace(".csv", "")
        snapshot = datetime.strptime(tag, "%Y-%m-%d_%H-%M")

        df = pd.read_csv(path)
        # rank,name,streamers,viewers,avg_viewers_per_stream
        df["snapshot"] = snapshot
        records.append(df)

    if not records:
        raise RuntimeError("data/ に履歴CSVがありません。まず収集スクリプトを動かして。")

    all_df = pd.concat(records, ignore_index=True)
    return all_df


def prepare_metrics(df):
    """
    基本的なメトリクス列を整える
    """
    df = df.copy()
    df["snapshot"] = pd.to_datetime(df["snapshot"])
    df["competition_index"] = df.apply(
        lambda r: r["viewers"] / r["streamers"] if r["streamers"] > 0 else 0, axis=1
    )
    return df


def plot_viewers_trend_top10(df, output="viewers_trend_top10.png"):
    """
    視聴者数トップ10カテゴリの視聴者数推移ラインチャート
    """
    latest_snap = df["snapshot"].max()
    latest = df[df["snapshot"] == latest_snap]
    top10_names = (
        latest.sort_values("viewers", ascending=False)
        .head(10)["name"]
        .tolist()
    )

    sub = df[df["name"].isin(top10_names)]

    plt.figure(figsize=(14, 6))
    for name in top10_names:
        tmp = sub[sub["name"] == name].sort_values("snapshot")
        plt.plot(tmp["snapshot"], tmp["viewers"], marker="o", label=name)

    plt.xlabel("Time")
    plt.ylabel("Total Viewers")
    plt.title("Top 10 Categories Viewers Trend")
    plt.legend()
    plt.tight_layout()
    plt.savefig(output)
    plt.close()
    print(f"📊 視聴者数推移(Top10) グラフ保存: {output}")


def make_heatmap_data_top50(df, output_csv="heatmap_top50_viewers.csv"):
    """
    ヒートマップ用に TOP50カテゴリ × 時間 の視聴者数をピボットしたCSVを吐く
    （グラフは自分でExcel / スプシ / Pythonで描けるようにする）
    """
    latest_snap = df["snapshot"].max()
    latest = df[df["snapshot"] == latest_snap]
    top50_names = (
        latest.sort_values("viewers", ascending=False)
        .head(50)["name"]
        .tolist()
    )

    sub = df[df["name"].isin(top50_names)]
    # 行: カテゴリ, 列: snapshot, 値: viewers
    pivot = sub.pivot_table(
        index="name",
        columns="snapshot",
        values="viewers",
        aggfunc="sum",
        fill_value=0,
    )

    pivot.to_csv(output_csv, encoding="utf-8-sig")
    print(f"📄 ヒートマップ用CSV保存: {output_csv}")


def detect_struggling_categories(df, output_csv="struggling_categories.csv"):
    """
    「配信者数は増えたのに視聴者数は減ったカテゴリ」を抽出
    -> 伸び悩みカテゴリとして出力
    """
    df = df.sort_values("snapshot")

    result_rows = []
    for name, g in df.groupby("name"):
        first = g.iloc[0]
        last = g.iloc[-1]

        streamers_first = first["streamers"]
        streamers_last = last["streamers"]
        viewers_first = first["viewers"]
        viewers_last = last["viewers"]

        if streamers_last > streamers_first and viewers_last < viewers_first:
            result_rows.append(
                {
                    "name": name,
                    "first_snapshot": first["snapshot"],
                    "last_snapshot": last["snapshot"],
                    "streamers_first": streamers_first,
                    "streamers_last": streamers_last,
                    "viewers_first": viewers_first,
                    "viewers_last": viewers_last,
                    "delta_streamers": streamers_last - streamers_first,
                    "delta_viewers": viewers_last - viewers_first,
                }
            )

    if not result_rows:
        print("伸び悩みカテゴリは検出されませんでした。")
        return

    out_df = pd.DataFrame(result_rows).sort_values(
        ["delta_viewers", "delta_streamers"], ascending=[True, False]
    )
    out_df.to_csv(output_csv, index=False, encoding="utf-8-sig")
    print(f"⚠ 伸び悩みカテゴリ一覧CSV保存: {output_csv}")


def main():
    df = load_history()
    df = prepare_metrics(df)

    # 1) Top10視聴者推移グラフ
    plot_viewers_trend_top10(df, output="viewers_trend_top10.png")

    # 2) Top50視聴者数ヒートマップ用データ
    make_heatmap_data_top50(df, output_csv="heatmap_top50_viewers.csv")

    # 3) 伸び悩みカテゴリ検出
    detect_struggling_categories(df, output_csv="struggling_categories.csv")

    print("✅ 解析完了")


if __name__ == "__main__":
    main()
