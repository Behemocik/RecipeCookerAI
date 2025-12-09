"""
Główny punkt wejścia aplikacji RecipeCookerAI.

Ten plik odpowiada za:
1. Wczytanie konfiguracji i zmiennych środowiskowych.
2. Inicjalizację bota Discord.
3. Uruchomienie pętli zdarzeń (event loop).

Przepływ wykonania:
- Weryfikacja zmiennych środowiskowych (.env)
- Konfiguracja uprawnień bota (Intents)
- Uruchomienie klienta Discord
- Obsługa błędów połączenia
"""

import discord
import sys
import asyncio
from core import DISCORD_TOKEN, CHANNEL_ID
from discord_bot import RecipeCookerClient

# ==============================================================================
# GŁÓWNA FUNKCJA STARTOWA
# ==============================================================================

if __name__ == "__main__":
    # Banner powitalny
    print("===========================================")
    print("🤖 Bot przepisowy - Startuję!")
    print("===========================================")

    # --- WALIDACJA KONFIGURACJI ---
    # Sprawdzamy czy wszystkie wymagane zmienne są ustawione
    # Bez nich bot nie może działać
    if not all([DISCORD_TOKEN, CHANNEL_ID]):
        print("❌ BŁĄD: Brak zmiennych środowiskowych.")
        print("   Sprawdź plik .env (DISCORD_TOKEN, CHANNEL_ID)")
        sys.exit(1)
    
    print("✓ Konfiguracja załadowana")

    # --- KONFIGURACJA UPRAWNIEŃ (INTENTS) ---
    # Discord wymaga jawnego deklarowania, do czego bot potrzebuje dostępu
    # message_content=True pozwala czytać treść wiadomości na kanałach
    intents = discord.Intents.default()
    intents.message_content = True
    
    # --- INICJALIZACJA KLIENTA ---
    # RecipeCookerClient to nasza klasa dziedzicząca z discord.Client
    # zawiera całą logikę biznesową bota
    client = RecipeCookerClient(intents=intents)
    
    # --- URUCHOMIENIE BOTA ---
    try:
        print("🔌 Łączenie z Discord...")
        # client.run() blokuje wykonanie i utrzymuje bota aktywnym
        # do momentu zamknięcia lub błędu
        client.run(DISCORD_TOKEN)
    except discord.errors.LoginFailure:
        # Błąd autoryzacji - zwykle oznacza nieprawidłowy token
        print("❌ BŁĄD: Nieprawidłowy token Discord")
    except Exception as e:
        # Przechwytujemy wszystkie inne błędy
        print(f"❌ Nieoczekiwany błąd: {e}")

