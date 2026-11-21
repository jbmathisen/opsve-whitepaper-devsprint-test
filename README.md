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

1. **Ta en uppgift.** Skriv "Jag tar den" i issuen, eller tilldela dig själv om du kan. Då syns den som din på tavlan.
2. **Ge feedback** i issuen. Hänvisa till numren i mockuperna (A1, B3 …), till exempel "A3: Utveckling känns för formellt".
3. **Ändra text** i en pull request. Länka issuen med "Fixes #12". Jonathan granskar och godkänner.
4. **Med Claude Code?** Installera Devsprinter-pluginet och skriv `/devsprinter:claim 12`. Då syns din agents framsteg på issuen av sig själv.

Där det står **TBC** saknas ett svar från styrelsen. Frågorna finns samlade sist i dokumentet och som issues med etiketten `styrelsen`.

## Mappen `devsprinter/` och `.github/`

Det är tavlan: en GitHub Action som håller issuen *Sprint board* aktuell. Den rör inte texterna.
