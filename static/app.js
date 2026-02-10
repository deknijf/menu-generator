const state = {
  user: null,
  days: [],
  plan: [],
  shopping: [],
  historyDays: [],
  historyMonthAnchor: null,
  settings: null,
  profileAllergies: [],
  profileLikes: [],
  profileDislikes: [],
  customMeals: [],
  selectedCustomMealIds: [],
  profileMenuMode: "ai_only",
  customMealsCount: 0,
  isPrimaryAdmin: false,
  isGroupAdmin: false,
  canManageGroupUsers: false,
  canManageGroups: false,
  canManageGroupMenuMode: false,
  adminGroupIds: [],
  availableGroups: [],
  manageableGroups: [],
  manageableAccounts: [],
};
const sidebarStorageKey = "sidebar_collapsed";
const activeTabStorageKey = "active_tab";

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

function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

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

function weekdayName(isoDate) {
  const date = parseIsoDate(isoDate);
  const names = ["zondag", "maandag", "dinsdag", "woensdag", "donderdag", "vrijdag", "zaterdag"];
  return names[date.getDay()];
}

function weekdayShort(isoDate) {
  const date = parseIsoDate(isoDate);
  const names = ["zo", "ma", "di", "wo", "do", "vr", "za"];
  return names[date.getDay()];
}

function monthLabel(date) {
  const months = [
    "januari",
    "februari",
    "maart",
    "april",
    "mei",
    "juni",
    "juli",
    "augustus",
    "september",
    "oktober",
    "november",
    "december",
  ];
  return `${months[date.getMonth()]} ${date.getFullYear()}`;
}

function prettyQuantity(value) {
  return Number.isInteger(value) ? String(value) : value.toFixed(1);
}

function isFishMeal(name) {
  const needle = (name || "").toLowerCase();
  return needle.includes("zalm") || needle.includes("kabeljauw") || needle.includes("vis") || needle.includes("cod");
}

function isVegetarianMeal(name) {
  const needle = String(name || "").toLowerCase();
  if (!needle) return false;
  const meatLikeTokens = [
    "kip",
    "chicken",
    "rund",
    "beef",
    "gehakt",
    "steak",
    "hamburger",
    "kalkoen",
    "turkey",
    "varken",
    "pork",
    "spek",
    "bacon",
    "ham",
    "salami",
    "worst",
    "chorizo",
    "lam",
    "lams",
    "kalf",
    "veal",
    "zalm",
    "kabeljauw",
    "tonijn",
    "vis",
    "fish",
    "garnalen",
    "shrimp",
    "prawns",
  ];
  return !hasAny(needle, meatLikeTokens);
}

function monthStart(date) {
  return new Date(date.getFullYear(), date.getMonth(), 1);
}

function shiftMonth(date, delta) {
  return new Date(date.getFullYear(), date.getMonth() + delta, 1);
}

function clampHistoryAnchor(date) {
  const now = monthStart(new Date());
  const min = shiftMonth(now, -12);
  const max = shiftMonth(now, 12);
  const anchor = monthStart(date);
  if (anchor < min) return min;
  if (anchor > max) return max;
  return anchor;
}

function getWeekMonday(date) {
  const clone = new Date(date);
  const day = clone.getDay();
  const mondayOffset = day === 0 ? -6 : 1 - day;
  clone.setDate(clone.getDate() + mondayOffset);
  return clone;
}

function getMonthBounds(anchorDate) {
  const first = new Date(anchorDate.getFullYear(), anchorDate.getMonth(), 1);
  const last = new Date(anchorDate.getFullYear(), anchorDate.getMonth() + 1, 0);
  return [iso(first), iso(last)];
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

function splitChipTokens(value) {
  return String(value || "")
    .split(/[\s,;]+/g)
    .map((item) => item.trim().toLowerCase())
    .filter(Boolean);
}

function getProfileChipState(field) {
  if (field === "allergies") return state.profileAllergies;
  if (field === "likes") return state.profileLikes;
  return state.profileDislikes;
}

function setProfileChipState(field, tokens) {
  const unique = [];
  for (const token of tokens || []) {
    if (token && !unique.includes(token)) unique.push(token);
  }
  if (field === "allergies") state.profileAllergies = unique;
  else if (field === "likes") state.profileLikes = unique;
  else state.profileDislikes = unique;
}

function renderProfileChips(field) {
  const root = document.getElementById(`profile-${field}-chips`);
  const input = document.getElementById(`profile-${field}-input`);
  if (!root || !input) return;

  root.querySelectorAll(".chip-tag").forEach((chip) => chip.remove());
  const values = getProfileChipState(field);
  values.forEach((value, index) => {
    const chip = document.createElement("span");
    chip.className = "chip-tag";
    chip.innerHTML = `<span>${value}</span><button type="button" aria-label="Verwijder ${value}">×</button>`;
    chip.querySelector("button").addEventListener("click", () => {
      const next = getProfileChipState(field).slice();
      next.splice(index, 1);
      setProfileChipState(field, next);
      renderProfileChips(field);
    });
    root.insertBefore(chip, input);
  });
}

function addProfileChipTokens(field, rawValue) {
  const tokens = splitChipTokens(rawValue);
  if (!tokens.length) return;
  const next = getProfileChipState(field).slice();
  tokens.forEach((token) => {
    if (!next.includes(token)) next.push(token);
  });
  setProfileChipState(field, next);
  renderProfileChips(field);
}

function initProfileChipField(field) {
  const input = document.getElementById(`profile-${field}-input`);
  const root = document.getElementById(`profile-${field}-chips`);
  if (!input || !root) return;

  input.addEventListener("keydown", (event) => {
    if (event.key === " " || event.key === "Enter" || event.key === "Tab" || event.key === ",") {
      event.preventDefault();
      addProfileChipTokens(field, input.value);
      input.value = "";
    } else if (event.key === "Backspace" && !input.value) {
      const items = getProfileChipState(field).slice();
      if (!items.length) return;
      items.pop();
      setProfileChipState(field, items);
      renderProfileChips(field);
    }
  });

  input.addEventListener("blur", () => {
    addProfileChipTokens(field, input.value);
    input.value = "";
  });

  input.addEventListener("paste", (event) => {
    const text = event.clipboardData?.getData("text");
    if (!text) return;
    event.preventDefault();
    addProfileChipTokens(field, text);
    input.value = "";
  });
}

function isAiGeneratedMeal(item) {
  const id = String(item?.meal_id || item?.id || "");
  return !id.startsWith("custom_");
}

function normalizeShoppingItems(rawItems) {
  return (rawItems || []).map((item, index) => ({
    id: Number(item.id || 0),
    name: String(item.name || "").trim(),
    quantity: Number(item.quantity || 0),
    unit: String(item.unit || "").trim(),
    checked: !!item.checked,
    sort_order: Number(item.sort_order ?? index),
    show_quantity: item.show_quantity !== false,
  }));
}

function sortedShoppingItems() {
  return state.shopping
    .slice()
    .sort((a, b) => {
      if (a.checked !== b.checked) return a.checked ? 1 : -1;
      if (a.sort_order !== b.sort_order) return a.sort_order - b.sort_order;
      return a.name.localeCompare(b.name);
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
  const [from, to] = start <= end ? [start, end] : [end, start];
  document.getElementById("range-preview").textContent = `Van ${weekdayName(from)} ${formatDateEu(from)} tot en met ${weekdayName(to)} ${formatDateEu(to)}`;
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
      localStorage.setItem(activeTabStorageKey, target);
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
  const profileNameEl = document.getElementById("profile-name");
  const profileEmailEl = document.getElementById("profile-email");
  if (profileNameEl) profileNameEl.value = state.user.name || "";
  if (profileEmailEl) profileEmailEl.value = state.user.email || "";
  const roleLabel = state.user.is_admin ? "Admin" : state.user.is_group_admin ? "Groep-admin" : "Gebruiker";
  document.getElementById("profile-role").textContent = roleLabel;
}

async function fetchProfileSettings() {
  const res = await fetch("/api/settings");
  if (!res.ok) return;
  const data = await res.json();
  state.settings = data;

  const profileGroupEl = document.getElementById("profile-group");
  if (profileGroupEl) {
    const isPrimary = Boolean(data.profile?.is_primary_admin);
    const selectedIds = new Set((data.profile?.group_ids || []).map((value) => Number(value)));
    const selectedNames = (data.profile?.available_groups || [])
      .filter((group) => selectedIds.has(Number(group.id || 0)))
      .map((group) => group.name);
    profileGroupEl.textContent = isPrimary && selectedNames.length ? selectedNames.join(", ") : data.profile?.group?.name || "-";
  }

  const baseServings = data.app?.base_servings || 2;
  if (!document.getElementById("person-count").value) {
    document.getElementById("person-count").value = String(baseServings);
  }

  setProfileChipState("allergies", data.profile?.allergies || []);
  setProfileChipState("likes", data.profile?.likes || []);
  setProfileChipState("dislikes", data.profile?.dislikes || []);
  renderProfileChips("allergies");
  renderProfileChips("likes");
  renderProfileChips("dislikes");
  state.profileMenuMode = data.profile?.menu_mode || "ai_only";
  state.customMealsCount = Number(data.profile?.custom_meals_count || 0);
  state.isPrimaryAdmin = Boolean(data.profile?.is_primary_admin);
  state.isGroupAdmin = Boolean(data.profile?.is_group_admin);
  state.canManageGroupUsers = Boolean(data.profile?.can_manage_group_users);
  state.canManageGroupMenuMode = Boolean(data.profile?.can_manage_group_menu_mode);
  state.canManageGroups = Boolean(data.profile?.can_manage_groups) || Boolean(state.user?.is_admin);
  state.adminGroupIds = (data.profile?.group_ids || []).map((value) => Number(value));
  state.availableGroups = data.profile?.available_groups || [];
  renderAdminGroupMemberships();
  const accountPanel = document.getElementById("profile-account-management");
  if (accountPanel) accountPanel.hidden = !state.canManageGroupUsers;
  const accountGroupSelectWrap = document.getElementById("profile-new-account-group-select-wrap");
  const accountGroupFixedWrap = document.getElementById("profile-new-account-group-fixed-wrap");
  const accountGroupFixed = document.getElementById("profile-new-account-group-fixed");
  if (accountGroupSelectWrap) accountGroupSelectWrap.hidden = !state.canManageGroups;
  if (accountGroupFixedWrap) accountGroupFixedWrap.hidden = state.canManageGroups;
  if (accountGroupFixed) accountGroupFixed.textContent = data.profile?.group?.name || state.user?.group_name || "-";
  const groupToolbar = document.getElementById("profile-group-toolbar");
  if (groupToolbar) {
    groupToolbar.hidden = !state.canManageGroups;
    groupToolbar.style.display = state.canManageGroups ? "grid" : "none";
  }
  const modeSelect = document.getElementById("profile-menu-mode");
  if (modeSelect) modeSelect.disabled = !state.canManageGroupMenuMode;
  if (state.canManageGroupUsers) {
    await loadManageableAccounts();
  }
  const profileNameEl = document.getElementById("profile-name");
  const profileEmailEl = document.getElementById("profile-email");
  if (profileNameEl) profileNameEl.value = state.user?.name || "";
  if (profileEmailEl) profileEmailEl.value = state.user?.email || "";

  updateProfileMenuModeOptions();
}

async function updateOwnPassword(status) {
  const currentEl = document.getElementById("profile-current-password");
  const newEl = document.getElementById("profile-new-password");
  const current_password = currentEl.value || "";
  const new_password = newEl.value || "";
  if (!current_password && !new_password) {
    return true;
  }
  if (!current_password || !new_password) {
    status.textContent = "Vul huidig en nieuw wachtwoord in.";
    return false;
  }
  const res = await fetch("/api/profile/password", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ current_password, new_password }),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    status.textContent = data.error || "Wachtwoord wijzigen mislukt.";
    return false;
  }
  currentEl.value = "";
  newEl.value = "";
  return true;
}

async function saveProfileAccount(status) {
  const nameEl = document.getElementById("profile-name");
  const emailEl = document.getElementById("profile-email");
  const name = (nameEl?.value || "").trim();
  const email = (emailEl?.value || "").trim().toLowerCase();
  if (!email) {
    status.textContent = "E-mail is verplicht.";
    return false;
  }
  const res = await fetch("/api/profile/account", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name, email }),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    status.textContent = data.error || "Naam/e-mail opslaan mislukt.";
    return false;
  }
  if (data.user) {
    state.user = data.user;
    document.getElementById("user-info").textContent = `${state.user.name}`;
    document.getElementById("profile-role").textContent = state.user.is_admin
      ? "Admin"
      : state.user.is_group_admin
        ? "Groep-admin"
        : "Gebruiker";
    if (nameEl) nameEl.value = state.user.name || "";
    if (emailEl) emailEl.value = state.user.email || "";
  }
  return true;
}

async function saveAdminGroupMemberships(status) {
  if (!state.isPrimaryAdmin) return true;
  const checks = Array.from(document.querySelectorAll(".profile-admin-group-check"));
  const group_ids = checks.filter((input) => input.checked).map((input) => Number(input.value));
  if (!group_ids.length) {
    status.textContent = "Selecteer minstens 1 groep voor admin.";
    return false;
  }
  const res = await fetch("/api/profile/groups", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ group_ids }),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    status.textContent = data.error || "Groepen opslaan mislukt.";
    return false;
  }
  state.adminGroupIds = (data.group_ids || []).map((value) => Number(value));
  const groupsLabel = (data.groups || []).map((item) => item.name).join(", ");
  const profileGroupEl = document.getElementById("profile-group");
  if (profileGroupEl && groupsLabel) profileGroupEl.textContent = groupsLabel;
  return true;
}

async function loadManageableAccounts() {
  if (!state.canManageGroupUsers) return;
  const list = document.getElementById("profile-accounts-list");
  if (!list) return;
  list.innerHTML = "";
  const [groupsRes, accountsRes] = await Promise.all([fetch("/api/groups"), fetch("/api/accounts")]);
  if (!groupsRes.ok || !accountsRes.ok) {
    list.innerHTML = "<li>Accounts laden mislukt.</li>";
    return;
  }

  const groupsData = await groupsRes.json().catch(() => ({}));
  const accountsData = await accountsRes.json().catch(() => ({}));
  state.manageableGroups = groupsData.items || [];
  state.manageableAccounts = accountsData.items || [];
  populateGroupSelects();

  const items = state.manageableAccounts;
  if (!items.length) {
    list.innerHTML = "<li>Geen accounts gevonden.</li>";
    return;
  }

  const byGroup = new Map();
  items.forEach((item) => {
    const gid = Number(item.group_id || 1);
    if (!byGroup.has(gid)) byGroup.set(gid, []);
    byGroup.get(gid).push(item);
  });

  state.manageableGroups.forEach((group) => {
    const gid = Number(group.id || 1);
    const members = byGroup.get(gid) || [];
    const canDeleteGroup = Boolean(state.user?.is_admin) && gid > 1;
    const li = document.createElement("li");
    li.className = "profile-group-row";
    const membersHtml = members.length
      ? members
          .map(
            (item) => {
              const isPrimaryAdmin = Boolean(item.is_super_admin) || String(item.email || "").toLowerCase() === String(state.settings?.auth?.admin_email || "").toLowerCase();
              const safeEmail = escapeHtml(item.email);
              const safeName = escapeHtml(item.name);
              const showEmailLine = String(item.name || "").trim().toLowerCase() !== String(item.email || "").trim().toLowerCase();
              const roleLabel = item.is_admin ? "admin" : item.is_group_admin ? "groep-admin" : "user";
              const roleClass = isPrimaryAdmin ? "profile-account-role profile-account-role-super" : "profile-account-role";
              const safeHref = `/account/${encodeURIComponent(item.email || "")}`;
              return `
      <a class="profile-account-row profile-account-row-link" href="${safeHref}">
        <span class="profile-account-main">
          <strong class="profile-account-name">${safeName}</strong>
          ${showEmailLine ? `<span class="profile-account-email">${safeEmail}</span>` : ""}
        </span>
        <span class="profile-account-tools">
          <span class="${roleClass}">${isPrimaryAdmin ? "super admin" : roleLabel}</span>
        </span>
      </a>
    `
            }
          )
          .join("")
      : `<div class="muted">Geen gebruikers in deze groep.</div>`;
    li.innerHTML = `
      <div class="profile-group-head">
        <strong class="profile-group-name">${escapeHtml(group.name)}</strong>
        <span class="profile-group-head-right">
          <span class="profile-group-count">${members.length} ${members.length === 1 ? "gebruiker" : "gebruikers"}</span>
          ${canDeleteGroup ? `
          <button class="profile-group-delete-btn" type="button" data-group-id="${gid}" data-group-name="${escapeHtml(group.name)}" aria-label="Verwijder groep" title="Verwijder groep">
            <svg viewBox="0 0 24 24" aria-hidden="true">
              <path d="M9 3h6l1 2h4v2H4V5h4l1-2zM7 9h2v9H7V9zm4 0h2v9h-2V9zm4 0h2v9h-2V9z"></path>
            </svg>
          </button>` : ""}
        </span>
      </div>
      <div class="profile-group-members">${membersHtml}</div>
    `;
    list.appendChild(li);
  });

  list.querySelectorAll(".profile-group-delete-btn").forEach((btn) => {
    btn.addEventListener("click", async (event) => {
      event.preventDefault();
      event.stopPropagation();
      const groupId = Number(btn.dataset.groupId || 0);
      const groupName = String(btn.dataset.groupName || "deze groep");
      if (!groupId) return;
      const confirmed = window.confirm(`Ben je zeker dat je deze groep "${groupName}" wil verwijderen?`);
      if (!confirmed) return;
      await deleteManagedGroup(groupId);
    });
  });
}

function renderGroupOptionsHtml(selectedGroupId) {
  return (state.manageableGroups || [])
    .map((group) => {
      const gid = Number(group.id || 1);
      return `<option value="${gid}" ${gid === Number(selectedGroupId || 1) ? "selected" : ""}>${escapeHtml(group.name)}</option>`;
    })
    .join("");
}

function renderAdminGroupMemberships() {
  const wrap = document.getElementById("profile-admin-groups-wrap");
  const list = document.getElementById("profile-admin-groups-list");
  if (!wrap || !list) return;
  if (!state.isPrimaryAdmin) {
    wrap.hidden = true;
    list.innerHTML = "";
    return;
  }
  wrap.hidden = false;
  const groups = state.availableGroups || [];
  const selected = new Set((state.adminGroupIds || []).map((value) => Number(value)));
  if (!groups.length) {
    list.innerHTML = "<p class='muted'>Geen groepen gevonden.</p>";
    return;
  }
  list.innerHTML = groups
    .map((group) => {
      const gid = Number(group.id || 0);
      return `
      <label class="checkline">
        <input type="checkbox" class="profile-admin-group-check" value="${gid}" ${selected.has(gid) ? "checked" : ""} />
        <span>${escapeHtml(group.name || `Groep ${gid}`)}</span>
      </label>
    `;
    })
    .join("");
}

function populateGroupSelects() {
  const accountGroupSelect = document.getElementById("profile-new-account-group");
  const renameGroupSelect = document.getElementById("profile-rename-group-select");
  const defaultGroup = state.canManageGroups ? state.user?.group_id || 1 : state.user?.group_id || 1;
  const options = renderGroupOptionsHtml(defaultGroup);
  if (accountGroupSelect) accountGroupSelect.innerHTML = options;
  if (renameGroupSelect) renameGroupSelect.innerHTML = options;
  if (accountGroupSelect) accountGroupSelect.disabled = !state.canManageGroups;
  if (renameGroupSelect) renameGroupSelect.disabled = !state.canManageGroups;
}

async function createManagedAccount() {
  if (!state.canManageGroupUsers) return;
  const emailEl = document.getElementById("profile-new-account-email");
  const nameEl = document.getElementById("profile-new-account-name");
  const passwordEl = document.getElementById("profile-new-account-password");
  const groupEl = document.getElementById("profile-new-account-group");
  const status = document.getElementById("profile-account-status");
  const email = (emailEl.value || "").trim().toLowerCase();
  const name = (nameEl.value || "").trim();
  const password = passwordEl.value || "";
  const group_id = state.canManageGroups ? Number(groupEl?.value || 1) : Number(state.user?.group_id || 1);
  if (!email || !password) {
    status.textContent = "E-mail en wachtwoord zijn verplicht.";
    return;
  }
  const res = await fetch("/api/accounts", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, name, password, group_id }),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    status.textContent = data.error || "Account aanmaken mislukt.";
    return;
  }
  emailEl.value = "";
  nameEl.value = "";
  passwordEl.value = "";
  status.textContent = "Account aangemaakt.";
  await loadManageableAccounts();
  setTimeout(() => {
    status.textContent = "";
  }, 2000);
}

async function createManagedGroup() {
  if (!state.canManageGroups) return;
  const nameEl = document.getElementById("profile-new-group-name");
  const status = document.getElementById("profile-account-status");
  const name = (nameEl?.value || "").trim();
  if (!name) {
    status.textContent = "Geef een groepsnaam op.";
    return;
  }
  const res = await fetch("/api/groups", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name }),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    status.textContent = data.error || "Groep aanmaken mislukt.";
    return;
  }
  if (nameEl) nameEl.value = "";
  status.textContent = "Groep aangemaakt.";
  await loadManageableAccounts();
  setTimeout(() => {
    status.textContent = "";
  }, 2000);
}

async function renameManagedGroup() {
  if (!state.canManageGroups) return;
  const selectEl = document.getElementById("profile-rename-group-select");
  const nameEl = document.getElementById("profile-rename-group-name");
  const status = document.getElementById("profile-account-status");
  const group_id = Number(selectEl?.value || 0);
  const name = (nameEl?.value || "").trim();
  if (!group_id || !name) {
    status.textContent = "Kies een groep en geef een nieuwe naam op.";
    return;
  }
  const res = await fetch(`/api/groups/${encodeURIComponent(String(group_id))}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name }),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    status.textContent = data.error || "Groep hernoemen mislukt.";
    return;
  }
  if (nameEl) nameEl.value = "";
  status.textContent = "Groep hernoemd.";
  await loadManageableAccounts();
  setTimeout(() => {
    status.textContent = "";
  }, 2000);
}

async function deleteManagedGroup(group_id) {
  if (!state.user?.is_admin || !group_id) return;
  const status = document.getElementById("profile-account-status");
  const res = await fetch(`/api/groups/${encodeURIComponent(String(group_id))}`, {
    method: "DELETE",
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    if (status) status.textContent = data.error || "Groep verwijderen mislukt.";
    return;
  }
  if (status) status.textContent = "Groep verwijderd.";
  await fetchProfileSettings();
  await loadManageableAccounts();
  setTimeout(() => {
    if (status) status.textContent = "";
  }, 2000);
}

async function moveManagedAccountToGroup(email, group_id) {
  if (!state.canManageGroups || !email || !group_id) return;
  const status = document.getElementById("profile-account-status");
  const res = await fetch(`/api/accounts/${encodeURIComponent(email)}/group`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ group_id }),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    status.textContent = data.error || "Groep wijzigen mislukt.";
    return;
  }
  status.textContent = `Groep van ${email} aangepast.`;
  await loadManageableAccounts();
  setTimeout(() => {
    status.textContent = "";
  }, 2000);
}

async function deleteManagedAccount(email) {
  if (!state.canManageGroupUsers || !email) return;
  const status = document.getElementById("profile-account-status");
  const ok = window.confirm(`Account ${email} verwijderen?`);
  if (!ok) return;
  const res = await fetch(`/api/accounts/${encodeURIComponent(email)}`, { method: "DELETE" });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    status.textContent = data.error || "Account verwijderen mislukt.";
    return;
  }
  status.textContent = `Account ${email} verwijderd.`;
  await loadManageableAccounts();
  setTimeout(() => {
    status.textContent = "";
  }, 2000);
}

async function setManagedGroupAdmin(email, is_group_admin) {
  if (!state.canManageGroups || !email) return;
  const status = document.getElementById("profile-account-status");
  const res = await fetch(`/api/accounts/${encodeURIComponent(email)}/group-admin`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ is_group_admin: Boolean(is_group_admin) }),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    status.textContent = data.error || "Rol wijzigen mislukt.";
    return;
  }
  status.textContent = `Rol van ${email} aangepast.`;
  await loadManageableAccounts();
  setTimeout(() => {
    status.textContent = "";
  }, 2000);
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
  updateProfilePreferencesHint();
}

function updateProfilePreferencesHint() {
  const note = document.getElementById("profile-ai-optional-note");
  const select = document.getElementById("profile-menu-mode");
  const prefs = document.getElementById("profile-ai-preferences");
  if (!note || !select) return;
  const aiAllowed = select.value !== "custom_only";
  if (prefs) {
    prefs.hidden = !aiAllowed;
    prefs.style.display = aiAllowed ? "grid" : "none";
  }
  const baseNote = aiAllowed
    ? "Allergieën, favorieten en afkeur zijn optioneel zolang AI-maaltijden toegelaten zijn."
    : "Je gebruikt nu alleen eigen maaltijden. Deze voorkeuren zijn niet verplicht en worden enkel gebruikt zodra AI weer aan staat.";
  if (!state.canManageGroupMenuMode) {
    note.textContent = `${baseNote} Alleen admin of groep-admin kan deze instelling aanpassen.`;
  } else {
    note.textContent = baseNote;
  }
}

async function saveProfilePreferences(status) {
  const allergies = (state.profileAllergies || []).map((item) => item.toLowerCase());
  const likes = (state.profileLikes || []).map((item) => item.toLowerCase());
  const dislikes = (state.profileDislikes || []).map((item) => item.toLowerCase());
  const menu_mode = document.getElementById("profile-menu-mode").value;

  const payload = { allergies, likes, dislikes, menu_mode };

  const res = await fetch("/api/profile", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

  if (!res.ok) {
    try {
      const err = await res.json();
      status.textContent = err.error || "Opslaan mislukt.";
    } catch {
      status.textContent = "Opslaan mislukt.";
    }
    return false;
  }

  const data = await res.json();
  setProfileChipState("allergies", data.allergies || []);
  setProfileChipState("likes", data.likes || []);
  setProfileChipState("dislikes", data.dislikes || []);
  renderProfileChips("allergies");
  renderProfileChips("likes");
  renderProfileChips("dislikes");
  state.profileMenuMode = data.menu_mode || state.profileMenuMode;
  state.customMealsCount = Number(data.custom_meals_count || state.customMealsCount || 0);
  const profileGroupEl = document.getElementById("profile-group");
  if (profileGroupEl) {
    if (state.isPrimaryAdmin) {
      const selected = new Set((state.adminGroupIds || []).map((value) => Number(value)));
      const names = (state.availableGroups || [])
        .filter((group) => selected.has(Number(group.id || 0)))
        .map((group) => group.name);
      profileGroupEl.textContent = names.length ? names.join(", ") : profileGroupEl.textContent;
    } else {
      profileGroupEl.textContent = data.group?.name || profileGroupEl.textContent;
    }
  }
  updateProfileMenuModeOptions();
  return true;
}

async function saveProfileAll() {
  const status = document.getElementById("profile-save-status");
  status.textContent = "";
  const okAccount = await saveProfileAccount(status);
  if (!okAccount) return;
  const okGroups = await saveAdminGroupMemberships(status);
  if (!okGroups) return;
  const okPassword = await updateOwnPassword(status);
  if (!okPassword) return;
  const okPrefs = await saveProfilePreferences(status);
  if (!okPrefs) return;
  status.textContent = "Opgeslagen.";
  setTimeout(() => {
    status.textContent = "";
  }, 2000);
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

async function exportBulkTemplate() {
  const status = document.getElementById("cm-bulk-status");
  const res = await fetch("/api/custom-meals/export");
  if (!res.ok) {
    status.textContent = "Bulk export mislukt.";
    return;
  }

  const payload = await res.json();
  const items = payload.items || [];
  const text = JSON.stringify(items, null, 2);
  const blob = new Blob([text], { type: "application/json;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const stamp = new Date().toISOString().slice(0, 19).replace(/[:T]/g, "-");
  const filename = `custom-meals-${stamp}.json`;

  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
  status.textContent = `${items.length} gerechten geëxporteerd.`;
  setTimeout(() => {
    status.textContent = "";
  }, 2000);
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
    .filter((day) => day.cook && day.meal_name)
    .map((day) => ({
      date: day.date,
      meal_name: day.meal_name,
      meal_id: day.meal_id,
      meal_image: day.meal_image,
      explanation: "Geplande maaltijd.",
    }));

  state.plan = plannedFromCalendar;

  updateRangePreview();
  renderCalendar();
  renderPlan();
  renderDashboard();
}

async function loadHistoryCalendar() {
  if (!state.historyMonthAnchor) {
    const now = new Date();
    state.historyMonthAnchor = new Date(now.getFullYear(), now.getMonth(), 1);
  }
  state.historyMonthAnchor = clampHistoryAnchor(state.historyMonthAnchor);
  const [start, end] = getMonthBounds(state.historyMonthAnchor);
  const res = await fetch(`/api/calendar?start=${start}&end=${end}`);
  if (!res.ok) return;
  const data = await res.json();
  state.historyDays = data.days || [];
  renderHistoryCalendar();
}

function renderHistoryCalendar() {
  const root = document.getElementById("history-calendar");
  const label = document.getElementById("history-month-label");
  const prevBtn = document.getElementById("history-prev-btn");
  const nextBtn = document.getElementById("history-next-btn");
  if (!root || !label || !state.historyMonthAnchor) return;

  root.innerHTML = "";
  label.textContent = monthLabel(state.historyMonthAnchor);

  const now = monthStart(new Date());
  const min = shiftMonth(now, -12);
  const max = shiftMonth(now, 12);
  if (prevBtn) prevBtn.disabled = state.historyMonthAnchor <= min;
  if (nextBtn) nextBtn.disabled = state.historyMonthAnchor >= max;

  const headers = ["maandag", "dinsdag", "woensdag", "donderdag", "vrijdag", "zaterdag", "zondag"];
  headers.forEach((name) => {
    const h = document.createElement("div");
    h.className = "history-weekday";
    h.textContent = name;
    root.appendChild(h);
  });

  if (!state.historyDays.length) return;

  const firstDate = parseIsoDate(state.historyDays[0].date);
  const weekday = firstDate.getDay();
  const mondayIndex = weekday === 0 ? 6 : weekday - 1;
  for (let i = 0; i < mondayIndex; i++) {
    const spacer = document.createElement("div");
    spacer.className = "history-day-spacer";
    root.appendChild(spacer);
  }

  const todayIso = iso(new Date());

  state.historyDays.forEach((day) => {
    const hasMeal = Boolean(day.meal_name);
    const hasShopping = Boolean(day.shopping_done);
    const isToday = day.date === todayIso;
    const cell = document.createElement("article");
    cell.className = `history-day${hasMeal ? " has-meal" : ""}${hasShopping ? " has-shopping" : ""}${isToday ? " is-today" : ""}`;

    const top = document.createElement("div");
    top.className = "history-day-top";
    const dateEl = document.createElement("strong");
    dateEl.textContent = formatDateEu(day.date);
    const weekEl = document.createElement("em");
    weekEl.textContent = weekdayShort(day.date);
    top.appendChild(dateEl);
    top.appendChild(weekEl);

    cell.appendChild(top);

    const content = document.createElement(hasMeal ? "a" : "span");
    content.className = "history-day-meal";
    if (hasMeal && day.meal_id) {
      content.href = `/meal/${encodeURIComponent(day.meal_id)}?date=${encodeURIComponent(formatDateEu(day.date))}&person_count=${encodeURIComponent(String(getPersonCount()))}`;
      content.title = day.meal_name;
    }
    content.textContent = hasMeal ? day.meal_name : "Geen maaltijd";
    cell.appendChild(content);

    if (hasShopping) {
      const shoppingTag = document.createElement("a");
      shoppingTag.className = "history-day-shopping";
      shoppingTag.href = `/shopping-history/${encodeURIComponent(day.date)}`;
      const shoppingCount = Number(day.shopping_count || 0);
      const extraCount = Math.max(0, shoppingCount - 1);
      shoppingTag.textContent = extraCount > 0 ? `Boodschappen +${extraCount}` : "Boodschappen";
      cell.appendChild(shoppingTag);
    }

    root.appendChild(cell);
  });
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
        state.shopping = [];
        renderShopping();
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
  const openList = document.getElementById("shopping-list-open");
  const doneList = document.getElementById("shopping-list-done");
  const sideList = document.getElementById("side-shopping-list");
  const sideMore = document.getElementById("side-shopping-more");
  const statTotal = document.getElementById("shopping-stat-total");
  const statOpen = document.getElementById("shopping-stat-open");
  const statDone = document.getElementById("shopping-stat-done");
  const completeWrap = document.getElementById("shopping-complete-wrap");
  const completeBtn = document.getElementById("shopping-complete-btn");

  if (openList) openList.innerHTML = "";
  if (doneList) doneList.innerHTML = "";
  if (sideList) sideList.innerHTML = "";
  if (sideMore) {
    sideMore.hidden = true;
    sideMore.textContent = "";
  }
  if (completeWrap) completeWrap.hidden = true;
  if (completeBtn) completeBtn.disabled = true;

  if (!state.shopping.length) {
    if (openList) openList.innerHTML = "<li>Genereer eerst je boodschappenlijst.</li>";
    if (doneList) doneList.innerHTML = "<li>Nog geen afgevinkte items.</li>";
    if (statTotal) statTotal.textContent = "0";
    if (statOpen) statOpen.textContent = "0";
    if (statDone) statDone.textContent = "0";
    if (sideList) sideList.innerHTML = "<li>Nog geen items.</li>";
    if (completeWrap) completeWrap.hidden = true;
    if (completeBtn) completeBtn.disabled = true;
    return;
  }

  const ordered = sortedShoppingItems();
  const sidePreviewLimit = 4;
  const openItems = ordered.filter((item) => !item.checked);
  const doneItems = ordered.filter((item) => item.checked);
  if (statTotal) statTotal.textContent = String(ordered.length);
  if (statOpen) statOpen.textContent = String(openItems.length);
  if (statDone) statDone.textContent = String(doneItems.length);
  if (completeWrap) completeWrap.hidden = false;
  if (completeBtn) completeBtn.disabled = doneItems.length === 0;

  function renderItem(item, idx, rootList) {
    if (!rootList) return;
    const li = document.createElement("li");
    li.className = item.checked ? "shopping-item checked shopping-item-done" : "shopping-item shopping-item-open";
    li.dataset.itemId = String(item.id);
    li.draggable = true;
    const qtyText = item.show_quantity ? `${prettyQuantity(item.quantity)} ${item.unit}`.trim() : "";
    li.innerHTML = `
      <span class="drag-handle" title="Versleep item" aria-label="Versleep item">
        <svg viewBox="0 0 10 14" aria-hidden="true">
          <circle cx="2" cy="2" r="1"></circle>
          <circle cx="8" cy="2" r="1"></circle>
          <circle cx="2" cy="7" r="1"></circle>
          <circle cx="8" cy="7" r="1"></circle>
          <circle cx="2" cy="12" r="1"></circle>
          <circle cx="8" cy="12" r="1"></circle>
        </svg>
      </span>
      <label class="shop-checkline">
        <input type="checkbox" ${item.checked ? "checked" : ""} />
        <span class="shop-text">${item.name}</span>
      </label>
      <div class="shop-item-actions">
        <strong class="shop-qty shop-qty-badge">${qtyText}</strong>
        <button class="shop-delete-btn" type="button" aria-label="Verwijder item" title="Verwijder item">
          <svg viewBox="0 0 24 24" aria-hidden="true">
            <path d="M9 3h6l1 2h4v2H4V5h4l1-2zm1 6h2v8h-2V9zm4 0h2v8h-2V9zM8 9h2v8H8V9zm-1 12h10a2 2 0 0 0 2-2V7H5v12a2 2 0 0 0 2 2z"></path>
          </svg>
        </button>
      </div>
    `;

    const checkbox = li.querySelector("input[type='checkbox']");
    const deleteBtn = li.querySelector(".shop-delete-btn");
    checkbox.addEventListener("change", async () => {
      checkbox.disabled = true;
      const res = await fetch(`/api/shopping-list/${encodeURIComponent(String(item.id))}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ checked: checkbox.checked }),
      });
      if (res.ok) {
        const data = await res.json();
        state.shopping = normalizeShoppingItems(data.items || []);
      } else {
        checkbox.checked = !checkbox.checked;
      }
      renderShopping();
    });

    if (deleteBtn) {
      deleteBtn.addEventListener("click", async () => {
        deleteBtn.disabled = true;
        const res = await fetch(`/api/shopping-list/${encodeURIComponent(String(item.id))}`, {
          method: "DELETE",
        });
        if (!res.ok) {
          deleteBtn.disabled = false;
          return;
        }
        const data = await res.json();
        state.shopping = normalizeShoppingItems(data.items || []);
        renderShopping();
      });
    }

    rootList.appendChild(li);

    if (sideList && idx < sidePreviewLimit) {
      const sli = document.createElement("li");
      sli.className = item.checked ? "checked" : "";
      const sideQty = item.show_quantity ? `${prettyQuantity(item.quantity)} ${item.unit}`.trim() : "";
      sli.innerHTML = `<span>${item.name}</span><strong>${sideQty}</strong>`;
      sideList.appendChild(sli);
    }
  }

  openItems.forEach((item, idx) => renderItem(item, idx, openList));
  doneItems.forEach((item, idx) => renderItem(item, openItems.length + idx, doneList));

  if (doneList && !doneItems.length) {
    doneList.innerHTML = "<li>Nog geen afgevinkte items.</li>";
  }

  if (sideMore && ordered.length > sidePreviewLimit) {
    const remaining = ordered.length - sidePreviewLimit;
    sideMore.hidden = false;
    sideMore.innerHTML = `<a href="#shopping">${remaining} extra ${remaining === 1 ? "item" : "items"} bekijken</a>`;
    const link = sideMore.querySelector("a");
    if (link) {
      link.addEventListener("click", (event) => {
        event.preventDefault();
        activateTab("shopping");
      });
    }
  }

  let dragItemId = null;

  async function persistOrder() {
    const item_ids = [...openItems, ...doneItems].map((item) => item.id);
    const res = await fetch("/api/shopping-list/reorder", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ item_ids }),
    });
    if (!res.ok) return;
    const data = await res.json();
    state.shopping = normalizeShoppingItems(data.items || []);
    renderShopping();
  }

  function bindDragForList(listEl, sectionItems) {
    if (!listEl) return;
    const rows = listEl.querySelectorAll("li[data-item-id]");
    rows.forEach((row) => {
      const rowId = Number(row.dataset.itemId || 0);
      row.addEventListener("dragstart", () => {
        dragItemId = rowId;
        row.classList.add("dragging");
      });
      row.addEventListener("dragend", () => {
        dragItemId = null;
        row.classList.remove("dragging");
        listEl.querySelectorAll(".drop-target").forEach((el) => el.classList.remove("drop-target"));
      });
      row.addEventListener("dragover", (event) => {
        if (!dragItemId || dragItemId === rowId) return;
        event.preventDefault();
        row.classList.add("drop-target");
      });
      row.addEventListener("dragleave", () => {
        row.classList.remove("drop-target");
      });
      row.addEventListener("drop", async (event) => {
        event.preventDefault();
        row.classList.remove("drop-target");
        if (!dragItemId || dragItemId === rowId) return;

        const fromIndex = sectionItems.findIndex((item) => item.id === dragItemId);
        const targetIndex = sectionItems.findIndex((item) => item.id === rowId);
        if (fromIndex < 0 || targetIndex < 0) return;

        const bounds = row.getBoundingClientRect();
        const insertAfter = event.clientY > bounds.top + bounds.height / 2;
        const [moved] = sectionItems.splice(fromIndex, 1);
        let nextIndex = targetIndex;
        if (insertAfter) nextIndex += 1;
        if (fromIndex < targetIndex) nextIndex -= 1;
        sectionItems.splice(Math.max(0, Math.min(sectionItems.length, nextIndex)), 0, moved);
        await persistOrder();
      });
    });
  }

  bindDragForList(openList, openItems);
  bindDragForList(doneList, doneItems);
}

async function completeShoppingList() {
  const res = await fetch("/api/shopping-list/complete", {
    method: "POST",
  });
  if (!res.ok) return;
  const data = await res.json();
  state.shopping = normalizeShoppingItems(data.items || []);
  renderShopping();
  await loadHistoryCalendar();
}

function renderDashboard() {
  const cookDays = state.days.filter((d) => d.cook).length;
  const skipDays = state.days.filter((d) => !d.cook).length;
  const vegetarianMeals = state.days.filter((d) => d.cook && d.meal_name && isVegetarianMeal(d.meal_name)).length;
  const fishMeals = state.days.filter((d) => isFishMeal(d.meal_name)).length;

  document.getElementById("metric-cook-days").textContent = String(cookDays);
  document.getElementById("metric-skip-days").textContent = String(skipDays);
  document.getElementById("metric-vegetarian").textContent = String(vegetarianMeals);
  document.getElementById("metric-fish").textContent = String(fishMeals);
  document.getElementById("cook-days-summary").textContent = `${cookDays} ${cookDays === 1 ? "dag" : "dagen"} zelf koken`;
}

async function generateMeals() {
  const payload = {
    start: document.getElementById("start-date").value,
    end: document.getElementById("end-date").value,
    options: getMealOptions(),
  };

  let res = await fetch("/api/generate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (res.status === 409) {
    const prompt = await res.json();
    const ok = window.confirm(prompt.error || "Er bestaat al een menu. Opnieuw genereren?");
    if (!ok) return;
    res = await fetch("/api/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ...payload, force: true }),
    });
  }
  if (!res.ok) return;
  const data = await res.json();
  state.plan = data.plan || [];
  state.shopping = [];

  renderPlan();
  renderShopping();
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
}

async function loadShoppingList() {
  const res = await fetch("/api/shopping-list");
  if (!res.ok) return;
  const data = await res.json();
  state.shopping = normalizeShoppingItems(data.items || []);
  renderShopping();
}

async function clearShoppingList() {
  const res = await fetch("/api/shopping-list", {
    method: "DELETE",
  });
  if (!res.ok) return;
  state.shopping = [];
  renderShopping();
}

function addExtraShoppingItem() {
  const nameEl = document.getElementById("extra-item-name");
  const qtyEl = document.getElementById("extra-item-qty");
  const unitEl = document.getElementById("extra-item-unit");

  const name = (nameEl.value || "").trim();
  if (!name) return;

  const quantity = Number(qtyEl.value || 1);
  const unit = (unitEl.value || "stuk").trim();

  fetch("/api/shopping-list/items", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name, quantity, unit }),
  }).then(async (res) => {
    if (!res.ok) return;
    const data = await res.json();
    state.shopping = normalizeShoppingItems(data.items || []);
    nameEl.value = "";
    qtyEl.value = "";
    unitEl.value = "";
    renderShopping();
  });
}

async function boot() {
  initSidebarToggle();
  initCustomMealUpload();
  initProfileChipField("allergies");
  initProfileChipField("likes");
  initProfileChipField("dislikes");
  bindTabs();
  const savedTab = localStorage.getItem(activeTabStorageKey);
  if (savedTab) {
    activateTab(savedTab);
  }
  setDefaultDates();
  await fetchSession();
  await fetchProfileSettings();
  await loadCustomMeals();
  await loadCalendar();
  await loadHistoryCalendar();
  await loadShoppingList();

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
  document.getElementById("shopping-clear-btn").addEventListener("click", clearShoppingList);
  document.getElementById("shopping-complete-btn").addEventListener("click", completeShoppingList);
  document.getElementById("hero-generate-btn").addEventListener("click", generateMeals);
  document.getElementById("hero-shopping-btn").addEventListener("click", generateShoppingList);
  document.getElementById("save-profile-btn").addEventListener("click", saveProfileAll);
  document.getElementById("profile-create-account-btn").addEventListener("click", createManagedAccount);
  document.getElementById("profile-create-group-btn").addEventListener("click", createManagedGroup);
  document.getElementById("profile-rename-group-btn").addEventListener("click", renameManagedGroup);
  document.getElementById("profile-menu-mode").addEventListener("change", updateProfilePreferencesHint);
  document.getElementById("cm-save-btn").addEventListener("click", createCustomMeal);
  document.getElementById("cm-delete-btn").addEventListener("click", deleteSelectedCustomMeals);
  document.getElementById("cm-bulk-toggle-btn").addEventListener("click", toggleBulkPanel);
  document.getElementById("cm-bulk-export-btn").addEventListener("click", exportBulkTemplate);
  document.getElementById("cm-bulk-upload-btn").addEventListener("click", uploadBulkTemplate);
  document.getElementById("add-extra-item-btn").addEventListener("click", addExtraShoppingItem);
  document.getElementById("history-prev-btn").addEventListener("click", async () => {
    state.historyMonthAnchor = shiftMonth(state.historyMonthAnchor, -1);
    await loadHistoryCalendar();
  });
  document.getElementById("history-next-btn").addEventListener("click", async () => {
    state.historyMonthAnchor = shiftMonth(state.historyMonthAnchor, 1);
    await loadHistoryCalendar();
  });
  document.getElementById("history-today-btn").addEventListener("click", async () => {
    const now = new Date();
    state.historyMonthAnchor = new Date(now.getFullYear(), now.getMonth(), 1);
    await loadHistoryCalendar();
  });
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
