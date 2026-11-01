# models.py

import config

GEMINI_MODELS = [
    "gemini-3.8-flash",
    "gemini-3.6-flash",
    "gemini-3.5-flash-lite",
    "gemini-3.1-flash-lite",
    "gemini-3-flash-preview",
    "gemma-4-31b-it",
    "gemma-4-26b-a4b-it",
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite"
]

GIGACHAT_MODELS = [
    "GigaChat",
    "GigaChat-Pro",
    "GigaChat-Max"
]

# ANSI-цвета для вывода
LIME = '\033[92m'
WHITE = '\033[97m'
RED = '\033[91m'
GREEN = '\033[92m'
CYAN = '\033[96m'
BOLD = '\033[1m'
RESET = '\033[0m'

def show_models():
    provider = config.PROVIDER
    print(f"\n{BOLD}{WHITE}=== ДОСТУПНЫЕ МОДЕЛИ ==={RESET}")
    
    if provider == "gemini":
        key_status = "ЕСТЬ" if config.GEMINI_API_KEY != "твой_ключ_от_гугла" and config.GEMINI_API_KEY else "НЕТ КЛЮЧА"
        print(f"Провайдер: {CYAN}GEMINI{RESET} | Статус ключа: {GREEN if key_status == 'ЕСТЬ' else RED}{key_status}{RESET}")
        print(f"Активная модель: {BOLD}{LIME}{config.GEMINI_MODEL}{RESET}\n")
        
        for i, model in enumerate(GEMINI_MODELS, 1):
            marker = " <-- АКТИВНА" if model == config.GEMINI_MODEL else ""
            color = LIME if model == config.GEMINI_MODEL else WHITE
            print(f"  {i}. {color}{model}{RESET}{marker}")
            
    elif provider == "gigachat":
        key_status = "ЕСТЬ" if config.GIGACHAT_AUTH_KEY != "твой_ключ_от_сбера" and config.GIGACHAT_AUTH_KEY else "НЕТ КЛЮЧА"
        print(f"Провайдер: {CYAN}GIGACHAT{RESET} | Статус ключа: {GREEN if key_status == 'ЕСТЬ' else RED}{key_status}{RESET}")
        print(f"Активная модель: {BOLD}{LIME}{config.GIGACHAT_MODEL}{RESET}\n")
        
        for i, model in enumerate(GIGACHAT_MODELS, 1):
            marker = " <-- АКТИВНА" if model == config.GIGACHAT_MODEL else ""
            color = LIME if model == config.GIGACHAT_MODEL else WHITE
            print(f"  {i}. {color}{model}{RESET}{marker}")
    
    print(f"\n{WHITE}Используй: /model <номер или название>{RESET}")
