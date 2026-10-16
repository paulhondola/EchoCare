# Ești bine? — Descrierea proiectului (versiunea finală)

**Sistem de avertizare timpurie pentru bolile provocate de căldură și frig la vârstnicii singuri.** Medicul de familie înrolează pacienții vulnerabili. În timpul episoadelor de caniculă și ger, sistemul îi sună automat pe orice telefon, inclusiv pe fix și fără internet. Un asistent AI vorbește natural cu ei, în română, și află cum se simt. Reguli fixe decid ce urmează, iar cazurile cu probleme ajung la familie și la dispeceratul DAS Timișoara.

| Pe scurt | |
|---|---|
| **Problema** | Vârstnicii singuri sunt cei mai expuși în caniculă și ger, dar tocmai ei nu cer ajutor. |
| **Soluția** | Apeluri automate cu un asistent AI, declanșate de avertizările meteo, cu escaladare deterministă. |
| **Actori** | Vârstnicul, medicul de familie, familia, dispeceratul DAS |
| **Componente** | Agentul telefonic (Twilio + LLM), motorul de reguli, trei aplicații web: medic, familie, DAS |
| **Track** | Medical Renaissance — UniHack 8, Timișoara, 13–15 noiembrie 2026 |

---

## 2. Problema

Vara 2026 a adus în Timiș cod roșu de caniculă, cu 39–41°C și nopți tropicale în care temperatura n-a coborât sub 26°C. În România, aproximativ 1,35 milioane de seniori locuiesc singuri. La nivel european, un studiu publicat în Nature Medicine a estimat peste 60.000 de decese legate de căldură doar în vara lui 2022.

Sistemul actual din Timișoara e reactiv. DAS are un dispecerat non-stop (0356.981), dar vârstnicul trebuie să sune el ca să primească ajutor. Echipele de teren au lucrat luni–vineri, între 08:00 și 16:00, și doar până la sfârșitul lui august. Contactul telefonic cu vârstnicii vulnerabili se face manual. La Telefonul Vârstnicului, 15 voluntari au reușit în 2025 să sune săptămânal doar 275 de seniori.

**Ideea de bază:** cei mai expuși sunt exact cei care nu cer ajutor. Insolația provoacă confuzie, iar izolarea face ca nimeni să nu observe la timp.

**De ce e o problemă medicală:** insolația e o urgență medicală cu mortalitate mare, iar confuzia acută e semnul-cheie la vârstnici. Factorii de risc sunt bine documentați: vârsta înaintată, bolile cardiovasculare, medicamentele care afectează reglarea temperaturii corpului (diuretice, antipsihotice, unele antihipertensive), mobilitatea redusă, declinul cognitiv și locuința la ultimul etaj, fără aer condiționat.

---

## 3. Ce există deja și ce lipsește

| Soluție | Cum funcționează | Limita |
|---|---|---|
| Dispeceratul DAS Timișoara | Non-stop, pe apeluri primite | Vârstnicul trebuie să sune el |
| Telefon cu brățară (DAS) | Buton de panică | Reactiv: un om confuz nu apasă |
| Telefonul Vârstnicului | Voluntari, reapel săptămânal | Axat pe singurătate, nu pe urgențe; nu scalează |
| Parents are OK | Detectează inactivitatea smartphone-ului | Cere smartphone, costă 59,99 lei/lună, alertează doar familia |
| Teleasistență privată | Dispozitiv cu buton SOS | Plătit și reactiv |

**Golul:** nimic nu sună proactiv și automat, pe orice telefon, la declanșarea avertizărilor meteo, cu evaluarea riscului fiecărei persoane și cu legătură directă la instituțiile care pot interveni.

---

## 4. Soluția

### 4.1 Actorii

| Actor | Rol în sistem | Interfață |
|---|---|---|
| **Vârstnicul** | Primește apelurile și vorbește cu asistentul AI | Doar telefonul: mobil sau fix, fără aplicație și fără internet |
| **Medicul de familie** | Înrolează pacienții, vede statusul, episoadele și transcrierile | Aplicație web, gândită pentru iPad |
| **Familia** | Vede statusul zilnic și dacă trebuie să sune persoana; confirmă verificările | Aplicație web, gândită pentru telefon |
| **Dispeceratul DAS** | Aprobă înrolările, preia cazurile, trimite echipa mobilă | Aplicație web pe desktop |

### 4.2 Principiile

1. **Vârstnicul nu are nevoie de nimic în afară de un telefon.** Apelul trece prin rețeaua de telefonie. Internetul e folosit doar între Twilio și server.
2. **AI-ul conversează, regulile decid.** Agentul conduce discuția natural, dar statusul persoanei și escaladarea sunt stabilite de reguli fixe, care pot fi explicate și auditate.
3. **Omul decide intervenția.** Sistemul nu sună niciodată singur la 112. Cazurile grave ajung la un dispecer.
4. **Fiecare actor vede minimul necesar.** Familia vede statusul, medicul vede tot despre pacienții lui, iar DAS vede ce îi trebuie pentru intervenție.

### 4.3 Fluxurile principale

```
ÎNROLARE   Medic (iPad) → cerere → DAS aprobă → apel de bun venit → pacient activ
CAMPANIE   Avertizare ANM → apeluri programate după scorul de risc
APEL       Vârstnic ⇄ Twilio ⇄ Agent AI → răspunsuri → motor de reguli → status
ESCALADARE Status → familie / sarcină DAS / dispecerat DAS
```

---

## 5. Fluxul de înrolare

### 5.1 Pașii

```
Medicul completează datele + încarcă documentul
        ↓
Factorii de risc sunt extrași automat → medicul confirmă
        ↓
Pacientul semnează consimțământul pe iPad
        ↓
Familia scanează codul QR → aplicația familiei se conectează
        ↓
Cererea ajunge la DAS → DAS aprobă
        ↓
Apel automat de bun venit → pacient activ
```

1. **Pacient nou.** În aplicația medicului se completează: numele, forma de adresare („doamna Maria”), telefonul (mobil sau fix), adresa și intervalul orar preferat pentru apeluri.
2. **Contactele familiei.** 1–2 persoane, cu nume, relație și telefon.
3. **Documentul medical.** Medicul încarcă un PDF cu situația medicală sau fotografiază documentul cu camera iPad-ului.
4. **Factorii de risc.** Sistemul extrage din document factorii de risc și îi pre-bifează. **Medicul doar confirmă sau corectează.** AI-ul propune, medicul decide.
5. **Consimțământul.** Pacientul citește textul pe ecran și semnează cu degetul sau cu Apple Pencil. Consimțământul acoperă apelurile, prelucrarea datelor de sănătate și partajarea statusului cu familia și cu DAS.
6. **Conectarea familiei.** Dacă un membru al familiei e la cabinet, scanează codul QR afișat pe iPad, iar aplicația familiei se deschide deja autentificată. Dacă nu e prezent, medicul îi trimite linkul de invitație.
7. **Trimiterea cererii.** Cererea ajunge în aplicația DAS, la „Cereri de înrolare”.
8. **Aprobarea DAS.** Operatorul verifică datele, alocă pacientul unei zone sau echipe și aprobă. Dacă lipsește ceva, cere completări medicului.
9. **Pacientul devine activ** și intră în campaniile de apeluri.

**Ținta de timp:** înrolarea durează pentru medic sub 3 minute. Medicii de familie sunt supraîncărcați, iar un flux lent nu ar fi folosit.

### 5.2 Statusurile cererii de înrolare

| Status | Semnificație | Cine vede |
|---|---|---|
| Trimisă | Medicul a trimis cererea | Medic, DAS |
| Completări necesare | DAS cere informații suplimentare | Medic, DAS |
| Aprobată | DAS a aprobat; urmează apelul de bun venit | Medic, DAS |
| Activă | Apelul de bun venit a avut loc | Medic, DAS, familie |
| Activă – număr neconfirmat | Apelul de bun venit n-a primit răspuns după două încercări | Medic, DAS |

### 5.3 Factorii de risc

| Factor | Efect |
|---|---|
| Vârsta înaintată | Crește scorul de risc |
| Boli cardiovasculare | Crește scorul de risc |
| Medicamente care afectează reglarea temperaturii (diuretice, antipsihotice, unele antihipertensive) | Crește scorul de risc |
| Mobilitate redusă | Crește scorul de risc; contează la recomandarea unui adăpost |
| Declin cognitiv cunoscut | Crește scorul de risc; **întrebarea de orientare se compară cu răspunsurile anterioare ale persoanei, nu cu răspunsul corect** |
| Locuință la ultimul etaj, fără aer condiționat | Crește scorul de risc la caniculă |

Ponderile scorului se stabilesc împreună cu un medic mentor. Proiectul nu pretinde validare clinică.

---

## 6. Campaniile de apeluri

O avertizare ANM de caniculă sau ger pentru Timiș pornește o campanie. Pacienții activi sunt sunați în ordinea scorului de risc, în intervalul orar preferat.

| Situație | Frecvența apelurilor |
|---|---|
| Cod galben | 1 apel pe zi |
| Cod roșu | 2 apeluri pe zi, inclusiv seara (nopțile tropicale sunt periculoase) |
| Scor de risc ridicat | Frecvență mărită |
| În afara episoadelor extreme | Opțional, un apel săptămânal |

În demo, campania e pornită de butonul „Simulează cod roșu” din aplicația DAS. Preluarea automată a avertizărilor de pe meteoromania.ro e o extensie.

---

## 7. Fluxul apelului

### 7.1 Arhitectura conversației

```
Bătrânul vorbește → Twilio (transcriere) → text → AGENTUL (LLM + tool-uri)
                                                         ↓
Bătrânul aude    ← Twilio (voce ElevenLabs) ← text, trimis pe bucăți
```

Conversația trece prin **Twilio ConversationRelay**. Twilio se ocupă de tot ce ține de voce și trimite conversația ca text, printr-un WebSocket. Serverul trimite înapoi textul agentului, pe bucăți, iar Twilio îl citește cu o voce ElevenLabs. **Serverul nu lucrează deloc cu audio** și nu are o integrare directă cu ElevenLabs. Vocea se alege din TwiML.

| Ce face Twilio | Ce face serverul |
|---|---|
| Preia audio-ul de pe linia telefonică | Primește textul prin WebSocket |
| Transcrie vocea în timp real (Google, pentru ro-RO) | Verifică cuvintele de alarmă pe fiecare frază |
| Detectează când omul a terminat de vorbit | Rulează agentul: LLM, istoricul conversației, tool-uri |
| Citește textul cu vocea ElevenLabs (implicită pentru ro-RO) | Trimite răspunsul pe bucăți, pe măsură ce e generat |
| Oprește vocea dacă omul vorbește peste asistent | Ține lista de verificare și starea conversației |
| Detectează tastele apăsate | Rulează motorul de reguli și escaladarea |

### 7.2 Pornirea apelului

Dialer-ul serverului pornește apelul prin API-ul Twilio. Când persoana răspunde, serverul întoarce un TwiML de forma:

```xml
<Response>
  <Connect action="https://<server>/voice/handoff">
    <ConversationRelay url="wss://<server>/relay" language="ro-RO"
      ttsProvider="ElevenLabs" voice="ID_VOCE"
      welcomeGreeting="Bună ziua, doamna Maria. Sunt asistentul DAS Timișoara.
        Vă sun pentru că azi e cod roșu de caniculă. Nu vă cer niciodată bani sau date.
        Cum vă simțiți azi?" />
  </Connect>
</Response>
```

Numele exacte ale atributelor se verifică în documentația ConversationRelay la implementare.

### 7.3 Mesajele de pe WebSocket

| Direcție | Mesaj | Când |
|---|---|---|
| Twilio → server | `setup` | La deschiderea conexiunii: ID-ul apelului, numerele |
| Twilio → server | `prompt` | Ce a spus omul, deja transcris |
| Twilio → server | `dtmf` | Omul a apăsat o tastă |
| Twilio → server | `interrupt` | Omul a vorbit peste asistent |
| Server → Twilio | `text` | Bucăți din răspunsul agentului; ultima are `last: true` |
| Server → Twilio | `end` | Închiderea sesiunii, de exemplu pentru transferul la un operator |

### 7.4 Apelul, pas cu pas

1. Campania programează apelul, iar dialer-ul îl pornește prin Twilio.
2. Persoana răspunde. Twilio deschide WebSocket-ul și redă salutul.
3. Persoana vorbește. Twilio transcrie și trimite un mesaj `prompt`.
4. **Serverul verifică întâi cuvintele de alarmă**, determinist, și abia apoi trimite textul mai departe.
5. Dacă răspunsul e clar, serverul răspunde direct din șablon. Dacă iese din tipar, răspunde agentul (secțiunea 8.5).
6. Fiecare informație aflată se salvează prin `record_answer`, după care rulează motorul de reguli.
7. Statusul se actualizează live în toate cele trei aplicații.
8. Când lista de verificare e completă, apelul se încheie politicos.
9. Statusul final declanșează escaladarea (secțiunea 10).

### 7.6 Apelurile fără răspuns

Detecția robotului de mesagerie rulează asincron, ca persoana să nu audă tăcere după „alo”. Dacă răspunde un robot, apelul se închide și e tratat ca nepreluat.

| Situație | Ce urmează |
|---|---|
| Nu răspunde sau răspunde robotul | Reapel după 20 de minute |
| A doua oară fără răspuns | Status **neclar**, escaladare către familie |
| Persoana închide în timpul apelului | Se evaluează răspunsurile primite; apelul întrerupt e el însuși un semnal |

---

## 8. Agentul AI

### 8.1 Principiul

**Agentul decide cum vorbește și ce întreabă mai departe. Serverul decide ce se întâmplă cu persoana.** Conversația sună natural, iar deciziile rămân deterministe.

### 8.2 Lista de verificare

| Câmp | Ce trebuie aflat |
|---|---|
| `wellbeing` | Cum se simte acum (bine / rău), cu simptomele spuse |
| `orientation` | Răspunsul la o întrebare de orientare: „Ce zi a săptămânii e azi?” |
| `water` | Dacă are apă și un loc răcoros (sau un loc cald, la ger) |
| `needs` | Dacă are nevoie de medicamente sau cumpărături |
| `location` | Doar dacă nu e acasă: unde se află |

### 8.3 Tool-urile

| Tool | Ce face |
|---|---|
| `record_answer(câmp, valoare, citat)` | Completează lista. „Citat” păstrează exact ce a spus omul. |
| `find_shelter(locație_spusă)` | Caută cel mai apropiat punct de refugiu deschis |
| `notify_family(mesaj)` | Trimite o notificare familiei |
| `escalate_to_das(nivel, motiv)` | Deschide un caz în aplicația DAS |
| `transfer_to_operator(motiv)` | Transferă apelul live la dispecerul DAS |
| `end_call(rezumat)` | Încheie apelul |

### 8.4 Reguli impuse de server

1. **Cuvintele de alarmă** („am căzut”, „durere în piept”, „nu pot respira”, „leșin”) se verifică pe fiecare transcriere, **înainte** ca textul să ajungă la agent. La un cuvânt de alarmă urmează transfer imediat.
2. **După fiecare `record_answer`, rulează motorul de reguli.** Dacă regulile dau roșu, serverul escaladează singur.
3. **Agentul poate escalada oricând, dar nu poate anula o escaladare cerută de reguli.** Poate doar crește nivelul.
4. **`end_call` e refuzat** până când lista e completă sau până la limita de 3 minute. Serverul îi indică agentului întrebarea care lipsește.
5. **Transferul live** se face prin mesajul `end`. Twilio apelează URL-ul din `action`, iar serverul întoarce un `<Dial>` către dispeceratul DAS.
6. **Tasta 9** sau cererea „vreau să vorbesc cu un om” duc oricând la transfer.

Modelul folosit e un **LLM rapid din cloud**, cu răspuns pe bucăți (streaming).

### 8.6 Schița promptului de sistem

> Ești asistentul telefonic al DAS Timișoara. Suni vârstnici singuri în timpul unui cod de caniculă sau ger. Vorbește în română, cald, rar și simplu. Răspunde în cel mult două propoziții scurte. Află, pe rând și natural: cum se simte persoana, ce zi a săptămânii e azi, dacă are apă și un loc răcoros, dacă are nevoie de medicamente sau cumpărături. După fiecare lucru aflat, apelează `record_answer`. Dacă un răspuns e ambiguu, cere confirmare („Am înțeles că nu vă simțiți bine, corect?”). Nu da sfaturi medicale în afara celor de bază (apă, umbră, odihnă). Nu promite nimic. Nu cere niciodată bani, coduri sau date personale. Dacă persoana cere un om, apelează `transfer_to_operator`. Nu încheia apelul până nu ai aflat toate cele patru lucruri.

### 8.7 Exemplu de conversație

| Cine | Ce spune | Ce se întâmplă în spate | Status |
|---|---|---|---|
| Asistentul | „Bună ziua, doamna Maria! Vă sun pentru că azi e cod roșu de caniculă. Cum vă simțiți?” | apelul începe | 🟢 |
| Doamna Maria | „Vai, e greu, n-am dormit toată noaptea de cald.” | răspuns neclar → răspunde LLM-ul | 🟢 |
| Asistentul | „Înțeleg, a fost o noapte grea. Acum, în acest moment, vă simțiți bine sau rău?” | | 🟢 |
| Doamna Maria | „Păi... cam amețită.” | `record_answer(wellbeing = rău, citat = „cam amețită”)` | 🟡 |
| Asistentul | „Îmi pare rău. Ca să știu cum vă pot ajuta: ce zi a săptămânii e azi?” | răspuns din șablon | 🟡 |
| Doamna Maria | „Stați... luni? Nu știu.” | `record_answer(orientation = greșit)` | 🔴 |
| Asistentul | „Vă conectez acum cu un operator, rămâneți pe fir.” | mesaj `end`, apoi `<Dial>` către DAS | 🔴 |

### 8.8 Adăpostul în funcție de locația spusă

Dacă persoana nu e acasă, agentul o întreabă unde se află și apelează `find_shelter`:

1. Din răspuns se extrage strada, reperul („lângă Catedrală”) sau cartierul.
2. Textul se potrivește aproximativ (rapidfuzz) cu lista străzilor și reperelor din Timișoara, preîncărcată din OpenStreetMap.
3. Coordonatele se obțin prin Nominatim, apoi se alege cel mai apropiat punct deschis în acel moment.
4. Agentul confirmă locația („Ați spus lângă Piața Unirii, corect?”) și spune numele locului, distanța și programul.

**Regula de siguranță:** adăpostul se recomandă doar dacă persoana se simte bine, punctul e la câteva sute de metri și persoana nu are mobilitate redusă. Altfel, i se spune să rămână la umbră sau în casă, iar cazul se escaladează cu locația.

**Lista adăposturilor** se editează din aplicația DAS. În vara lui 2026, spațiile de răcorire au fost la Cinema Timiș, Filarmonică, Teatrul German și Teatrul Maghiar, Centrul de Proiecte și containerul din Piața Sf. Gheorghe (program 10–18), plus sediile DAS. În august s-au adăugat Hotel Mercure și sucursalele UniCredit. La ger, logica e aceeași, cu spațiile încălzite.

### 8.9 Latența

Pauza dintre replici se adună din trei părți: Twilio detectează că omul a terminat de vorbit, LLM-ul produce primul cuvânt, apoi ElevenLabs începe să vorbească. Ca să rămână mică:

1. Replicile obișnuite vin din șabloane, fără LLM.
2. Modelul e rapid, iar răspunsul se trimite pe bucăți.
3. Agentul răspunde în cel mult două propoziții.
4. Când un tool e lent, agentul spune întâi „Un moment, vă rog...”.

Pentru măsurare, serverul loghează momentul sosirii fiecărui `prompt`, momentul primului cuvânt de la LLM și momentul trimiterii primului `text`.

**De testat cu vârstnici reali:** vârstnicii fac pauze lungi în mijlocul frazei. Dacă sistemul decide prea repede că omul a terminat, îi taie vorba.

### 8.10 Pronunția

Cu ElevenLabs, tag-urile SSML de pronunție funcționează doar pentru en-US. Cuvintele pronunțate greșit (nume de străzi, „DAS”) se scriu în text așa cum trebuie să sune.

### 8.12 Ce nu face AI-ul

Nu pune diagnostice, nu „detectează emoții” din voce, nu decide escaladarea și nu poate anula o decizie a regulilor.

---

## 9. Statusurile

### 9.1 Cele cinci statusuri

| Status | Când | În timpul apelului | După apel |
|---|---|---|---|
| 🟢 **Verde** | Toate răspunsurile sunt în regulă | Încheiere normală, cu un sfat scurt | Nimic. Următorul apel, conform programului. |
| 🔵 **Sarcină** | Singurul semnal e o nevoie: medicamente sau cumpărături | Apelul continuă normal | Sarcină în coada DAS pentru echipa mobilă. Nu e alarmă, familia nu e alertată. |
| 🟡 **Galben** | Un semnal de îngrijorare, dar nu urgent | Apelul continuă până la final | Escaladare către familie, apoi, dacă e cazul, către DAS |
| 🔴 **Roșu** | Semn de pericol | **Transfer imediat** la dispecer | Caz direct în coada dispeceratului. Familia e anunțată, medicul primește rezumatul. |
| ⚪ **Neclar** | Nicio conversație: nu a răspuns de două ori | — | Aceeași escaladare ca la galben |

Dacă o nevoie apare împreună cu alt semnal, statusul e dat de celălalt semnal, iar sarcina se adaugă separat.

### 9.2 Ce declanșează fiecare status

**🔴 Roșu:**
- un cuvânt de alarmă, oricând în apel;
- nu se simte bine **și** (răspunde greșit la orientare **sau** nu are apă ori loc răcoros).

**🟡 Galben**, la oricare dintre semnalele de mai jos, luat singur:
- nu se simte bine;
- răspunde greșit la întrebarea de orientare;
- nu are apă sau loc răcoros;
- două sau mai multe răspunsuri neclare;
- închide înainte de final;
- cere un om (transferul are loc, cazul rămâne galben);
- de la o zi la alta, un tipar de tipul „ieri bine, azi neclar”.

**La pacienții cu declin cognitiv cunoscut,** răspunsul la întrebarea de orientare se compară cu răspunsurile lor anterioare. Contează schimbarea, nu greșeala în sine.

### 9.3 Cum evoluează statusul în timpul apelului

Statusul pornește verde, se recalculează după fiecare răspuns și **poate doar să crească.** Dacă persoana spune la final „acum parcă mi-e mai bine”, statusul nu scade: într-un sistem de siguranță e preferabilă o alarmă în plus decât una ratată. Statusul final se fixează la încheierea apelului și declanșează escaladarea.

---

## 10. Escaladarea

| Status | Ce se întâmplă |
|---|---|
| 🟢 Verde | Aplicația familiei afișează „Totul e bine azi”. |
| 🔵 Sarcină | Sarcina apare în coada DAS. Aplicația familiei afișează nevoia, fără alarmă. |
| 🟡 Galben / ⚪ Neclar | Familia e alertată în aplicație **și** printr-un apel automat. La apel, familia apasă 1 („Verific eu”) sau 2 („Nu pot”). În aplicație, aceleași opțiuni sunt butoane. |
| 🔴 Roșu | Cazul intră imediat în coada dispeceratului. Familia vede „DAS a preluat cazul”. Medicul primește rezumatul. |

**Fluxul familiei la galben sau neclar:**

1. Familia alege „Verific eu”, din aplicație sau prin tasta 1.
2. Are la dispoziție 30 de minute ca să confirme în aplicație: „E bine” sau „Nu e bine”.
3. „E bine” închide cazul. „Nu e bine” trimite cazul la dispecerat.
4. „Nu pot”, lipsa răspunsului sau lipsa confirmării în 30 de minute trimit cazul automat la dispecerat.

Apelul automat către familie e canalul sigur, pentru că funcționează și fără internet. Aplicația e canalul rapid.

**Sistemul nu sună niciodată singur la 112.** Decizia o ia întotdeauna dispecerul.

---

## 11. Aplicațiile web

Cele trei aplicații fac parte dintr-un **singur proiect React** (Vite + Tailwind), cu trei zone separate și autentificare pe roluri. Clientul API, componentele comune (cardul de status, culorile) și conexiunea live (SSE) sunt scrise o singură dată. Pe iPad și pe telefon, aplicațiile se pot adăuga pe ecranul principal și se deschid fără bara de adrese, ca niște aplicații native.

### 11.1 Aplicația medicului — `/medic` (gândită pentru iPad)

| Ecran | Conținut |
|---|---|
| **Pacienții mei** | Lista pacienților înrolați, cu statusul curent în culori și statusul cererii de înrolare |
| **Pacient nou** | Formularul de înrolare (secțiunea 5): datele pacientului, contactele familiei, documentul, factorii de risc pre-bifați, semnătura, codul QR pentru familie |
| **Fișa pacientului** | Datele, factorii de risc, documentul medical, istoricul apelurilor |
| **Episod** | Statusul, motivele, rezumatul și transcrierea completă a apelului |

Detalii tehnice: încărcarea documentului deschide și camera iPad-ului; semnătura se desenează pe un canvas (de exemplu cu biblioteca signature_pad), cu degetul sau cu Apple Pencil; codul QR se generează în pagină.

### 11.2 Aplicația familiei — `/familie` (gândită pentru telefon)

| Ecran | Conținut |
|---|---|
| **Azi** | Statusul persoanei în culori și o recomandare clară (vezi tabelul de mai jos) |
| **Acțiuni** | „Verific eu”, „E bine”, „Nu e bine”, când există un caz deschis |
| **Istoric** | Ultimele apeluri, pe scurt: data, statusul, motivul |

| Status | Ce vede familia |
|---|---|
| 🟢 Verde | „Totul e bine azi. Nu e nevoie să sunați.” |
| 🔵 Sarcină | „Are nevoie de [medicamente / cumpărături]. DAS a fost anunțat.” |
| 🟡 Galben / ⚪ Neclar | „Sunați-o acum.” + motivul + butoanele de acțiune |
| 🔴 Roșu | „Dispeceratul DAS a preluat cazul. Dacă puteți ajunge la ea, anunțați aici.” |

**Autentificarea** se face fără parolă: codul QR de la cabinet sau linkul de invitație conțin un token care conectează direct telefonul familiei la pacient. **Actualizarea** e live prin SSE cât timp aplicația e deschisă. Notificările push pe web funcționează pe Android, iar pe iPhone doar dacă aplicația e adăugată pe ecranul principal. Apelul automat către familie rămâne canalul garantat.

### 11.3 Aplicația DAS — `/das` (desktop)

| Ecran | Conținut |
|---|---|
| **Cereri de înrolare** | Cererile medicilor: aprobare, alocare pe zonă sau echipă, cerere de completări |
| **Dispecerat** | Harta pacienților activi, colorați după status, și coada de cazuri (roșu sus), cu motivele, rezumatul și transcrierea |
| **Sarcini** | Nevoile (medicamente, cumpărături) de alocat echipelor mobile |
| **Campanii** | Campaniile active; butonul „Simulează cod roșu” pentru demo |
| **Adăposturi** | Lista editabilă a punctelor de răcorire și a spațiilor încălzite |

Acțiunile pe un caz: preluare, trimiterea echipei mobile, apel direct către pacient sau familie, închidere cu notă.

### 11.4 Cine vede ce

| Informație | Familie | Medic | DAS |
|---|---|---|---|
| Statusul și motivul | ✅ | ✅ | ✅ |
| Istoricul apelurilor (pe scurt) | ✅ | ✅ | ✅ |
| Transcrierea apelului | ❌ | ✅ | ✅ |
| Factorii de risc | ❌ | ✅ | ✅ |
| Documentul medical (PDF) | ❌ | ✅ | doar la un caz roșu activ |

Medicul vede doar pacienții proprii. Familia vede doar persoana la care e conectată.

---

## 12. Telefonia

### 12.1 Numărul de telefon

Pentru hackathon se folosește **un număr Twilio din SUA**. Se cumpără instant, fără documente, și poate suna pe telefoane românești.

Un număr românesc cere un pachet de documente (Regulatory Bundle), cu dovada adresei, și o verificare care poate dura zile. În plus, în România **nu se poate suna afișând un număr românesc care nu aparține Twilio**: ghidul Twilio interzice acest lucru, din cauza măsurilor ANCOM împotriva falsificării numărului afișat. Regula ANCOM în vigoare din 7 iulie 2025 blochează apelurile din străinătate care afișează fals numere românești. Un număr +1 nu se prezintă drept număr românesc, deci nu intră sub această regulă.

La pilot, sistemul va suna de pe un număr de Timișoara, cu prefix local.

### 12.2 Configurarea Twilio

| Pas | Ce se face |
|---|---|
| 1 | Cont + card + credit. Contul de probă sună doar numere verificate și redă la început un mesaj în engleză. |
| 2 | Cumpărarea unui număr din SUA |
| 3 | Voice → Geo Permissions: activarea României |
| 4 | Voice → Settings → Privacy & Security: acceptarea termenilor pentru funcții AI („Predictive and Generative AI/ML Features Addendum”). Fără ei, ConversationRelay întoarce eroarea 95250. |
| 5 | Server public cu `wss://` (deploy), cerut de ConversationRelay |

### 12.3 Ce trebuie testat înainte

| Risc | Ce se verifică |
|---|---|
| Cum apare numărul pe ecran | +1, „necunoscut” sau rescris de rețea |
| Etichetarea ca spam | Dacă telefonul marchează apelul drept „posibil spam” |
| Calitatea și întârzierea pe ruta internațională | Se adaugă la latența agentului |
| Semnalul din sala muzeului | Acoperirea pe fiecare rețea |

Testul se face pe câte un telefon din fiecare rețea mare (Orange, Vodafone, Digi).

### 12.4 SMS-urile

Un sender ID cu nume (de exemplu „DAS-TM”) cere în România înregistrare la operatori, cu 9 documente, așa că nu e folosit. Familia e alertată prin aplicație și prin apel automat. SMS-ul e opțional, doar dacă testele arată că ajunge sigur.

### 12.5 Rezervele pentru demo

1. **În demo se sună un telefon al echipei**, pus pe masă pe difuzor, ca toată sala să audă conversația. Un jurat e sunat doar dacă e anunțat înainte.
2. **Telefon în browser** (Twilio Voice SDK): același agent, fără rețea de telefonie.
3. **Varianta A** a apelului, dacă agentul LLM are probleme.
4. **Video înregistrat** cu un flux complet reușit.

---

## 13. Arhitectura

### 13.1 Schema

```
                 Aplicația medicului   Aplicația familiei   Aplicația DAS
                          \                   |                 /
                           \______ HTTP + SSE (live) __________/
                                              |
Avertizare ANM ──► Campanii ──► BACKEND (FastAPI + Postgres)
                                  │      ▲
                     apel (API)   │      │  WebSocket (text)
                                  ▼      │
                             Twilio ConversationRelay
                        (transcriere Google, voce ElevenLabs)
                                  ▲
                                  │ rețeaua de telefonie
                                  ▼
                       Telefonul vârstnicului / al familiei

În backend: dialer · verificare cuvinte de alarmă · șabloane + agent LLM · motor de reguli · escaladare
```

### 13.2 Stack-ul

| Componentă | Tehnologie |
|---|---|
| Telefonie | Twilio Programmable Voice (număr din SUA), ConversationRelay |
| Transcriere și voce | Gestionate de Twilio: transcriere Google, voce ElevenLabs (ro-RO) |
| Agent | LLM rapid din cloud, cu tool calling și streaming |
| Extragerea factorilor de risc | Extragere de text din PDF; pentru fotografii, un model care citește imagini; confirmarea medicului e obligatorie |
| Backend | FastAPI (HTTP, WebSocket, SSE), Postgres, scheduler pentru campanii și reapeluri |
| Frontend | React, Vite, Tailwind; Leaflet pentru hărți; signature_pad; o bibliotecă pentru coduri QR |
| Date geo | OpenStreetMap, Nominatim, rapidfuzz |
| Rezervă pentru apel | Varianta A (`<Gather>`), din scheletul `esti_bine_call_flow.py` |

**Principiul arhitecturii:** stratul de voce se poate înlocui (alt furnizor, alt număr), dar logica (agentul, regulile, escaladarea, aplicațiile) rămâne independentă. DAS nu depinde de un singur furnizor.

### 13.3 Modelul de date

| Entitate | Câmpuri principale |
|---|---|
| **Medic** | nume, cabinet, cont |
| **Pacient** | nume, formă de adresare, telefon, adresă, coordonate, interval orar, medic, factori de risc, document, consimțământ (semnătură, dată), status înrolare |
| **ContactFamilie** | pacient, nume, relație, telefon, token de acces |
| **CerereÎnrolare** | pacient, medic, status, zonă/echipă, observații DAS |
| **Campanie** | tip (caniculă/ger), cod, început, sfârșit |
| **Apel** | pacient, campanie, tip (bun venit/verificare/familie), încercare, status Twilio, transcriere, durată |
| **Răspuns** | apel, câmp, valoare, citat |
| **Caz** | pacient, apel, status, motive, stare (deschis/familie/dispecerat/închis), termen |
| **Sarcină** | pacient, tip (medicamente/cumpărături), stare |
| **Adăpost** | nume, tip (răcorire/încălzit), coordonate, program |

### 13.4 Endpoint-urile principale (orientativ)

| Endpoint | Rol |
|---|---|
| `POST /api/enrollments` | Medicul trimite o cerere de înrolare |
| `POST /api/enrollments/{id}/document` | Încărcarea documentului și extragerea factorilor de risc |
| `POST /api/enrollments/{id}/approve` | DAS aprobă cererea |
| `POST /api/invites/{token}/accept` | Familia se conectează prin QR sau link |
| `POST /api/campaigns/trigger` | Pornirea unei campanii (butonul de demo) |
| `POST /voice/{welcome,checkin,family}` | TwiML pentru fiecare tip de apel |
| `WS /relay` | Conversația ConversationRelay |
| `POST /voice/handoff` | Transferul la dispecer după mesajul `end` |
| `POST /voice/status`, `POST /voice/amd` | Starea apelului și detecția robotului |
| `POST /api/cases/{id}/family-ack` | „Verific eu”, „E bine”, „Nu e bine” |
| `GET /events` | Evenimente live (SSE), filtrate pe rol |
| `GET/PUT /api/shelters` | Lista adăposturilor |

---

## 14. Siguranță, încredere și GDPR

**Protecția împotriva țepelor.** Apelul de bun venit cere salvarea numărului. Asistentul strigă persoana pe nume și anunță din prima frază că nu cere niciodată bani sau date.

**Omul decide mereu.** Cazurile grave ajung la dispecer. Tasta 9 sau cererea „vreau să vorbesc cu cineva” duc la un operator. Sistemul nu sună niciodată singur la 112.

**Consimțământ și date minime.** Consimțământul se semnează la cabinet. Medicul și DAS sunt operatorii de date. Fiecare rol vede minimul necesar (secțiunea 11.4). Nu se stochează înregistrări audio, doar transcrierea și răspunsurile structurate. Locația spusă la telefon se folosește doar pentru acel apel.

**Date de sănătate și AI.** Documentul medical și conversațiile ajung la furnizorul LLM, iar audio-ul trece prin Twilio. În demo se folosesc exclusiv date fictive. La pilot sunt necesare acorduri de prelucrare a datelor cu furnizorii. Un model rulat local e o opțiune pentru a păstra datele la DAS.

---

## 15. Adoptarea și impactul

Dispeceratul non-stop al DAS există deja. Sistemul doar îi aduce în coadă cazurile prioritizate, fără angajați în plus. Medicii de familie au deja pacienții și documentele lor medicale, iar înrolarea durează sub 3 minute. Apelurile funcționează pe orice telefon, deci acoperă exact oamenii rămași în afara soluțiilor digitale.

| Metrică |
|---|
| Procentul pacienților activi contactați în fiecare episod extrem |
| Timpul de la avertizarea ANM până la confirmarea „bine” |
| Numărul de cazuri escaladate și timpul până la intervenție |
| Timpul mediu de înrolare pentru medic |
| Costul pe pacient pe sezon, calculat cu tarifele reale Twilio |

---

## 16. Demo-ul (3–4 minute)

**Dispozitivele de pe masă:** laptopul cu aplicația DAS, iPad-ul cu aplicația medicului, un telefon cu aplicația familiei, telefonul „vârstnicului” pe difuzor și telefonul „dispecerului DAS”.

**Modul demo** comprimă timpii: reapelul vine după 20 de secunde în loc de 20 de minute, iar termenul familiei e de 30 de secunde în loc de 30 de minute.

1. **Hook:** „15 voluntari pentru 275 de seniori. Oamenii nu scalează.”
2. **Înrolarea (~45 s):** pe iPad, medicul încarcă un document fictiv. Factorii de risc apar pre-bifați, iar medicul confirmă. Pacientul semnează. Telefonul familiei scanează codul QR și se conectează. Pe laptop, DAS aprobă cererea, iar **telefonul vârstnicului sună cu apelul de bun venit**.
3. **Cod roșu:** DAS apasă „Simulează cod roșu”. Telefonul de pe difuzor sună, iar asistentul vorbește natural cu „doamna Maria”. Ea spune că e bine, dar e foarte cald și e lângă Catedrală. Asistentul îi recomandă cel mai apropiat punct de răcorire, iar pinul ei și adăpostul apar pe hartă.
4. **Escaladarea:** la al doilea apel, „vârstnicul” spune că e amețit și răspunde confuz la ziua săptămânii. Cardul devine galben, apoi roșu, **în aceeași secundă în toate cele trei aplicații**. Asistentul anunță transferul, iar **telefonul dispecerului sună**. Medicul vede episodul cu transcrierea, iar familia vede „DAS a preluat cazul”.
5. **Fără răspuns:** un al treilea pacient nu răspunde. Urmează reapelul, apoi alerta către familie, iar familia apasă „Verific eu” în aplicație.
6. **Final:** costul pe pacient pe sezon și faptul că nu e nevoie de angajați în plus.

Rezervele sunt în secțiunea 12.5.

---

## 18. Întrebări probabile de la juriu

| Întrebare | Răspuns |
|---|---|
| „Ce se întâmplă dacă LLM-ul greșește?” | LLM-ul doar conduce conversația. Cuvintele de alarmă se verifică înaintea lui, statusul îl dau reguli fixe, iar agentul nu poate anula o escaladare. |
| „Ce faceți cu vârstnicii fără medic de familie?” | Pilotul pornește prin medicii de familie. Înscrierea directă prin DAS e în planul de extindere. |
| „Medicii n-au timp pentru asta.” | Înrolarea durează sub 3 minute: documentul există deja, iar factorii de risc vin pre-completați. |
| „Vârstnicii nu răspund la numere necunoscute.” | Apelul de bun venit cere salvarea numărului, iar asistentul strigă persoana pe nume și anunță din prima că nu cere bani sau date. |
| „De ce un număr din SUA?” | Doar pentru demo, fiindcă se configurează instant. La pilot se sună de pe un număr de Timișoara. |
| „Ce se întâmplă cu cei fără internet?” | Vârstnicul nu are nevoie de internet, doar de semnal pentru apeluri. Și familia e alertată prin apel. |
| „De ce nu Parents are OK?” | Cere smartphone și abonament și alertează doar familia. Aici apelul merge pe orice telefon, iar alerta ajunge și la DAS. |
| „GDPR?” | Consimțământ semnat la cabinet, operatori de date medicul și DAS, acces minim pe roluri, fără înregistrări audio. |
| „Răspunderea medicală?” | Sistemul nu pune diagnostice, orice dubiu se escaladează, iar decizia o ia un om. |

---

## 20. Pregătirea înainte de hackathon

- [ ] Cont Twilio, card, credit, număr din SUA, România la Geo Permissions, termenii pentru funcții AI
- [ ] Testul de telefonie pe Orange, Vodafone și Digi (secțiunea 12.3)
- [ ] Primul apel ConversationRelay în ro-RO, cu vocea ElevenLabs aleasă
- [ ] Test cu 3–5 vârstnici reali: pauzele, cât de natural sună, dacă sistemul le taie vorba
- [ ] Discuție cu DAS (0356.981): câte persoane contactează manual în caniculă, dacă ar folosi un astfel de sistem; o frază de susținere pentru pitch
- [ ] Un medic de familie sau un medic mentor: fluxul de înrolare, factorii de risc, ponderile scorului
- [ ] Regulile hackathonului despre codul scris înainte
- [ ] Datele de demo: 3–4 pacienți fictivi, documente medicale fictive (PDF), JSON cu adăposturile, străzile din Timișoara din OpenStreetMap

---

## 22. Decizii luate pe parcurs

| Variantă analizată | Decizia | Motivul |
|---|---|---|
| Apple Watch ca semnal suplimentar | Scos | Complexitate în 48 de ore; grupul țintă rar are smartwatch |
| Aplicații native iOS și iPadOS | Înlocuite cu aplicații web | Prea mult de construit în 48 de ore; pe iPad și telefon, aplicațiile web arată ca aplicații native |
| Înrolare prin mai multe canale (familie, DAS, medic) | Doar prin medicul de familie | Poveste medicală coerentă, factori de risc credibili, consimțământ la cabinet |
| Număr românesc pentru demo | Număr din SUA; numărul românesc rămâne pentru pilot | Numărul românesc cere documente și o verificare care durează |
| Numărul personal ca Caller ID sau ca gateway | Respins | Interzis de regulile Twilio pentru România; Android nu permite accesul la audio-ul apelurilor |
| Platforme de agenți vocali (ElevenLabs Agents, Retell, Vapi) | Nefolosite; ElevenLabs e folosit doar ca voce, prin Twilio | Control complet asupra regulilor și escaladării |
| Model LLM local | Nefolosit în demo; opțiune pentru pilot | Calitatea în română și fiabilitatea sunt mai bune la un model rapid din cloud |
| Dialogul pe replici (`<Gather>`) | Păstrat ca rezervă | Robust și deja implementat |
| Nevoile tratate ca alarmă | Transformate în sarcini pentru DAS | Coada de urgențe rămâne curată, familia nu e alarmată inutil |

---

## Surse

DAS Timișoara (dispeceratul și echipele mobile), Fundația Regală Margareta a României (Telefonul Vârstnicului), ANM (avertizările meteo), Nature Medicine (decesele legate de căldură în Europa, vara 2022), presa locală din vara lui 2026 (codurile roșii, spațiile de răcorire), documentația Twilio (ConversationRelay, ghidul pentru România, cerințele pentru numere românești, sender ID în România), decizia ANCOM privind apelurile cu număr falsificat (în vigoare din 7 iulie 2025), site-ul UniHack (unihack.eu).
