import os
import math
import requests
import pandas as pd
from bs4 import BeautifulSoup
import datetime as dt
from collections import Counter
from itertools import combinations

BASE_URL = "https://lotostatistika.com.hr/eurojackpot/eurojackpot-izvlacenje-arhiva.aspx?g={}"
HEADERS = {"User-Agent": "Mozilla/5.0"}


def fetch_year(year: int) -> pd.DataFrame | None:
    url = BASE_URL.format(year)
    r = requests.get(url, headers=HEADERS, timeout=30)
    if r.status_code != 200:
        return None
    soup = BeautifulSoup(r.text, "html.parser")
    table = soup.find("table")
    if table is None:
        return None
    try:
        df = pd.read_html(str(table))[0]
    except Exception:
        return None
    return df


def load_all_history() -> pd.DataFrame:
    current_year = dt.datetime.now().year
    frames = []
    for year in range(2012, current_year + 1):
        df = fetch_year(year)
        if df is not None and not df.empty:
            frames.append(df)
    if not frames:
        raise RuntimeError("Nema dohvaćenih podataka sa izvora.")

    df = pd.concat(frames, ignore_index=True)
    df["date"] = pd.to_datetime(df["Datum"], format="%d.%m.%Y", errors="coerce")
    df = df.dropna(subset=["date"]).copy()
    df = df.rename(columns={
        "Br 1": "main_1", "Br 2": "main_2", "Br 3": "main_3", "Br 4": "main_4", "Br 5": "main_5",
        "D 1": "euro_1", "D 2": "euro_2",
    })
    num_cols = ["main_1", "main_2", "main_3", "main_4", "main_5", "euro_1", "euro_2", "Kolo"]
    for c in num_cols:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.sort_values("date").reset_index(drop=True)
    return df


def subset_5y(df: pd.DataFrame) -> pd.DataFrame:
    cutoff = dt.datetime.now() - dt.timedelta(days=5 * 365)
    out = df[df["date"] >= cutoff].copy()
    if out.empty:
        raise RuntimeError("Nema podataka za zadnjih 5 godina.")
    return out.reset_index(drop=True)


def build_draw_lists(df: pd.DataFrame):
    mains = []
    euros = []
    for _, row in df.iterrows():
        mains.append(sorted([int(row[f"main_{i}"]) for i in range(1, 6)]))
        euros.append(sorted([int(row[f"euro_{i}"]) for i in range(1, 3)]))
    return mains, euros


def frequency_stats(draws, max_num):
    flat = [n for draw in draws for n in draw]
    counts = Counter(flat)
    total_draws = len(draws)
    return pd.DataFrame({
        "number": list(range(1, max_num + 1)),
        "count": [counts.get(i, 0) for i in range(1, max_num + 1)],
        "rate": [counts.get(i, 0) / total_draws for i in range(1, max_num + 1)]
    })


def gap_stats(draws, max_num):
    positions = {i: [] for i in range(1, max_num + 1)}
    for idx, draw in enumerate(draws):
        for n in draw:
            positions[n].append(idx)
    rows = []
    last_idx = len(draws) - 1
    for n in range(1, max_num + 1):
        pos = positions[n]
        if not pos:
            avg_gap = len(draws)
            current_gap = len(draws)
            max_gap = len(draws)
        elif len(pos) == 1:
            avg_gap = len(draws)
            current_gap = last_idx - pos[-1]
            max_gap = current_gap
        else:
            gaps = [b - a for a, b in zip(pos[:-1], pos[1:])]
            avg_gap = sum(gaps) / len(gaps)
            current_gap = last_idx - pos[-1]
            max_gap = max(gaps)
        overdue_ratio = current_gap / avg_gap if avg_gap and avg_gap > 0 else 1.0
        rows.append({
            "number": n,
            "avg_gap": avg_gap,
            "current_gap": current_gap,
            "max_gap": max_gap,
            "overdue_ratio": overdue_ratio
        })
    return pd.DataFrame(rows)


def recency_weighted(draws, max_num):
    weights = Counter()
    total = len(draws)
    for idx, draw in enumerate(draws):
        w = (idx + 1) / total
        for n in draw:
            weights[n] += w
    max_w = max(weights.values()) if weights else 1
    return pd.DataFrame({
        "number": list(range(1, max_num + 1)),
        "recency_weight": [weights.get(i, 0) / max_w for i in range(1, max_num + 1)]
    })


def pair_triplet_stats(draws, top_n=15):
    pair_counter = Counter()
    triplet_counter = Counter()
    for draw in draws:
        for p in combinations(sorted(draw), 2):
            pair_counter[p] += 1
        for t in combinations(sorted(draw), 3):
            triplet_counter[t] += 1
    top_pairs = pair_counter.most_common(top_n)
    top_triplets = triplet_counter.most_common(top_n)
    return top_pairs, top_triplets, pair_counter, triplet_counter


def merge_scores(freq_df, gap_df, rec_df, max_num):
    df = freq_df.merge(gap_df, on="number").merge(rec_df, on="number")
    df["freq_norm"] = df["count"] / df["count"].max() if df["count"].max() else 0
    df["overdue_norm"] = df["overdue_ratio"] / df["overdue_ratio"].max() if df["overdue_ratio"].max() else 0
    df["gap_norm"] = df["current_gap"] / df["current_gap"].max() if df["current_gap"].max() else 0

    df["score"] = (
        0.38 * df["freq_norm"] +
        0.27 * df["recency_weight"] +
        0.20 * df["overdue_norm"] +
        0.15 * df["gap_norm"]
    )
    return df.sort_values(["score", "count"], ascending=False).reset_index(drop=True)


def common_structures(main_draws):
    patterns = []
    for draw in main_draws:
        odd = sum(1 for x in draw if x % 2 == 1)
        even = 5 - odd
        low = sum(1 for x in draw if x <= 25)
        high = 5 - low
        total = sum(draw)
        consec = sum(1 for a, b in zip(draw[:-1], draw[1:]) if b - a == 1)
        patterns.append((odd, even, low, high, total, consec))
    df = pd.DataFrame(patterns, columns=["odd", "even", "low", "high", "sum", "consec"])
    odd_even = df.groupby(["odd", "even"]).size().sort_values(ascending=False)
    low_high = df.groupby(["low", "high"]).size().sort_values(ascending=False)
    sum_min = int(df["sum"].quantile(0.25))
    sum_max = int(df["sum"].quantile(0.75))
    consec_mode = int(df["consec"].mode().iloc[0])
    return odd_even, low_high, (sum_min, sum_max), consec_mode


def score_combination(combo, euro_combo, main_score_map, euro_score_map, pair_counter, triplet_counter):
    combo = sorted(combo)
    odd = sum(1 for x in combo if x % 2 == 1)
    low = sum(1 for x in combo if x <= 25)
    s = sum(combo)
    consec = sum(1 for a, b in zip(combo[:-1], combo[1:]) if b - a == 1)

    base = sum(main_score_map[x] for x in combo) + sum(euro_score_map[x] for x in euro_combo)
    pair_bonus = sum(pair_counter.get(tuple(p), 0) for p in combinations(combo, 2)) * 0.08
    triplet_bonus = sum(triplet_counter.get(tuple(t), 0) for t in combinations(combo, 3)) * 0.15

    structure_bonus = 0
    if odd in (2, 3):
        structure_bonus += 0.35
    if low in (2, 3):
        structure_bonus += 0.35
    if 90 <= s <= 170:
        structure_bonus += 0.35
    if consec <= 1:
        structure_bonus += 0.15

    return round(base + pair_bonus + triplet_bonus + structure_bonus, 4)


def generate_combinations(main_scores_df, euro_scores_df, pair_counter, triplet_counter, count=5):
    main_candidates = main_scores_df.head(14)["number"].tolist()
    euro_candidates = euro_scores_df.head(6)["number"].tolist()
    main_score_map = dict(zip(main_scores_df["number"], main_scores_df["score"]))
    euro_score_map = dict(zip(euro_scores_df["number"], euro_scores_df["score"]))

    combos = []
    for combo in combinations(main_candidates, 5):
        odd = sum(1 for x in combo if x % 2 == 1)
        low = sum(1 for x in combo if x <= 25)
        s = sum(combo)
        consec = sum(1 for a, b in zip(sorted(combo)[:-1], sorted(combo)[1:]) if b - a == 1)
        if odd not in (2, 3):
            continue
        if low not in (2, 3):
            continue
        if not (90 <= s <= 170):
            continue
        if consec > 1:
            continue
        for ecombo in combinations(euro_candidates, 2):
            sc = score_combination(combo, ecombo, main_score_map, euro_score_map, pair_counter, triplet_counter)
            combos.append((sc, sorted(combo), sorted(ecombo)))

    combos.sort(key=lambda x: x[0], reverse=True)
    selected = []
    used_signatures = set()
    for sc, combo, ecombo in combos:
        sig = (tuple(combo), tuple(ecombo))
        if sig in used_signatures:
            continue
        if any(len(set(combo) & set(existing[1])) >= 4 for existing in selected):
            continue
        selected.append((sc, combo, ecombo))
        used_signatures.add(sig)
        if len(selected) == count:
            break
    return selected


def evaluate_against_last(pred_main, pred_euro, last_main, last_euro):
    hit_main = sorted(set(pred_main) & set(last_main))
    hit_euro = sorted(set(pred_euro) & set(last_euro))
    return hit_main, hit_euro


def fmt_pairs(items):
    return ", ".join([f"{'-'.join(map(str, k))} ({v}x)" for k, v in items]) if items else "nema"


def build_messages(df5: pd.DataFrame):
    main_draws, euro_draws = build_draw_lists(df5)

    main_freq = frequency_stats(main_draws, 50)
    euro_freq = frequency_stats(euro_draws, 12)
    main_gap = gap_stats(main_draws, 50)
    euro_gap = gap_stats(euro_draws, 12)
    main_rec = recency_weighted(main_draws, 50)
    euro_rec = recency_weighted(euro_draws, 12)

    main_scores = merge_scores(main_freq, main_gap, main_rec, 50)
    euro_scores = merge_scores(euro_freq, euro_gap, euro_rec, 12)

    top_pairs, top_triplets, pair_counter, triplet_counter = pair_triplet_stats(main_draws, 8)
    euro_pairs, _, euro_pair_counter, _ = pair_triplet_stats(euro_draws, 5)

    odd_even, low_high, sum_range, consec_mode = common_structures(main_draws)

    generated = generate_combinations(main_scores, euro_scores, pair_counter, triplet_counter, count=5)
    best_main = generated[0][1]
    best_euro = generated[0][2]

    last = df5.iloc[-1]
    last_main = sorted([int(last[f"main_{i}"]) for i in range(1, 6)])
    last_euro = sorted([int(last[f"euro_{i}"]) for i in range(1, 3)])
    hit_main, hit_euro = evaluate_against_last(best_main, best_euro, last_main, last_euro)

    hot_main = ", ".join([f"{int(r.number)} ({int(r['count'])}x)" for _, r in main_scores.head(8).iterrows()])
    cold_main = ", ".join([f"{int(r.number)} ({int(r['count'])}x)" for _, r in main_scores.sort_values('count').head(8).iterrows()])
    overdue_main = ", ".join([f"{int(r.number)} (gap {int(r.current_gap)})" for _, r in main_scores.sort_values('overdue_ratio', ascending=False).head(8).iterrows()])

    hot_euro = ", ".join([f"{int(r.number)} ({int(r['count'])}x)" for _, r in euro_scores.head(5).iterrows()])
    cold_euro = ", ".join([f"{int(r.number)} ({int(r['count'])}x)" for _, r in euro_scores.sort_values('count').head(5).iterrows()])
    overdue_euro = ", ".join([f"{int(r.number)} (gap {int(r.current_gap)})" for _, r in euro_scores.sort_values('overdue_ratio', ascending=False).head(5).iterrows()])

    odd_even_top = odd_even.head(3)
    low_high_top = low_high.head(3)
    odd_even_str = ", ".join([f"{k[0]}N/{k[1]}P ({int(v)}x)" for k, v in odd_even_top.items()])
    low_high_str = ", ".join([f"{k[0]} low/{k[1]} high ({int(v)}x)" for k, v in low_high_top.items()])

    combo_lines = []
    for idx, (score, combo, ecombo) in enumerate(generated, start=1):
        combo_lines.append(f"{idx}. {', '.join(map(str, combo))} + {', '.join(map(str, ecombo))}  [score {score}]")
    combos_text = "\n".join(combo_lines)

    now = dt.datetime.now().strftime("%d.%m.%Y. %H:%M")

    prediction = (
        f"🎰 *Eurojackpot PRO Analiza*\n"
        f"Vrijeme: {now}\n"
        f"Baza: zadnjih 5 godina, {len(df5)} kola\n\n"
        f"🔥 *Topli glavni brojevi:*\n{hot_main}\n\n"
        f"❄️ *Hladni glavni brojevi:*\n{cold_main}\n\n"
        f"⏳ *Overdue glavni brojevi:*\n{overdue_main}\n\n"
        f"🔥 *Topli Euro brojevi:*\n{hot_euro}\n\n"
        f"❄️ *Hladni Euro brojevi:*\n{cold_euro}\n\n"
        f"⏳ *Overdue Euro brojevi:*\n{overdue_euro}\n\n"
        f"📊 *Najčešće strukture:*\n"
        f"- Par/Nepar: {odd_even_str}\n"
        f"- Low/High: {low_high_str}\n"
        f"- Tipični zbroj: {sum_range[0]}–{sum_range[1]}\n"
        f"- Tipični broj uzastopnih parova: {consec_mode}\n\n"
        f"🔗 *Najčešći parovi:*\n{fmt_pairs(top_pairs[:5])}\n\n"
        f"🧩 *Najčešći tripleti:*\n{fmt_pairs(top_triplets[:5])}\n\n"
        f"⭐ *TOP 5 kombinacija za sljedeće kolo:*\n{combos_text}"
    )

    evaluation = (
        f"🎰 *Eurojackpot PRO Evaluacija*\n"
        f"Vrijeme: {now}\n"
        f"Zadnje kolo {int(last['Kolo']) if 'Kolo' in last and not pd.isna(last['Kolo']) else '-'} / {last['Datum']}\n\n"
        f"🎲 Izvučeno:\n"
        f"- Glavni: {', '.join(map(str, last_main))}\n"
        f"- Euro: {', '.join(map(str, last_euro))}\n\n"
        f"🎯 Najjača prognoza modela:\n"
        f"- Glavni: {', '.join(map(str, best_main))}\n"
        f"- Euro: {', '.join(map(str, best_euro))}\n\n"
        f"✅ Pogodci glavni: {len(hit_main)}/5 -> {', '.join(map(str, hit_main)) if hit_main else 'nema'}\n"
        f"✅ Pogodci euro: {len(hit_euro)}/2 -> {', '.join(map(str, hit_euro)) if hit_euro else 'nema'}\n\n"
        f"📌 Ostale jake kombinacije:\n{combos_text}"
    )

    return prediction, evaluation


def send_telegram(text: str):
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not bot_token or not chat_id:
        print(text)
        return
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}
    r = requests.post(url, json=payload, timeout=30)
    r.raise_for_status()


def main():
    mode = os.environ.get("MODE", "PREDICTION").upper()
    df = load_all_history()
    df5 = subset_5y(df)
    prediction, evaluation = build_messages(df5)
    send_telegram(evaluation if mode == "EVALUATION" else prediction)


if __name__ == "__main__":
    main()
