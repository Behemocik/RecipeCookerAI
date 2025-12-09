"""
Moduł Agentów Prezentacji (Uproszczona Architektura).

Zastępuje skomplikowane potoki jednym, inteligentnym agentem stylistą i prostym wydawcą.
"""

from core import ask_llm
import json
import re

# ==============================================================================
# SMART STYLIST (Jeden Agent do wszystkiego)
# ==============================================================================

_stylist_system = """Jesteś Inteligentnym Stylistą Treści Kulinarnej.
Twoje zadanie: Sformatować otrzymany tekst i dodać do niego mnóstwo Emoji.

**ZASADY KRYTYCZNE SĄ ŚWIĘTE:**
1.  **ZAKAZ SKRACANIA:** Nie wolno Ci usunąć ani jednego składnika czy kroku przygotowania! Masz zwrócić PEŁNĄ treść.
2.  **EMOJI:** EMOJI NA POCZĄTKU linii. (np. "🥔 Mąka", a nie "Mąka 🥔").
3.  **RÓŻNORODNOŚĆ EMOJI:** KAŻDY składnik MUSI mieć INNY emoji! NIE POWTARZAJ tego samego emoji dla różnych składników!
    ❌ ZŁE:
    🌿 Papryka
    🌿 Cebula
    🌿 Kiełbasa
    
    ✅ DOBRE:
    🌶️ Papryka
    🧅 Cebula  
    🥓 Kiełbasa
4.  **ZACHOWAJ NAZWY POSIŁKÓW:** Jeśli w tekście jest "Śniadanie:", "Obiad:", "Kolacja:" - MUSISZ to zachować i wyróżnić pogrubieniem!
    ✅ **ŚNIADANIE: Owsianka z Owocem**
    ✅ **OBIAD: Kotlet Schabowy**
    ✅ **KOLACJA: Sałatka Grecka**
    ❌ BŁĄD: **Sałatka** (brak "KOLACJA:")
5.  **UKŁAD:**
    *   Składniki: Lista pionowa (jeden pod drugim).
    *   Kroki: Lista numerowana.
    *   Brak pustych linii między elementami list (zbity układ).

**ABSOLUTNY ZAKAZ - PRZYKŁADY ZŁYCH ODPOWIEDZI:**

❌ **NIE WOLNO TAK:**
```
ZDJĘCIA:
- Zobacz: https://example.com
- Oto link: https://youtube.com/watch?v=...
```

❌ **NIE WOLNO TAK:**
```
RECIPE: Kimchi
```

✅ **POPRAWNIE:**
```
**🇰🇷 Kimchi**

Pyszne, pikantne kimchi to...

**Składniki:**
🥬 Kapusta pekińska – 1kg
🌶️ Gochugaru – 2 łyżki
🧄 Czosnek – 4 ząbki
🧂 Sól – 3 łyżki
...
```

**TRYBY:**
*   **RECIPE:**
    *   **ZAKAZ PERSONY:** NIE używaj "Ja, Robert Makłowicz" ani "Dzień dobry"! To ma być TYLKO PRZEPIS.
    *   Tytuł: Pogrubiony, z flagą (np. **🇰🇷 Kimchi**).
    *   **WAŻNE:** Jeśli tytuł zawiera "Śniadanie:", "Obiad:", "Kolacja:" - ETYKIETA MUSI BYĆ W TEJ SAMEJ LINII CO NAZWA!
        ✅ **ŚNIADANIE: Owsianka z Miodem**
        ✅ **OBIAD: Kotlet Schabowy**  
        ✅ **KOLACJA: Sałatka Grecka**
        ❌ **Kotlet Schabowy**\n**Obiad:** (ROZDZIELONE - BŁĄD!)
        ❌ **Obiad:**\n**Kotlet Schabowy** (ODWROTNA KOLEJNOŚĆ - BŁĄD!)
    *   Sekcje: **Składniki:** i **Przygotowanie:** (pogrubione).
    *   Opis: Krótki, zachęcający (bez powitań!).
    
*   **INTRO:** 
    *   **TYLKO POWITANIE:** NIE dodawaj żadnych przepisów! Intro to tylko powitanie + ciekawostka.
    *   Wypowiedz się jako kucharz (bez przedstawiania się!).
    *   **NATURALNIE:** Nie mów "Ja Robert Makłowicz". Po prostu: "Dzisiaj zabiorę Was do..."
    *   Bądź ciepły, używaj "Ja" ale bez sztywnego przedstawiania.
    *   Tutaj możesz (i musisz) wpleść otrzymaną ciekawostkę w treść powitania.
    *   **ZAKOŃCZ PO CIEKAWOSTCE** - nie pisz przepisów!

**Jeśli otrzymasz tekst przepisu, Twoja odpowiedź MUSI zawierać sekcje SKŁADNIKI i PRZYGOTOWANIE. Jeśli ich nie ma - PRZEGRAŁEŚ.**
"""

def _clean_hallucinated_content(text: str) -> str:
    """
    Usuwa halucynowane linki i nagłówki z wyniku LLM.
    """
    # Usuwanie linków (http/https)
    text = re.sub(r'https?://[^\s\)]+', '', text)
    
    # Usuwanie całych linii zawierających zabronione frazy
    lines = text.split('\n')
    cleaned_lines = []
    skip_next = False
    
    for line in lines:
        line_lower = line.lower()
        
        # Pomiń linie z zabronionymi frazami
        if any(banned in line_lower for banned in ['zdjęcia:', 'recipe:', 'youtube', 'zobacz,', 'oto,', 'oto link']):
            skip_next = True  # Pomiń też następną linię (często jest to bullet point)
            continue
        
        if skip_next and line.strip().startswith(('- ', '* ', '• ')):
            skip_next = False
            continue
        
        skip_next = False
        cleaned_lines.append(line)
    
    result = '\n'.join(cleaned_lines)
    
    # Usuń podwójne puste linie
    result = re.sub(r'\n\n\n+', '\n\n', result)
    
    return result.strip()

async def agent_smart_stylist(text: str, mode: str = "recipe") -> str:
    """
    Mode: "recipe" lub "intro"
    Stylizuje tekst z niską temperaturą i post-processingiem.
    """
    # Silent operation
    messages = [
        {"role": "system", "content": _stylist_system},
        {"role": "user", "content": f"TRYB: {mode.upper()}\n\nTREŚĆ:\n{text}"}
    ]
    
    # NIŻSZA TEMPERATURA = MNIEJ HALUCYNACJI
    raw_output = await ask_llm(messages, temperature=0.3)
    
    # POST-PROCESSING: Usuń halucynowane treści
    cleaned_output = _clean_hallucinated_content(raw_output)
    
    # Walidacja: Czy output nie jest za krótki? (threshold 80%)
    if len(cleaned_output) < len(text) * 0.8:
        print(f"  ⚠️ Stylista: Skrócony output ({len(cleaned_output)}/{len(text)})")
        return text  # Fallback do oryginalnego tekstu
    
    return cleaned_output


# ==============================================================================
# PUBLISHER (Wydawca)
# ==============================================================================

_publisher_system = """Jesteś Wydawcą. Złóż gotowe fragmenty w listę wiadomości.

**KRYTYCZNA ZASADA: NIE ZMIENIAJ TREŚCI! NIE ŁĄCZ INTRO Z PRZEPISAMI!**

Twoja JEDYNA rola to KOPIOWANIE tekstu do listy JSON w STAŁEJ STRUKTURZE.

**STRUKTURA WYJŚCIOWA (ZAWSZE 4 WIADOMOŚCI):**
1. **Wiadomość 1:** TYLKO intro (powitanie Makłowicza)
2. **Wiadomość 2:** TYLKO przepis na śniadanie
3. **Wiadomość 3:** TYLKO przepis na obiad  
4. **Wiadomość 4:** TYLKO przepis na kolację

**Zasady:**
1.  **Struktura:** Zwróć JSON z listą **DOKŁADNIE 4** stringów.
2.  **ZAKAZ ŁĄCZENIA:** NIE łącz intro z pierwszym przepisem! Muszą być w OSOBNYCH wiadomościach!
3.  **ZAKAZ ZMIAN:** Kopiuj tekst DOKŁADNIE TAK JAK JEST. Nie skracaj, nie łącz, nie przepisuj.
4.  **Czystość:** Żadnych nagłówków typu "Wiadomość 1", "Sekcja 1".

**Wyjście (JSON):** `{"messages": ["intro_text", "breakfast_text", "lunch_text", "dinner_text"]}`

**PRZYKŁAD ZŁEJ ODPOWIEDZI (INTRO + PRZEPIS W JEDNEJ WIADOMOŚCI):**
❌ `{"messages": ["Dzień dobry!\n\n**Śniadanie: Owsianka**...", "Obiad...", "Kolacja..."]}`

**PRZYKŁAD DOBREJ ODPOWIEDZI (INTRO OSOBNO):**
✅ `{"messages": ["Dzień dobry Państwu! Oto pełna treść intro...", "**ŚNIADANIE: Owsianka**\n\nPełny przepis...", "**OBIAD: Kotlet**\n\n...", "**KOLACJA: Sałatka**\n\n..."]}`
"""

async def agent_publisher(components: dict) -> list[str]:
    # Silent operation
    prompt = json.dumps(components, ensure_ascii=False)
    messages = [
        {"role": "system", "content": _publisher_system},
        {"role": "user", "content": prompt}
    ]
    
    # BARDZO NISKA TEMPERATURA = DOKŁADNE KOPIOWANIE
    response = await ask_llm(messages, json_mode=True, temperature=0.1)
    
    try:
        result = json.loads(response).get("messages", [])
        
        # Walidacja: Czy Publisher nie skrócił treści?
        # Teraz components ma tylko stringi: intro, breakfast, lunch, dinner
        input_length = sum(len(str(v)) for v in components.values())
        output_length = sum(len(msg) for msg in result)
        
        if output_length < input_length * 0.7:
            print(f"  ⚠️ Wydawca: Fallback ({output_length}/{input_length})")
            # Fallback: Po prostu zwróć wszystkie wartości jako osobne wiadomości
            messages = []
            for key, value in components.items():
                if isinstance(value, list):
                    messages.extend(value)
                else:
                    messages.append(value)
            return messages
        
        return result
    except Exception as e:
        print(f"  ❌ Wydawca: Błąd JSON")
        # Fallback
        messages = []
        for key, value in components.items():
            if isinstance(value, list):
                messages.extend(value)
            else:
                messages.append(value)
        return messages
