# Wire do botão "Abrir Mercado (3)" — mobile

O botão que já existe embaixo do painel (`ABRIR MERCADO (3)`) deve disparar a fase 3 completa: 3 chamadas paralelas pros carriers pré-configurados no backend.

## Comportamento

**Clique →** POST em `${VITE_BACKEND_URL}/demo/dial-market` (body vazio `{}`).

O endpoint faz por baixo:
1. Reseta a operação `MZO-GDL-4471` de volta pra `mandate_issued` (limpa auction/calls anteriores)
2. Lê os 3 carriers do `carriers.json` server-side
3. Dispara `POST /phase3/open` internamente
4. Retorna `{auction_id, carriers, legs_planned, legs_budget, soft_deadline_s, hard_deadline_s, warnings}`

## UX (mobile, 430px)

### Antes do clique
Botão pill grande, altura 56px, no rodapé fixo ou logo abaixo do phase rail:

```
┌─────────────────────────────────────┐
│  🎯  ABRIR MERCADO (3)              │
│  vai discar pros 3 carriers · ~$0.20│
└─────────────────────────────────────┘
```

Só habilitado quando `operations.phase` está em `mandate_issued`. Nos outros estados fica esmaecido com tooltip: "operação em {phase} — reseta primeiro".

### Bottom sheet de confirmação (mobile-friendly, não modal centralizado)

Sobe do rodapé quando clica. Ocupa ~60% da altura:

```
┌─────────────────────────────────────┐
│      ═══                            │
│                                     │
│  Vai discar simultaneamente:        │
│                                     │
│  📞 Fletes del Bajío                │
│     +55 11 9593-6644                │
│                                     │
│  📞 Transportes Ruiz                │
│     +55 11 9970-3489                │
│                                     │
│  📞 Autolíneas MX                   │
│     +55 11 9348-4301                │
│                                     │
│  ⚠️ 3 celulares vão tocar em ~2s.   │
│     Se algum não atender, o          │
│     watchdog fecha em 45s.          │
│                                     │
│  [ Cancelar ]   [ 🎯 Discar ]      │
└─────────────────────────────────────┘
```

Se você quiser mais controle: adicione um botão pequeno "Editar carriers" no topo da bottom sheet — abre uma tela onde o usuário edita nome/telefone dos 3 e salva num override em localStorage; o body do POST passa a incluir `carriers: [...]`.

### Depois do clique em "Discar"

1. Fecha a bottom sheet
2. Toast rápido: `🎯 Discando 3 carriers em paralelo...`
3. Phase rail avança sozinho pra `market_open` (via Realtime — o backend escreve, o painel reage)
4. As 3 colunas de call (que já existem) começam a se preencher:
   - Header vira `dialing` com ponto pulsante
   - Depois `live` (verde) quando cada perna atende
   - Ou `failed` (vermelho) se der `no-answer` ou erro Twilio (mostrar `dial_error` no tooltip)
5. Transcript rola em cada coluna conforme utterances chegam
6. Policy strip abaixo do transcript se preenche
7. **Momento wow #1:** quando alguém bate o alvo → coluna vencedora fica destacada + fase avança pra `reserved` → `committed`; as outras duas fazem fade + carimbam `released` + ouve-se a frase de despedida cordial
8. **Momento wow #2** (se pintar): banda de escalação → card de escalação vermelho pulsando aparece com a conta lado a lado + botões Aprovar/Recusar

### Se der erro

Toast vermelho com o corpo do JSON de erro:
- `admissão`: falta de mandato, R7 quebra, orçamento estourado, janela terminou
- `Twilio`: 21215 (geo), 10004 (concurrency), 21212 (número não é seu)

## Erros esperados e como tratar

| Status | Corpo | Ação UX |
|---|---|---|
| 200 | `{auction_id, carriers: 3, ...}` | fecha sheet, toast success |
| 422 | `{error: "R7 exige..."}` | inline warning "precisa 3 carriers" |
| 422 | `{error: "orçamento de pernas estourado"}` | mostra sugestão "aumente TWILIO_CONCURRENCY no .env do backend" |
| 400 | `{error: "21215: PERMISSÃO..."}` | mostra "habilita Brasil no Twilio Geo Permissions" |
| 500 | `{error: "carriers.json inválido"}` | tem que corrigir no repo |

## Diferenciação visual com o botão "Me liga"

| Botão | Ação | Cor primária | Ícone |
|---|---|---|---|
| **📞 Me liga** | 1 chamada, Twilio → você | azul (informativo) | 📞 |
| **🎯 Abrir Mercado (3)** | 3 chamadas, Twilio → carriers | verde (produtivo) | 🎯 |

Ambos são triggers de outbound. A diferença é semântica: "Me liga" é debug/test, "Abrir Mercado" é a operação REAL do produto.

## Estado idle

Quando não há operação viva OU quando o mercado está aberto: botão esmaecido, texto muda:
- Sem operação: `⏳ aguardando operação`
- Já aberto: `🔓 mercado aberto — {n_carriers} pernas ativas`

Nesses casos o botão vira uma STATUS PILL, não um CTA.

## Endpoints relacionados

| Rota | Uso | Body |
|---|---|---|
| POST `/demo/dial-market` | botão "Abrir Mercado" | `{}` (usa defaults) |
| POST `/demo/dial-market` | com override | `{"carriers":[{"id","name","phone"},...], "reset": bool}` |
| POST `/demo/reset` | botão "Falhar Manualmente" ou "Reiniciar" | `{operation_ref?}` |
| POST `/demo/call-me` | botão "Me liga" (já existe) | `{}` ou `{"to": "+55..."}` |
| POST `/phase3/abort/{auction_id}` | botão "Cancelar leilão" | vazio |
| POST `/escalate/{call_id}/resolve` | botão do card de escalação | `{approved: bool, note?: str}` |

Todas retornam JSON. Nunca engule erro — mostra toast com o corpo.
