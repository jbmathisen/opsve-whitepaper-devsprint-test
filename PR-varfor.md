# PR: Vad opensverige är, på /varfor

**Gren:** `feature/vad-opensverige-ar` i en lokal klon av `opensverige/webbplats`
**Mot:** `opensverige/webbplats` `main`
**Öppnas som:** draft, så vi granskar den tillsammans

---

## Vad

Två nya avsnitt på [/varfor](https://opensverige.se/varfor), mellan grundarens text och Vanliga frågor:

1. **Ett community och en förening.** Vad Discorden är, vad föreningen är och vad den gör, och att medlemskapet är gratis med frivillig avgift.
2. **Så håller vi på.** Fem principer: det du delar är ditt, ingen säljer något, ingen köper sig plats, öppet för alla, var schysst.

Plus en ny fråga i Vanliga frågor, *Måste jag bli medlem för att vara med?*, som också ligger i FAQPage-datan.

## Varför

Sidan förklarar varför opensverige finns, men inte vad det är. Många blandar ihop Discorden och föreningen. Texten bygger på utkastet "Vilka vi är" och tar bara med det som redan står i [stadgarna](https://opensverige.se/stadgar) (§2, §3, §4, §10) och [reglerna](https://opensverige.se/regler). Inget nytt är påhittat.

Grundarens text är orörd.

## Att granska tillsammans

- [ ] **Placering.** Här på /varfor, eller en egen sida /om, som i förslag A i utkastet?
- [ ] **Tonen i grundarens text.** Utkastet föreslår att vi undviker "mellanhänder", "bygga bort", "survival mode", jämförelser med konsultbolag och "inget liknande i Sverige". Alla finns på /varfor i dag. Ändra, eller låt det vara grundarens röst?
- [ ] **Siffrorna.** Beskrivningen säger 600+ builders, texten 700+. Vilken gäller?
- [ ] **Grundår.** Personschemat säger att opensverige grundades 2025, föreningen bildades 23 april 2026. Båda stämmer nog, men ska det synas?
- [ ] **Principer som inte är med.** "Rollen följer vad du gör", "vi lyfter varandra" och "kritik mot bygget, inte personen" finns i utkastet men inte i reglerna. Ska de in?

## Kontroll

- `python tools/verifiera.py`: inga nya fel. De tio felen om saknade logotyper i `index.html` finns även på `main`, eftersom logotyperna inte ligger i repot.
- JSON-LD parsar.
- `sitemap.xml` är inte ändrad. `verifiera.py` sätter dagens datum på alla sidor; det får den som deployar ta.
- Förhandsgranskad lokalt.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
