/* Tekstveld waarin elke komma de ingetypte tekst omzet in een pill met kruisje.
 *
 * Enter en Tab doen hetzelfde als een komma. Spatie niet: dan zou "gerookte
 * zalm" in twee losse pills uiteenvallen. Backspace in een leeg veld haalt de
 * laatste pill weg, zoals in een adresveld van een mailprogramma.
 */
(function () {
  function splits(tekst) {
    return String(tekst || "")
      .split(",")
      .map((deel) => deel.trim().toLowerCase())
      .filter(Boolean);
  }

  function koppel(root, opties) {
    const instellingen = opties || {};
    const invoer = root.querySelector("input");
    if (!invoer) return null;
    let waarden = [];

    function meld() {
      if (typeof instellingen.opWijziging === "function") instellingen.opWijziging(waarden.slice());
    }

    function teken() {
      root.querySelectorAll(".chip-tag").forEach((pill) => pill.remove());
      waarden.forEach((waarde, index) => {
        const pill = document.createElement("span");
        pill.className = "chip-tag";
        const tekst = document.createElement("span");
        tekst.textContent = waarde;
        const knop = document.createElement("button");
        knop.type = "button";
        knop.setAttribute("aria-label", `Verwijder ${waarde}`);
        knop.textContent = "×";
        knop.addEventListener("click", () => {
          waarden.splice(index, 1);
          teken();
          meld();
        });
        pill.append(tekst, knop);
        root.insertBefore(pill, invoer);
      });
    }

    function voegToe(tekst) {
      const nieuwe = splits(tekst).filter((token) => !waarden.includes(token));
      if (!nieuwe.length) return;
      waarden = waarden.concat(nieuwe);
      teken();
      meld();
    }

    invoer.addEventListener("keydown", (event) => {
      if (event.key === "," || event.key === "Enter" || event.key === "Tab") {
        if (!invoer.value.trim()) return;
        event.preventDefault();
        voegToe(invoer.value);
        invoer.value = "";
      } else if (event.key === "Backspace" && !invoer.value && waarden.length) {
        waarden.pop();
        teken();
        meld();
      }
    });

    // Wie het veld verlaat zonder komma verwacht toch dat zijn woord blijft staan.
    invoer.addEventListener("blur", () => {
      if (!invoer.value.trim()) return;
      voegToe(invoer.value);
      invoer.value = "";
    });

    invoer.addEventListener("paste", (event) => {
      const tekst = event.clipboardData && event.clipboardData.getData("text");
      if (!tekst || tekst.indexOf(",") === -1) return;
      event.preventDefault();
      voegToe(tekst);
    });

    root.addEventListener("click", (event) => {
      if (event.target === root) invoer.focus();
    });

    waarden = splits((instellingen.waarden || []).join(","));
    teken();

    return {
      waarden: () => waarden.slice(),
      zet: (lijst) => {
        waarden = splits((lijst || []).join(","));
        teken();
        meld();
      },
    };
  }

  window.ChipInput = { koppel, splits };
})();
