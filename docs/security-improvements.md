# Melhorias adicionais de segurança — passo a passo

Esta entrega implementa duas melhorias adicionais ao fluxo funcional de cadastro, login, perfil, consultas e chats:

| Melhoria | Implementação nova | Verificação |
| --- | --- | --- |
| M01 — Rate limiting na API | Cota por IP, cota de consultas por usuário, resposta `429`, recuperação da janela e armazenamento compartilhado exigido fora do modo local | Oito testes específicos, incluindo isolamento, tentativa de falsificar IP e falha de armazenamento |
| M02 — Headers HTTP | CSP, bloqueio de enquadramento e política de permissões na API e no frontend; HSTS condicional na API | Três testes específicos no backend e verificação HTTP da página e do JavaScript no Vite/preview |

Os exemplos da atividade são alternativas: o requisito de pelo menos duas melhorias é atendido por **rate limiting** e **headers de segurança**. A validação consistente de entradas, já existente em `backend/validation.py`, permanece como controle complementar. As duas melhorias acima não dependem de implementar hashing próprio de senhas ou substituir o Firebase Authentication.

A etapa posterior de [observabilidade](observability.md) adiciona logs JSON, `/health` e `/metrics`. Essas duas rotas e `OPTIONS` ficam isentas das cotas de negócio; o acesso às métricas tem proteção própria. As evidências e os números de testes abaixo permanecem como histórico desta etapa de segurança.

## Parte 1 — Instalar as dependências

Na raiz do repositório, com o ambiente virtual preparado conforme [setup.md](setup.md):

```powershell
.\backend\.venv\Scripts\python.exe -m pip install -r backend/requirements.txt
cd frontend
npm ci
cd ..
```

O backend usa `Flask-Limiter[redis]==4.1.1`. O extra instala o cliente Redis necessário ao armazenamento compartilhado. Nenhuma instância externa de Redis é provisionada por esses comandos.

## Parte 2 — Implementar o rate limiting

### 2.1 — Definir as cotas

Em [rate_limiting.py](../backend/rate_limiting.py), foram definidos:

- **120 requisições por minuto por IP**, compartilhadas entre as rotas reconhecidas da API, antes de verificar o token.
- **20 consultas válidas por minuto por UID** em `POST /users/query`, depois de autenticar e validar a consulta, antes de buscar o perfil e gerar a resposta.
- Janela móvel: a liberação considera as requisições ocorridas nos últimos 60 segundos.
- Requisições `OPTIONS` de preflight não consomem a cota da aplicação.

As cotas são valores iniciais para esta aplicação e devem ser calibradas conforme tráfego e capacidade. O limite global por IP também afeta usuários que compartilham uma rede ou proxy.

### 2.2 — Escolher as identidades corretamente

1. A cota de IP usa `request.remote_addr`, fornecido pelo servidor HTTP.
2. `X-Forwarded-For` enviado pelo cliente não é usado para escolher a cota; nenhum `ProxyFix` foi habilitado implicitamente.
3. A cota de consultas usa `g.uid`, obtido pela verificação do token. Trocar de IP ou renovar o token não cria uma nova cota para o mesmo UID.
4. As chaves armazenadas usam prefixo e SHA-256 do identificador, sem incluir o token Bearer. Isso evita armazenar o token e os identificadores em texto direto nessas chaves; não torna IPs anônimos nem substitui regras de privacidade do armazenamento.

Atrás de um gateway, o endereço visto pela API pode ser o do próprio gateway, compartilhando a cota de IP. Configure a limitação por IP original também no gateway. Confiar em cabeçalhos encaminhados exige conhecer e restringir exatamente quais proxies são confiáveis; essa configuração não foi presumida.

### 2.3 — Configurar o armazenamento

**Desenvolvimento local:** ao iniciar `endpoints.py` no modo local, o armazenamento padrão é `memory://`. Ele dispensa Redis, mas cada processo tem seus próprios contadores e eles são perdidos ao reiniciar.

**Modo Firebase real:** a API exige uma URL Redis explícita em `COURSESPHERE_RATE_LIMIT_STORAGE_URI`. Todos os processos e instâncias da aplicação devem usar o mesmo armazenamento e namespace. Exemplo para uma instância Redis já disponível no mesmo host:

```powershell
$env:COURSESPHERE_RATE_LIMIT_STORAGE_URI = "redis://127.0.0.1:6379/0"
.\backend\.venv\Scripts\python.exe backend/endpoints.py --firebase
```

Para Redis remoto, use `rediss://` com TLS. A configuração recusa `memory://` fora do modo local e recusa Redis remoto sem TLS. Credenciais reais da URL devem ser fornecidas pelo ambiente ou mecanismo privado de configuração, não versionadas.

### 2.4 — Integrar à API

Em [endpoints.py](../backend/endpoints.py):

1. Gerar `request_id` antes de inicializar os hooks do limitador, para que erros de quota também tenham correlação.
2. Aplicar o limite global na entrada da requisição.
3. Na consulta, usar o limitador dentro de um bloco executado depois de `require_auth`; assim, a chave por usuário só é calculada quando o UID já foi verificado.
4. Responder com JSON genérico, status `429` e `Retry-After` quando a cota for excedida. O código protegido não continua sendo executado.
5. Em falha do armazenamento de cotas, responder `503` com mensagem genérica e `Retry-After: 5`. Não há fallback automático para memória nem liberação silenciosa da requisição.

Os cabeçalhos `X-RateLimit-Limit`, `X-RateLimit-Remaining` e `X-RateLimit-Reset` são emitidos pela extensão. Não usar as cotas como mecanismo de autorização: elas se somam à verificação do token e do proprietário dos dados.

### 2.5 — Reproduzir o bloqueio local

Inicie uma instância nova da API em modo local, conforme [setup.md](setup.md), sem outras chamadas concorrentes. No PowerShell, execute:

```powershell
$statuses = foreach ($attempt in 1..121) {
    try {
        (Invoke-WebRequest -Uri "http://127.0.0.1:5000/users/info" -UseBasicParsing).StatusCode
    } catch {
        [int]$_.Exception.Response.StatusCode
    }
}
$statuses | Group-Object | Select-Object Name, Count
curl.exe -i "http://127.0.0.1:5000/users/info"
```

Como não há token, as primeiras 120 chamadas retornam `401`; a próxima retorna `429` antes da verificação de identidade. O `curl` permite conferir `Retry-After`. A cota libera capacidade conforme as chamadas anteriores saem da janela de 60 segundos; reiniciar o processo local também apaga os contadores em memória.

Para a cota por usuário, os testes automatizados reduzem temporariamente o valor a duas consultas por minuto, usam verificação de token simulada e demonstram que a terceira consulta é bloqueada, outro usuário mantém sua própria cota e trocar de IP não contorna o limite. A expiração da janela é testada avançando o relógio simulado, sem esperar um minuto.

### 2.6 — Limites desta melhoria

Este controle **mitiga abuso e consumo excessivo**, mas não resolve sozinho DDoS, ataques distribuídos, criação de muitas contas ou esgotamento de conexões. O armazenamento em Redis, suas permissões, disponibilidade e TLS precisam de configuração operacional.

O login e o cadastro de senha acontecem diretamente no Firebase Authentication. **Não foi implementado bloqueio de tentativas de senha no Firebase**, e o rate limiting da API não deve ser apresentado como esse controle. Quotas e proteção contra abuso do provedor continuam sendo configurações separadas.

## Parte 3 — Implementar os headers HTTP

### 3.1 — Aplicar uma política à API JSON

[security_headers.py](../backend/security_headers.py) centraliza os cabeçalhos e é chamado pelo `after_request` da API:

| Header | Valor/política | Finalidade |
| --- | --- | --- |
| `Content-Security-Policy` | `default-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'` | Política restritiva para respostas da API, que servem JSON |
| `X-Frame-Options` | `DENY` | Recusar enquadramento da resposta |
| `X-Content-Type-Options` | `nosniff` | Usar o tipo de conteúdo declarado |
| `Permissions-Policy` | `camera=(), microphone=(), geolocation=()` | Desabilitar recursos não usados pela aplicação |
| `Referrer-Policy` | `no-referrer` | Evitar envio de referência a partir desses documentos |
| `Cache-Control` | `no-store` | Evitar armazenamento das respostas da API |
| `Strict-Transport-Security` | `max-age=31536000`, somente quando `request.is_secure` | Declarar uso futuro de HTTPS para o host que recebeu a resposta segura |

`X-Request-ID` continua sendo emitido para correlação. Os headers também são aplicados às respostas de erro, incluindo `400`, `401`, `404`, `405`, `429` e `500`, não apenas às respostas de sucesso.

### 3.2 — Proteger o documento do frontend

Headers da API não protegem automaticamente o HTML da SPA. Por isso, a política também foi configurada em:

- [nginx.conf](../frontend/nginx.conf): headers com `always`, incluindo erros como o `503` de `/api/` sem gateway.
- [vite.config.ts](../frontend/vite.config.ts): headers no servidor de desenvolvimento e no preview do build.

A CSP de produção:

1. Restringe scripts à própria origem, sem `unsafe-inline` ou `unsafe-eval` na diretiva de scripts.
2. Bloqueia plugins/objetos com `object-src 'none'` e enquadramento com `frame-ancestors 'none'`, em conjunto com `X-Frame-Options: DENY`.
3. Restringe base de URLs e envio de formulários à própria origem.
4. Autoriza as conexões de autenticação do Firebase e os domínios do Realtime Database e do helper de autenticação do projeto atualmente configurado.
5. Mantém estilos inline permitidos para o MUI/Emotion e os estilos existentes. Isso é uma concessão deliberada para compatibilidade e não permite scripts inline na política de produção.
6. Permite imagens HTTPS e imagens/fontes embutidas conforme a política explícita.

Ao trocar o projeto Firebase, ajuste as origens correspondentes em `firebaseConfig.ts`, na CSP do Vite e na CSP do Nginx. O verificador compara as duas políticas de produção para detectar divergências.

### 3.3 — Separar desenvolvimento e produção

O modo de desenvolvimento permite o preâmbulo inline do Vite/React Refresh, os WebSockets de atualização e as conexões locais dos emuladores. Essas permissões não entram no preview ou na configuração Nginx de produção.

O Vite usa `127.0.0.1:5173` com porta estrita, coerente com as origens locais documentadas. O preview também fica em loopback e serve para verificar o build; não substitui o servidor de implantação.

### 3.4 — Configurar HSTS na terminação HTTPS

A API não confia em um `X-Forwarded-Proto: https` fornecido arbitrariamente pelo cliente para decidir emitir HSTS. Em HTTP local, o header está ausente. Os testes validam o ramo HTTPS usando o cliente de testes Flask; isso não instala um certificado nem publica HTTPS.

Quando um gateway termina TLS e encaminha HTTP para a API ou para o contêiner Nginx, configure HSTS **no gateway HTTPS**. Exemplo da diretiva dentro do servidor TLS apropriado:

```nginx
add_header Strict-Transport-Security "max-age=31536000" always;
```

Não foram adicionados `includeSubDomains` nem `preload`. O contêiner atual escuta HTTP na porta 3000 e não é responsável pela terminação TLS externa; não foi alegado que HSTS esteja ativo em uma implantação real.

### 3.5 — Verificar os headers

Com a API local em execução:

```powershell
curl.exe -i "http://127.0.0.1:5000/users/info"
```

A ausência de token retorna `401`, mantendo CSP, `X-Frame-Options: DENY`, `nosniff` e os demais headers. HSTS deve estar ausente nesse HTTP local.

Para verificar o frontend, execute em `frontend`:

```powershell
npm run build
npm run test:headers
```

[check-security-headers.mjs](../frontend/scripts/check-security-headers.mjs) inicia servidores temporários de loopback, verifica os headers do HTML de desenvolvimento, do HTML compilado e do JavaScript de entrada, compara a CSP de produção com o Nginx e encerra os servidores. O script tem timeout e gera uma evidência sanitizada.

O teste confirma as respostas HTTP e a política configurada. Não executa ataques em navegador nem comprova que todos os fluxos de tela foram exercitados sob a CSP. A imagem Nginx não foi construída porque o Docker Engine não estava disponível.

### 3.6 — Alcance de segurança

CSP reduz fontes de scripts e recursos permitidos; headers de enquadramento expressam uma política contra clickjacking. Eles **não substituem** validação, escape de saída, autenticação ou correção de um XSS real. Não foi alegado que o simples envio desses headers elimine toda a classe de vulnerabilidades.

## Parte 4 — Executar os testes e conferir evidências

Na raiz:

```powershell
.\backend\.venv\Scripts\python.exe -m unittest discover -s backend/tests -p test_rate_limiting.py -v
.\backend\.venv\Scripts\python.exe -m unittest discover -s backend/tests -p test_security_headers.py -v
.\backend\.venv\Scripts\python.exe -m pip check
.\backend\.venv\Scripts\python.exe -m pip_audit
```

Para executar toda a suíte, mantenha `npm run emulators` em outro terminal e execute na raiz:

```powershell
$env:RUN_FIREBASE_EMULATOR_TESTS = "1"
.\backend\.venv\Scripts\python.exe -m unittest discover -s backend/tests -v
Remove-Item Env:RUN_FIREBASE_EMULATOR_TESTS
cd frontend
npm run lint
npm run build
npm test
npm run test:headers
```

| Verificação nesta etapa | Resultado | Evidência |
| --- | --- | --- |
| Backend completo, com Authentication/RTDB locais | **38 testes passaram**, sem falhas, erros ou skips; inclui 8 novos testes de rate limiting e 3 de headers | [security-improvements-tests.json](evidence/security-improvements-tests.json) |
| Cliente | **5 testes passaram** | [frontend-tests-security-improvements.txt](evidence/frontend-tests-security-improvements.txt) |
| Headers do frontend por HTTP | Aprovados no HTML de desenvolvimento, HTML compilado e JavaScript; CSP de produção igual à configuração Nginx | [security-headers-frontend.json](evidence/security-headers-frontend.json) |
| ESLint | Aprovado | [frontend-lint-security-improvements.txt](evidence/frontend-lint-security-improvements.txt) |
| TypeScript/Vite | Build aprovado; permanece o aviso de bundle maior que 500 kB | [frontend-build-security-improvements.txt](evidence/frontend-build-security-improvements.txt) |
| Dependências Python, incluindo Flask-Limiter/Redis | **Zero avisos conhecidos**; `pip check` sem incompatibilidades | [pip-audit-security-improvements.json](evidence/pip-audit-security-improvements.json) |

Os testes de Redis verificam a seleção da configuração e o comportamento de recusa em falhas simuladas. Não foi usado um Redis real em produção nem comprovado compartilhamento entre instâncias contra um servidor Redis ativo. A configuração compartilhada está implementada, mas essa validação operacional permanece para a implantação.

Os relatórios anteriores de 27 testes do backend continuam preservados como histórico da primeira entrega. A etapa atual tem 38 testes no backend e 5 no cliente, além da verificação HTTP dos headers.

## Parte 5 — Commits e checklist

Os arquivos de implementação e os testes são separados por melhoria, com as mensagens:

- `feat(security): limitar requisicoes por IP e consultas por usuario`.
- `feat(security): aplicar CSP e protecao contra enquadramento`.
- `docs(security): detalhar melhorias preventivas e atualizar checklist`.

Os identificadores e os arquivos de cada parte estão na [checklist atualizada](commit-checklist.md). As alterações locais anteriores de classificação, o agregador de requisitos e o rascunho de findings continuam separados.

## Referências

- [Flask-Limiter: instalação e uso](https://flask-limiter.readthedocs.io/en/stable/) e [configuração de armazenamento e limites](https://flask-limiter.readthedocs.io/en/stable/configuration.html).
- [Flask: considerações de segurança e headers](https://flask.palletsprojects.com/en/stable/web-security/).
