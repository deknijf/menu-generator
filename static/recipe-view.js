/* Gedeelde weergavelogica voor recepten.
 *
 * Wordt gebruikt door de detailpagina (meal_detail.html) en het formulier voor
 * nieuwe maaltijden (index.html). Staat los van app.js omdat de detailpagina
 * die niet laadt.
 *
 * Twee vormen per veld:
 *   - bewerken: platte tekst in een textarea, makkelijk te typen op een telefoon
 *   - bekijken: nette tabel voor ingredienten, genummerde stappen voor de bereiding
 */
(function (global) {
  "use strict";

  const MIN_SERVINGS = 1;
  const MAX_SERVINGS = 6;
  const DEFAULT_SERVINGS = 2;

  function escapeHtml(value) {
    return String(value == null ? "" : value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function clampServings(value, fallback) {
    const number = Number.parseInt(value, 10);
    if (!Number.isFinite(number)) return fallback == null ? DEFAULT_SERVINGS : fallback;
    return Math.min(MAX_SERVINGS, Math.max(MIN_SERVINGS, number));
  }

  /* Hoeveelheden netjes tonen: geen 0.30000000000000004, geen "2.0". */
  function formatQuantity(value) {
    const number = Number(value || 0);
    if (!Number.isFinite(number) || number === 0) return "";
    const rounded = Math.round(number * 100) / 100;
    return String(rounded).replace(".", ",");
  }

  /* Korte naam van de bron, om als pill te tonen.
   * https://dagelijksekost.vrt.be/... -> "dagelijksekost"
   * https://www.joshuaweissman.com/... -> "joshuaweissman"
   * geen bron -> "custom" (zelf ingevoerd) */
  function sourceLabel(sourceUrl) {
    const ruw = String(sourceUrl || "").trim();
    if (!ruw) return "custom";
    let host = "";
    try {
      host = new URL(ruw).hostname.toLowerCase();
    } catch (err) {
      return "custom";
    }
    host = host.replace(/^www\./, "");
    const eerste = host.split(".")[0];
    return eerste || "custom";
  }

  // --- Ingredienten ---

  function parseIngredients(text) {
    return String(text || "")
      .split("\n")
      .map((line) => line.trim())
      .filter(Boolean)
      .map((line) => {
        const parts = line.split(",").map((part) => part.trim());
        return {
          name: parts[0] || "",
          quantity: Number(String(parts[1] || "0").replace(",", ".")) || 0,
          unit: parts[2] || "",
        };
      })
      .filter((item) => item.name);
  }

  function ingredientsToText(ingredients) {
    return (ingredients || [])
      .map((item) => [item.name, item.quantity, item.unit].join(", "))
      .join("\n");
  }

  /* scale = gekozen porties / porties van het recept. */
  function renderIngredientsTable(ingredients, scale) {
    const factor = Number.isFinite(scale) && scale > 0 ? scale : 1;
    const rows = (ingredients || []).filter((item) => item && item.name);
    if (!rows.length) {
      return '<p class="muted">Nog geen ingredienten ingevuld.</p>';
    }
    const body = rows
      .map((item) => {
        const amount = formatQuantity(Number(item.quantity || 0) * factor);
        return (
          "<tr>" +
          `<td class="ing-name">${escapeHtml(item.name)}</td>` +
          `<td class="ing-qty">${escapeHtml(amount)}</td>` +
          `<td class="ing-unit">${escapeHtml(item.unit || "")}</td>` +
          "</tr>"
        );
      })
      .join("");
    return (
      '<table class="ingredients-table">' +
      "<thead><tr><th>Naam</th><th>Aantal</th><th>Eenheid</th></tr></thead>" +
      `<tbody>${body}</tbody>` +
      "</table>"
    );
  }

  // --- Bereidingswijze ---
  //
  // Elke stap is een blok tekst, gescheiden door een lege regel. Een blok mag
  // beginnen met "## Eigen titel"; anders wordt het "Stap N". Regels die met
  // - of * beginnen worden opsommingstekens. **vet** werkt inline.

  function parseSteps(text) {
    return String(text || "")
      .replace(/\r\n/g, "\n")
      .split(/\n\s*\n/)
      .map((block) => block.trim())
      .filter(Boolean);
  }

  function stepsToText(steps) {
    return (steps || [])
      .map((step) => String(step).trim())
      .filter(Boolean)
      .join("\n\n");
  }

  function renderInline(text) {
    // Eerst escapen, daarna pas opmaak toepassen: anders is **<script>** een gat.
    return escapeHtml(text).replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
  }

  function renderSteps(steps) {
    const blocks = (steps || []).map((step) => String(step).trim()).filter(Boolean);
    if (!blocks.length) {
      return '<p class="muted">Nog geen bereidingswijze ingevuld.</p>';
    }

    let nummer = 0;
    const html = blocks
      .map((block) => {
        const lines = block.split("\n").map((line) => line.trim()).filter(Boolean);
        let titel = "";
        // Expliciete titel met # of ##
        const kop = lines[0] && lines[0].match(/^#{1,3}\s+(.*)$/);
        if (kop) {
          titel = kop[1];
          lines.shift();
        } else {
          // "Stap 2" bovenaan een blok zelf getypt: gebruiken als titel.
          const eigenStap = lines[0] && lines[0].match(/^stap\s*\d+\s*:?\s*$/i);
          if (eigenStap) {
            titel = lines[0];
            lines.shift();
          }
        }
        nummer += 1;
        if (!titel) titel = `Stap ${nummer}`;

        let body = "";
        let bullets = [];
        const flushBullets = () => {
          if (!bullets.length) return;
          body += `<ul>${bullets.map((b) => `<li>${renderInline(b)}</li>`).join("")}</ul>`;
          bullets = [];
        };
        lines.forEach((line) => {
          const bullet = line.match(/^[-*]\s+(.*)$/);
          if (bullet) {
            bullets.push(bullet[1]);
            return;
          }
          flushBullets();
          body += `<p>${renderInline(line)}</p>`;
        });
        flushBullets();

        return (
          '<li class="prep-step">' +
          `<h4 class="prep-step-title">${escapeHtml(titel)}</h4>` +
          `<div class="prep-step-body">${body}</div>` +
          "</li>"
        );
      })
      .join("");

    return `<ol class="prep-steps">${html}</ol>`;
  }

  // --- Portie-stepper: pijltje omhoog boven, omlaag onder ---

  function createServingsStepper(options) {
    const opts = options || {};
    const wrap = document.createElement("div");
    wrap.className = "servings-stepper";

    let waarde = clampServings(opts.value, DEFAULT_SERVINGS);

    const up = document.createElement("button");
    up.type = "button";
    up.className = "servings-arrow servings-up";
    up.setAttribute("aria-label", "Een persoon meer");
    up.innerHTML = '<span aria-hidden="true">▲</span>';

    const down = document.createElement("button");
    down.type = "button";
    down.className = "servings-arrow servings-down";
    down.setAttribute("aria-label", "Een persoon minder");
    down.innerHTML = '<span aria-hidden="true">▼</span>';

    const readout = document.createElement("div");
    readout.className = "servings-readout";

    const arrows = document.createElement("div");
    arrows.className = "servings-arrows";
    arrows.appendChild(up);
    arrows.appendChild(down);

    wrap.appendChild(readout);
    wrap.appendChild(arrows);

    function teken() {
      readout.innerHTML =
        `<span class="servings-value">${waarde}</span>` +
        `<span class="servings-label">${waarde === 1 ? "persoon" : "personen"}</span>`;
      up.disabled = waarde >= MAX_SERVINGS;
      down.disabled = waarde <= MIN_SERVINGS;
      wrap.dataset.servings = String(waarde);
    }

    function zet(next) {
      const volgende = clampServings(next, waarde);
      if (volgende === waarde) return;
      waarde = volgende;
      teken();
      if (typeof opts.onChange === "function") opts.onChange(waarde);
    }

    up.addEventListener("click", () => zet(waarde + 1));
    down.addEventListener("click", () => zet(waarde - 1));
    teken();

    return {
      element: wrap,
      get value() {
        return waarde;
      },
      set value(next) {
        zet(next);
      },
    };
  }

  global.RecipeView = {
    MIN_SERVINGS,
    MAX_SERVINGS,
    DEFAULT_SERVINGS,
    escapeHtml,
    sourceLabel,
    clampServings,
    formatQuantity,
    parseIngredients,
    ingredientsToText,
    renderIngredientsTable,
    parseSteps,
    stepsToText,
    renderSteps,
    createServingsStepper,
  };
})(window);
