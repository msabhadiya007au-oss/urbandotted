import axios from "axios";

// Backend URL:
//   - Set REACT_APP_BACKEND_URL to a full URL when the API is on a different origin
//     (e.g. Emergent preview). In this case cookies rely on SameSite=None; Secure.
//   - Leave REACT_APP_BACKEND_URL empty (or unset) in production when the Static
//     Site rewrites /api/* to the backend — API calls become same-origin and
//     cookies are first-party (works in Incognito, Safari, Edge, everywhere).
const BACKEND_URL = (process.env.REACT_APP_BACKEND_URL || "").replace(/\/+$/, "");
export const API = `${BACKEND_URL}/api`;

export const api = axios.create({ baseURL: API, withCredentials: true });

let businessId = null;
export const setBusinessId = (id) => {
  businessId = id;
};
api.interceptors.request.use((config) => {
  if (businessId) config.headers["X-Business-Id"] = businessId;
  return config;
});

export function apiError(detail) {
  if (detail == null) return "Something went wrong. Please try again.";
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail))
    return detail.map((e) => (e && typeof e.msg === "string" ? e.msg : JSON.stringify(e))).join(" ");
  if (detail && typeof detail.msg === "string") return detail.msg;
  return String(detail);
}

export const errText = (e) => apiError(e?.response?.data?.detail) || e?.message || "Request failed";

// Auth-specific error messages that distinguish network/CORS from server errors.
export function authErrorMessage(err) {
  // No response object at all => network, CORS or DNS failure
  if (!err || !err.response) {
    // Some browsers surface "Network Error" from axios when the request never
    // returned (offline, DNS, blocked by CORS, or backend cold-starting).
    return "We couldn't reach the server. It may be waking up on a free plan — please try again in a few seconds. If this keeps happening, check your internet connection.";
  }
  const status = err.response.status;
  const detail = apiError(err.response.data?.detail);
  if (status === 401) return "Invalid email or password.";
  if (status === 403) return detail || "Access denied.";
  if (status === 404) return "This account or resource was not found.";
  if (status === 422) return detail || "Some fields are missing or invalid.";
  if (status === 429) return "Too many attempts. Please wait 15 minutes and try again.";
  if (status === 501) return detail || "This sign-in method isn't configured on this deployment.";
  if (status === 502 || status === 503 || status === 504) {
    return "The server is starting up or temporarily unreachable. Please try again in a moment.";
  }
  if (status >= 500) return "Server error. Please try again shortly.";
  return detail || "Something went wrong. Please try again.";
}

// ---------- en-AU formatting ----------
const money0 = new Intl.NumberFormat("en-AU", {
  style: "currency", currency: "AUD", minimumFractionDigits: 0, maximumFractionDigits: 0,
});
const money2 = new Intl.NumberFormat("en-AU", {
  style: "currency", currency: "AUD", minimumFractionDigits: 2, maximumFractionDigits: 2,
});

export const fmtMoney = (v, decimals = 2) => {
  const n = Number(v ?? 0);
  return decimals === 0 ? money0.format(n) : money2.format(n);
};
export const fmtNum = (v) => new Intl.NumberFormat("en-AU").format(Number(v ?? 0));
export const fmtPct = (v) => (v === null || v === undefined ? "—" : `${Number(v).toFixed(2)}%`);
export const fmtDate = (iso) => {
  if (!iso) return "—";
  const [y, m, d] = String(iso).slice(0, 10).split("-");
  return `${d}/${m}/${y}`;
};
export const todayISO = () => new Date().toISOString().slice(0, 10);
export const fyLabel = (fy) => (fy ? `FY ${fy.replace("FY", "")}` : "");

export const MONTHS = ["January", "February", "March", "April", "May", "June", "July",
  "August", "September", "October", "November", "December"];

export const fyMonthKeys = (fy) => {
  const start = parseInt(String(fy).replace("FY", "").split("-")[0], 10);
  return Array.from({ length: 12 }, (_, i) => {
    const m = 7 + i;
    const y = m <= 12 ? start : start + 1;
    const mm = m <= 12 ? m : m - 12;
    return `${y}-${String(mm).padStart(2, "0")}`;
  });
};
export const monthLabel = (key) => {
  if (!key) return "";
  const [y, m] = key.split("-");
  return `${MONTHS[parseInt(m, 10) - 1]} ${y}`;
};
export const monthShort = (key) => {
  if (!key) return "";
  const [y, m] = key.split("-");
  return `${MONTHS[parseInt(m, 10) - 1].slice(0, 3)} ${y.slice(2)}`;
};

export const GST_LABELS = {
  gst_included: "GST included",
  gst_excluded: "GST excluded",
  gst_free: "GST-free",
  no_gst: "No GST",
  custom: "Custom tax rate",
  unknown: "Unknown / needs review",
};

export const TXN_TYPE_LABELS = {
  expense: "Expense", sale: "Sale", refund: "Refund", other_income: "Other Income",
};

export const downloadFile = async (url, filename, opts = {}) => {
  const res = await api.request({
    url, method: opts.method || "GET", data: opts.data, responseType: "blob",
  });
  const blobUrl = URL.createObjectURL(res.data);
  const a = document.createElement("a");
  a.href = blobUrl;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(blobUrl), 2000);
};
