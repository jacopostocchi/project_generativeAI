# TODO 6 e TODO 7 — le risposte scritte

I due file dicono "The written answer is at the bottom": `01_survive.py` si
intesta **TODO 6**, `02_gate.py` si intesta **TODO 7**. Il README invece mette
6 e 7 entrambi nel blocco 3. Qui sotto c'e' il blocco per il fondo di
ciascuno dei due file, cosi' copri entrambe le letture.

Incollali come stringa a fine file (dopo `if __name__ == "__main__":`), oppure
come docstring `WRITTEN_ANSWER = """..."""`.

---

## TODO 6 — in fondo a `starter/01_survive.py`

```python
WRITTEN_ANSWER = """
Il seme e' 42, le due configurazioni sono NO_POLICY (1 tentativo, nessun
fallback, nessuna validazione) e HARDENED (3 tentativi, backoff esponenziale
con jitter, max_elapsed 3.0, fallback su search, validate_fee su fees).

                correct   WRONG   degraded   failed
    baseline          1       0          2        5
    hardened          2       0          5        1

Cosa ha comprato l'hardening: non risposte corrette. Ha spostato quattro
fallimenti secchi nella colonna "degraded", cioe' li ha trasformati da
silenzio in una risposta parziale che dice cosa manca. L'unico aumento di
"correct" e' `flaky`, che e' il caso di controllo: un solo retry lo fa
sparire del tutto, ed e' anche l'unico caso in cui il retry e' davvero la
risposta giusta. Concludere da quella riga che robustezza = retry e'
esattamente l'errore che la riga esiste per smascherare.

La riga `empty` resta "failed" dopo l'hardening, ed e' corretto: niente e'
stato recuperato, quindi non c'e' nulla a cui degradare. Una pipeline che
rispondesse comunque su `empty` guadagnerebbe una riga "correct" inventando
il dato. Il fallimento onesto e' il risultato migliore disponibile.

Il numero di tentativi e' la prova che la scala e' una scala e non un
wrapper di retry:

    timeout / rate_limit / server_error   search x3 poi fallback, fees x3 poi degrade
    malformed                             fees x1   la validazione, non il retry
    drift                                 fees x1   la chiamata e' RIUSCITA
    flaky                                 x2        il retry fa il suo lavoro
    slow / empty                          x1        nessun errore da riprovare

Su `drift` e `malformed` il contatore e' 1. Se fosse 3, `is_retryable`
avrebbe messo un errore di contratto dal lato riprovabile e la policy
pagherebbe tre volte la stessa risposta sbagliata.

Sulla colonna WRONG: qui e' 0 in entrambe le configurazioni, e non e' un
merito della baseline. E' 0 perche' il fault `drift` rinomina la CHIAVE, e
quindi `fee.value.get("fee_eur")` legge None invece di un numero plausibile:
la risposta sbagliata si autodenuncia. Basta un drift che cambi il valore
invece del nome del campo, o che rinomini la chiave in qualcosa che il nostro
codice legge comunque, e la colonna WRONG della baseline si riempie. La
colonna hardened non puo' riempirsi, perche' validate_fee rifiuta la forma
prima che qualcuno legga il numero. La differenza fra le due righe non e'
nei numeri di oggi, e' in quale delle due puo' produrre un numero sbagliato
presentato come giusto.
"""
```

---

## TODO 7 — in fondo a `starter/02_gate.py`

```python
WRITTEN_ANSWER = """
PARTE 1, il gate.

Lo step gated e' `submit`, ed e' l'unico. Il criterio e' la conseguenza, non
la confidenza: `submit` e' il solo nodo il cui effetto esce dal sistema e non
si annulla. Deposita una pratica presso l'amministrazione, e a valle di
quella pratica un cittadino riceve una lettera con un importo. Un modello
molto sicuro di se' su un dato sbagliato e' esattamente il caso in cui il
gate serve, quindi gating-per-confidenza gatterebbe proprio i casi in cui
non scatta.

Perche' gli altri tre no:

  gather   e' una lettura, idempotente, senza effetti esterni. Se sbaglia,
           sbaglia verso il basso: nessun passaggio, non un passaggio
           inventato. Retry piu' fallback coprono gia' i suoi modi di
           rompersi, e un umano davanti a una ricerca non aggiunge
           informazione che la ricerca non abbia.
  price    stessa cosa, e in piu' il suo errore peggiore (drift) non e'
           rilevabile a occhio: il payload rinominato sembra corretto a un
           umano che lo legge. La difesa giusta li' e' la validazione, non
           l'attenzione di una persona.
  draft    e' una funzione pura dello stato. Non chiama nulla e non scrive
           nulla, e il suo output e' comunque dentro il payload che
           l'approvatore legge al gate.

Il motivo di fondo per cui sono esattamente uno: l'attenzione
dell'approvatore e' la risorsa piu' scarsa del sistema. Quattro prompt per
una pratica insegnano a cliccare avanti, e un approvatore che clicca avanti
e' peggio di nessun gate, perche' produce una firma su una cosa non letta.
Si spende una volta, nel punto irreversibile.

Il payload porta gli argomenti esatti, le prove, il flag `degraded` e la
lista `missing`. Deliberatamente NON porta un riassunto scritto da un
modello: il componente il cui giudizio stiamo controllando scriverebbe anche
il resoconto di se stesso, e l'approvatore starebbe approvando il resoconto,
non l'azione.

Le tre vie sono tutte implementate e provate su due processi distinti,
thread_id RB-2026-0042, SqliteSaver su artifacts/week08_runs.sqlite:

  approve   submitted True,  decision approve, side effect SUBMITTED
  reject    submitted False, decision reject,  nessun side effect
  edit      submitted True,  decision edit,    fee 60.00 -> 55.00 e viene
            depositato l'importo MODIFICATO, non l'originale

La via `edit` non e' un extra. La risposta piu' frequente di un approvatore
reale non e' approve ne' reject, e' "approvo con un campo cambiato". Un gate
senza edit costringe a buttare lavoro corretto per un errore in un campo, e
quindi insegna ad approvare invece che a correggere.

Approvazione non risposta dopo il timeout: default a NON depositare, con
verdetto registrato come "timeout" e nessuna identita' nel record, perche'
nessuno ha deciso. Protegge il cittadino e l'amministrazione, non il tasso
di completamento della run. E' anche il default che usera' il batch non
presidiato della settimana 10: `request_approval(payload, unattended=True)`
ritorna quel default invece di aspettare.

PARTE 2, quello che non c'e' su nessuna slide.

Al resume il nodo interrotto riparte dalla PRIMA riga, quindi tutto cio' che
sta sopra `interrupt()` viene eseguito due volte. Questo e' nella lezione.
Quello che non c'e': lo stato registrato non te lo mostra. La prima
esecuzione non ritorna mai, solleva per persistere l'interrupt, quindi il
suo valore di ritorno viene scartato mentre cio' che ha fatto al mondo
esterno no.

Misurato con interrupt_smoke_test.py: il side effect sopra l'interrupt viene
stampato in entrambi i processi, e `side_effects` nello stato lo contiene una
volta sola. Eseguito due volte, registrato una.

Quindi il modo di fallire non e' "lo stato si sporca". E' una pratica
depositata due volte, o una mail spedita due volte, o un pagamento preso due
volte, su una run che dopo sembra pulita. L'unico registro che hai e' quello
che non mostra il duplicato.

La regola che segue e' stretta e senza eccezioni: sopra un interrupt, solo
letture. Tutto cio' che scrive va sotto, nel ramo che ha gia' visto il
verdetto. Per il mio progetto ne derivano due vincoli: il nodo gated e'
l'unico posto in cui avviene una scrittura, e la scrittura e' idempotente su
case_id, cosi' un replay e' rilevabile invece che invisibile.
"""
```
