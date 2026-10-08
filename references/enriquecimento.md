# Enriquecimento por scraping (S4)

Única etapa do pipeline fora do BaseCNPJ. Roda **depois** do S3 (validação cadastral) — só entra em cena para leads já validados, e usa dado cadastral como pista e como fonte de verificação cruzada. Quatro sub-etapas.

## 4.1 — Descoberta do site oficial

- Usa telefone/e-mail cadastral e nome fantasia (vindos do S3) como pista de busca web.
- **Valida o match**: o site precisa mencionar o CNPJ, a razão social, o nome fantasia ou o telefone.
- Sem confirmação, é match fraco → descarta o site em vez de gravar lixo.
- O CNPJ no rodapé é o sinal mais forte que existe — e só está disponível porque o S3 rodou antes.

## 4.2 — Descoberta de contatos

- Rastreia páginas de alto sinal: `/contato`, `/sobre`, `/equipe`, `/quem-somos`, rodapé da home.
- Teto rígido de **5 páginas por domínio**.
- Extrai: e-mails, telefones, WhatsApp, redes sociais, nomes e cargos de decisores.

## 4.3 — Verificação de e-mail

Escada de confiança, sem custo e sem SMTP handshake:

| Nível | Checagem | Confiança |
|---|---|---|
| 1 | sintaxe válida (RFC) | baixa |
| 2 | domínio não é descartável nem provedor genérico | média |
| 3 | domínio tem registro MX | boa |
| 4 | e-mail publicado no site oficial confirmado | alta |
| 5 | e-mail nominal (`nome@empresa.com.br`) e não genérico | alta + nominal |
| + | e-mail bate com o cadastral do BaseCNPJ | **máxima — dupla fonte** |

O nível "+" (cruzamento com o e-mail cadastral do BaseCNPJ) é o diferencial da ferramenta: combina dado oficial e dado de mercado.

## 4.4 — Sinais de contexto

Redes sociais ativas, e-commerce, tecnologia do site, indícios de tamanho de equipe.

## Disciplina de execução

Ver `compliance.md` para as regras completas de rate limiting, cache e LGPD que se aplicam a toda esta etapa. Resumo operacional:

- 1 requisição simultânea por domínio, delay de 2-5s com jitter.
- teto de 5 páginas por domínio (repetido acima porque é a regra mais violável).
- backoff exponencial em 429/503, respeitando `Retry-After`.
- `User-Agent` honesto e identificável.
- `robots.txt` e `Crawl-delay` respeitados.
- cache em disco, TTL de 7 dias para conteúdo de site.

## Fora de escopo no v1

LinkedIn não entra no S4 — viola Termos de Uso, exige proxy pago, tem bloqueio agressivo e é o maior ponto de exposição a LGPD do projeto. Só entra depois, via input manual ou API oficial.
