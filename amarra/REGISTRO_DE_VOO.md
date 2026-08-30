# Registro de Voo · Amarra

Log narrativo das decisões de arquitetura, produto e infraestrutura tomadas ao longo da construção do Amarra para o NextWave Hackathon 2026 · Desafio 04 "The Agent on the Line".

Cada entrada tem: **decisão**, **alternativas consideradas**, **por quê**, **consequência** (o que essa decisão obrigou depois).

---

## D01 · Escolher "compromisso" como átomo do sistema, não "chamada"

**Alternativas:**
1. Modelar como transcrição + extração posterior via LLM
2. Modelar como intents + entidades detectadas por chamada
3. Modelar como **compromissos verificados** que só existem se ancorados no áudio ✓

**Decisão:** #3.

**Por quê:** O enunciado é literal — "commitments, not transcripts". Uma transcrição é auditoria fraca porque o LLM pode alucinar; um compromisso ancorado no áudio + confirmado por read-back + amarrado ao mandato tem propriedades de contrato. Isso vira o átomo do produto e também abre porta pra recebível on-chain no futuro (design em INBOUND_PIPELINE.md).

**Consequência:** Toda a fase 6 (read-back) e fase 7 (âncora) existem por causa disso. Sem o átomo certo, seriam features cosméticas; com ele, viraram invariantes de sistema.

---

## D02 · 8 fases + 4 desvios como espinha explícita, com guardas no advance()

**Alternativas:**
1. Estados livres, cada endpoint muda o que quiser
2. Máquina de estados leve (só valida transições permitidas)
3. Máquina de estados **com guardas semânticas** que codificam invariantes ✓

**Decisão:** #3.

**Por quê:** Se `verified` só exige transição válida, a fase pode avançar sem compromisso ancorado. Se `closed` só exige transição válida, a operação fecha sem recap enviado. Se as guardas consultam o banco (`SELECT count(*) FROM commitments WHERE anchor_state='anchored'` antes de permitir `verified`), o painel LITERALMENTE não pode mentir.

**Consequência:** `phases.py::advance()` chama `_guard()` que faz queries no banco. Isso é lento em comparação com máquinas puras (~50ms por transição vs microssegundos), mas o custo vale — o pitch pode dizer "cada fase codifica uma invariante" e mostrar SQL.

---

## D03 · Policy engine puro (sem LLM) — o modelo NUNCA fala número que ele inventou

**Alternativas:**
1. Deixar o modelo negociar livremente e conferir depois
2. Modelo negocia, política "revisa" no fim
3. Modelo **chama tool** `respond_to_price`, política **decide**, agente **fala a frase exata** devolvida pela política, sem passar pelo modelo de novo ✓

**Decisão:** #3 + um gate de segurança (`gate_text`) que bloqueia qualquer valor não pré-aprovado que vaze.

**Por quê:** Existe benchmark publicado de 2026 mostrando que modelos de fronteira violam mandato mesmo quando negociam bem — raciocínio econômico e cumprimento de restrição são desacoplados no modelo. Portanto a restrição não pode morar no modelo. Isso é a razão do policy_events ter 800+ testes em pytest com invariante "nunca ALLOW acima do teto".

**Consequência:** Toda a lógica de contra-oferta é pré-computada na fase 2 (`concession_ladder`). O modelo é um cliente burro do policy engine.

---

## D04 · Mandato como HASH canônico (identidade da autoridade)

**Alternativas:**
1. Mandato é só uma linha em `mandates` com target/max
2. Mandato tem versionamento simples (`updated_at`)
3. Mandato é **hash de forma canônica** que aparece em cada `policy_events` e `commitments` ✓

**Decisão:** #3.

**Por quê:** O enunciado pergunta "under which mandate" (R3 do R4). Se alguém muda o teto no meio da operação, o hash muda e a trilha auditável mostra exatamente sob qual autoridade cada decisão foi tomada. É a mesma ideia de commit hash do git, mas pra autoridade delegada.

**Consequência:** Fase 2 tem `canonicalize()` + `mandate_hash()`. Cada `policy_events` e `commitments` carrega `mandate_hash text`. Rota `/phase2/verify/{op_id}` recalcula o hash a partir do canonical guardado — divergência prova adulteração.

---

## D05 · Escalation band pré-computada (a faixa "bom e proibido")

**Alternativas:**
1. Escalar sempre que `ask > max_rate` (comportamento binário)
2. Deixar o modelo decidir quando escalar
3. **Pré-computar** na fase 2 a faixa `[max_rate, break_even]` como "escalation_band". Se `ask` cai nela, escala; se acima do break-even, recusa e segue. ✓

**Decisão:** #3.

**Por quê:** Entre o teto e o ponto de equilíbrio existe uma zona onde fechar é **economicamente correto E politicamente proibido**. O agente escala porque o sistema NOMEOU essa faixa antes da primeira ligação. Isso separa "o agente se confundiu" de "o sistema previu esta situação". No caso do pitch, é o 9200 pesos da Transportes Ruiz — Amarra recusa porque teto=9000, mas escala porque break_even=10400 (economicamente melhor que perder 1 dia de demurrage).

**Consequência:** `escalation_triggers` do mandato inclui `within_escalation_band`. Card de escalação renderiza a conta lado a lado (opção on-time vs late) com "excede mandato em X pesos" — o humano decide em 9 segundos.

---

## D06 · Lock de reserva ATÔMICO no Postgres (não asyncio.Lock)

**Alternativas:**
1. `asyncio.Lock` em processo (funciona com 1 worker)
2. Lock via Redis / distributed lock
3. **`UPDATE ... WHERE reserved_by IS NULL` dentro de `SELECT FOR UPDATE`** — Postgres ✓

**Decisão:** #3.

**Por quê:** A primeira versão usava asyncio.Lock. Cai na primeira pergunta séria do júri: "e se subirem 2 workers?". Postgres já tem primitiva atômica pra isso (row lock). Zero infra extra, e o teto é reverificado NO POSTGRES — cinto e suspensórios além do policy engine.

**Consequência:** Fase 5 tem função stored `try_reserve_auction(op_id, call_id, amount, reason)` que faz o UPDATE atômico. Cliente Python é 3 linhas. Ganha ponto na defesa técnica: "vale com 1 worker ou com 10".

---

## D07 · Backend nunca fala com o frontend — só escreve no Supabase

**Alternativas:**
1. WebSocket próprio do backend pro painel
2. Server-Sent Events (SSE)
3. **Supabase Realtime pub/sub** — backend só escreve, painel só lê ✓

**Decisão:** #3.

**Por quê:** Elimina toda a complexidade de: manter conexões vivas do painel, autenticação de WebSocket, CORS pro WS, reconexão. Supabase Realtime é WebSocket já resolvido. Backend fica statelesss no que toca ao painel.

**Consequência:** RLS aberto pra leitura anônima (é demo). Painel usa `supabase.channel().on('postgres_changes', ...)` pra 13 tabelas. Prompt do Lovable diz literalmente "Assine, não pergunte".

---

## D08 · ConversationRelay em vez de Media Streams (Twilio)

**Alternativas:**
1. Twilio Media Streams: stream de áudio bruto, você resolve STT/TTS/VAD/barge-in
2. **Twilio ConversationRelay: STT + TTS + VAD + barge-in prontos, você só escreve o WebSocket de conversa** ✓

**Decisão:** #2.

**Por quê:** Media Streams economiza 2 semanas se você precisa controle profundo do áudio (background music, mixer custom, etc). Não é o caso — o Amarra só precisa "receber transcrição, responder texto, sobreviver interrupção". ConversationRelay entrega isso e mais: `interruptible="speech"`, `reportInputDuringAgentSpeech`, Deepgram nova-3 nativo, ElevenLabs TTS.

**Consequência:** Toda a fase 4 é 300 linhas de Python. Se fosse Media Streams, seriam ~2000 linhas + integração com Deepgram streaming + gerenciar filas de áudio.

---

## D09 · TwiML App + Conference (não `<Dial><Number>` direto)

**Alternativas:**
1. `<Dial><Number>` direto — mais simples pra 1-to-1
2. **`<Dial><Conference>` + injeção de perna do agente** ✓

**Decisão:** #2.

**Por quê:** Sem Conference, não dá pra injetar um humano depois sem cortar o áudio. E injetar humano sem cortar áudio é o requisito **R6** do enunciado (escalação mid-call). Se a chamada não está numa Conference desde o segundo zero, a escalação exige derrubar+reconectar (perde contexto, perde robustez).

**Consequência:** Toda chamada nasce dentro de `<Conference>`. Escalação usa `join_human(coaching=True)` — supervisor entra MUDO, agente ouve, quando `coaching=False` o humano fala com todos. Ninguém desligou. R6 é uma linha de código, não uma arquitetura.

---

## D10 · Deepgram nova-3 pós-chamada (não em real time durante a call)

**Alternativas:**
1. Deepgram nova-3 em real-time durante a chamada, ancorar palavras conforme chegam
2. **Gravar a conference inteira; ancorar DEPOIS via Deepgram batch** ✓

**Decisão:** #2.

**Por quê:** ConversationRelay já dá transcrição pra tomada de decisão em tempo real (via Twilio's own Deepgram config). Precisar do TIMESTAMP POR PALAVRA pra ancoragem só faz sentido pós-chamada, quando você tem o compromisso completo pra buscar no áudio. Rodar 2 pipelines de Deepgram (real-time + batch) seria caro sem ganho.

**Consequência:** Fase 7 baixa a gravação Twilio, envia bytes pro Deepgram, recebe words com start/end, casa cada `commitments.quote` no índice. `number_variants` gera "ocho mil cuatrocientos" quando o quote é "8400" e vice-versa — sem isso, ancoragem falha em números falados.

---

## D11 · Read-back token (o "sim" preso a valores específicos)

**Alternativas:**
1. Aceitar "sim" da contraparte como confirmação genérica
2. Aceitar "sim" só se dito em janela temporal específica
3. **Hash dos slots ("read_back_token"); se qualquer valor mudar, o token muda e o "sim" antigo vira `superseded`** ✓

**Decisão:** #3.

**Por quê:** Contraparte fala "sim, 8500, quinta 10h" e depois muda pra "9000, sexta". O "sim" do primeiro não vale pro segundo. Token = hash dos valores no momento da fala; se qualquer valor mudou, token muda, `outcome='superseded'`, agente relê. E `classify_response` é conservador — silêncio, "aham", hedge nunca viram sim.

**Consequência:** Fase 6 tem PHRASES + classify_response + read_back_token + 28 testes cobrindo cada variante de sim/não/ambíguo. Trial by fire ("agree and then change") tem resposta pré-testada.

---

## D12 · Fases 1-8 como MÓDULOS separados, não god-class

**Alternativas:**
1. Um único `amarra_engine.py` com todas as fases
2. **`phase1_detected.py` até `phase8_closed.py` + `phase_disruption.py`**, cada um com router próprio ✓

**Decisão:** #2.

**Por quê:** Facilita defesa técnica ("me mostra a fase 5") + facilita test isolation (cada fase tem seu test_phaseN.py). Também mapeia 1:1 com o rail visual do painel, o que reduz cognitive load pra jurado seguir a demo.

**Consequência:** 9 arquivos `phase*.py`, cada um ~200-400 linhas. main.py só faz orquestração. Custo: importar entre fases exige cuidado (fase 4 importa fase 5 e 6, mas fase 5 e 6 não podem importar fase 4). Circular imports resolvidos com late-import dentro de funções.

---

## D13 · Auto-reset da operação em `/demo/dial-market`

**Alternativas:**
1. Cada disparo precisa reset manual via SQL
2. Endpoint separado `/demo/reset`
3. **`/demo/dial-market` faz auto-reset a menos que passe `reset: false`** ✓

**Decisão:** #3.

**Por quê:** Sem isso, cada teste do botão "ABRIR MERCADO" no painel bate no admit() com "operação está em 'negotiating'". Botão do painel vira um-clique-e-funciona. Trade-off: se você QUERIA preservar a operação anterior (pra auditoria), tem que passar `reset:false` explícito.

**Consequência:** `_demo_reset()` apaga `calls`, `auctions`, `phase_events` da operação e devolve pra `mandate_issued`. Preserva `mandates` (hash não muda). Endpoint `/demo/reset` também exposto pra reset explícito.

---

## D14 · Idioma default = inglês (AGENT_LANG=en), não espanhol

**Alternativas:**
1. Espanhol default (o caso é Manzanillo, mercado da Nauta é LatAm)
2. **Inglês default; pt/es como fallbacks quando o carrier explicitamente fala** ✓

**Decisão:** #2.

**Por quê:** Jurado do NextWave é internacional (Y.uno, Yuno). Inglês é lingua franca. Bônus B2 do enunciado permite mistura de idiomas — implementamos com `_switch_language` que sente troca de idioma via Deepgram e reconfigura TTS on-the-fly. Se o jurado quiser testar em espanhol, o agente acompanha.

**Consequência:** Toda frase da política tem 3 branches (en/es/pt). Testes em espanhol preservados via `Mandate.lang` default "es" (só a sessão runtime usa "en" via env var). PHRASES dict + `_lang_key` helper.

---

## D15 · SMS DESCARTADO — email é canal único do R3a

**Alternativas:**
1. SMS via Twilio (custa ~$0.03/msg BR)
2. SMS + email
3. **Email only** ✓

**Decisão:** #3, tomada em 2026-08-30 tarde.

**Por quê:** SMS US→BR é frequentemente filtrado por carriers brasileiros (Vivo, Claro, TIM). Testamos, funcionou pros primeiros 3 mensagens curtas mas falhou pro recap real (multi-segmento com acentos). WhatsApp Business API seria alternativa robusta mas exige aprovação Meta (dias). Email via Resend funciona globalmente sem restrições e o enunciado diz "(SMS/e-mail)" com barra — um satisfaz.

**Consequência:** `send_recap_sms` deletada. Endpoint `/demo/test-sms` fora. Codebase mais limpo pro pitch — não precisa explicar "por que SMS falha". Trade-off: perdemos redundância de canal. Mitigação: `RECAP_TO` + `RECAP_CC` comma-separated pra múltiplos emails (jurados incluídos).

---

## D16 · Ngrok em vez de deploy real (Fly.io, Railway)

**Alternativas:**
1. Deploy real em Fly.io / Railway (backend 24/7)
2. **Ngrok + laptop local** ✓

**Decisão:** #2.

**Por quê:** Ngrok reserved domain (grátis) resolve o problema de "público HTTPS pra Twilio + Lovable falarem com o backend" em 5 minutos. Deploy real levaria 30-40 min de configuração + primeira falha. Trade-off: laptop precisa estar ligado durante a demo. Aceitável pra o formato do hackathon.

**Consequência:** `PUBLIC_HOST=clique-lukewarm-frail.ngrok-free.dev` no `.env`. Script `start_all.ps1` sobe uvicorn + ngrok num clique. Se um dia migrar pra deploy real, só troca `PUBLIC_HOST` — código não muda.

---

## D17 · Auto-commit + push depois de cada mudança que passa nos testes

**Alternativas:**
1. Perguntar antes de cada commit
2. Commitar mudanças pequenas, perguntar antes de mudanças grandes
3. **Auto-commit + push depois de `pytest` verde** ✓

**Decisão:** #3, formalizada em 2026-08-30 tarde depois do usuário confirmar preferência.

**Por quê:** Velocidade — hackathon é velocidade acima de elegância. Cada round-trip "pergunto antes?" custa 30s. Salvamos em memória permanente do assistente pra próximas sessões honrarem.

**Consequência:** Formato padrão de commit: título curto imperativo + body com contexto + "N tests still green" + Co-Authored-By. Push direto pro `main` (branch principal, mesma que Lovable usa). Exceção: mudança grande de schema, refactor de API pública, ou coisa que afeta pitch — ainda pergunto antes.

---

## D18 · Jurados como config, não hard-code

**Alternativas:**
1. Hard-code os telefones dos jurados no código
2. Env var por jurado
3. **`judges.json` com roster estruturado + endpoint `/demo/call-judge/{id}`** ✓

**Decisão:** #3.

**Por quê:** Jurados podem mudar até o dia do pitch. Config em arquivo separado é editar sem tocar código. Endpoint faz o padrão callback (Twilio disca eles, zero custo pro lado deles). `RECAP_CC` no `.env` faz email do recap chegar automaticamente na caixa deles.

**Consequência:** `judges.json` tem Walter (BR) e Denis Dvoretskikh (AR). Denis é AR — flag documentado que exige Geo Permission ARG no Twilio antes do primeiro `/demo/call-judge/denis`.

---

## D19 · Frontend mobile-first (430px) mesmo rodando em desktop

**Alternativas:**
1. Layout desktop tradicional (3 colunas lado a lado)
2. Responsive (mesma UI, layouts adaptativos)
3. **Mobile-first fixo (max-width 430px, tabs no lugar de colunas)** ✓

**Decisão:** #3.

**Por quê:** Painel de operação é consumo mid-call, não navegação. Mobile impõe hierarquia visual clara — countdown gigante, phase rail, uma tab por visão. Também facilita o jurado abrir no próprio celular durante a demo.

**Consequência:** Prompts Lovable (`LOVABLE_PROMPT_MOBILE_CALL.md`, `LOVABLE_PROMPT_OUTBOUND_BUTTON.md`) descrevem bottom-sheet-style, botões pill de 56px, tabs em vez de sidebar. Lovable implementou (commits do bot `gpt-engineer-app`).

---

## D20 · Renegociação automática pro runner-up (fase disruption)

**Alternativas:**
1. Quando `report_disruption` dispara, só marca a operação como disrupted e para
2. Marca disrupted + escala pro humano decidir o que fazer
3. **Marca disrupted + auto-dispara callback pro segundo colocado do último leilão (dentro do teto)** ✓

**Decisão:** #3.

**Por quê:** Resultado #3 do enunciado exige renegociação sem passar do mandato. Se aguardar humano, perdemos tempo do free time (o relógio!). Runner-up já foi negociado, o `auction_quotes` tem o preço final — se ainda cabe no teto, é a decisão certa em automático. Se não cabe → escala.

**Consequência:** `phase_disruption.py::renegotiate_with_runner_up` lê `auction_quotes`, filtra `winner=false` + `final_ask <= max_rate`, ordena por preço, disca o vencedor via `tw.dial_counterparty`. Se não houver viável, chama `_escalate_no_runner_up`.

---

## D21 · Dossiê como artefato único auditável (JSON aninhado)

**Alternativas:**
1. Múltiplas queries que o jurado precisa cruzar
2. View SQL agregada
3. **Row em `dossiers` com blob JSON contendo tudo: financial, operational, timeline, commitments, comparison, escalations, mandate_hash, headline** ✓

**Decisão:** #3.

**Por quê:** R4 do enunciado é "auditable trail". Se o jurado abre uma URL e vê tudo, o R4 está literalmente respondido. Formato JSON permite renderizar de qualquer forma no painel + consumir via API + subir on-chain como IPFS metadata futuramente.

**Consequência:** Fase 8 tem `build_dossier()` que agrega 6 fontes. Frontend rota `/dossier/:ref`. Endpoint `/phase8/dossier/{op_id}`. Recap R3a é a mesma coisa em texto humano (email).

---

## D22 · Coreografia de 20 min com endpoint único `/demo/scenario/full`

**Alternativas:**
1. Cada fase é curl separado, jurado vê você digitar
2. Script bash que sequencia curls
3. **`POST /demo/scenario/full`** que faz reset → issue mandate → open market e retorna plano ✓

**Decisão:** #3.

**Por quê:** Pitch de 7 min não pode ter "espera, deixa eu digitar o próximo curl". Botão único. `demo_scenario.py` faz polling do `/demo/scenario/status/{ref}` e mostra scorecard 7/6 verde em tempo real.

**Consequência:** `demo_scenario.py` + `OBJECTIVES_TO_RESULTS.md` + `SYNC_STATUS.md` documentam a coreografia. Rodar durante o pitch: 1 comando kickoff + 1 comando close, o resto acontece via chamadas reais.

---

## D23 · CORS permissivo (`allow_origins=["*"]`) no backend

**Alternativas:**
1. Whitelist explícita dos origens (Lovable, localhost)
2. **Wildcard `*` com `allow_credentials=False`** ✓

**Decisão:** #2.

**Por quê:** Hackathon-mode. Wildcard é seguro quando não há cookies (credentials=False força isso). O painel Lovable + `curl` de dev + browser preview do desenvolvedor todos passam sem drama. Trade-off: qualquer site externo pode chamar o backend. Aceitável pra demo, seria restringido em produção.

**Consequência:** `main.py` tem 8 linhas de `app.add_middleware(CORSMiddleware, ...)`. Rota de escapatória: se um jurado abrir o painel do celular dele, funciona sem config extra.

---

## D24 · Workflow git — auto-commit direto no `main` (sem PR)

**Alternativas:**
1. `main` protegido, tudo via PR revisada
2. Branch `dev` + PR pra `main` a cada bloco
3. **Direto no `main`, sem branch intermediária** ✓

**Decisão:** #3, depois de tentar #2 e verificar que Lovable também escreve no `main` direto.

**Por quê:** Lovable auto-commita no `main`. Se nós usamos `dev`, cada PR precisa rebasar com o Lovable. Overhead alto pra hackathon. Direto no `main` sincroniza com o Lovable naturalmente.

**Consequência:** Branch `dev` deletada. Todos os pushes vão pra `main`. Confia no `pytest` verde como gate.

---

## Métricas do voo

- **34 commits** entre o início e o momento deste registro
- **9 arquivos `phase*.py`** na espinha (~2500 linhas)
- **9 arquivos SQL** de migração (~500 linhas)
- **951 testes** pytest, ~15 segundos total
- **13 endpoints REST** demo + 9 fase + 6 Twilio webhooks + 1 WebSocket
- **13 tabelas** Supabase + Realtime + Storage
- **5 prompts Lovable** consumidos (`LOVABLE_PROMPT_*.md`)
- **Zero dependências pesadas fora da stack** — sem Redis, RabbitMQ, K8s, Elasticsearch

## Última decisão · quando parar

**D25 — Parar de fazer feature, focar em provar ao vivo:** de agora até a demo, cada minuto vai pra rodar `dial_market` real + call inbound real + `close` real + gerar o dossiê. Cada objetivo que fica ✅ na visão de status é mais valioso que qualquer feature nova. O software está pronto; falta usar.

---

_Registro compilado em 2026-08-30, tarde. Versão viva — cada decisão futura vira D26, D27..._
