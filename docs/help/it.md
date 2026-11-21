<!-- Kalmido help, Italian (2.1086.0, #5820). One block per "How to" section of docs/*.md: the key and the fingerprint (src)
of the English text it was translated from. **Bold** = the label exactly as the interface shows it.
Check: python3 tools/check_userhelp.py. -->

<!-- help: files#how-to-set-up-a-scan-inbox src=e3875c5bca -->
## Configurare una casella di scansione

Una casella di scansione invia le nuove scansioni da una cartella del tuo computer direttamente nei tuoi documenti.

1. Apri **Impostazioni** > **Documenti** (in Documenti: il pulsante **Impostazioni** in alto) e vai a **Documenti: ingressi**.
2. In **Osservatore cartelle** scarica il programma per il tuo computer (Mac o Windows).
3. Apri **Nuova casella di scansione**, scrivi un **Nome**, scegli la cartella in **Nella cartella** e tocca **Crea casella**.
4. Kalmido mostra il **Codice di configurazione** solo questa volta. Tocca **Copia**, avvia il programma, incolla il codice e
   scegli la cartella da osservare.

Poi: ogni nuovo file di quella cartella viene caricato, letto e archiviato nei tuoi documenti. Ritrovi la casella nello stesso
posto per cambiare cartella, prolungarla di un anno o revocarla. Solo tu crei una casella di scansione, mai un agente.

<!-- help: files#how-to-add-documents-and-find-them-again src=4520b96808 -->
## Aggiungere documenti e ritrovarli

1. Apri **File** > **Documenti**.
2. Tocca **Aggiungi documenti** e scegli PDF o foto, oppure trascinali sulla pagina. Sul telefono **Scansiona** fotografa
   una lettera.
3. Scrivi una parola in **Cerca nei documenti…**: la ricerca trova anche le parole dentro le lettere.

Poi: Kalmido legge ogni documento e compila data, importo e mittente. Ciò di cui non è sicuro aspetta in **Da verificare**:
aprilo, correggi e tocca **Verificato** (oppure **Accetta tutto** per i suggerimenti).

<!-- help: files#how-to-share-a-folder src=f6f99fa88e -->
## Condividere una cartella

1. Apri **File** e il menu **Altro** (⋯) della cartella, poi **Condividi…**.
2. In **Condividi con …** scegli una persona, un gruppo o un agente.
3. Scegli **Può vedere** o **Può modificare**, tocca **Aggiungi** e poi **Fatto**.

Poi: la persona vede la cartella e tutto il suo contenuto, anche ciò che verrà aggiunto. Solo il proprietario può condividere
una cartella.

<!-- help: agent-setup#how-to-create-your-personal-agent src=55f8406267 -->
## Creare il tuo agente personale

Un agente è un assistente (per esempio Claude) che lavora in Kalmido con un proprio account e vede solo ciò che condividi con lui.

1. Apri **Impostazioni** > **Agenti** e la scheda **Configura**.
2. In **I tuoi agenti personali** compila **Nome visualizzato** e gli altri due campi, poi tocca **Crea agente**.
3. Nella finestra che si apre scegli il tuo **Computer** e la **Cartella del progetto** e tocca **Crea comando**.
4. Tocca **Copia**, apri il Terminale su quel computer, incolla il comando e premi Invio. Poi **Fatto**.

Poi: l'agente compare in **I tuoi agenti personali**. Non vede ancora nulla: dagli un progetto o una cartella. Il comando vale
una volta e per pochi minuti; **Configura** nella riga dell'agente ne crea uno nuovo.

<!-- help: agent-setup#how-to-give-an-agent-access-to-a-project-or-folder src=aaf357fa82 -->
## Dare a un agente accesso a un progetto o una cartella

Un progetto:

1. Apri il menu (⋯) del progetto e scegli **Agente…**.
2. In **Agenti** scegli l'agente e conferma con **Condividi**.

Una cartella in File o Conoscenza:

1. Apri il menu (⋯) della cartella e scegli **Condividi…**.
2. In **Condividi con …** scegli l'agente, **Può vedere** o **Può modificare**, tocca **Aggiungi** e poi **Fatto**.

Poi: l'agente lavora in quel progetto o in quella cartella, e solo lì. Ogni accesso di un agente resta nella cronologia; una
cartella bloccata non si condivide mai con un agente.

<!-- help: agent-setup#how-to-approve-what-an-agent-asks-for src=dfbe19a2e9 -->
## Approvare ciò che chiede un agente

1. Quando un agente ha bisogno del tuo sì, compare una scheda "… ti aspetta" (in Oggi e in Agenti).
2. Tocca **Approva** o **Rifiuta**. Per una proposta prima **Esamina la proposta**.

Poi: l'agente prosegue con ciò che hai approvato; un passo rifiutato non avviene.

<!-- help: office#how-to-write-a-quotation src=c3eae76ef0 -->
## Scrivere un preventivo

1. Apri **Ufficio** > **Preventivi** e tocca **Nuovo preventivo**. La bozza si apre subito.
2. Scegli il **Cliente**.
3. Aggiungi righe con **Aggiungi servizio**.
4. Quando è pronto tocca **Bloccare**. Dopo, numero, righe e importi non cambiano più.
5. Tocca **Invia** per mandarlo via e-mail, oppure **Scarica PDF**.

Poi: il preventivo è nella lista. Segnalo come inviato e poi come **Accettato** o rifiutato; da un preventivo accettato nasce
la fattura in un passo. Una bozza si guarda con **Anteprima**.

<!-- help: office#how-to-turn-a-quotation-into-an-invoice src=faeae491ab -->
## Trasformare un preventivo in fattura

1. Apri il preventivo accettato e tocca **Crea fattura**.
2. Scegli il **Tipo di fattura** e conferma.
3. Controlla la fattura, tocca **Bloccare** e poi **Invia**.

Una fattura senza preventivo: **Ufficio** > **Fatture** > **Nuova fattura**.

Poi: la fattura riceve il suo numero quando la blocchi, senza buchi. Resta aperta finché non si registra un pagamento.

<!-- help: office#how-to-record-a-payment src=6663fe7a8c -->
## Registrare un pagamento

1. Apri la fattura bloccata e tocca **Registra pagamento**.
2. Controlla data e importo e tocca **Registra**.

Oppure con l'estratto conto: **Ufficio** > **Banca** > **Importa estratto conto** e conferma il suggerimento con **Subentra**.

Poi: la fattura risulta pagata (o pagata in parte). Solo un amministratore dell'organizzazione registra i pagamenti.

<!-- help: tasks#how-to-add-a-task-with-a-date src=8a3685b666 -->
## Aggiungere un'attività con una data

1. Tocca **Aggiungi attività…** in fondo al progetto (sul telefono: il pulsante +).
2. Scrivi l'attività come la pensi, per esempio "Chiamare il dentista domani 15", oppure scegli la data.
3. Premi Invio.

Poi: l'attività finisce nel progetto aperto (o nella **Raccolta**) con la sua data e compare quel giorno in **Oggi**. Per
cambiare la data apri l'attività e tocca la data: **Oggi**, **Domani**, **Prossima settimana** o un giorno del calendario.

<!-- help: tasks#how-to-make-a-task-repeat src=b22f5f0a3c -->
## Ripetere un'attività

Un'attività ricorrente torna da sola: ogni giorno, ogni settimana o con una regola tua.

1. Apri l'attività e tocca la sua data.
2. Scegli in **Ripetizione**, per esempio **Ogni giorno**, oppure **Personalizza…** per una regola tua.
3. Tocca **Fatto**.

Poi: quando completi l'attività compare la successiva con la prossima data.

<!-- help: tasks#how-to-assign-a-task-or-share-a-project src=d8a87df384 -->
## Assegnare un'attività o condividere un progetto

1. Condividere il progetto: il suo menu (⋯) > **Condividi…**, scegli la persona in **Condividi con …**, un ruolo (per esempio
   **Membro**) e tocca **Aggiungi**.
2. Assegnare un'attività: apri l'attività, tocca **Assegna** e scegli la persona.

Poi: la persona vede il progetto e riceve l'attività. Si può assegnare solo a persone del progetto.

<!-- help: calendar#how-to-create-an-event src=5f4ebe03b3 -->
## Creare un evento

1. Apri **Calendario** e tocca **Evento** (sul telefono: il pulsante +).
2. Compila **Titolo**, **Inizio** e **Termina** e, se serve, **Ripetizione**.
3. Tocca **Salva**.

Poi: l'evento è nel calendario e sul tuo telefono, se è collegato.

<!-- help: calendar#how-to-subscribe-to-another-calendar src=349059272c -->
## Abbonarsi a un altro calendario

1. Apri **Calendario** > **Calendari** > **Abbonamenti…** (oppure **Impostazioni** > **Connessioni** > **Calendari**).
2. Tocca **Aggiungi calendario**.
3. Incolla il link del calendario e tocca **Aggiungi**. Per un account scegli **Account CalDAV** e **Trova calendari**.

Poi: i suoi eventi compaiono nel tuo calendario, in sola lettura e solo per te.

<!-- help: calendar#how-to-show-kalmido-on-your-phone src=06e571f04f -->
## Vedere Kalmido sul telefono

1. Apri **Calendario** > **Calendari** > **Sul telefono…** (oppure **Impostazioni** > **Connessioni** > **App calendario (CalDAV)**).
2. Tocca **Nuova password per app** e copia server, nome utente e password nelle impostazioni del calendario del telefono.

Poi: i tuoi eventi e le attività con data compaiono nel calendario del telefono. Usa lì la password per app, mai la tua
password di Kalmido.

<!-- help: wiki#how-to-write-a-knowledge-page src=122a76cda7 -->
## Scrivere una pagina di conoscenza

1. Apri **Conoscenza** nella barra laterale e tocca **Nuova pagina**.
2. Scrivi il nome della pagina in **Nome**. Una `/` crea cartelle: «Processi/Lista» finisce nella cartella *Processi*.
3. Scrivi il testo. Con `[[` colleghi un'altra pagina.

Cosa succede dopo: la pagina si salva da sola e compare nell'albero a sinistra. Sotto ogni pagina, **Collegata da** elenca
le pagine che rimandano ad essa.

<!-- help: wiki#how-to-share-a-page-read-only src=f589cec1bf -->
## Condividere una pagina in sola lettura

1. Apri la pagina, apri il suo menu (⋯) e scegli **Condividi…**.
2. Per una persona: sceglila in **Scegli una persona…** (o scrivi un indirizzo e-mail) e tocca **Aggiungi**.
3. Per chi non ha un account: scegli **Crea link pubblico**, imposta **Valido fino al** se vuoi e copia il link.

Cosa succede dopo: la persona legge questa pagina (o l'intera cartella, con *Condividi cartella…*) e nient'altro delle
tue pagine; il link apre una pagina semplice senza accesso. **Disattiva** termina un link subito.

<!-- help: wiki#how-to-bring-back-an-earlier-version-of-a-page src=f736215a16 -->
## Ripristinare una versione precedente di una pagina

1. Apri la pagina, apri il suo menu (⋯) e scegli **Cronologia**.
2. Scegli una versione nell'elenco: Kalmido mostra cosa differisce dal testo attuale.
3. Tocca **Ripristina**.

Cosa succede dopo: il vecchio testo torna a essere quello attuale come nuova versione, quindi non si perde nulla; il
ripristino si può annullare.

<!-- help: sheets#how-to-make-a-table-with-a-formula src=b8056fbeac -->
## Creare una tabella con una formula

1. Apri **Tabelle**, tocca **Nuova tabella**, dagli un nome e tocca **Crea**.
2. Tocca **Aggiungi colonna** e **Aggiungi riga** finché la griglia va bene e scrivi i valori nelle celle.
3. Inizia una cella con `=`, per esempio `=B2*C2` (ore per tariffa) o `=SOMMA(C2:C9)`.

Cosa succede dopo: la cella mostra il risultato e si ricalcola quando cambia un valore; la tabella si salva da sola.

<!-- help: sheets#how-to-share-one-table src=e19d1eba08 -->
## Condividere una tabella

1. Apri la tabella, apri il suo menu e scegli **Condividi…**.
2. Scegli una persona o un agente in **Condividi con …**, poi **Può vedere** o **Può modificare** e tocca **Aggiungi**.

Cosa succede dopo: la persona vede solo questa tabella, non il resto del tuo spazio di lavoro; la trova in **Condiviso con me**.
**Smetti di condividere** la termina subito.

<!-- help: team#how-to-write-to-a-colleague-in-the-team-chat src=d14fa10beb -->
## Scrivere a qualcuno nella chat del team

1. Apri **Chat del team** e tocca **Nuovo messaggio**.
2. Scegli la persona (o **Nuovo canale** per un canale).
3. Scrivi il messaggio e tocca **Invia**.

Cosa succede dopo: la persona riceve il messaggio e una notifica; vedi quando l'ha letto. Ogni progetto che condividi ha
anche una propria chat.

<!-- help: team#how-to-pin-a-message-or-answer-in-a-thread src=d57b9f4728 -->
## Fissare un messaggio o rispondere in un thread

1. Apri il menu di un messaggio (sul telefono: tienilo premuto).
2. Scegli **Fissa** per tenere in vista in alto un messaggio importante, oppure **Rispondi nel thread** per rispondere senza
   riempire la conversazione principale.

Cosa succede dopo: i messaggi fissati restano nella barra sopra i messaggi (al massimo cinque per conversazione); un
thread mostra le risposte a quel messaggio e i suoi partecipanti vengono avvisati.

<!-- help: team#how-to-invite-someone-without-an-account-by-a-link src=45b346e536 -->
## Invitare con un link qualcuno senza account

1. In Impostazioni > Account scegli **Trova una persona …**.
2. Scegli **Invita con link**, aggiungi se vuoi per chi è (lo vedi solo tu) e scegli **Crea link**.
3. Invia il link con **Copia** o **Condividi**, oppure fai scansionare il codice QR alla persona.

Cosa succede poi: chi apre il link crea un account con nome e indirizzo e-mail ed è subito collegato con te; ricevi una
notifica. Il link funziona una volta e per 14 giorni e viene mostrato solo subito dopo averlo creato; **Ritira** chiude
subito un link aperto. Chi ha già un account lo apre dopo aver effettuato l'accesso e conferma il collegamento.

<!-- self-hosted -->
Un admin del server può disattivare questi link (Impostazioni > Server > Accesso).

<!-- help: budget#how-to-start-a-household-budget src=1116c1b0a8 -->
## Creare un budget domestico

1. Apri **Budget** (nell'area **Casa e vita**, da attivare in *Impostazioni > Moduli*) e tocca **Crea un budget**.
2. Tocca **Nuova voce**, compila **Importo**, la data e **Cosa**, scegli una categoria e tocca **Salva**.

Cosa succede dopo: il mese mostra cosa hai **Ricevuto** e **Speso** e cosa è **Rimane**; le categorie mostrano le spese
rispetto al piano. Ogni modifica si può annullare.

<!-- help: budget#how-to-add-rent-and-other-recurring-entries src=cd197ab4f2 -->
## Aggiungere l'affitto e altre voci ricorrenti

1. Nel budget apri il menu (⋯), scegli **Voci ricorrenti** e poi **Nuova voce ricorrente**.
2. Indica cos'è e l'importo, scegli in **Ogni quanto** mensile, trimestrale o annuale e tocca **Salva**.

Cosa succede dopo: la voce compare sotto **Da registrare questo mese** quando scade. Kalmido non la registra mai da solo: tocca
**Prenotato** quando i soldi sono davvero usciti (o entrati).

<!-- help: budget#how-to-import-a-bank-statement-into-the-budget src=45308584bc -->
## Importare un estratto conto nel budget

Kalmido non ha accesso alla tua banca: scarichi tu il file.

1. Scarica dalla tua banca l'esportazione CSV (o CAMT) dell'estratto conto.
2. Nel budget apri il menu (⋯), scegli **Importa file CSV** e il file in **Scegli file**.
3. Controlla quale colonna contiene data, importo e testo, e conferma.

Cosa succede dopo: i nuovi movimenti entrano nel budget; quelli già presenti non vengono raddoppiati. **Annulla questa importazione**
annulla tutta l'importazione.

<!-- help: home#how-to-make-a-shopping-list src=c52a018554 -->
## Creare una lista della spesa

1. Apri **Casa e vita**; senza lista offre **Lista della spesa**. Toccala.
2. Aggiungi gli articoli come scrivi un'attività; «2 l di latte» e «latte» contano come lo stesso articolo.

Cosa succede dopo: gli articoli vengono ordinati per reparto (spostane uno una volta e il successivo ci va da solo), e
chi condivide la lista spunta in diretta mentre fa la spesa.

<!-- help: home#how-to-sort-projects-into-folders src=9e6ec9656c -->
## Ordinare i progetti in cartelle

1. Nella barra laterale apri il menu (⋯) di un progetto e scegli **Sposta nella cartella…**.
2. Scegli una cartella o tocca **Nuova cartella…** e dalle un nome.

Cosa succede dopo: il progetto sta in quella cartella nella barra laterale. Puoi anche trascinare i progetti tra le
cartelle e condividere un'intera cartella in una volta (vedi «Condividere una cartella con altre persone»).

<!-- help: team#how-to-share-a-folder-with-people src=d68cfe0773 -->
## Condividere una cartella con altre persone

1. Nella barra laterale apri il menu (⋯) di una cartella e scegli **Condividi cartella…**.
2. Scegli una persona in **Condividi con …** e tocca **Aggiungi**. Per gli agenti c'è la parte **Agenti** dello stesso dialogo.

Cosa succede dopo: tutti i progetti della cartella sono condivisi con lei, anche quelli aggiunti più tardi.
**Smetti di condividere** la termina subito. Un singolo progetto si condivide allo stesso modo dal suo menu.

<!-- help: team#how-to-give-people-without-an-account-a-public-link src=5c9b76a147 -->
## Dare un link pubblico a chi non ha un account

1. Apri il dialogo **Condividi…** del progetto o della cartella e cerca **Link pubblico**.
2. Imposta **Valido fino al** se il link deve scadere, copialo con **Copia il link** e invialo.

Cosa succede dopo: chiunque abbia il link può leggere il progetto, senza accesso, in sola lettura, senza commenti,
assegnatari o file. **Disattiva** termina il link subito.

<!-- help: team#how-to-move-the-company-to-another-server src=12d13760a6 -->
## Trasferire l'azienda su un altro server

1. Sul nuovo server (il tuo o app.kalmido.com) crea un'organizzazione vuota e invita i suoi membri in Impostazioni >
   Organizzazione > Persone - oppure spunta **Invita via e-mail** per le persone mancanti nell'anteprima dell'importazione.
2. Sul vecchio server annota la chiave di ripristino (Impostazioni > Organizzazione > Dati > Cifratura), poi apri
   **Trasferire l’organizzazione** e scegli **Avvia il trasloco…**: l'organizzazione diventa di sola lettura, le serie
   di fatture, i solleciti e il recupero di posta e banca si fermano.
3. Scegli **Esporta l’organizzazione**, poi **Crea esportazione** e **Scarica**. Ogni persona sceglie inoltre
   **Esporta tutto** (i propri dati), e chi ha un ufficio proprio **Esporta l’ufficio**.
4. Sul nuovo server scegli **Importa da un’esportazione Kalmido**: prima il file dell'organizzazione (con la chiave di
   ripristino, la nuova organizzazione come destinazione), poi ogni persona il proprio file.
5. Configura di nuovo ciò che non viene trasferito: password e passkey, password degli account di posta, dispositivi di
   calendario e contatti, webhook e connessioni, link pubblici, dei moduli e delle prenotazioni, indirizzi e-mail in
   entrata e agenti.

Cosa succede poi: da ora in poi i numeri delle fatture li assegna solo il nuovo server. Chiedi all'admin del vecchio
server di eliminare la vecchia organizzazione; **Termina il trasloco** solo se alla fine resti lì. Cambiare il nome
dell'azienda non richiede un trasloco - cambia il nome. Due aziende non si possono unire in una, né una dividere, senza
perdite.

Senza organizzazione, solo con il tuo ufficio: apri Impostazioni > Azienda e ufficio > Dati, scegli **Trasferire l’ufficio**
e **Avvia il trasloco**; poi **Esporta l’ufficio** e **Esporta tutto**, e importa entrambi sul nuovo server. La tua area
privata fuori dall'ufficio resta modificabile.

<!-- help: office#how-to-set-up-your-office src=fb04d9cb9f -->
## Configurare il tuo ufficio

1. Apri Impostazioni > Azienda e ufficio. In Azienda inserisci nome, indirizzo e logo della tua azienda.
2. In Banca e imposte inserisci il tuo conto bancario, il tuo codice fiscale e come paghi l'IVA.
3. In Documenti spunta **Piccola impresa** se non addebiti l'IVA (articolo 19 UStG) e stabilisci come appaiono i numeri
   di preventivi e fatture.
4. In Testi e modelli scrivi i testi sopra e sotto i tuoi documenti; in Pacchetti attiva ciò che serve al tuo mestiere.
5. Vuoi provare prima? Attiva la **Modalità di prova** in Documenti: i documenti ricevono un numero TEST e la filigrana
   MUSTER. Disattivala prima della tua prima fattura vera.

Cosa succede poi: ogni nuovo preventivo e ogni nuova fattura usa questi dati. L'ufficio mostra cosa manca ancora per una
fattura finché c'è tutto. Chi nella tua azienda può vedere e cambiare cosa lo stabilisci in «Decidere chi vede cosa
nell'ufficio».

<!-- help: office#how-to-decide-who-sees-what-in-the-office src=cd8aa74ee0 -->
## Decidere chi vede cosa nell'ufficio

1. Apri Impostazioni > Azienda e ufficio e scegli **Diritti nell’ufficio**.
2. In Persone dai a ogni persona un gruppo: un modello (per esempio solo le proprie ricevute, spese di viaggio e tempi) o
   un gruppo tuo: copia un modello in Gruppi e imposta per ogni parte dell'ufficio cosa può fare il gruppo.

Cosa succede poi: da ora la persona vede solo quelle parti dell'ufficio. Gli admin dell'organizzazione vedono sempre
tutto; chi non ha un gruppo mantiene l'accesso del suo ruolo nell'organizzazione. Ogni modifica finisce nel registro, e
ognuno vede i propri in **I miei permessi**.

<!-- help: office#how-to-come-from-another-program src=df1c3a51e1 -->
## Arrivare da un altro programma

1. Continua la tua numerazione: in Impostazioni > Azienda e ufficio > Documenti inserisci il numero successivo di ogni
   serie (quello che il tuo vecchio programma avrebbe dato dopo).
2. Porta con te clienti, servizi e attrezzature: in Impostazioni > Azienda e ufficio > Dati scegli
   **Importa dati precedenti**, scegli il tuo foglio di calcolo (.xlsx) e controlla l'anteprima prima di confermare. Le
   vecchie fatture e i vecchi preventivi (PDF) vengono archiviati così come sono.

Cosa succede poi: la tua prossima fattura continua la tua numerazione senza buchi. Un'importazione si può annullare
finché niente si basa su di essa. Arrivi da un altro server Kalmido? Vedi «Trasferire l'azienda su un altro server».

<!-- help: office#how-to-send-e-invoices src=56ef8356c7 -->
## Inviare fatture elettroniche

1. Per la maggior parte dei clienti non c'è niente da fare: ogni fattura è una fattura ZUGFeRD, un normale PDF con dentro
   i dati della fattura.
2. Un ente pubblico ti dà un codice di instradamento (Leitweg-ID): apri il cliente e inseriscilo in
   **Riferimento acquirente (es. codice di instradamento)**. A quel cliente viene proposta XRechnung (XML puro).
3. Per scegliere un altro formato per tutti, apri Impostazioni > Azienda e ufficio > Documenti,
   **Formato fattura elettronica**.

Cosa succede poi: il codice di instradamento è stampato sulla fattura e va nella fattura elettronica. Il tuo
commercialista e il destinatario leggono i dati della fattura senza ribatterli.

<!-- help: team#how-to-create-your-company src=ca851ef163 -->
## Creare la tua azienda

1. Apri Impostazioni > Account e scegli **Aggiungi un’organizzazione**.
2. Inserisci il nome della tua azienda e scegli **Crea**.

Cosa succede poi: sei admin dell'organizzazione della tua azienda. I suoi progetti, file e il suo ufficio restano separati
dalle tue cose private; la barra laterale ne mostra una alla volta. Poi invita i tuoi colleghi (vedi «Invitare persone e
dare loro un ruolo»). Se lavori da solo non ti serve un'organizzazione: il tuo ufficio funziona allo stesso modo nella tua
area privata.

<!-- help: team#how-to-invite-people-and-give-them-a-role src=1c51bbc4ab -->
## Invitare persone e dare loro un ruolo

1. Apri Impostazioni > Organizzazione > Persone e scegli **Invita persone**.
2. Inserisci l'indirizzo e-mail e scegli il **Ruolo**: un membro vede e cambia ciò che l'organizzazione condivide, un
   admin gestisce anche persone, ruoli e impostazioni, sola lettura legge soltanto, contabilità legge ed esporta
   l'ufficio, un ospite vede solo ciò che è condiviso con lui personalmente.
3. Scegli **Invita**.

Cosa succede poi: la persona riceve un'e-mail ed entra con il proprio account; chi non ne ha uno sceglie prima una
password. Il ruolo lo cambi più tardi nella stessa lista. Cosa può fare ognuno nell'ufficio si stabilisce a parte (vedi
«Decidere chi vede cosa nell'ufficio»).

<!-- help: team#how-to-create-an-account-or-get-a-new-password src=9e70b000b7 -->
## Creare un account o ottenere una nuova password

1. Per creare un account scegli **Crea account** nella pagina di accesso, inserisci nome, indirizzo e-mail e una password
   e apri il link nell'e-mail che ricevi.
2. Password dimenticata? Scegli **Password dimenticata?** nella pagina di accesso, inserisci il tuo indirizzo e-mail e
   scegli **Invia il link**. Apri il link nell'e-mail e scegli una nuova password.

Cosa succede poi: hai effettuato l'accesso. Una nuova password ti disconnette sugli altri dispositivi e chiude le password
per app e i token API; i tuoi webhook e canali vengono disattivati finché non li riattivi. Nessuna e-mail dopo qualche
minuto? Guarda nella cartella spam.

<!-- self-hosted -->
**Crea account** manca quando sul server solo gli admin aggiungono persone: chiedi loro un account.

<!-- help: team#how-to-get-help-from-a-person src=00bf17443f -->
## Ricevere aiuto da una persona

<!-- hosted -->
1. Apri Impostazioni > Aiuto e scegli **Scrivi al supporto** (in **Aiuto da una persona**). Una persona risponde per
   e-mail.
2. Se devono guardare nel tuo account, aprilo per un tempo limitato con **Consenti l’accesso al supporto**.

<!-- self-hosted -->
1. Il tuo server è gestito dalla tua azienda o da te: il suo admin ti aiuta.
2. Un errore in Kalmido stesso? Segnalalo con **Segnala un problema** in Impostazioni > Aiuto.

<!-- hosted -->
Cosa succede poi: nessuno del supporto può guardare nel tuo account prima che tu lo consenta, e solo fino all'ora che hai
scelto. Lo chiudi prima in Impostazioni > Account > Accesso del supporto.
