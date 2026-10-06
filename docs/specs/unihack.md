# Ești bine?

**Sistem de avertizare timpurie pentru bolile provocate de căldură și frig la vârstnicii singuri.** În timpul episoadelor de caniculă și ger, sistemul sună automat persoanele vulnerabile, pe orice telefon, inclusiv pe fix. Detectează semnele de pericol din răspunsurile lor și, opțional, de pe un Apple Watch, apoi escaladează cazurile către familie, medicul de familie și DAS Timișoara.

> Proiect pentru UniHack 8 · Timișoara · 13–15 noiembrie 2026

---

## 1. Contextul hackathonului

UniHack 8 are loc între 13 și 15 noiembrie 2026, la Muzeul Corneliu Mikloși din Timișoara. Durează 48 de ore, iar echipele au între 2 și 4 membri. Proiectele sunt expuse public între 16 și 19 noiembrie. Fiecare track are premiul lui oferit de sponsori, iar pe deasupra se acordă un mare premiu.

**Track principal: Medical Renaissance.** Track-ul cere tehnologie care îmbunătățește îngrijirea pacienților, prevenția și accesul la sănătate. Ne prezentăm ca sistem de prevenție pentru o urgență medicală reală, insolația și hipotermia la vârstnici, nu ca serviciu social.

**Alternative:**

| Track | Condiție |
|---|---|
| Community Hero | Doar dacă o problemă similară (vârstnici singuri, caniculă, lipsa ajutorului) apare pe lista Vocea Cetățenilor. De întrebat pe Discord dacă alegerea din listă e obligatorie. |
| Solve Your Own Problem | Dacă cineva din echipă are un bunic care locuiește singur. Povestea personală e chiar cerința track-ului. |

**De ce putem concura cu proiectele hardware:** demo-ul are un apel telefonic live către un jurat și un Apple Watch care declanșează escaladarea pe scenă. Juriul vede trei dispozitive care lucrează împreună în timp real.

---

## 2. Problema

Vara 2026 a adus în Timiș cod roșu de caniculă, cu 39–41°C și nopți tropicale în care temperatura n-a coborât sub 26°C. În România, aproximativ 1,35 milioane de seniori locuiesc singuri. La nivel european, un studiu publicat în Nature Medicine a estimat peste 60.000 de decese legate de căldură doar în vara lui 2022.

Sistemul actual din Timișoara e reactiv. DAS are un dispecerat non-stop (0356.981), dar vârstnicul trebuie să sune el ca să primească ajutor. Echipele de teren au lucrat luni–vineri, între 08:00 și 16:00, și doar până la sfârșitul lui august. Contactul telefonic cu vârstnicii vulnerabili se face manual.

Oamenii nu scalează. La Telefonul Vârstnicului, 15 voluntari au reușit în 2025 să sune săptămânal doar 275 de seniori.

**Ideea de bază:** cei mai expuși sunt exact cei care nu cer ajutor. Insolația provoacă confuzie, iar izolarea face ca nimeni să nu observe la timp.

### De ce e o problemă medicală

Insolația (heat stroke) e o urgență medicală cu mortalitate mare, iar confuzia acută e semnul-cheie la vârstnici. Factorii de risc la căldură sunt bine documentați:

| Factor de risc |
|---|
| vârsta înaintată |
| bolile cardiovasculare |
| medicamentele care afectează reglarea temperaturii corpului (diuretice, antipsihotice, unele antihipertensive) |
| mobilitatea redusă |
| locuința la ultimul etaj, fără aer condiționat |

---

## 3. Ce există deja și ce lipsește

| Soluție | Cum funcționează | Limita |
|---|---|---|
| Dispeceratul DAS Timișoara | Non-stop, pe apeluri primite | Vârstnicul trebuie să sune el |
| Telefon cu brățară (DAS, pentru beneficiarii de îngrijire la domiciliu) | Buton de panică | Reactiv: un om confuz nu apasă |
| Telefonul Vârstnicului | Voluntari, reapel săptămânal | Axat pe singurătate, nu pe urgențe; nu scalează |
| Parents are OK | Detectează inactivitatea smartphone-ului | Cere smartphone, costă 59,99 lei/lună, alertează doar familia |
| Teleasistență privată | Dispozitiv cu buton SOS | Plătit și reactiv |

**Golul:** niciuna dintre soluții nu sună proactiv și automat, pe orice telefon, la declanșarea avertizărilor meteo, cu evaluarea riscului fiecărei persoane și cu legătură directă la instituțiile care pot interveni.

---

## 4. Soluția pe scurt

Sistemul are trei componente.

**Nivelul 1: apelurile.** Funcționează pentru toată lumea, pe orice telefon, inclusiv pe fix, fără aplicație și fără cost pentru vârstnic. E miezul produsului.

**Nivelul 2: Apple Watch (opțional).** Pentru cine are deja un smartwatch sau îl primește de la familie. Ceasul reacționează înainte ca persoana să fie sunată: puls ridicat în repaus, inactivitate prelungită sau apăsarea unui buton.

**Creierul sistemului.** Un scor de risc personalizat decide pe cine suni și cât de des. AI-ul înțelege răspunsurile date prin voce și detectează confuzia. Reguli deterministe decid escaladarea.

**Încadrarea pentru pitch:** *„sistem de avertizare timpurie pentru bolile provocate de căldură și frig la vârstnici”*.

---

## 5. Fluxul complet

### 5.1 Înscrierea

Persoana poate fi înscrisă prin trei canale:

1. **Medicul de familie.** E canalul medical: medicul cunoaște diagnosticele și medicamentele pacientului.
2. **DAS Timișoara.** Pentru beneficiarii existenți ai serviciilor sociale.
3. **Familia sau un vecin.** Printr-un formular scurt.

La înscriere se completează numele, numărul de telefon, adresa, 1–2 contacte de urgență și intervalul orar preferat pentru apeluri. Opțional, cu consimțământ explicit, se adaugă factorii de risc (boli, categorii de medicamente, mobilitate, tipul locuinței).

La înscriere, vârstnicul își salvează numărul sistemului în telefon, ca să-l recunoască atunci când sună.

### 5.2 Scorul de risc

Pentru fiecare persoană, sistemul calculează un scor din factorii de risc de la înscriere, combinat cu prognoza meteo (indicele de căldură, nopțile tropicale, gerul). Scorul decide ordinea apelurilor și frecvența lor. Ponderile se stabilesc împreună cu un medic mentor. Nu pretindem validare clinică.

### 5.3 Declanșarea

O avertizare ANM de caniculă sau ger pentru Timiș pornește o campanie de apeluri:

| Situație | Frecvența apelurilor |
|---|---|
| Cod galben | 1 apel pe zi |
| Cod roșu | 2 apeluri pe zi, inclusiv seara |
| Scor de risc ridicat | Frecvență mărită |
| În afara episoadelor extreme | Opțional, un apel săptămânal |

### 5.4 Apelul

Apelul durează sub 60 de secunde. Vocea e lentă, iar persoana poate răspunde fie vorbind, fie apăsând taste.

> „Bună ziua, doamna Maria. Sunt asistentul DAS Timișoara. Nu vă cerem niciodată bani sau date. Vă simțiți bine azi?”
>
> „Ce zi e azi?” *(întrebare de orientare, pentru screening-ul de confuzie)*
>
> „Aveți apă și un loc răcoros?”
>
> „Aveți nevoie de medicamente sau cumpărături?”
>
> „Dacă vreți să vorbiți acum cu un operator, apăsați 9.”
>
> La final: un sfat scurt și, dacă e cazul, cel mai apropiat punct de refugiu.

### 5.5 Evaluarea

Răspunsurile trec printr-un motor de reguli deterministe, care atribuie un status: **verde**, **galben** sau **roșu**.

### 5.6 Escaladarea

1. Dacă persoana nu răspunde, sistemul reîncearcă după 20 de minute.
2. După două apeluri fără răspuns sau un răspuns negativ, sistemul trimite SMS și sună familia.
3. Dacă familia nu confirmă, sau dacă statusul e direct roșu, cazul intră în coada dispeceratului DAS. Medicul de familie primește rezumatul.
4. Tasta 9 transferă apelul direct la un om.

**Sistemul nu sună niciodată singur la 112.** Decizia o ia întotdeauna dispecerul.

---

## 6. Componenta AI

Principiul de bază: **AI-ul înțelege ce spune omul, iar deciziile de escaladare le iau reguli fixe.** Nu construim un chatbot liber.

### 6.1 Recunoașterea vocii

Mulți vârstnici nu se descurcă să apese taste. Twilio are recunoașterea vorbirii integrată în `<Gather>`, așa că fiecare întrebare acceptă atât taste, cât și voce:

```xml
<Gather input="dtmf speech" language="ro-RO" speechTimeout="auto"
        hints="da, nu, bine, rău, apă, medicamente" action="/answer?q=1">
```

Callback-ul primește `Digits` sau `SpeechResult`, împreună cu `Confidence`. În `hints` intră cuvintele uzuale și numele străzilor și reperelor din Timișoara, ceea ce îmbunătățește recunoașterea.

**În prima oră a hackathonului testăm calitatea recunoașterii pentru ro-RO.** Dacă e slabă, planul B e să înregistrăm răspunsul și să-l transcriem cu Whisper, care se descurcă bine cu româna, cu prețul unei latențe puțin mai mari.

### 6.2 Înțelegerea răspunsurilor

Un LLM mic și rapid transformă un răspuns liber, de genul „păi nu prea, mă cam doare capul și n-am apă rece”, în date structurate:

```json
{
  "answer": "no",
  "symptoms": ["durere de cap"],
  "needs": ["apă"],
  "is_home": true,
  "location_text": null,
  "orientation_ok": true,
  "unclear": false,
  "summary": "Nu se simte bine, durere de cap, fără apă rece"
}
```

Cât procesează LLM-ul, apelul redă „Un moment, vă rog...”. Tăcerea la telefon îi derutează pe vârstnici.

### 6.3 Plasa de siguranță

O listă fixă de cuvinte de alarmă („durere în piept”, „nu pot respira”, „am căzut”, „leșin”) duce direct la statusul roșu, independent de LLM.

Când sistemul nu înțelege răspunsul, procedează așa:

1. Repetă întrebarea mai rar, o singură dată.
2. Cere răspunsul pe taste.
3. Dacă tot nu reușește, marchează cazul „neclar” și îl escaladează către familie.

**„Neclar” nu înseamnă niciodată „bine”.**

### 6.4 Screening-ul de confuzie

Confuzia acută e semnul-cheie al insolației la vârstnici. Apelul include 1–2 întrebări de orientare, cum ar fi „Ce zi e azi?”, iar sistemul măsoară **timpul de răspuns** și **coerența** răspunsurilor. Rezultatele se compară cu nivelul obișnuit al persoanei, adică cu răspunsurile ei din zilele anterioare.

Sistemul **semnalează o schimbare, nu pune diagnostic**. Cazul ajunge întotdeauna la un om. Metoda se validează împreună cu un medic mentor.

### 6.5 Adăpost în funcție de locația spusă la telefon

Dacă persoana e acasă, sistemul folosește adresa de la înscriere. Dacă nu e acasă:

1. Întreabă: „Unde vă aflați acum? Spuneți strada sau un loc cunoscut.”
2. LLM-ul extrage din răspuns strada, reperul („lângă Catedrală”) sau cartierul.
3. Sistemul face o potrivire aproximativă (rapidfuzz) cu lista străzilor și reperelor din Timișoara, preîncărcată din OpenStreetMap.
4. Obține coordonatele prin Nominatim și alege cel mai apropiat punct deschis în acel moment, după distanța de mers pe jos.
5. Confirmă locația: „Ați spus lângă Piața Unirii, e corect?”
6. Răspunde cu numele locului, distanța aproximativă și ora până la care e deschis.

**Regula de siguranță:** nu trimitem pe jos, la 40°C, un vârstnic care nu se simte bine. Adăpostul se recomandă doar dacă persoana se simte bine și punctul e la câteva sute de metri. Altfel, persoana e sfătuită să rămână la umbră sau în casă, iar cazul se escaladează, împreună cu locația, către echipa mobilă.

**Datele despre adăposturi** sunt într-un fișier JSON. În vara lui 2026, spațiile de răcorire au fost la Cinema Timiș, Filarmonică, Teatrul German și Teatrul Maghiar, Centrul de Proiecte și containerul din Piața Sf. Gheorghe, cu program 10–18. În plus, sediile DAS au funcționat ca puncte de refugiu. În august s-au adăugat Hotel Mercure și sucursalele UniCredit. Pentru că lista se schimbă pe parcursul sezonului, **o facem editabilă din dashboard-ul DAS**. Pentru ger, aceeași logică funcționează cu spațiile încălzite.

### 6.6 Rezumat și tendință

Dispecerul primește un rezumat de o frază, care include motivul urgenței. Sistemul compară și răspunsurile cu zilele anterioare: un tipar de genul „ieri bine, azi neclar” e un semnal de escaladare.

### 6.7 Ce nu face AI-ul

AI-ul nu pune diagnostice, nu „detectează emoții” din voce și nu poartă conversații libere. Toate trei ar atrage întrebări incomode de la juriu și ar reduce încrederea în sistem.

---

## 7. Nivelul 2: Apple Watch

### 7.1 Ce detectează ceasul

| Semnal | Cum îl folosim |
|---|---|
| Puls ridicat în repaus | Pulsul curent se compară cu pulsul de repaus al persoanei din HealthKit, nu cu un prag fix. Un puls mult peste nivelul ei obișnuit, în timp ce stă nemișcată, e un semnal de stres termic. |
| Inactivitate prelungită | Nicio mișcare timp de 4–6 ore în timpul zilei, în timpul unei alerte ANM. |
| Buton „Nu mă simt bine” | O singură atingere pe ecran declanșează escaladarea. |

### 7.2 Ce nu folosim

| Funcție | De ce nu |
|---|---|
| Detectarea căderilor | E integrată în Apple Watch, dar accesul aplicațiilor terțe (`CMFallDetectionManager`) cere un entitlement special de la Apple, pe care nu-l obținem până la hackathon. |
| Temperatura încheieturii | Vine doar ca deviație măsurată noaptea, în somn, nu în timp real. |
| Monitorizarea continuă în fundal | E limitată de watchOS. Pentru puls în timp real e nevoie de un `HKWorkoutSession` activ („mod monitorizare”). Pentru demo e perfect, dar consumă bateria. |

### 7.3 Fluxul

1. Ceasul detectează un semnal.
2. Pe ecran apare o întrebare mare, însoțită de vibrație: **„Sunteți bine?”**, cu butoanele Da și Nu.
3. Dacă persoana nu răspunde în 2 minute sau apasă Nu, backend-ul declanșează apelul „Ești bine?”.
4. Mai departe urmează escaladarea obișnuită: familia, apoi DAS sau medicul.

Tehnic, ceasul trimite evenimentul la backend, fie direct prin Wi-Fi sau rețea mobilă, fie prin iPhone cu WatchConnectivity. Endpoint-ul `/events` trece prin același motor de reguli ca apelurile.

### 7.4 Alarmele false

Un prag bazat doar pe puls dă alarme false, pentru că pulsul crește și când urci scările. De aceea combinăm pulsul cu contextul de mișcare: puls mare fără mișcare e mai suspect decât puls mare în timpul unei plimbări.

### 7.5 Poziționarea

Ceasul e **nivelul 2, nu produsul principal**. Grupul țintă sunt vârstnicii singuri, adesea fără smartphone și fără bani pentru un Apple Watch. Nivelul 1, apelurile, rămâne disponibil pentru toată lumea. Prin Family Setup, un Apple Watch cu cartelă proprie se poate configura de pe iPhone-ul unui membru al familiei, fără ca vârstnicul să aibă iPhone.

Așa, sistemul combină mai multe semnale: **vocea** (confuzia), **ceasul** (pulsul, inactivitatea), **mediul** (indicele de căldură) și **profilul de risc**.

---

## 8. Utilizatori și ecrane

| Utilizator | Ce vede și ce face |
|---|---|
| Vârstnicul | Nu are nimic de instalat, doar răspunde la telefon. Opțional, poartă un Apple Watch. |
| Familia | Primește SMS-uri cu un link către statusul zilei și este sunată la escaladare. |
| Dispecerul DAS | Folosește un dashboard cu harta tuturor celor înscriși, colorați după status. Are o coadă prioritizată (roșu sus), rezumatele apelurilor, un buton „trimite echipa mobilă” și lista editabilă de adăposturi. |
| Medicul de familie | Înscrie pacienții cu risc și primește rezumatul episoadelor. |
| Operatorul de înscriere | Completează un formular scurt (DAS, medic sau familie). |

---

## 9. Arhitectura

```
Avertizare ANM ──┐
Apple Watch ─────┼─► Scheduler / Motor de evenimente ─► Apel Twilio ─► Webhook
                 │                                                        │
Scor de risc ────┘                                                        ▼
                                      Transcriere (Twilio / Whisper) ─► Parser LLM
                                                                          │
                                                                          ▼
                                      Dashboard + SMS ◄── Status ◄── Motor de reguli
```

| Componentă | Tehnologie |
|---|---|
| Telefonie | Twilio Voice (taste + voce ro-RO), Twilio SMS |
| Backend | FastAPI, Postgres, APScheduler pentru campanii; webhook-urile Twilio sunt expuse prin ngrok sau un deploy rapid |
| AI | LLM mic și rapid pentru parsarea răspunsurilor și rezumate; Whisper ca plan B pentru transcriere |
| Date geo | Străzile și reperele din OpenStreetMap, geocodare prin Nominatim, potrivire aproximativă cu rapidfuzz, JSON cu adăposturile |
| Frontend | React și Leaflet, cu actualizare live prin SSE |
| Ceas | App watchOS în SwiftUI, cu HealthKit și HKWorkoutSession; comunicare directă cu backend-ul sau prin WatchConnectivity |
| Avertizări ANM | Buton „simulează cod roșu” pentru demo; scraper pe meteoromania.ro doar dacă rămâne timp |

---

## 10. Siguranță, încredere și GDPR

**Protecția împotriva țepelor.** Vârstnicul salvează numărul sistemului în telefon la înscriere. Apelul îl strigă pe nume și anunță din prima secundă că nu cere niciodată bani sau date.

**Omul decide mereu.** Orice caz grav ajunge la dispecer, iar tasta 9 îl pune pe vârstnic în legătură directă cu un operator. Sistemul nu sună singur la 112.

**Date minime.** DAS și medicul de familie sunt operatorii de date. Factorii de risc sunt date de sănătate, deci se colectează doar cu consimțământ explicit. Nu stocăm înregistrări audio, doar răspunsurile structurate. Locația spusă la telefon se folosește doar pentru acel apel. Pentru demo folosim exclusiv date fictive.

---

## 11. De ce poate fi adoptat

Dispeceratul non-stop al DAS există deja. „Ești bine?” doar îi aduce în coadă cazurile prioritizate, fără angajați în plus. Sistemul funcționează pe orice telefon, deci acoperă exact oamenii rămași în afara soluțiilor digitale. Același sistem merge pentru ger, pentru apeluri săptămânale împotriva singurătății și în orice alt oraș.

### Cum măsurăm impactul

| Metrică |
|---|
| Procentul celor înscriși contactați în fiecare episod extrem |
| Timpul de la avertizarea ANM până la confirmarea „bine” |
| Numărul de cazuri escaladate și timpul până la intervenție |
| Costul pe vârstnic pe sezon, calculat cu tariful real Twilio pentru România înainte de pitch |

---

## 12. Demo-ul (3–4 minute)

1. **Hook:** „15 voluntari pentru 275 de seniori. Oamenii nu scalează.”
2. **Apple Watch:** un coleg poartă ceasul pe scenă. Pulsul crește (aleargă pe loc sau simulăm valorile), ceasul vibrează și întreabă „Sunteți bine?”, iar colegul nu răspunde. **Câteva secunde mai târziu sună telefonul**, iar cardul din dashboard devine roșu.
3. **Apel către un jurat, cu adăpost:** apăsăm „Cod roșu” și sună telefonul unui jurat. Juratul spune „Sunt bine, dar e foarte cald, sunt lângă Catedrală”. Sistemul îi recomandă cel mai apropiat punct de refugiu, iar pe hartă apar simultan pin-ul lui și adăpostul.
4. **Confuzie și simptome:** un coleg răspunde confuz la întrebarea de orientare și spune „Nu mă simt bine, am amețeli”. Cazul devine roșu, cu rezumat generat automat. Pleacă SMS-ul către familie, iar cazul intră în coada dispeceratului.
5. **Fără răspuns:** un al treilea „vârstnic” nu răspunde, iar sistemul reîncearcă și escaladează.
6. **Final:** costul pe vârstnic pe sezon și faptul că dispeceratul non-stop există deja, deci nu trebuie angajat nimeni.

Tastele funcționează mereu ca rezervă: dacă sala e zgomotoasă, demo-ul merge oricum. Înregistrăm și un video de backup al demo-ului.

---

## 13. Planul pe 48h și rolurile

| Când | Ce facem |
|---|---|
| Vineri seara | Apelul outbound cu input pe taste, funcțional cap-coadă. E cel mai mare risc, deci îl facem primul. |
| Sâmbătă dimineața | Motorul de reguli, escaladarea, SMS-urile. |
| Sâmbătă după-amiaza | Vocea și parserul LLM, apoi dashboard-ul. App-ul pentru Apple Watch, în paralel. |
| Sâmbătă seara | Locația și adăposturile, screening-ul de confuzie. |
| Sâmbătă noaptea | Scorul de risc și declanșatorul ANM, doar dacă restul e stabil. |
| Duminică dimineața | Freeze, repetiția pitch-ului, video de backup al demo-ului. |

**Roluri propuse:**

| Rol | Cine |
|---|---|
| Backend, telefonie, parser LLM | Alex |
| App watchOS | [de stabilit] |
| Dashboard React | [de stabilit] |
| Scriptul apelului, testarea cu vârstnici, pitch | [de stabilit] |

---

## 14. Întrebări probabile de la juriu

| Întrebare | Răspuns |
|---|---|
| „Vârstnicii nu răspund la numere necunoscute, de frica țepelor.” | Numărul e salvat în telefonul lor la înscriere, apelul îi strigă pe nume și anunță din prima că nu cere bani sau date. |
| „De ce nu Parents are OK?” | Cere smartphone și abonament și alertează doar familia. Noi funcționăm pe orice telefon, gratuit, iar alerta ajunge la DAS și la medic, care pot interveni. |
| „Cine le cumpără bătrânilor Apple Watch?” | Ceasul e nivelul 2, opțional. Nivelul 1, apelurile, merge pe orice telefon. Prin Family Setup, familia poate configura ceasul fără ca vârstnicul să aibă iPhone. |
| „Unde e partea medicală?” | Stratificarea riscului pe baza factorilor clinici, screening-ul de confuzie comparat cu nivelul obișnuit al persoanei, semnalele de la ceas și integrarea cu medicul de familie. |
| „GDPR?” | DAS și medicul sunt operatorii de date, cu consimțământ explicit la înscriere. Colectăm minimul necesar și nu stocăm înregistrări audio. |
| „Alarme false?” | Escaladarea merge întâi la familie. La ceas, pulsul se combină cu contextul de mișcare. |
| „Răspunderea medicală?” | Sistemul nu pune diagnostice, orice dubiu se escaladează, iar decizia o ia întotdeauna un om. |

---

## 15. Riscuri tehnice

| Risc | Ce facem |
|---|---|
| Recunoaștere slabă a vorbirii în română | Tastele sunt mereu disponibile, folosim `hints`, planul B e Whisper |
| Latență la apel | LLM mic și rapid, plus mesajul „Un moment, vă rog...” |
| Contul de probă Twilio sună doar numere verificate | Cont cu credit pentru telefonul juratului |
| Zgomot în sală la demo | Rezervă pe taste și video de backup |
| Bateria ceasului în modul de monitorizare | Mod de monitorizare doar în alertă; în demo nu contează |

---

## 16. De făcut înainte de hackathon

- [ ] **Sunăm la DAS (0356.981)** și întrebăm: câte persoane contactează manual în caniculă, câți oameni se ocupă de asta, ar folosi un astfel de sistem? O frază de susținere de la ei intră în pitch.
- [ ] **Căutăm un medic mentor** pentru scorul de risc și screening-ul de confuzie.
- [ ] **Testăm scriptul apelului cu 3–5 bunici reali.**
- [ ] **Facem cont Twilio**, cu credit pentru telefonul juratului, și calculăm costul pe apel.
- [ ] **Întrebăm pe Discord:** e obligatoriu, pe Community Hero, să alegem o problemă din lista Vocea Cetățenilor?
- [ ] **Verificăm regula** despre codul scris înainte de hackathon.
- [ ] **Pregătim datele:** lista de adăposturi (JSON), străzile din Timișoara din OpenStreetMap, persoane fictive pentru demo.
- [ ] **Prezentăm ideea ca „caniculă și ger”**, pentru că în noiembrie gerul e de actualitate.

---

## 17. După hackathon

Primul pas e un pilot cu DAS Timișoara, pe un grup mic de beneficiari, în sezonul de ger. După aceea, extindem înscrierea prin medicii de familie și prin canalele Primăriei. Pe termen lung, sistemul poate face apeluri săptămânale împotriva singurătății, în afara episoadelor extreme, și poate fi preluat de alte orașe.

---

## Surse de verificat

DAS Timișoara (dispeceratul și echipele mobile din caniculă), Fundația Regală Margareta a României (Telefonul Vârstnicului), ANM (avertizările meteo), Nature Medicine (decesele legate de căldură în Europa, vara 2022), presa locală din vara lui 2026 (codurile roșii, spațiile de răcorire), site-ul UniHack (unihack.eu).
