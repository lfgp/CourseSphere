# Observabilidade — implementação e passo a passo

Esta etapa adiciona logs JSON, uma sonda de vida do processo e métricas Prometheus à API Flask. Os SLIs usam as operações de perfil e chat que já estão registradas em `backend/endpoints.py`. Login e cadastro acontecem no SDK do Firebase no navegador; a API observa a **verificação de ID tokens**, sem medir o tempo completo do login por senha. O blueprint de cursos continua desativado.

## 1. O que foi implementado

| Requisito | Implementação | Evidência |
| --- | --- | --- |
| Requests em JSON | Evento `request_completed`, método, modelo da rota, status, duração e ID de correlação gerado pelo servidor | Teste de captura do fluxo JSON e teste de `429` |
| Erros em JSON | Eventos `request_rejected`, `request_failed` e `rate_limit_storage_unavailable`; respostas genéricas preservadas | Testes com mensagens de exceção contendo marcadores privados |
| Autenticação em JSON | Evento `authentication`, com resultado e motivo de conjunto fixo | Sucesso, token rejeitado e falha do provedor distinguida de credencial inválida |
| Saúde | `GET /health`, com `200 {"status":"ok","check":"liveness"}` | Teste HTTP real em loopback e teste com Redis indisponível |
| Performance | `GET /metrics`, formato textual Prometheus, contadores, histogramas e requisições em andamento | Parser oficial, teste HTTP e teste determinístico do bucket de 500 ms |
| SLIs e SLOs | Latência e taxa de respostas `5xx` de perfil/chat; janela móvel de 30 dias | Definições e PromQL na seção 6 |
| Dashboard | Painéis, consultas, alertas e correlação com logs | Procedimento descritivo na seção 7; Grafana não foi instalado nesta etapa |

### Arquivos envolvidos

1. `backend/structured_logging.py`: formatter JSON e campos permitidos; configuração do logger da aplicação e do Werkzeug.
2. `backend/observability.py`: registro Prometheus próprio, medição com relógio monotônico, hooks de requisição e endpoints de observabilidade.
3. `backend/endpoints.py`: integração dos erros e dos eventos de autenticação.
4. `backend/rate_limiting.py`: exceção das sondagens e scrapes às cotas de negócio.
5. `backend/requirements.txt`: cliente oficial `prometheus-client==0.26.0`, com versão fixada.
6. `backend/tests/test_observability.py`: 13 testes específicos. O teste anterior de logging em `test_security.py` passa a verificar o evento estruturado.

O JSON substitui as mensagens de texto livres dos eventos da aplicação. O contador e o histograma são atualizados na finalização da resposta, inclusive em `401`, `429`, `500` e `503`. O gauge em andamento é decrementado no encerramento do contexto, inclusive quando ocorre erro.

## 2. Instalar e executar localmente

Prepare os emuladores e o ambiente virtual conforme [setup.md](setup.md). Na raiz do repositório:

```powershell
.\backend\.venv\Scripts\python.exe -m pip install -r backend/requirements.txt
.\backend\.venv\Scripts\python.exe backend/endpoints.py
```

No segundo terminal, também na raiz:

```powershell
Invoke-RestMethod http://127.0.0.1:5000/health
(Invoke-WebRequest http://127.0.0.1:5000/metrics).Content
```

No modo local, sem segredo de métricas configurado, apenas conexões cujo peer seja `127.0.0.1` ou `::1` podem ler `/metrics`. Um `X-Forwarded-For` enviado pelo cliente não altera essa decisão. O frontend não precisa receber o segredo.

`/health` é público e não consulta Firebase ou Redis. Seu `200` significa que a aplicação está respondendo; ele pode continuar saudável enquanto uma operação de perfil retorna `503`. Ele não é um endpoint de readiness nem uma garantia sobre as dependências. Para detectar indisponibilidade completa, use também uma sonda externa; um processo parado não consegue registrar seu próprio erro.

Sondagens `/health`, `/metrics` e preflights `OPTIONS` ficam fora dos contadores/histogramas HTTP de negócio e das cotas da API. Ainda geram logs de conclusão. Isso evita que o próprio coletor consuma a cota ou melhore artificialmente os SLIs. Erros de acesso ao endpoint de métricas podem aparecer no contador separado de erros tratados.

## 3. Conferir os logs JSON

Faça uma chamada a uma rota privada sem token:

```powershell
curl.exe -i http://127.0.0.1:5000/users/info
```

O resultado esperado é `401`. No terminal da API aparecem os eventos `authentication`, `request_rejected` e `request_completed`, todos com o mesmo `request_id`. A resposta traz esse ID no JSON e no header `X-Request-ID`. Não há confiança em um ID enviado pelo cliente.

Exemplo ilustrativo de uma linha de conclusão:

```json
{"timestamp":"2026-10-24T15:00:00.000+00:00","level":"INFO","service":"coursesphere-api","event":"request_completed","request_id":"00112233445566778899aabbccddeeff","method":"GET","route":"/users/info","status":401,"duration_ms":0.8}
```

| Campo | Significado |
| --- | --- |
| `timestamp` | Data UTC com precisão de milissegundos |
| `level`, `service`, `event` | Severidade, aplicação e evento |
| `request_id` | Correlação gerada no servidor; não é identidade do usuário |
| `method`, `route` | Método de conjunto fixo e modelo da rota; caminhos desconhecidos viram `unmatched` |
| `status`, `duration_ms` | Resultado HTTP e tempo dentro do Flask |
| `outcome`, `reason` | Resultado e motivo da verificação do token |
| `kind` | Categoria fixa de erro tratado |

Eventos de autenticação usam somente estas combinações:

| `outcome` | `reason` | Comportamento |
| --- | --- | --- |
| `success` | `verified` | Token verificado e UID válido; execução da rota continua |
| `rejected` | `missing_or_malformed` | Bearer ausente ou malformado; `401` |
| `rejected` | `invalid_or_inactive` | Token inválido, expirado, revogado, usuário desativado/inexistente ou UID inválido; `401` |
| `error` | `provider_unavailable` | Falha inesperada na verificação; acesso permanece bloqueado e resposta `503` |

O logger usa uma lista explícita de campos. Não grava tokens, senhas, UID, e-mail, IP, corpos, textos de chat, query strings, caminhos com IDs, mensagens de exceção ou traceback. Registros livres que chegarem a esses loggers são substituídos por `runtime_message_suppressed`; não basta embrulhar uma mensagem sensível em JSON. Métodos desconhecidos viram `OTHER`. Isso também limita injeção de conteúdo em logs e cardinalidade nas métricas.

Os eventos da aplicação saem em `stdout`. O logger de acesso do Werkzeug não imprime as URLs das requisições; os eventos de conclusão da aplicação fornecem o registro seguro. Outros loggers de bibliotecas, mensagens anteriores à inicialização e logs do servidor WSGI/gateway exigem configuração própria. Não encaminhe logs brutos de depuração do Firebase CLI para o repositório: ele pode imprimir variáveis de ambiente.

## 4. Proteger a coleta de métricas

Fora de `COURSESPHERE_LOCAL=1`, a inicialização exige `COURSESPHERE_METRICS_TOKEN`: segredo aleatório de 32 a 256 caracteres de `A-Z`, `a-z`, `0-9`, `_` e `-`. Não é um Firebase ID token. A comparação é feita em tempo constante; valor incorreto/ausente retorna `401`. URLs e corpo não autenticam o scrape.

Para reproduzir a coleta protegida em desenvolvimento, gere um segredo **local e ignorado pelo Git**, na raiz do repositório:

```powershell
New-Item -ItemType Directory -Path .tools -Force | Out-Null
$metricsSecret = .\backend\.venv\Scripts\python.exe -c "import secrets; print(secrets.token_urlsafe(32))"
[System.IO.File]::WriteAllText((Join-Path (Get-Location) '.tools/metrics-token.txt'), $metricsSecret)
$env:COURSESPHERE_METRICS_TOKEN = $metricsSecret
.\backend\.venv\Scripts\python.exe backend/endpoints.py
```

Interrompa uma API anterior antes de reiniciá-la com a variável. Em outro terminal, na raiz:

```powershell
$metricsSecret = (Get-Content -Raw .tools/metrics-token.txt).Trim()
$headers = @{ Authorization = "Bearer $metricsSecret" }
(Invoke-WebRequest http://127.0.0.1:5000/metrics -Headers $headers).Content
```

Em produção, injete o segredo pelo gerenciador de segredos do ambiente e disponibilize a mesma credencial somente ao coletor. Restrinja `/metrics` à rede de monitoramento e bloqueie `/api/metrics` no gateway público. O modo local sem token não deve ser exposto por um proxy: nesse caso o backend enxergaria o peer do proxy como loopback. Mantenha a API vinculada ao loopback e configure token antes de qualquer encaminhamento externo. Para coleta entre máquinas, use TLS no gateway privado, valide o certificado e mantenha a autenticação.

### Configuração de exemplo do Prometheus

Exemplo para Prometheus e API no mesmo host Linux, com o segredo montado em `/run/secrets/coursesphere_metrics_token`. Adapte o caminho absoluto para Windows; o arquivo contém somente o token, sem o prefixo `Bearer`.

```yaml
global:
  scrape_interval: 15s
  scrape_timeout: 5s
  evaluation_interval: 15s

scrape_configs:
  - job_name: coursesphere
    metrics_path: /metrics
    scheme: http
    static_configs:
      - targets: ['127.0.0.1:5000']
    authorization:
      type: Bearer
      credentials_file: /run/secrets/coursesphere_metrics_token
```

Salve como uma configuração local do Prometheus, valide com `promtool check config CAMINHO` e inicie `prometheus --config.file=CAMINHO --storage.tsdb.retention.time=35d`. A retenção precisa cobrir a janela de 30 dias. Em contêineres separados, `127.0.0.1` aponta para o próprio contêiner; ajuste o target para a API na rede privada e a terminação TLS. O header de autenticação por arquivo segue a [configuração oficial do Prometheus](https://prometheus.io/docs/prometheus/latest/configuration/configuration/).

Nesta etapa, Prometheus, `promtool` e Grafana não foram instalados ou executados; a configuração acima é uma instrução de implantação. O endpoint foi verificado com o parser oficial e por HTTP local.

## 5. Métricas disponíveis e alcance

| Métrica | Tipo e labels | Uso |
| --- | --- | --- |
| `coursesphere_http_requests_total` | Counter: `route`, `method`, `status` | Volume e códigos HTTP das requisições concluídas |
| `coursesphere_http_request_duration_seconds` | Histogram: `route`, `method`, `outcome` | Duração das respostas, buckets, soma e contagem |
| `coursesphere_http_requests_in_progress` | Gauge sem labels | Requisições de negócio em execução naquele processo |
| `coursesphere_auth_events_total` | Counter: `outcome`, `reason` | Verificações aceitas, rejeitadas e falhas do provedor |
| `coursesphere_auth_verification_duration_seconds` | Histogram: `outcome` | Custo da verificação de ID tokens; não do login completo |
| `coursesphere_errors_total` | Counter: `kind` (`http`, `internal`, `rate_limit_storage`) | Erros tratados; inclui recusas HTTP, não apenas falhas `5xx` |

`outcome` do histograma HTTP é `success` para status abaixo de 400, `client_error` para `4xx` e `server_error` para `5xx`. Nenhuma métrica recebe ID de requisição, usuário, IP, texto, token ou ID concreto de chat como label. IDs permanecem apenas na correlação dos logs.

Os buckets em segundos são `0.005`, `0.01`, `0.025`, `0.05`, `0.1`, `0.25`, **`0.5`**, `1`, `2.5`, `5`, `10` e `+Inf`. O limite de 500 ms existe explicitamente para que a proporção do SLO seja calculada diretamente. Os histogramas expõem `_bucket`, `_sum` e `_count`, conforme o [cliente oficial do Prometheus](https://prometheus.github.io/client_python/instrumenting/histogram/).

A medição começa antes do rate limiter e termina na finalização da resposta pelo Flask. Inclui autenticação e chamadas síncronas da rota; não inclui fila anterior ao Flask, trânsito de rede, renderização do navegador ou transmissão completa de um corpo em streaming. As respostas atuais são JSON sem streaming.

O registro é isolado por processo. Reinícios zeram os contadores; `rate` e `increase` tratam resets observáveis. Não há persistência local de séries nem retenção sem um coletor. Uma série com labels surge quando a combinação é observada; são necessários scrapes e tráfego suficientes para calcular variações.

**Implantação suportada:** um processo por target, podendo usar threads. Se houver réplicas, cada processo deve ter endereço próprio de scrape e label `instance` distinta. Não faça scrape através de um balanceador que alterne workers: isso mistura contadores e compromete os SLIs. `PROMETHEUS_MULTIPROC_DIR` provoca erro explícito nesta configuração; habilitar múltiplos workers exige implementar e validar o [modo multiprocess do cliente](https://prometheus.github.io/client_python/multiprocess/), que não faz parte desta entrega.

## 6. Dois SLIs e seus SLOs propostos

Escopo comum: `GET/POST /users/info`, `POST /chats/<chat_id>/messages` e `DELETE /chats/<chat_id>`. O seletor PromQL de `route` abaixo representa essas rotas. Os métodos não suportados retornam `405` e ficam fora dos denominadores. `HEAD` em rotas GET segue a semântica do Flask e entra como leitura.

| Indicador | Fórmula conceitual | SLO proposto, janela móvel de 30 dias | Razão de negócio |
| --- | --- | --- | --- |
| SLI 1 — proporção de respostas rápidas de perfil/chat | Respostas `2xx/3xx` com duração **≤ 500 ms** / todas as respostas `2xx/3xx` no escopo | **≥ 95%** | Carregar perfil e salvar/excluir chats com interação responsiva |
| SLI 2 — taxa de falha de servidor em perfil/chat | Respostas `5xx` / respostas `2xx/3xx/5xx` no escopo | **≤ 0,5%**; equivale a ≥ 99,5% sem erro de servidor entre respostas elegíveis | Evitar perda de acesso ao perfil e falhas ao persistir conversas |

O primeiro SLI considera somente respostas bem-sucedidas para que uma falha rápida não conte como boa latência. O segundo inclui `500` e `503`, inclusive indisponibilidade de autenticação e Redis antes de a rota executar. `4xx` são excluídos por representarem validação, autenticação negada ou cota; acompanhe-os em painel separado para detectar bloqueios indevidos. Essa exclusão é uma definição de escopo, não uma declaração de boa experiência para quem recebeu `429`.

Nenhum dos dois indicadores mede tempo de login por senha, qualidade da resposta de IA, CRUD de cursos ou disponibilidade durante uma parada total do processo. A consulta ainda retorna uma implementação de demonstração. Completude de coleta e sondas externas devem ser analisadas junto dos SLIs.

### SLI 1 — percentual de respostas bem-sucedidas em até 500 ms

```promql
100 *
sum(increase(coursesphere_http_request_duration_seconds_bucket{
  job="coursesphere", route=~"/users/info|/chats/<chat_id>(/messages)?",
  outcome="success", le="0.5"
}[30d]))
/
sum(increase(coursesphere_http_request_duration_seconds_count{
  job="coursesphere", route=~"/users/info|/chats/<chat_id>(/messages)?",
  outcome="success"
}[30d]))
```

Meta no painel: resultado **≥ 95**, unidade percentual. Essa proporção por bucket é a medida de cumprimento; o p95 serve para diagnóstico e pode ser uma estimativa entre buckets, conforme a [documentação de histogramas e SLOs](https://prometheus.io/docs/practices/histograms/).

### SLI 2 — percentual de respostas elegíveis com erro de servidor

```promql
100 *
(
  sum(increase(coursesphere_http_requests_total{
    job="coursesphere", route=~"/users/info|/chats/<chat_id>(/messages)?",
    status=~"5.."
  }[30d])) or vector(0)
)
/
sum(increase(coursesphere_http_requests_total{
  job="coursesphere", route=~"/users/info|/chats/<chat_id>(/messages)?",
  status=~"2..|3..|5.."
}[30d]))
```

Meta no painel: resultado **≤ 0,5**, unidade percentual. O `or vector(0)` atende à ausência da série de `5xx` quando houve tráfego elegível sem erro; não cria um denominador. Sem tráfego elegível, sem scrapes suficientes ou com denominador zero, mostrar **Sem dados**, sem substituir a divisão por uma aprovação automática. Não usar `clamp_min(..., 1)` para fabricar cumprimento com baixo volume.

As somas agregam todos os targets do job. Se ambientes distintos compartilharem o Prometheus, use jobs separados ou um filtro de ambiente consistente em **todas** as parcelas. Configure retenção e confirme cobertura de coleta por 30 dias antes de afirmar cumprimento mensal. Uma interrupção de coleta, mesmo com resultado numérico, deixa a avaliação incompleta.

As metas são propostas iniciais. Devem ser aprovadas pelo responsável do serviço e ajustadas a partir de carga representativa. Os testes desta etapa comprovam instrumentação e classificação; não demonstram que o serviço cumpriu 30 dias de SLO nem constituem benchmark de produção.

## 7. Como visualizar no Grafana

1. Suba Prometheus na rede privada, carregue a configuração de coleta e confira **Targets**: `coursesphere` deve estar `UP`. `up{job="coursesphere"}` comprova scrape bem-sucedido, não a saúde do Firebase.
2. No Grafana, configure uma fonte de dados do tipo Prometheus apontando para o coletor; valide a conexão. Não aponte a fonte de dados diretamente para `/metrics`. O suporte está descrito na [documentação oficial do Grafana](https://grafana.com/docs/grafana/latest/datasources/prometheus/).
3. Crie o dashboard **CourseSphere — API**, com filtro por `instance`, atualização de 15 segundos, janela inicial de uma hora e painéis de SLO com janela fixa de 30 dias.
4. Adicione os painéis abaixo; use percentuais de 0 a 100, segundos para latência e requests/s para vazão. Faça agregação das contagens antes de dividir, evitando média simples de percentuais por instância.

| Painel | Visualização e consulta | Interpretação |
| --- | --- | --- |
| Estado da coleta | Stat por instância: `up{job="coursesphere"}` | 0 = falha de scrape; pode ser processo, rede ou credencial do coletor |
| Volume | Time series: `sum by (route) (rate(coursesphere_http_requests_total{job="coursesphere"}[5m]))` | Tráfego por operação; também mostra se há volume para avaliar os SLIs |
| Latência p95 por rota | Time series com a expressão abaixo | Aumento de duração; separa perfil de chats |
| Respostas por status | Time series: `sum by (status) (rate(coursesphere_http_requests_total{job="coursesphere"}[5m]))` | Separa recusas `401/429` de falhas `500/503` |
| Verificação de autenticação | Time series: `sum by (outcome, reason) (rate(coursesphere_auth_events_total{job="coursesphere"}[5m]))` | Tokens recusados versus falhas do provedor; não representa tentativas de senha |
| Verificações lentas | Time series: `histogram_quantile(0.95, sum by (le) (rate(coursesphere_auth_verification_duration_seconds_bucket{job="coursesphere",outcome="success"}[5m])))` | Custo da verificação de ID token |
| Requisições em andamento | Time series: `sum(coursesphere_http_requests_in_progress{job="coursesphere"})` | Crescimento persistente sugere operações acumuladas; não mede fila anterior ao Flask |
| Cumprimento dos SLOs | Dois Stat com as expressões de 30 dias da seção 6 | Verde a partir de 95% no SLI 1; verde até 0,5% no SLI 2; sem dados em cinza |

Consulta do p95 por rota:

```promql
histogram_quantile(0.95,
  sum by (route, le) (
    rate(coursesphere_http_request_duration_seconds_bucket{
      job="coursesphere", outcome="success"
    }[5m])
  )
)
```

Para filtrar uma instância, acrescente o mesmo matcher `instance` a todas as consultas/parcela dos SLIs. Não remova `le` na agregação de buckets.

### Alertas e investigação

Proponha alerta de coleta com `up{job="coursesphere"} == 0` sustentado por 2 minutos e outro para ausência completa do job com `absent(up{job="coursesphere"})`. Trate a ausência de dados explicitamente no Grafana. Para degradação, use as proporções dos SLIs com janela curta de 5 minutos, sustentadas por 10 minutos, condicionadas a volume mínimo de 100 respostas elegíveis na janela. Assim, uma chamada isolada não se torna conclusão sobre a meta mensal. Acompanhe a janela de 30 dias separadamente.

Centralize `stdout` com um agente de coleta de logs, por exemplo Grafana Alloy encaminhando para Loki, e adicione Loki como outra fonte do Grafana. Use `service`, `event` e `level` como labels; mantenha `request_id` como campo JSON pesquisável, evitando uma série por requisição. A coleta central e o Loki são uma proposta de implantação; não foram configurados nesta etapa.

No Explore do Loki, após essa coleta, uma investigação pode usar:

```logql
{service="coursesphere-api"} | json | event="request_failed"
```

Ou localizar um ID retornado ao cliente:

```logql
{service="coursesphere-api"} | json | request_id="00112233445566778899aabbccddeeff"
```

O painel de falhas identifica horário e rota; o `request_id` obtido do erro HTTP ou do evento de erro liga os eventos da mesma chamada. Métricas agregadas não fornecem esse ID e não há tracing distribuído ou exemplars nesta implementação. Defina retenção, acesso e alertas para os logs no ambiente de implantação; revise também a redação de dados no gateway e no servidor WSGI.

## 8. Reproduzir a validação

Com as dependências instaladas, na raiz:

```powershell
.\backend\.venv\Scripts\python.exe -m unittest discover -s backend/tests -p test_observability.py -v
```

Esse comando executa os **13 testes específicos** sem depender dos serviços Firebase em execução: as verificações de token/banco são substituídas por mocks, e o teste HTTP inicia um servidor apenas em loopback com porta temporária. O teste de sonda simula falha do Redis, não uma instância Redis real.

Para executar também os fluxos reais nos emuladores, inicie `npm run emulators` em outro terminal e execute:

```powershell
$env:RUN_FIREBASE_EMULATOR_TESTS = '1'
.\backend\.venv\Scripts\python.exe -m unittest discover -s backend/tests -v
.\backend\.venv\Scripts\python.exe -m pip check
.\backend\.venv\Scripts\python.exe -m pip_audit
```

Resultado desta etapa: **51 testes do backend aprovados, sem falhas, erros ou skips**, incluindo os 13 novos, integração de Authentication/RTDB, rate limiting, headers, autenticação e SQL. O frontend não foi alterado nem sua suíte repetida nesta etapa. A auditoria do ambiente Python instalado terminou sem vulnerabilidades conhecidas e `pip check` não encontrou dependências incompatíveis.

Evidências sanitizadas: [observability-tests.json](evidence/observability-tests.json) e [pip-audit-observability.json](evidence/pip-audit-observability.json). Os resultados anteriores de segurança permanecem como histórico, sem sobrescrever as evidências de cada etapa.

## 9. Por que a implementação atende ao problema

A ausência de visibilidade na API foi tratada nos pontos que executam o trabalho: início/final da requisição, verificação de identidade e tratamento central dos erros. Hooks anteriores ao limitador capturam inclusive chamadas recusadas por cota. O registro único das métricas e os eventos com campos definidos tornam esses dados coletáveis sem depender de examinar mensagens livres manualmente.

Essa implementação resolve a falta de instrumentação neste processo da aplicação. Ela **não corrige, por si só, vulnerabilidades de autorização, injeção ou credenciais expostas**: essas causas e correções continuam em [vulnerabilities.md](vulnerabilities.md). Centralização de logs, retenção, sondas externas, implantação dos coletores e comprovação dos SLOs continuam sendo responsabilidades operacionais documentadas, sem alegação de que já estejam concluídas.

Os arquivos e os commits locais desta entrega estão separados por parte em [commit-checklist.md](commit-checklist.md).
