<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="assets/logo-dark.png">
    <img src="assets/logo.png" alt="SuspiciousDog, che guarda di traverso i tuoi plugin" width="260">
  </picture>
</p>

<h1 align="center">SuspiciousDog</h1>

<p align="center"><b>Non si fida dei tuoi plugin. Ha letto i tuoi transcript.</b></p>

<p align="center"><a href="README.md">English</a></p>

<p align="center">
  <img src="assets/hypotheses.svg" alt="Tre idee messe alla prova su 980 turni veri: due morte, una sopravvissuta" width="820">
</p>

Ogni plugin, skill, hook e riga di `CLAUDE.md` o `AGENTS.md` che dai a un agente AI è un'ipotesi: *se l'agente fa X,
lavoro meglio.* Nessuno la verifica. La installi perché suona bene.

Intanto il tuo agente ha preso appunti. Ogni turno di ogni sessione è sul disco, insieme a quello che hai risposto
subito dopo. L'esperimento è già fatto. SuspiciousDog lo legge.

## Lo conosci

Sta nell'angolo. Non dice niente quando installi il plugin di cui parlano tutti. Due settimane dopo si avvicina con
un foglio stampato: non è cambiato niente. Aveva ragione. Ha sempre ragione. Ha letto i log.

## I numeri

Lo abbiamo provato prima sulle nostre sessioni: 290 sessioni di Claude Code, 980 turni, 28 giorni. Una persona, un
modello. Dati veri, gli stessi conteggi che chiunque può rifare con `sdog sniff`. Gli abbiamo dato le nostre tre
idee migliori.

**Nomi scritti a memoria: morta.** Se un agente scrive un metodo, un flag o una colonna che non ha mai visto nel
contesto, lo prende dalla memoria del modello: lì nascono le allucinazioni, pensavamo. Su 90.101 nomi, i 19.244
scritti a memoria hanno fatto fallire uno strumento nello 0,07% dei casi. Quelli visti prima, nello 0,13%.

**"Fatto", senza guardare: morta.** L'agente dice di aver finito senza aver eseguito, aperto o visualizzato niente
dopo l'ultima modifica. È successo in 27 turni. Risposte negative dopo: 3,7%, contro 3,1% negli altri turni.

**"Faccio anche…?": vera.** L'agente chiude il turno offrendo altro lavoro. La risposta è negativa nel 14,3% dei casi,
contro il 2,6% (q = 0,045). `sdog show` spiega perché: non è rabbia, è *"no, mettila tra le cose da fare in
futuro"*. Gli stessi turni finiscono in un rinvio nel 10,2% dei casi contro l'1,4%, appena sotto la soglia.

Due idee su tre sono morte in una sera. Senza misurare le avremmo installate come hook su tutti i nostri progetti.
Quella sopravvissuta ce l'ha fatta per un soffio.

È una persona sola. Per effetti così piccoli ne servono molte di più. **Qui entri tu.**

## Aiuta il branco

```bash
sdog share
```

Ti mostra tutto quello che invierebbe e aspetta il tuo sì. Poi apre una issue su GitHub, a tuo nome, con questo e
solo questo:

| Inviato | Mai inviato |
|---|---|
| quali agenti, quante sessioni | i tuoi prompt, le risposte dell'agente |
| quanti turni, in quanti giorni | nomi di file, percorsi, nomi dei progetti |
| per ogni fattore × esito: quattro numeri interi | codice, comandi, qualsiasi cosa tu abbia scritto |

I nomi dei fattori vengono dall'elenco di SuspiciousDog, e un test blocca la build se potesse entrare altro
([PRIVACY.md](PRIVACY.md)). Ogni risultato condiviso è pubblico: il dataset è di tutti quelli che lo arricchiscono.
Pubblicheremo cosa mostra: quali abitudini degli agenti ricevono più "no", su quali agenti, e se i plugin di moda
spostano davvero qualcosa.

## Dieci secondi

```bash
pipx install git+https://github.com/Saturday-Company/SuspiciousDog
sdog demo        # sessioni sintetiche, per vedere com'è
sdog             # le tue
```

Comandi, installazione per ogni agente, agenti supportati e metodo sono nel [README in inglese](README.md) e in
[INSTALL.md](INSTALL.md). I nostri conteggi sono in [`results/`](results/), il metodo in [RESULTS.md](RESULTS.md).

## Licenza

MIT. Fatto da [Saturday Company](https://saturdaycompany.it).
