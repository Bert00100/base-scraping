# base-scraping

Captação e enriquecimento de leads B2B brasileiros, construído **sobre o [BaseCNPJ](https://basecnpj.app)**, pra rodar como uma *skill* do [Claude Code](https://claude.com/claude-code) — ou como CLI standalone.

Você pede em linguagem natural ("dentistas ativos em Campinas, porte ME") e recebe uma lista de empresas reais, validadas contra o cadastro oficial da Receita Federal, com contato e site verificados quando disponíveis.

## Como funciona, em uma frase

O **BaseCNPJ é a espinha dorsal**: ele define quem é lead e valida quem continua no funil. O scraping é periferia — só preenche o que o cadastro não tem (site, e-mail comercial vivo, redes sociais). Se o scraping falhar, o lead continua existindo e utilizável, só que com menos campos.

```
nicho ("dentista") ──▶ CNAE (8630-5/04) ──▶ busca avançada no BaseCNPJ ──▶ leads validados
                                                                              │
                                                          site oficial + e-mail/contato (scraping)
                                                                              │
                                                                    score + JSON final
```

## Instalação

Pré-requisito: [`uv`](https://docs.astral.sh/uv/getting-started/installation/).

```bash
git clone <url-do-repo> base-scraping
cd base-scraping
uv sync
```

### Token do BaseCNPJ

1. Crie uma conta no [BaseCNPJ](https://basecnpj.app) (plano Business — busca avançada e rede societária exigem esse plano).
2. No painel, vá em **API Keys** e gere um token.
3. Copie o template e preencha:
   ```bash
   cp .env.example .env
   # edite .env e preencha BASECNPJ_TOKEN=<seu-token>
   ```

O token nunca deve entrar no repositório — `.env` está no `.gitignore`, só `.env.example` é versionado.

## Como usar

### Opção A — como skill do Claude Code

Claude Code carrega skills a partir de um arquivo `SKILL.md` colocado numa pasta específica. **Não existe instalador automático** que baixe e configure isso sozinho só porque alguém pede "instala essa skill" — o passo que importa de verdade é copiar a pasta pro lugar certo. Passo a passo:

1. Clone este repositório em qualquer lugar:
   ```bash
   git clone <url-do-repo> base-scraping
   ```
2. Copie a pasta pro diretório de skills do Claude Code — escolha uma das duas:
   - **Pessoal** (fica disponível em qualquer projeto que você abrir):
     ```bash
     mkdir -p ~/.claude/skills
     cp -r base-scraping ~/.claude/skills/base-scraping
     ```
   - **Só neste projeto** (dentro do repo onde você quer usar a skill):
     ```bash
     mkdir -p .claude/skills
     cp -r base-scraping .claude/skills/base-scraping
     ```
3. Entre na pasta copiada e instale as dependências:
   ```bash
   cd ~/.claude/skills/base-scraping   # ou .claude/skills/base-scraping, se for por projeto
   uv sync
   ```
4. Configure o token (ver [Token do BaseCNPJ](#token-do-basecnpj) acima):
   ```bash
   cp .env.example .env
   # edite .env e preencha BASECNPJ_TOKEN=<seu-token>
   ```
5. Abra uma sessão nova do Claude Code (ou reinicie a atual) — skills são carregadas no início da sessão.
6. Teste pedindo algo como: *"me traz 10 dentistas ativos em Campinas, porte ME"*.

**Se você só disser "instala essa skill" pro Claude Code, sem mais nada:** ele não vai fazer isso sozinho de forma confiável — precisa ou seguir esse passo a passo manualmente, ou você pedir explicitamente pra ele rodar os comandos acima (ele tem acesso a bash, então consegue clonar, copiar e rodar `uv sync` se você instruir isso). O motivo é de design: esta skill foi feita como "skill simples" (clonar + copiar pasta), sem manifesto de plugin — um instalador de fato exigiria empacotar como plugin com sistema de marketplace, que é um escopo diferente deste projeto.

### Opção B — CLI direto

Dois comandos, ambos sempre devolvendo **JSON** no stdout:

```bash
# S0→S3: descoberta + validação cadastral, sem scraping
uv run python -m scripts.pipeline_cli descobrir "dentista" --uf SP --municipio Campinas --porte ME

# S0→S4→S6: pipeline completo, com score e enriquecimento de contato
uv run python -m scripts.pipeline_cli prospectar "dentista" --uf SP --municipio Campinas --porte ME
```

**Opções disponíveis** (ambos os comandos):

| Flag | Efeito |
|---|---|
| `--uf` | UF do cadastro (ex. `SP`) |
| `--municipio` | nome do município |
| `--porte` | `ME`, `EPP` ou `demais` |
| `--cep` | prefixo de CEP — usado pra filtrar por bairro/região dentro de um município (ex. `--cep 0507` cobre a região da Lapa em São Paulo capital) |
| `--situacao` | situação cadastral desejada (padrão: `ativa`) |
| `--db-path` | onde fica o checkpoint SQLite (padrão: `.cache/pipeline.sqlite3`) |
| `--sites-json` | (só em `prospectar`) arquivo `{"cnpj": "url candidata"}` pra habilitar o enriquecimento por scraping (site, e-mail, redes sociais) |

Sem `--sites-json`, `prospectar` ainda funciona e pontua os leads — só não tem os campos de site/e-mail/redes sociais, que dependem de uma URL candidata (achada via busca web, fora do escopo do script; ver `SKILL.md`).

Rodar o mesmo comando de novo com os mesmos parâmetros é seguro e rápido: o checkpoint SQLite evita refazer chamadas já feitas.

### Exemplo de saída

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
  ]
}
```

Todo campo carrega sua origem em `proveniencia` — pra qualquer dado, dá pra responder "de onde veio isso e quando".

## Limites de design

- **Teto de 100 leads por execução**, fixo — a busca avançada para de paginar ao chegar nesse número.
- **Saída sempre em JSON.** SQLite é usado só como checkpoint interno do pipeline, nunca é a saída final.
- **Rede societária e Playwright ficam fora desta versão** — o cliente já expõe a rota `rede`, mas o pipeline não a chama; sites que exigem JavaScript pra renderizar são marcados e pulados.
- **LinkedIn está fora de escopo** — viola os Termos de Uso da plataforma e é o maior risco de LGPD do projeto.

## Estrutura do projeto

```
base-scraping/
├── SKILL.md                    # instruções completas pra rodar como skill do Claude Code
├── .env.example                 # BASECNPJ_TOKEN=
├── references/
│   ├── basecnpj.md              # rotas, filtros, erros e limites confirmados da API
│   ├── cnae.md                  # dicionário nicho → CNAE
│   ├── enriquecimento.md        # receita do scraping (site, contato, e-mail, contexto)
│   └── compliance.md            # LGPD, robots.txt, rate limiting
├── schemas/
│   └── lead.md                  # contrato de dados do Lead
├── scripts/
│   ├── basecnpj/                # cliente da API (cache, retry, mapa de erros)
│   ├── pipeline/                # descoberta, validação, score, export
│   ├── scraping/                # site oficial, contatos, verificação de e-mail
│   ├── cli.py                   # CLI de teste manual das 6 rotas do BaseCNPJ
│   └── pipeline_cli.py          # CLI principal: descobrir / prospectar
└── tests/                       # suíte de testes (pytest)
```

## Testes

```bash
uv run pytest
```

A suíte cobre o cliente da API, o pipeline de descoberta/validação, o scraping e o scoring — sem chamada de rede real (tudo mockado com `respx`).

## LGPD e compliance

Dado de empresa é público; nome e e-mail de pessoa física são dados pessoais, tratados com finalidade clara (contato B2B) e proveniência registrada por campo. Rate limiting rígido nos sites externos (1 requisição simultânea por domínio, `robots.txt` respeitado, teto de 5 páginas por domínio). Detalhes em `references/compliance.md`.

## Licença

MIT — ver [`LICENSE`](./LICENSE).
