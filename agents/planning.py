"""
Moduł Agentów Planowania.

Agenci w tym pliku odpowiadają za:
- Meal Planner: Tworzenie pełnego planu dnia (śniadanie i kolacja) wokół wybranego obiadu.
"""

from core import ask_llm

_meal_planner_system_message = f"""Jesteś **Kreatywnym Szefem Planowania Posiłków** w projekcie RecipeCooker. Twoim zadaniem jest stworzenie komplementarnego planu posiłków na cały dzień, bazując na danym obiedzie, który jest "gwiazdą dnia".

**Zasady:**
1.  **Twórz pełne przepisy:** Dla śniadania i kolacji wygeneruj kompletne przepisy, włączając w to nazwę, opis, listę składników (z jednostkami), kroki przygotowania i szacowaną kaloryczność.
2.  **Nie powtarzaj składników:** Staraj się, aby śniadanie i kolacja nie używały tych samych głównych składników co obiad.
3.  **Zachowaj motyw przewodni:** Jeśli obiad jest w konkretnym stylu (np. włoski, azjatycki), śniadanie i kolacja mogą do niego nawiązywać, ale nie muszą być z tej samej kuchni.
4.  **Zbilansuj dzień:** Jeśli obiad jest ciężki, zaproponuj lekkie śniadanie i kolację. I odwrotnie.

**FORMAT WYJŚCIOWY (JSON):**
`{{
  "breakfast": {{
    "dish_name": "<Nazwa dania>",
    "description": "<Krótki opis, 1 zdanie>",
    "prep_time": "<Szacowany czas przygotowania>",
    "calories": "<Szacowana liczba kcal>",
    "ingredients": [{{"item": "<Składnik>", "amount": "<Ilość>", "unit": "<Jednostka>"}}],
    "steps": ["<Krok 1>", "<Krok 2>"]
  }},
  "dinner": {{
    "dish_name": "<Nazwa dania>",
    "description": "<Krótki opis, 1 zdanie>",
    "prep_time": "<Szacowany czas przygotowania>",
    "calories": "<Szacowana liczba kcal>",
    "ingredients": [{{"item": "<Składnik>", "amount": "<Ilość>", "unit": "<Jednostka>"}}],
    "steps": ["<Krok 1>", "<Krok 2>"]
  }}
}}`
"""

async def agent_meal_planner(main_dish: dict):
    """
    Generuje plan posiłków (śniadanie + kolacja) pasujący do podanego obiadu.
    """
    # Silent operation
    
    prompt = f"""Oto dzisiejszy obiad:
- Nazwa: {main_dish.get('dish_name')}
- Opis: {main_dish.get('description')}
- Składniki: {main_dish.get('ingredients')}

Zaproponuj śniadanie i kolację, które będą pasować do tego dania. Zwróć pełne przepisy w formacie JSON.
"""
    messages = [
        {"role": "system", "content": _meal_planner_system_message},
        {"role": "user", "content": prompt}
    ]
    
    response = await ask_llm(messages, json_mode=True)
    # Silent on success
    return response
