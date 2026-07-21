# Contribuindo para o AD Report Hub

Obrigado por considerar contribuir para o AD Report Hub! Este é um projeto focado em simplificar a auditoria de segurança e conformidade do Active Directory.

## Como começar

### 1. Clonar o Repositório
```bash
git clone https://github.com/wweber993/ad-report-hub.git
cd ad-report-hub
```

### 2. Configurar o Ambiente de Desenvolvimento
Crie um ambiente virtual Python:
```bash
python3 -m venv venv
source venv/bin/activate  # ou no Windows: .\venv\Scripts\activate
```

Instale as dependências de desenvolvimento:
```bash
pip install -r requirements.txt
```

### 3. Executando Localmente
O AD Report Hub usa SQLite por padrão para o desenvolvimento local.
```bash
# Inicializar o banco de dados e criar o primeiro admin
python create_admin.py

# Iniciar o servidor de desenvolvimento
flask run --port=8090
```

## Estrutura do Projeto
- `app/` - Aplicação Flask principal.
  - `admin/` - Rotas e lógicas do painel administrativo.
  - `auth/` - Autenticação e MFA.
  - `modules/report_ad/` - Regras de negócio, ingestão de dados e dashboard do Active Directory.
  - `templates/` - Páginas HTML e componentes UI (Jinja2).
  - `static/` - CSS, JS e imagens.
- `scripts/` - Coletores PowerShell que devem ser executados no Active Directory.
- `tests/` - Testes unitários (pytest).

## Testes e Validação
Garantimos a qualidade do código através de testes unitários. Sempre que alterar lógicas críticas (como o motor de cálculo de risco ou conformidade), adicione ou atualize testes.

Para rodar os testes:
```bash
pytest
```

## Padrões de Commit
Utilizamos mensagens de commit claras e descritivas, de preferência em inglês:
- `feat: added new compliance control`
- `fix: resolved issue with MFA reset`
- `docs: updated readme instructions`

## Submetendo um Pull Request
1. Faça um *fork* do repositório.
2. Crie uma *branch* para a sua feature (`git checkout -b feature/minha-feature`).
3. Faça *commit* das suas alterações.
4. Envie a *branch* para o seu fork (`git push origin feature/minha-feature`).
5. Abra um Pull Request e descreva claramente a motivação e as alterações realizadas.

Agradecemos imensamente a sua contribuição!
