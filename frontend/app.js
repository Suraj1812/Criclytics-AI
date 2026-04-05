const API_BASE_URL = window.CRICLYTICS_API_BASE_URL || window.location.origin;

const form = document.getElementById("analysis-form");
const submitButton = document.getElementById("submit-button");
const submitLabel = document.getElementById("submit-label");
const submitSpinner = document.getElementById("submit-spinner");
const insightOutput = document.getElementById("insight-output");
const responseMeta = document.getElementById("response-meta");
const errorBanner = document.getElementById("error-banner");
const toneField = document.getElementById("tone");

const pressureSignal = document.getElementById("pressure-signal");
const momentumSignal = document.getElementById("momentum-signal");
const stabilitySignal = document.getElementById("stability-signal");
const confidenceBadge = document.getElementById("confidence-badge");

const pressureScore = document.getElementById("pressure-score");
const momentumScore = document.getElementById("momentum-score");
const stabilityScore = document.getElementById("stability-score");
const confidenceScore = document.getElementById("confidence-score");

const currentRunRate = document.getElementById("current-rr");
const matchPhase = document.getElementById("match-phase");
const rateGap = document.getElementById("rate-gap");
const themeToggle = document.getElementById("theme-toggle");
const themeIconSun = document.getElementById("theme-icon-sun");
const themeIconMoon = document.getElementById("theme-icon-moon");
const themeColorMeta = document.querySelector('meta[name="theme-color"]');
const rootElement = document.documentElement;

const SIGNAL_BADGE_BASE = "signal-badge";
const THEME_STORAGE_KEY = "criclytics-theme";
const OVERS_PATTERN = /^\d+(?:\.[0-5])?$/;
const TOTAL_OVERS = 20;
const toast = window.CriclyticsToast || {
  success() {},
  error() {},
  warning() {},
  info() {},
};
const FIELD_CONFIG = {
  runs: { id: "runs", label: "Runs" },
  wickets: { id: "wickets", label: "Wickets" },
  overs: { id: "overs", label: "Overs" },
  required_rate: { id: "required-rate", label: "Required Rate" },
  tone: { id: "tone", label: "Tone" },
  seed: { id: "seed", label: "Seed" },
};

function getCurrentTheme() {
  return rootElement.dataset.theme === "light" ? "light" : "dark";
}

function syncThemeToggle(theme) {
  const showingLightMode = theme === "light";

  themeIconSun.classList.toggle("hidden", showingLightMode);
  themeIconMoon.classList.toggle("hidden", !showingLightMode);

  themeToggle.setAttribute(
    "aria-label",
    showingLightMode ? "Switch to dark mode" : "Switch to light mode",
  );
  themeToggle.setAttribute(
    "title",
    showingLightMode ? "Switch to dark mode" : "Switch to light mode",
  );

  if (themeColorMeta) {
    themeColorMeta.setAttribute("content", showingLightMode ? "#F4F7FB" : "#0B1220");
  }
}

function setTheme(theme, persist = true) {
  rootElement.dataset.theme = theme;
  syncThemeToggle(theme);

  if (!persist) {
    return;
  }

  try {
    localStorage.setItem(THEME_STORAGE_KEY, theme);
  } catch {
    // Ignore storage failures and keep the active session theme only.
  }
}

function toggleTheme() {
  setTheme(getCurrentTheme() === "dark" ? "light" : "dark");
}

function escapeHtml(value) {
  return value
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function formatTitleCase(value) {
  return value
    .split("_")
    .join(" ")
    .split(" ")
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(" ");
}

function formatSigned(value) {
  const normalized = Number(value || 0);
  const sign = normalized > 0 ? "+" : "";
  return `${sign}${normalized.toFixed(2)}`;
}

function formatPercent(value) {
  return `${Math.round(Number(value || 0) * 100)}%`;
}

function setLoadingState(isLoading) {
  submitButton.disabled = isLoading;
  submitSpinner.classList.toggle("hidden", !isLoading);
  submitLabel.textContent = isLoading ? "Generating..." : "Generate Insight";

  if (isLoading) {
    responseMeta.textContent = `Processing live request${toneField ? ` · ${toneField.value}` : ""}`;
  }
}

function clearError() {
  errorBanner.textContent = "";
  errorBanner.classList.add("hidden");
}

function showError(message) {
  errorBanner.textContent = message;
  errorBanner.classList.remove("hidden");
}

function getFieldElement(fieldKey) {
  const config = FIELD_CONFIG[fieldKey];
  return config ? document.getElementById(config.id) : null;
}

function clearFieldErrors() {
  Object.keys(FIELD_CONFIG).forEach((fieldKey) => {
    const field = getFieldElement(fieldKey);
    if (!field) {
      return;
    }
    field.removeAttribute("aria-invalid");
    field.removeAttribute("title");
  });
}

function markFieldError(fieldKey, message) {
  const field = getFieldElement(fieldKey);
  if (!field) {
    return null;
  }
  field.setAttribute("aria-invalid", "true");
  field.setAttribute("title", message);
  return field;
}

function oversToBalls(overs) {
  const [whole, partial = "0"] = overs.split(".");
  return (Number(whole) * 6) + Number(partial);
}

function validatePayload(payload) {
  const issues = [];

  if (!Number.isInteger(payload.runs) || payload.runs < 0 || payload.runs > 500) {
    issues.push({ field: "runs", message: "Runs must be a whole number between 0 and 500." });
  }

  if (!Number.isInteger(payload.wickets) || payload.wickets < 0 || payload.wickets > 10) {
    issues.push({ field: "wickets", message: "Wickets must be a whole number between 0 and 10." });
  }

  if (!OVERS_PATTERN.test(payload.overs)) {
    issues.push({ field: "overs", message: "Overs must use cricket notation like 13.2 or 19.5." });
  } else if (oversToBalls(payload.overs) > TOTAL_OVERS * 6) {
    issues.push({ field: "overs", message: `Overs cannot exceed ${TOTAL_OVERS}.0 in this dashboard.` });
  }

  if (!Number.isFinite(payload.required_rate) || payload.required_rate < 0 || payload.required_rate > 36) {
    issues.push({ field: "required_rate", message: "Required Rate must be between 0.00 and 36.00." });
  }

  if (!Number.isInteger(payload.seed) || payload.seed < 0 || payload.seed > 1_000_000) {
    issues.push({ field: "seed", message: "Seed must be a whole number between 0 and 1,000,000." });
  }

  if (OVERS_PATTERN.test(payload.overs) && oversToBalls(payload.overs) === 0 && payload.required_rate > 0 && payload.runs > 36) {
    issues.push({ field: "runs", message: "Runs look too high for 0.0 overs in a chase state." });
  }

  return issues;
}

function extractFieldKeyFromLocation(location) {
  if (!Array.isArray(location)) {
    return null;
  }

  const reversed = [...location].reverse();
  return reversed.find((part) => typeof part === "string" && part !== "body") || null;
}

function sanitizeBackendMessage(message, fieldKey) {
  const cleaned = String(message || "Invalid value")
    .replace(/^Value error,\s*/i, "")
    .replace(/^Input should\s*/i, "Should ");

  if (fieldKey === "overs" && /cricket notation/i.test(cleaned)) {
    return "Overs must use cricket notation like 13.2 or 19.5.";
  }

  if (fieldKey === "runs" && /implausibly high/i.test(cleaned)) {
    return "Runs are too high for 0.0 overs in the current match state.";
  }

  return cleaned.charAt(0).toUpperCase() + cleaned.slice(1);
}

function applyIssues(issues) {
  clearFieldErrors();
  const seen = new Set();
  const details = [];
  let firstInvalidField = null;

  issues.forEach((issue) => {
    const label = FIELD_CONFIG[issue.field]?.label || formatTitleCase(issue.field || "input");
    const detail = `${label}: ${issue.message}`;
    if (!seen.has(detail)) {
      seen.add(detail);
      details.push(detail);
    }

    const invalidField = markFieldError(issue.field, issue.message);
    if (!firstInvalidField && invalidField) {
      firstInvalidField = invalidField;
    }
  });

  if (firstInvalidField) {
    firstInvalidField.focus();
  }

  return details;
}

function notifyClientValidation(issues) {
  const details = applyIssues(issues);
  const message =
    details.length === 1
      ? "Fix the highlighted field before generating an insight."
      : `Fix the ${details.length} highlighted fields before generating an insight.`;

  responseMeta.textContent = "Input validation failed";
  showError("Match input needs attention.");
  toast.error({
    title: "Check your match input",
    message,
    details,
    id: "client-validation-error",
  });
}

function setSignalBadge(element, label, variant) {
  const variants = {
    low: "signal-badge--low",
    medium: "signal-badge--medium",
    high: "signal-badge--high",
    positive: "signal-badge--positive",
    neutral: "signal-badge--neutral",
    negative: "signal-badge--negative",
    stable: "signal-badge--stable",
    unstable: "signal-badge--unstable",
    confidence: "signal-badge--confidence",
  };

  element.textContent = label;
  element.className = `${SIGNAL_BADGE_BASE} ${variants[variant] || variants.neutral}`;
}

function animateInsight(html) {
  insightOutput.classList.remove("is-visible");
  window.requestAnimationFrame(() => {
    insightOutput.innerHTML = html;
    insightOutput.classList.add("is-visible");
  });
}

function syncToneStatus() {
  responseMeta.textContent = responseMeta.textContent.includes("Awaiting request")
    ? `Awaiting request · ${toneField.value}`
    : responseMeta.textContent;
}

function renderInsight(payload) {
  const insightHtml = payload.insight
    .split("\n")
    .map((line) => `<div>${escapeHtml(line)}</div>`)
    .join("");

  animateInsight(insightHtml);
  responseMeta.textContent = [
    payload.source === "fallback" ? "Fallback synthesis" : "Engine synthesis",
    payload.cached ? "Cache hit" : "Fresh output",
    payload.prompt_version,
    payload.tone,
  ].join(" · ");

  setSignalBadge(pressureSignal, payload.signals.pressure, payload.signals.pressure);
  setSignalBadge(momentumSignal, payload.signals.momentum, payload.signals.momentum);
  setSignalBadge(stabilitySignal, payload.signals.stability, payload.signals.stability);
  setSignalBadge(confidenceBadge, formatPercent(payload.confidence), "confidence");

  pressureScore.textContent = `Score ${payload.signals.pressure_score.toFixed(2)}`;
  momentumScore.textContent = `Score ${payload.signals.momentum_score.toFixed(2)}`;
  stabilityScore.textContent = `Score ${payload.signals.stability_score.toFixed(2)}`;
  confidenceScore.textContent = formatPercent(payload.confidence);

  currentRunRate.textContent = payload.metrics.current_run_rate.toFixed(2);
  matchPhase.textContent = formatTitleCase(payload.metrics.phase);
  rateGap.textContent = formatSigned(payload.metrics.rate_gap);
  rateGap.className = `mt-6 font-display text-3xl font-semibold tracking-tight ${
    payload.metrics.rate_gap >= 0 ? "metric-copy-positive" : "metric-copy-negative"
  }`;
}

function notifySuccess(payload) {
  const details = [
    `Win probability: ${formatPercent(payload.win_probability)}`,
    `Collapse probability: ${formatPercent(payload.collapse_probability)}`,
    `Confidence: ${formatPercent(payload.confidence)}`,
    payload.trend ? `Trend: ${formatTitleCase(payload.trend.trend)}` : null,
    payload.scoring_projection ? `Next 2 overs projection: ${payload.scoring_projection.expected_runs.toFixed(1)} runs` : null,
  ].filter(Boolean);

  if (payload.source === "fallback") {
    toast.warning({
      title: "Fallback insight returned",
      message: "The primary synthesis path failed, so Criclytics returned a safe fallback insight.",
      details,
      id: "insight-fallback",
    });
    return;
  }

  toast.success({
    title: payload.cached ? "Insight loaded from cache" : "Insight generated successfully",
    message: payload.cached
      ? "Repeated match input was served instantly from cache."
      : "Fresh match intelligence is ready.",
    details,
    id: payload.cached ? "insight-cache-hit" : "insight-success",
  });
}

async function parseResponseBody(response) {
  const contentType = response.headers.get("content-type") || "";
  if (contentType.includes("application/json")) {
    return response.json();
  }

  const text = await response.text();
  return text ? { detail: text } : {};
}

function buildApiError(response, data) {
  const requestId = response.headers.get("X-Request-ID");

  if (response.status === 422 && Array.isArray(data.errors)) {
    const issues = data.errors
      .map((issue) => {
        const fieldKey = extractFieldKeyFromLocation(issue.loc);
        return {
          field: fieldKey,
          message: sanitizeBackendMessage(issue.msg, fieldKey),
        };
      })
      .filter((issue) => issue.field);
    const details = applyIssues(issues);

    return {
      title: "Check your match input",
      message: "One or more fields are invalid for cricket analysis.",
      details: details.length > 0
        ? details
        : data.errors.map((issue) => sanitizeBackendMessage(issue.msg, extractFieldKeyFromLocation(issue.loc))),
      banner: "Match input needs attention.",
    };
  }

  clearFieldErrors();

  if (response.status === 429) {
    const retryAfter = Number(response.headers.get("Retry-After") || 0);
    return {
      title: "Rate limit reached",
      message: retryAfter > 0
        ? `Too many analyze requests were sent. Wait ${retryAfter} seconds before trying again.`
        : "Too many analyze requests were sent. Please wait a moment before trying again.",
      details: [
        response.headers.get("X-RateLimit-Limit")
          ? `Limit: ${response.headers.get("X-RateLimit-Limit")} requests per window`
          : null,
        requestId ? `Request ID: ${requestId}` : null,
      ].filter(Boolean),
      banner: "Rate limit reached. Please wait and try again.",
    };
  }

  if (response.status === 413) {
    return {
      title: "Request rejected",
      message: "The request payload was too large for the server to process.",
      details: [requestId ? `Request ID: ${requestId}` : null].filter(Boolean),
      banner: "The request was rejected because it was too large.",
    };
  }

  if (response.status >= 500) {
    return {
      title: "Server error",
      message: data.detail || "The insight engine hit an unexpected internal error.",
      details: [requestId ? `Request ID: ${requestId}` : null].filter(Boolean),
      banner: "The server failed while generating the insight.",
    };
  }

  return {
    title: "Request failed",
    message: data.detail || "Something went wrong while generating the insight.",
    details: [requestId ? `Request ID: ${requestId}` : null].filter(Boolean),
    banner: data.detail || "Insight generation failed.",
  };
}

async function submitAnalysis(event) {
  event.preventDefault();
  clearError();
  clearFieldErrors();
  setLoadingState(true);

  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), 10000);

  const payload = {
    runs: Number(document.getElementById("runs").value),
    wickets: Number(document.getElementById("wickets").value),
    overs: document.getElementById("overs").value.trim(),
    required_rate: Number(document.getElementById("required-rate").value),
    tone: toneField.value,
    seed: Number(document.getElementById("seed").value),
  };

  const clientIssues = validatePayload(payload);
  if (clientIssues.length > 0) {
    clearTimeout(timeoutId);
    setLoadingState(false);
    notifyClientValidation(clientIssues);
    return;
  }

  try {
    const response = await fetch(`${API_BASE_URL}/analyze`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
      signal: controller.signal,
    });

    const data = await parseResponseBody(response);
    if (!response.ok) {
      const apiError = buildApiError(response, data);
      responseMeta.textContent = "Request failed";
      showError(apiError.banner);
      toast.error({
        title: apiError.title,
        message: apiError.message,
        details: apiError.details,
        id: `api-error-${response.status}`,
      });
      throw new Error(apiError.message);
    }

    clearError();
    clearFieldErrors();
    renderInsight(data);
    notifySuccess(data);
  } catch (error) {
    if (error.name === "AbortError") {
      showError("The request timed out while waiting for the backend.");
      toast.error({
        title: "Request timed out",
        message: "Criclytics did not respond within 10 seconds.",
        details: [
          "Make sure the local backend is running.",
          `Expected API origin: ${API_BASE_URL}`,
        ],
        id: "request-timeout",
      });
    } else if (error instanceof TypeError && /fetch/i.test(error.message || "")) {
      showError("The dashboard could not reach the Criclytics backend.");
      toast.error({
        title: "Backend connection failed",
        message: "The browser could not connect to the Criclytics API.",
        details: [
          "Check that the local app is running.",
          `Expected API origin: ${API_BASE_URL}`,
        ],
        id: "network-error",
      });
    } else if (!String(error.message || "").includes("invalid for cricket analysis")) {
      responseMeta.textContent = "Request failed";
    }
  } finally {
    clearTimeout(timeoutId);
    setLoadingState(false);
  }
}

toneField.addEventListener("change", syncToneStatus);
form.addEventListener("submit", submitAnalysis);
themeToggle.addEventListener("click", toggleTheme);
syncToneStatus();
setTheme(getCurrentTheme(), false);
