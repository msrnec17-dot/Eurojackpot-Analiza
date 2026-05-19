import os
import requests
import pandas as pd
from bs4 import BeautifulSoup
import datetime as dt

# --- DIO 1: SCRAPING SVIH REZULTATA ---

def dohvati_arhivu_za_godinu(godina):
    url = f"https://lotostatistika.com.hr/eurojackpot/eurojackpot-izvlacenje-arhiva.aspx?g={godina}"
    headers = {'User-Agent': 'Mozilla/5.0'}
    
    response = requests.get(url, headers=headers)
    if response.status_code != 200:
        return None
        
    soup = BeautifulSoup(response.text, 'html.parser')
    table = soup.find('table')
    if not table:
        return None
        
    try:
        df = pd.read_html(str(table))[0]
        return df
    except Exception:
        return None

def azuriraj_bazu():
    trenutna_godina = dt.datetime.now().year
    sve_godine_df = []
    
    for god in range(2012, trenutna_godina + 1):
        df_god = dohvati_arhivu_za_godinu(god)
        if df_god is not None and not df_god.empty:
            sve_godine_df.append(df_god)
            
    if not sve_godine_df:
        return None
        
    ukupni_df = pd.concat(sve_godine_df, ignore_index=True)
    ukupni_df['date'] = pd.to_datetime(ukupni_df['Datum'], format='%d.%m.%Y', errors='coerce')
    
    ukupni_df.rename(columns={
        'Br 1': 'main_1', 'Br 2': 'main_2', 'Br 3': 'main_3', 'Br 4': 'main_4', 'Br 5': 'main_5',
        'D 1': 'euro_1', 'D 2': 'euro_2'
    }, inplace=True)
    
    return ukupni_df.sort_values('date').dropna(subset=['date'])

# --- DIO 2: ANALIZA (Zadnjih 5 godina) ---

def compute_stats_last_5_years(df: pd.DataFrame):
    cutoff = dt.datetime.now() - dt.timedelta(days=5 * 365)
    recent = df[df["date"] >= cutoff].copy()
    
    main_nums = recent[["main_1", "main_2", "main_3", "main_4", "main_5"]].values.flatten()
    euro_nums = recent[["euro_1", "euro_2"]].values.flatten()
    
    main_freq = pd.Series(main_nums).value_counts().sort_index()
    euro_freq = pd.Series(euro_nums).value_counts().sort_index()

    hot_main = main_freq.sort_values(ascending=False).head(10)
    cold_main = main_freq.sort_values(ascending=True).head(10)
    hot_euro = euro_freq.sort_values(ascending=False).head(5)
    cold_euro = euro_freq.sort_values(ascending=True).head(5)

    pred_main = hot_main.head(5).index.tolist()
    pred_euro = hot_euro.head(2).index.tolist()

    last_draw = recent.iloc[-1]
    last_main = [int(last_draw[f"main_{i+1}"]) for i in range(5)]
    last_euro = [int(last_draw[f"euro_{j+1}"]) for j in range(2)]

    return {
        "recent_count": len(recent),
        "hot_main": hot_main, "cold_main": cold_main,
        "hot_euro": hot_euro, "cold_euro": cold_euro,
        "pred_main": pred_main, "pred_euro": pred_euro,
        "last_main": last_main, "last_euro": last_euro,
        "last_date": last_draw['Datum']
    }

# --- DIO 3: TELEGRAM PORUKE ---

def format_prediction_message(stats) -> str:
    today = dt.datetime.now().strftime("%d.%m.%Y.")
    hot_m = ", ".join(f"{int(n)}({int(c)}x)" for n, c in stats["hot_main"].head(5).items())
    cold_m = ", ".join(f"{int(n)}({int(c)}x)" for n, c in stats["cold_main"].head(5).items())
    hot_e = ", ".join(f"{int(n)}({int(c)}x)" for n, c in stats["hot_euro"].head(3).items())
    cold_e = ", ".join(f"{int(n)}({int(c)}x)" for n, c in stats["cold_euro"].head(3).items())

    pm = ", ".join(str(int(x)) for x in sorted(stats["pred_main"]))
    pe = ", ".join(str(int(x)) for x in sorted(stats["pred_euro"]))

    return (
        f"🎰 *Eurojackpot Analiza* ({today})\n\n"
        f"Analizirano zadnjih {stats['recent_count']} izvlačenja (5 god).\n\n"
        f"🔥 *Topli glavni*: {hot_m}\n"
        f"❄️ *Hladni glavni*: {cold_m}\n"
        f"🔥 *Topli Euro*: {hot_e}\n"
        f"❄️ *Hladni Euro*: {cold_e}\n\n"
        f"🎯 *Predikcija (po frekvenciji)*:\n"
        f"🟢 Glavni: *{pm}*\n"
        f"🟡 Euro: *{pe}*\n\n"
        f"Sretno! 🍀"
    )

def format_evaluation_message(stats) -> str:
    today = dt.datetime.now().strftime("%d.%m.%Y.")
    hit_main_set = sorted(set(stats["pred_main"]) & set(stats["last_main"]))
    hit_euro_set = sorted(set(stats["pred_euro"]) & set(stats["last_euro"]))

    lm = ", ".join(str(int(x)) for x in sorted(stats["last_main"]))
    le = ", ".join(str(int(x)) for x in sorted(stats["last_euro"]))
    pm = ", ".join(str(int(x)) for x in sorted(stats["pred_main"]))
    pe = ", ".join(str(int(x)) for x in sorted(stats["pred_euro"]))
    
    hm_str = ", ".join(str(int(x)) for x in hit_main_set) if hit_main_set else "nema"
    he_str = ", ".join(str(int(x)) for x in hit_euro_set) if hit_euro_set else "nema"

    return (
        f"🎰 *Eurojackpot Provjera* ({today})\n\n"
        f"🎲 *Zadnje kolo ({stats['last_date']}):*\n"
        f"🟢 {lm}\n"
        f"🟡 {le}\n\n"
        f"🎯 *Tvoja predikcija:*\n"
        f"🟢 {pm}\n"
        f"🟡 {pe}\n\n"
        f"✅ *Pogoci glavnih:* {len(hit_main_set)}/5 ({hm_str})\n"
        f"✅ *Pogoci Euro:* {len(hit_euro_set)}/2 ({he_str})"
    )

def send_telegram(message: str):
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    
    if bot_token and chat_id:
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        payload = {"chat_id": chat_id, "text": message, "parse_mode": "Markdown"}
        requests.post(url, json=payload)

if __name__ == "__main__":
    df = azuriraj_bazu()
    if df is not None:
        stats = compute_stats_last_5_years(df)
        mode = os.environ.get("MODE", "PREDICTION").upper()
        
        if mode == "EVALUATION":
            msg = format_evaluation_message(stats)
        else:
            msg = format_prediction_message(stats)
            
        send_telegram(msg)
