import os
import requests
import datetime

def dohvati_statistiku():
    # Ovdje se implementira stvarna logika čitanja zadnjih rezultata
    # Za sada koristimo najčešće povijesne brojeve kao bazu
    glavni = [19, 7, 18, 49, 33]
    euro = [5, 8]
    return glavni, euro

def posalji_na_telegram(glavni, euro):
    BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
    CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID')

    if not BOT_TOKEN or not CHAT_ID:
        print("Greška: Nisu postavljeni TELEGRAM_BOT_TOKEN i/ili TELEGRAM_CHAT_ID.")
        return

    today = datetime.datetime.now().strftime("%d.%m.%Y.")

    poruka = f"🎰 *Eurojackpot Analiza* ({today})\n\n"
    poruka += "Najizglednija kombinacija za sljedeće kolo (bazirano na frekvenciji):\n"
    poruka += f"🟢 Glavni brojevi: *{', '.join(map(str, glavni))}*\n"
    poruka += f"🟡 Euro brojevi: *{', '.join(map(str, euro))}*\n\n"
    poruka += "Sretno! 🍀"

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": poruka,
        "parse_mode": "Markdown"
    }

    try:
        response = requests.post(url, json=payload)
        response.raise_for_status()
        print("Uspješno poslano na Telegram!")
    except Exception as e:
        print(f"Greška pri slanju na Telegram: {e}")

if __name__ == "__main__":
    glavni_brojevi, euro_brojevi = dohvati_statistiku()
    posalji_na_telegram(glavni_brojevi, euro_brojevi)
