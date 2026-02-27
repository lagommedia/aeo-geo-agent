async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    credentials: "include",
    ...options,
  });
  let payload = null;
  try {
    payload = await response.json();
  } catch (e) {
    payload = { detail: "No JSON response" };
  }
  if (!response.ok) {
    throw new Error(payload.detail || "Request failed");
  }
  return payload;
}

function setStatus(message, isError = false) {
  const el = document.getElementById("status");
  el.textContent = message;
  el.style.color = isError ? "#9d1b1b" : "";
}

function toggleCredentials() {
  const method = document.getElementById("login_method").value;
  const group = document.getElementById("credentials-group");
  group.style.display = method === "credentials" ? "grid" : "none";
}

function renderState(payload) {
  document.getElementById("state-view").textContent = JSON.stringify(payload, null, 2);
}

async function refreshState() {
  try {
    const data = await api("/me");
    renderState(data);
    setStatus("Loaded account state.");
  } catch (error) {
    renderState({ detail: "Not logged in or session expired." });
    setStatus(error.message, true);
  }
}

async function initPlatforms() {
  const select = document.getElementById("platform");
  const data = await api("/platforms", { method: "GET" });
  for (const platform of data.supported_platforms) {
    const option = document.createElement("option");
    option.value = platform;
    option.textContent = platform;
    select.appendChild(option);
  }
}

document.getElementById("register-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = new FormData(event.target);
  try {
    const body = {
      email: String(form.get("email")),
      password: String(form.get("password")),
    };
    await api("/auth/register", { method: "POST", body: JSON.stringify(body) });
    setStatus("Registration complete. You can now log in.");
  } catch (error) {
    setStatus(error.message, true);
  }
});

document.getElementById("login-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = new FormData(event.target);
  try {
    const body = {
      email: String(form.get("email")),
      password: String(form.get("password")),
    };
    await api("/auth/login", { method: "POST", body: JSON.stringify(body) });
    setStatus("Logged in.");
    await refreshState();
  } catch (error) {
    setStatus(error.message, true);
  }
});

document.getElementById("logout-btn").addEventListener("click", async () => {
  try {
    await api("/auth/logout", { method: "POST" });
    setStatus("Logged out.");
    await refreshState();
  } catch (error) {
    setStatus(error.message, true);
  }
});

document.getElementById("platform-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = new FormData(event.target);
  const method = String(form.get("login_method"));
  const body = {
    platform: String(form.get("platform")),
    login_method: method,
  };
  if (method === "credentials") {
    body.username = String(form.get("username") || "");
    body.password = String(form.get("password") || "");
  }
  try {
    await api("/platforms/connect", { method: "POST", body: JSON.stringify(body) });
    setStatus(`Connected ${body.platform} with ${method}.`);
    await refreshState();
  } catch (error) {
    setStatus(error.message, true);
  }
});

document.getElementById("refresh-btn").addEventListener("click", refreshState);
document.getElementById("login_method").addEventListener("change", toggleCredentials);

toggleCredentials();
initPlatforms()
  .then(refreshState)
  .catch((error) => setStatus(error.message, true));
