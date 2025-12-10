"""
Moduł Core (Rdzeń Aplikacji).

Zawiera:
- Konfigurację globalną i ładowanie zmiennych środowiskowych.
- Wrapper dla klienta LLM (Groq) z obsługą wielu kluczy API (load balancing).
- Wrapper dla wyszukiwarki Google.
- Zarządzanie historią (odczyt/zapis JSON).
- Logikę warsztatu kulinarnego (koordynacja agentów).
"""

import os
import json
import asyncio
import random
import requests
from functools import partial
from dotenv import load_dotenv

# ==============================================================================
# KONFIGURACJA
# ==============================================================================

load_dotenv()

# Ładowanie kluczy API Groq (obsługa wielu kluczy w celu ominięcia limitów Rate Limit)
GROQ_API_KEYS = []
if os.environ.get("GROQ_API_KEY"):
    GROQ_API_KEYS.append(os.environ.get("GROQ_API_KEY"))

# Obsługa dodatkowych kluczy zdefiniowanych jako GROQ_API_KEY_2, _3, itd.
for i in range(2, 11):
    key = os.environ.get(f"GROQ_API_KEY_{i}")
    if key:
        GROQ_API_KEYS.append(key)

# Główny klucz (fallback)
GROQ_API_KEY = GROQ_API_KEYS[0] if GROQ_API_KEYS else None

DISCORD_TOKEN = os.environ.get("DISCORD_TOKEN")
try:
    CHANNEL_ID = int(os.environ.get("DISCORD_CHANNEL_ID", 0))
except (ValueError, TypeError):
    CHANNEL_ID = 0

# Konfiguracja Google Search
GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY")
GOOGLE_CX = os.environ.get("GOOGLE_CX")

# Pliki Historii
HISTORY_DIR = "memory"
MAIN_HISTORY_FILE = os.path.join(HISTORY_DIR, "main.json")  # Historia regionów, kuchni, ankiet
TRENDS_FILE = os.path.join(HISTORY_DIR, "trends.json")      # Historia trendów
INSIGHTS_FILE = os.path.join(HISTORY_DIR, "insights.json")  # Wnioski o użytkowniku

# Stałe konfiguracyjne
MAX_INSIGHTS = 15      # Maksymalna liczba wniosków trzymanych w pamięci
RECENT_REGION_COUNT = 2 # Ile ostatnich regionów pamiętać, by ich nie powtarzać

# Mapowanie Regionów i Kuchni
# Struktura: Kontynent -> Rodzaj Kuchni -> Nazwa wyświetlana (dopełniacz: "do...")
CUISINE_REGIONS = {
    "Europa": {
        "Włoska (Klasyczna)": "Włoch",
        "Włoska (Sycylia/Południe)": "Słonecznej Sycylii",
        "Francuska (Prowansalska)": "Prowansji",
        "Francuska (Bistro)": "Paryża",
        "Hiszpańska (Tapas/Paella)": "Hiszpanii",
        "Grecka (Tawerna)": "Grecji",
        "Polska (Staropolska)": "Szlacheckiego Dworku",
        "Polska (Bar Mleczny)": "PRL-u",
        "Ukraińska (Wareniki/Barszcz)": "Ukrainy",
        "Gruzińska (Supra)": "Gruzji",
        "Węgierska (Papryka)": "Węgier",
        "Niemiecka (Wurst/Kartoffel)": "Bawarii",
        "Skandynawska (Hygge)": "Północy",
        "Bałkańska (Grill)": "Bałkanów",
    },
    "Azja": {
        "Japońska (Ramen Shop)": "Tokio",
        "Japońska (Domowa)": "Japonii",
        "Chińska (Syzuana/Ostry)": "Syczuanu",
        "Chińska (Kantońska/DimSum)": "Kantonu",
        "Wietnamska (Street Food)": "Hanoi",
        "Tajska (Curry/PadThai)": "Bangkoku",
        "Indyjska (Curry House)": "Mumbaju",
        "Koreańska (K-Drama Food)": "Seulu",
        "Indonezyjska (Bali Vibe)": "Bali",
        "Turecka (Kebab/Meze)": "Stambułu",
        "Libańska/Arabska": "Bejrutu",
    },
    "Ameryki": {
        "Meksykańska (Cantina)": "Meksyku",
        "Meksykańska (Tex-Mex)": "Pogranicza USA/Meksyk",
        "USA (Southern BBQ)": "Teksasu",
        "USA (NYC Style)": "Nowego Jorku",
        "USA (Cajun/Creole)": "Nowego Orleanu",
        "Brazylijska": "Rio de Janeiro",
        "Argentyńska": "Buenos Aires",
        "Peruwiańska": "Limon",
    },
    "Specjalne / Klimatyczne": {
        "Babcina Kuchnia (Comfort Food)": "Domu Babci",
        "Smak Jesieni (Dyniowe/Grzybowe)": "Złotej Jesieni",
    }
}

# Spłaszczona mapa kuchni
CUISINE_MAP = {k: v for region in CUISINE_REGIONS.values() for k, v in region.items()}
CUISINES = list(CUISINE_MAP.keys())


# ==============================================================================
# SERWISY (LLM & Google)
# ==============================================================================

try:
    from groq import Groq
    
    # Inicjalizacja klientów Groq (po jednym na każdy klucz API)
    GROQ_CLIENTS = []
    if GROQ_API_KEYS:
        for key in GROQ_API_KEYS:
            GROQ_CLIENTS.append(Groq(api_key=key))
            
    if not GROQ_CLIENTS:
        GROQ_CLIENT = None
    else:
        GROQ_CLIENT = GROQ_CLIENTS[0]

    def get_groq_client():
        """Zwraca losowego klienta Groq w celu rozłożenia obciążenia (load balancing)."""
        if not GROQ_CLIENTS:
            return None
        return random.choice(GROQ_CLIENTS)

except ImportError:
    GROQ_CLIENT = None
    GROQ_CLIENTS = []
    def get_groq_client():
        return None

# Semafor ograniczający liczbę równoległych zapytań do LLM (zapobiega spamowaniu API)
LLM_SEMAPHORE = asyncio.Semaphore(1)

def is_google_search_configured():
    """Sprawdza, czy klucze API Google są poprawnie skonfigurowane."""
    return bool(GOOGLE_API_KEY and GOOGLE_CX)

def google_search(query, num_results=3):
    """
    Wykonuje wyszukiwanie w Google Custom Search API.
    
    Args:
        query (str): Fraza do wyszukania.
        num_results (int): Oczekiwana liczba wyników.
        
    Returns:
        str: Połączone fragmenty (snippets) znalezionych stron lub komunikat błędu.
    """
    # Silent operation
    if not is_google_search_configured():
        print("  ⚠️ Brak klucza Google API")
        return "Brak danych z wyszukiwarki."
    
    url = "https://www.googleapis.com/customsearch/v1"
    params = {
        'key': GOOGLE_API_KEY,
        'cx': GOOGLE_CX,
        'q': query,
        'num': num_results
    }
    
    try:
        response = requests.get(url, params=params)
        response.raise_for_status()
        result = response.json()
        snippets = [item.get('snippet', '') for item in result.get('items', [])]
        if not snippets:
            return f"Brak wyników dla zapytania: '{query}'"
        # Silent on success
        return "\n".join(snippets)
    except requests.exceptions.HTTPError as http_err:
        error_details = response.json().get('error', {}).get('message', 'Brak szczegółów')
        print(f"  ❌ Google API: Błąd {response.status_code}")
        return f"Błąd serwera Google: {error_details}"
    except Exception as e:
        print(f"  ❌ Google: {str(e)[:40]}")
        return f"Błąd podczas wyszukiwania frazy: {query}"

async def ask_llm(messages, model="llama-3.1-8b-instant", temperature=0.7, json_mode=False):
    """
    Funkcja wysyłająca zapytanie do LLM (Groq API) z mechanizmami odporności na błędy.
    
    Mechanizmy zabezpieczeń:
    - Semaphore: Ogranicza równoległe wywołania API (1 na raz)
    - Retry logic: Automatyczne ponowne próby przy błędzie 429 (Rate Limit)
    - Exponential backoff: Zwiększanie czasu oczekiwania między próbami (1s, 2s, 4s, 8s, 16s)
    - Load balancing: Jeśli mamy wiele kluczy API, wybiera losowy
    
    Args:
        messages (list): Lista wiadomości w formacie [{"role": "system/user", "content": "..."}]
        model (str): Nazwa modelu Groq (domyślnie llama-3.1-8b-instant)
        temperature (float): Kreatywność/losowość odpowiedzi (0.0=deterministyczny, 1.0=kreatywny)
        json_mode (bool): Czy wymusić odpowiedź w formacie JSON
        
    Returns:
        str: Odpowiedź modelu (tekst lub JSON string) albo "" w przypadku błędu
    """
    # Wyciągamy nazwę agenta z system message (dla logowania)
    agent_name = messages[0].get('content', 'Agent').split('.')[0][:30]  # Max 30 znaków
    
    # Pobieramy klienta Groq (może być jeden z wielu kluczy API)
    current_client = get_groq_client()

    # Sprawdzenie czy klient jest dostępny
    if not current_client:
        print(f"  ⚠️ LLM niedostępny")
        return "{}" if json_mode else ""

    # Przygotowanie parametrów wywołania API
    params = {
        "messages": messages,
        "model": model,
        "temperature": temperature,
        "max_tokens": 4096,
    }
    if json_mode:
        params["response_format"] = {"type": "json_object"}

    # Konfiguracja retry logic
    max_retries = 5
    initial_delay = 1.0

    # Semaphore zapewnia że tylko 1 zapytanie LLM jest wysyłane w danym momencie
    # (ograniczenie API rate limit)
    async with LLM_SEMAPHORE:
        delay = initial_delay
        for attempt in range(max_retries):
            try:
                # Wywołanie Groq API (blokujące, więc używamy executor)
                blocking_task = partial(current_client.chat.completions.create, **params)
                loop = asyncio.get_running_loop()
                response = await loop.run_in_executor(None, blocking_task)
                
                # Sukces! Wyciągamy treść odpowiedzi
                content = response.choices[0].message.content
                
                # CLEANED LOG: Tylko jeśli sukces po retry
                if attempt > 0:
                    print(f"  ✓ {agent_name} (próba {attempt+1})")
                
                # Krótkie opóźnienie dla API (dobre obyczaje)
                await asyncio.sleep(0.5)
                return content
                
            except Exception as e:
                # --- OBSŁUGA BŁĘDU RATE LIMIT (429) ---
                if '429' in str(e):
                    if attempt < max_retries - 1:
                        # Mamy jeszcze próby - czekamy i ponawiamy
                        print(f"  ⏳ {agent_name}: Rate limit, czekam {delay:.0f}s...")
                        await asyncio.sleep(delay)
                        delay *= 2  # Exponential backoff: 1s -> 2s -> 4s -> 8s -> 16s
                    else:
                        # Skończyły się próby
                        print(f"  ❌ {agent_name}: Rate limit po {max_retries} próbach")
                        break
                else:
                    # --- INNY BŁĄD (NIE 429) ---
                    # Nie ma sensu retry - przerywamy od razu
                    print(f"  ❌ {agent_name}: Błąd API - {str(e)[:50]}")
                    break


    return "{}" if json_mode else ""


# ==============================================================================
# ZARZĄDZANIE HISTORIĄ (PAMIĘĆ)
# ==============================================================================

MAIN_KEYS = ["last_cuisines", "last_regions", "last_poll"]
TRENDS_KEYS = ["last_trends"]
INSIGHTS_KEYS = ["user_insights", "liked_trends"]

def _load_json_file(file_path, default_value):
    """Pomocnicza funkcja do bezpiecznego wczytywania JSON."""
    if not os.path.exists(file_path):
        return default_value
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
            if not content:
                return default_value
            return json.loads(content)
    except (json.JSONDecodeError, FileNotFoundError):
        return default_value

def load_history():
    """Wczytuje całą historię (główną, trendy, insighty) do jednego słownika."""
    os.makedirs(HISTORY_DIR, exist_ok=True)
    
    history = {}
    
    main_data = _load_json_file(MAIN_HISTORY_FILE, {k: [] for k in MAIN_KEYS})
    trends_data = _load_json_file(TRENDS_FILE, {k: [] for k in TRENDS_KEYS})
    insights_data = _load_json_file(INSIGHTS_FILE, {k: [] for k in INSIGHTS_KEYS})
    
    history.update(main_data)
    history.update(trends_data)
    history.update(insights_data)
    
    # Inicjalizacja brakujących kluczy
    for key in MAIN_KEYS + TRENDS_KEYS + INSIGHTS_KEYS:
        if key not in history:
            history[key] = [] if 'last' in key else {}
            
    return history

def _save_json_file(file_path, data):
    """Pomocnicza funkcja do zapisu JSON."""
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

def save_history(history):
    """Zapisuje stan historii do odpowiednich plików JSON."""
    os.makedirs(HISTORY_DIR, exist_ok=True)
    
    main_data = {k: history.get(k) for k in MAIN_KEYS if k in history}
    trends_data = {k: history.get(k) for k in TRENDS_KEYS if k in history}
    insights_data = {k: history.get(k) for k in INSIGHTS_KEYS if k in history}
    
    _save_json_file(MAIN_HISTORY_FILE, main_data)
    _save_json_file(TRENDS_FILE, trends_data)
    _save_json_file(INSIGHTS_FILE, insights_data)

def save_daily_plan(date_str, content):
    """Zapisuje wygenerowany plan (Markdown) do pliku w folderze daily_plans."""
    os.makedirs("daily_plans", exist_ok=True)
    file_path = os.path.join("daily_plans", f"{date_str}.md")
    with open(file_path, 'w', encoding='utf-8', errors='replace') as f:
        f.write(content)
    print(f"💾 [PLIK] Zapisano plan dzienny: {file_path}")


# ==============================================================================
# WARSZTAT KULINARNY (KOORDYNACJA AGENTÓW)
# ==============================================================================

async def culinary_workshop(trend, cuisine, daily_brief, insights_list):
    """
    Warsztat kulinarny - iteracyjny proces tworzenia przepisu.
    
    Proces: Chef -> Logistyk -> Dietetyk -> (jeśli odrzucono: powtórz z feedbackiem)
    Maksymalnie 3 iteracje.
    """
    from agents.workshop import agent_chef_refiner, agent_shopper_audit, agent_nutrition_audit
    
    # Przygotowanie draftu przepisu
    draft = {
        "idea": trend, "cuisine": cuisine,
        "guidelines": {"daily_brief": daily_brief, "user_insights": insights_list},
        "feedback_history": [], "chef_work": {}, "final_macros": {}
    }
    MAX_ITERATIONS = 3
    
    # Iteracje warsztatu (maksymalnie 3)
    for i in range(MAX_ITERATIONS):
        # --- CHEF ---
        chef_response_str = await agent_chef_refiner(draft)
        try: 
            chef_response = json.loads(chef_response_str)
        except (json.JSONDecodeError, TypeError): 
            chef_response = None
        
        if not chef_response or not isinstance(chef_response, dict) or not chef_response.get("dish_name"):
            draft["feedback_history"].append("Błąd formatu JSON")
            continue
            
        draft["chef_work"] = chef_response
        dish = chef_response.get('dish_name', '')[:30]  # Skrócona nazwa
        print(f"  ✓ '{dish}'")

        # --- LOGISTYK ---
        shopper_review_str = await agent_shopper_audit(draft)
        try: 
            shopper_review = json.loads(shopper_review_str)
        except (json.JSONDecodeError, TypeError): 
            shopper_review = None

        if not isinstance(shopper_review, dict) or not shopper_review.get("approved", False):
            feedback = f"Logistyk: {shopper_review.get('feedback', 'Odrzucony') if isinstance(shopper_review, dict) else 'Błąd'}"
            draft["feedback_history"].append(feedback)
            print(f"  ✗ Odrzucono (logistyk)")
            continue

        # --- DIETETYK ---
        nutrition_review_str = await agent_nutrition_audit(draft)
        try: 
            nutrition_review = json.loads(nutrition_review_str)
        except (json.JSONDecodeError, TypeError): 
            nutrition_review = None

        if not isinstance(nutrition_review, dict) or not nutrition_review.get("approved", False):
            feedback = f"Dietetyk: {nutrition_review.get('feedback', 'Odrzucony') if isinstance(nutrition_review, dict) else 'Błąd'}"
            draft["feedback_history"].append(feedback)
            print(f"  ✗ Odrzucono (dietetyk)")
            continue
        
        # SUKCES - wszystkie audyty przeszły!
        draft["final_macros"] = {"calories": nutrition_review.get("calories", "?")}
        return draft["chef_work"], draft["final_macros"]

    # Porażka po MAX_ITERATIONS próbach
    return None, None
