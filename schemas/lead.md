# Contrato de dados — o Lead

Cada campo carrega sua origem, o que permite rastrear proveniência ponta a ponta (exigido pela seção LGPD de `references/compliance.md`).

| Campo | Origem (abstrato) | Origem (campo real na API, `route=cnpj`) | Obrigatório |
|---|---|---|---|
| `cnpj` | BaseCNPJ | `cnpj_basico` + `cnpj_completo_formatado` | sim (chave) |
| `razao_social`, `nome_fantasia` | `route=cnpj` | `razao_social`, `estabelecimento_matriz.nome_fantasia` | sim |
| `cnae_principal`, `cnaes_secundarios` | `route=cnpj` | `estabelecimento_matriz.cnae_principal_codigo`, (secundários em `estabelecimento_matriz`) | sim |
| `situacao_cadastral`, `data_abertura`, `porte`, `capital_social` | `route=cnpj` | `estabelecimento_matriz.situacao_cadastral`/`situacao_descricao`, `estabelecimento_matriz.data_inicio_atividade`, `porte_descricao`, `capital_social` | sim |
| `natureza_juridica`, `matriz_filial` | `route=cnpj` | `natureza_juridica_descricao`, `estabelecimentos[].matriz_filial` | sim |
| `endereco` (logradouro, município, UF, CEP) | `route=cnpj` | `estabelecimento_matriz.{logradouro,municipio,uf,cep}` | sim |
| `telefone_cadastral`, `email_cadastral` | `route=cnpj` | `estabelecimento_matriz.email` (telefone: campo equivalente na matriz) | não |
| `socios[]` (nome, qualificação) | `route=cnpj` | quadro societário do payload de `route=cnpj` | não |
| `grupo_economico[]`, `orange_flags[]` | `route=rede` (**fase 2 — fora do v1**) | — | não |
| `site` | S4.1 (descoberta do site oficial) | — | não |
| `emails[]` (valor + nível 1-5+) | S4.2/4.3 (descoberta + verificação) | — | não |
| `telefones[]`, `whatsapp`, `redes_sociais{}` | S4 | — | não |
| `contatos[]` (nome, cargo, email) | S4.2 | — | não |
| `score`, `score_breakdown{}` | S6 (scoring) | — | sim |
| `proveniencia{campo: {fonte, rota_ou_url, timestamp}}` | todo o pipeline | — | sim |

Ver `scripts/basecnpj/models.py` (`CNPJDetalhe`, `EstabelecimentoMatriz`, `AvancadaItem`) para os modelos Pydantic reais, e `references/basecnpj.md` para o levantamento completo do formato observado.

## Scoring (S6) — pesos por dimensão

| Dimensão | Peso | Fonte |
|---|---|---|
| aderência ao ICP (CNAE principal vs. secundário, porte, região) | 30 | BaseCNPJ |
| qualidade do contato (nível do e-mail, telefone, WhatsApp) | 30 | cadastral + scraping |
| presença digital (site validado, redes ativas) | 20 | scraping |
| saúde cadastral (situação, tempo de casa, capital) | 20 | BaseCNPJ |

## Saída

**Sempre JSON**, com proveniência por campo (fonte, URL/rota, timestamp), no máximo **100 leads por execução** — decisão fechada, seção 11 do `ARCTETURE.md`. SQLite é usado só como storage interno de checkpoint do pipeline (retomar de onde parou), nunca como formato de saída para o usuário.
