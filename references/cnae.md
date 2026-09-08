# Dicionário de nichos comerciais → CNAE

Não é a tabela CNAE inteira (mais de 1.300 subclasses — inviável e desnecessário). É um dicionário dos nichos que aparecem em prospecção B2B real, cada um com: termos que o usuário usaria, CNAEs correspondentes (principal e vizinhos), e a largura de prefixo recomendada.

## Largura de prefixo — quando usar cada uma

| Largura | Exemplo | Alcance | Quando usar |
|---|---|---|---|
| Subclasse (7 dígitos) | `8630504` | estreito e preciso | nicho bem definido |
| Classe (5 dígitos) | `86305` | médio | nicho com variações |
| Grupo (4 dígitos) | `4520` | amplo | categoria geral |

**Regra de negócio**: o skill sempre propõe a subclasse mais precisa, mostra ao usuário quantas empresas cada largura retorna, e deixa ele escolher entre precisão e volume antes de rodar o pipeline inteiro.

## Nichos com múltiplos CNAEs

Muitos nichos reais não cabem em um CNAE só (ex.: "oficina mecânica" cobre mecânica, elétrica, funilaria e alinhamento). Nesses casos o skill trata o nicho como **conjunto de CNAEs**: executa uma consulta por CNAE e deduplica por CNPJ na união dos resultados.

## CNAE secundário

O detalhe do CNPJ (`route=cnpj`) traz os CNAEs secundários. Empresa cujo CNAE **principal** é o do nicho → lead forte. Empresa que tem o CNAE apenas como **secundário** → lead fraco (atividade existe, mas não é o core do negócio) — isso alimenta o score, não descarta.

## Dicionário

| Nicho (como o usuário fala) | CNAEs | Prefixo sugerido |
|---|---|---|
| dentista, clínica odontológica | 8630-5/04 | `8630504` |
| oficina mecânica, auto center | 4520-0/01 a /05 | `4520` |
| contabilidade, escritório contábil | 6920-6/01, 6920-6/02 | `69206` |
| loja de roupas, boutique | 4781-4/00 | `4781400` |
| restaurante, lanchonete | 5611-2/01 a /05 | `56112` |
| salão de beleza, barbearia | 9602-5/01, 9602-5/02 | `96025` |
| academia, box de crossfit | 9313-1/00 | `9313100` |
| pet shop, banho e tosa | 4789-0/04, 9609-2/08 | dois CNAEs distintos |
| advocacia | 6911-7/01 | `6911701` |
| padaria | 4721-1/02, 1091-1/02 | dois CNAEs distintos |
| ótica, ótica de óculos, loja de óculos | 4774-1/00 | `4774100` |

> Cobertura atual: 11 nichos (10 do ponto de partida extraído do `ARCTETURE.md` + "ótica", confirmado contra a API real em 2026-09-08 e adicionado após uso). A meta de longo prazo é 60-80 entradas cobrindo os nichos mais comuns de prospecção B2B real.

## Nicho fora do dicionário

Quando o nicho pedido não estiver aqui, o Claude propõe o CNAE por raciocínio e **pede confirmação do usuário antes de rodar**. A entrada confirmada deve ser adicionada a este arquivo, que assim melhora com o uso.
