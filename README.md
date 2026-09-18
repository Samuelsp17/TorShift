# TorShift

Rotacionador automático de IP via **Tor**, com integração ao proxy do sistema no **Windows** (funciona com Chrome, Brave, Edge e qualquer app que respeite o proxy do sistema), deduplicação de IPs por sessão, e um **Kill Switch opcional**.

```
 _______        _____ _     _  __ _
|__   __|      / ____| |   (_)/ _| |
   | | ___  _ _| (___ | |__  _| |_| |_
   | |/ _ \| '__\___ \| '_ \| |  _| __|
   | | (_) | |   ____) | | | | | | |_
   |_|\___/|_|  |_____/|_| |_|_|_|  \__|
```

---

## ⚠️ Aviso de uso responsável

Esta ferramenta foi feita para **privacidade pessoal legítima** e **pesquisa de segurança em ambientes autorizados**. Trocar de IP com frequência pode violar os Termos de Serviço de vários sites (scraping, criação de múltiplas contas, evasão de rate-limit, etc.) e, dependendo do uso, pode ter implicações legais. Você é responsável por como utiliza esta ferramenta. Ela **não** foi projetada nem deve ser usada para mascarar ataques (DoS/DDoS), fraude, evasão de banimentos ou qualquer atividade ilegal.

O Kill Switch (explicado mais abaixo) é **best-effort**: ele reduz o risco de vazamento de tráfego fora do Tor, mas **não é uma garantia absoluta** de anonimato à prova de falhas.

---

## O que a ferramenta faz

1. Conecta no **ControlPort** do Tor e solicita um novo circuito (`SIGNAL NEWNYM`) em intervalos definidos por você (mínimo **20 segundos**).
2. Consulta o novo IP de saída e **verifica se ele já foi usado nesta sessão**. Se já foi, descarta e pede outro automaticamente (até um limite de tentativas).
3. Registra tudo em um **log da sessão atual** (`logs/session_<timestamp>.log`).
4. Configura o **proxy do sistema Windows** (registro do Windows) para SOCKS5 do Tor — isso faz com que **qualquer navegador ou app** que use o proxy do sistema (Chrome, Brave, Edge, etc.) passe a navegar pela rede Tor automaticamente, sem precisar configurar cada app manualmente.
5. Se você ativar o **Kill Switch**, a ferramenta monitora continuamente se o tráfego realmente está saindo pelo Tor. Se detectar falha, mostra um **popup nativo do Windows** ("TOR não conectado, erro...") e aplica regras temporárias no Firewall do Windows para reduzir o risco de vazamento, até a conexão normalizar.
6. Ao encerrar (Ctrl+C), **restaura o proxy original do sistema** e remove qualquer regra de firewall temporária.

---

## Requisitos

- **Windows 10/11**
- **Python 3.9+**
- **Tor** instalado e acessível (pode ser o Tor Expert Bundle, ou o `tor.exe` que acompanha o Tor Browser)
- Privilégios de **administrador** apenas se você for usar o Kill Switch (necessário para editar regras do Firewall do Windows)

---

## Instalação

### 1. Instale o Tor

Baixe o **Tor Expert Bundle** em [torproject.org](https://www.torproject.org/download/tor/) (ou use o `tor.exe` dentro da pasta de instalação do Tor Browser). Extraia em um local fixo, por exemplo:

```
C:\Tor\tor.exe
```

### 2. Configure o `torrc`

Dentro da pasta do Tor, crie/edite o arquivo .txt `torrc` com o seguinte conteúdo mínimo:

```
ControlPort 9051
CookieAuthentication 0
HashedControlPassword <hash_gerado_no_passo_abaixo>
SocksPort 9050
```

Gere o hash da sua senha do ControlPort rodando no terminal, dentro da pasta do Tor:

```powershell
tor.exe --hash-password "sua_senha_aqui"
```

Isso vai imprimir algo como:

```
16:8A9B3C...(hash longo)
```

Copie esse valor completo e cole na linha `HashedControlPassword` do `torrc`.

Depois modifique o nome do arquivo dentro do PowerShell: 

```powershell
Rename-Item .\torrc.txt torrc
```

### 3. Inicie o Tor

```powershell
tor.exe -f torrc
```

Deixe essa janela aberta (ou configure o Tor como serviço do Windows, se preferir).

### 4. Instale as dependências do TorShift

Dentro da pasta do projeto:

```powershell
pip install -r requirements.txt
```

### 5. Configure o `config.json`

Abra `config.json` e preencha:

```json
{
    "control_host": "127.0.0.1",
    "control_port": 9051,
    "control_password": "sua_senha_aqui",
    "socks_host": "127.0.0.1",
    "socks_port": 9050,
    "tor_exe_path": "C:\\Tor\\tor.exe",
    "interval_seconds": 60,
    "killswitch_enabled": false,
    "max_retry_duplicate": 8,
    "show_country_lookup": true,
    "notify_on_recovery": true
}
```

> **Importante:** `control_password` aqui é a senha **em texto puro** que você usou no passo 2 — ela é enviada para o Tor autenticar, que a compara internamente com o hash salvo no `torrc`. Nunca compartilhe seu `config.json` preenchido.

---

## Como usar

Execute (de preferência como Administrador, caso vá usar o Kill Switch):

```powershell
python torshift.py
```

A ferramenta vai perguntar:

1. **Intervalo de troca de IP** (mínimo 20 segundos) — aperte Enter para usar o valor padrão do `config.json`.
2. **Ativar Kill Switch?** (s/n)

Depois disso, ela:
- Conecta no Tor
- Ativa o proxy do sistema
- Começa o loop de rotação, mostrando uma contagem regressiva até a próxima troca

Para parar, pressione **Ctrl+C**. A ferramenta restaura automaticamente o proxy original do Windows antes de fechar.

---

## Entendendo os detalhes internos

### Deduplicação de IP por sessão

A cada rotação, o IP obtido é comparado com um conjunto (`set`) de IPs já vistos **desde que a ferramenta foi iniciada**. Esse histórico **não persiste entre execuções** — cada sessão começa do zero, e cada sessão gera seu próprio arquivo de log em `logs/`. Se o novo IP já constar no histórico da sessão atual, a ferramenta solicita outro automaticamente, até `max_retry_duplicate` tentativas (padrão: 8). Isso evita, por exemplo, cair no mesmo exit node duas vezes seguidas.

### Kill Switch — como funciona por dentro

1. Uma thread separada checa, a cada 10 segundos, se o tráfego realmente está saindo pelo Tor (consultando `check.torproject.org/api/ip` através do próprio proxy SOCKS5 do Tor).
2. Se a checagem falhar (Tor caiu, travou, ou parou de responder):
   - Um **popup nativo do Windows** aparece (`MessageBoxW`), mesmo que o terminal esteja minimizado, avisando **"TOR não conectado, erro na conexão..."**.
   - São criadas 3 regras temporárias no Firewall do Windows via `netsh`:
     - Libera o tráfego local (`127.0.0.1`)
     - Libera o próprio processo `tor.exe` (para que ele consiga se recuperar sozinho)
     - **Bloqueia todo o restante do tráfego de saída**
3. Quando a checagem voltar a confirmar que o Tor está ativo, as 3 regras são removidas automaticamente e (se `notify_on_recovery` estiver ativo) um segundo popup avisa que a conexão foi normalizada.

**Limitação a saber:** o Firewall do Windows, por padrão, dá prioridade a regras de **bloqueio** sobre regras de **liberação** quando ambas combinam com o mesmo tráfego. Isso torna essa implementação uma proteção *best-effort* — funciona bem para o caso comum (evitar que o navegador volte a navegar "exposto" silenciosamente após uma queda do Tor), mas não é uma garantia de nível de kernel. Para cenários de altíssima exigência, seria necessário um driver WFP (Windows Filtering Platform) dedicado, fora do escopo deste projeto.

### Proxy do sistema

A ferramenta altera as chaves `ProxyEnable` e `ProxyServer` em:
```
HKEY_CURRENT_USER\Software\Microsoft\Windows\CurrentVersion\Internet Settings
```
Os valores originais são lidos e guardados **antes** de qualquer alteração, e restaurados automaticamente ao encerrar a ferramenta (Ctrl+C, fechamento normal, ou erro fatal — via `atexit`).

Se por algum motivo a ferramenta fechar de forma abrupta (queda de energia, kill do processo) e o proxy não for restaurado, você pode desfazer manualmente em:

**Configurações do Windows → Rede e Internet → Proxy → desative "Usar um servidor proxy"**

---

## Estrutura de arquivos

```
TorShift/
├── torshift.py            # script principal / loop de rotação / CLI
├── config.json             # configurações (ControlPort, senha, intervalo, etc.)
├── requirements.txt
├── modules/
│   ├── tor_control.py      # comunicação com o ControlPort do Tor
│   ├── proxy_manager.py    # gerencia o proxy do sistema Windows (registro)
│   ├── killswitch.py       # heartbeat + popup + regras de firewall
│   └── logger.py           # log da sessão + deduplicação de IPs
└── logs/
    └── session_<timestamp>.log
```

---

## Solução de problemas

**"Não foi possível conectar ao ControlPort"**
Verifique se o `tor.exe` está rodando e se `ControlPort 9051` está no seu `torrc`.

**"Falha na autenticação do ControlPort"**
A senha em `config.json` (`control_password`) precisa ser a senha em texto puro correspondente ao `HashedControlPassword` gerado com `tor.exe --hash-password`.

**A checagem diz que o tráfego não está saindo pelo Tor mesmo com o Tor rodando**
Pode ser lentidão momentânea na construção do circuito. A ferramenta já espera alguns segundos após cada `NEWNYM`, mas em conexões mais lentas pode ser necessário aumentar esse tempo dentro de `torshift.py`.

**O navegador não parece estar usando o Tor**
Confirme em `Configurações do Windows → Proxy` se "Usar um servidor proxy" está ativado e apontando para `socks=127.0.0.1:9050`. Alguns navegadores (principalmente com extensões de proxy próprias) podem ignorar o proxy do sistema — desative extensões desse tipo para testar.

**Kill Switch não bloqueia nada**
Confirme que você está rodando o `torshift.py` como **Administrador** — regras de firewall via `netsh` exigem privilégio elevado.

---

## Licença e responsabilidade

Projeto fornecido "como está", sem garantias, para fins de privacidade pessoal e pesquisa em segurança. Use com responsabilidade e dentro da lei aplicável à sua jurisdição.
