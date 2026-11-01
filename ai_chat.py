# ai_chat.py

import sys
import os
import json
import time
import threading
import glob
import re
import subprocess
import zipfile
import uuid
import urllib3
import requests
from bs4 import BeautifulSoup

# МАГИЯ ПУТЕЙ: Добавляем папку Tools в пути поиска Python
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "Tools"))

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

import config
import system_info
import models

# ANSI-цвета
LIME = '\033[92m'
RED = '\033[91m'
WHITE = '\033[97m'
BOLD = '\033[1m'
GREEN = '\033[92m'
CYAN = '\033[96m'
YELLOW = '\033[93m'
RESET = '\033[0m'

CHATS_DIR = "Chats"
MEMORY_FILE = "memory.json"
LAST_CHAT_FILE = "last_chat.txt"
AGENTS_FILE = os.path.join("Tools", "agents.json")

PROTECTED_FILES = [
    "system_prompt.md", "system_prompt.txt", "ai_chat.py",
    "config.py", "system_info.py", "memory.json", "last_chat.txt", "models.py", "agents.json"
]

last_ai_reply = ""
token = None


def is_protected(path):
    filename = os.path.basename(path)
    return filename in PROTECTED_FILES


def ensure_chats_dir():
    if not os.path.exists(CHATS_DIR):
        os.makedirs(CHATS_DIR)


def get_chats():
    ensure_chats_dir()
    files = glob.glob(os.path.join(CHATS_DIR, "*.json"))
    files.sort()
    return files


def load_chat(filepath):
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def save_chat(filepath, history):
    try:
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(history, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(RED + f"Ошибка 601: Не удалось сохранить чат ({e})." + RESET)


def get_current_chat_file():
    chats = get_chats()
    if not chats:
        filepath = os.path.join(CHATS_DIR, "chat_1.json")
        save_chat(filepath, [])
        set_last_chat("chat_1.json")
        return filepath

    last_chat = None
    if os.path.exists(LAST_CHAT_FILE):
        with open(LAST_CHAT_FILE, "r", encoding="utf-8") as f:
            last_chat = f.read().strip()

    if last_chat and os.path.exists(os.path.join(CHATS_DIR, last_chat)):
        return os.path.join(CHATS_DIR, last_chat)

    default_chat = chats[0]
    set_last_chat(os.path.basename(default_chat))
    return default_chat


def set_last_chat(filename):
    try:
        with open(LAST_CHAT_FILE, "w", encoding="utf-8") as f:
            f.write(filename)
    except Exception:
        pass


def load_memory():
    if not os.path.exists(MEMORY_FILE):
        return []
    try:
        with open(MEMORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def save_memory(fact):
    mem = load_memory()
    if fact not in mem:
        mem.append(fact)
        try:
            with open(MEMORY_FILE, "w", encoding="utf-8") as f:
                json.dump(mem, f, ensure_ascii=False, indent=2)
        except Exception:
            pass


def load_agents():
    if not os.path.exists(AGENTS_FILE):
        return {}
    try:
        with open(AGENTS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def load_prompt():
    try:
        filename = "system_prompt.md" if os.path.exists("system_prompt.md") else config.SYSTEM_PROMPT_FILE
        with open(filename, "r", encoding="utf-8") as f:
            base_prompt = f.read().strip()
        mode = getattr(config, "RESPONSE_MODE", "normal")
        base_prompt = base_prompt.replace("{RESPONSE_MODE}", mode.upper())
        mem = load_memory()
        if mem:
            base_prompt += "\n\n## ТВОЯ ПАМЯТЬ (ФАКТЫ ОТ G45):\n"
            for fact in mem:
                base_prompt += f"- {fact}\n"
        return base_prompt
    except FileNotFoundError:
        return "Ты полезный ИИ-ассистент."


def update_config_var(var_name, new_value):
    try:
        with open("config.py", "r", encoding="utf-8") as f:
            content = f.read()

        if isinstance(new_value, bool):
            pattern = rf'{var_name}\s*=\s*(True|False)'
            content = re.sub(pattern, f'{var_name} = {new_value}', content)
        else:
            pattern = rf'{var_name}\s*=\s*".*?"'
            content = re.sub(pattern, f'{var_name} = "{new_value}"', content)

        with open("config.py", "w", encoding="utf-8") as f:
            f.write(content)
        setattr(config, var_name, new_value)
        return True
    except Exception as e:
        print(RED + f"Ошибка 505: Не удалось изменить config.py ({e})." + RESET)
        return False


def get_gigachat_token():
    url = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"
    headers = {
        'Content-Type': 'application/x-www-form-urlencoded',
        'Accept': 'application/json',
        'RqUID': str(uuid.uuid4()),
        'Authorization': f'Basic {config.GIGACHAT_AUTH_KEY}'
    }
    payload = {'scope': 'GIGACHAT_API_PERS'}
    try:
        response = requests.post(url, headers=headers, data=payload, verify=False)
        response.raise_for_status()
        return response.json().get("access_token")
    except Exception as e:
        print(RED + f"Ошибка авторизации GigaChat: {e}" + RESET)
        return None


def clean_reply(text):
    text = text.replace("</K.E.R.N|>>", "</K.E.R.N|>")
    text = re.sub(r'(?<!^)</K\.E\.R\.N\|>', '', text, flags=re.MULTILINE)
    return text


def format_code_blocks(text):
    return text


def print_text(text):
    if getattr(config, "TYPEWRITER_ENABLED", True):
        for char in text:
            sys.stdout.write(LIME + char + RESET)
            sys.stdout.flush()
            time.sleep(0.015)
        print()
    else:
        print(LIME + text + RESET)


def download_file(url, dest_path):
    try:
        os.makedirs(os.path.dirname(dest_path), exist_ok=True)
        print(CYAN + f"\n[NET] Скачивание: {url}" + RESET)
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        response = requests.get(url, headers=headers, stream=True, timeout=30, verify=False)
        response.raise_for_status()
        total_size = int(response.headers.get('content-length', 0))
        block_size = 1024 * 8
        with open(dest_path, 'wb') as file:
            downloaded = 0
            for data in response.iter_content(block_size):
                file.write(data)
                downloaded += len(data)
                if total_size > 0:
                    percent = int((downloaded / total_size) * 100)
                    sys.stdout.write(f"\r{CYAN}[{'=' * (percent // 2)}{' ' * (50 - percent // 2)}] {percent}%{RESET}")
                    sys.stdout.flush()
        print(f"\n{GREEN}Файл успешно скачан: {dest_path}{RESET}")
        return f"Файл скачан в {dest_path}"
    except Exception as e:
        return f"Ошибка скачивания: {e}"


def create_archive(source_path, dest_path):
    try:
        print(CYAN + f"\n[ZIP] Создание архива: {dest_path}" + RESET)
        if source_path.endswith('/'):
            source_path = source_path[:-1]
        base_name = os.path.basename(source_path)
        with zipfile.ZipFile(dest_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            if os.path.isdir(source_path):
                for root, dirs, files in os.walk(source_path):
                    for file in files:
                        file_path = os.path.join(root, file)
                        arcname = os.path.join(base_name, os.path.relpath(file_path, source_path))
                        zipf.write(file_path, arcname)
            else:
                zipf.write(source_path, base_name)
        return f"Архив успешно создан: {dest_path}"
    except Exception as e:
        return f"Ошибка архивации: {e}"


def send_telegram_msg(text):
    if not getattr(config, "TG_BOT_TOKEN", "") or not getattr(config, "TG_CHAT_ID", ""):
        return "Ошибка: токен или Chat ID не заданы в config.py."

    url = f"https://api.telegram.org/bot{config.TG_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": config.TG_CHAT_ID,
        "text": text,
        "parse_mode": "Markdown"
    }

    try:
        response = requests.post(url, json=payload, timeout=15)
        if response.status_code == 200:
            return "Сообщение успешно отправлено в Telegram."
        else:
            return f"Ошибка Telegram: {response.text}"
    except Exception as e:
        return f"Ошибка отправки: {e}"


def run_python_code_sandbox(code_string):
    """Запускает код и возвращает (успех, результат_или_ошибка)."""
    clean_code = code_string.replace("```python", "").replace("```", "").strip()
    temp_file = "temp_test_script.py"
    try:
        with open(temp_file, "w", encoding="utf-8") as f:
            f.write(clean_code)
            
        result = subprocess.run(
            [sys.executable, temp_file], 
            capture_output=True, text=True, timeout=5
        )
        
        if os.path.exists(temp_file):
            os.remove(temp_file)
            
        if result.returncode == 0:
            return True, result.stdout
        else:
            return False, result.stderr
    except subprocess.TimeoutExpired:
        if os.path.exists(temp_file):
            os.remove(temp_file)
        return False, "Ошибка: Превышено время выполнения (таймаут 5 секунд). Возможно, бесконечный цикл."
    except Exception as e:
        if os.path.exists(temp_file):
            os.remove(temp_file)
        return False, f"Системная ошибка при запуске: {e}"


def execute_action(action_data):
    action_type = action_data.get("type")
    if action_type == "download":
        return download_file(action_data.get("url"), action_data.get("path"))
    if action_type == "archive":
        return create_archive(action_data.get("source"), action_data.get("destination"))
    if action_type == "remember":
        fact = action_data.get("fact", "")
        if fact:
            save_memory(fact)
            return f"Факт сохранен: {fact}"
        return "Ошибка: пустой факт."
    if action_type == "web_read":
        url = action_data.get("url")
        print(CYAN + f"\n[NET] Скачиваем и парсим: {url}..." + RESET)
        try:
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
            response = requests.get(url, headers=headers, timeout=15, verify=False)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')
            for script in soup(["script", "style", "nav", "footer", "header"]):
                script.extract()
            text = soup.get_text(separator='\n')
            lines = (line.strip() for line in text.splitlines())
            chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
            text = '\n'.join(chunk for chunk in chunks if chunk)
            return f"Текст сайта ({url}):\n{text[:3000]}"
        except Exception as e:
            return f"Ошибка загрузки: {e}"
    if action_type == "execute":
        code = action_data.get("code", "")
        try:
            with open("temp_exec.py", "w", encoding="utf-8") as f:
                f.write(code)
            result = subprocess.run([sys.executable, "temp_exec.py"], capture_output=True, text=True, timeout=10)
            os.remove("temp_exec.py")
            if result.returncode == 0:
                return f"Вывод:\n{result.stdout}"
            else:
                return f"Ошибка:\n{result.stderr}"
        except subprocess.TimeoutExpired:
            if os.path.exists("temp_exec.py"):
                os.remove("temp_exec.py")
            return "Ошибка: Таймаут."
        except Exception as e:
            return f"Системная ошибка: {e}"

    path = action_data.get("path")
    try:
        if action_type in ["create", "update"]:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                f.write(action_data.get("content", ""))
            return f"Файл {path} успешно создан/обновлен."
        elif action_type == "read":
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    return f"Содержимое файла:\n{f.read()}"
            return "Ошибка 602: Файл не найден."
        elif action_type == "delete":
            if os.path.exists(path):
                os.remove(path)
                return f"Файл {path} удален."
            return "Ошибка 603: Файл не найден."
        return "Ошибка 701: Неизвестный тип."
    except PermissionError:
        return "Ошибка 604: Отказано в доступе."
    except Exception as e:
        return f"Ошибка 606: ({e})."


def show_help():
    print(f"\n{BOLD}{WHITE}=== СПРАВКА ПО КОМАНДАМ ==={RESET}")
    print(f"{CYAN}/help{RESET}       - Показать это меню")
    print(f"{CYAN}/new{RESET}        - Создать новый чат")
    print(f"{CYAN}/list{RESET}       - Список всех чатов")
    print(f"{CYAN}/switch <N>{RESET} - Переключиться на чат номер N")
    print(f"{CYAN}/del{RESET}        - Удалить текущий чат")
    print(f"{CYAN}/memory{RESET}     - Показать сохраненные факты")
    print(f"{CYAN}/provider{RESET}   - Сменить нейросеть")
    print(f"{CYAN}/models{RESET}     - Список моделей")
    print(f"{CYAN}/model <N>{RESET}  - Переключить модель")
    print(f"{CYAN}/request{RESET}    - Вкл/Выкл подтверждение действий")
    print(f"{CYAN}/tw{RESET}         - Вкл/Выкл печатную машинку")
    print(f"{CYAN}/brief{RESET}      - Краткие ответы")
    print(f"{CYAN}/long{RESET}       - Подробные ответы")
    print(f"{CYAN}/normal{RESET}     - Стандартный режим")
    print(f"{CYAN}/chain <задача>{RESET} - Автономный агент (Self-Healing)")
    print(f"{CYAN}/tg <текст>{RESET} - Отправить в Telegram")
    print(f"{CYAN}/tg_code{RESET}    - Отправить последний ответ ИИ в Telegram")
    print(f"{CYAN}/tg_auto{RESET}    - Вкл/Выкл автоотправку в Telegram")
    print(f"{CYAN}quit{RESET}        - Выйти\n")

def main():
    global last_ai_reply, token

    provider = config.PROVIDER
    if provider == "gemini" and (config.GEMINI_API_KEY == "твой_ключ_от_гугла" or not config.GEMINI_API_KEY):
        print(RED + "Ошибка 402: Заполни GEMINI_API_KEY в config.py." + RESET)
        return
    elif provider == "gigachat" and (config.GIGACHAT_AUTH_KEY == "твой_ключ_от_сбера" or not config.GIGACHAT_AUTH_KEY):
        print(RED + "Ошибка 402: Заполни GIGACHAT_AUTH_KEY в config.py." + RESET)
        return

    current_file = get_current_chat_file()
    history = load_chat(current_file)

    os.system('clear')
    system_info.draw(history_len=len(history), chat_name=os.path.basename(current_file))
    print()

    token = None
    if provider == "gigachat":
        print(WHITE + "Авторизация в GigaChat..." + RESET)
        token = get_gigachat_token()
        if not token:
            print(RED + "Авторизация провалена. Введи /provider gemini или перезапусти с VPN." + RESET)

    while True:
        try:
            user_input = input(BOLD + WHITE + "Вы: " + RESET).strip()
            if not user_input:
                continue

            if user_input.lower() in ("quit", "exit", "выход"):
                break

            if user_input.lower().startswith("/"):
                cmd_parts = user_input.split(maxsplit=1)
                cmd = cmd_parts[0].lower()

                if cmd == "/help":
                    show_help()
                    continue
                elif cmd == "/models":
                    models.show_models()
                    continue
                elif cmd == "/model" and len(cmd_parts) > 1:
                    target = cmd_parts[1]
                    current_models = models.GEMINI_MODELS if provider == "gemini" else models.GIGACHAT_MODELS
                    if target.isdigit():
                        idx = int(target) - 1
                        if 0 <= idx < len(current_models):
                            target = current_models[idx]
                        else:
                            print(RED + "Неверный номер модели." + RESET)
                            continue
                    var_name = "GEMINI_MODEL" if provider == "gemini" else "GIGACHAT_MODEL"
                    if update_config_var(var_name, target):
                        print(GREEN + f"Модель изменена на: {target}" + RESET)
                    continue
                elif cmd == "/chain" and len(cmd_parts) > 1:
                    task = cmd_parts[1].strip()
                    if not task:
                        print(WHITE + "Использование: /chain <задача>" + RESET)
                        continue

                    agents = load_agents()
                    coder_cfg = agents.get("Coder", {})
                    reviewer_cfg = agents.get("Reviewer", {})
                    coder_role = coder_cfg.get("role", "Ты — эксперт по Python. Отвечай только кодом.")
                    coder_temp = float(coder_cfg.get("temperature", 0.7))

                    print(CYAN + f"\n[CHAIN] Запуск автономного агента для: {task}" + RESET)

                    def _chain_request(system_role, user_content, temperature, agent_name):
                        if provider == "gemini":
                            url = f"https://generativelanguage.googleapis.com/v1beta/models/{config.GEMINI_MODEL}:generateContent?key={config.GEMINI_API_KEY}"
                            payload = {
                                "systemInstruction": {"parts": [{"text": system_role}]},
                                "contents": [{"role": "user", "parts": [{"text": user_content}]}],
                                "generationConfig": {"temperature": temperature}
                            }
                            r = requests.post(url, headers={"Content-Type": "application/json"}, json=payload, timeout=120, verify=False)
                            if r.status_code != 200:
                                raise RuntimeError(f"API {r.status_code}: {r.text[:200]}")
                            return r.json()["candidates"][0]["content"]["parts"][0]["text"]
                        elif provider == "gigachat":
                            global token
                            if not token:
                                token = get_gigachat_token()
                                if not token: raise RuntimeError("Нет токена GigaChat")
                            
                            model_name = coder_cfg.get("model", "GigaChat-Max") if agent_name == "Coder" else reviewer_cfg.get("model", "GigaChat-Pro")
                            url = "https://gigachat.devices.sberbank.ru/api/v1/chat/completions"
                            headers = {"Content-Type": "application/json", "Authorization": f"Bearer {token}"}
                            payload = {
                                "model": model_name,
                                "messages": [{"role": "system", "content": system_role}, {"role": "user", "content": user_content}],
                                "temperature": temperature
                            }
                            r = requests.post(url, headers=headers, json=payload, timeout=120, verify=False)
                            if r.status_code != 200:
                                raise RuntimeError(f"API {r.status_code}: {r.text[:200]}")
                            return r.json()["choices"][0]["message"]["content"]

                    max_iterations = 3
                    current_code = ""
                    history_context = task

                    for iteration in range(1, max_iterations + 1):
                        print(WHITE + f"\n--- Итерация {iteration} из {max_iterations} ---" + RESET)
                        
                        print(WHITE + "1. [Coder] Пишет код..." + RESET)
                        try:
                            coder_prompt = f"Задача: {history_context}\nВыведи только код, без лишних слов."
                            coder_result = _chain_request(coder_role, coder_prompt, coder_temp, "Coder")
                        except Exception as e:
                            print(RED + f"[Coder] Ошибка: {e}" + RESET)
                            break
                            
                        current_code = coder_result.strip()
                        print(GREEN + "[Coder] Код получен." + RESET)
                        
                        print(WHITE + "2. [Sandbox] Запускаю код..." + RESET)
                        success, run_output = run_python_code_sandbox(current_code)
                        
                        if success:
                            print(GREEN + "[Sandbox] Код работает без ошибок!" + RESET)
                            print(WHITE + "3. [Reviewer] Проверяет логику..." + RESET)
                            try:
                                reviewer_prompt = f"Проверь код на логические ошибки (если все ок, напиши ОК):\n{current_code}"
                                reviewer_result = _chain_request(reviewer_cfg.get("role", "Ты тестировщик."), reviewer_prompt, 0.5, "Reviewer")
                                if "ОК" in reviewer_result.upper() or "НЕТ ОШИБОК" in reviewer_result.upper():
                                    print(GREEN + "[Reviewer] Код идеален." + RESET)
                                    break
                                else:
                                    print(RED + f"[Reviewer] Найдены замечания: {reviewer_result}" + RESET)
                                    history_context = f"Задача: {task}. Твой предыдущий код: {current_code}. Ревьюер сказал: {reviewer_result}. Исправь это."
                            except Exception as e:
                                print(RED + f"[Reviewer] Ошибка API: {e}" + RESET)
                                break
                        else:
                            print(RED + f"[Sandbox] Ошибка выполнения:\n{run_output}" + RESET)
                            history_context = f"Задача: {task}. Твой предыдущий код: {current_code}. Python выдал ошибку:\n{run_output}\nИсправь эту ошибку."
                    
                    print(CYAN + "\n[CHAIN] Финальный код:" + RESET)
                    print(current_code)
                    print(CYAN + "[CHAIN] Работа агента завершена." + RESET)

                    history.append({"role": "user", "parts": [{"text": f"/chain {task}"}]})
                    history.append({"role": "assistant", "parts": [{"text": f"[Code]\n{current_code}"}]})
                    save_chat(current_file, history)
                    continue
                elif cmd == "/brief":
                    update_config_var("RESPONSE_MODE", "brief")
                    print(GREEN + "Режим: КРАТКИЙ" + RESET)
                    continue
                elif cmd == "/long":
                    update_config_var("RESPONSE_MODE", "long")
                    print(GREEN + "Режим: ПОДРОБНЫЙ" + RESET)
                    continue
                elif cmd == "/normal":
                    update_config_var("RESPONSE_MODE", "normal")
                    print(GREEN + "Режим: СТАНДАРТНЫЙ" + RESET)
                    continue
                elif cmd == "/tw":
                    new_state = not getattr(config, "TYPEWRITER_ENABLED", True)
                    update_config_var("TYPEWRITER_ENABLED", new_state)
                    print(GREEN + f"Печатная машинка: {'ВКЛ' if new_state else 'ВЫКЛ'}" + RESET)
                    continue
                elif cmd == "/tg_auto":
                    new_state = not getattr(config, "TG_AUTO_SEND_CODE", False)
                    update_config_var("TG_AUTO_SEND_CODE", new_state)
                    print(GREEN + f"Автоотправка в TG: {'ВКЛ' if new_state else 'ВЫКЛ'}" + RESET)
                    continue
                elif cmd == "/request":
                    new_state = not getattr(config, "AUTO_CONFIRM", False)
                    update_config_var("AUTO_CONFIRM", new_state)
                    print(GREEN + f"Подтверждение действий: {'ВКЛ' if new_state else 'ВЫКЛ'}" + RESET)
                    continue
                elif cmd == "/tg":
                    if len(cmd_parts) < 2:
                        print(WHITE + "Использование: /tg <текст>" + RESET)
                        continue
                    print(CYAN + "Отправка..." + RESET)
                    print(GREEN + send_telegram_msg(cmd_parts[1]) + RESET)
                    continue
                elif cmd == "/tg_code":
                    if not last_ai_reply:
                        print(WHITE + "Нет последнего ответа ИИ." + RESET)
                        continue
                    print(CYAN + "Отправка..." + RESET)
                    print(GREEN + send_telegram_msg(last_ai_reply) + RESET)
                    continue
                elif cmd == "/provider":
                    if len(cmd_parts) < 2:
                        print(WHITE + f"Текущий: {provider.upper()}. /provider gemini или /provider gigachat" + RESET)
                    else:
                        new_provider = cmd_parts[1].lower()
                        if new_provider in ["gemini", "gigachat"]:
                            update_config_var("PROVIDER", new_provider)
                            print(GREEN + f"Провайдер: {new_provider.upper()}. Перезапусти скрипт." + RESET)
                        else:
                            print(RED + "Неизвестный провайдер." + RESET)
                    continue
                elif cmd == "/memory":
                    mem = load_memory()
                    print(WHITE + "Память:" + RESET if mem else "Пусто.")
                    for i, fact in enumerate(mem, 1):
                        print(WHITE + f"  {i}. {fact}" + RESET)
                    continue
                elif cmd == "/new":
                    chats = get_chats()
                    new_name = f"chat_{len(chats) + 1}.json"
                    new_path = os.path.join(CHATS_DIR, new_name)
                    save_chat(new_path, [])
                    set_last_chat(new_name)
                    current_file = new_path
                    history = []
                    os.system('clear')
                    print(GREEN + f"Создан: {new_name}" + RESET)
                    system_info.draw(history_len=0, chat_name=new_name)
                    continue
                elif cmd == "/list":
                    chats = get_chats()
                    print(WHITE + "Чаты:" + RESET)
                    for i, c in enumerate(chats):
                        marker = " <-- АКТИВНЫЙ" if c == current_file else ""
                        print(WHITE + f"  {i+1}. {os.path.basename(c)}{marker}" + RESET)
                    continue
                elif cmd == "/switch" and len(cmd_parts) > 1:
                    try:
                        idx = int(cmd_parts[1]) - 1
                        chats = get_chats()
                        if 0 <= idx < len(chats):
                            current_file = chats[idx]
                            set_last_chat(os.path.basename(current_file))
                            history = load_chat(current_file)
                            os.system('clear')
                            print(GREEN + f"Переключено: {os.path.basename(current_file)}" + RESET)
                            system_info.draw(history_len=len(history), chat_name=os.path.basename(current_file))
                    except Exception:
                        pass
                    continue
                elif cmd == "/del":
                    chats = get_chats()
                    if len(chats) > 1:
                        os.remove(current_file)
                        current_file = get_current_chat_file()
                        history = load_chat(current_file)
                        os.system('clear')
                        print(GREEN + "Удален. Открыт следующий." + RESET)
                        system_info.draw(history_len=len(history), chat_name=os.path.basename(current_file))
                    else:
                        print(RED + "Нельзя удалить последний." + RESET)
                    continue
                else:
                    print(WHITE + "Неизвестная команда. /help." + RESET)
                    continue

            if provider == "gigachat" and not token:
                print(RED + "Нет токена GigaChat. Смени провайдера или перезапусти с VPN." + RESET)
                continue

            print(BOLD + LIME + "K.E.R.N: " + RESET, end="", flush=True)

            is_waiting = True

            def spinner():
                chars = ["-", "\\", "|", "/"]
                i = 0
                while is_waiting:
                    sys.stdout.write(f"\r{BOLD}{LIME}K.E.R.N: [THINK {chars[i % 4]}]{RESET}")
                    sys.stdout.flush()
                    time.sleep(0.15)
                    i += 1
                sys.stdout.write("\r" + " " * 30 + "\r")
                sys.stdout.write(f"{BOLD}{LIME}K.E.R.N: {RESET}")

            t = threading.Thread(target=spinner)
            t.start()

            try:
                full_reply = ""

                if provider == "gemini":
                    url = f"https://generativelanguage.googleapis.com/v1beta/models/{config.GEMINI_MODEL}:generateContent?key={config.GEMINI_API_KEY}"
                    headers = {"Content-Type": "application/json"}
                    prompt_text = load_prompt()

                    contents = []
                    for msg in history:
                        role = "model" if msg["role"] in ["model", "assistant"] else "user"
                        contents.append({"role": role, "parts": [{"text": msg["parts"][0]["text"]}]})
                    contents.append({"role": "user", "parts": [{"text": user_input}]})

                    payload = {
                        "systemInstruction": {"parts": [{"text": prompt_text}]},
                        "contents": contents,
                        "generationConfig": {"temperature": 0.7}
                    }

                    response = requests.post(url, headers=headers, json=payload, timeout=120, verify=False)
                    
                    retries = 3
                    while response.status_code in [503, 429] and retries > 0:
                        is_waiting = False
                        t.join()
                        print(RED + f"\n[API] Сервер Gemini перегружен (код {response.status_code}). Ждем 5 секунд... ({retries} попытки)" + RESET)
                        time.sleep(5)
                        print(WHITE + "Повторный запрос..." + RESET)
                        is_waiting = True
                        t = threading.Thread(target=spinner)
                        t.start()
                        response = requests.post(url, headers=headers, json=payload, timeout=120, verify=False)
                        retries -= 1

                    if response.status_code != 200:
                        raise Exception(f"API {response.status_code}: {response.text}")

                    data = response.json()
                    full_reply = data["candidates"][0]["content"]["parts"][0]["text"]

                elif provider == "gigachat":
                    url = "https://gigachat.devices.sberbank.ru/api/v1/chat/completions"
                    headers = {
                        "Content-Type": "application/json",
                        "Accept": "application/json",
                        "Authorization": f"Bearer {token}"
                    }
                    messages = [{"role": "system", "content": load_prompt()}]
                    for msg in history:
                        role = "assistant" if msg["role"] in ["model", "assistant"] else "user"
                        messages.append({"role": role, "content": msg["parts"][0]["text"]})
                    messages.append({"role": "user", "content": user_input})

                    payload = {
                        "model": config.GIGACHAT_MODEL,
                        "messages": messages,
                        "temperature": 0.7,
                        "stream": False
                    }

                    response = requests.post(url, headers=headers, json=payload, timeout=120, verify=False)
                    if response.status_code == 401:
                        token = get_gigachat_token()
                        if not token:
                            raise Exception("Не удалось обновить токен после 401")
                        headers["Authorization"] = f"Bearer {token}"
                        response = requests.post(url, headers=headers, json=payload, timeout=120, verify=False)
                    if response.status_code != 200:
                        raise Exception(f"API {response.status_code}: {response.text}")

                    data = response.json()
                    full_reply = data["choices"][0]["message"]["content"]

                is_waiting = False
                t.join()

                last_ai_reply = full_reply

                formatted_reply = format_code_blocks(full_reply)
                print_text(formatted_reply)

                if getattr(config, "TG_AUTO_SEND_CODE", False):
                    print(CYAN + "\n[TG] Отправляем..." + RESET)
                    tg_res = send_telegram_msg(full_reply)
                    print(GREEN + f"[TG] {tg_res}" + RESET)

                full_reply = clean_reply(full_reply)
                history.append({"role": "user", "parts": [{"text": user_input}]})
                history.append({"role": "assistant", "parts": [{"text": full_reply}]})
                save_chat(current_file, history)

                action_match = re.search(r'<action>(.*?)</action>', full_reply, re.DOTALL)
                if action_match:
                    try:
                        action_json = action_match.group(1).strip()
                        if action_json.startswith("```json"):
                            action_json = action_json[7:-3].strip()
                        elif action_json.startswith("```"):
                            action_json = action_json[3:-3].strip()

                        action_data = json.loads(action_json)
                        action_type = action_data.get('type')

                        print(WHITE + "\n" + "=" * 40)
                        print(BOLD + WHITE + "ЗАПРОС НА ДЕЙСТВИЕ:" + RESET)
                        print(WHITE + f"Тип: {action_type}")

                        if action_type == "download":
                            print(WHITE + f"URL: {action_data.get('url')}")
                            print(WHITE + f"Куда: {action_data.get('path')}")
                        elif action_type == "archive":
                            print(WHITE + f"Источник: {action_data.get('source')}")
                            print(WHITE + f"Архив: {action_data.get('destination')}")
                        elif action_type == "remember":
                            print(WHITE + f"Факт: {action_data.get('fact')}")
                        elif action_type == "web_read":
                            print(WHITE + f"URL: {action_data.get('url')}")
                        elif action_type == "execute":
                            print(WHITE + f"Язык: {action_data.get('language')}")
                            print(WHITE + "\nКод:")
                            print(YELLOW + "---")
                            print(action_data.get('code'))
                            print(YELLOW + "---" + RESET)
                        else:
                            path = action_data.get('path')
                            print(WHITE + f"Путь: {path}")
                            if is_protected(path) and action_type in ["delete", "update", "create"]:
                                print(RED + f"\nОшибка 801: Файл '{os.path.basename(path)}' защищен!" + RESET)
                                history.append({"role": "user", "parts": [{"text": "System: Ошибка 801. Файл защищен."}]})
                                save_chat(current_file, history)
                                continue

                        auto_confirm = getattr(config, "AUTO_CONFIRM", False)
                        if auto_confirm:
                            print(WHITE + "Автоподтверждение включено, выполняю..." + RESET)
                            confirm = 'y'
                        else:
                            confirm = input(BOLD + GREEN + "\nРазрешить действие? [y/N]: " + RESET).strip().lower()

                        if confirm == 'y':
                            result = execute_action(action_data)
                            if result.startswith("Ошибка"):
                                print(RED + f"РЕЗУЛЬТАТ: {result}" + RESET)
                            else:
                                print(GREEN + f"РЕЗУЛЬТАТ: {result[:500]}..." + RESET)
                            
                            history.append({"role": "user", "parts": [{"text": f"System: {result}"}]})
                            save_chat(current_file, history)
                        else:
                            print(WHITE + "Отменено." + RESET)
                            history.append({"role": "user", "parts": [{"text": "System: Действие отменено пользователем."}]})
                            save_chat(current_file, history)
                    except json.JSONDecodeError as e:
                        print(RED + f"Ошибка 802: Невалидный JSON в action ({e})." + RESET)
                    except Exception as e:
                        print(RED + f"Ошибка 803: Сбой обработки action ({e})." + RESET)

            except KeyboardInterrupt:
                is_waiting = False
                t.join()
                print(WHITE + "\nПрервано." + RESET)
                continue
            except Exception as e:
                is_waiting = False
                t.join()
                print(RED + f"\nОшибка 500: Сбой запроса к API ({e})." + RESET)
                continue

        except KeyboardInterrupt:
            print(WHITE + "\nВыход." + RESET)
            break
        except Exception as e:
            print(RED + f"Ошибка 501: Непредвиденный сбой ({e})." + RESET)
            continue


if __name__ == "__main__":
    main()