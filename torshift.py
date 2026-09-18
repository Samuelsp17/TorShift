#!/usr/bin/env python3
"""
TorShift - Rotacionador automatico de IP via Tor com integracao ao proxy
do sistema Windows, deduplicacao de IPs por sessao e kill switch opcional.

Uso responsavel: esta ferramenta e destinada a privacidade pessoal e
pesquisa de seguranca em ambientes autorizados. Ver README.md.
"""

import sys
import os
import json
import time
import signal
import atexit

try:
    import pyfiglet
    HAS_PYFIGLET = True
except ImportError:
    HAS_PYFIGLET = False

try:
    from colorama import init as colorama_init, Fore, Style
    colorama_init(autoreset=True)
    HAS_COLORAMA = True
except ImportError:
    HAS_COLORAMA = False

    class _Dummy:
        def __getattr__(self, _):
            return ""

    Fore = Style = _Dummy()

from modules.logger import SessionLogger
from modules.tor_control import TorController, TorControlError
from modules.proxy_manager import ProxyManager, ProxyManagerError, IS_WINDOWS
from modules.killswitch import KillSwitch

CONFIG_PATH = "config.json"
MIN_INTERVAL_SECONDS = 20


# ============================================================ UI helpers
def print_banner():
    title = "TorShift"
    if HAS_PYFIGLET:
        try:
            print(Fore.CYAN + pyfiglet.figlet_format(title, font="slant"))
        except Exception:
            print(Fore.CYAN + f"=== {title} ===")
    else:
        print(Fore.CYAN + r"""
 _______        _____ _     _  __ _
|__   __|      / ____| |   (_)/ _| |
   | | ___  _ _| (___ | |__  _| |_| |_
   | |/ _ \| '__\___ \| '_ \| |  _| __|
   | | (_) | |   ____) | | | | | | |_
   |_|\___/|_|  |_____/|_| |_|_|_|  \__|
        """)
    print(Style.DIM + "  Rotacionador automatico de IP via Tor | uso responsavel\n")


def info(msg):
    print(Fore.CYAN + "[*] " + Style.RESET_ALL + msg)


def ok(msg):
    print(Fore.GREEN + "[OK] " + Style.RESET_ALL + msg)


def warn(msg):
    print(Fore.YELLOW + "[!] " + Style.RESET_ALL + msg)


def error(msg):
    print(Fore.RED + "[ERRO] " + Style.RESET_ALL + msg)


# ============================================================ Config
def load_config():
    if not os.path.exists(CONFIG_PATH):
        error(f"Arquivo {CONFIG_PATH} nao encontrado. Restaure-o a partir do repositorio original.")
        sys.exit(1)
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def ask_interval(default_value):
    while True:
        raw = input(
            f"Intervalo de troca de IP em segundos (minimo {MIN_INTERVAL_SECONDS}) "
            f"[Enter = {default_value}]: "
        ).strip()

        if not raw:
            return default_value

        if not raw.isdigit():
            warn("Digite apenas numeros inteiros.")
            continue

        value = int(raw)
        if value < MIN_INTERVAL_SECONDS:
            warn(f"O intervalo minimo permitido e {MIN_INTERVAL_SECONDS} segundos.")
            continue

        return value


def ask_killswitch(default_value):
    default_label = "S" if default_value else "N"
    raw = input(f"Ativar Kill Switch? (s/n) [Enter = {default_label}]: ").strip().lower()
    if not raw:
        return default_value
    return raw.startswith("s")


# ============================================================ Main
def main():
    print_banner()
    config = load_config()

    if not IS_WINDOWS:
        warn("Esta ferramenta foi projetada para Windows (altera o proxy do sistema "
             "e usa o Firewall do Windows). Algumas funcoes serao simuladas/desativadas.")

    interval = ask_interval(config.get("interval_seconds", 60))
    killswitch_enabled = ask_killswitch(config.get("killswitch_enabled", False))

    logger = SessionLogger()
    info(f"Log desta sessao: {logger.log_path}")

    controller = TorController(
        control_host=config["control_host"],
        control_port=config["control_port"],
        control_password=config.get("control_password", ""),
        socks_host=config["socks_host"],
        socks_port=config["socks_port"],
    )

    proxy_manager = None
    killswitch = None

    # ------------------------------------------------------------
    def cleanup(*_):
        warn("Encerrando TorShift e restaurando configuracoes originais...")
        try:
            if killswitch:
                killswitch.stop()
        except Exception as e:
            error(f"Falha ao parar kill switch: {e}")

        try:
            if proxy_manager and proxy_manager.is_active:
                proxy_manager.disable_proxy()
                ok("Proxy do sistema restaurado ao estado original.")
        except ProxyManagerError as e:
            error(f"Falha ao restaurar proxy: {e}")

        try:
            controller.close()
        except Exception:
            pass

        logger.close()
        print(Style.DIM + f"\nResumo da sessao: {logger.summary()}")
        sys.exit(0)

    atexit.register(cleanup)
    signal.signal(signal.SIGINT, cleanup)
    signal.signal(signal.SIGTERM, cleanup)

    # ------------------------------------------------------------
    try:
        info("Conectando ao ControlPort do Tor...")
        controller.connect()
        ok("Autenticado no ControlPort com sucesso.")
    except TorControlError as e:
        error(str(e))
        sys.exit(1)

    if IS_WINDOWS:
        try:
            info("Configurando proxy do sistema (Windows) para usar o Tor...")
            proxy_manager = ProxyManager()
            proxy_manager.enable_socks_proxy(config["socks_host"], config["socks_port"])
            ok(f"Proxy do sistema ativo -> socks={config['socks_host']}:{config['socks_port']}")
        except ProxyManagerError as e:
            error(str(e))
            sys.exit(1)
    else:
        warn("Pulei a configuracao de proxy do sistema (nao estamos no Windows).")

    if killswitch_enabled:
        info("Iniciando Kill Switch em background...")
        killswitch = KillSwitch(
            tor_controller=controller,
            tor_exe_path=config.get("tor_exe_path", ""),
            check_interval=10,
            logger=logger,
            notify_on_recovery=config.get("notify_on_recovery", True),
        )
        killswitch.start()
        ok("Kill Switch ativo.")

    info(f"Rotacao automatica de IP a cada {interval} segundos. Ctrl+C para parar.\n")

    max_retries = config.get("max_retry_duplicate", 8)

    # ------------------------------------------------------------ Loop principal
    while True:
        try:
            controller.new_identity()
            time.sleep(3)  # tempo para o Tor construir o novo circuito

            attempt = 0
            while attempt < max_retries:
                status = controller.get_current_ip()
                ip = status.get("ip")

                if not status.get("is_tor"):
                    warn("A checagem indica que o trafego NAO esta saindo pelo Tor no momento.")

                if ip and not logger.is_duplicate(ip):
                    country = None
                    if config.get("show_country_lookup") and ip:
                        country = controller.get_country(ip)
                    logger.register_ip(ip, country=country)
                    pais_txt = f" ({country})" if country else ""
                    ok(f"Novo IP de saida: {ip}{pais_txt}")
                    break
                else:
                    logger.register_ip(ip, duplicate=True)
                    warn(f"IP repetido ({ip}), solicitando outro...")
                    controller.new_identity()
                    time.sleep(3)
                    attempt += 1
            else:
                warn(f"Nao foi possivel obter um IP inedito apos {max_retries} tentativas. "
                     f"Seguindo com o ultimo IP obtido.")

        except TorControlError as e:
            error(f"Erro de comunicacao com o Tor: {e}")

        for remaining in range(interval, 0, -1):
            print(f"\r{Style.DIM}Proxima troca em {remaining:>3}s...{Style.RESET_ALL}", end="")
            time.sleep(1)
        print("\r" + " " * 40 + "\r", end="")


if __name__ == "__main__":
    main()
