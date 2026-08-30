# Pipeline de Inbound do Amarra — mundo como contrato

Base do desenho: **cada ligação é um contrato incompleto sendo negociado sob incerteza bilateral**. O agente não é um chatbot que "extrai intenção" — é uma parte de barganha que joga um jogo Bayesiano com informação privada nos dois lados, e o resultado é um artefato criptograficamente rastreável que pode virar recebível.

---

## 1 · Mundo como contrato

Três camadas de contrato empilhadas, todas selamento por hash:

```
mandate_hash        (fase 2)  → autoridade concedida ao agente
   └── commitment_hash  (fase 6) → acordo específico com contraparte
          └── audio_anchor  (fase 7) → prova do acordo em áudio
                 └── dossier_hash  (fase 8) → contrato completo, imutável
```

Nenhum humano assinou nada. Mas cada linha carrega o mandate_hash sob qual foi decidida, o read-back pega o consentimento explícito, e o áudio prova que a contraparte disse aquilo. Isso é **contrato executável sem intermediário jurídico** — a base da divisibilidade.

## 2 · Teoria dos jogos aplicada

O agente joga uma variante do **problema de barganha de Rubinstein** com informação incompleta:

| Elemento | Modelo | Implementação |
|---|---|---|
| Jogadores | Amarra + N transportadoras | fase 3 abre 3 pernas paralelas |
| Ação | proposta de preço $p$ | `respond_to_price(amount)` |
| Utilidade Amarra | $-p + \text{demurrage evitado}$ | break_even + escalation_band |
| Utilidade carrier | $p - \text{custo marginal}$ | (privado, desconhecido) |
| Informação privada | teto, custo marginal | mandate.max_rate NUNCA revelado |
| Sinais permitidos | "melhor oferta" (sem nome) | `may_reveal_best_price` |
| Ponto de discordância | escalação humana | escalation_triggers |

Três estratégias que o código já implementa:

**a. Cheap talk credível** — o agente pode dizer "tenho oferta melhor" quando é verdade e o mandato permite (`may_reveal_best_price=true`), mas nunca diz o valor exato. Sinaliza sem revelar. Isso é [Crawford-Sobel](https://en.wikipedia.org/wiki/Signaling_game) aplicado direto — comunicação parcial que preserva vantagem informacional.

**b. Concessões em escada previstas** — `concession_ladder = [8200, 8400, 8600, 8800]` é conhecida no momento da emissão. O agente não decide quanto ceder na hora; a política pré-computou. Isso previne o [problema do estucador](https://en.wikipedia.org/wiki/Hold-up_problem) onde o negociador pode ser pressionado a mudar o plano sob estresse.

**c. Compromisso de saída (escalation band)** — a faixa `[teto, break_even]` = `[9000, 10400]` é a zona onde **fechar seria economicamente correto E politicamente proibido**. O agente escala PORQUE já sabe a conta, não porque se confundiu. Isso é o [equilíbrio de Selten](https://en.wikipedia.org/wiki/Subgame_perfect_equilibrium) — o valor de comprometimento é maior que o valor da flexibilidade.

## 3 · Três ligações simultâneas — leilão competitivo tácito

Fase 3 disca 3 pernas em paralelo. As sessões da fase 4 **compartilham estado via `Auction.market_best`**:

```
Ruiz diz 8900   → auction.report_ask(ruiz, 8900)
Bajio negocia   → session.state.market_best = auction.market_best(exclude=bajio)
                = 8900
Agente pra Bajio: "Tenho oferta melhor. Pode chegar a 8400?"
```

Isso transforma 3 chamadas independentes em um **leilão inglês descendente implícito**. As transportadoras não sabem que estão competindo em tempo real, mas o comportamento de convergência mostra que estão. É o efeito de leilão sem a formalidade do leilão — o que permite operar num mercado (drayage) que nunca teria adotado uma bolsa.

Regra de parada: **buy-it-now** quando alguém bate o alvo. As duas perdedoras recebem uma frase de despedida cordial (fase 5) e desligam com dignidade. Não são notificadas de que perderam pra alguém — só que "para esta carga não vai dar". Preserva relacionamento pras próximas cargas.

## 4 · Ranking — quem deve receber a próxima ligação primeiro

Hoje o `carriers.json` é estático. Próxima iteração: **score dinâmico por carrier** consumindo três sinais:

### 4a · Histórico da empresa (externo)
Antes de discar, consulta:
- Registro no SICT (México) / FMCSA (EUA) → certificação em dia?
- Reviews públicas → nota agregada
- Incidentes reportados → sinistralidade
- Tempo de atividade → longevidade

Peso: 40% do score.

### 4b · Histórico próprio (interno, banco Amarra)
- Últimas N operações com esse carrier
- % de compromissos ancorados vs rejeitados na fase 7
- Desvio médio entre `agreed_rate` e `paid_rate` (não estamos capturando ainda — TODO)
- % de pickup within window
- Média de rodadas até fechar

Peso: 40% do score.

### 4c · Análise de tom de voz (em tempo real)
Deepgram nova-3 devolve `confidence` por palavra. Extensões:
- **Cadência**: pausas longas antes de dizer preço → dúvida/margem de negociação
- **Interrupções**: quem interrompe muito → posição forte percebida
- **Volume/energia** (via Deepgram `intensity` se disponível ou análise externa)
- **Palavras-âncora**: "definitivo", "não tem como", "posso ver" → margem inversa

Peso: 20% do score, aplicado como fator de correção sobre a proposta.

**Onde plugar no código:**
- Tabela nova `carrier_scores(carrier_id, dimension, score, ts)` — histórico do score
- Fase 3 `_dial_all()` ordena pernas por `score_atual` — chama primeiro os melhor rankeados
- Fase 4 `_on_price()` guarda tom em `policy_events.voice_tone` (novo)
- Fase 8 `build_dossier()` incorpora `carrier_ranking_at_close` no artefato

## 5 · Fechamento cordial (fase 5, já implementado)

Todo carrier que perdeu ouve uma frase de despedida real, não corte de linha. Templates atuais:

```python
GOODBYE_EN = ("I appreciate your time. On this shipment we'll close with "
              "another option, but let's stay in touch for the next one.")
GOODBYE_ES = ("Le agradezco el tiempo. Por esta carga vamos a cerrar con otra "
              "opción, pero seguimos en contacto para la próxima.")
GOODBYE_PT = ("Agradeço o tempo. Nesta carga vamos fechar com outra opção, "
              "mas seguimos em contato para a próxima.")
```

Vale a pena adicionar:
- Se o carrier CHEGOU perto (ficou em segundo lugar), oferecer prioridade na próxima operação da mesma rota
- Se rankeado alto mas o preço não bateu, adicionar sinal explícito de que a rejeição não é por qualidade

## 6 · Divisibilidade — o dossiê como recebível on-chain

O `dossiers` table da fase 8 tem tudo que um mercado de fatoring precisa:

```
dossier
├── mandate_hash          → prova de autoridade
├── commitments[]         → cada um com audio_anchor
├── financial             → agreed_rate + demurrage_avoided
├── operational           → carrier + performance metrics
└── timeline              → toda transição de fase
```

### Mint como recebível

Cada `operation` fechada com `outcome='booked'` vira um **NFT ERC-721** com metadata IPFS:

```json
{
  "operation_ref": "MZO-GDL-4471",
  "mandate_hash": "mdt_59d90c2b...",
  "carrier": "Fletes del Bajío",
  "amount": 8400,
  "currency": "MXN",
  "pickup_at": "2026-09-03T10:00-06:00",
  "audio_url": "ipfs://...",
  "commitments_hash": "sha256(...)",
  "signed_by": "amarra_key",
  "signed_at": "2026-09-03T14:12:00Z"
}
```

### Fracionamento como fatoring

O direito de receber o pagamento pelo transporte (a NF-e futura) é dividido em cotas **ERC-1155**:
- 100% × R$ X = principal do recebível
- Investidor compra 20% da cota, adianta 20% do valor com desconto (ex: 3%)
- Vencimento = data de pagamento contratual do embarcador

Vantagem sobre fatoring tradicional:
- **Auditabilidade em 3 segundos**: hash do mandato + áudio ancorado prova que o serviço foi realmente contratado sob autoridade
- **Divisibilidade programável**: um único recebível pode ser fatiado 100:100 sem sobrecarga administrativa
- **Precificação automática**: score do carrier (item 4) alimenta prêmio de risco on-chain

### Fluxo de estados on-chain

```
COMMITTED   → mint pending (NFT criado, mas ainda sem áudio)
VERIFIED    → mint sealed (âncora presente, hash imutável)
CLOSED      → tradable (pode ser dividido/vendido)
PAID        → burnable (embarcador pagou, cota liquida)
```

Isso NÃO precisa entrar no MVP do hackathon — mas o desenho de dados de todas as 8 fases foi feito pensando nisso. Cada compromisso é ancorado, hasheado, e amarrado ao mandato. É contrato desde o primeiro segundo.

---

## Resumo executivo

O Amarra não é "IA pra atender telefone". É:

- Um **motor de contratos** que negocia sob autoridade delegada
- Jogando **teoria dos jogos** com informação privada
- Fazendo **leilão competitivo tácito** de 3 vias
- Rankeando contrapartes por **reputação + tom em tempo real**
- Encerrando **cordialmente** independente do resultado
- Produzindo **recebíveis divisíveis** on-chain como subproduto

É factor + broker + escrow + auditor, embutido numa ligação de 3 minutos.
