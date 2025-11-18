import os
import json
import datetime
import random
import requests
import time
from groq import Groq
from dotenv import load_dotenv

load_dotenv()

# --- KONFIGURACJA ---
GROQ_CLIENT = Groq(api_key=os.environ.get("GROQ_API_KEY"))
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")
HISTORY_FILE = "recipe_history.json"

# Słownik: Klucz (Przymiotnik dla AI) -> Wartość (Kraj dla tekstu "Podróżujemy do...")
CUISINE_MAP = {
    "Włoska": "Włoch",
    "Meksykańska": "Meksyku",
    "Japońska": "Japonii",
    "Tajska": "Tajlandii",
    "Polska": "Polski",
    "Francuska": "Francji",
    "Indyjska": "Indii",
    "Grecka": "Grecji",
    "Amerykańska BBQ": "Stanów Zjednoczonych (USA)",
    "Koreańska": "Korei",
    "Hiszpańska": "Hiszpanii",
    "Gruzińska": "Gruzji"
}

# Lista kluczy do losowania
CUISINES = list(CUISINE_MAP.keys())

# --- NARZĘDZIA SYSTEMOWE ---

def load_history():
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"last_trends": [], "last_cuisines": []}

def save_history(trend, cuisine):
    data = load_history()
    data["last_trends"] = ([trend] + data.get("last_trends", []))[:7]
    data["last_cuisines"] = ([cuisine] + data.get("last_cuisines", []))[:7]
    
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def google_search(query):
    print(f"🔍 [Google] Szukam: {query}")
    api_key = os.environ.get("GOOGLE_API_KEY")
    cx = os.environ.get("GOOGLE_CX")
    
    if not api_key or not cx: return "Brak kluczy Google API."

    url = "https://www.googleapis.com/customsearch/v1"
    params = {'key': api_key, 'cx': cx, 'q': query, 'num': 4}
    try:
        resp = requests.get(url, params=params)
        data = resp.json()
        items = data.get("items", [])
        if not items: return "Brak wyników."
        return "\n".join([f"- {i['title']}: {i['snippet']}" for i in items])
    except Exception as e:
        return f"Błąd Google: {e}"

def send_webhook(content, cuisine_adjective):
    """Wysyła gotowe menu na Discorda"""
    if not DISCORD_WEBHOOK_URL: return
    
    # Tłumaczymy "Włoska" na "Włoch"
    destination = CUISINE_MAP.get(cuisine_adjective, cuisine_adjective)
    
    data = {
        "username": "Robert Makłowicz",  # <-- ZMIANA: Stała nazwa
        # Opcjonalnie możesz dodać zdjęcie Makłowicza:
        # "avatar_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/e/e2/Robert_Mak%C5%82owicz_2013.jpg/220px-Robert_Mak%C5%82owicz_2013.jpg",
        "content": f"🌍 **Dziś podróżujemy do {destination}!**\n\n{content}" # <-- ZMIANA: Gramatyka
    }
    requests.post(DISCORD_WEBHOOK_URL, json=data)

# --- LOGIKA LLM ---

def ask_llm(messages, json_mode=False):
    params = {
        "model": "llama-3.3-70b-versatile",
        "messages": messages,
        "temperature": 0.7,
        "max_tokens": 2000
    }
    if json_mode: params["response_format"] = {"type": "json_object"}
    return GROQ_CLIENT.chat.completions.create(**params).choices[0].message.content

# --- AGENCI ---

# Zmieniona definicja: dodajemy current_banned_trends
def agent_tiktoker(history, current_banned_trends):
    """Agent 1: Szuka trendu, unika powtórzeń (historycznych i dzisiejszych)"""
    print("\n📱 [TikToker] Szukam co jest viralowe...")
    
    # 1. Szukamy w Google
    year = datetime.datetime.now().year
    search_results = google_search(f"viral food trends {year} tiktok instagram")
    
    # Łączymy trendy z historii z trendami, które nie przeszły dziś
    history_banned = history.get("last_trends", [])
    # TUTAJ JEST KLUCZOWA ZMIANA: łączymy obie listy i tworzymy jeden string
    all_banned_topics = ", ".join(history_banned + current_banned_trends)
    
    prompt = f"""
    Jesteś researcherem trendów kulinarnych (TikTok/Instagram).
    
    TWOJE DANE:
    {search_results}
    
    HISTORIA TRENDÓW (Tego NIE WOLNO ci wybrać, bo było ostatnio LUB ODRZUCONO WCZEŚNIEJ W TEJ SESJI):
    {all_banned_topics}
    
    ZADANIE:
    Wybierz JEDEN konkretny trend lub składnik, który jest teraz modny.
    MUSISZ wybrać trend, który nie znajduje się na liście HISTORYCZNEJ.
    Zwróć tylko nazwę tego trendu (maks 5 słów).
    """
    
    trend = ask_llm([{"role": "system", "content": prompt}])
    print(f"📱 [TikToker] Wybrałem trend: {trend}")
    return trend

def agent_chef(trend, cuisine, feedback=""):
    print(f"\n👨‍🍳 [Szef Kuchni] Projektuję menu ({cuisine})...")
    prompt = f"""
    Jesteś Robertem Makłowiczem. Twoim stylem jest kuchnia: {cuisine}.
    Opowiadaj barwnie, używaj ciekawego słownictwa, ale bądź konkretny w przepisach.
    Pamiętaj: Dozwolone są kreatywne fuzje i unowocześnienia tradycyjnych dań.
    
    TREND DNIA: {trend}
    POPRZEDNIE UWAGI: {feedback}
    
    ZADANIE:
    Stwórz menu na cały dzień (Śniadanie, Obiad, Kolacja).
    1. Styl: {cuisine}.
    2. Wykorzystaj trend "{trend}".
    
    Format (Markdown):
    # 🍳 Śniadanie: [Nazwa]
    (Opis i składniki)
    # 🥘 Obiad: [Nazwa]
    (Instrukcja)
    # 🥗 Kolacja: [Nazwa]
    (Lekka propozycja)
    """
    return ask_llm([{"role": "system", "content": prompt}])

def agent_advisor(trend, cuisine):
    """Sprawdza, czy trend pasuje do kuchni."""
    print(f"\n🧠 [Doradca] Analizuję zgodność trendu '{trend}' z kuchnią {cuisine}...")
    
    prompt = f"""
    Jesteś ekspertem kulinarnym. Oceniasz, czy trend: "{trend}"
    jest realistycznie możliwy do wplecenia w autentyczną kuchnię: {cuisine}.
    
    ZADANIE:
    Odpowiedz TYLKO w formacie JSON.
    Zwróć approved: true, jeśli trend jest w ogóle wykonalny.
    Zwróć approved: false, jeśli trend jest absurdalny lub niezgodny z kuchnią.
    """
    response = ask_llm([{"role": "system", "content": prompt}], json_mode=True)
    return json.loads(response)

def agent_critic(menu_draft, cuisine):
    print("\n🧐 [Krytyk] Sprawdzam jakość...")
    prompt = f"""
    Jesteś krytykiem kulinarnym, który docenia fuzję smaków i kreatywność.
    Oceniasz menu zaproponowane przez Szefa Kuchni (styl: {cuisine}).
    
    MENU DO OCENY:
    {menu_draft}
    
    ZASADY AKCEPTACJI:
    1. Czy menu jest **spójne** i logiczne (np. czy da się to zjeść)?
    2. Czy Szef Kuchni umiejętnie **wplótł trend** w ramy kuchni {cuisine}? (Dozwolone są nowoczesne fuzje).
    3. Czy jest jasny podział na Śniadanie/Obiad/Kolację?
    
    Odpowiedz w formacie JSON:
    {{
        "approved": true lub false,
        "feedback": "Krótka lista uwag co poprawić"
    }}
    """
    response = ask_llm([{"role": "system", "content": prompt}], json_mode=True)
    return json.loads(response)

# --- MAIN ---

def main():
    history = load_history()
    
    max_global_attempts = 5
    final_menu = "" 
    successful_run = False
    
    # NOWOŚĆ: Lista trendów, które nie przeszły walidacji Doradcy dzisiaj
    banned_trends_today = [] 

    for global_attempt in range(max_global_attempts):
        print(f"\n======== PRÓBA GLOBALNA {global_attempt + 1} / {max_global_attempts} ========")
        
        # 2. Wybór kuchni (innej niż ostatnio)
        available = [c for c in CUISINES if c not in history.get("last_cuisines", [])]
        if not available: available = CUISINES
        today_cuisine = random.choice(available)
        print(f"🌍 Losuję kuchnię: {today_cuisine}")
        
        # 3. TikToker znajduje trend - PRZEKAZUJEMY LISTĘ ZABLOKOWANYCH
        trend = agent_tiktoker(history, banned_trends_today)
        
        # 4. Agent Doradca sprawdza spójność
        advisor_check = agent_advisor(trend, today_cuisine)
        
        if not advisor_check["approved"]:
            print(f"❌ [Doradca] Trend '{trend}' nie pasuje do {today_cuisine}. Ponawiam próbę.")
            # KLUCZOWA ZMIANA: Dodajemy odrzucony trend do listy na dziś
            banned_trends_today.append(trend) 
            continue 
        else:
            print("✅ [Doradca] Trend jest spójny. Przekazuję do Szefa Kuchni.")
            
            # --- START ISTNIEJĄCEJ PĘTLI REFINACJI (Szef <-> Krytyk) ---
            attempts = 0
            feedback = ""
            
            while attempts < 5:
                attempts += 1
                print(f"--- Próba generowania nr {attempts} ---")
                
                draft = agent_chef(trend, today_cuisine, feedback)
                review = agent_critic(draft, today_cuisine)
                
                if review["approved"]:
                    print("✅ [Krytyk] Menu zaakceptowane!")
                    final_menu = draft
                    successful_run = True
                    break
                else:
                    print(f"❌ [Krytyk] Odrzucono: {review['feedback']}")
                    feedback = review['feedback']
            
            if successful_run:
                break

    # --- ZAKOŃCZENIE I PUBLIKACJA ---
    
    if not final_menu:
        final_menu = f"Po {max_global_attempts} próbach agent nie znalazł spójnego menu na dziś. Dziś Makłowicz poszedł na wino."

    send_webhook(final_menu, today_cuisine)
    save_history(trend if successful_run else "FAILURE", today_cuisine)
    
    folder = "daily_plans"
    if not os.path.exists(folder): os.makedirs(folder)
    today_str = datetime.datetime.now().strftime("%Y-%m-%d")
    with open(f"{folder}/{today_str}.md", "w", encoding="utf-8") as f:
        f.write(f"# Menu Dnia: {today_cuisine}\nTrend: {trend if successful_run else 'Brak'}\n\n{final_menu}")

if __name__ == "__main__":
    main()