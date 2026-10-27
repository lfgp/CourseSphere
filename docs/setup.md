# Instalação

Execute os comandos no PowerShell, a partir da raiz do repositório.

As correções de segurança, suas reproduções e os testes estão em [vulnerabilities.md](vulnerabilities.md).

O passo a passo das melhorias adicionais de **rate limiting** e **headers HTTP** está em [security-improvements.md](security-improvements.md).

Logs JSON, `/health`, `/metrics`, SLIs/SLOs e a proposta de dashboard estão em [observability.md](observability.md), com configuração de coleta e passos de validação.

## Execução local sem conta Firebase

Este modo usa os emuladores oficiais de Authentication e Realtime Database com o projeto fictício `demo-coursesphere`. Não precisa de login no Firebase, `credentials.json` ou chave da OpenAI.

### 1. Iniciar os emuladores

No primeiro terminal, na raiz do repositório:

```powershell
npm ci
npm run emulators
```

O script é para Windows x64 e baixa um Java 21 portátil em `.tools/`, validando o checksum publicado pela Adoptium. Na primeira execução também baixa os emuladores; essas instalações precisam de internet. Não altera a instalação de Java do Windows.

Aguarde a mensagem de que os emuladores estão prontos. O painel fica em http://127.0.0.1:4000, o Authentication em `127.0.0.1:9099` e o banco em `127.0.0.1:9000`.

Os usuários e dados de teste são exportados para `.firebase-data/` quando os emuladores encerram normalmente com `Ctrl+C` e são importados na próxima execução. Esse diretório é ignorado pelo Git.

### 2. Iniciar o backend local

No segundo terminal, na raiz do repositório:

```powershell
cd backend
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade "pip==26.2.2"
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe endpoints.py
```

Se o ambiente e as dependências já estão instalados, basta executar o último comando. A API fica em http://127.0.0.1:5000.

A execução direta de `endpoints.py` usa o modo local por padrão: conecta os dois serviços aos emuladores em `127.0.0.1` e dispensa o JSON da conta de serviço. Com o ambiente virtual ativo, você também pode usar `py endpoints.py`. O parâmetro `--local` continua disponível; para usar um projeto real, passe `--firebase`.

Os eventos da API são emitidos em JSON no terminal. `GET /health` verifica se o processo responde; `GET /metrics` expõe métricas Prometheus. Sem token de métricas, a leitura fica restrita ao loopback no modo local. Veja o [guia de observabilidade](observability.md) antes de encaminhar essas rotas por um proxy.

### 3. Iniciar o frontend local

No terceiro terminal, na raiz do repositório:

```powershell
cd frontend
npm ci
npm run dev:local
```

Abra http://localhost:5173, cadastre um usuário pela página de cadastro e faça login com ele. As contas e os perfis ficam nos emuladores locais. O script `dev:local` carrega `.env.emulator` e configura o SDK do navegador para o mesmo projeto `demo-coursesphere`.

O endpoint de consultas ainda retorna a resposta de demonstração de `query_manager.py` (`Fake implementation`); este modo não implementa recomendações por IA nem os endpoints de histórico que ainda estão incompletos no projeto.

### Verificação

No diretório `backend`, execute os testes de configuração:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Com os emuladores em execução, inclua os testes de cadastro, login, perfil e mensagens:

```powershell
$env:RUN_FIREBASE_EMULATOR_TESTS = "1"
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Referências: [Authentication local](https://firebase.google.com/docs/emulator-suite/connect_auth) e [Realtime Database local](https://firebase.google.com/docs/emulator-suite/connect_rtdb).

## Execução com um projeto Firebase real

### Frontend

```powershell
cd frontend
npm ci
npm run dev
```

Abra o endereço exibido no terminal, normalmente http://localhost:5173.

### Backend

Em outro terminal, na raiz do repositório:

```powershell
cd backend
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade "pip==26.2.2"
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

#### Credenciais do Firebase

O backend exige o JSON de uma conta de serviço do Firebase Admin SDK.

1. Abra o [Firebase Console](https://console.firebase.google.com/) e selecione o projeto usado pelo frontend. A configuração atual em `frontend/src/firebaseConfig.ts` aponta para `coursesphere-8bd9a`.
2. Acesse **Configurações do projeto > Contas de serviço > Gerar nova chave privada** e baixe o JSON.
3. Salve o arquivo baixado como `backend/credentials.json`.

O arquivo `backend/credentials.example.json` mostra apenas a estrutura esperada. Para autenticar, use o JSON real baixado do Firebase. O arquivo de credenciais está no `.gitignore`.

Se você não tem acesso ao projeto atual, solicite acesso ao responsável ou configure seu próprio projeto. Nesse caso, atualize também `frontend/src/firebaseConfig.ts` e a URL do Realtime Database usada pelo backend:

```powershell
$env:FIREBASE_DATABASE_URL = "https://URL-DO-SEU-REALTIME-DATABASE"
```

Como alternativa a `backend/credentials.json`, mantenha o JSON em outro local e informe o caminho absoluto na mesma sessão do terminal:

```powershell
$env:GOOGLE_APPLICATION_CREDENTIALS = "C:\caminho\conta-de-servico.json"
```

Referência: [configuração do Firebase Admin SDK](https://firebase.google.com/docs/admin/setup#initialize_the_sdk_in_non-google_environments).

No Firebase Authentication, habilite o provedor **E-mail/senha**. O cadastro usa `createUserWithEmailAndPassword` diretamente no SDK do navegador. A rota administrativa pública `POST /users/create` foi removida. Configure a política de senhas e a proteção contra enumeração de e-mails no provedor.

#### Iniciar a API

Ainda no diretório `backend`, depois de configurar as credenciais:

No modo Firebase real, configure também uma instância Redis compartilhada já disponível para as cotas de requisição. O exemplo abaixo usa Redis no mesmo host; um servidor remoto exige `rediss://` com TLS. Todos os processos da API devem usar o mesmo armazenamento. O modo local com emuladores continua usando memória e dispensa Redis.

```powershell
$env:COURSESPHERE_RATE_LIMIT_STORAGE_URI = "redis://127.0.0.1:6379/0"
$env:COURSESPHERE_METRICS_TOKEN = .\.venv\Scripts\python.exe -c "import secrets; print(secrets.token_urlsafe(32))"
.\.venv\Scripts\python.exe endpoints.py --firebase
```

Sem essa configuração válida, a API real recusa a inicialização. Uma falha do Redis durante as requisições retorna `503`, sem liberar chamadas silenciosamente. Veja o [guia de rate limiting](security-improvements.md) para reproduzir o `429` e verificar a configuração.

No modo real, `COURSESPHERE_METRICS_TOKEN` também é obrigatório. O comando gera um segredo aleatório para a sessão do terminal; na implantação, injete um segredo persistido no gerenciador de segredos e configure o coletor com a mesma credencial, conforme [observability.md](observability.md). Não envie esse segredo ao frontend. Bloqueie `/api/metrics` no gateway público e disponibilize `/metrics` somente ao monitoramento privado. A instrumentação suporta um processo por endereço de scrape; múltiplos workers no mesmo endereço exigem outra configuração de coleta.

A API fica em http://127.0.0.1:5000. O caminho padrão das credenciais é relativo ao arquivo `firebase.py`, independentemente do diretório de execução.

O servidor inicia com `debug=False` e fica restrito a `127.0.0.1`. Para hospedar, use um servidor WSGI apropriado e um gateway HTTPS. O frontend chama URLs relativas `/api/...`; o gateway deve encaminhar `/api/` ao backend, removendo o prefixo e preservando o cabeçalho `Authorization`. O Vite já faz esse encaminhamento no desenvolvimento. O contêiner do frontend retorna `503` em `/api/` se o gateway não estiver configurado.

A API e o frontend agora enviam CSP e headers contra enquadramento. Em desenvolvimento, o Vite mantém as permissões necessárias ao React Refresh e aos emuladores; a CSP de produção não permite scripts inline. Se o gateway terminar TLS e encaminhar HTTP internamente, configure HSTS no próprio gateway. O HSTS da API depende de ela reconhecer HTTPS e não confia em um `X-Forwarded-Proto` arbitrário.

Para conferir os headers do frontend após a instalação, execute em `frontend`:

```powershell
npm run build
npm run test:headers
```

Todas as rotas privadas exigem `Authorization: Bearer <Firebase ID token>`. Tokens na URL ou no corpo não autenticam. O SDK verifica revogação e usuários desativados. Ao carregar a API em um servidor WSGI, mantenha `COURSESPHERE_LOCAL=0`; variáveis de emulador nesse modo impedem a inicialização.

Se o navegador acessar a API a partir de outra origem, informe somente as origens HTTPS autorizadas:

```powershell
$env:COURSESPHERE_ALLOWED_ORIGINS = "https://app.exemplo.com"
```

O padrão fora do modo local é não liberar CORS entre origens. CORS não substitui autenticação. Não use os servidores de desenvolvimento do Flask ou do Vite como servidores públicos.

### Atualização e auditoria de dependências

O ambiente virtual utilizado nesta revisão tinha uma versão vulnerável do `pip`. Atualize a ferramenta e confira as dependências:

```powershell
.\.venv\Scripts\python.exe -m pip install --upgrade "pip==26.2.2"
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pip install "pip-audit==2.10.1"
.\.venv\Scripts\python.exe -m pip_audit
.\.venv\Scripts\python.exe -m pip check
```

Execute `npm audit` na raiz e em `frontend`. Use `npm ci` com os lockfiles versionados. O lockfile alternativo do Bun foi retirado para evitar instalar novamente a árvore antiga.

### Credenciais da coleta do Reddit

Copie `backend/cornell-course-sphere-data/reddit-data/reddit_key.example.json` para `reddit_key.json` no mesmo diretório e preencha apenas a cópia local, ignorada pelo Git. A credencial que já estava no histórico precisa ser revogada no provedor antes de gerar uma substituta; apagar o arquivo não invalida uma chave exposta.

### Script de classificação com OpenAI

O arquivo `backend/main.py` também contém um script de classificação. Para executá-lo diretamente, crie `backend/config.json` com sua chave:

```json
{
  "openai_api_key": "SUA_CHAVE_OPENAI"
}
```

Esse arquivo está no `.gitignore`. Ele é carregado apenas quando a função de classificação é chamada; iniciar `endpoints.py` não executa essa chamada. O endpoint de consultas em `query_manager.py` ainda retorna uma resposta de demonstração (`Fake implementation`).
