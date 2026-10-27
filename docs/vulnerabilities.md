# Revisão de vulnerabilidades — CourseSphere

Data: **24/10/2026**. Referência: [OWASP Top 10:2025](https://top10.owasp.org/2025/pt-BR/). A edição foi indicada explicitamente porque a numeração mudou em relação a 2021.

## Escopo e método

Foram revisados a API Flask, o acesso privilegiado ao Firebase, o frontend React, os módulos SQLite, os scripts de coleta, células relevantes dos notebooks, os manifestos e lockfiles de dependências e a configuração do contêiner. O projeto já tinha alterações locais, que foram mantidas durante a análise e a aplicação das correções.

A reprodução usou o cliente de testes do Flask, Firebase simulado, bancos SQLite temporários e os emuladores locais oficiais de Authentication e Realtime Database do projeto fictício `demo-coursesphere`. Não foram feitos ataques ao Firebase de produção nem testes de validade das credenciais expostas.

Este documento separa falhas confirmadas, código vulnerável ainda desativado, configurações perigosas condicionais e melhorias preventivas. Uma ocorrência no código não comprova que um serviço publicado esteja explorável. As severidades abaixo são avaliações qualitativas do contexto; não são pontuações CVSS.

## Atendimento aos critérios da atividade

O mínimo de **cinco vulnerabilidades de causas distintas** é atendido pelos achados abaixo. Eles cobrem **três das categorias solicitadas**: exposição de dados sensíveis, configuração incorreta de segurança e dependências vulneráveis. Não é necessário encontrar XSS ou demonstrar alteração de cursos de outro usuário para cumprir o requisito de duas categorias.

| Achado contabilizado | Categoria solicitada | Severidade | Confirmação disponível |
| --- | --- | --- | --- |
| V02 — ID token na URL | Exposição de dados sensíveis / gestão de sessão | Média | Cliente construía a URL com a credencial e a API a aceitava; reprodução anterior retornou `200` |
| V04 — Detalhes de exceções na resposta HTTP | Exposição de dados sensíveis / configuração de segurança | Média | Mensagem interna controlada foi devolvida pela API; código interpolava `str(e)` |
| V05 — CORS permitindo origem arbitrária | Configuração incorreta de segurança | Média | Preflight de origem não autorizada recebia `Access-Control-Allow-Origin` para essa origem |
| V08 — Versões instaladas com avisos de segurança | Uso de dependências vulneráveis | Alta | Relatórios npm identificam versões afetadas e avisos específicos; a atualização removeu os avisos do inventário |
| V09 — Segredo do Reddit versionado | Exposição de dados sensíveis | Alta | Arquivo no Git continha `client_secret` preenchido e sem indicação de placeholder; evidência sanitizada preservada |

Para esses cinco achados, a existência do mecanismo inseguro ou do componente afetado foi confirmada. Isso não equivale a comprovar roubo de contas, exploração em produção ou validade atual da chave do Reddit. Cada seção apresenta descrição, severidade, reprodução, impacto potencial, correção e validação. Os impactos de negócio são cenários potenciais, não incidentes observados.

**Não entram nessa contagem mínima:** o SQL do blueprint desativado (V03), a configuração condicional de emuladores (V10), a decisão de exigir login em consultas que admitiam visitantes (parte de V01) e a simples existência de um cadastro público (V07). Esses casos continuam registrados com suas condições e limites. Não foi encontrada evidência de que um usuário conseguisse editar cursos de outro criador, nem de XSS explorável.

### Convenções para reproduzir

- Os passos marcados como **antes** descrevem o estado capturado anteriormente às correções. Executar os comandos na árvore atual deve produzir o resultado corrigido; não se deve desfazer as correções no ambiente de uso.
- Para comparação dinâmica com o código antigo, use somente uma cópia isolada desse estado e os emuladores, sem credenciais reais. O estado inicial tinha alterações locais e não é necessariamente igual a `HEAD`; por isso, um checkout de `HEAD` não reproduz automaticamente toda a linha de base.
- `ID_TOKEN_LOCAL` significa um ID token de uma conta fictícia criada no emulador. Não é um token real fornecido por este documento. Os testes automatizados criam contas locais ou simulam a verificação do Firebase e não exigem copiar tokens de produção.
- Execute os comandos HTTP apenas contra `127.0.0.1:5000`, conforme [setup.md](setup.md). Nas seções seguintes, **reprodução** demonstra a falha; **passo a passo aplicado** explica sua correção.

## O que significa resolver, em vez de mitigar

**Correção** elimina a causa da falha no componente analisado. Exemplo: parâmetros SQL deixam de integrar a estrutura do comando e passam a ser enviados ao driver como dados. O ataque deixa de funcionar mesmo sem um WAF.

**Mitigação** reduz probabilidade ou impacto mantendo alguma causa ou exposição. Exemplo: limitar o tamanho do corpo reduz uma forma de consumo excessivo de recursos, mas não impede DDoS, abuso por muitas contas ou esgotamento de conexões.

Os testes demonstram a eliminação de caminhos específicos de exploração. Eles não provam ausência de toda vulnerabilidade. Em particular, **a exposição histórica da chave do Reddit continua pendente até sua revogação**; removê-la do código e adicioná-la ao `.gitignore` não a torna inválida.

## Atendimento ao requisito de corrigir pelo menos três vulnerabilidades

As correções de **V02, V04, V05 e V08** atendem ao mínimo solicitado, considerando o escopo de cada achado. Elas não dependem de contar a remoção da chave do Reddit como exposição encerrada, nem de considerar o módulo SQL desativado como uma rota ativa.

| Correção | Causa raiz | Mudança que elimina a causa | Por que não é apenas mitigação | Validação |
| --- | --- | --- | --- | --- |
| V02 — Token na URL | O cliente colocava uma credencial Bearer no endereço e a API aceitava esse canal para autenticar | Usar exclusivamente `Authorization`, remover a credencial da URL e recusar o canal antigo | A aplicação deixa de produzir e aceitar esse transporte de credencial; não depende apenas de esconder URLs nos logs | URL sem Bearer retorna `401`; Bearer válido sem parâmetros mantém o acesso legítimo |
| V04 — Exceções expostas | Os handlers convertiam diretamente `str(e)` em resposta pública e a execução direta habilitava o depurador | Respostas genéricas centralizadas e `debug=False`; detalhes sensíveis não são serializados na resposta | A origem da informação exposta foi retirada do caminho HTTP, em vez de filtrar algumas palavras ou depender de um firewall | Marcador interno ausente da resposta e dos registros da aplicação; inicialização sem depurador verificada |
| V05 — CORS permissivo | A configuração autorizava qualquer origem, sem expressar quais frontends tinham permissão | Lista de origens exatas, sem curingas, com comparação escapada e ancorada; nenhuma liberação entre origens por padrão fora do modo local | A política deixa de conceder a permissão indevida na aplicação; não depende da autenticação para corrigir a configuração CORS | Origem não autorizada não recebe permissão; origens locais previstas continuam funcionando |
| V08 — Componentes vulneráveis | Os manifestos/lockfiles selecionavam versões afetadas por avisos conhecidos; o ambiente tinha pip vulnerável | Substituir ou remover componentes afetados, atualizar lockfiles e o pip do ambiente | As versões vulneráveis saem do inventário instalado; não há supressão de alertas para aparentar aprovação | Auditorias npm da raiz e frontend e auditoria Python sem avisos conhecidos na data registrada |

Outras causas também foram corrigidas, como a concatenação SQL (V03) e a validação tardia de lotes (parte de V06). Seus limites estão descritos nas respectivas seções. Limitar tamanho de corpo continua sendo mitigação de consumo de recursos; remover um arquivo com segredo continua exigindo revogação externa.

### Organização dos commits

Os commits desta entrega são agrupados por finalidade. A configuração local necessária aos testes acompanha os commits correspondentes; arquivos anteriores sem relação com as correções permanecem fora deles. Não foi feito push nem reescrita do histórico.

| Commit | Mensagem | Escopo e relação com os achados |
| --- | --- | --- |
| `d758a4c` | `fix(deps): atualizar componentes vulneraveis e runtime do frontend` | V08: versões corrigidas, lockfiles, construção do frontend e infraestrutura de emuladores necessária à validação |
| `510d9e0` | `fix(sql): parametrizar consultas e validar campos de atualizacao` | V03: causa da injeção retirada do módulo e das migrações, com testes SQLite separados; blueprint continua desativado |
| `56cc195` | `fix(api): corrigir transporte de tokens, erros e politica CORS` | V02, V04 e V05: três correções da aplicação ativa; também inclui validação de entradas, autenticação e seus testes |
| `cad3e40` | `fix(secrets): remover credencial Reddit da arvore versionada` | V09: remoção do segredo atual e exemplo seguro; **não comprova revogação e não entra nas três correções concluídas** |

Um commit final, `docs(security): registrar causas raizes, correcoes e evidencias`, reúne este relatório, as evidências sanitizadas e o guia de configuração. Seu identificador pode ser consultado no log, sem criar uma referência circular dentro do próprio arquivo commitado.

As mensagens incluem o motivo técnico e o escopo das mudanças. Os testes SQL acompanham seu commit; os testes de API e do cliente acompanham as correções da API. Para inspecionar a entrega:

```powershell
git log --oneline 71616a0..HEAD
git show --stat d758a4c
git show --stat 56cc195
```

As mudanças anteriores de carregamento de configuração em `backend/main.py`, o agregador de requisitos na raiz e o rascunho `docs/evidence/findings.md` foram preservados fora desses commits. No arquivo `main.py`, somente a substituição do gerador de IDs foi incluída no commit da API.

## Inventário dos achados

| ID | Achado | OWASP 2025 | Severidade no contexto | Estado |
| --- | --- | --- | --- | --- |
| V01 | Falha de autenticação convertida em consulta anônima | A01, A07, A10 | Média no fluxo atual; impacto maior depende da evolução do serviço | Fallback removido; política de login obrigatória adotada |
| V02 | Firebase ID token transmitido na URL do perfil | A07, A02 | Média | Transporte pela URL removido do cliente e recusado pela API |
| V03 | SQL construído com valores e identificadores concatenados | A05 | Alta se o módulo for exposto | Corrigido; blueprint permanece desativado na API principal |
| V04 | Erros internos expostos e execução com depurador | A02, A10 | Média; depurador dependia de acesso ao serviço local | Corrigido no caminho de execução analisado |
| V05 | CORS autorizando origens arbitrárias | A02 | Média | Política permissiva substituída por origens exatas |
| V06 | JSON sem esquema, mensagens inválidas gravadas parcialmente e corpo ilimitado | A10, A06 | Média | Validação corrigida; limites são mitigação de consumo de recursos |
| V07 | Cadastro público com credenciais administrativas do servidor | A06, A07 | Alta | Rota removida; cadastro transferido ao SDK cliente |
| V08 | Dependências com avisos de segurança e ferramenta de instalação vulnerável | A03 | Alta; há pacotes com avisos classificados como críticos no inventário inicial | Atualizações e evidências na seção de dependências |
| V09 | `client_secret` do Reddit versionado | A02 | Alta; validade da chave não foi testada | Arquivo retirado; revogação e resposta à exposição pendentes |
| V10 | Importação da API real aceitando configuração de emulador | A02, A07 | Alta se um ambiente real herdar essas variáveis | Inicialização passa a recusar a combinação |

## V01 — Autenticação que falhava permitindo continuar

**Evidência anterior:** `POST /users/query` com `{"query":"test"}` e sem credenciais retornava `200`. A função `Firebase.try_get_user_info` capturava qualquer exceção e retornava `None`, permitindo que a consulta continuasse. No frontend, `user?.getIdToken()` também era usado sem `await`, produzindo um cabeçalho sem um token resolvido.

**Limite da conclusão:** comentários do cliente admitiam consultas de visitantes, e o serviço atual retorna apenas `Fake implementation`. O `200` sem login, isoladamente, não demonstra acesso indevido a dados privados nem cobrança de IA. O comportamento inseguro identificado é ignorar indistintamente token inválido e falha operacional. Como mudança explícita de política, a correção também passa a exigir login nas consultas; se o produto voltar a oferecer consultas públicas, deverá separar o fluxo público e rejeitar credenciais inválidas, sem esse fallback silencioso.

**Arquivos:** [endpoints.py](../backend/endpoints.py), [firebase.py](../backend/firebase.py), [api.ts](../frontend/src/api.ts).

**Severidade:** Média no fluxo atual; não foi demonstrado acesso indevido a dados de outro usuário.

**Causa raiz:** erros de autenticação e de infraestrutura eram capturados indistintamente e convertidos em ausência de perfil, sem interromper o fluxo.

**Passos de reprodução:**

1. No estado anterior, enviar `POST /users/query` com `{"query":"test"}` sem `Authorization`: a API retornava `200`.
2. Repetir com `id_token` inválido no JSON. A verificação falhava e `try_get_user_info` convertia a falha em `None`, mantendo a consulta anônima.
3. No código corrigido, repetir sem Bearer válido: o resultado é `401`. O teste `test_invalid_revoked_and_disabled_tokens_fail_closed` verifica a recusa de credenciais inválidas.

**Impacto potencial para o negócio:** falhas de login e de infraestrutura poderiam ficar invisíveis, prejudicando a confiabilidade da personalização e a investigação de incidentes. Consumo indevido de um serviço de IA pago seria um risco futuro se essa integração fosse ativada sem alterar a política; esse custo não foi observado na implementação de demonstração.

**Passo a passo aplicado:**

1. Criar `require_auth` e aplicá-lo a todas as rotas de perfil, consulta, IDs de mensagem e chats.
2. Aceitar apenas `Authorization: Bearer <token>`, com estrutura validada.
3. Verificar o token pelo Admin SDK com `check_revoked=True`, incluindo a checagem de usuários desativados.
4. Derivar o proprietário dos dados exclusivamente do `uid` verificado e guardá-lo em `g.uid`.
5. Remover a função que transformava falhas em perfil anônimo. Uma falha do banco interrompe a consulta com resposta genérica.
6. No cliente, aguardar `await user.getIdToken()` em uma função compartilhada, `apiRequest`.

**Validação:** sem token ou com esquema incorreto, token inválido, revogado ou usuário desativado, a API retorna `401` antes do acesso aos dados. Uma falha de infraestrutura impede a criação do `QueryManager`. Testes verificam também que operações usam o UID autenticado e que um segundo usuário não lê nem apaga os dados do primeiro.

**Por que foi corrigido:** o caminho que executava consultas sem autenticação foi removido. A decisão está no servidor e independe de esconder botões, da origem CORS ou da boa conduta do cliente. O endpoint de demonstração agora exige login; consultas de visitantes deixam de ser aceitas.

## V02 — Token na URL

**Evidência anterior:** o cliente solicitava `GET /users/info?id_token=...` e a API aceitava esse token. URLs podem ser registradas por servidores, proxies, ferramentas de observabilidade e clientes. Não foi comprovado um vazamento histórico específico; foi confirmado o mecanismo de exposição. As respostas do perfil não definiam `Cache-Control`.

**Severidade:** Média.

**Causa raiz:** o contrato cliente/servidor tratava a query string como canal válido para uma credencial de sessão, expondo-a a superfícies que registram URLs.

**Passos de reprodução:**

1. No ambiente anterior isolado, criar uma conta no emulador, fazer login e obter seu ID token local.
2. Executar `curl.exe -i "http://127.0.0.1:5000/users/info?id_token=ID_TOKEN_LOCAL"`, substituindo apenas o placeholder pelo token local. Antes, a resposta era `200` e a credencial integrava o endereço da requisição.
3. Conferir a captura [security-before.json](evidence/security-before.json), campo `url_token_profile_status`, e o caminho de construção da URL anteriormente existente em `api.ts`.
4. No estado corrigido, essa requisição retorna `401`. Com `Authorization: Bearer ID_TOKEN_LOCAL` e sem parâmetros na URL, o perfil continua acessível. O teste `test_credentials_in_url_or_body_cannot_authenticate` valida a recusa do canal antigo.

**Impacto potencial para o negócio:** alguém com acesso indevido a URLs registradas poderia reutilizar o token enquanto ele permanecesse aceito e acessar ou alterar dados da conta nas rotas permitidas. Isso pode expor informações de perfil e conversas, gerar atendimento para recuperação de contas e reduzir a confiança no serviço. Não há comprovação de que isso tenha ocorrido.

**Passo a passo aplicado:**

1. Substituir o parâmetro por `Authorization: Bearer <token>` em [api.ts](../frontend/src/api.ts).
2. Remover a leitura de tokens de query string e de corpos JSON no servidor.
3. Recusar parâmetros na leitura do perfil, mesmo que exista um cabeçalho válido.
4. Aplicar `Cache-Control: no-store` e `Referrer-Policy: no-referrer` às respostas da API.
5. Usar caminhos relativos `/api/...`, com proxy local do Vite. A implantação deve encaminhá-los no mesmo domínio por HTTPS.

**Validação:** token apenas na URL retorna `401`; URL com parâmetros e Bearer válido retorna `400`; perfil com Bearer válido e sem parâmetros retorna `200`. O teste também verifica `no-store`.

**Por que foi corrigido:** a aplicação não produz mais URLs com credenciais nem usa esse canal para autenticar. A remoção do canal é a correção; os cabeçalhos são medidas complementares. Isso não apaga registros antigos, não elimina um cabeçalho capturado por um proxy configurado incorretamente e não comprova a existência de TLS em produção.

## V03 — Injeção SQL

**Evidência no código anterior:** [courses.py](../backend/blueprints/courses.py) usava expressões como:

```python
f"SELECT * FROM courses WHERE semester = '{semester}'"
```

Um valor como `' OR 1=1--` altera a condição SQL. Os filtros de departamento e professor tinham o mesmo padrão. As rotas com `<int:...>` já restringiam o tipo no Flask, mas também foram parametrizadas para retirar a concatenação. **O blueprint não estava registrado em `endpoints.py` e continua sem registro**: não foi comprovada exploração remota dessas rotas na aplicação principal. Além disso, o helper devolvia um cursor depois de fechar sua conexão, um defeito funcional separado que impedia seu uso normal.

O método `DataMigrations.update_post` concatenava nomes de campos de `kwargs`. Parâmetros SQL protegem valores; eles não tornam um identificador arbitrário seguro.

**Severidade:** Alta se o código for disponibilizado a entradas não confiáveis; achado latente, fora da contagem mínima da aplicação ativa.

**Causa raiz:** valores de filtros e nomes de campos eram concatenados à estrutura SQL, sem separar dados de comandos nem restringir identificadores.

**Passos de reprodução controlada:**

1. Em um banco SQLite temporário, inserir pelo menos dois cursos e montar a expressão antiga de filtro usando o valor `' OR 1=1--` como semestre.
2. Executar essa expressão diretamente no SQLite de teste: a condição passa a selecionar registros independentemente do semestre. Isso demonstra a injeção na construção SQL, sem alegar que o blueprint estava acessível pela API principal.
3. No helper antigo, considerar também o defeito independente do cursor fechado; não interpretar uma falha desse cursor como comprovação de exploração remota.
4. Executar `test_injection_is_literal_data_in_every_filter` no código corrigido: os três filtros tratam a carga como dado literal e não retornam cursos para ela. O teste de migração verifica separadamente o identificador de coluna malicioso.

**Impacto potencial para o negócio:** se essas rotas fossem ativadas sem correção, consultas manipuladas poderiam revelar dados fora do filtro solicitado e comprometer a integridade das recomendações. Nas migrações, identificadores não autorizados poderiam alterar o comando executado. Interrupção da coleta, retrabalho de dados e informações acadêmicas incorretas seriam consequências possíveis; não foram observadas em produção.

**Passo a passo aplicado:**

1. Mudar [db.py](../backend/db.py) para `execute_query(query, parameters=())` e executar `conn.execute(query, parameters)`.
2. Materializar o resultado antes de fechar a conexão e retornar uma lista de dicionários serializável.
3. Trocar a interpolação por placeholders em todos os filtros:

   ```python
   execute_query("SELECT * FROM courses WHERE semester = ?", (semester,))
   ```

4. Separar as rotas ambíguas em `/courses/semester/...`, `/courses/department/...` e `/courses/instructor/...`. Essas rotas só existem quando o blueprint é registrado.
5. Validar os nomes de campos de `update_post` por uma lista derivada de `RedditPost`, excluindo `post_id` e `comments`, antes de qualquer mutação.
6. Manter os valores do `UPDATE` como parâmetros do driver.

**Validação:** o teste registra o blueprint apenas em uma aplicação isolada e usa SQLite temporário. A carga de injeção não retorna registros nos três filtros; `O'Brien` continua funcionando como dado legítimo. Um nome de coluna malicioso é recusado antes de excluir comentários; um valor contendo sintaxe SQL é armazenado literalmente. O notebook de experimentos já usava placeholders na cláusula `IN` examinada.

**Por que foi corrigido:** a entrada deixa de compor o comando SQL. Identificadores são escolhidos de um conjunto fechado. Não foi usada uma lista de palavras proibidas nem um filtro para retirar apóstrofos, que apenas reduziria alguns ataques e prejudicaria dados legítimos.

## V04 — Erros internos e depurador

**Evidência anterior:** diversas rotas devolviam `str(e)` ao cliente. Uma exceção controlada com o marcador `INTERNAL_SENTINEL` apareceu na resposta HTTP de `/hash`. A execução direta chamava `app.run(debug=True)`. O Flask usava loopback por padrão; não há evidência de que o depurador estivesse exposto à internet.

**Severidade:** Média. O achado contabilizado é a exposição das mensagens de exceção; o depurador é uma condição adicional de configuração local.

**Causa raiz:** os handlers publicavam mensagens de exceção diretamente por `str(e)`, e a inicialização habilitava o depurador sem necessidade para o funcionamento da API.

**Passos de reprodução:**

1. Na versão anterior isolada, executar `curl.exe -i -X POST "http://127.0.0.1:5000/hash" -H "Content-Type: application/json" --data "{}"` sem `Authorization`.
2. O código antigo tentava executar `.split()` sobre o cabeçalho ausente e devolvia o texto da exceção no JSON, com status `500`, expondo detalhes da implementação em vez de uma recusa de autenticação.
3. Na reprodução já registrada, uma falha controlada do verificador também fez a API devolver `INTERNAL_SENTINEL`: ver `internal_exception_disclosed: true` em [security-before.json](evidence/security-before.json). Essa variante usa um provedor simulado, sem acesso a produção.
4. No código corrigido, o comando sem Bearer retorna `401` genérico. `test_error_responses_and_logs_do_not_contain_secrets` confirma que uma falha interna não publica sua mensagem nem nos logs da aplicação.

**Impacto potencial para o negócio:** detalhes internos podem facilitar o reconhecimento da tecnologia e a preparação de ataques posteriores. Dependendo da exceção, informações operacionais também poderiam vazar. As consequências potenciais incluem maior custo de resposta a incidentes e perda de confiança; a reprodução não demonstrou vazamento de uma senha real nem execução remota de código.

**Passo a passo aplicado:**

1. Substituir a execução por `app.run(host='127.0.0.1', debug=False)`.
2. Centralizar respostas para erros HTTP, validação e exceções inesperadas.
3. Retornar mensagens estáveis e códigos coerentes: `400`, `401`, `404`, `413`, `415` e `500` conforme o caso.
4. Gerar um identificador de requisição no servidor e devolvê-lo em `X-Request-ID`; nos erros, incluir também `request_id` no JSON.
5. Registrar evento, status ou tipo da exceção e identificador. Não registrar mensagens de exceção, corpo, token, senha nem query string no logger da aplicação.

**Validação:** o marcador privado não aparece na resposta nem no registro da aplicação. Os testes conferem os argumentos de inicialização e a correlação do erro com seu identificador. Serviços externos, gateways e o logger de acesso têm configurações próprias e precisam de revisão na implantação.

**Por que foi corrigido:** os dois mecanismos identificados — serializar a exceção e iniciar com depurador — foram removidos do caminho analisado. Limitar o acesso por firewall sem mudar o código seria apenas uma mitigação. Um operador ainda pode habilitar um depurador por outros comandos; esses comandos não foram autorizados nem usados nesta revisão.

## V05 — CORS permissivo

**Evidência anterior:** `CORS(app)` devolvia `Access-Control-Allow-Origin: https://untrusted.example` para uma origem arbitrária. Como as credenciais são enviadas explicitamente em Bearer e não em cookies de sessão, isso não comprova que um site terceiro conseguiria roubar automaticamente a sessão de outra pessoa.

**Severidade:** Média, referente à configuração permissiva. O impacto concreto sobre dados privados depende de o atacante conseguir credenciais ou de outra falha independente.

**Causa raiz:** `CORS(app)` não estabelecia uma lista de origens confiáveis e concedia a permissão a origens arbitrárias.

**Passos de reprodução:**

1. Executar o preflight abaixo contra o ambiente local:

   ```powershell
   curl.exe -i -X OPTIONS "http://127.0.0.1:5000/users/info" -H "Origin: https://untrusted.example" -H "Access-Control-Request-Method: POST" -H "Access-Control-Request-Headers: authorization,content-type"
   ```

2. No estado anterior, observar `Access-Control-Allow-Origin: https://untrusted.example`, embora essa origem não fosse parte do frontend autorizado.
3. No estado corrigido, o cabeçalho de permissão para essa origem está ausente. Repetir com `Origin: http://localhost:5173` no modo local confirma que a origem prevista continua autorizada.
4. Conferir `test_cors_only_allows_exact_local_origins` e o campo `untrusted_cors_origin` nas evidências anteriores e posteriores.

**Impacto potencial para o negócio:** páginas de terceiros poderiam integrar chamadas à API a partir do navegador e ler respostas nas condições que a API permitisse, ampliando as origens capazes de consumir o serviço. Com outra exposição de token, isso facilitaria o uso de dados fora do frontend oficial. Não foi demonstrado envio automático de sessão, furto de conta ou leitura anônima de perfis.

**Passo a passo aplicado:**

1. Autorizar por padrão apenas `http://localhost:5173` e `http://127.0.0.1:5173` no modo local.
2. Fora desse modo, manter a lista vazia por padrão: o frontend usa a mesma origem via gateway.
3. Permitir configuração explícita em `COURSESPHERE_ALLOWED_ORIGINS`, aceitando HTTPS; HTTP é permitido somente em loopback.
4. Recusar curingas e caminhos, escapar as origens e ancorar a comparação para impedir que sejam interpretadas como expressões parciais.
5. Restringir métodos e cabeçalhos e manter `supports_credentials=False`.

**Validação:** origens desconhecidas e origens parecidas não recebem autorização CORS; as duas origens locais previstas continuam aceitas. Os testes também verificam que produção não tem liberação entre origens por padrão.

**Por que foi corrigido:** a política de autorizar qualquer origem foi substituída na configuração da aplicação. Isso resolve essa configuração específica. CORS controla o navegador; clientes de linha de comando continuam capazes de chamar a API e precisam passar pela autenticação.

## V06 — Entrada sem contrato e gravação parcial por erro de validação

**Evidência anterior:** uma lista JSON onde o servidor esperava objeto causava `500`. Uma consulta com mais de 300 mil caracteres era aceita. `Firebase.save_chat` gravava cada mensagem à medida que a validava; se a segunda entrada fosse inválida, a primeira já teria sido escrita.

**Severidade:** Média.

**Causa raiz:** a API não validava previamente o contrato completo da entrada; o armazenamento validava cada item depois de já poder ter gravado os anteriores. A ausência de limite de corpo ampliava o consumo possível, mas constitui um problema de recursos separado.

**Passos de reprodução:**

1. No ambiente anterior, enviar um array JSON em lugar do objeto esperado e observar `500`; a captura inicial usou a antiga rota de cadastro.
2. Enviar uma consulta com mais de 300 mil caracteres a `/users/query`: a captura anterior registrou `200`.
3. Para a gravação parcial, preparar um lote local com uma mensagem válida seguida de um item que não seja objeto. A implementação antiga fazia `push` da primeira antes de rejeitar o segundo item.
4. No código corrigido, executar `test_json_type_content_type_and_size_are_validated`, `test_chat_validation_happens_before_any_write` e `test_privileged_chat_storage_enforces_user_paths_and_batch_validation`. Os testes verificam `400`/`413` e nenhuma escrita por lote com erro de validação.

**Impacto potencial para o negócio:** históricos incompletos, processamento desperdiçado e erros evitáveis podem reduzir a disponibilidade e a confiabilidade do serviço, aumentar custos de infraestrutura e gerar chamados de suporte. A aceitação de um corpo grande não demonstra, sozinha, que houve indisponibilidade ou ataque de DoS bem-sucedido.

**Passo a passo aplicado:**

1. Criar [validation.py](../backend/validation.py), validando objetos, campos permitidos, tipos, comprimentos, listas e chaves de banco.
2. Limitar consultas a 8.000 caracteres; perfil a listas e textos delimitados; lotes a 100 mensagens e conteúdo textual a 16.000 caracteres por mensagem.
3. Recusar campos desconhecidos, incluindo `uid` e `admin` fornecidos no corpo do perfil.
4. Validar o lote inteiro antes da primeira escrita, tanto na rota quanto no método privilegiado do Firebase.
5. Validar também chaves e profundidade dos objetos de recomendações; recusar identificadores com separadores de caminhos do Realtime Database.
6. Definir `MAX_CONTENT_LENGTH = 256 * 1024`, com retorno `413` para corpos maiores.

**Validação:** arrays, `null`, tipos errados, JSON quebrado e lotes inválidos são recusados. O mock de armazenamento não recebe escrita quando há uma entrada inválida posterior à primeira. Há testes na fronteira HTTP e diretamente no método privilegiado.

**Por que parte foi corrigida e parte foi mitigada:** o contrato de entrada e a validação prévia eliminam os erros de tipo e a gravação parcial causada por validação tardia. **Os limites são mitigação de consumo excessivo**, não solução completa contra DoS. Falhas de rede ainda podem interromper um lote durante múltiplas escritas; não foi implementada uma transação atômica nem alegada essa garantia. As regras existentes do banco já restringiam usuários aos próprios dados; isso foi preservado e testado, não contado como nova correção.

## V07 — Cadastro público executado como administrador

**Evidência no código:** `POST /users/create` recebia e-mail e senha e chamava `firebase_admin.auth.create_user` sem autenticação. Cadastro público é uma funcionalidade legítima; o problema é disponibilizar a operação administrativa por uma rota genérica, fora do fluxo cliente de cadastro, e devolver detalhes das falhas do provedor.

**Severidade:** Alta para a exposição da capacidade administrativa, condicionada aos controles do projeto; não contabilizada isoladamente para atingir as cinco falhas confirmadas.

**Causa raiz:** uma rota pública de cadastro delegava o provisionamento à identidade administrativa do servidor, em vez do fluxo cliente de Authentication, e repassava detalhes das falhas.

**Passos de reprodução:**

1. Na versão anterior e somente com emuladores, enviar um cadastro fictício a `/users/create`, sem Bearer.
2. Verificar que a rota chamava `Firebase.create_user`, cujo código delegava ao Admin SDK. O fato de criar uma conta não prova, por si só, falha de segurança em um produto com cadastro aberto.
3. Não executar criação em massa nem presumir que quotas ou políticas do projeto real foram contornadas: essa exploração não foi demonstrada.
4. No código corrigido, a rota retorna `404`; `test_public_admin_signup_is_removed` confirma que o método administrativo não é chamado. O cadastro legítimo segue pelo SDK cliente e é exercitado nos emuladores.

**Impacto potencial para o negócio:** um caminho administrativo público pode ampliar a possibilidade de provisionamento abusivo e uso indevido de recursos, conforme os controles do provedor. Contas indevidas, consumo de quotas e trabalho de limpeza seriam impactos potenciais. Não foi comprovado abuso desse tipo no projeto real.

**Passo a passo aplicado:**

1. Remover completamente a rota pública de provisionamento administrativo.
2. Fazer `createUser` no frontend chamar `createUserWithEmailAndPassword` do SDK oficial do Firebase Authentication.
3. Usar a sessão já criada pelo SDK, sem um segundo login após o cadastro.
4. Mostrar erro genérico no cadastro e no login. As configurações de política de senhas e proteção contra enumeração devem ser conferidas no provedor.
5. Ajustar os testes locais para cadastrar pela API de Authentication do emulador, equivalente ao serviço usado pelo SDK.

**Validação:** `/users/create` retorna `404` e não chama o método administrativo. Os testes com emuladores exercitam cadastro, login, perfil e mensagens pelo fluxo ajustado.

**Por que foi corrigido:** o caminho público que usava a identidade administrativa foi eliminado. Limitar algumas chamadas mantendo esse caminho seria apenas reduzir seu abuso. A remoção não comprova que quotas, política de senhas, verificação de e-mail ou controles antifraude do projeto real estejam corretamente configurados.

## V08 — Dependências e construção do frontend

**Evidência inicial:** `npm audit` identificou **39 pacotes sinalizados no frontend**: 2 críticos, 19 altos, 17 moderados e 1 baixo. Na raiz, foram sinalizados **5 pacotes moderados** da ferramenta Firebase CLI. Esses números incluem relações transitivas; não representam 44 explorações independentes. Os avisos e suas URLs estão nos relatórios JSON.

O `pip-audit` encontrou no ambiente virtual `pip==26.1.2`, associado a `CVE-2026-13346` / `GHSA-qwm4-qh6w-59xr`. O relatório duplicou entradas do mesmo aviso; é um pacote e uma falha conhecida, não duas falhas distintas. O `pip` é ferramenta de instalação, não uma rota da aplicação.

**Severidade:** Alta para o achado agregado de componentes vulneráveis; os avisos individuais têm suas próprias classificações no relatório. Os dois pacotes críticos não tornam automaticamente toda a aplicação criticamente explorável.

**Causa raiz:** a árvore instalada e os lockfiles mantinham versões afetadas por avisos conhecidos; a ferramenta pip instalada também estava numa versão vulnerável.

**Passos de reprodução e verificação:**

1. Na cópia isolada com os lockfiles anteriores, instalar as dependências e executar `npm audit --json --ignore-scripts` na raiz e em `frontend`. Os relatórios preservados são a evidência da consulta feita na data da revisão; resultados de uma consulta futura podem mudar.
2. Abrir [npm-frontend-before.json](evidence/npm-frontend-before.json) e selecionar um aviso específico, por exemplo os associados a `vite`. Conferir versão afetada, intervalo vulnerável, URL do aviso e caminho da dependência. Não contar entradas transitivas do mesmo aviso como explorações independentes.
3. Conferir os componentes Python em [pip-audit-before.json](evidence/pip-audit-before.json), lembrando que o inventário inclui a ferramenta de instalação.
4. No estado corrigido, instalar com `npm ci` e repetir `npm audit` nos dois diretórios; os relatórios posteriores registram zero avisos. Repetir `pip-audit` no ambiente atualizado verifica os pacotes Python instalados.

**Impacto potencial para o negócio:** conforme o componente e suas condições de uso, falhas conhecidas podem expor arquivos do ambiente de desenvolvimento, interromper processamento ou comprometer dados. Isso pode gerar indisponibilidade, investigação e retrabalho. O risco dos componentes usados apenas para desenvolvimento/instalação é diferente daquele dos componentes incluídos no navegador; a auditoria de inventário não demonstra execução de cada ataque na aplicação.

**Passo a passo aplicado:**

1. Auditar a raiz e o frontend separadamente e preservar os resultados anteriores em `docs/evidence/`.
2. Atualizar o Vite da série 5 para `^6.4.5`, retirando também o esbuild antigo da árvore correspondente; atualizar dependências compatíveis e respectivos lockfiles. As atualizações dentro das séries antigas não eliminaram todos os avisos: o Firebase foi migrado para `13.1.0` e o React Router DOM para `7.18.4`. O gRPC transitivo foi atualizado por override `^1.13.6`, resolvido como `1.14.6`, sem fazer o downgrade de Firebase sugerido automaticamente pelo audit.
3. Remover `jquery` após substituir a leitura de campos por APIs do DOM, e remover `uuid`, que não era usado pelo código.
4. Na ferramenta Firebase CLI, usar overrides para `uuid` na série corrigida `^11.1.1` e `@opentelemetry/core` em `^2.8.0`. A versão efetivamente resolvida fica no lockfile; os testes com emuladores verificam o funcionamento do CLI após essa troca.
5. Fixar as versões diretas do backend já instaladas e auditadas em `backend/requirements.txt`.
6. Atualizar o `pip` do ambiente virtual para `26.2.2` e documentar como atualizar ambientes novos.
7. Substituir `node:16-alpine` por construção com Node 24, usar `npm ci` e servir o resultado estático em uma etapa Nginx separada. Acrescentar `.dockerignore` e uma configuração de rotas SPA. O gateway de implantação é responsável por `/api/`.
8. Retirar `bun.lockb`, que preservava a árvore antiga, e adotar os lockfiles npm como fonte para instalação.
9. Reexecutar auditorias e o build. Conferir o resultado consolidado na seção de validação.

**Por que a atualização é correção:** uma versão afetada por um aviso deixa de fazer parte da árvore instalada e bloqueada no lockfile. Apenas ignorar o aviso, restringir a rede ou ocultar o servidor de desenvolvimento não removeria o componente vulnerável. Zero avisos conhecidos é uma observação da base consultada naquela data; não é uma garantia permanente.

**Limites:** versões Python diretas fixas não equivalem a um lockfile transitivo com hashes. As imagens Docker ainda usam tags e precisam de manutenção e auditoria; não foram fixadas por digest. O Docker Engine não estava disponível neste ambiente, portanto a imagem não foi construída nem escaneada. As dependências exclusivas dos scripts auxiliares, fora do ambiente virtual instalado, não estão cobertas pelo resultado de `pip-audit` desse ambiente.

## V09 — Segredo do Reddit no Git: pendência externa

**Evidência:** `backend/cornell-course-sphere-data/reddit-data/reddit_key.json` estava versionado com `client_id` e `client_secret` preenchidos, sem indicação de placeholder. A evidência sanitizada registra apenas a presença dos campos, nunca seus valores. Não foi feita chamada ao Reddit para confirmar se a chave continua ativa. A configuração pública do SDK web do Firebase não foi classificada como chave privada de conta de serviço.

**Severidade:** Alta para a exposição do segredo; sua validade e eventual uso indevido permanecem desconhecidos.

**Causa raiz:** um arquivo operacional contendo credencial privada foi incluído no controle de versão e, por consequência, permaneceu acessível no histórico. A ausência de revogação mantém a exposição anterior sem encerramento comprovado.

**Passos de reprodução sem publicar a credencial:**

1. Confirmar a presença do arquivo na revisão Git sem imprimir seu conteúdo:

   ```powershell
   git cat-file -e 71616a0:backend/cornell-course-sphere-data/reddit-data/reddit_key.json
   ```

2. O código de saída `0` confirma que o objeto existe na revisão anterior `71616a0`, preservada no histórico. `HEAD` já inclui os novos commits e não deve ser usado como referência do arquivo antigo. A evidência [secret-review.json](evidence/secret-review.json) registra separadamente a revisão examinada e que os campos estavam preenchidos e não pareciam placeholders; o comando anterior sozinho não demonstra isso.
3. A leitura controlada realizada na revisão permitiu verificar esses indicadores sem guardar os valores no relatório. Não copiar o segredo para a documentação, prints ou console compartilhado.
4. Conferir que o arquivo real não está na árvore atual e que existe apenas o exemplo com placeholders. O objeto continua acessível no histórico, portanto essa reprodução histórica não deixa de funcionar apenas com a exclusão do arquivo atual.

**Impacto potencial para o negócio:** se ainda aceito pelo provedor, o segredo pode permitir uso não autorizado da integração e consumo de suas quotas ou limites, comprometendo a continuidade da coleta. Rotação emergencial, investigação e redistribuição das credenciais geram esforço operacional. Não foi comprovado uso indevido nem que o segredo permita acessar contas pessoais de usuários do CourseSphere.

**Ações realizadas:**

1. Retirar `reddit_key.json` da árvore de trabalho, deixando sua exclusão como alteração revisável no Git.
2. Adicionar o nome exato ao `.gitignore` e acrescentar padrões para arquivos locais `.env`, preservando os exemplos e a configuração fictícia dos emuladores.
3. Criar `reddit_key.example.json` somente com placeholders. O coletor continua aceitando a cópia local ignorada.
4. Documentar a configuração local em [setup.md](setup.md).

**Passo a passo que o responsável pela credencial ainda precisa executar:**

1. Revogar o segredo exposto nas configurações da aplicação no provedor e gerar um substituto.
2. Verificar registros e consumo associados à credencial e investigar eventual uso indevido.
3. Distribuir a nova credencial por um mecanismo privado, sem commitá-la.
4. Se for necessário remover o conteúdo do histórico remoto, coordenar a reescrita com os colaboradores, considerando branches, tags, forks e clones. Não foi reescrito o histórico nesta revisão.

**Por que não se pode chamar isso de resolvido:** o valor antigo permanece no histórico e em possíveis cópias. `.gitignore` não remove arquivos já versionados nem revoga segredos. A correção do arquivo atual é verificável; o encerramento da exposição depende da revogação, que não foi executada nem presumida. Mesmo limpar o histórico não substitui a rotação.

## V10 — Emulador de autenticação em ambiente real

**Evidência no código anterior:** a execução direta com `--firebase` já limpava variáveis de emulador. Entretanto, a importação de `firebase.py` por um servidor WSGI podia inicializar um projeto real com `FIREBASE_AUTH_EMULATOR_HOST` herdado do ambiente. O Firebase Admin SDK, quando direcionado ao emulador, aceita os tokens sem assinatura emitidos para testes. O cenário depende de configuração do processo, não é um parâmetro manipulável por uma requisição HTTP.

**Severidade:** Alta na combinação de configuração descrita; cenário condicional, fora da contagem mínima.

**Causa raiz:** o caminho de importação não recusava variáveis de emulador herdadas ao inicializar a configuração real, permitindo uma combinação incompatível com a confiança esperada em produção.

**Passos de reprodução controlada:**

1. Examinar o caminho antigo de importação com `COURSESPHERE_LOCAL=0` e uma variável de emulador preenchida: não havia uma recusa explícita dessa combinação antes de inicializar o SDK.
2. Não usar credenciais reais para materializar esse cenário. O achado é de configuração e não comprova que um ambiente publicado estava nessa condição.
3. No código corrigido, executar `test_import_refuses_unsigned_emulator_tokens_in_production`: o teste define cada variável de emulador em um processo com modo local desativado e confirma `RuntimeError` antes da inicialização real.
4. Confirmar com os demais testes de configuração que o modo local legítimo continua usando apenas projeto fictício e loopback.

**Impacto potencial para o negócio:** se uma implantação real desviasse a verificação de identidade para emuladores, poderia perder a confiança na autenticação ou na separação dos dados de teste. Isso poderia levar a acesso indevido e incidentes operacionais. Esse desvio não foi observado em produção.

**Passo a passo aplicado:**

1. Exigir `COURSESPHERE_LOCAL=1` para o ramo local, com projeto `demo-coursesphere` e os dois serviços em loopback.
2. Fora desse ramo, recusar a inicialização caso exista `FIREBASE_AUTH_EMULATOR_HOST` ou `FIREBASE_DATABASE_EMULATOR_HOST` preenchido.
3. Preservar a exigência de credenciais reais no modo Firebase, sem fallback automático para o modo local.
4. Documentar que a implantação deve manter o modo local desativado.

**Validação:** testes de importação confirmam a rejeição de cada variável fora do modo local. Os testes anteriores de configuração e inicialização foram preservados e ajustados às novas garantias.

**Por que foi corrigido:** a combinação de inicialização real com desvio de serviço para emulador passa a ser rejeitada antes de servir requisições. Um processo deliberadamente iniciado em modo local continua sendo de desenvolvimento e não deve ser publicado.

## Melhorias complementares e cobertura do Top 10

Uma etapa adicional implementou **rate limiting por IP/usuário** e **headers HTTP de segurança** como dois controles preventivos além do fluxo funcional original. A configuração, o passo a passo de reprodução, os testes e os limites desses controles estão em [security-improvements.md](security-improvements.md). A validação de inputs continua como controle complementar. O rate limiting mitiga abuso; não foi apresentado como solução completa de DoS nem como bloqueio de login no Firebase

Os IDs de mensagem agora usam `secrets.token_hex(32)` em vez de uma composição de aleatoriedade e hash. O frontend resolve o ID antes de serializar a mensagem, que antes podia conter uma `Promise` convertida em `{}`. Esse identificador não é hash de senha nem mecanismo de autorização, portanto a implementação anterior não foi apresentada como quebra criptográfica comprovada.

O campo de senha do cadastro passou a usar `type="password"` e `autocomplete="new-password"`. Também foram corrigidos erros de tipagem e parâmetros/imports não usados que impediam o build de TypeScript já no estado inicial.

| Categoria 2025 | Resultado desta revisão |
| --- | --- |
| A01 — Controle de acesso | V01; isolamento por UID e regras existentes do RTDB verificados |
| A02 — Configuração insegura | V02, V04, V05, V09 e V10 |
| A03 — Cadeia de suprimentos | V08; auditoria limitada aos inventários indicados |
| A04 — Falhas criptográficas | Não foi encontrada uma quebra criptográfica explorável no fluxo ativo; TLS da implantação não foi inspecionado |
| A05 — Injeção | V03; SQL corrigido, com alcance dos módulos explicitado |
| A06 — Design inseguro | V06 e V07; proteção geral contra abuso ainda depende da implantação |
| A07 — Autenticação | V01, V02, V07 e V10 |
| A08 — Integridade de software/dados | Validação de mensagens reforçada; não foi comprovado um ataque independente à cadeia de publicação. O script Java já validava checksum, o que foi preservado |
| A09 — Registro e monitoramento | Eventos de rejeição e falha com correlação acrescentados; coleta centralizada e alertas continuam pendentes |
| A10 — Condições excepcionais | V01, V04 e V06; falhas de autenticação e de dados deixam de liberar continuação silenciosa |

Não foi confirmada uma rota ativa de SSRF, execução arbitrária de comandos ou XSS. As mensagens examinadas são renderizadas como texto React, sem `dangerouslySetInnerHTML`. Isso descreve o escopo revisado e não certifica ausência de outras falhas.

## Como reproduzir a validação

Na raiz, execute:

```powershell
npm ci
cd frontend
npm ci
npm test
npm run build
npm audit
cd ..
npm audit
.\backend\.venv\Scripts\python.exe -m unittest discover -s backend/tests -v
.\backend\.venv\Scripts\python.exe -m pip_audit
.\backend\.venv\Scripts\python.exe -m pip check
```

Para incluir a integração real com os emuladores, mantenha `npm run emulators` em outro terminal e execute na raiz:

```powershell
$env:RUN_FIREBASE_EMULATOR_TESTS = "1"
.\backend\.venv\Scripts\python.exe -m unittest discover -s backend/tests -v
Remove-Item Env:RUN_FIREBASE_EMULATOR_TESTS
```

As cargas de ataque à API são exercitadas por [test_security.py](../backend/tests/test_security.py); a injeção SQL e os identificadores das migrações são verificados separadamente em [test_sql_security.py](../backend/tests/test_sql_security.py). O fluxo de cadastro, login, usuário desativado, perfil, mensagens e isolamento entre usuários está em [test_firebase_local.py](../backend/tests/test_firebase_local.py). Os testes não usam credenciais de produção.

### Evidências da primeira entrega

Os resultados abaixo preservam a rodada original de correções. A etapa posterior de melhorias preventivas passou com **38 testes no backend e 5 no cliente**, além das verificações HTTP de headers; suas evidências e limitações estão no [guia de melhorias](security-improvements.md).

| Verificação | Resultado final | Evidência |
| --- | --- | --- |
| Backend com emuladores de Authentication e RTDB | **27 testes passaram; zero falhas, erros ou testes ignorados** | [security-tests.json](evidence/security-tests.json) |
| Regressão de segurança do cliente | **5 testes passaram**, incluindo token aguardado, ausência de token em URL/corpo e cadastro pelo SDK | [frontend-tests.txt](evidence/frontend-tests.txt), [testes](../frontend/tests/api-security.test.cjs) |
| Compilação TypeScript e build Vite | **Passou**; aviso de bundle JavaScript maior que 500 kB | [frontend-build.txt](evidence/frontend-build.txt) |
| ESLint | **Passou**, sem erros ou avisos | [frontend-lint.txt](evidence/frontend-lint.txt) |
| `npm audit` no frontend | **39 → 0 pacotes sinalizados** | [antes](evidence/npm-frontend-before.json), [depois](evidence/npm-frontend-after.json) |
| `npm audit` na raiz | **5 → 0 pacotes sinalizados** | [antes](evidence/npm-root-before.json), [depois](evidence/npm-root-after.json) |
| `pip-audit` do ambiente instalado | **1 pacote vulnerável → 0 avisos conhecidos** após atualizar o pip | [antes](evidence/pip-audit-before.json), [depois](evidence/pip-audit-after.json) |
| `pip check` | Sem requisitos incompatíveis | Executado no mesmo ambiente auditado |
| Revisão da credencial | Removida da árvore atual; ainda consta no histórico | [secret-review.json](evidence/secret-review.json), sem valores secretos |
| Imagem Docker | Não construída: Docker Engine indisponível | Limitação registrada; não conta como teste aprovado |

As reproduções antes/depois estão em [security-before.json](evidence/security-before.json) e [security-after.json](evidence/security-after.json). O corpo excessivo e o array JSON foram testados com Bearer válido depois da correção, para verificar a validação sem que a ausência de autenticação interrompesse o teste antes.

| Reprodução | Antes | Depois |
| --- | --- | --- |
| Consulta sem autenticação | `200` | `401` |
| Perfil autenticado somente por token na URL | `200` | `401` |
| Marcador da exceção retornado ao cliente | Presente | Ausente |
| Origem CORS desconhecida autorizada | Sim | Não |
| Consulta com corpo maior que 256 KiB | `200` | `413` com autenticação válida |
| Array no lugar de objeto JSON | `500` na rota antiga de cadastro | `400` na consulta autenticada; rota antiga removida |
| Cache do perfil explicitamente proibido | Não | `Cache-Control: no-store` |

O relatório inicial de integração teve um erro de isolamento do teste de configuração: o processo de teste herdou variáveis do emulador. O teste foi ajustado para limpar essas variáveis no cenário que exige credenciais reais. A rodada final acima passou integralmente. Logs brutos de diagnóstico do Firebase não foram incluídos, pois podem imprimir o ambiente do processo.

## Pendências de implantação e riscos restantes

1. **Revogar a credencial exposta do Reddit** e avaliar seu uso. É a pendência diretamente relacionada a uma exposição já confirmada.
2. Publicar as regras de banco revisadas em um projeto real somente pelo processo de implantação apropriado. O teste local não comprova quais regras estão hoje em produção; o Admin SDK tem privilégios que exigem autorização na própria API.
O [ambiente local com Docker Compose](containers.md) implementa proxy `/api/`, Nginx com duas APIs Waitress e Redis compartilhado por socket Unix. HTTPS, limites adicionais no gateway, calibração de cotas e validação no ambiente real continuam pendentes de implantação. Contêineres e balanceamento não substituem as correções da lógica da aplicação nem constituem solução completa contra DoS.
4. Conferir política de senhas, proteção contra enumeração, verificação de e-mail e controles de abuso do Firebase Authentication real.
5. Os logs de requisições, erros e verificação de tokens agora são JSON, com métricas e sonda de vida implementadas; veja [observability.md](observability.md) e as [evidências de 51 testes](evidence/observability-tests.json). Ainda é necessário implantar a coleta central, retenção, alertas e o dashboard, além de verificar a redação de credenciais nos logs de gateway. O próprio Firebase CLI em modo diagnóstico pode imprimir o ambiente; esses logs brutos não são evidências versionadas desta revisão. Observabilidade não substitui as correções de causa raiz descritas neste relatório.
6. Manter atualização e auditoria de dependências. A auditoria Python do ambiente instalado não inclui automaticamente todos os scripts auxiliares e notebooks.
7. Antes de habilitar os endpoints de cursos, validar seu esquema real e registrar o blueprint intencionalmente. A listagem/edição de históricos ainda tem rotas incompletas no frontend; a revisão não as implementa. A consulta continua retornando uma resposta de demonstração e não passou a executar IA.

## Referências técnicas

- [OWASP Top 10:2025 em português](https://top10.owasp.org/2025/pt-BR/) — classificação usada.
- [Firebase: verificar ID tokens](https://firebase.google.com/docs/auth/admin/verify-id-tokens) e [gerenciar sessões e revogação](https://firebase.google.com/docs/auth/admin/manage-sessions).
- [Firebase: conectar o emulador de Authentication](https://firebase.google.com/docs/emulator-suite/connect_auth) — separação entre emuladores e serviços reais.
- [Flask: considerações de segurança](https://flask.palletsprojects.com/en/stable/web-security/) — limites de recursos e segurança HTTP.
- [Node.js: versões e suporte](https://nodejs.org/en/about/previous-releases) — manutenção do runtime usado na construção.
- [Python sqlite3: placeholders](https://docs.python.org/3/library/sqlite3.html#how-to-use-placeholders-to-bind-values-in-sql-queries) — separação entre comandos e dados.
- [pip-audit](https://github.com/pypa/pip-audit) — escopo da auditoria de dependências Python.
- Os avisos específicos de dependências estão identificados por URLs nos relatórios em `docs/evidence/`.
