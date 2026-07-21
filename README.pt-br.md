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
- **Python 3.9+**
- **PowerShell 5.1+** com o módulo RSAT `ActiveDirectory` instalado no Controlador de Domínio ou em uma máquina de gerenciamento ingressada no domínio.

### 1. Instalação (Windows)

A maneira mais fácil de começar é utilizando o instalador automatizado integrado para Windows:

```powershell
git clone https://github.com/wweber993/ad-report-hub.git
cd ad-report-hub

# Execute o assistente de instalação
.\install_hub.ps1
```

O instalador solicitará interativamente as configurações necessárias (porta, token de ingestão), criará um ambiente virtual Python, instalará as dependências e ajudará a criar a primeira conta de Administrador.

### 2. Instalação Manual (Linux / macOS)

Se você não estiver no Windows, pode instalar a plataforma manualmente:

```bash
git clone https://github.com/wweber993/ad-report-hub.git
cd ad-report-hub

python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# Edite o arquivo .env para definir o INGEST_TOKEN e a porta (PORT)

python create_admin.py
```

### 3. Executando a Aplicação Web

Inicie a aplicação utilizando o ambiente virtual:

#### Windows:
```powershell
.\venv\Scripts\python app.py
```

#### Linux/macOS:
```bash
python app.py
```

#### Modo de Produção (Gunicorn/Linux):
```bash
gunicorn -w 2 -b 0.0.0.0:8090 'app:app'
```

Acesse a aplicação no navegador em: `http://localhost:8090/`
*Nota: No seu primeiro acesso, você será solicitado a configurar o seu Aplicativo Autenticador (Google Authenticator / Authy) para a Autenticação em Duas Etapas (MFA).*

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
