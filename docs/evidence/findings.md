# Relatório de segurança e confiabilidade — CourseSphere

**Consolidação:** 27/10/2026, America/Fortaleza. **Formato:** Markdown. **Escopo:** implementação e evidências presentes no repositório. A linha de base histórica corresponde ao estado examinado antes das correções de segurança, incluindo as alterações locais existentes na coleta.

Este relatório reúne as evidências de revisão, testes locais e execução em Docker. A atualização de SCA da seção 4.1 documenta uma nova execução de auditoria npm em 27/10/2026; os testes dinâmicos da aplicação não foram repetidos. Os resultados descrevem as execuções identificadas, não uma verificação de produção ou uma garantia de que serviços continuam disponíveis neste momento.

## 1. Síntese para gestão

Foram confirmados **cinco achados principais**, de causas distintas: token de sessão na URL, mensagens internas de erro expostas, CORS permissivo, dependências com avisos conhecidos e uma credencial do Reddit versionada. São **dois achados de severidade Alta e três de severidade Média**. A exposição de credencial, a configuração e o inventário de componentes foram comprovados; não foi demonstrado furto de contas ou exploração em produção.

As causas de **quatro desses cinco achados foram corrigidas no escopo testado**. A credencial do Reddit foi removida da árvore atual, mas sua revogação não foi comprovada. Essa é a ação de segurança mais urgente: excluir um arquivo não invalida cópias existentes no histórico ou em clones.

Na confiabilidade, o ambiente demonstrou duas APIs atendendo requisições pelo mesmo Nginx, com dados e cotas compartilhados. Porém, host, gateway e Redis continuam concentrados em pontos únicos de falha. **Distribuição de requisições foi comprovada; recuperação após falhas e alta disponibilidade não foram comprovadas.**

| Informação para decisão | Resultado e implicação |
| --- | --- |
| Correções principais comprovadas | V02, V04, V05 e V08, limitadas aos caminhos e inventários analisados |
| Pendência imediata | V09: revogar a credencial exposta, verificar uso e substituir sua distribuição |
| Regressão funcional e de segurança | Última suíte registrada: **57 testes do backend aprovados, sem falhas, erros ou skips** |
| Contêineres | Seis serviços saudáveis na captura; oito chamadas à sonda, quatro por instância, correlacionadas nos logs |
| Estado compartilhado | Ambas as APIs leram o mesmo perfil; 22 consultas do mesmo usuário resultaram em 20 respostas `200` e duas `429` |
| Condição de uso | Demonstração local com Firebase emulado e HTTP em loopback; implantação real exige ações adicionais |
| Metas propostas | Pelo menos 95% das respostas bem-sucedidas de perfil/chat em até 500 ms; no máximo 0,5% de respostas `5xx` entre as respostas elegíveis, em 30 dias |

**Decisão recomendada:** encerrar a exposição da credencial e cumprir os critérios de implantação da seção 7 antes de promover essa topologia a um serviço público. Os riscos de negócio incluem exposição de perfis/conversas, uso indevido de integrações, interrupção de acesso e custo de recuperação. Não foram calculadas perdas financeiras nem observados incidentes reais.

## 2. Escopo, metodologia e limites

### 2.1 Componentes e fluxos examinados

| Componente | Cobertura |
| --- | --- |
| API Flask e Firebase Admin | Autenticação Bearer, revogação, propriedade dos dados, perfis, consultas, mensagens, erros e validação |
| Frontend React/Firebase | Transporte do token, cadastro/login pelo SDK cliente, integração com `/api/` e headers do documento |
| SQLite e coleta de dados | Construção de consultas e identificadores SQL em código e migrações; testes com banco temporário |
| Dependências e segredos | Manifestos/lockfiles npm, ambiente Python instalado, arquivo de credencial e revisão sanitizada do histórico |
| Observabilidade | Logs JSON, correlação, `/health`, proteção de `/metrics`, contadores e histogramas |
| Infraestrutura local | Dockerfiles, Compose, Nginx, duas APIs Waitress, Redis por socket Unix e emuladores Auth/RTDB |

Rotas ativas consideradas: `GET/POST /users/info`, `POST /users/query`, `POST /hash`, `POST /chats/<chat_id>/messages` e `DELETE /chats/<chat_id>`. O cadastro/login por senha ocorre diretamente no Firebase do navegador. O blueprint de cursos permanece desativado na API principal, e a consulta ainda responde com uma implementação de demonstração, sem executar IA paga.

Os cenários envolveram visitante sem token, usuário autenticado, um segundo usuário e credenciais inválidas/revogadas ou usuário desativado. A identidade administrativa do Firebase foi tratada como fronteira privilegiada: a API precisa validar o proprietário mesmo quando o Admin SDK não depende das regras de acesso do cliente.

### 2.2 Método utilizado

1. **Inspeção de código e configuração:** seguir a entrada desde o frontend até autenticação, validação e persistência; revisar CORS, depuração, segredos, Docker e proxy.
2. **Auditoria de componentes:** comparar os relatórios npm da raiz/frontend e `pip-audit` do ambiente instalado, preservando os resultados anteriores e posteriores.
3. **Reprodução controlada:** usar Flask test client com Firebase simulado para falhas determinísticas; SQLite temporário para injeção; contas fictícias nos emuladores para autenticação e isolamento entre usuários.
4. **Validação das correções:** testar transporte de token, erros genéricos, origens exatas, esquemas de entrada, revogação e ausência de dados sensíveis nos logs.
5. **Verificação operacional local:** construir/iniciar o Compose, validar Nginx e executar HTTP real através do gateway; conferir identidade de instância, perfil compartilhado, cota Redis e correlação de logs.
6. **Classificação e consolidação:** distinguir mecanismo confirmado, cenário condicional, código desativado e risco inferido da arquitetura. Não contar avisos transitivos duplicados como vulnerabilidades independentes.

A taxonomia adotada é a [OWASP Top 10:2025](https://top10.owasp.org/2025/). A severidade é qualitativa: **Alta** indica potencial de comprometimento relevante ou interrupção importante nas condições descritas; **Média** indica exposição/configuração com impacto mais limitado ou dependente de outras condições. Não foram calculados vetores CVSS. A severidade de um aviso de pacote não se transfere automaticamente para toda a aplicação.

### 2.3 Limites da conclusão

Não houve ataque ao Firebase/Reddit real, teste de validade da credencial exposta, teste de carga, falha deliberada de host/réplica/Redis, restauração de backup, scan dos pacotes de sistema das imagens ou execução de ataques em navegador. As dependências exclusivas de scripts auxiliares fora do ambiente Python auditado não estão automaticamente cobertas. Não foi comprovado XSS explorável nem acesso de um usuário aos cursos de outro criador.

Os comandos de reprodução deste relatório se referem à **raiz do repositório e a ambientes locais isolados**. Cargas do estado anterior não devem ser executadas em produção. Para acesso manual à composição atual, o gateway usa `http://127.0.0.1:8080/api/`; os testes Flask registram os caminhos internos sem `/api/`. Tokens mencionados como placeholders não são credenciais reais.

## 3. Vulnerabilidades principais, evidências e correções

Os IDs abaixo preservam o inventário de [vulnerabilities.md](../vulnerabilities.md). Os cinco achados abrangem exposição de dados/gestão de sessão, configuração incorreta e dependências vulneráveis.

| ID | Achado | OWASP 2025 | Severidade | Estado no escopo examinado |
| --- | --- | --- | --- | --- |
| V02 | Token de sessão na URL | A07 / A02 | Média | Causa corrigida no cliente e na API |
| V04 | Exposição de erros internos | A02 / A10 | Média | Serialização pública da exceção removida; depurador desabilitado no caminho analisado |
| V05 | CORS permitindo origem arbitrária | A02 | Média | Política permissiva substituída por origens exatas |
| V08 | Componentes com avisos conhecidos | A03 | Alta | Versões afetadas removidas/atualizadas no inventário auditado |
| V09 | Segredo do Reddit no Git | A02 | Alta | Arquivo atual retirado; encerramento da exposição depende de revogação externa |

### V02 — Token de sessão na URL

**Descrição e causa raiz:** o frontend construía `GET /users/info?id_token=...`, e a API aceitava a query string como canal de autenticação. URLs podem chegar a registros de servidores, proxies e ferramentas de diagnóstico. A existência desse transporte foi confirmada; não há prova de vazamento histórico de uma sessão específica.

**Reprodução controlada:** no ambiente anterior isolado, obter um token fictício do emulador e solicitar `/users/info?id_token=ID_TOKEN_LOCAL`, sem header Bearer. O status registrado foi `200`. No caminho corrigido, a mesma forma de autenticar retorna `401`; o perfil com Bearer válido continua retornando `200`.

**Evidência persistida**, nos campos dos arquivos [security-before.json](security-before.json) e [security-after.json](security-after.json):

```json
{"antes":{"url_token_profile_status":200},"depois":{"url_token_profile_status":401,"authenticated_profile_status":200,"profile_cache_control":"no-store"}}
```

O trecho reúne campos reais de duas capturas; não é uma resposta HTTP completa. O teste `test_credentials_in_url_or_body_cannot_authenticate` confirma a recusa do canal antigo.

**Impacto no negócio e na disponibilidade:** um token obtido indevidamente poderia permitir leitura/alteração de dados nas rotas da conta enquanto aceito. A resposta operacional poderia exigir revogação de sessões e suporte aos usuários, interrompendo temporariamente seu acesso.

**Correção e motivo:** [api.ts](../../frontend/src/api.ts) passa a enviar somente `Authorization: Bearer`; [endpoints.py](../../backend/endpoints.py) não autentica por URL/corpo e recusa parâmetros no perfil. Isso elimina o canal inseguro na aplicação. `no-store` e `no-referrer` são controles complementares, não a causa da correção. Revisar registros antigos e garantir TLS na implantação continuam sendo recomendações.

### V04 — Mensagens de exceção expostas ao cliente

**Descrição e causa raiz:** handlers retornavam `str(e)` na resposta pública; uma falha controlada expôs o marcador interno `INTERNAL_SENTINEL`. A execução direta também habilitava depuração. Não foi demonstrado depurador acessível pela internet nem execução remota de código.

**Reprodução controlada:** na versão anterior, enviar `POST /hash` sem `Authorization` provocava falha de parsing e resposta `500` com detalhe da implementação. A reprodução com verificador simulado confirmou divulgação da mensagem. Hoje a ausência de credenciais produz `401`, e falhas internas têm respostas genéricas correlacionadas por `request_id`.

**Evidência:** `internal_exception_disclosed` mudou de `true` para `false` entre [security-before.json](security-before.json) e [security-after.json](security-after.json). O teste `test_error_responses_and_logs_do_not_contain_secrets`, registrado em [container-tests.json](container-tests.json), exige ausência do marcador privado na resposta e nos logs da aplicação.

**Impacto no negócio e na disponibilidade:** detalhes internos facilitam reconhecimento e podem divulgar informação operacional, aumentando custo de resposta a incidentes. Erros de entrada tratados como `500` também confundem a medição de falhas e o suporte, sem que isso, isoladamente, comprove uma indisponibilidade generalizada.

**Correção e motivo:** tratamento centralizado em [endpoints.py](../../backend/endpoints.py), mensagens estáveis, depurador desabilitado e logs JSON com campos permitidos. O runtime dos contêineres usa Waitress. A mensagem da exceção deixa de integrar o caminho público; não se trata de filtrar palavras de algumas mensagens. A redação dos logs de outros componentes precisa continuar sendo verificada na implantação.

### V05 — CORS permitindo origem não autorizada

**Descrição e causa raiz:** `CORS(app)` não expressava quais origens tinham permissão e autorizava a origem arbitrária usada no teste. Como a aplicação envia Bearer explicitamente, isso não demonstra envio automático de sessão por cookies nem leitura anônima de perfis.

**Reprodução controlada:** enviar preflight `OPTIONS /users/info` com `Origin: https://untrusted.example`, método solicitado `POST` e headers `authorization,content-type`. Antes, a resposta autorizava aquela origem; depois, o header de permissão está ausente. Uma origem local prevista continua aceita no modo local.

**Evidência:** o campo `untrusted_cors_origin` contém `https://untrusted.example` em [security-before.json](security-before.json) e `null` em [security-after.json](security-after.json). Os testes de origens exatas e configuração de produção constam de [container-tests.json](container-tests.json).

**Impacto no negócio e na disponibilidade:** amplia as origens de navegador capazes de consumir a API e ler respostas autorizadas. Com credenciais obtidas por outra via, favorece uso fora do frontend previsto. O impacto em disponibilidade seria indireto, por abuso de consumo; não foi medido nem demonstrado furto de sessão por CORS isoladamente.

**Correção e motivo:** lista explícita, comparação escapada/ancorada, recusa de curingas e ausência de liberação entre origens por padrão fora do modo local. A permissão indevida foi retirada da configuração da aplicação. CORS não substitui autenticação nem impede chamadas de clientes fora do navegador.

### V08 — Componentes com vulnerabilidades conhecidas

**Descrição e causa raiz:** dependências e lockfiles selecionavam versões sinalizadas pelas bases consultadas. O ambiente também continha `pip==26.1.2` com aviso de segurança. A presença do componente afetado foi confirmada; não foi executado cada exploit nem demonstrada a alcançabilidade de todos os avisos em produção.

**Reprodução/verificação:** consultar os relatórios anteriores, incluindo pacote, intervalo afetado e origem do aviso. Em uma cópia isolada da árvore antiga, a auditoria do inventário permite comparar a seleção de versões. Para verificar a árvore atual instalada, usar `npm audit` na raiz e no frontend e `python -m pip_audit` no ambiente correspondente. As bases mudam; uma nova consulta pode produzir resultados diferentes.

| Inventário | Antes | Depois registrado | Evidência |
| --- | --- | --- | --- |
| npm do frontend | 39 entradas de pacotes: 2 críticas, 19 altas, 17 moderadas, 1 baixa | Zero avisos conhecidos | [antes](npm-frontend-before.json) / [depois](npm-frontend-after.json) |
| npm da raiz/Firebase CLI | 5 entradas moderadas | Zero avisos conhecidos | [antes](npm-root-before.json) / [depois](npm-root-after.json) |
| Ambiente Python inicial | `pip` sinalizado; entradas duplicadas do mesmo aviso não são falhas independentes | Sem avisos no relatório posterior | [antes](pip-audit-before.json) / [depois](pip-audit-after.json) |
| Ambiente Python após os contêineres | 87 pacotes examinados | Zero avisos conhecidos naquela execução | [pip-audit-containers.json](pip-audit-containers.json) |

**Impacto no negócio e na disponibilidade:** conforme o pacote e seu uso, falhas conhecidas podem expor arquivos ou provocar interrupção, consumo de memória/CPU e retrabalho. Ferramentas de desenvolvimento/instalação têm uma superfície diferente do bundle do navegador; os números acima não são 44 explorações distintas.

**Correção e motivo:** atualização/remoção dos componentes afetados, lockfiles npm atualizados, ajustes compatíveis no frontend e atualização do pip. As versões vulneráveis deixam de compor o inventário analisado, em vez de suprimir alertas. A manutenção permanece recorrente: zero avisos não prova ausência de falhas desconhecidas. Dependências transitivas Python e imagens por tag ainda exigem controle de artefatos e auditorias próprias.

### V09 — Credencial do Reddit versionada

**Descrição e causa raiz:** `backend/cornell-course-sphere-data/reddit-data/reddit_key.json` foi versionado com `client_id` e `client_secret` preenchidos, sem indicação de placeholders. O mecanismo de distribuição de segredos permitia incluir uma credencial no Git.

**Reprodução segura:** consultar os indicadores em [secret-review.json](secret-review.json) e verificar a presença histórica do arquivo no material analisado, sem imprimir seu conteúdo. O campo `redditCredentialTrackedInReviewedHistory: true` descreve o histórico inspecionado na coleta; não afirma que o arquivo permanece na árvore atual.

**Evidência:** o relatório sanitizado marca os dois campos como preenchidos e não placeholders e registra ausência do arquivo na árvore de trabalho após a retirada. Nenhum valor do segredo é publicado. Não houve chamada ao Reddit para testar se ele ainda é aceito.

**Impacto no negócio e na disponibilidade:** se válido, o segredo pode permitir uso indevido da integração e consumo de quotas, prejudicando a coleta e exigindo rotação/investigação. Não foi demonstrado acesso a contas pessoais de usuários nem abuso real.

**Ações feitas e pendência:** arquivo removido da árvore atual, exclusões no Git e exemplo apenas com placeholders. O responsável pela integração precisa **revogar o valor exposto, emitir substituto, verificar uso e comprovar a distribuição privada**. Limpeza de histórico, se necessária, deve ser coordenada; não substitui revogação.

**Por que permanece aberto:** o segredo antigo pode continuar válido e acessível em cópias do histórico. Retirada do arquivo e `.gitignore` reduzem nova propagação, mas não eliminam a aceitação da credencial pelo provedor. Encerrar o achado exige comprovação de revogação, sem registrar o segredo no relatório.

### 3.1 Outros achados e condições técnicas

Estes itens complementam a revisão e não são usados para inflar a contagem dos cinco achados principais:

| ID | Condição e severidade | Tratamento e limite da conclusão |
| --- | --- | --- |
| V01 | Falhas de autenticação/infraestrutura convertidas em consulta anônima; Média no fluxo de demonstração | Fallback removido; login passa a ser obrigatório. O produto antes admitia visitantes em comentários, e não foi demonstrado acesso privado ou custo real de IA |
| V03 | SQL concatenado; Alta se o módulo fosse exposto | Placeholders e identificadores permitidos corrigem a construção SQL; testes com SQLite temporário. O blueprint de cursos permanece desativado, sem exploração remota demonstrada |
| V06 | Entrada sem esquema e validação tardia de lote; Média | Validação completa antes da escrita corrige o lote inválido; limites de corpo/cota mitigam consumo. Isso não garante atomicidade frente a falhas de rede, discutida em R07 |
| V07 | Cadastro público delegado ao Admin SDK; Alta para o risco arquitetural descrito | Rota administrativa removida; cadastro segue pelo SDK cliente. Cadastro aberto por si só não prova vulnerabilidade; não houve demonstração de bypass dos controles reais do provedor |
| V10 | Variáveis de emulador herdadas em configuração real; Alta sob essa condição | Inicialização real recusa essas variáveis. Cenário de configuração controlada; nenhuma implantação real nessa condição foi observada |

Passos e causas detalhados estão em [vulnerabilities.md](../vulnerabilities.md); testes correspondentes em [test_security.py](../../backend/tests/test_security.py), [test_sql_security.py](../../backend/tests/test_sql_security.py) e [container-tests.json](container-tests.json).

## 4. Evidências de validação e sua rastreabilidade

| Referência | Evidência e o que comprova | O que não comprova |
| --- | --- | --- |
| E01 | [security-before.json](security-before.json): linha de base por Flask test client e Firebase simulado | Estado de um serviço público ou de produção |
| E02 | [security-after.json](security-after.json): recusa de URL token, erro genérico, CORS restrito, validação e remoção da rota administrativa | Ausência de toda falha ou comparação idêntica de todas as rotas antigas |
| E03 | Relatórios npm e Python ligados em V08: seleção de pacotes antes/depois | Exploração de cada aviso ou scan de sistema operacional das imagens |
| E04 | [secret-review.json](secret-review.json): presença histórica da credencial sem publicar valores | Validade atual, revogação ou ausência de uso indevido |
| E05 | [container-tests.json](container-tests.json): 57 testes aprovados, incluindo Firebase emulado, SQL e regressão de segurança | Carga de produção, failover ou disponibilidade mensal |
| E06 | [frontend-tests-security-improvements.txt](frontend-tests-security-improvements.txt): 5 testes do cliente; [security-headers-frontend.json](security-headers-frontend.json): verificação HTTP de headers | Ataques completos em navegador; é uma etapa anterior, separada dos 57 testes |
| E07 | [docker-load-balancing.txt](docker-load-balancing.txt) / [JSON](docker-load-balancing.json): requisições por ambas as APIs, perfil compartilhado e 20 respostas `200` + 2 `429` | Throughput, sobrevivência à queda de uma réplica ou de um host |
| E08 | [docker-runtime.json](docker-runtime.json): seis serviços saudáveis na captura, UIDs 10001/101 e oito IDs correlacionados entre gateway/API | Estado online atual, backup recuperável ou segurança completa dos contêineres |
| E09 | [sca-summary.json](sca-summary.json), [raiz](sca-npm-root.json), [frontend](sca-npm-frontend.json) e [saída](sca-execution.txt): execução da ferramenta SCA configurada no repositório | Análise de código, dependências Python, sistema operacional das imagens ou execução do workflow remoto |

Trecho **literal** da demonstração HTTP registrada em E07:

```text
request=1 status=200 instance=backend-1 request_id=9ca4d9f4d3e5102fc0953dc4f064d4cf
request=2 status=200 instance=backend-2 request_id=5e5a713c00d9c2db1459e14553810031
shared_profile=ok shared_redis_quota=20 accepted, 2 rejected across both instances
```

Os dois primeiros registros são linhas consecutivas da amostra; a última linha é um resumo posterior do mesmo arquivo. E08 confirma status `200` no gateway e na API para cada ID. Não há screenshots fabricadas: logs, resultados de requests e arquivos de testes/auditoria constituem as evidências disponíveis. Os relatórios intermediários de 27, 38 e 51 testes são históricos e sobrepostos; não devem ser somados aos 57 como execuções independentes.

Para revisão técnica, a preparação e os comandos estão em [setup.md](../setup.md), [security-improvements.md](../security-improvements.md) e [containers.md](../containers.md). Reexecutar testes atualiza a observação; não recria automaticamente a linha de base antiga.

### 4.1 Ferramenta SCA configurada e execução anexada

Foi configurado **npm audit**, por meio de `npm run security:sca` na raiz. O script [security-sca.mjs](../../scripts/security-sca.mjs) audita os dois lockfiles, inclui todos os tipos de dependência, grava evidências e retorna falha por achados a partir de severidade baixa ou por execução inconclusiva. O [workflow](../../.github/workflows/sca.yml) prepara a mesma análise em GitHub Actions, sem depender da conta de origem.

| Execução local de 27/10/2026 | Dependências contabilizadas pelo npm | Avisos conhecidos | Status |
| --- | --- | --- | --- |
| Raiz/Firebase CLI | 632 | 0 | Aprovado |
| Frontend | 421 | 0 | Aprovado |

A ferramenta usada foi npm **11.17.0**, em Node **v24.19.0**. O comando encerrou com código `0`; os quatro testes da política de falha do scanner também passaram. Erro de rede, relatório inválido ou consulta interrompida não são classificados como auditoria limpa. A contagem não deve ser confundida com pacotes únicos entre os dois projetos.

A execução remota do workflow não foi realizada: apenas a execução local está comprovada pelos anexos E09. Esta SCA não reexecuta os 57 testes históricos do backend nem audita Python ou pacotes de sistema das imagens. A configuração, o passo a passo e os limites completos estão em [sca.md](../sca.md).

## 5. Confiabilidade: SLIs e SLOs propostos

**SLI** é a medida observada do serviço; **SLO** é a meta acordada para essa medida. A proposta usa proporções de eventos e uma janela móvel de 30 dias, de acordo com o modelo de [definição de SLOs do Google SRE](https://sre.google/workbook/implementing-slos/). As metas abaixo ainda dependem de aprovação do responsável do produto e de histórico representativo; não são um SLA contratual nem cumprimento já demonstrado.

### 5.1 Indicadores implementáveis com as métricas existentes

Escopo: leitura/atualização de perfil, gravação de mensagens e exclusão de chat. São as rotas `/users/info`, `/chats/<chat_id>/messages` e `/chats/<chat_id>`. `HEAD` nas leituras segue a semântica do Flask; métodos recusados com `405` ficam fora do denominador.

| Indicador | Cálculo | SLO de 30 dias | Interpretação para gestão |
| --- | --- | --- | --- |
| SLI 1 — respostas rápidas | Respostas `2xx/3xx` com duração ≤ 500 ms / total de respostas `2xx/3xx` no escopo | **≥ 95%** | Perfil e chats devem responder rapidamente na maior parte das operações bem-sucedidas |
| SLI 2 — falhas de servidor | Respostas `5xx` / total de respostas `2xx/3xx/5xx` no escopo | **≤ 0,5%** | No máximo 5 falhas de servidor a cada 1.000 respostas elegíveis; não equivale à disponibilidade total do serviço |

Uma resposta `500` rápida não conta como boa latência. `401`, `403`, `400` e `429`, entre outros `4xx`, não entram nesses denominadores; recusas devem aparecer em painel separado, pois bloqueios indevidos também prejudicam o usuário. `/health`, `/metrics` e `OPTIONS` ficam fora dos SLIs de negócio.

O tempo medido inclui autenticação e chamadas síncronas dentro do Flask, até finalizar a resposta. Não inclui fila anterior ao Flask, trânsito de rede, renderização do navegador ou o login por senha realizado no SDK do Firebase. O SLI 2 observa respostas: uma parada completa sem respostas não será contada pelo próprio backend. É necessário complementar a análise com sonda externa do percurso do usuário e cobertura da coleta.

Para uma amostra **ilustrativa** de 100.000 respostas elegíveis, o orçamento de erro do SLI 2 seria 500 falhas. Esse valor não representa minutos permitidos de parada nem volume observado nos testes. Esgotado esse orçamento, propõe-se priorizar estabilização e suspender mudanças de risco até revisão conjunta de produto/engenharia.

### 5.2 Medição, visualização e tratamento de ausência de dados

- Coletar `/metrics` de **cada processo** (`backend-1:5000` e `backend-2:5000`) com o segredo privado, sem passar pelo balanceador. A label `instance` do coletor identifica o target; UID, IP, token e IDs de chat não são labels de métricas.
- Usar `coursesphere_http_request_duration_seconds_bucket{le="0.5",outcome="success"}` e `_count` para SLI 1; `coursesphere_http_requests_total` filtrado pelos status elegíveis para SLI 2. Somar as contagens das réplicas antes de calcular proporções.
- As consultas PromQL completas e as condições dos denominadores estão em [observability.md](../observability.md). Reinícios podem zerar contadores; usar `increase`/`rate` e confirmar continuidade da coleta.
- No Grafana, apresentar dois painéis Stat de 30 dias, volume elegível, p95 por rota, códigos HTTP, falhas de verificação de token, requisições em andamento e disponibilidade da coleta. Acompanhar `429` separadamente do cumprimento dos SLOs.
- Exibir **Sem dados** quando não houver denominador, scrapes suficientes ou cobertura confiável. Não transformar ausência de tráfego/coleta em 100% de cumprimento. Manter retenção que cubra pelo menos a janela de 30 dias; o guia propõe 35 dias.
- Propor alertas para falha/ausência de scrape e sonda externa; para degradação de latência/erros, usar janela curta, duração sustentada e volume mínimo para evitar conclusões por uma chamada isolada. Correlacionar incidentes pelo `request_id` nos logs JSON centralizados.

Logs, endpoint e métricas estão implementados/testados. Coletor Prometheus, Grafana/Loki, retenção, alertas operacionais, sonda externa e histórico de 30 dias **não foram implantados ou comprovados nas evidências**.

## 6. Principais riscos de disponibilidade e recomendações de resiliência

Os riscos abaixo resultam da inspeção de [compose.yaml](../../compose.yaml), [Nginx](../../deploy/nginx/nginx.conf), [serve.py](../../backend/serve.py), [firebase.py](../../backend/firebase.py) e da instrumentação. São projeções de falha para essa topologia, especialmente se promovida a produção, não incidentes observados. Ter duas APIs no mesmo host reduz dependência de um processo, mas não elimina falhas compartilhadas.

| ID / risco | Evidência arquitetural e impacto potencial | Recomendação e prova de aceitação |
| --- | --- | --- |
| R01 — host, gateway e frontend únicos; Alta em implantação real | As duas APIs e o único gateway estão no mesmo Compose/host. Falha do host ou Nginx interrompe o acesso a todas as réplicas; falha do frontend pode impedir novas sessões de uso | Distribuir réplicas em domínios de falha distintos e usar entrada redundante/gerenciada; em homologação, retirar um processo e um host separadamente e medir erro/tempo de recuperação |
| R02 — Redis único e recusa em falha; Alta | Redis é comum às duas APIs. Falha de armazenamento do limitador resulta em `503`, inclusive antes da autenticação; reinício perde as cotas porque persistência está desativada | Preservar a recusa segura e adotar armazenamento compartilhado com recuperação/HA conforme criticidade. O socket Unix atual é local: múltiplos hosts exigem outro transporte, como `rediss://`, e configuração compatível. Testar indisponibilidade, reconexão e preservação da política de cotas |
| R03 — dependências Firebase e orçamento de espera; Alta | Autenticação e RTDB são síncronos. No Compose, um serviço de emuladores atende ambos. O gateway espera até 30 s de leitura, e o código não define um orçamento de timeout por operação Firebase alinhado ao SLO; esperas podem ocupar as quatro threads por API | Usar serviços reais apropriados na implantação, definir timeouts/retries limitados ao orçamento, evitar tempestade de novas tentativas e considerar circuit breaker que recuse com erro controlado sem liberar acesso. Injetar atraso/falha e verificar recuperação sem saturar as duas APIs |
| R04 — liveness sem readiness; Média | `/health` só verifica se o processo responde; pode retornar `200` enquanto perfil/chat falham. `depends_on` organiza a inicialização e não mede continuamente o percurso de negócio | Separar liveness, readiness de custo limitado e sonda externa; não reiniciar todas as réplicas por uma falha transitória comum do provedor. Validar que tráfego e alertas representem a capacidade real de servir |
| R05 — capacidade e filas não aferidas; Média | Um processo/quatro threads por API, limites de memória e nenhuma prova de carga ou failover. Cotar IP/UID e limitar corpo reduz abuso, mas não prova capacidade no pico ou proteção contra DDoS | Testar carga representativa e perda de uma réplica, observando latência, filas, memória e `429`; calibrar limites e reservar capacidade para operar com uma réplica a menos |
| R06 — observabilidade sem operação central; Média | Não há evidência de coletor, alertas e histórico operacionais. O próprio backend não registra a sua parada completa | Implantar coleta por instância, logs sanitizados, retenção e sonda externa; provocar uma falha controlada e verificar detecção, responsável e procedimento de resposta |
| R07 — recuperação de dados e operações não atômicas; Alta conforme criticidade dos dados | Volume local do Firebase não é backup independente. `save_chat` valida o lote antes de gravar, mas usa múltiplos `push`: uma falha de rede no meio ainda pode deixar lote parcial e uma repetição pode duplicar mensagens | Definir backup/exportação fora do host e testar restauração. Para mensagens, implementar escrita atômica adequada e idempotência por operação/ID, antes de retries automáticos. Injetar falha entre escritas e repetir a mesma operação, exigindo ausência de parcialidade/duplicação |
| R08 — atualização e recuperação de versão; Média | Imagens por tags de série e dependências transitivas podem mudar entre construções. Duas réplicas da mesma versão defeituosa não resolvem uma falha de software comum | Promover artefatos identificados por digest, testar contratos e aplicar rollout gradual/rollback. Restaurar a versão anterior em homologação, preservando compatibilidade dos dados |

Os testes que recusam falha do Redis de forma segura usam falhas simuladas; o smoke test demonstra um Redis real compartilhando cotas no Compose, **sem interrompê-lo**. Nenhuma das provas de falha/recuperação propostas na tabela foi executada nesta consolidação.

`restart: unless-stopped` não torna um processo travado automaticamente recuperável: as políticas de reinício do Docker tratam saída/reinício do contêiner, conforme a [documentação do Docker](https://docs.docker.com/engine/containers/start-containers-automatically/). Um healthcheck insatisfatório, por si só, não equivale à recuperação ou à remoção contínua do tráfego.

Para gestão, recomenda-se acordar **RTO** (tempo máximo de recuperação) e **RPO** (perda máxima aceitável de dados). Como ponto de partida para avaliação de custo, propõem-se RTO ≤ 60 minutos e RPO ≤ 15 minutos para perfil/conversas numa implantação real. São propostas ainda não aprovadas nem demonstradas; a definição final deve considerar valor dos dados, custo e resultados de restauração.

## 7. Plano priorizado de correção e implantação

As prioridades abaixo são propostas de execução, não prazos contratados. **P0** exige ação imediata; **P1** é condição antes de exposição pública/produção; **P2** é evolução após estabelecer os controles básicos. Ações de alta disponibilidade podem ser dimensionadas segundo impacto e orçamento aprovados.

| Prioridade | Ação e risco tratado | Responsável proposto | Critério objetivo de conclusão |
| --- | --- | --- | --- |
| P0 | Revogar/substituir a credencial Reddit e verificar possível uso — V09 | Responsável pela integração e segurança | Confirmação de revogação no provedor, substituto distribuído em privado e revisão dos registros; não publicar valores |
| P1 | Configurar implantação real: modo de emulador desativado, Firebase/regras revisados, HTTPS/HSTS, credenciais montadas e métricas privadas — V02/V09/V10 | Infra e backend | Verificação externa do gateway TLS e teste de separação entre ambientes; nenhum emulador acessível publicamente; credenciais fora de imagens e Git |
| P1 | Definir disponibilidade requerida e remover falhas compartilhadas incompatíveis com ela — R01/R02/R03 | Infra, backend e produto | Decisão explícita sobre host/gateway/Redis, prova de failover adequada à meta aprovada e erros controlados sem contornar autenticação/cotas |
| P1 | Implantar monitoramento, readiness/sonda externa e resposta a incidentes — R04/R06 | Infra/operação | Falha controlada gera alerta acionável; logs correlacionados, retenção e responsável definidos; SLI sem dados não aparece como aprovado |
| P1 | Proteger recuperação e consistência dos dados — R07 | Backend e operação | Metas RTO/RPO aprovadas; backup restaurado e cronometrado; teste de lote/repetição sem mensagens parciais ou duplicadas |
| P1 | Manter as correções e checagens de dependências na entrega — V02/V04/V05/V08 | Desenvolvimento e CI | Regressões de autenticação, validação e CORS executadas; lockfiles respeitados; auditorias atuais e análise dos avisos, incluindo imagens/artefatos pertinentes |
| P2 | Calibrar capacidade, cotas, timeouts e política de erro — R03/R05 | Backend/infra e produto | Teste de carga e perda de réplica com critérios aprovados; orçamento de espera compatível com as metas |
| P2 | Fixar e promover artefatos aprovados, com rollout/rollback — R08 | CI/infra | Digest registrado, implantação gradual e retorno à versão anterior demonstrados em homologação |
| P2 | Medir por 30 dias e revisar metas/erro permitido | Produto e engenharia | Janela completa com volume/cobertura conhecidos e decisão documentada sobre ajuste dos SLOs |

Antes de adicionar retry de escrita, implementar/testar idempotência; antes de aumentar timeouts para esconder falhas, avaliar filas e impacto no usuário. Não habilitar o blueprint de cursos sem validar contrato real, autorização e regressão de injeção. A parametrização SQL já corrige a causa no módulo, mas não substitui autorização de novas rotas.

## 8. Critérios de encerramento e manutenção do relatório

V02, V04, V05 e V08 têm correções sustentadas pelas evidências no escopo descrito. **V09 permanece pendente de comprovação externa.** Contêineres, rate limiting, headers e logs melhoram defesa/operabilidade, mas não substituem a eliminação de causas de injeção, autorização incorreta ou credencial exposta.

Para encerrar ações abertas, anexar evidência sanitizada, responsável, data e resultado ao achado/risco correspondente. Uma eventual nova auditoria ou prova de failover deve ser identificada como nova execução, sem converter recomendações em controles já existentes. Os passos técnicos completos permanecem em [vulnerabilities.md](../vulnerabilities.md), [observability.md](../observability.md) e [containers.md](../containers.md).
