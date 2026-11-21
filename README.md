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

1. **Ta en uppgift.** Skriv `/claim` först på en rad i issuen. Då blir den din och syns på tavlan. Fler kommandon: `/join` (vara med på en uppgift som någon annan har, till exempel en granskning), `/waiting @namn` (du väntar på någon), `/back`, `/done` och `/release`.
2. **Ge feedback** i issuen. Hänvisa till numren i mockuperna (A1, B3 …), till exempel "A3: Utveckling känns för formellt".
3. **Ändra text** i en pull request: gör en fork av repot (knappen *Fork* uppe till höger), ändra i en egen gren och öppna en pull request hit. Skriv "Fixes #17" i beskrivningen, så kopplas den till issuen. Sprintmastern (Jonathan) granskar och godkänner.
4. **Med en AI-agent?** Öppna repot i den (Claude Code, Codex, Cursor, Copilot …). Den läser `AGENTS.md` och vet hur sprinten fungerar. Med Claude Code och Devsprinter-pluginet syns agentens framsteg på issuen av sig själv.

Varje pull request får en automatisk kontroll som pekar ut dold text, skript och ändringar i filer utanför texterna. Läs mer om säkerheten i `AGENTS.md`.

Där det står **TBC** saknas ett svar från styrelsen. Frågorna finns samlade sist i dokumentet och som issues med etiketten `styrelsen`.

## Mappen `devsprinter/` och `.github/`

Det är tavlan: en GitHub Action som håller issuen *Sprint board* aktuell. Den rör inte texterna.
