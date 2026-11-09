# Week 8: retries, recovery, and a human approval gate

---

## Week 8

**Run conditions.** fault seed: 42 | attempts: 3 | base delay: 0.02 (01_survive
HARDENED), 0.05 (SEARCH_POLICY / FEES_POLICY) | max elapsed: 3.0 |
LangGraph 1.2.x (verifica con `pip show langgraph | grep Version`) |
date: 2026-11-09

### 1. Which errors are retryable

Retryable: `ToolTimeout`, `RateLimited`, `ServerError`.

Deliberately NOT retryable: `ContractDrift`, because la chiamata e' riuscita:
200, corpo valido, campo rinominato da `fee_eur` ad `amount_eur`.

Riprovare una chiamata riuscita produce la stessa risposta valida e sbagliata
alla velocita' della rete, e poi riporta una scala esaurita per un
fallimento che non c'e' mai stato: tre volte il costo, zero informazione in
piu', e un log che accusa il trasporto di un problema di contratto.

La lista e' una allowlist (`RETRYABLE`), non una blocklist, quindi il default
per un'eccezione non ancora classificata e' "non riprovare". Un 401 cade
fuori gratis, ed e' quello che si vuole: un credenziale rotta riprovata tre
volte e' un credenziale rotta lenta, e su certi upstream un account bloccato.

### 2. The fault matrix

| | correct | WRONG | degraded | failed |
| baseline | 1 | 0 | 2 | 5 |
| hardened | 2 | 0 | 5 | 1 |

What hardening actually bought:

Quattro fallimenti secchi su cinque sono diventati risposte degradate che
dicono cosa manca. Non risposte corrette: l'unico `correct` in piu' e'
`flaky`, il caso di controllo, dove un retry e' davvero la risposta giusta.
`empty` resta `failed` ed e' corretto, perche' non e' stato recuperato nulla
e non c'e' nulla a cui degradare. WRONG resta 0 in entrambe le righe solo
perche' il drift rinomina la chiave e quindi si autodenuncia: un drift che
cambiasse il valore riempirebbe la colonna WRONG della baseline, non quella
hardened, dove la validazione rifiuta la forma prima che il numero venga
letto.

Prova che e' una scala e non un wrapper di retry: su `drift` e `malformed` lo
step `fees` riporta **1** tentativo, non 3.

### 3. The empty result

An empty result is not an error. My pipeline treats it as **input mancante**,
non come ricerca riuscita senza risultati, because il manuale che non copre
il tema e l'indice costruito male sono indistinguibili da dentro la pipeline.
Trattarlo come successo e' il modo in cui si risponde partendo dal nulla. Il
costo accettato e' che un tema davvero non coperto viene riportato come
degradato; quello che quel costo compra e' che nessuna risposta sicura esce
senza una fonte sotto. Lo stesso vale per `fees`, dove un `{}` diventa
`missing: ["the fee"]` invece di un importo assente e silenzioso.

### 4. The gate

Gated step: **`submit`**. The others are not gated because `gather` e `price`
sono letture idempotente senza effetti esterni, gia' coperte da retry,
fallback e validazione, e `draft` e' una funzione pura dello stato il cui
output finisce comunque nel payload che l'approvatore legge. `submit` e'
l'unico il cui effetto esce dal sistema e non si annulla. Il criterio e' la
conseguenza, non la confidenza: gattare tutto insegna all'approvatore a
cliccare avanti, e una firma su una cosa non letta e' peggio di nessun gate.

An unanswered approval after the timeout: **non deposita**, verdetto
registrato come `timeout`, nessuna identita' nel record perche' nessuno ha
deciso. That protects il cittadino e l'amministrazione, non il tasso di
completamento della run. E' anche il default che usa il batch non presidiato
della settimana 10.

The approval payload carries gli argomenti esatti, le prove, il flag
`degraded` e la lista `missing`, and deliberately does not carry un riassunto
scritto da un modello: il componente sotto controllo scriverebbe anche il
resoconto di se stesso.

### 5. The duplicate the state does not show

I put a side effect above the interrupt. It executed **2** times. The recorded
state showed it **1** time.

What that means for anything my gated node does before it asks:

La prima esecuzione non ritorna mai, solleva per persistere l'interrupt,
quindi il suo valore di ritorno viene scartato mentre cio' che ha fatto al
mondo esterno resta. Il modo di fallire non e' "lo stato si sporca": e' una
pratica depositata due volte su una run che dopo sembra pulita, e l'unico
registro che ho e' quello che non mostra il duplicato. Regola: sopra un
interrupt, solo letture. Ne derivano due vincoli sul progetto: il nodo gated
e' l'unico posto in cui avviene una scrittura, e la scrittura e' idempotente
su `case_id`, cosi' un replay e' rilevabile invece che invisibile.

### Deferred

Il timeout sull'approvazione non risposta e la traccia OpenTelemetry sono
compiti per casa (entrambi previsti dal brief). La dimostrazione del side
effect sopra l'interrupt e' fatta con `interrupt_smoke_test.py`; ripeterla
sulla mia pipeline e' da fare.
