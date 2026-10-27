# Análise de dependências (SCA) — configuração e resultado

A ferramenta configurada é **npm audit**, executada por um comando único na raiz do projeto. A análise compara as versões resolvidas nos dois lockfiles npm com os avisos conhecidos consultados pelo npm. É SCA, não análise estática da lógica da aplicação.

## 1. Configuração no repositório

| Arquivo | Função |
| --- | --- |
| [package.json](../package.json) | Define `npm run security:sca` e `npm run test:sca` |
| [scripts/security-sca.mjs](../scripts/security-sca.mjs) | Audita raiz e frontend, valida a conclusão da ferramenta, grava resultados e retorna erro quando necessário |
| [scripts/tests/security-sca.test.mjs](../scripts/tests/security-sca.test.mjs) | Verifica que vulnerabilidades, saída inválida, timeout e falhas da ferramenta não sejam interpretados como aprovação |
| [.github/workflows/sca.yml](../.github/workflows/sca.yml) | Prepara execução automática em push, pull request, acionamento manual e semanalmente |

## 2. Executar localmente

Com Node.js 24 e npm disponíveis, na raiz:

```powershell
npm run test:sca
npm run security:sca
```

No PowerShell, se a política local bloquear o atalho `npm.ps1`, use `npm.cmd` nos mesmos comandos. Não é necessário instalar dependências para executar esse scanner: o script usa apenas módulos nativos do Node, e a consulta usa os lockfiles. É necessário acesso à rede para consultar o registro configurado no npm.

Para cada diretório, o comando aplicado é:

```text
npm audit --json --package-lock-only --ignore-scripts --audit-level=low --include=prod --include=dev --include=optional --include=peer --fetch-retries=1 --fetch-timeout=30000
```

`--package-lock-only` seleciona o inventário dos lockfiles, sem depender de `node_modules`; os tipos de dependência são incluídos explicitamente. `--ignore-scripts` evita scripts de lifecycle. A consulta não instala pacotes, não usa `audit fix` e não altera versões ou lockfiles. O npm consulta o registro com informações do inventário, como nomes e versões dos pacotes, conforme a [documentação oficial do npm audit](https://docs.npmjs.com/cli/v11/commands/npm-audit/).

O limite é `low`: avisos classificados como Low, Moderate, High ou Critical fazem a verificação falhar. O runner também considera qualquer achado informado no total, mesmo que um código de saída inconsistente da ferramenta sugerisse aprovação.

| Código do comando | Significado | Ação |
| --- | --- | --- |
| `0` | As duas consultas terminaram com relatórios válidos e sem avisos conhecidos | Anexar os resultados, considerando os limites do escopo |
| `1` | Pelo menos um relatório contém vulnerabilidades | Revisar pacote, caminho da dependência, versão corrigida e compatibilidade antes de atualizar |
| `2` | Ferramenta/rede, lockfile ausente, relatório inválido ou outra falha de conclusão | Corrigir a execução e repetir; não apresentar como zero vulnerabilidades |

Os dois escopos são processados mesmo se o primeiro falhar. Um relatório de erro contém mensagem genérica e contagens não avaliadas; stderr bruto não é publicado. Cada consulta tem timeout de 90 segundos. O scanner é executado por `npm run`, que fornece o caminho do CLI; subprocessos são iniciados diretamente por Node, sem montar comandos de shell.

## 3. Resultados anexados

Execução local em **27/10/2026**, com Node **v24.19.0** e npm **11.17.0**:

| Escopo | Lockfile | Total informado pelo npm | Resultado | Saída da ferramenta |
| --- | --- | --- | --- | --- |
| Ferramentas da raiz/Firebase CLI | `package-lock.json` | 632 dependências | Zero avisos conhecidos | `0` |
| Aplicação frontend e ferramentas | `frontend/package-lock.json` | 421 dependências | Zero avisos conhecidos | `0` |

As contagens por tipo do npm podem se sobrepor; não some produção, desenvolvimento e opcionais como categorias exclusivas. Os totais dos dois projetos também não representam pacotes únicos entre projetos.

Evidências reais geradas pelo comando:

- [sca-summary.json](evidence/sca-summary.json): ferramenta/versões, início/fim em UTC, comando, escopos, SHA-256 dos lockfiles, contagens e conclusão.
- [sca-npm-root.json](evidence/sca-npm-root.json): relatório JSON da raiz.
- [sca-npm-frontend.json](evidence/sca-npm-frontend.json): relatório JSON do frontend.
- [sca-execution.txt](evidence/sca-execution.txt): resumo textual da execução, com os códigos de saída.

As quatro verificações de `npm run test:sca` passaram: resultado limpo, bloqueio por achados, erros/saída incompleta e consistência/agregação dos resultados. São testes da política do scanner e não se somam aos testes históricos do backend para aparentar nova execução da aplicação.

Repetir o comando atualiza os quatro arquivos desta etapa, preservando os relatórios históricos com outros nomes. As bases de avisos podem mudar, mesmo com o mesmo lockfile. Os hashes registrados identificam os arquivos examinados, não uma revisão do controle de versão.

## 4. Automação preparada

O workflow usa Node 24, permissões de leitura do repositório e não persiste credenciais do checkout. Não usa segredos adicionais nem precisa de um nome de conta/repositório fixo. Ele executa os testes da política e a mesma análise usada localmente.

Ao terminar, tenta anexar os resultados como artifact `sca-reports`, inclusive quando a análise falha, com retenção de 30 dias. Os arquivos da execução ficam no diretório temporário do job, usando `SCA_OUTPUT_DIR`; isso evita anexar um relatório antigo do repositório caso a execução não tenha chegado à análise. Não há correção automática nem supressão de falha com `continue-on-error`.

O agendamento está definido para segunda-feira às **10:20 UTC (07:20 em America/Fortaleza)**. O workflow está apenas preparado no repositório: **não foi publicado nem executado no GitHub nesta etapa**. A validação anexada é a execução local. Após incluir os arquivos na conta de destino, confirme se GitHub Actions está habilitado e revise o artifact da primeira execução nessa plataforma.

## 5. Cobertura e limites

Esta configuração atende ao requisito de ao menos uma ferramenta SAST ou SCA com execução anexada. A cobertura automatizada aqui é dos **dois inventários npm**, incluindo desenvolvimento, opcionais e peers. O alcance não inclui dependências Python, pacotes de sistema das imagens Docker, segredos, comportamento do código ou configuração de serviços.

Os relatórios Python anteriores permanecem como evidências separadas; não foram executados por este comando. A presença de um aviso não comprova automaticamente exploração na aplicação; ausência de avisos não comprova inexistência de falhas desconhecidas. SCA complementa revisão de código, testes e controles operacionais.

Para achados futuros, avaliar o aviso e a dependência que o introduz, atualizar/remover o componente compatível, repetir os testes pertinentes e executar a SCA novamente. Não usar `npm audit fix --force` indiscriminadamente nem apenas ocultar avisos. O resultado consolidado está também em [findings.md](evidence/findings.md).
