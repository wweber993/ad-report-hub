# Módulo Report AD — AD Report Hub

> **Versão:** 2.0 | **Plataforma:** AD Report Hub | **Data:** Julho/2026

---

## 1. Visão Geral

O módulo **Report AD** é o núcleo central do **AD Report Hub**, responsável por coletar, processar e visualizar dados de usuários do **Active Directory (AD)** de um ou mais ambientes corporativos. Ele fornece um painel de segurança centralizado com análise de riscos, conformidade com frameworks de segurança (ISO 27001 e SOC 2 Type II) e gestão de exceções aprovadas.

### Objetivo Principal

Dar visibilidade completa ao time de segurança e auditoria sobre o estado das contas de usuário no AD, identificando vulnerabilidades e riscos como:
- Contas inativas com acesso ativo
- Usuários com privilégios administrativos excessivos (Domain Admins, Enterprise Admins, etc.)
- Senhas que nunca expiram ou senhas expiradas
- Contas de serviço expostas (SPNs configurados / Kerberoasting risk)
- Contas bloqueadas por falhas repetidas de autenticação

---

## 2. Arquitetura do Módulo

```text
app/modules/report_ad/
├── __init__.py          # Define o Blueprint Flask (ad_bp)
├── routes.py            # Endpoints HTTP (páginas e APIs)
└── utils/
    ├── __init__.py
    └── data_manager.py  # Lógica de negócio: carga de dados, scoring de risco, compliance
```

### Fluxo de Dados

```text
Active Directory (DC)
       │
       ▼
[report_ad.ps1] ──────POST /ad/api/ingest──────▶  [AD Report Hub]
(Script PowerShell)   (X-API-Key Header)          (Salva JSON em data/ad)
                                                         │
                                                         ▼
                                               [data_manager.py]
                                               (Carrega, enriquece
                                                e calcula riscos)
                                                         │
                                                         ▼
                                                [APIs REST + Frontend]
                                                (Dashboard / ISO-SOC)
```

---

## 3. Coleta de Dados — Script PowerShell (`scripts/report_ad.ps1`)

O script `scripts/report_ad.ps1` é executado em um servidor Windows com suporte ao módulo RSAT `ActiveDirectory`.

### Recursos do Coletor
1. **Configuração Integrada**: Todas as configurações são feitas em um único arquivo, basta editar as variáveis no topo do próprio script `report_ad.ps1`. Sem necessidade de arquivos `.json` adicionais ou dezenas de parâmetros.
2. **Instalação Automática**: Pode se auto-registrar no Windows Task Scheduler via o parâmetro `-InstallTask`.
3. **Auto-descoberta de DCs**: Consulta controladores de domínio para obter o último logon real (`Get-TrueLastLogon`).
4. **Análise de Privilégios**: Mapeia grupos administrativos de forma recursiva (LDAP Matching Rule In Chain).

### Exemplo de Execução CLI

Primeiro, edite as variáveis no bloco `$CONFIG` no topo do arquivo `report_ad.ps1`.
Depois, execute o script sem parâmetros:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\report_ad.ps1
```

Para registrar a execução diária automaticamente:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\report_ad.ps1 -InstallTask -TaskTime "02:00"
```

---

## 4. Endpoints da API

| Método | Rota | Auth | Descrição |
|---|---|---|---|
| `GET` | `/ad/` ou `/ad/dashboard` | Sessão | Painel principal de usuários e riscos |
| `GET` | `/ad/iso-soc` | Sessão | Painel de conformidade ISO 27001 / SOC 2 |
| `GET` | `/ad/api/users` | Sessão | Lista todos os usuários com scores calculados |
| `GET` | `/ad/api/stats` | Sessão | Estatísticas consolidadas do ambiente |
| `POST` | `/ad/api/ingest` | `X-API-Key` | Recebe dados coletados pelo script PowerShell |
| `GET` | `/ad/api/iso-soc` | Sessão | Dados de conformidade ISO/SOC por controle |
| `POST` | `/ad/api/exceptions/<username>` | Sessão | Registra exceção aprovada para um usuário |
| `DELETE` | `/ad/api/exceptions/<username>` | Sessão | Remove exceção de um usuário |
