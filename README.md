# OpenSverige: vilka vi är, vad vi är och hur vi agerar

> **Work in progress.** Det här är ett utkast för diskussion i OpenSverige-teamet. Inget här är beslutat eller publicerat på opensverige.se.
>
> **Testrepo.** Här testar vi samtidigt [Devsprinter](https://github.com/jbmathisen/devsprinter), ett sätt att se vem som jobbar med vad. Originalet ligger i [opensverige-whitepaper](https://github.com/jbmathisen/opensverige-whitepaper) och uppdateras när sprinten är klar.

Ett förslag på hur OpenSverige kan berätta vad communityt och föreningen är. Det består av ett dokument och mockups som visar hur det kan synas på sajten och i sociala medier.

## Innehåll

| Fil | Vad |
|---|---|
| `index.html` | Översikt, börja här |
| `a-om-sidan.html` | Förslag A: en ny om-sida (opensverige.se/om) |
| `b-startsidan.html` | Förslag B: placering på startsidan, i menyn och i sidfoten |
| `c-sociala-medier.html` | Förslag C: fem kort för LinkedIn och Instagram |
| `dokument.html` | Texten allt bygger på, med frågor till styrelsen |
| `infomote.html`, `infomote-punkter.md` | Presentationen och punkterna från infomötet 12 november |
| `PR-varfor.md` | Utkast till en PR mot opensverige.se: vad opensverige är, på /varfor |

## Så tittar du

Öppna `index.html` i en webbläsare. Ingen server eller installation behövs.

## Så bidrar du

Allt arbete finns som issues. Den fästa issuen **Sprint board** visar vem som har vad och vad som är ledigt.

| Etikett | Betyder |
|---|---|
| `ready` | Ledig. Vem som helst får ta den. |
| `granskning` | Läs och ge feedback. |
| `text` | Skriv eller ändra text. |
| `styrelsen` | Behöver ett svar eller ett beslut från styrelsen. Alla får tycka till i kommentarerna. |

### Med din AI (enklast)

**Du behöver:** ett GitHub-konto, [GitHub CLI](https://cli.github.com/) inloggad (`gh auth login`), git och Python 3.10 eller nyare. Din AI kan hjälpa dig att installera det som saknas.

1. Gör en fork av repot (knappen *Fork* uppe till höger) och klona den.
2. Öppna mappen i din AI-assistent (Claude Code, Codex, Cursor, Copilot …). Den läser `AGENTS.md` och sköter sprinten åt dig.
3. Prata som vanligt:
   - *"Vad finns att göra?"* eller *"Vad kan jag granska?"*
   - *"Visa dashboarden."* Du får en webbsida med hela sprinten: vem som gör vad, öppna pull requests, lediga uppgifter och det som väntar på styrelsen.
   - *"Jag tar 15."*
   - *"Jag kör fast, jag behöver styrelsens svar."*
   - *"Jag är klar."* Din AI visar texten eller ändringen och lämnar in den efter ditt ja: feedback som en kommentar i issuen, ändringar som en pull request.

Du behöver inte kunna några kommandon. Sprintmastern (Jonathan) granskar och godkänner.

### Utan AI

- **Ta en uppgift:** skriv `/claim` ensamt på en rad i issuen. Då blir den din och syns på tavlan. Vill du vara med på en som någon annan har: `/join`. Klar: `/done`.
- **Ge feedback** i issuen. Hänvisa till numren i mockuperna (A1, B3 …), till exempel "A3: Utveckling känns för formellt".
- **Ändra text** i en pull request från din fork. Skriv "Fixes #17" i beskrivningen, så kopplas den till issuen.

Varje pull request får en automatisk kontroll som pekar ut dold text, skript och ändringar i filer utanför texterna. Läs mer om säkerheten i `AGENTS.md`.

Där det står **TBC** saknas ett svar från styrelsen. Frågorna finns samlade sist i dokumentet och som issues med etiketten `styrelsen`.

## Mappen `devsprinter/` och `.github/`

Det är tavlan: en GitHub Action som håller issuen *Sprint board* aktuell. Den rör inte texterna.
