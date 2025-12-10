"""
Moduł Agentów Analitycznych.

Agenci w tym pliku odpowiadają za "mózg" operacji:
- Deep Analyst: Analizuje historię użytkownika i decyduje co gotować.
- Search Strategist: Układa plan wyszukiwania w Google.
- Trend Analyst: Wybiera najlepsze pomysły na podstawie wyników wyszukiwania.
"""

from core import ask_llm, MAX_INSIGHTS, CUISINES

# ==============================================================================
# 1. DEEP ANALYST (GŁÓWNY ANALITYK)
# ==============================================================================

_deep_analyst_system_message = f"""Jesteś **Głównym Analitykiem** w projekcie kulinarnym RecipeCooker. Twoim zadaniem jest analiza historii gotowania i preferencji użytkownika, aby wyciągnąć wnioski i zasugerować kierunek na dzisiejszy dzień.

**KLUCZOWE ZASADY:**
1. **Otrzymasz historię czatu Discord jako PRIORYTETOWE ŹRÓDŁO** - jeśli użytkownik wyraził konkretną preferencję (np. "chcę kebab", "mam ochotę na pizzę"), to jest NAJWAŻNIEJSZA informacja.
2. Musisz zmapować preferencje użytkownika na DOKŁADNĄ nazwę kuchni z poniższej listy.
3. Przykłady mapowania:
   - "kebab" → "Turecka (Kebab/Meze)"
   - "pizza" lub "makaron" → "Włoska (Klasyczna)"
   - "sushi" lub "ramen" → "Japońska (Ramen Shop)"
   - "burrito" lub "tacos" → "Meksykańska (Cantina)"
   - "pierogi" → "Polska (Staropolska)"

**DOSTĘPNE KUCHNIE:**
{', '.join(CUISINES)}

**FORMAT WYJŚCIOWY (JSON):**
{{
  "daily_brief": "<Twój zwięzły brief na dziś, np. tanio i szybko, danie wegetariańskie, coś na imprezę>",
  "suggested_cuisine": "<DOKŁADNA nazwa kuchni z powyższej listy, np. 'Turecka (Kebab/Meze)'>",
  "new_learning": "<Nowy, ciekawy wniosek na temat preferencji użytkownika, np. Użytkownik często wybiera dania z makaronem w weekendy, ale unika dań mięsnych w poniedziałki.>"
}}
"""

async def agent_deep_analyst(user_query: str, history: dict):
    """
    Analizuje historię i preferencje, aby wygenerować brief na dany dzień.
    Zwraca JSON z briefem, sugerowaną kuchnią i nowym wnioskiem (insight).
    """
    # Silent operation
    
    insights = history.get("user_insights", [])[:MAX_INSIGHTS]
    
    prompt = f"""**Ostatnia historia czatu (PRIORYTET):**
{user_query if user_query else 'Brak nowych wiadomości.'}

**Obecne wnioski analityczne (Insights):**
{insights if insights else 'Brak.'}

**Pełna historia (ostatnie wpisy):**
- Ostatnio lubiane trendy: {history.get('liked_trends', [])[-5:]}
- Ostatnio proponowane kuchnie: {history.get('last_cuisines', [])[:5]}
- Ostatnio proponowane regiony: {history.get('last_regions', [])}

Wykonaj analizę i zwróć JSON. Jeśli w historii czatu użytkownik wyraził konkretną chęć (np. "zjadłbym kebaba"), potraktuj to jako nadrzędną wytyczną dla 'suggested_cuisine' i 'daily_brief'.
"""
    messages = [
        {"role": "system", "content": _deep_analyst_system_message},
        {"role": "user", "content": prompt}
    ]
    
    response = await ask_llm(messages, json_mode=True)
    # Silent on success
    return response


# ==============================================================================
# 2. SEARCH STRATEGIST (STRATEG WYSZUKIWANIA)
# ==============================================================================

_strategist_system_message = """Jesteś **Strategiem Wyszukiwania** w projekcie kulinarnym. Twoim zadaniem jest wygenerowanie zwięzłych, trafnych zapytań do wyszukiwarki Google, aby znaleźć inspirujące i trendy przepisy kulinarne.

**Zasady:**
1.  **Maksymalnie 3 zapytania.**
2.  Zapytania muszą być po polsku lub angielsku, w zależności co da lepsze wyniki.
3.  Muszą być zgodne z briefem i kuchnią tematyczną.

**FORMAT WYJŚCIOWY (JSON):**
`{ "queries": ["<zapytanie 1>", "<zapytanie 2>"] }`
"""

async def agent_search_strategist(cuisine: str, daily_brief: str):
    """
    Generuje zapytania do Google na podstawie kuchni i briefu.
    """
    # Silent operation
    
    prompt = f"""**Kuchnia:** {cuisine}\n**Brief:** {daily_brief}\n\nWygeneruj zapytania i zwróć JSON.
"""
    messages = [
        {"role": "system", "content": _strategist_system_message},
        {"role": "user", "content": prompt}
    ]
    
    response = await ask_llm(messages, json_mode=True)
    # Silent on success
    return response


# ==============================================================================
# 3. TREND ANALYST (ANALITYK TRENDÓW)
# ==============================================================================

_trend_analyst_system_message = """Jesteś **Analitykiem Trendów Kulinarnych** w projekcie RecipeCooker. Twoim zadaniem jest przeanalizowanie dostarczonych danych (wyników wyszukiwania, historii) i zidentyfikowanie 3-5 najbardziej obiecujących pomysłów na dania.

**Zasady:**
1.  **Filtruj bezwartościowe wyniki:** Odrzuć reklamy, menu restauracji, strony główne bez konkretnych przepisów.
2.  **Identyfikuj trendy:** Szukaj ciekawych połączeń smaków, nietypowych składników, popularnych ostatnio dań.
3.  **Bądź zwięzły:** Każdy pomysł to tylko nazwa i krótki, intrygujący opis.

**FORMAT WYJŚCIOWY (JSON):**
`{ "ideas": [{"nazwa": "<nazwa dania>", "opis": "<opis>"}, ...] }`
"""

async def agent_trend_analyst_multi_source(cuisine: str, search_data: str, history: dict, guidelines: list):
    """
    Analizuje surowe dane z wyszukiwarki i historię, aby wyłonić konkretne pomysły na dania.
    """
    # Silent operation
    
    prompt = f"""**Analizowany temat:** Kuchnia {cuisine}

**Dane z wyszukiwarki Google:**
{search_data if search_data else 'Brak danych z wyszukiwarki.'}

**Dane historyczne i wnioski:**
- Ostatnio lubiane trendy: {history.get('liked_trends', [])[-5:]}
- Ostatnio proponowane dania (unikać, jeśli to możliwe): {history.get('last_trends', [])[:1]}
- Dodatkowe wytyczne: {guidelines if guidelines else 'Brak'}

Przeanalizuj wszystkie dane i przedstaw od 3 do 5 unikalnych, inspirujących pomysłów na dania. Zwróć JSON.
"""
    messages = [
        {"role": "system", "content": _trend_analyst_system_message},
        {"role": "user", "content": prompt}
    ]
    
    response = await ask_llm(messages, model="llama-3.1-8b-instant", json_mode=True)
    # Silent on success
    return response
