---
name: base-scraping
description: Captação e enriquecimento de leads B2B brasileiros, construído sobre o BaseCNPJ. Ativa quando o usuário pede prospecção de empresas por nicho/CNAE, validação cadastral de CNPJs, ou enriquecimento de contatos (site, e-mail, redes sociais) para uma lista de empresas.
---

# base-scraping

## Quando ativar

Ative este skill quando o usuário pedir algo como:
- "me traz [nicho] em [cidade/UF]" (ex.: "dentistas em Campinas")
- "valida esses CNPJs" / "quero saber a situação cadastral dessas empresas"
- "enriquece essa lista de leads com contato"
- qualquer pedido de geração de lista de leads B2B a partir de nicho, CNAE, região ou porte

## Premissa central

O **BaseCNPJ é a espinha dorsal**: define quem é lead, valida quem continua no funil, fornece toda a camada cadastral. O scraping é periferia — só preenche o que a base cadastral não tem (site, e-mail comercial vivo, redes sociais, sinais de atividade). Se o scraping falhar, o lead continua existindo e utilizável, apenas com menos campos.

Ver `references/basecnpj.md` para rotas/erros/limites da API, `references/cnae.md` para o dicionário nicho→CNAE, `references/enriquecimento.md` para a receita de scraping, `references/compliance.md` para LGPD/robots.txt/ToS, e `schemas/lead.md` para o contrato de dados. Esses arquivos, junto com o código em `scripts/`, são autossuficientes — não há dependência de nenhum outro documento pra este skill funcionar.

## Como invocar (instruções práticas para o Claude executando o skill)

O pipeline já está implementado e testado (137 testes) em `scripts/`. Não escreva Python novo para responder um pedido de prospecção — **rode os comandos abaixo via Bash**.

1. **Diretório de trabalho:** todos os comandos abaixo assumem `cd` para a raiz deste skill (onde estão `pyproject.toml` e `scripts/`). Rode `ls pyproject.toml` para confirmar que está no lugar certo antes de tudo.
2. **Dependências:** se for a primeira vez, `uv sync` instala tudo (ambiente já costuma estar pronto). Nunca rode `pip install` direto — este projeto usa `uv`.
3. **Token:** `BASECNPJ_TOKEN` precisa estar em `.env` na raiz do skill (ver `.env.example`). Se não existir, pare e peça o token ao usuário — nunca invente um.
4. **Comando de descoberta+validação só (S0→S3), sem scraping:**
   ```
   uv run python -m scripts.pipeline_cli descobrir "<nicho>" --uf <UF> [--municipio <cidade>] [--porte ME|EPP|demais] [--cep <prefixo>] [--matriz]
   ```
5. **Comando completo (S0→S4→S6), com score e enriquecimento:**
   ```
   uv run python -m scripts.pipeline_cli prospectar "<nicho>" --uf <UF> [--municipio <cidade>] [--porte ME|EPP|demais] [--cep <prefixo>] [--matriz] [--sites-json <arquivo.json>]
   ```
   Sem `--sites-json`, os leads saem sem enriquecimento de site/e-mail (só dado cadastral) — ainda assim é uma saída válida e completa em JSON, com score. Para enriquecer, ache as URLs candidatas via busca web (uma por lead validado, usando nome fantasia/razão social + cidade como pista) e escreva um JSON `{"<cnpj>": "<url>"}` num arquivo temporário antes de rodar `prospectar` com `--sites-json`.
   **Lista própria (S2→S3→S4→S6), sem descoberta:** quando o usuário já tem uma lista de empresas (CNPJs ou nomes), escreva um JSON `[{"cnpj": "..."}, {"nome": "...", "uf": "SP", "municipio": "Campinas"}]` num arquivo temporário e rode:
   ```
   uv run python -m scripts.pipeline_cli validar-lista --arquivo <lista.json> [--situacao ativa] [--sites-json <arquivo.json>]
   ```
   Teto de 100 itens (o excedente é ignorado e aparece em `aviso`). A validação não checa CNAE. A saída é `{"total", "leads", "descartados", "nao_resolvidos"}`: explique ao usuário os `nao_resolvidos` (nome ambíguo ou sem resultado; peça o CNPJ ou mais dados) e os `descartados`.
6. **Bairro/região dentro de um município:** a API não tem filtro de bairro nomeado. Use `--cep` com um **prefixo** de CEP (ex. `0507` cobre boa parte do bairro Lapa em São Paulo capital — confirmado empiricamente, ver `references/basecnpj.md`). Se não souber o prefixo de CEP do bairro pedido, pesquise (conhecimento geral ou busca web) antes de rodar, e mostre o prefixo escolhido ao usuário. Se o usuário quiser só matrizes (uma entrada por empresa, sem filiais), adicione `--matriz`.
7. **Nicho fora do dicionário:** o comando já recusa sozinho (`erro: nicho_nao_encontrado`) e não inventa CNAE. Proponha o CNAE certo (raciocínio ou busca web), **confirme com o usuário**, e depois de confirmado adicione a entrada em `references/cnae.md` seguindo o formato das linhas existentes — assim o dicionário melhora com o uso.
8. **Saída:** sempre JSON no stdout do comando. Leia, interprete e apresente pro usuário em linguagem natural (tabela, lista, etc.) — não jogue o JSON cru na resposta final a menos que o usuário peça o dado bruto. Sempre explique ao usuário: (a) a lista `descartados` (`cnpj` + `motivo`) — leads que a descoberta achou mas não entraram, por ICP divergente ou CNPJ não encontrado; (b) o `enriquecimento.status` de cada lead que tenha o campo — `ok`, `requer_navegador` (site com JavaScript, não raspado), `match_fraco` (a URL candidata não confirmou ser a empresa; sugira outra) ou `falha` (veja `motivo`).
9. **Retomada:** rodar o mesmo comando com os mesmos parâmetros de novo é seguro e barato — o checkpoint em SQLite (`.cache/pipeline.sqlite3` por padrão) evita refazer chamadas já feitas.

## Fluxo S0 → S3 (funil cadastral, sem scraping)

Regra de ouro do skill: **os scripts não chamam LLM nenhum.** Eles entregam JSON do BaseCNPJ e texto limpo dos sites; quem interpreta é o Claude Code executando este skill.

### S0 — Definição do ICP
1. Traduzir o pedido em linguagem natural para filtros estruturados: nicho → CNAE(s) (via `references/cnae.md`), cidade → município + UF, "pequenas" → porte ME/EPP, situação cadastral = ativa por padrão.
2. Se o nicho não estiver no dicionário, propor o CNAE por raciocínio e **pedir confirmação do usuário antes de continuar**.
3. Executar `route=status` como preflight (valida token e conectividade).
4. **Mostrar a consulta montada e a contagem estimada ao usuário, e só prosseguir com confirmação explícita.** Nunca paginar a busca avançada sem essa confirmação.

### S1 — Descoberta via busca avançada
- Motor primário de descoberta (plano Business não tem teto de chamadas).
- Para cada CNAE do conjunto do nicho, paginar `route=avancada` (até 100/página) até esgotar ou atingir o teto.
- **Teto fixo de 100 leads por execução, sem override do usuário** — parar de paginar ao atingir esse número, mesmo que a API tenha mais resultados.
- Deduplicar por CNPJ na união dos resultados de todos os CNAEs.
- Consultas com filtro de capital/porte podem levar 5-30s — usar timeout generoso, nunca o padrão curto.
- Consultas pesadas rodam sequencialmente, nunca em paralelo.
- Checkpoint por página (retomar de onde parou se interrompido).

### S2 — Resolução de identidade
- Para candidatos sem CNPJ (lista do usuário, diretório, indicação): `route=sugestao` para candidatos rápidos, `route=busca` para busca textual mais ampla.
- Desempatar por UF/município — limitação da API real: `sugestao` não devolve `uf` nem `municipio`, e `busca` devolve `uf` mas não `municipio`. Na prática o desempate só funciona por UF, e só na `busca`.
- Ligado ao comando `validar-lista` (lista própria de CNPJs/nomes); a descoberta por nicho (`descobrir`/`prospectar`) não passa pelo S2.
- Match ambíguo → marcar como `nao_resolvido` e seguir. Nunca chutar.
- Dedup em cascata: CNPJ (chave forte) → domínio do site → nome normalizado + CEP.

### S3 — Validação e hidratação cadastral
- `route=cnpj` para cada lead — aqui o BaseCNPJ vira filtro de qualidade.
- Regras de descarte/flag: situação ≠ ativa → descarta; CNAE fora do ICP (nem secundário bate) → descarta; CNAE só secundário → mantém, rebaixa score; porte fora da faixa → descarta; abertura < 6 meses → flag "empresa nova"; filial quando ICP pede matriz → descarta.
- Lead com e-mail/telefone cadastral já sai **contactável sem scraping** — ganho direto.

## S4 — Enriquecimento por scraping

Implementado em `scripts/scraping/`: `site_discovery.py` (4.1, valida se uma URL candidata é mesmo o site oficial — CNPJ/razão social/nome fantasia/telefone no HTML), `contacts.py` (4.2, rastreia até 5 páginas de alto sinal e extrai e-mail/telefone/WhatsApp/redes sociais), `email_verify.py` (4.3, escada de confiança 1-5 + cruzamento com o cadastral), `context_signals.py` (4.4, e-commerce/tecnologia/indícios de equipe), e `enrich.py` que amarra tudo num `enrich(candidate_url, ...)` por lead.

**A descoberta da URL candidata em si é responsabilidade do skill (busca web), não dos scripts** — regra de ouro do projeto: os scripts entregam JSON do BaseCNPJ e texto limpo dos sites, quem pesquisa e interpreta é o Claude Code. Fluxo esperado: para cada lead validado no S3, o skill busca candidatos a site oficial (nome fantasia + cidade, ou telefone cadastral) e chama `enrich()` com a URL achada.

Sites que parecem exigir JavaScript (SPA vazia no HTML estático) são marcados `requer_navegador=true` e pulados — **Playwright fica fora do v1**.

## S6 — Scoring e saída

`scripts/pipeline/score.py` pontua cada lead validado (30 aderência ICP + 30 qualidade de contato + 20 presença digital + 20 saúde cadastral). `scripts/pipeline/export.py` monta o JSON final com `proveniencia{campo: {fonte, rota_ou_url, timestamp}}` por campo e aplica o teto de 100 leads (mantendo os de maior score se sobrar mais que isso).

`scripts/pipeline_cli.py` expõe os dois comandos de ponta a ponta:
- `descobrir <nicho> --uf UF --municipio MUN --porte PORTE [--matriz]`: S0→S3, retomável via checkpoint SQLite.
- `validar-lista --arquivo lista.json [--situacao ativa] [--sites-json arquivo.json]`: S2→S3→S4→S6 sobre uma lista de CNPJs/nomes do usuário (até 100 itens), sem CNAE.
- `prospectar <nicho> --uf UF --municipio MUN --porte PORTE [--matriz] [--sites-json arquivo.json]`: S0→S4→S6 completo (sem S5). `--sites-json` é o ponto de entrada pro skill informar as URLs candidatas já encontradas via busca web.

**S5 (rede societária) fica fora do v1.** O cliente já expõe `routes.rede()` (Passo 4), mas o pipeline não a chama; fica pra fase 2.

## Regras transversais (sempre válidas)

- **Confirmação do ICP é obrigatória** antes de qualquer paginação em massa.
- **Erros da API**: 400 → erro nosso, não repetir; 403 → token inválido/expirado, abortar com mensagem clara; 404 → lead não resolvido, seguir; 429 → backoff exponencial + `Retry-After` (não deveria ocorrer no Business); 500 → retry com backoff até 3x, depois enfileirar.
- **LinkedIn está fora do v1** — não scrapear, não contornar bloqueios.
- **Saída sempre em JSON**, no máximo **100 leads por execução**. SQLite é só checkpoint interno, nunca formato de saída para o usuário.
- **LGPD**: dado de empresa é público; nome/e-mail de pessoa física é dado pessoal — tratar com finalidade clara e proveniência registrada. Ver `references/compliance.md`.
- Token do BaseCNPJ vem de `BASECNPJ_TOKEN` (variável de ambiente) — nunca hardcoded, nunca no output para o usuário.
