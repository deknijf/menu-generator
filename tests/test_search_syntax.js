/* Losse controle van de zoek-parser uit static/app.js.
 *
 * Draaien: node tests/test_search_syntax.js
 *
 * De rest van de frontend heeft geen testopzet, en die hier optuigen is meer werk
 * dan het waard is. De parser is wel de plek waar een fout stil verkeerde
 * resultaten geeft, dus die controleren we apart. De logica staat hieronder
 * opnieuw; houd ze gelijk met parseZoekQuery/komtOvereen in app.js.
 */

function parseZoekQuery(ruw) {
  const tokens = String(ruw || "")
    .split(/([&|!])/)
    .map((t) => t.trim())
    .filter(Boolean);

  const groepen = [[]];
  let negeer = false;
  for (const token of tokens) {
    if (token === "&") continue;
    if (token === "|") {
      groepen.push([]);
      negeer = false;
      continue;
    }
    if (token === "!") {
      negeer = true;
      continue;
    }
    groepen[groepen.length - 1].push({ term: token.toLowerCase(), negeer });
    negeer = false;
  }
  return groepen.filter((groep) => groep.length);
}

function komtOvereen(tekst, groepen) {
  if (!groepen.length) return true;
  return groepen.some((groep) =>
    groep.every(({ term, negeer }) => {
      const gevonden = tekst.includes(term);
      return negeer ? !gevonden : gevonden;
    })
  );
}

const zoek = (tekst, query) => komtOvereen(tekst.toLowerCase(), parseZoekQuery(query));

const gevallen = [
  // [omschrijving, tekst, query, verwacht]
  ["losse term vindt", "kip met tomaat", "kip", true],
  ["losse term mist", "vis met prei", "kip", false],
  ["en: beide aanwezig", "kip met tomaat", "kip & tomaat", true],
  ["en: een ontbreekt", "kip met prei", "kip & tomaat", false],
  ["of: eerste raak", "kip met prei", "kip | vis", true],
  ["of: tweede raak", "vis met prei", "kip | vis", true],
  ["of: geen van beide", "soep met brood", "kip | vis", false],
  ["niet: sluit uit", "kip met citroen", "kip ! citroen", false],
  ["niet: laat door", "kip met tomaat", "kip ! citroen", true],
  ["voorbeeld uit de opdracht", "kip met tomaat en look", "kip & tomaat ! citroen", true],
  ["voorbeeld, met citroen", "kip met tomaat en citroen", "kip & tomaat ! citroen", false],
  ["en bindt sterker dan of", "vis met prei", "kip & tomaat | vis", true],
  ["term van twee woorden", "stoemp van zoete aardappel", "zoete aardappel", true],
  ["lege query toont alles", "wat dan ook", "", true],
  ["alleen spaties toont alles", "wat dan ook", "   ", true],
  ["alleen een operator", "wat dan ook", "&", true],
  ["hoofdletters maken niet uit", "Kip met Tomaat", "KIP & tomaat", true],
  ["enkel uitsluiten", "vis met prei", "! kip", true],
  ["enkel uitsluiten, raak", "kip met prei", "! kip", false],
];

let gezakt = 0;
for (const [naam, tekst, query, verwacht] of gevallen) {
  const uitkomst = zoek(tekst, query);
  if (uitkomst !== verwacht) {
    gezakt += 1;
    console.error(`FAIL  ${naam}\n      tekst="${tekst}" query="${query}" -> ${uitkomst}, verwacht ${verwacht}`);
  }
}

console.log(`${gevallen.length - gezakt}/${gevallen.length} geslaagd`);
process.exit(gezakt ? 1 : 0);
