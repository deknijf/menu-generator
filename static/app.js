const state = {
  user: null,
  days: [],
  plan: [],
  shopping: [],
  shoppingCounter: 0,
  settings: null,
  profileAllergies: [],
  customMeals: [],
  selectedCustomMealIds: [],
  profileMenuMode: "ai_only",
  customMealsCount: 0,
};
const sidebarStorageKey = "sidebar_collapsed";

const mealImages = {
  grilled_chicken_salad: "https://images.unsplash.com/photo-1546793665-c74683f339c1?auto=format&fit=crop&w=600&q=80",
  salmon_broccoli: "https://images.unsplash.com/photo-1467003909585-2f8a72700288?auto=format&fit=crop&w=600&q=80",
  turkey_stir_fry: "https://images.unsplash.com/photo-1512058564366-18510be2db19?auto=format&fit=crop&w=600&q=80",
  beef_zoodles: "https://images.unsplash.com/photo-1473093295043-cdd812d0e601?auto=format&fit=crop&w=600&q=80",
  lentil_chicken_soup: "https://images.unsplash.com/photo-1547592180-85f173990554?auto=format&fit=crop&w=600&q=80",
  cod_spinach: "https://images.unsplash.com/photo-1519708227418-c8fd9a32b7a2?auto=format&fit=crop&w=600&q=80",
  chicken_pasta: "https://images.unsplash.com/photo-1621996346565-e3dbc353d2e5?auto=format&fit=crop&w=600&q=80",
  beef_rice_bowl: "https://images.unsplash.com/photo-1512058564366-18510be2db19?auto=format&fit=crop&w=600&q=80",
  baked_potato_cod: "https://images.unsplash.com/photo-1604503468506-a8da13d82791?auto=format&fit=crop&w=600&q=80",
  spaghetti_bolognaise: "https://images.unsplash.com/photo-1621996346565-e3dbc353d2e5?auto=format&fit=crop&w=600&q=80",
};

const fallbackMealImage = "https://images.unsplash.com/photo-1498837167922-ddd27525d352?auto=format&fit=crop&w=600&q=80";
const rotationLimitLabels = {
  "2_per_week": "max 2x/week",
  "1_per_week": "max 1x/week",
  "1_per_month": "max 1x/maand",
};

function iso(d) {
  return d.toISOString().slice(0, 10);
}

function parseIsoDate(isoDate) {
  const [year, month, day] = isoDate.split("-").map(Number);
  return new Date(year, month - 1, day);
}

function formatDateEu(isoDate) {
  const [year, month, day] = isoDate.split("-");
  return `${day}/${month}/${year}`;
}

function weekdayShort(isoDate) {
  const date = parseIsoDate(isoDate);
  const names = ["zo", "ma", "di", "wo", "do", "vr", "za"];
  return names[date.getDay()];
}

function prettyQuantity(value) {
  return Number.isInteger(value) ? String(value) : value.toFixed(1);
}

function isFishMeal(name) {
  const needle = (name || "").toLowerCase();
  return needle.includes("zalm") || needle.includes("kabeljauw") || needle.includes("vis") || needle.includes("cod");
}

function getWeekMonday(date) {
  const clone = new Date(date);
  const day = clone.getDay();
  const mondayOffset = day === 0 ? -6 : 1 - day;
  clone.setDate(clone.getDate() + mondayOffset);
  return clone;
}

function mealImageFor(item) {
  if (!item) return fallbackMealImage;
  if (item.image_url && String(item.image_url).trim()) return item.image_url;
  if (item.meal_image) return item.meal_image;
  if (item.meal_id && mealImages[item.meal_id]) return mealImages[item.meal_id];
  const haystack = ingredientHaystack(item);
  if (hasAny(haystack, ["kabeljauw", "cod"])) return mealImages.cod_spinach;
  if (hasAny(haystack, ["zalm", "salmon"])) return mealImages.salmon_broccoli;
  if (hasAny(haystack, ["spaghetti", "pasta", "penne", "fusilli"])) return mealImages.spaghetti_bolognaise || mealImages.chicken_pasta;
  if (hasAny(haystack, ["kip", "chicken"])) return mealImages.grilled_chicken_salad;
  if (hasAny(haystack, ["runder", "beef", "rund"])) return mealImages.beef_zoodles;
  if (hasAny(haystack, ["kalkoen", "turkey"])) return mealImages.turkey_stir_fry;
  if (hasAny(haystack, ["rijst", "rice"])) return mealImages.beef_rice_bowl;
  if (hasAny(haystack, ["aardappel", "krieltjes", "potato"])) return mealImages.baked_potato_cod;
  if (hasAny(haystack, ["linzen", "lentil", "soep"])) return mealImages.lentil_chicken_soup;
  return fallbackMealImage;
}

function hasAny(text, tokens) {
  return tokens.some((token) => text.includes(token));
}

function ingredientHaystack(item) {
  const chunks = [];
  chunks.push((item?.meal_name || item?.name || "").toLowerCase());

  if (Array.isArray(item?.ingredients)) {
    item.ingredients.forEach((ing) => chunks.push(String(ing?.name || "").toLowerCase()));
  }

  if (item?.meal_id && String(item.meal_id).startsWith("custom_")) {
    const custom = state.customMeals.find((m) => m.id === item.meal_id);
    if (custom) {
      chunks.push(String(custom.name || "").toLowerCase());
      (custom.ingredients || []).forEach((ing) => chunks.push(String(ing?.name || "").toLowerCase()));
    }
  }

  return chunks.join(" ");
}

function bindImageFallback(img, item) {
  img.addEventListener("error", () => {
    if (img.dataset.fallbackApplied === "1") return;
    img.dataset.fallbackApplied = "1";
    const inferred = mealImageFor({ ...item, image_url: "" });
    img.src = inferred === img.src ? fallbackMealImage : inferred;
  });
}

function splitCsvText(value) {
  return (value || "")
    .split(",")
    .map((x) => x.trim())
    .filter(Boolean);
}

function splitLinesText(value) {
  return (value || "")
    .split("\n")
    .map((x) => x.trim())
    .filter(Boolean);
}

function isAiGeneratedMeal(item) {
  const id = String(item?.meal_id || item?.id || "");
  return !id.startsWith("custom_");
}

function shoppingBaseKey(item) {
  const name = String(item.name || "").trim().toLowerCase();
  const unit = String(item.unit || "").trim().toLowerCase();
  return `${name}|${unit}`;
}

function shoppingUiItem(item, order, previousByBaseKey = {}) {
  const baseKey = shoppingBaseKey(item);
  const prev = previousByBaseKey[baseKey];
  state.shoppingCounter += 1;
  return {
    ...item,
    __id: `${baseKey}|${state.shoppingCounter}`,
    __baseKey: baseKey,
    __order: order,
    __checked: prev ? !!prev.__checked : false,
  };
}

function normalizeShoppingItems(rawItems) {
  const prevByBaseKey = {};
  state.shopping.forEach((item) => {
    prevByBaseKey[item.__baseKey] = item;
  });

  return (rawItems || []).map((item, index) => shoppingUiItem(item, index, prevByBaseKey));
}

function sortedShoppingItems() {
  return state.shopping
    .slice()
    .sort((a, b) => {
      if (a.__checked !== b.__checked) return a.__checked ? 1 : -1;
      return a.__order - b.__order;
    });
}

function parseIngredientsText(text) {
  const lines = (text || "")
    .split("\n")
    .map((x) => x.trim())
    .filter(Boolean);

  const out = [];
  for (const line of lines) {
    let parts = line.split(",").map((x) => x.trim());
    if (parts.length < 3 && line.includes("|")) {
      parts = line.split("|").map((x) => x.trim());
    }
    out.push({
      name: parts[0] || "",
      quantity: Number(parts[1] || 0),
      unit: parts[2] || "",
    });
  }
  return out.filter((i) => i.name);
}

function setDefaultDates() {
  const today = new Date();
  const start = getWeekMonday(today);
  const end = new Date(start);
  end.setDate(end.getDate() + 6);
  document.getElementById("start-date").value = iso(start);
  document.getElementById("end-date").value = iso(end);
  updateRangePreview();
}

function updateRangePreview() {
  const start = document.getElementById("start-date").value;
  const end = document.getElementById("end-date").value;
  if (!start || !end) return;
  document.getElementById("range-preview").textContent = `Periode: ${formatDateEu(start)} - ${formatDateEu(end)} (start maandag)`;
}

function bindTabs() {
  const tabs = Array.from(document.querySelectorAll(".tab"));
  tabs.forEach((tab) => {
    tab.addEventListener("click", () => {
      const target = tab.dataset.tab;
      tabs.forEach((t) => t.classList.remove("active"));
      tab.classList.add("active");
      document.querySelectorAll(".tab-panel").forEach((panel) => panel.classList.remove("active"));
      document.getElementById(`tab-${target}`).classList.add("active");
    });
  });
}

function activateTab(name) {
  const tab = document.querySelector(`.tab[data-tab="${name}"]`);
  if (tab) tab.click();
}

function setSidebarCollapsed(collapsed) {
  document.body.classList.toggle("sidebar-collapsed", collapsed);
  const toggle = document.getElementById("sidebar-toggle");
  const label = document.getElementById("sidebar-toggle-text");
  if (toggle) {
    toggle.setAttribute("aria-pressed", collapsed ? "true" : "false");
    toggle.title = collapsed ? "Uitklappen" : "Inklappen";
  }
  if (label) {
    label.textContent = collapsed ? "Uitklappen" : "Inklappen";
  }
  localStorage.setItem(sidebarStorageKey, collapsed ? "1" : "0");
}

function initSidebarToggle() {
  const toggle = document.getElementById("sidebar-toggle");
  if (!toggle) return;
  const collapsed = localStorage.getItem(sidebarStorageKey) === "1";
  setSidebarCollapsed(collapsed);
  toggle.addEventListener("click", () => {
    const next = !document.body.classList.contains("sidebar-collapsed");
    setSidebarCollapsed(next);
  });
}

function getPersonCount() {
  return parseInt(document.getElementById("person-count").value, 10) || 2;
}

function getMealOptions() {
  const preferFish = document.getElementById("opt-fish").checked;
  return {
    prefer_fish: preferFish,
    high_protein: document.getElementById("opt-protein").checked,
    low_carb: document.getElementById("opt-low-carb").checked,
    min_fish: preferFish ? 1 : 0,
    person_count: getPersonCount(),
  };
}

async function fetchSession() {
  const res = await fetch("/api/session");
  const data = await res.json();
  if (!data.user) {
    window.location.href = "/login";
    return;
  }

  state.user = data.user;
  document.getElementById("user-info").textContent = `${state.user.name}`;
  document.getElementById("profile-user").textContent = `${state.user.name} (${state.user.email})`;
  document.getElementById("profile-role").textContent = state.user.is_admin ? "Admin" : "Gebruiker";
}

async function fetchProfileSettings() {
  const res = await fetch("/api/settings");
  if (!res.ok) return;
  const data = await res.json();
  state.settings = data;

  document.getElementById("profile-admin").textContent = data.auth?.admin_email || "-";
  const allowed = data.auth?.allowed_emails || [];
  document.getElementById("profile-allowed").textContent = allowed.length ? allowed.join(", ") : "-";

  const baseServings = data.app?.base_servings || 2;
  if (!document.getElementById("person-count").value) {
    document.getElementById("person-count").value = String(baseServings);
  }

  state.profileAllergies = data.profile?.allergies || [];
  document.getElementById("profile-allergies").value = state.profileAllergies.join(", ");
  document.getElementById("profile-likes").value = (data.profile?.likes || []).join(", ");
  state.profileMenuMode = data.profile?.menu_mode || "ai_only";
  state.customMealsCount = Number(data.profile?.custom_meals_count || 0);
  updateProfileMenuModeOptions();
}

function updateProfileMenuModeOptions() {
  const select = document.getElementById("profile-menu-mode");
  const help = document.getElementById("profile-menu-mode-help");
  if (!select || !help) return;
  const count = Number(state.customMealsCount || 0);
  const opt2 = select.querySelector('option[value="ai_and_custom"]');
  const opt3 = select.querySelector('option[value="custom_only"]');
  if (opt2) opt2.disabled = count < 1;
  if (opt3) opt3.disabled = count < 8;

  let mode = state.profileMenuMode || "ai_only";
  if (mode === "custom_only" && count < 8) mode = count >= 1 ? "ai_and_custom" : "ai_only";
  if (mode === "ai_and_custom" && count < 1) mode = "ai_only";
  state.profileMenuMode = mode;
  select.value = mode;

  help.textContent = `Je hebt momenteel ${count} eigen ${count === 1 ? "maaltijd" : "maaltijden"}.`;
}

async function saveProfileAllergies() {
  const raw = document.getElementById("profile-allergies").value;
  const allergies = splitCsvText(raw).map((item) => item.toLowerCase());
  const likesRaw = document.getElementById("profile-likes").value;
  const likes = splitCsvText(likesRaw).map((item) => item.toLowerCase());
  const menu_mode = document.getElementById("profile-menu-mode").value;

  const res = await fetch("/api/profile", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ allergies, likes, menu_mode }),
  });

  const status = document.getElementById("profile-save-status");
  if (!res.ok) {
    try {
      const err = await res.json();
      status.textContent = err.error || "Opslaan mislukt.";
    } catch {
      status.textContent = "Opslaan mislukt.";
    }
    return;
  }

  const data = await res.json();
  state.profileAllergies = data.allergies || [];
  document.getElementById("profile-likes").value = (data.likes || []).join(", ");
  state.profileMenuMode = data.menu_mode || state.profileMenuMode;
  state.customMealsCount = Number(data.custom_meals_count || state.customMealsCount || 0);
  updateProfileMenuModeOptions();
  status.textContent = "Opgeslagen.";
  setTimeout(() => {
    status.textContent = "";
  }, 1800);
}

async function loadCustomMeals() {
  const prevSelected = new Set(state.selectedCustomMealIds || []);
  const res = await fetch("/api/custom-meals");
  if (!res.ok) return;
  const data = await res.json();
  state.customMeals = data.items || [];
  state.customMealsCount = state.customMeals.length;
  updateProfileMenuModeOptions();
  state.selectedCustomMealIds = state.customMeals
    .map((meal) => meal.id)
    .filter((mealId) => prevSelected.has(mealId));
  renderCustomMeals();
  updateCustomMealDeleteButton();
}

function renderCustomMeals() {
  const root = document.getElementById("custom-meals-list");
  if (!root) return;
  root.innerHTML = "";

  if (!state.customMeals.length) {
    root.innerHTML = "<p class='muted'>Nog geen eigen maaltijden aangemaakt.</p>";
    return;
  }

  state.customMeals.forEach((meal) => {
    const selected = state.selectedCustomMealIds.includes(meal.id);
    const card = document.createElement("article");
    card.className = `menu-card menu-card-selectable${selected ? " selected" : ""}`;

    const link = document.createElement("a");
    link.className = "menu-card-link";
    link.href = `/meal/${encodeURIComponent(meal.id)}?person_count=${encodeURIComponent(String(getPersonCount()))}`;
    const img = document.createElement("img");
    img.src = mealImageFor(meal);
    img.alt = meal.name;
    bindImageFallback(img, meal);

    const body = document.createElement("div");
    body.className = "menu-card-body";
    body.innerHTML = `
      <h4>${meal.name}</h4>
      <p>${meal.description || "Eigen maaltijd"}</p>
      <p>${rotationLimitLabels[meal.rotation_limit] || rotationLimitLabels["1_per_week"]}</p>
    `;

    const checkboxWrap = document.createElement("label");
    checkboxWrap.className = "meal-select-check";
    checkboxWrap.innerHTML = `<input type="checkbox" ${selected ? "checked" : ""} /><span aria-hidden="true"></span>`;
    checkboxWrap.addEventListener("click", (event) => event.stopPropagation());
    const checkbox = checkboxWrap.querySelector("input");
    checkbox.addEventListener("change", () => {
      toggleCustomMealSelection(meal.id, checkbox.checked);
    });

    link.appendChild(img);
    link.appendChild(body);
    card.appendChild(link);
    card.appendChild(checkboxWrap);
    root.appendChild(card);
  });
}

function toggleCustomMealSelection(mealId, checked) {
  const current = new Set(state.selectedCustomMealIds || []);
  if (checked) current.add(mealId);
  else current.delete(mealId);
  state.selectedCustomMealIds = Array.from(current);
  updateCustomMealDeleteButton();
  renderCustomMeals();
}

function updateCustomMealDeleteButton() {
  const btn = document.getElementById("cm-delete-btn");
  if (!btn) return;
  const count = (state.selectedCustomMealIds || []).length;
  btn.disabled = count === 0;
  btn.textContent = count > 0 ? `Verwijder (${count})` : "Verwijder";
}

async function deleteSelectedCustomMeals() {
  const ids = state.selectedCustomMealIds || [];
  if (!ids.length) return;
  const status = document.getElementById("cm-save-status");
  const res = await fetch("/api/custom-meals", {
    method: "DELETE",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ meal_ids: ids }),
  });

  if (!res.ok) {
    status.textContent = "Verwijderen mislukt.";
    return;
  }

  state.selectedCustomMealIds = [];
  status.textContent = "Maaltijden verwijderd.";
  await loadCustomMeals();
  setTimeout(() => {
    status.textContent = "";
  }, 2000);
}

function toggleBulkPanel() {
  const panel = document.getElementById("cm-bulk-panel");
  const btn = document.getElementById("cm-bulk-toggle-btn");
  if (!panel || !btn) return;
  const nextHidden = !panel.hidden;
  panel.hidden = nextHidden;
  btn.textContent = nextHidden ? "Bulk upload" : "Sluit bulk upload";
}

async function uploadBulkTemplate() {
  const raw = document.getElementById("cm-bulk-json").value || "";
  const status = document.getElementById("cm-bulk-status");
  let items;
  try {
    items = JSON.parse(raw);
  } catch (error) {
    status.textContent = "Template is geen geldige JSON.";
    return;
  }

  if (!Array.isArray(items) || !items.length) {
    status.textContent = "Template moet een niet-lege lijst zijn.";
    return;
  }

  const res = await fetch("/api/custom-meals/bulk", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ items }),
  });

  if (!res.ok) {
    status.textContent = "Bulk upload mislukt.";
    return;
  }

  const payload = await res.json();
  const created = payload.created || 0;
  const errors = payload.errors || [];
  status.textContent = errors.length
    ? `${created} toegevoegd, ${errors.length} met fout.`
    : `${created} gerechten toegevoegd.`;
  await loadCustomMeals();
}

async function createCustomMeal() {
  const payload = {
    name: document.getElementById("cm-name").value.trim(),
    description: document.getElementById("cm-description").value.trim(),
    image_url: document.getElementById("cm-image-url").value.trim(),
    protein: Number(document.getElementById("cm-protein").value || 0),
    carbs: Number(document.getElementById("cm-carbs").value || 0),
    calories: Number(document.getElementById("cm-calories").value || 0),
    tags: splitCsvText(document.getElementById("cm-tags").value).map((x) => x.toLowerCase()),
    allergens: splitCsvText(document.getElementById("cm-allergens").value).map((x) => x.toLowerCase()),
    ingredients: parseIngredientsText(document.getElementById("cm-ingredients").value),
    preparation: splitLinesText(document.getElementById("cm-preparation").value),
    rotation_limit: document.getElementById("cm-rotation-limit").value,
  };

  const status = document.getElementById("cm-save-status");
  if (!payload.name) {
    status.textContent = "Naam is verplicht.";
    return;
  }

  const res = await fetch("/api/custom-meals", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

  if (!res.ok) {
    status.textContent = "Opslaan mislukt.";
    return;
  }

  status.textContent = "Maaltijd opgeslagen.";
  document.getElementById("cm-name").value = "";
  document.getElementById("cm-description").value = "";
  document.getElementById("cm-image-url").value = "";
  document.getElementById("cm-image-file").value = "";
  document.getElementById("cm-image-filename").textContent = "Geen bestand gekozen";
  document.getElementById("cm-tags").value = "";
  document.getElementById("cm-allergens").value = "";
  document.getElementById("cm-ingredients").value = "";
  document.getElementById("cm-preparation").value = "";
  document.getElementById("cm-rotation-limit").value = "1_per_week";
  await loadCustomMeals();

  setTimeout(() => {
    status.textContent = "";
  }, 2000);
}

function initCustomMealUpload() {
  const pickBtn = document.getElementById("cm-upload-btn");
  const input = document.getElementById("cm-image-file");
  const hidden = document.getElementById("cm-image-url");
  const label = document.getElementById("cm-image-filename");
  if (!pickBtn || !input || !hidden || !label) return;

  pickBtn.addEventListener("click", () => input.click());
  input.addEventListener("change", () => {
    const file = input.files && input.files[0];
    if (!file) return;
    if (!file.type.startsWith("image/")) {
      label.textContent = "Kies een geldige afbeelding.";
      input.value = "";
      hidden.value = "";
      return;
    }

    const reader = new FileReader();
    reader.onload = () => {
      hidden.value = String(reader.result || "");
      label.textContent = file.name;
    };
    reader.onerror = () => {
      hidden.value = "";
      label.textContent = "Upload mislukt.";
    };
    reader.readAsDataURL(file);
  });
}

async function loadCalendar() {
  const start = document.getElementById("start-date").value;
  const end = document.getElementById("end-date").value;
  const res = await fetch(`/api/calendar?start=${start}&end=${end}`);
  const data = await res.json();
  state.days = data.days || [];

  const plannedFromCalendar = state.days
    .filter((day) => day.meal_name)
    .map((day) => ({
      date: day.date,
      meal_name: day.meal_name,
      meal_id: day.meal_id,
      meal_image: day.meal_image,
      explanation: "Geplande maaltijd.",
    }));

  if (!state.plan.length) {
    state.plan = plannedFromCalendar;
  }

  updateRangePreview();
  renderCalendar();
  renderPlan();
  renderDashboard();
}

function renderCalendar() {
  const root = document.getElementById("calendar");
  root.innerHTML = "";

  const headers = ["maandag", "dinsdag", "woensdag", "donderdag", "vrijdag", "zaterdag", "zondag"];
  headers.forEach((label) => {
    const h = document.createElement("div");
    h.className = "weekday-header";
    h.textContent = label;
    root.appendChild(h);
  });

  if (!state.days.length) return;

  const firstDate = parseIsoDate(state.days[0].date);
  const weekday = firstDate.getDay();
  const mondayIndex = weekday === 0 ? 6 : weekday - 1;

  for (let i = 0; i < mondayIndex; i++) {
    const spacer = document.createElement("div");
    spacer.className = "day-spacer";
    root.appendChild(spacer);
  }

  state.days.forEach((day) => {
    const el = document.createElement("div");
    el.className = `day ${day.cook ? "cook" : "skip"}`;
    const retryDisabled = !day.cook ? "disabled" : "";
    el.innerHTML = `
      <span class="day-top">
        <strong>${formatDateEu(day.date)}</strong>
        <em>${weekdayShort(day.date)}</em>
      </span>
      <span class="day-state">${day.cook ? "Koken" : "Niet koken"}</span>
      <span class="day-meal">${day.meal_name || "Nog geen maaltijd"}</span>
      <span class="day-actions"><button class="retry-btn" ${retryDisabled} type="button">Opnieuw</button></span>
    `;

    el.addEventListener("click", async () => {
      await fetch(`/api/calendar/${day.date}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ cook: !day.cook }),
      });
      await loadCalendar();
    });

    const retryBtn = el.querySelector(".retry-btn");
    retryBtn.addEventListener("click", async (event) => {
      event.preventDefault();
      event.stopPropagation();
      if (!day.cook) return;
      retryBtn.disabled = true;
      retryBtn.textContent = "...";

      const res = await fetch(`/api/calendar/${day.date}/retry`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ options: getMealOptions(), person_count: getPersonCount() }),
      });

      if (res.ok) {
        const payload = await res.json();
        const item = payload.item;
        const idx = state.plan.findIndex((p) => p.date === item.date);
        if (idx >= 0) state.plan[idx] = item;
        else state.plan.push(item);
      }

      await loadCalendar();
    });

    root.appendChild(el);
  });
}

function renderMenuGallery() {
  const root = document.getElementById("menu-gallery");
  if (!root) return;
  root.innerHTML = "";

  if (!state.plan.length) {
    root.innerHTML = "<p class='muted'>Genereer maaltijden om de preview te zien.</p>";
    return;
  }

  state.plan
    .slice()
    .sort((a, b) => a.date.localeCompare(b.date))
    .slice(0, 4)
    .forEach((item) => {
      const hasMealId = !!item.meal_id;
      const card = document.createElement(hasMealId ? "a" : "article");
      card.className = "menu-card menu-card-link";
      if (hasMealId) {
        card.href = `/meal/${encodeURIComponent(item.meal_id)}?date=${encodeURIComponent(formatDateEu(item.date))}&person_count=${encodeURIComponent(String(getPersonCount()))}`;
      }
      const img = document.createElement("img");
      img.src = mealImageFor(item);
      img.alt = item.meal_name;
      bindImageFallback(img, item);
      const body = document.createElement("div");
      body.className = "menu-card-body";
      const badge = isAiGeneratedMeal(item) ? `<span class="ai-badge">✦ AI</span>` : "";
      body.innerHTML = `<div class="menu-card-head"><h4>${item.meal_name}</h4>${badge}</div><p>${formatDateEu(item.date)}</p>`;
      card.appendChild(img);
      card.appendChild(body);
      root.appendChild(card);
    });
}

function renderPlan() {
  const list = document.getElementById("plan-list");
  list.innerHTML = "";

  if (!state.plan.length) {
    list.innerHTML = "<li>Nog geen maaltijden gepland.</li>";
    renderMenuGallery();
    return;
  }

  state.plan
    .slice()
    .sort((a, b) => a.date.localeCompare(b.date))
    .forEach((item) => {
      const li = document.createElement("li");
      const info = item.explanation || "Geplande maaltijd.";
      const detailUrl = item.meal_id
        ? `/meal/${encodeURIComponent(item.meal_id)}?date=${encodeURIComponent(formatDateEu(item.date))}&person_count=${encodeURIComponent(String(getPersonCount()))}`
        : "";

      const wrapperTag = detailUrl ? "a" : "div";
      const wrapper = document.createElement(wrapperTag);
      wrapper.className = `plan-link${detailUrl ? "" : " is-static"}`;
      if (detailUrl) wrapper.href = detailUrl;
      const badge = isAiGeneratedMeal(item) ? `<span class="ai-badge plan-ai-badge">✦ AI</span>` : "";
      wrapper.innerHTML = `
        <img alt="${item.meal_name}" />
        <div class="plan-content">
          <div class="plan-title">
            <span class="plan-date">${formatDateEu(item.date)}</span>
            <span class="plan-name">${item.meal_name}</span>
            ${badge}
          </div>
          <small>${info}</small>
        </div>
        <span class="plan-arrow" aria-hidden="true">›</span>
      `;
      const img = wrapper.querySelector("img");
      if (img) {
        img.src = mealImageFor(item);
        bindImageFallback(img, item);
      }
      li.appendChild(wrapper);
      list.appendChild(li);
    });

  renderMenuGallery();
}

function renderShopping() {
  const list = document.getElementById("shopping-list");
  const sideList = document.getElementById("side-shopping-list");
  list.innerHTML = "";
  if (sideList) sideList.innerHTML = "";

  if (!state.shopping.length) {
    list.innerHTML = "<li>Genereer eerst je boodschappenlijst.</li>";
    if (sideList) sideList.innerHTML = "<li>Nog geen items.</li>";
    return;
  }

  const ordered = sortedShoppingItems();

  ordered.forEach((item, idx) => {
    const li = document.createElement("li");
    li.className = item.__checked ? "shopping-item checked" : "shopping-item";
    li.innerHTML = `
      <label class="shop-checkline">
        <input type="checkbox" ${item.__checked ? "checked" : ""} />
        <span class="shop-text">${item.name}</span>
      </label>
      <strong class="shop-qty">${prettyQuantity(item.quantity)} ${item.unit}</strong>
    `;

    const checkbox = li.querySelector("input[type='checkbox']");
    checkbox.addEventListener("change", () => {
      item.__checked = checkbox.checked;
      renderShopping();
    });

    list.appendChild(li);

    if (sideList && idx < 6) {
      const sli = document.createElement("li");
      sli.className = item.__checked ? "checked" : "";
      sli.innerHTML = `<span>${item.name}</span><strong>${prettyQuantity(item.quantity)} ${item.unit}</strong>`;
      sideList.appendChild(sli);
    }
  });
}

function renderDashboard() {
  const cookDays = state.days.filter((d) => d.cook).length;
  const skipDays = state.days.filter((d) => !d.cook).length;
  const planned = state.days.filter((d) => d.meal_name).length;
  const fishMeals = state.days.filter((d) => isFishMeal(d.meal_name)).length;
  const completion = cookDays === 0 ? 0 : Math.round((planned / cookDays) * 100);

  document.getElementById("metric-cook-days").textContent = String(cookDays);
  document.getElementById("metric-skip-days").textContent = String(skipDays);
  document.getElementById("metric-planned").textContent = String(planned);
  document.getElementById("metric-fish").textContent = String(fishMeals);
  document.getElementById("metric-completion").textContent = `${completion}%`;
  document.getElementById("completion-bar").style.width = `${Math.min(completion, 100)}%`;
}

async function generateMeals() {
  const payload = {
    start: document.getElementById("start-date").value,
    end: document.getElementById("end-date").value,
    options: getMealOptions(),
  };

  const res = await fetch("/api/generate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const data = await res.json();
  state.plan = data.plan || [];

  renderPlan();
  activateTab("dashboard");
  await loadCalendar();
}

async function generateShoppingList() {
  const payload = {
    start: document.getElementById("start-date").value,
    end: document.getElementById("end-date").value,
    person_count: getPersonCount(),
  };

  const res = await fetch("/api/shopping-list", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const data = await res.json();
  state.shopping = normalizeShoppingItems(data.items || []);

  renderShopping();
  activateTab("shopping");
}

function addExtraShoppingItem() {
  const nameEl = document.getElementById("extra-item-name");
  const qtyEl = document.getElementById("extra-item-qty");
  const unitEl = document.getElementById("extra-item-unit");

  const name = (nameEl.value || "").trim();
  if (!name) return;

  const quantity = Number(qtyEl.value || 1);
  const unit = (unitEl.value || "stuk").trim();
  const nextOrder = state.shopping.length
    ? Math.max(...state.shopping.map((i) => i.__order || 0)) + 1
    : 0;

  state.shopping.push(
    shoppingUiItem(
      { name, quantity, unit },
      nextOrder,
      {},
    ),
  );

  nameEl.value = "";
  qtyEl.value = "";
  unitEl.value = "";
  renderShopping();
}

async function boot() {
  initSidebarToggle();
  initCustomMealUpload();
  bindTabs();
  setDefaultDates();
  await fetchSession();
  await fetchProfileSettings();
  await loadCustomMeals();
  await loadCalendar();
  renderShopping();

  document.getElementById("start-date").addEventListener("change", async () => {
    updateRangePreview();
    await loadCalendar();
  });

  document.getElementById("end-date").addEventListener("change", async () => {
    updateRangePreview();
    await loadCalendar();
  });

  document.getElementById("generate-btn").addEventListener("click", generateMeals);
  document.getElementById("shopping-btn").addEventListener("click", generateShoppingList);
  document.getElementById("shopping-refresh-btn").addEventListener("click", generateShoppingList);
  document.getElementById("hero-generate-btn").addEventListener("click", async () => {
    activateTab("planner");
    await generateMeals();
  });
  document.getElementById("hero-shopping-btn").addEventListener("click", generateShoppingList);
  document.getElementById("save-profile-btn").addEventListener("click", saveProfileAllergies);
  document.getElementById("cm-save-btn").addEventListener("click", createCustomMeal);
  document.getElementById("cm-delete-btn").addEventListener("click", deleteSelectedCustomMeals);
  document.getElementById("cm-bulk-toggle-btn").addEventListener("click", toggleBulkPanel);
  document.getElementById("cm-bulk-upload-btn").addEventListener("click", uploadBulkTemplate);
  document.getElementById("add-extra-item-btn").addEventListener("click", addExtraShoppingItem);
  document.getElementById("user-info").addEventListener("click", (event) => {
    event.preventDefault();
    activateTab("profile");
  });
  document.getElementById("extra-item-name").addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      addExtraShoppingItem();
    }
  });
}

boot();
