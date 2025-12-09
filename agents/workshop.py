"""
Moduł Agentów Warsztatowych.

Odpowiada za proces tworzenia i weryfikacji przepisów:
- Chef Refiner: Tworzy i poprawia przepisy.
- Shopper Audit: Sprawdza dostępność i koszt składników.
- Nutrition Audit: Sprawdza wartości odżywcze i zgodność z dietą.
"""

from core import ask_llm

# ==============================================================================
# 1. CHEF REFINER (SZEF KUCHNI)
# ==============================================================================

_chef_system_message = """Jesteś **Mistrzem Kuchni** w projekcie RecipeCooker. Twoim zadaniem jest tworzenie kompletnych, kreatywnych przepisów na podstawie wstępnej idei i wytycznych.

**Zasady:**
1.  **Kompletność:** Przepis musi mieć nazwę, TREŚCIWY OPIS (w tym 1 zdanie wyjaśniające co to za danie i skąd pochodzi, dla laika), listę składników i instrukcje.
2.  **Kreatywność:** Dodaj "twist".
3.  **Realizm:** Składniki dostępne w Polsce.
4.  **Ścisły JSON.**

**FORMAT WYJŚCIOWY (JSON):**
`{
  "dish_name": "<Nazwa dania>",
  "description": "<Opis dania + Wyjaśnienie kulturowe>",
  "prep_time": "<Szacowany czas przygotowania>",
  "ingredients": [{"item": "<Składnik>", "amount": "<Ilość>", "unit": "<Jednostka>"}],
  "steps": ["<Krok 1>", "<Krok 2>"]
}`
"""

async def agent_chef_refiner(draft: dict):
    """
    Agent szefa kuchni - tworzy lub poprawia przepis na podstawie feedbacku.
    
    Proces:
    1. Otrzymuje pomysł + kuchnię + wytyczne
    2. Analizuje historię feedbacku (jeśli były poprawki)
    3. Generuje kompletny przepis w JSON (nazwa, opis, składniki, kroki)
    """
    dish_name = draft.get('idea', 'Danie')[:40]  # Max 40 znaków dla czytelności
    print(f"  🧑‍🍳 Chef: '{dish_name}'...")
    
    # Budujemy prompt dla LLM z całym kontekstem
    prompt = f"""**Pomysł:** {draft.get('idea')}
**Kuchnia:** {draft.get('cuisine')}
**Wytyczne:** {draft.get('guidelines')}
**Historia feedbacku (do poprawy):** {draft.get('feedback_history', 'Brak')}

Stwórz lub popraw przepis, stosując się do powyższych informacji. Zwróć uwagę na feedback, jeśli jest dostępny.
"""
    messages = [
        {"role": "system", "content": _chef_system_message},
        {"role": "user", "content": prompt}
    ]
    
    return await ask_llm(messages, json_mode=True)


# ==============================================================================
# 2. SHOPPER AUDIT (AUDYTOR LOGISTYCZNY)
# ==============================================================================

_shopper_system_message = """Jesteś **Audytorem Logistycznym** w RecipeCooker. Twoim zadaniem jest ocena przepisu pod kątem kosztów i dostępności składników w polskich supermarketach (np. Lidl, Biedronka, Auchan).

**Zasady Oceny:**
1.  **Dostępność:** Czy większość składników jest łatwo dostępna w typowym polskim supermarkecie? Egzotyczne, trudno dostępne składniki są OK, ale tylko jeśli jest ich 1-2 i stanowią dodatek, a nie bazę dania.
2.  **Koszt:** Czy przepis jest ekonomiczny? Odrzuć go, jeśli wymaga wielu bardzo drogich składników (np. szafran, polędwica wołowa, świeże owoce morza w dużych ilościach).
3.  **Decyzja:** Zatwierdź przepis (`approved: true`), jeśli jest rozsądny cenowo i logistycznie. Odrzuć (`approved: false`) tylko w przypadku POWAŻNYCH problemów z kosztem lub dostępnością. Zawsze podaj krótkie uzasadnienie.

**FORMAT WYJŚCIOWY (JSON):**
`{\"approved\": <true/false>, \"feedback\": \"<Twoje zwięzłe uzasadnienie>\"}`
"""

async def agent_shopper_audit(draft: dict):
    """
    Audytor logistyczny - sprawdza czy składniki są dostępne i niezbyt drogie.
    
    Kryteria oceny:
    - Dostępność w polskich supermarketach (Lidl, Biedronka, Auchan)
    - Koszt (odrzuca przepisy z wieloma drogimi składnikami)
    
    Returns:
        JSON: {"approved": true/false, "feedback": "uzasadnienie"}
    """
    dish_name = draft.get('chef_work', {}).get('dish_name', 'Danie')[:30]
    print(f"  🛒 Logistyk: '{dish_name}'...")
    
    prompt = f"""**Danie:** {draft.get('chef_work', {}).get('dish_name')}
**Składniki:** {draft.get('chef_work', {}).get('ingredients')}
**Wytyczne:** {draft.get('guidelines')}

Oceń przepis pod kątem logistyki i kosztów dla polskiego użytkownika.
"""
    messages = [
        {"role": "system", "content": _shopper_system_message},
        {"role": "user", "content": prompt}
    ]
    
    return await ask_llm(messages, json_mode=True)


# ==============================================================================
# 3. NUTRITION AUDIT (AUDYTOR DIETETYCZNY)
# ==============================================================================

_nutrition_system_message = """Jesteś **Audytorem Dietetycznym** w RecipeCooker. Twoim zadaniem jest ocena przepisu pod kątem wartości odżywczych i zgodności z wytycznymi.

**Zasady Oceny:**
1.  **Zbilansowanie:** Czy przepis jest w miarę zbilansowany? Nie musi być super-fit, ale nie powinien być skrajnie niezdrowy (np. sam tłuszcz i cukier).
2.  **Kaloryczność:** Dokonaj *szacunkowej* oceny kalorii. Dopuszczalny przedział na obiad to 400-900 kcal. Nie odrzucaj przepisu, jeśli lekko wychodzi poza te ramy, ale jest sensowny.
3.  **Zgodność:** Sprawdź, czy przepis jest zgodny z podstawowymi założeniami (np. czy danie wegetariańskie nie zawiera mięsa). To jest najważniejsze kryterium.
4.  **Decyzja:** Zatwierdź (`approved: true`), jeśli przepis jest akceptowalny. Odrzuć (`approved: false`) tylko w przypadku rażących błędów (np. mięso w daniu wege) lub gdy danie jest skrajnie niezbilansowane. Podaj uzasadnienie.

**FORMAT WYJŚCIOWY (JSON):**
`{\"approved\": <true/false>, \"calories\": \"<Twoja szacowana wartość kcal>\", \"feedback\": \"<Twoje zwięzłe uzasadnienie>\"}`
"""

async def agent_nutrition_audit(draft: dict):
    """
    Weryfikuje przepis pod kątem wartości odżywczych i zgodności z dietą.
    """
    # (agent already logged by simplified logging in core.py)
    
    prompt = f"""**Danie:** {draft.get('chef_work', {}).get('dish_name')}
**Składniki i Kroki:** {draft.get('chef_work')}
**Wytyczne:** {draft.get('guidelines')}

Oceń przepis pod kątem wartości odżywczych.
"""
    messages = [
        {"role": "system", "content": _nutrition_system_message},
        {"role": "user", "content": prompt}
    ]
    
    response = await ask_llm(messages, json_mode=True)
    # (silent on success)
    return response
