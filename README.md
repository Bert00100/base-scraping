# 🧭 base-scraping

**Captação e enriquecimento de leads B2B brasileiros**, construído sobre o [BaseCNPJ](https://basecnpj.app) — roda como *skill* do [Claude Code](https://claude.com/claude-code) ou como CLI standalone.

<p>
  <img alt="Python 3.11+" src="https://img.shields.io/badge/python-3.11%2B-blue?logo=python&logoColor=white">
  <img alt="uv" src="https://img.shields.io/badge/deps-uv-6340ac">
  <img alt="Tests" src="https://img.shields.io/badge/tests-140%20passing-brightgreen?logo=pytest&logoColor=white">
  <img alt="License MIT" src="https://img.shields.io/badge/license-MIT-informational">
  <img alt="Saída" src="https://img.shields.io/badge/output-JSON-black?logo=json">
</p>

> 💬 Você pede em linguagem natural — *"óticas ativas na região da Lapa, em São Paulo capital"* — e recebe uma lista de empresas **reais**, validadas contra o cadastro oficial da Receita Federal, com contato e site verificados quando disponíveis.

```
$ uv run python -m scripts.pipeline_cli prospectar "dentista" --uf SP --municipio Campinas --porte ME

{
  "total": 8,
  "leads": [ { "razao_social": "CLINICA ODONTOLOGICA QUILES LTDA", "situacao_cadastral": "Ativa", "score": 58.0, ... } ]
}
```

---

## 📚 Sumário

- [🧠 Como funciona](#-como-funciona)
- [🔁 O pipeline, estágio por estágio](#-o-pipeline-estágio-por-estágio)
- [📦 Instalação](#-instalação)
- [🔑 Token do BaseCNPJ](#-token-do-basecnpj)
- [🚀 Como usar](#-como-usar)
- [📊 Exemplo de saída](#-exemplo-de-saída)
- [⚠️ Limites de design](#️-limites-de-design)
- [🗂️ Estrutura do projeto](#️-estrutura-do-projeto)
- [🧪 Testes](#-testes)
- [🔒 LGPD e compliance](#-lgpd-e-compliance)
- [📄 Licença](#-licença)

---

## 🧠 Como funciona

O **BaseCNPJ é a espinha dorsal** do projeto: ele define quem é lead e valida quem continua no funil. O scraping é periferia — só preenche o que o cadastro oficial não tem (site, e-mail comercial vivo, redes sociais).

```
🗂️  BaseCNPJ  =  QUEM é a empresa   (verdade cadastral, oficial, estruturada)
🌐  Scraping   =  COMO falar com ela hoje (verdade de mercado, volátil)
```

Essa separação é o que torna o resultado confiável: **se o scraping falhar num lead, o lead continua existindo e utilizável** — só com menos campos preenchidos. Nenhum dado inventado, nenhum lead perdido por causa de um site fora do ar.

```
 "dentista em Campinas"
        │
        ▼
 🔤  nicho → CNAE (references/cnae.md)         8630-5/04
        │
        ▼
 🔎  busca avançada no BaseCNPJ (S0→S1)        até 100 leads, paginado
        │
        ▼
 ✅  validação cadastral (S3)                  situação ativa, CNAE, porte...
        │
        ▼
 🌐  site oficial + e-mail + contato (S4)       scraping, opcional
        │
        ▼
 🏆  score + JSON final com proveniência (S6)
```

---

## 🔁 O pipeline, estágio por estágio

| Estágio | O que faz | Rota/fonte |
|---|---|---|
| **S0** — ICP | Traduz o pedido em filtros estruturados (nicho→CNAE, cidade, porte) | `route=status` (preflight) |
| **S1** — Descoberta | Pagina a busca avançada, teto fixo de **100 leads** por execução | `route=avancada` |
| **S2** — Resolução | Resolve candidatos sem CNPJ (comando `validar-lista`); desempate só por UF, e só na `busca` | `route=sugestao`, `route=busca` |
| **S3** — Validação | Filtra por situação cadastral, CNAE, porte; sinaliza empresa nova | `route=cnpj` |
| **S4** — Enriquecimento | Valida o site oficial, extrai contato, verifica e-mail em 5 níveis | scraping externo |
| **S6** — Score e saída | Pontua (0-100) com breakdown por dimensão, exporta JSON com proveniência | — |

> ℹ️ Não existe **S5** ativo nesta versão — a expansão por rede societária (`route=rede`) já está implementada no cliente, mas fica reservada pra uma fase futura. Ver [Limites de design](#️-limites-de-design).

---

## 📦 Instalação

Pré-requisito: [`uv`](https://docs.astral.sh/uv/getting-started/installation/).

```bash
git clone <url-do-repo> base-scraping
cd base-scraping
uv sync
```

## 🔑 Token do BaseCNPJ

1. Crie uma conta no [BaseCNPJ](https://basecnpj.app) — plano **Business** (busca avançada e rede societária exigem esse plano).
2. No painel, vá em **API Keys** e gere um token.
3. Copie o template e preencha:
   ```bash
   cp .env.example .env
   # edite .env e preencha BASECNPJ_TOKEN=<seu-token>
   ```

🔐 O token **nunca** entra no repositório — `.env` está no `.gitignore`, só `.env.example` é versionado.

---

## 🚀 Como usar

### 🧩 Opção A — como skill do Claude Code

Claude Code carrega skills a partir de um arquivo `SKILL.md` colocado numa pasta específica. **Não existe instalador automático** que baixe e configure isso sozinho só porque alguém pede "instala essa skill" — o passo que importa de verdade é copiar a pasta pro lugar certo.

1. Clone este repositório em qualquer lugar:
   ```bash
   git clone <url-do-repo> base-scraping
   ```
2. Copie a pasta pro diretório de skills do Claude Code — escolha uma das duas:

   | Escopo | Onde fica disponível | Comando |
   |---|---|---|
   | 🌍 **Pessoal** | Qualquer projeto que você abrir | `mkdir -p ~/.claude/skills && cp -r base-scraping ~/.claude/skills/base-scraping` |
   | 📁 **Só este projeto** | Só dentro do repo onde você colar | `mkdir -p .claude/skills && cp -r base-scraping .claude/skills/base-scraping` |

3. Entre na pasta copiada e instale as dependências:
   ```bash
   cd ~/.claude/skills/base-scraping   # ou .claude/skills/base-scraping, se for por projeto
   uv sync
   ```
4. Configure o token — ver [🔑 Token do BaseCNPJ](#-token-do-basecnpj).
5. Abra uma sessão **nova** do Claude Code (ou reinicie a atual) — skills são carregadas no início da sessão.
6. Teste pedindo algo como:
   > 💬 *"me traz 10 dentistas ativos em Campinas, porte ME"*

> ⚠️ **Só dizer "instala essa skill" pro Claude Code, sem mais contexto, não é confiável.** Ou você segue o passo a passo acima manualmente, ou pede explicitamente pra ele rodar os comandos (ele tem acesso a bash, então consegue clonar/copiar/`uv sync` se instruído). É uma escolha de design: esta é uma "skill simples" (clonar + copiar pasta), sem manifesto de plugin/marketplace.

### 💻 Opção B — CLI direto

Três comandos, todos sempre devolvendo **JSON** no stdout:

```bash
# 🔍 S0→S3 — descoberta + validação cadastral, sem scraping
uv run python -m scripts.pipeline_cli descobrir "dentista" --uf SP --municipio Campinas --porte ME

# 🏆 S0→S4→S6 — pipeline completo, com score e enriquecimento de contato
uv run python -m scripts.pipeline_cli prospectar "dentista" --uf SP --municipio Campinas --porte ME

# 📋 S2→S3→S4→S6 — valida uma lista própria (CNPJs ou nomes), sem descoberta
uv run python -m scripts.pipeline_cli validar-lista --arquivo lista.json
```

`lista.json` é uma lista de `{"cnpj": "..."}` ou `{"nome": "...", "uf": "SP", "municipio": "Campinas"}`, com teto de 100 itens (o excedente é ignorado e informado em `aviso`). Nomes são resolvidos por `route=sugestao`/`route=busca`; match ambíguo vai para `nao_resolvidos` (nunca chuta). A validação não checa CNAE. A saída traz `total`, `leads`, `descartados` e `nao_resolvidos`.

> ⚠️ O desempate de nomes ambíguos só funciona por **UF**, e só na `busca`: a API real não devolve `uf` na `sugestao` nem `municipio` em nenhuma das duas rotas.

**Flags disponíveis** (ambos os comandos):

| Flag | Efeito |
|---|---|
| `--uf` | UF do cadastro (ex. `SP`) |
| `--municipio` | nome do município |
| `--porte` | `ME`, `EPP` ou `demais` |
| `--arquivo` | (só em `validar-lista`) JSON com a lista de CNPJs/nomes |
| `--cep` | 📍 prefixo de CEP — filtra por **bairro/região** dentro de um município (ex. `--cep 0507` cobre a região da Lapa em São Paulo capital) |
| `--matriz` | só estabelecimentos **matriz** (exclui filiais; envia `matriz_filial=1` na busca avançada) |
| `--situacao` | (também em `validar-lista`) situação cadastral desejada (padrão: `ativa`) |
| `--db-path` | onde fica o checkpoint SQLite (padrão: `.cache/pipeline.sqlite3`) |
| `--sites-json` | (em `prospectar` e `validar-lista`) arquivo `{"cnpj": "url candidata"}` pra habilitar o enriquecimento por scraping (site, e-mail, redes sociais) |

Sem `--sites-json`, `prospectar` ainda funciona e pontua os leads — só não tem os campos de site/e-mail/redes sociais, que dependem de uma URL candidata (achada via busca web, fora do escopo do script; ver `SKILL.md`).

♻️ Rodar o mesmo comando de novo com os mesmos parâmetros é seguro e rápido: o checkpoint SQLite evita refazer chamadas já feitas.

---

## 📊 Exemplo de saída

```json
{
  "total": 8,
  "leads": [
    {
      "cnpj": "43292842000177",
      "razao_social": "CLINICA ODONTOLOGICA QUILES LTDA",
      "cnae_principal": "8630504",
      "situacao_cadastral": "Ativa",
      "endereco": { "municipio": "HOLAMBRA", "uf": "SP", "cep": "13825-000" },
      "telefone_cadastral": "(19) 3802-1183",
      "enriquecimento": { "status": "ok", "motivo": null },
      "score": 58.0,
      "score_breakdown": {
        "aderencia_icp": 30.0,
        "qualidade_contato": 8.0,
        "presenca_digital": 0.0,
        "saude_cadastral": 20.0
      },
      "proveniencia": {
        "razao_social": { "fonte": "basecnpj", "rota_ou_url": "route=cnpj", "timestamp": 1788869605.6 }
      }
    }
  ],
  "descartados": [{ "cnpj": "11111111000111", "motivo": "situacao_cadastral=04 (esperado 02)" }]
}
```

📋 `descartados` lista os leads que não entraram na saída (`cnpj` + `motivo`: ICP divergente ou CNPJ não encontrado), e `enriquecimento.status` (`ok`, `requer_navegador`, `match_fraco` ou `falha`) explica o resultado do scraping de cada lead com site candidato.

🔎 Todo campo carrega sua origem em `proveniencia` — pra qualquer dado, dá pra responder **"de onde veio isso e quando"**.

---

## ⚠️ Limites de design

| Limite | Detalhe |
|---|---|
| 🔢 Teto de leads | **100 por execução**, fixo — a busca avançada para de paginar ao chegar nesse número |
| 📤 Formato de saída | **Sempre JSON.** SQLite é só checkpoint interno, nunca é a saída final |
| 🧩 Resolução de identidade (S2) | Só no `validar-lista`; `descobrir`/`prospectar` não passam por ela. Desempate de nome só por UF, e só na `busca` (a API não devolve município) |
| 🕸️ Rede societária (S5) | Cliente já expõe `routes.rede()`, mas o pipeline não a chama — fica pra uma fase 2 |
| 🎭 Sites com JavaScript | Marcados (`requer_navegador=true`) e pulados — sem Playwright nesta versão |
| 🚫 LinkedIn | Fora de escopo — viola os Termos de Uso da plataforma e é o maior risco de LGPD do projeto |

---

## 🗂️ Estrutura do projeto

```
base-scraping/
├── SKILL.md                    # 🧭 instruções completas pra rodar como skill do Claude Code
├── .env.example                 # 🔑 BASECNPJ_TOKEN=
├── references/
│   ├── basecnpj.md              # 📡 rotas, filtros, erros e limites confirmados da API
│   ├── cnae.md                  # 📖 dicionário nicho → CNAE
│   ├── enriquecimento.md        # 🌐 receita do scraping (site, contato, e-mail, contexto)
│   └── compliance.md            # 🔒 LGPD, robots.txt, rate limiting
├── schemas/
│   └── lead.md                  # 🧾 contrato de dados do Lead
├── scripts/
│   ├── basecnpj/                # 📡 cliente da API (cache, retry, mapa de erros)
│   ├── pipeline/                # 🔁 descoberta, validação, score, export
│   ├── scraping/                # 🌐 site oficial, contatos, verificação de e-mail
│   ├── utils.py                 # 🧰 helpers compartilhados (only_digits)
│   ├── cli.py                   # 🛠️ CLI de teste manual das 6 rotas do BaseCNPJ
│   └── pipeline_cli.py          # 🚀 CLI principal: descobrir / prospectar / validar-lista
└── tests/                       # 🧪 suíte de testes (pytest), incluindo test_pipeline_cli.py (CLI ponta a ponta com respx)
```

---

## 🧪 Testes

```bash
uv run --group dev pytest
```

✅ **140 testes**, cobrindo o cliente da API, o pipeline de descoberta/validação e o scraping — sem nenhuma chamada de rede real (tudo mockado com `respx`).

---

## 🔒 LGPD e compliance

Dado de empresa é público; nome e e-mail de pessoa física são dados pessoais, tratados com finalidade clara (contato B2B) e proveniência registrada por campo. Rate limiting rígido nos sites externos:

- 1️⃣ requisição simultânea por domínio
- 🤖 `robots.txt`/`Crawl-delay` sempre respeitados
- 5️⃣ páginas de teto por domínio
- 🕐 cache de 7 dias pra não bater duas vezes no mesmo site

Detalhes completos em [`references/compliance.md`](./references/compliance.md).

---

## 📄 Licença

MIT — ver [`LICENSE`](./LICENSE).
