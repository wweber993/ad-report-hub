# AD Report Hub 🛡️

*🌎 Leia em outros idiomas: [Inglês (English)](README.md), [Português](README.pt-br.md).*

O **AD Report Hub** é uma plataforma de código aberto voltada à comunidade, projetada para simplificar o monitoramento de segurança, governança de privilégios, pontuação de riscos e acompanhamento de conformidade (ISO 27001 & SOC 2 Type II) do Active Directory.

---

## 🚀 Principais Recursos

- 👤 **Auditoria de Usuários e Contas do AD**: Monitora contas ativas, inativas, bloqueadas e desativadas do domínio.
- ⚡ **Motor de Pontuação de Riscos (Risk Scoring)**: Calcula automaticamente a pontuação de risco das contas com base em inatividade, senhas expiradas, privilégios administrativos, SPNs (Service Principal Names) e senhas que nunca expiram.
- 🛡️ **Governança e Rastreamento de Privilégios**: Identifica associações a grupos privilegiados (Domain Admins, Enterprise Admins, Schema Admins, etc.) e contas de serviço.
- 📊 **Painel de Conformidade (Compliance)**: Mapeia as métricas do AD para os controles da **ISO 27001:2022** e **SOC 2 Type II**.
- 📝 **Gestão de Exceções Aprovadas**: Registre e gerencie exceções formais de segurança para contas legítimas (ex.: contas de serviço antigas, processos em lote).
- 🔄 **Coletor de Dados Automatizado**: Um script PowerShell leve (`scripts/report_ad.ps1`) configurado para integração simples com o Agendador de Tarefas do Windows ou execução manual.

---

## 🏗️ Arquitetura e Fluxo

```text
Active Directory (Controlador de Domínio)
              │
              ▼
    [Coletor report_ad.ps1]
    (Executa no Servidor AD)
              │
              ▼ HTTP POST (X-API-Key) / Exportação Local JSON
       [AD Report Hub]
       (Aplicação Web Flask)
              │
              ▼
  [Painel de Segurança e Conformidade]
```

---

## 🛠️ Guia de Início Rápido

### Pré-requisitos
- **Ubuntu 24.04 LTS (Recomendado)** ou qualquer distribuição Linux moderna para a aplicação web.
- **Python 3.10+** (Python 3.12 padrão do Ubuntu 24.04 é totalmente suportado).
- **PowerShell 5.1+** com o módulo RSAT `ActiveDirectory` (Rodando separadamente no Controlador de Domínio Windows).

> [!NOTE]
> **Arquitetura Multi-Ambiente**: O AD Report Hub foi projetado para rodar seu painel web em um servidor Linux seguro (ex: Ubuntu 24.04), enquanto o script leve de coleta de dados (`report_ad.ps1`) roda de forma independente no seu servidor Active Directory (Windows). Eles se comunicam de forma segura via HTTPS/API.

### 1. Instalação (Linux / Ubuntu 24.04)

Para um ambiente de produção, recomendamos implantar a aplicação em `/opt/report-hub`.

```bash
# 1. Atualizar e instalar dependências
sudo apt update
sudo apt install python3 python3-venv python3-pip git -y

# 2. Clonar repositório para /opt
cd /opt
git clone https://github.com/wweber993/report-ad-hub.git report-hub
sudo chown -R $USER:$USER /opt/report-hub
cd report-hub

# 3. Criar ambiente virtual e instalar pacotes
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 4. Configurar variáveis de ambiente
cp .env.example .env
# Edite o arquivo .env para definir seu INGEST_TOKEN, PORT e WEBHOOK_URL
nano .env

# 5. Inicializar banco de dados e criar primeiro administrador
flask db upgrade
python create_admin.py
```

### 2. Executando a Aplicação (Systemd + Gunicorn)

Para manter a aplicação rodando em segundo plano, você pode configurar um serviço Systemd.
Crie um arquivo em `/etc/systemd/system/report-hub.service`:

```bash
sudo nano /etc/systemd/system/report-hub.service
```

```ini
[Unit]
Description=AD Report Hub Daemon
After=network.target

[Service]
User=www-data
Group=www-data
WorkingDirectory=/opt/report-hub
Environment="PATH=/opt/report-hub/venv/bin"
ExecStart=/opt/report-hub/venv/bin/gunicorn -w 4 -b 0.0.0.0:8090 app:app

[Install]
WantedBy=multi-user.target
```

Em seguida, habilite e inicie o serviço:
```bash
sudo systemctl daemon-reload
sudo systemctl enable report-hub
sudo systemctl start report-hub
```

Acesse a aplicação no navegador em: `http://<seu-ip-do-servidor>:8090/`
*Nota: No seu primeiro acesso, você será solicitado a configurar o seu Aplicativo Autenticador (Google Authenticator / Authy) para a Autenticação em Duas Etapas (MFA).*

### 3. Instalação Alternativa (Windows / Local)
Se preferir testar a aplicação localmente no Windows, um script de instalação automatizado está disponível:
```powershell
git clone https://github.com/wweber993/ad-report-hub.git
cd ad-report-hub
.\install_hub.ps1
```

---

## 📊 Script de Coleta de Dados (`scripts/report_ad.ps1`)

O script coletor roda em qualquer servidor Windows com as ferramentas RSAT do AD instaladas.

### Configuração

Em vez de digitar vários parâmetros no terminal, toda a configuração é feita diretamente no topo do arquivo **`scripts/report_ad.ps1`**.
Basta abrir o script em qualquer editor de texto e atualizar o bloco `$CONFIG`:

```powershell
$CONFIG = @{
    Environment = "Producao"
    ApiUrl      = "http://localhost:8090/ad/api/ingest"
    ApiToken    = "seu_token_de_ingestao_aqui"
    # ... outras opções
}
```

Depois, execute o coletor sem nenhum argumento:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\report_ad.ps1
```

### Instalação Automática no Agendador de Tarefas do Windows

Para facilitar e rodar o coletor diariamente no seu servidor Active Directory, você pode usar a chave de instalação embutida:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\report_ad.ps1 -InstallTask -TaskTime "02:00"
```

Isso registrará uma tarefa diária chamada `ADReportHub_Collector` que será executada com os privilégios `SYSTEM` usando o script atual.

---

## 🔒 Segurança e Boas Práticas

- **Segurança de Token**: Sempre configure um `INGEST_TOKEN` forte no seu `.env` e insira o mesmo no bloco `$CONFIG` do `report_ad.ps1`.
- **HTTPS/SSL**: Ative certificados SSL em produção configurando `SSL_CERT` e `SSL_KEY` no `.env` ou colocando um proxy reverso (Nginx, IIS) na frente do Gunicorn/Flask.

---

## 🤝 Contribuições e Comunidade

Contribuições, solicitações de funcionalidades e relatos de bugs são muito bem-vindos! Fique à vontade para abrir "issues" ou enviar "Pull Requests".

## 📄 Licença

Este projeto é de código aberto sob a **Licença MIT**.
