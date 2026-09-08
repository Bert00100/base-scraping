# Compliance — LGPD, robots.txt, ToS

Regras transversais que se aplicam a todo o pipeline, com foco na etapa de scraping (S4), onde o risco de exposição é maior.

## Rate limiting

O plano Business remove o teto de chamadas do BaseCNPJ, então a disciplina de rate limiting se concentra inteiramente nos **sites externos**:

- 1 requisição simultânea por domínio, delay de 2-5s com jitter.
- teto de 5 páginas por domínio.
- backoff exponencial em 429/503, respeitando o header `Retry-After`.
- `User-Agent` honesto e identificável (nunca se passar por navegador comum para evadir bloqueio).
- `robots.txt` e `Crawl-delay` sempre respeitados.
- No BaseCNPJ: consultas pesadas (capital/porte) rodam em série, nunca em paralelo — a advertência de 5-30s é oficial.

## Cache

Toda resposta — do BaseCNPJ e de HTTP externo — é cacheada em disco com TTL:

- 30 dias para dado cadastral (muda pouco).
- 7 dias para conteúdo de site.

Reprocessar o pipeline não deve refazer nenhuma requisição já cacheada e válida.

## LGPD

- Dado de empresa é público.
- **Nome e e-mail de pessoa física são dado pessoal.**
- Base legal: legítimo interesse para contato B2B, com finalidade clara, opt-out e registro de origem.
- Não coletar dado de sócio além do que a Receita Federal já publica.
- Não burlar login, paywall, CAPTCHA ou `robots.txt`.
- A **proveniência por campo** (fonte, URL/rota, timestamp — ver `schemas/lead.md`) é o que sustenta essa conformidade na prática: para qualquer campo, deve ser possível responder de onde veio e quando.

## Segredos

- O token do BaseCNPJ nunca entra no repositório.
- `.env` está no `.gitignore`; `.env.example` é versionado como template.
- O `README.md` explica como gerar o token no painel do BaseCNPJ.

## Fora de escopo (v1)

LinkedIn está fora do v1: viola os Termos de Uso da plataforma, exige proxy pago, tem bloqueio agressivo, e é o maior ponto de exposição a LGPD do projeto. Só entra depois — via input manual do usuário ou API oficial do LinkedIn.
