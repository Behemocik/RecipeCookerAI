"""
Moduł Discord Bot.

Zawiera:
- Logikę klienta Discord (`RecipeCookerClient`).
- Zarządzanie cyklem życia bota (start, analiza, wysyłanie wiadomości).
- Prezentację wyników na kanale Discord (`present_culinary_journey`).
"""

import discord
import random
import json
import asyncio
from datetime import datetime

from core import (
    CHANNEL_ID, CUISINE_MAP, CUISINE_REGIONS, CUISINES, RECENT_REGION_COUNT,
    load_history, save_history, google_search, is_google_search_configured,
    culinary_workshop, save_daily_plan
)

from agents.analysis import (
    agent_deep_analyst,
    agent_search_strategist,
    agent_trend_analyst_multi_source
)

from agents.planning import agent_meal_planner

from agents.presentation import (
    agent_smart_stylist,
    agent_publisher
)

# ==============================================================================
# LOGIKA PREZENTACJI (WYSYŁANIE WIADOMOŚCI)
# ==============================================================================



def format_recipe_raw(recipe: dict, title: str, macros: dict = None) -> str:
    """Tworzy surowy ciąg znaków z przepisem (przed stylizacją)."""
    if not recipe or not isinstance(recipe, dict): return ""
    
    calories = macros.get('calories') if macros else recipe.get('calories')
    # Obsługa brakujących nazw składników i podwójnych jednostek
    ing_list = []
    for i in recipe.get('ingredients', []):
        name = i.get('item', 'Składnik')
        if not name: name = "Składnik"
        
        amount = str(i.get('amount', '')).strip()
        unit = str(i.get('unit', '')).strip()
        
        # Eliminacja duplikatów (np. amount="200g", unit="g")
        if unit and unit.lower() in amount.lower():
            display_amount = amount
        elif amount and unit:
            display_amount = f"{amount} {unit}"
        else:
            display_amount = amount or unit  
              
        ing_list.append(f"- {name} – {display_amount}")

    ingredients = "\n".join(ing_list)
    steps = "\n".join([f"{idx+1}. {s}" for idx, s in enumerate(recipe.get('steps', []))])
    
    return (
        f"{title}: {recipe.get('dish_name','Danie')}\n"
        f"{recipe.get('description','Smaczne danie.')}\n"
        f"Kalorie: {calories or '?'}, Czas: {recipe.get('prep_time','?')}\n\n"
        f"Składniki:\n{ingredients}\n\n"
        f"Przygotowanie:\n{steps}"
    )

import urllib.parse

async def present_culinary_journey(channel, cuisine, brief, insight, options, star_dish, meal_plan, history, preferences, chat_history):
    """
    Główna funkcja prezentacyjna. Tworzy narrację, stylizuje ją i wysyła na Discorda.
    """
    print("\n--- Prezentacja Podróży Kulinarnej (Architektura Uproszczona) ---")
    
    # --- Krok 1: Ankieta (Szybka, bez AI) ---
    print("📤 [DISCORD] Wysyłam ankietę...")
    num_options = len(options)
    poll_title = f"Oto {num_options} propozycje na obiad:" if num_options > 1 else "Propozycja na obiad:"
    poll_embed = discord.Embed(title=poll_title, description="Głosujcie, która opcja podoba Wam się najbardziej!", color=0x5865F2)
    
    for i, opt in enumerate(options):
        recipe, macros = opt.get('recipe', {}), opt.get('macros', {})
        poll_embed.add_field(
            name=f"{i+1}️⃣ {recipe.get('dish_name', 'N/A')}", 
            value=f"> {recipe.get('description', 'N/A')}\n*🔥 {macros.get('calories', '?')} kcal | ⏱️ {recipe.get('prep_time', '?')}*", 
            inline=False
        )
    
    poll_message = await channel.send(embed=poll_embed)
    
    reactions = [f"{i+1}\u20e3" for i in range(num_options)] if num_options > 1 else ["👍", "👎"]
    for r in reactions: await poll_message.add_reaction(r)

    # --- Krok 2: Generowanie Treści (Smart Stylist) ---
    print("🎨 [REDACJA] Uruchamiam Inteligentnego Stylistę...")
    
    destination = CUISINE_MAP.get(cuisine, cuisine)
    
    # A. Wprowadzenie (Raw -> Stylist)
    # Uproszczone intro - bez surowych danych, tylko esencja
    raw_intro = f"Dziś zabieram Was do {destination}!"
    
    # Dodaj ciekawostkę zamiast briefu (brief będzie wykorzystany przez LLM automatycznie)
    # anecdote_context informuje Stylist żeby dodał ciekawostkę o regionie
    anecdote_context = f"Wpleć ciekawostkę o {destination} (kultura, historia, tradycja kulinarna)."
      # C. Przepisy (Raw -> Stylists)
    # Tu przygotowujemy listę krotek (raw_text, dish_name) aby potem móc dodać link
    recipe_data_list = []
    
    def prepare_recipe_data(r_data, title, macros):
         r = r_data.get('recipe') if 'recipe' in r_data else r_data # Handle varying structure
         if not r: r = {}
         raw = format_recipe_raw(r, title, macros)
         return (raw, r.get('dish_name', ''))

    # Struktura danych wejściowych jest niespójna (meal_plan vs star_dish), ujednolicam:
    # meal_plan.get('breakfast') zwraca słownik przepisu (nie ma klucza 'recipe')
    # star_dish ma klucz 'recipe'
    
    # Śniadanie
    r_breakfast = meal_plan.get('breakfast', {})
    if r_breakfast: recipe_data_list.append( (format_recipe_raw(r_breakfast, 'Śniadanie'), r_breakfast.get('dish_name')) )
    
    # Obiad
    r_lunch = star_dish.get('recipe', {})
    m_lunch = star_dish.get('macros', {})
    if r_lunch: recipe_data_list.append( (format_recipe_raw(r_lunch, 'Obiad', m_lunch), r_lunch.get('dish_name')) )

    # Kolacja
    r_dinner = meal_plan.get('dinner', {})
    if r_dinner: recipe_data_list.append( (format_recipe_raw(r_dinner, 'Kolacja'), r_dinner.get('dish_name')) )
    
    # WALIDACJA KRYTYCZNA: Wymuszamy dokładnie 3 przepisy
    while len(recipe_data_list) < 3:
        meal_names = ['Śniadanie', 'Obiad', 'Kolacja']
        placeholder = f"{meal_names[len(recipe_data_list)]}: Proste danie\n\nKalorie: 300\n\nSkładniki:\n- Podstawowe składniki\n\nPrzygotowanie:\n1. Przygotuj zgodnie z przepisem"
        recipe_data_list.append( (placeholder, 'Proste danie') )
    
    # Uruchamiamy zadania równolegle
    tasks = {
        'intro': asyncio.create_task(agent_smart_stylist(f"{raw_intro} ({anecdote_context})", mode="intro")),
    }
    recipe_tasks = [asyncio.create_task(agent_smart_stylist(r_raw, mode="recipe")) for r_raw, _ in recipe_data_list]

    # Czekamy na wyniki
    intro_res = await tasks['intro']
    recipe_styled_texts = await asyncio.gather(*recipe_tasks)
    
    # Dodajemy linki do zdjęć do Stylizowanych Przepisów
    # WAŻNE: Musimy mieć dokładnie 3 przepisy (śniadanie, obiad, kolacja)
    final_recipes = []
    for styled_text, (_, dish_name) in zip(recipe_styled_texts, recipe_data_list):
        if dish_name:
            query = urllib.parse.quote(dish_name)
            link = f"https://www.google.com/search?q={query}&tbm=isch"
            final_text = f"{styled_text}\n\n📷 [Zobacz {dish_name}]({link})"
            final_recipes.append(final_text)
        else:
            final_recipes.append(styled_text)

    # --- Krok 3: Publikacja (Publisher) ---
    print("📰 [REDACJA] Składanie numeru...")
    
    # KLUCZOWE: Publisher oczekuje oddzielnych kluczy, nie listy!
    # Musimy przekazać: intro, breakfast, lunch, dinner
    components = {
        "intro": intro_res,
        "breakfast": final_recipes[0] if len(final_recipes) > 0 else "",
        "lunch": final_recipes[1] if len(final_recipes) > 1 else "",
        "dinner": final_recipes[2] if len(final_recipes) > 2 else ""
    }
    
    final_messages = await agent_publisher(components)
    
    # WALIDACJA KRYTYCZNA: Wymuszamy dokładnie 4 wiadomości!
    if len(final_messages) != 4:
        print(f"  ⚠️ Publisher zwrócił {len(final_messages)} zamiast 4. Używam fallbacku.")
        final_messages = [
            components["intro"],
            components["breakfast"] if components.get("breakfast") else "Brak śniadania",
            components["lunch"] if components.get("lunch") else "Brak obiadu",
            components["dinner"] if components.get("dinner") else "Brak kolacji"
        ]
    
    print(f"📤 [DISCORD] Wysyłam {len(final_messages)} wiadomości...")
    for msg in final_messages:
        if msg.strip():
            await channel.send(msg)
            await asyncio.sleep(1) # Odstęp dla czytelności

    print("✔️ Prezentacja zakończona.")
    return poll_message, final_messages


# ==============================================================================
# KLIENT DISCORD (GŁÓWNA KLASA BOTA)
# ==============================================================================

class RecipeCookerClient(discord.Client):
    """
    Główna klasa bota. Zarządza logiką biznesową od uruchomienia do zamknięcia.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.history = load_history()
        # Konfiguracja ładowana jest z domyślnych ustawień (brak pliku config.json)

    def get_region_for_cuisine(self, cuisine):
        """Pomocnicza funkcja mapująca kuchnię na region."""
        return next((r for r, cs in CUISINE_REGIONS.items() if cuisine in cs), "Specjalne / Klimatyczne")

    def choose_cuisine(self, suggested):
        """
        Wybiera kuchnię na dziś.
        Jeśli analityk coś zasugerował (i nie było to ostatnio), akceptuje.
        W przeciwnym razie losuje kuchnię, unikając powtórzeń.
        """
        print("\n--- Wybór Kuchni ---")
        last_cuisines = self.history.get("last_cuisines", [])
        
        # 1. Sprawdzenie sugestii analityka
        if suggested in CUISINES and suggested not in last_cuisines[:3]:
            print(f"🕵️ Analityk zasugerował: {suggested}. Akceptuję.")
            return suggested

        if suggested:
            print(f"🕵️ Analityk zasugerował: {suggested}, ale była już ostatnio. Ignoruję i losuję.")

        # 2. Losowanie regionu (unikając ostatnich)
        last_regions = self.history.get("last_regions", [])
        available_regions = [r for r in CUISINE_REGIONS.keys() if r not in last_regions] or list(CUISINE_REGIONS.keys())
        chosen_region = random.choice(available_regions)
        print(f"🌍 Wylosowany region: {chosen_region} (Ostatnio: {', '.join(last_regions)})")
        
        # 3. Losowanie kuchni w ramach regionu
        available_cuisines = list(CUISINE_REGIONS[chosen_region].keys())
        final_choices = [c for c in available_cuisines if c not in last_cuisines] or available_cuisines
        chosen_cuisine = random.choice(final_choices)
        
        print(f"🍝 Ostateczny wybór: {chosen_cuisine}")
        return chosen_cuisine

    async def on_ready(self):
        """Główna pętla wykonywana po uruchomieniu bota."""
        if getattr(self, "has_run", False):
            return
        self.has_run = True

        print(f'✅ Zalogowano jako: {self.user}')
        
        channel = self.get_channel(CHANNEL_ID)
        if not channel: 
            print("❌ KRYTYCZNY BŁĄD: Nie znaleziono kanału. Sprawdź CHANNEL_ID.")
            return await self.close()
            
        print(f"📍 Kanał docelowy: #{channel.name} (ID: {channel.id})")

        print("\n--- FAZA 1: Analiza i Planowanie ---")
        await self.analyze_last_poll(channel)

        # 0. Pobranie historii czatu (dla kontekstu)
        print("💬 Pobieram historię czatu Discord (dla analityka)...")
        chat_history_list = []
        async for message in channel.history(limit=10):
            chat_history_list.append(f"{message.author.name}: {message.content}")
        chat_history_list.reverse()
        chat_history_str = "\n".join(chat_history_list)
        print(f"📜 [DEBUG] Historia czatu ({len(chat_history_list)} wiadomości):")
        for msg in chat_history_list[-3:]:  # Pokaż ostatnie 3
            print(f"   {msg}")

        # 1. Głęboka Analiza (Deep Analyst)
        analysis_str = await agent_deep_analyst(chat_history_str, self.history)
        try: analysis_result = json.loads(analysis_str)
        except (json.JSONDecodeError, AttributeError): analysis_result = {}

        daily_brief = analysis_result.get("daily_brief", "Standardowo, szukamy czegoś taniego i dobrego")
        new_insight = analysis_result.get("new_learning", "")
        suggested_cuisine = analysis_result.get("suggested_cuisine", "")
        
        print(f"📝 Codzienny brief: {daily_brief}")
        print(f"🔍 [DEBUG] Analityk zasugerował: '{suggested_cuisine}'")
        if new_insight: 
            print(f"💡 Nowy wniosek o użytkowniku: {new_insight}")
            self.history.setdefault("user_insights", []).append(new_insight)

        # 2. Wybór Kuchni
        print(f"\n🎯 [DEBUG] Przekazuję '{suggested_cuisine}' do choose_cuisine()")
        cuisine = self.choose_cuisine(suggested_cuisine)
        print(f"🌍 Wybrana kuchnia na dziś: {cuisine}")
        print(f"✅ [DEBUG] Ostateczna decyzja: {cuisine}")

        # 3. Badanie Trendów (Research)
        ideas_str = await self.research_trends(cuisine, daily_brief)
        try: ideas = json.loads(ideas_str).get("ideas", [])
        except (json.JSONDecodeError, AttributeError): ideas = []

        if not ideas:
            print("❌ Brak pomysłów na dziś. Zamykam bota.")
            await channel.send("Dziś wena mnie opuściła, moi drodzy. Spróbujmy jutro!")
            return await self.close()
        
        print(f"✔️ Znaleziono {len(ideas)} pomysłów: {', '.join(map(str, ideas))}")

        print("\n--- FAZA 2: Warsztat Kulinarny ---")
        verified_options = []
        
        # Iteracja przez pomysły i generowanie przepisów
        for i, idea_item in enumerate(ideas):
            if len(verified_options) >= 3:
                print("✔️ Zebrano 3 zweryfikowane opcje. Kończę warsztat.")
                break

            # Wyodrębnienie nazwy (obsługa różnych formatów JSON od modelu)
            trend_name = ""
            if isinstance(idea_item, dict):
                for key in ['nazwa', 'idea', 'name', 'dish_name']:
                    if key in idea_item:
                        trend_name = idea_item[key]; break
            elif isinstance(idea_item, str):
                trend_name = idea_item
            
            if not trend_name:
                print(f"⚠️ Nie udało się wyodrębnić nazwy pomysłu z: {idea_item}")
                continue

            # Uruchomienie warsztatu dla pojedynczego pomysłu
            recipe, macros = await culinary_workshop(trend_name, cuisine, daily_brief, self.history.get("user_insights", []))
            
            if recipe and macros:
                verified_options.append({"recipe": recipe, "macros": macros})
        
        if not verified_options:
            print("❌ Żaden z projektów nie został zaakceptowany. Zamykam bota.")
            await channel.send("Żaden z pomysłów nie sprostał dziś moim wyśrubowanym standardom. Widzimy się jutro!")
            return await self.close()

        print(f"\n--- FAZA 3: Prezentacja ---")
        print(f"🍝 Wybrano {len(verified_options)} opcje do prezentacji.")
        star_dish = random.choice(verified_options) # Wybór "gwiazdy dnia" do pełnego planu
        
        print("📅 Przygotowuję plany żywieniowe (śniadanie/kolacja)...")
        for option in verified_options:
            meal_plan_str = await agent_meal_planner(option.get('recipe'))
            try: 
                meal_plan = json.loads(meal_plan_str)
                option['meal_plan'] = meal_plan
            except (json.JSONDecodeError, TypeError, AttributeError): 
                # Fallback: Zapewniamy podstawowy meal_plan zamiast None
                option['meal_plan'] = {
                    'breakfast': {'dish_name': 'Owsianka', 'ingredients': [], 'steps': []},
                    'dinner': {'dish_name': 'Sałatka', 'ingredients': [], 'steps': []}
                }

        print("🎉 Prezentuję wyniki na Discordzie!")
        sent_message, final_messages = await present_culinary_journey(
            channel=channel, 
            cuisine=cuisine, 
            brief=daily_brief, 
            insight=new_insight, 
            options=verified_options, 
            star_dish=star_dish, 
            meal_plan=star_dish.get('meal_plan'), 
            history=self.history, 
            preferences={}, 
            chat_history=chat_history_list
        )

        # Zapisz plan dnia do Markdown
        date_str = datetime.now().strftime("%Y-%m-%d")
        full_markdown_content = "\n\n".join(final_messages)
        save_daily_plan(date_str, full_markdown_content)

        # Aktualizuj historię
        self.update_history(cuisine, ideas, sent_message.id, verified_options)
        save_history(self.history)
        
        print("\n✅ Podróż kulinarna na dziś zakończona.")
        await self.close()

    async def analyze_last_poll(self, channel):
        """Sprawdza wyniki ostatniej ankiety na Discordzie i aktualizuje preferencje."""
        last_poll = self.history.get("last_poll")
        if not last_poll or not last_poll.get("message_id"): 
            print("📊 Brak ostatniej ankiety do analizy.")
            return
        try:
            print(f"📊 Analizuję ankietę: {last_poll.get('message_id')}")
            message = await channel.fetch_message(last_poll["message_id"])
            reactions = message.reactions
            options = last_poll.get("options", [])
            
            if not reactions:
                print("- Ankieta bez reakcji.")
                return

            winner = max(reactions, key=lambda r: r.count, default=None)
            if winner and winner.count > 1:
                winner_emoji = str(winner.emoji)
                if '️⃣' in winner_emoji:
                    # Konwersja emoji (1️⃣ -> indeks 0)
                    winner_idx = int(winner_emoji.replace('\u20e3', '')) - 1
                    if 0 <= winner_idx < len(options):
                        winner_dish = options[winner_idx]
                        self.history.setdefault("liked_trends", []).append(winner_dish)
                        print(f"🏆 Zwycięzca ankiety: {winner_dish} (Głosy: {winner.count})")
            else:
                print("- Brak wyraźnego zwycięzcy ankiety.")
        except discord.NotFound:
            print(f"- Nie znaleziono wiadomości z ankietą ({last_poll['message_id']}).")
        except Exception as e:
            print(f"- Błąd podczas analizy ankiety: {e}")
        finally:
            self.history["last_poll"] = {} # Wyczyść po analizie

    async def research_trends(self, cuisine, daily_brief):
        """Przeprowadza research trendów w Google lub fallback do historii."""
        print("\n--- Badanie Trendów ---")
        if not is_google_search_configured():
            print("🌐 [Tryb Offline] Wyszukiwanie Google nie jest skonfigurowane. Używam tylko historii.")
            return await agent_trend_analyst_multi_source(cuisine, "", self.history, [])

        queries_str = await agent_search_strategist(cuisine, daily_brief)
        try: queries = json.loads(queries_str).get("queries", [])
        except (json.JSONDecodeError, AttributeError): queries = []
        
        data = ""
        if queries:
            print(f"🔍 Wykonuję zapytania: {', '.join(queries)}")
            search_coroutines = [asyncio.to_thread(google_search, q) for q in queries]
            search_results = await asyncio.gather(*search_coroutines)
            
            for q, res in zip(queries, search_results):
                 data += f"\n--- WYNIKI DLA '{q}' ---\n{res}\n"
        else:
            print("⚠️ Strateg nie wygenerował żadnych zapytań.")
            
        return await agent_trend_analyst_multi_source(cuisine, data, self.history, [])

    def update_history(self, cuisine, ideas, message_id, options):
        """Aktualizuje lokalną historię sesji."""
        print("\n--- Aktualizacja Historii ---")
        region = self.get_region_for_cuisine(cuisine)
        
        self.history.setdefault("last_regions", []).insert(0, region)
        self.history["last_regions"] = self.history["last_regions"][:RECENT_REGION_COUNT]
        
        self.history.setdefault("last_cuisines", []).insert(0, cuisine)
        self.history["last_cuisines"] = self.history["last_cuisines"][:15]
        
        self.history.setdefault("last_trends", []).insert(0, ideas)
        self.history["last_trends"] = self.history["last_trends"][:20]
        
        dish_names = [opt.get('recipe', {}).get('dish_name', '') for opt in options]
        self.history["last_poll"] = {"message_id": message_id, "options": dish_names}
        
        print(f"💾 Zapisano historię (Region: {region}, Kuchnia: {cuisine}). Ankieta: {message_id}")
