# BaseCNPJ API — rotas, filtros, erros, limites

Referência operacional da API BaseCNPJ para o skill `base-scraping`. Plano contratado: **Business** (chamadas ilimitadas, todas as rotas liberadas).

## Autenticação e transporte

- Header `Authorization: Bearer SEU_TOKEN`. Token gerado no painel da conta, seção API Keys.
- Todas as rotas são **GET**. POST/PUT retornam 405.
- Resposta sempre JSON.

## Envelope de resposta

- Sucesso: `{ "ok": true, "data": { ... } }`
- Erro: `{ "ok": false, "error": { "code": "...", "message": "..." } }`

## Rotas disponíveis

| # | Rota | Path | Auth | Plano |
|---|---|---|---|---|
| 1 | Status | `/api/v1/?route=status` | não | público |
| 2 | Busca textual | `/api/v1/?route=busca&q=TERMO&page=1&per_page=15` | sim | Pro+ |
| 3 | Detalhe do CNPJ | `/api/v1/?route=cnpj&cnpj=XXXXXXXX` | sim | Pro+ |
| 4 | Autocomplete | `/api/v1/?route=sugestao&q=TERMO` | sim | Pro+ |
| 5 | Busca avançada | `/api/v1/?route=avancada&<filtros>` | sim | Pro/Business |
| 6 | Rede societária | `/api/v1/?route=rede&cnpj=XXX&depth=2` | sim | **Business** |

## Filtros da busca avançada (até 12 combináveis)

UF, município, CNAE (prefixo de até 7 dígitos), porte (ME/EPP/demais), situação cadastral, faixa de capital social (mín/máx), nome de sócio, CEP, matriz/filial. Paginação de 1 a 100 por página.

### Parâmetros confirmados da busca avançada (descoberto empiricamente, Passo 4)

O doc original só descrevia os *conceitos* de filtro, sem os nomes de query string. Testado contra a API real (`https://basecnpj.app/api/v1/?route=avancada`, base CNAE `8630504`/UF `SP` como controle) — parâmetros desconhecidos são **silenciosamente ignorados** pela API (não dá erro 400), então cada nome abaixo foi confirmado checando se `total` mudava e se o parâmetro aparecia ecoado em `filtros_aplicados` na resposta:

| Parâmetro | Exemplo | Observação |
|---|---|---|
| `uf` | `uf=SP` | confirmado no doc original |
| `municipio` | `municipio=Campinas` | nome da cidade, não código IBGE |
| `cnae` | `cnae=8630504` | prefixo de até 7 dígitos |
| `situacao` | `situacao=02` | **código numérico**, não o rótulo (`ativa` não funciona). Códigos observados: `02`=Ativa, `04`=Inapta, `08`=Baixada — lista completa não confirmada |
| `porte` | `porte=01` | **código numérico**, não a sigla (`ME` não funciona). Códigos observados: `01`=Micro empresa, `05`=Demais — lista completa não confirmada |
| `capital_min`, `capital_max` | `capital_min=100000` | faixa de capital social |
| `socio` | `socio=Maria` | busca por nome de sócio (`nome_socio` **não** funciona) |
| `cep` | `cep=11900000` ou `cep=0507` (prefixo) | aceita CEP completo **ou prefixo** — confirmado em 2026-09-08: `cep=0507` retorna só resultados cujos CEPs começam com esse prefixo. É o jeito prático de filtrar por bairro/região dentro de um município, já que não existe filtro de bairro nomeado (ex. região da Lapa em São Paulo capital ≈ prefixo `0507`/`0508`) |
| `matriz_filial` | `matriz_filial=1` | `1`=matriz (valor para filial ainda não testado) |
| `page`, `per_page` | `page=1&per_page=15` | paginação, confirmado no doc original |

**Atenção:** como parâmetros errados não geram erro, um nome de filtro incorreto no código falha silenciosamente (a busca simplesmente ignora aquele filtro) — sempre validar mudança em `filtros_aplicados`/`total` ao adicionar um filtro novo, nunca assumir que "não deu erro" significa "funcionou".

**Teto de leads do pipeline (não é limite da API):** a API não impõe teto de resultados no plano Business, mas o pipeline (`scripts/pipeline/discovery.py`, Passo 5) para de paginar `route=avancada` ao atingir **100 leads por execução** — decisão fechada na seção 11 do `ARCTETURE.md`, sem override de CLI.

## Dados retornados pelo detalhe de CNPJ (`route=cnpj`)

CNPJ básico e formatado, razão social, nome fantasia, capital social, porte, CNAE principal + secundários, natureza jurídica, regime tributário, situação cadastral (ativa/suspensa/inapta/baixada), endereço completo com CEP, e-mail, telefones, quadro societário com qualificação, filiais.

**Formato real observado (Passo 4):** os nomes de campo da resposta real são mais granulares do que este resumo sugere — ex. `cnpj_basico`, `cnpj_completo_formatado`, dados de matriz aninhados em `estabelecimento_matriz{situacao_cadastral, situacao_descricao, cnae_principal_codigo, email, uf, municipio, cep, logradouro, ...}`, filiais em `estabelecimentos[]`, opção pelo Simples/MEI em `simples{}`. Ver `scripts/basecnpj/models.py` (`CNPJDetalhe`) para o subconjunto de campos que o pipeline usa — o modelo aceita campos extra (`extra="allow"`) porque a resposta tem mais dado do que o mapeado.

## Rede societária (`route=rede`, exclusiva Business)

Grafo em formato Cytoscape.js ligando empresas e sócios. Limites anti-explosão: fan-out máximo de 20, teto de 1000 nós. Inclui detecção de *orange flags*. Usar `depth=2` como padrão.

## Advertência de performance (oficial)

Consultas avançadas que usam filtro de **capital** ou **porte** podem levar de **5 a 30 segundos**. Isso é requisito de arquitetura, não detalhe — usar timeout de leitura generoso (60s) nessas rotas, nunca o padrão de 10s. Consultas pesadas rodam sequencialmente, nunca em paralelo.

## Mapa de erros

| HTTP | Códigos | Tratamento |
|---|---|---|
| 400 | `missing_q`, `invalid_cnpj`, `no_filters` | erro de programação nosso — falhar alto, não repetir |
| 403 | `forbidden`, `plan_required` | token inválido/expirado — abortar execução com mensagem clara |
| 404 | `not_found`, `unknown_route` | CNPJ inexistente → marcar lead como não resolvido, seguir |
| 405 | `method_not_allowed` | nunca deve acontecer (só usamos GET) |
| 429 | `rate_limit` | backoff exponencial + `Retry-After`; no Business não deve ocorrer |
| 500 | `server_error` | retry com backoff, até 3 tentativas, depois enfileirar para depois |

## Impacto do plano Business no desenho

Sem teto de chamadas, a busca avançada é o **motor primário de descoberta**: dá para paginar CNAEs inteiros, consultar o detalhe completo de todo lead antes de decidir se vale scraping, e usar a rede societária para expandir a base. O gargalo do projeto deixa de ser a API e passa a ser exclusivamente o scraping dos sites externos — onde o rate limiting precisa ser rígido (ver `compliance.md`).

## Mapa de estágios do pipeline

| Estágio | Rota usada | Papel |
|---|---|---|
| S0 — ICP | `status` | preflight: valida token, conectividade e versão |
| S1 — Descoberta | `avancada` | motor primário: CNAE + geografia + porte + situação, paginado |
| S2 — Resolução | `busca`, `sugestao` | resolve candidatos sem CNPJ |
| S3 — Validação | `cnpj` | detalhe completo: situação, CNAEs, sócios, filiais, contatos cadastrais |
| S4 — Enriquecimento | — | scraping externo, fora do BaseCNPJ |
| S5 — Expansão | `rede` | grafo societário: empresas irmãs do mesmo grupo |
| S6 — Score/saída | — | consolidação |
