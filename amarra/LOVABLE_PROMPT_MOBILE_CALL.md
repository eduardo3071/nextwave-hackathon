# Amarra Dashboard — botão de discar + banner de chamada entrante (mobile)

**Não reconstrua o app.** Adicione o comportamento abaixo ao painel que já existe. A viewport de referência é **mobile (375–430px)** rodando em navegador desktop — pense em layout de app, não de site.

---

## 0 · Padrão de callback — o jurado NÃO precisa ter crédito internacional

Como o número Twilio é US (`+18126253258`) e conseguir número BR leva dias na ANATEL, o modelo de teste é **callback**: quem quer experimentar entra o próprio telefone num input, clica um botão, e o Amarra liga pra ele. Custo zero pro visitante (receber chamada é grátis no BR).

Isso vira o hero pattern do painel: **input + botão** em vez de um número decorado pra ligar.

```
┌─────────────────────────────────────┐
│  Experimente o Amarra ao vivo       │
│                                     │
│  Seu telefone (E.164):              │
│  ┌───────────────────────────────┐  │
│  │ +55                          │  │
│  └───────────────────────────────┘  │
│                                     │
│  [ 📞 Me liga em 3 segundos ]      │
│                                     │
│  A chamada é gratuita pra você.     │
│  A Twilio paga, ~$0.03/min.         │
└─────────────────────────────────────┘
```

Valida E.164 no input (regex `^\+[1-9]\d{7,14}$`), botão desabilitado até estar válido. Persist o número em `localStorage` (`amarra:my_phone`) pra o próximo teste já vir preenchido.

**Ao clicar:** POST em `${VITE_BACKEND_URL}/demo/call-me` com body `{"to": "+55...", "dry_run": false}`. Antes disso, opcionalmente chama com `dry_run: true` pra confirmar que o backend está pronto.

Se o backend retornar `warnings`, mostra em toast âmbar sem bloquear (ex: "mandato não emitido — o agente vai atender mas não vai negociar").

## 1 · Novo BOTÃO no topo do painel: "📞 Me liga"

Grande, chamativo, sempre visível no topo da coluna principal. Estilo pill button, altura mínima 56px (touch-friendly).

**Texto:** `📞 Me liga` (em português) — pode alternar pra `📞 Call me` se `AGENT_LANG=en`.

**Sub-texto pequeno abaixo:** `A Twilio vai discar pro seu celular · sem gasto internacional`

**Comportamento:**

Clique dispara:

```ts
const res = await fetch(`${import.meta.env.VITE_BACKEND_URL}/demo/call-me`, {
  method: "POST",
  headers: { "content-type": "application/json" },
  body: JSON.stringify({}),   // usa SUPERVISOR_PHONE do backend
});
const { call_sid, to, error } = await res.json();
```

Se `error`: toast vermelho com o texto do erro (ex: `21215: PERMISSÃO GEOGRÁFICA`).

Se sucesso: **imediatamente** troca o botão por um card:

```
┌────────────────────────────────────┐
│  📞 Discando pra +5511934843013…   │
│  ⚡ atende quando tocar             │
│  ▓▓▓▓▓▓▓▓▓░░░░ (bar animada)       │
│                                    │
│  [ ⏹ cancelar ]                    │
└────────────────────────────────────┘
```

O card fica visível enquanto `calls` (filtrado por `call_sid == call_sid retornado`) mostra status `dialing` ou `ringing`. Quando vira `live`, o card sobe pra `🟢 conectado` e depois some (ou colapsa) e o resto do painel (transcript, phase rail, etc.) toma conta da tela.

Se o status virar `no-answer`, `failed`, `busy` ou `canceled`, mostra em vermelho `❌ chamada falhou: {status}` e volta o botão.

**Botão `⏹ cancelar`**: hoje não temos endpoint pra isso — omita se não vai implementar. Ou pode fazer POST `${VITE_BACKEND_URL}/phase3/abort/{auction_id}` se houver leilão associado (é um botão diferente por natureza).

---

## 2 · Banner de CHAMADA ENTRANTE (aparece SOZINHO quando alguém liga pro número Twilio)

Assine a tabela `calls` via Realtime, filtro `direction = 'inbound'` e status recente (`dialing`/`ringing`/`live`).

Quando um novo `calls` aparece com `direction='inbound'`, mostra um banner FIXO no topo da tela (sobrepõe o botão de "Me liga"), animado, com pulso e som opcional:

```
╔════════════════════════════════════╗
║  📞 CHAMADA ENTRANDO               ║
║  De: {calls.phone}                 ║
║  Toca há: {segundos}s              ║
║                                    ║
║  ⏳ agente entrando em segundos    ║
╚════════════════════════════════════╝
```

Cor de fundo pulsando entre verde e verde-escuro (frequência ~1Hz, tipo um telefone tocando).

Quando `calls.status` vira `live` (atendido pelo agente do backend), muda o banner pra:

```
┌────────────────────────────────────┐
│  🟢 EM CHAMADA · {phone}           │
│  Duração: 0:23                     │
└────────────────────────────────────┘
```

E abre o resto da tela (transcript rolando, phase rail atualizando).

Quando a chamada termina (`status='done'`), o banner some com fade e mostra toast:
`✓ chamada com {phone} encerrada. Duração: {mm:ss}`.

---

## 3 · Diferença visual crítica: outbound-demo vs inbound

Duas cores/ícones:

| `calls.direction` | Cor primária | Ícone | Legenda no card |
|---|---|---|---|
| `inbound` | 🟢 verde | 📞⬇️ | "Alguém está te ligando" |
| `outbound_demo` | 🔵 azul | 📞⬆️ | "Você mandou a Twilio ligar pra você" |
| `outbound` (leilão real) | 🟣 roxo | 📞→ | "Amarra discando pra transportadora" |

Isso está no campo `calls.direction` que o backend já popula:
- `/twiml/inbound` sem query param → `direction='inbound'` (alguém ligou pro seu Twilio)
- `/twiml/inbound?demo=1` → `direction='outbound_demo'` (o botão "Me liga" disparou)
- `/phase3/open` → `direction='outbound'` (Amarra dialing carriers do leilão)

---

## 4 · Layout mobile (375–430px viewport)

**Container principal**: `max-width: 430px`, `margin: 0 auto`. O resto da tela desktop fica cinza escuro (indicando que o app é "mobile em navegador").

**Empilhamento vertical** (nada de colunas lado a lado — é mobile):

```
┌────────── 430px max ──────────┐
│  TOP BAR (altura ~80px)       │
│  ├ ref MZO-GDL-4471           │
│  └ ⏱ 28h 40m (countdown)      │
├───────────────────────────────┤
│  🟩 CALL BANNER (se ativo)    │  ← seção 2
├───────────────────────────────┤
│  📞 [ Me liga ]  (botão)      │  ← seção 1
├───────────────────────────────┤
│  PHASE RAIL (horizontal scroll)│
│  detected→…→closed             │
├───────────────────────────────┤
│  ATIVIDADE (tabs)              │
│  [ Transcript ] [ Compromissos ]│
│  [ Comparação ] [ Escalação ]  │
│                                │
│  (conteúdo da tab, scroll)    │
├───────────────────────────────┤
│  BOTTOM NAV (fixa)             │
│  [ 🏠 ] [ 📊 dossiê ] [ ⚙ ]   │
└───────────────────────────────┘
```

Sem sidebar. Sem 3 colunas. **Tabs** pra alternar entre visões que na versão desktop ficariam lado a lado. Scroll vertical natural.

**Tipografia mobile:**
- countdown: `text-6xl` (não 8xl como no desktop)
- números: `tabular-nums` sempre
- botões touch: min-height 56px, padding 16px 24px
- espaçamento generoso entre seções (16-24px)

---

## 5 · Empty states (mobile)

Sem operação ativa:
```
┌───────────────────────────────┐
│                               │
│         📦                    │
│                               │
│  Nenhuma operação             │
│  Aguardando descarga do       │
│  primeiro contêiner           │
│                               │
│  ────────────────────────     │
│                               │
│  📞 [ Testar chamada ]        │  ← botão maior aqui
│                               │
└───────────────────────────────┘
```

Uma vez que a operação chega, layout normal aparece.

---

## 6 · Micro-detalhes

- **Vibrate na chamada entrante** (mobile): `navigator.vibrate([200, 100, 200])` no evento de novo `calls.direction='inbound'` (só funciona em mobile real; desktop ignora silenciosamente)
- **Som opcional**: `<audio autoplay>` com um ring curto quando `inbound` novo aparece (~2s). Silêncio no `outbound_demo` (você não precisa de som pra saber que você mesmo clicou o botão).
- **Não polling**: como no resto do painel, TUDO via Realtime do Supabase.

---

## 7 · Ordem sugerida pra você implementar

1. Adiciona o botão "Me liga" com o `fetch` — testa que dispara a chamada
2. Faz o card de "discando" com estado local (não precisa de Realtime ainda)
3. Adiciona subscription pra `calls` e reage a mudanças de status (dialing→live→done)
4. Adiciona o banner de chamada entrante com pulso + cor diferenciada
5. Aplica o layout mobile (max-width, empilha verticalmente, tabs)
6. (opcional) vibrate + som

Não precisa fazer tudo de uma vez — o backend já suporta o botão AGORA. Uma vez que o Lovable renderiza o botão e faz o POST, você já pode testar sem sair do painel.
