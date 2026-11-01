# system_info.py

import platform
import config

# ANSI-цвета
W = '\033[97m' # White
C = '\033[96m' # Cyan
B = '\033[1m'  # Bold
R = '\033[91m' # Red
G = '\033[92m' # Green
RS = '\033[0m' # Reset

def draw(history_len=0, chat_name="chat_1.json"):
    uname = platform.uname()
    cpu_arch = uname.machine if uname.machine else "ARM64"
    
    mode = getattr(config, "RESPONSE_MODE", "normal").upper()
    provider = config.PROVIDER.upper()
    
    # Определяем активную модель в зависимости от провайдера
    if provider == "GEMINI":
        current_model = getattr(config, "GEMINI_MODEL", "N/A")
        api_status = "ACTIVE" if getattr(config, "GEMINI_API_KEY", "") not in ("", "твой_ключ_от_гугла") else "NO KEY"
    elif provider == "GIGACHAT":
        current_model = getattr(config, "GIGACHAT_MODEL", "N/A")
        api_status = "ACTIVE" if getattr(config, "GIGACHAT_AUTH_KEY", "") not in ("", "твой_ключ_от_сбера") else "NO KEY"
    else:
        current_model = "UNKNOWN"
        api_status = "UNKNOWN"
        
    # Красим статус: зеленый если ACTIVE, красный если NO KEY
    status_color = G if api_status == "ACTIVE" else R
    
    # Твой GUI
    gui = f"""
█████████████████████████████████   
            
                       {B}AI: K.E.R.N CODE{RS}
        ███████        {W}OS: Droid{RS}
 ██ █░███░█ ██         {W}CPU: {cpu_arch}{RS}
        ███████        {W}API: {status_color}{api_status}{RS}
            █       █  {W}MODEL: {current_model}{RS}
                       {W}CTX: {history_len} msg{RS}

█████████████████████████████████

{W}ACTIVE CHAT: {RS}{B}{chat_name}{RS}
{W}PROV: {C}{provider}{RS} {W}| MODE: {C}{mode}{RS}
{W}ENTER "/HELP" FOR COMMANDS{RS}

█████████████████████████████████

{B}{W}K.E.R.N CODE [{status_color}{api_status}{RS}{B}{W}]{RS}

█████████████████████████████████
    """
    print(gui)

if __name__ == "__main__":
    draw(0, "chat_1.json")