// API client for FastAPI File Classifier backend.

export function getDefaultBackendUrl(): string {
  if (typeof window === "undefined") return "http://localhost:8000";
  const protocol = window.location.protocol;
  const hostname = window.location.hostname || "localhost";
  return `${protocol}//${hostname}:8000`;
}

export function getBackendUrl(): string {
  if (typeof window === "undefined") return "http://localhost:8000";
  const stored = localStorage.getItem("fc_backend_url");
  if (stored) {
    const isLocalStored = stored.includes("://localhost") || stored.includes("://127.0.0.1");
    const isCurrentHostRemote = window.location.hostname !== "localhost" && window.location.hostname !== "127.0.0.1";
    if (!isLocalStored || !isCurrentHostRemote) {
      return stored;
    }
  }
  return getDefaultBackendUrl();
}

export function setBackendUrl(url: string) {
  localStorage.setItem("fc_backend_url", url.replace(/\/$/, ""));
}

async function request<T>(path: string, init?: RequestInit, query?: Record<string, any>): Promise<T> {
  const base = getBackendUrl();
  let url = `${base}${path}`;
  if (query) {
    const params = new URLSearchParams();
    Object.entries(query).forEach(([k, v]) => {
      if (v !== undefined && v !== null && v !== "") params.set(k, String(v));
    });
    const qs = params.toString();
    if (qs) url += `?${qs}`;
  }
  const res = await fetch(url, {
    ...init,
    credentials: "include",
    headers: {
      ...(init?.body && !(init.body instanceof FormData) ? { "Content-Type": "application/json" } : {}),
      ...(init?.headers || {}),
    },
  });
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`;
    try {
      const data = await res.json();
      detail = data.detail || JSON.stringify(data);
    } catch { }
    throw new Error(detail);
  }
  const ct = res.headers.get("content-type") || "";
  if (ct.includes("application/json")) return res.json() as Promise<T>;
  return (await res.text()) as any;
}

// ===== Types =====
export interface HealthResponse {
  status: string; version: string; categories_loaded: number;
  llm_model: string; openai_key_configured: boolean;
}
export interface CategoryInfo { name: string; keyword_count: number; keywords: string[]; }
export interface ConfigResponse {
  llm_model: string; min_score_threshold: number; pdf_max_pages: number;
  poppler_path: string | null; categories: CategoryInfo[];
}
export interface DetectResponse {
  filename: string; pdf_type: string; is_digital: boolean; detection_time_sec: number;
}
export interface ExtractResponse {
  filename: string; pdf_type: string; char_count: number; rotation_info: string;
  text_preview: string; text_full: string; error: string; extraction_time_sec: number;
}
export interface ClassifyResponse {
  filename?: string; category: string; confidence_score: number; llm_score_0_10: number;
  pdf_type?: string; rotation_info?: string; classification_time_sec: number;
  error: string; extracted_text: string;
}
export interface OrganiseResponse {
  source_path: string; destination_path: string; category: string;
  action: string; dry_run: boolean;
}
export interface PipelineResultItem {
  file_name: string; original_path: string; pdf_type: string; category: string;
  llm_score: number; destination_folder: string; rotation_applied: string;
  processing_time: number; error: string;
}
export interface PipelineResponse {
  total_files: number; successful: number; failed: number;
  categories_found: Record<string, number>; total_time_sec: number;
  results: PipelineResultItem[];
}
export interface ReportRow {
  file_name: string; original_path: string; destination_folder: string;
  category: string; pdf_type?: string; confidence: string; processing_time: string; error: string;
}
export interface ReportResponse { report_path: string; total_rows: number; rows: ReportRow[]; }
export interface DriveStatusResponse {
  connected: boolean; drive_root: string; drive_input: string; drive_output: string;
  pdf_count: number; pdf_files: string[]; input_ok: boolean; output_ok: boolean;
}
export interface OneDriveStatusResponse {
  connected: boolean; onedrive_root: string; onedrive_input: string; onedrive_output: string;
  pdf_count: number; pdf_files: string[]; input_ok: boolean; output_ok: boolean;
}
export interface GoogleSetupResponse {
  status: string; oauth_configured: boolean; message: string;
}
export interface GoogleProfileResponse {
  authenticated: boolean; email: string | null; name: string | null; picture: string | null;
}
export interface GoogleFoldersResponse {
  status: string; parent_id: string; parent_name: string; folders: { id: string; name: string }[];
}

// ===== Endpoints =====
export const api = {
  health: () => request<HealthResponse>("/health"),
  getConfig: () => request<ConfigResponse>("/config"),
  config: () => request<ConfigResponse>("/config"),
  listCategories: () => request<CategoryInfo[]>("/config/categories"),
  getUniversalLogs: (limit = 100) =>
    request<{ status: string; logs: { id: number; module: string; action: string; file_name: string; status: string; details: string; created_date: string }[] }>("/api/universal-logs", {}, { limit }),
  getDashboardStats: () =>
    request<{ status: string; stats: any }>("/api/dashboard-stats"),
  addCategory: (name: string, keywords: string[]) =>
    request<{ status: string; category: string; keywords: string[] }>("/config/categories", {
      method: "POST", body: JSON.stringify({ name, keywords }),
    }),

  detect: (file: File) => {
    const fd = new FormData(); fd.append("file", file);
    return request<DetectResponse>("/detect", { method: "POST", body: fd });
  },

  extract: (file: File, opts: { max_pages?: number; force_ocr?: boolean; use_auto_rotation?: boolean }) => {
    const fd = new FormData(); fd.append("file", file);
    return request<ExtractResponse>("/extract", { method: "POST", body: fd }, opts);
  },

  classifyText: (text: string, llm_model?: string, threshold?: number) =>
    request<ClassifyResponse>("/classify/text", {
      method: "POST", body: JSON.stringify({ text, llm_model, threshold }),
    }),

  classifyPdf: (file: File, opts: {
    max_pages?: number; llm_model?: string; threshold?: number;
    force_ocr?: boolean; categories?: string; run_id?: string;
  } = {}) => {
    const fd = new FormData(); fd.append("file", file);
    return request<ClassifyResponse>("/classify/pdf", { method: "POST", body: fd }, opts);
  },

  organise: (body: {
    source_path: string; category: string; output_folder: string;
    copy_mode?: boolean; dry_run?: boolean;
  }) => request<OrganiseResponse>("/organise", { method: "POST", body: JSON.stringify(body) }),

  pipeline: (body: {
    input_folder: string; output_folder: string; pdf_max_pages?: number;
    min_score?: number; llm_model?: string; copy_mode?: boolean; dry_run?: boolean;
  }) => request<PipelineResponse>("/pipeline/run", { method: "POST", body: JSON.stringify(body) }),

  getReport: (output_folder: string) =>
    request<ReportResponse>("/report", undefined, { output_folder }),

  downloadReportUrl: (output_folder: string) =>
    `${getBackendUrl()}/report/download?output_folder=${encodeURIComponent(output_folder)}`,

  driveStatus: (input_folder?: string) =>
    request<DriveStatusResponse>("/drive/status", undefined, input_folder ? { input_folder } : undefined),

  driveClassify: (body: {
    drive_input_folder?: string; drive_output_folder?: string;
    copy_mode?: boolean; dry_run?: boolean; pdf_max_pages?: number;
    min_score?: number; llm_model?: string;
  }) => request<any>("/drive/classify", { method: "POST", body: JSON.stringify(body) }),

  gpuDriveStatus: (input_folder?: string) =>
    request<DriveStatusResponse>("/api/gpu/api/drive/status", undefined, input_folder ? { input_folder } : undefined),

  gpuDriveClassify: (body: {
    input_folder: string; output_folder: string;
    max_pages?: number; min_score?: number; model?: string;
  }) => request<any>("/api/gpu/api/drive/classify", { method: "POST", body: JSON.stringify(body) }),

  gpuExtractDirect: (file: File, pipeline?: string) => {
    const fd = new FormData();
    fd.append("file", file);
    const headers: any = { "X-Source-Module": "DRIVE" };
    if (pipeline) headers["X-Document-Type"] = pipeline;
    return request<any>("/api/gpu/api/extract", {
      method: "POST",
      body: fd,
      headers
    });
  },

  googleCheckSetup: () =>
    request<GoogleSetupResponse>("/google/check-setup"),

  googleProfile: () =>
    request<GoogleProfileResponse>("/google/profile"),

  googleDriveFolders: (parent_id: string = "root") =>
    request<GoogleFoldersResponse>(`/google/drive/folders`, undefined, { parent_id }),

  googleDriveClassify: (body: {
    drive_input_folder_id: string; drive_output_folder_id: string;
    copy_mode?: boolean; dry_run?: boolean; pdf_max_pages?: number;
    min_score?: number; llm_model?: string; max_files?: number;
  }) => request<any>("/google/drive/classify", { method: "POST", body: JSON.stringify(body) }),

  onedriveStatus: (input_folder?: string) =>
    request<OneDriveStatusResponse>("/onedrive/status", undefined, input_folder ? { input_folder } : undefined),

  onedriveClassify: (body: {
    onedrive_input_folder?: string; onedrive_output_folder?: string;
    copy_mode?: boolean; dry_run?: boolean; pdf_max_pages?: number;
    min_score?: number; llm_model?: string;
  }) => request<any>("/onedrive/classify", { method: "POST", body: JSON.stringify(body) }),

  onedriveCheckSetup: () =>
    request<GoogleSetupResponse>("/onedrive/check-setup"),

  onedriveProfile: () =>
    request<GoogleProfileResponse>("/onedrive/profile"),

  onedriveFolders: (parent_id: string = "root") =>
    request<GoogleFoldersResponse>(`/onedrive/folders`, undefined, { parent_id }),

  onedriveCloudClassify: (body: {
    onedrive_input_folder_id: string; onedrive_output_folder_id: string;
    copy_mode?: boolean; dry_run?: boolean; pdf_max_pages?: number;
    min_score?: number; llm_model?: string; max_files?: number;
  }) => request<any>("/onedrive/drive/classify", { method: "POST", body: JSON.stringify(body) }),

  selectFolder: () => request<{ path: string | null }>("/select-folder"),

  listDirectories: (path?: string) =>
    request<{
      current_path: string;
      parent_path: string | null;
      subdirectories: { name: string; path: string }[];
      drives: string[];
    }>("/list-directories", undefined, path ? { path } : undefined),

  automationStatus: () =>
    request<{
      outlook_connected: boolean;
      gmail_connected: boolean;
      running: boolean;
      active_provider: "outlook" | "gmail" | null;
      pid: number | null;
      started_at: number | null;
    }>("/api/automation/status"),

  automationStart: (provider: "outlook" | "gmail") =>
    request<{ status: string; pid: number; provider: string }>("/api/automation/start", {
      method: "POST",
      body: JSON.stringify({ provider }),
    }),

  automationStop: () =>
    request<{ status: string }>("/api/automation/stop", { method: "POST" }),

  automationLogs: (lines: number = 50) =>
    request<{ logs: string[] }>("/api/automation/logs", undefined, { lines }),

  monitorFinish: (body: {
    run_id: string;
    status?: string;
    attachments?: number;
    files_classified?: number;
    errors?: number;
  }) => request<{ status: string }>("/api/monitor/finish", { method: "POST", body: JSON.stringify(body) }),

  convertFile: (file: File, source_format: string, target_format: string, user_id?: number, processed_by?: string) => {
    const fd = new FormData();
    fd.append("file", file);
    fd.append("source_format", source_format.toLowerCase());
    fd.append("target_format", target_format.toLowerCase());
    if (user_id !== undefined) fd.append("user_id", String(user_id));
    if (processed_by) fd.append("processed_by", processed_by);
    return fetch(`${getBackendUrl()}/api/convert`, {
      method: "POST",
      body: fd,
      credentials: "include",
    });
  },

  getConversionHistory: (limit: number = 100) =>
    request<ConversionHistoryRecord[]>("/api/convert/history", undefined, { limit }),

  // --- Parity Setup ---
  extractParity: (file: File, processed_by?: string) => {
    const fd = new FormData();
    fd.append("file", file);
    if (processed_by) fd.append("processed_by", processed_by);
    return request<{ task_id: string; fileName: string; status: string; message: string }>("/api/parity/api/extract", {
      method: "POST",
      body: fd,
    });
  },
  getParityTask: (taskId: string) =>
    request<{ task_id: string; fileName: string; status: string; progress: number; results: any; error: string | null }>(`/api/parity/api/extract/${taskId}`),
  getParityJobs: () =>
    request<any[]>("/api/parity/api/jobs"),
  mergeParityJson: (taskIds: string[]) =>
    fetch(`${getBackendUrl()}/api/parity/api/merge-json`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ task_ids: taskIds }),
    }),

  // --- Renewal Process ---
  processRenewal: (censusFile: File, invoiceFile: File) => {
    const fd = new FormData();
    fd.append("census", censusFile);
    fd.append("invoice", invoiceFile);
    return request<any>("/api/renewal/api/process", {
      method: "POST",
      body: fd,
    });
  },
  getRenewalJobs: () =>
    request<any[]>("/api/renewal/api/jobs"),
  getRenewalJob: (jobId: string) =>
    request<any>(`/api/renewal/api/jobs/${jobId}`),

  // --- Resourcing Edge ---
  processResourcingPdf: (file: File) => {
    const fd = new FormData();
    fd.append("file", file);
    return request<any>("/api/resourcing/process-pdf", {
      method: "POST",
      body: fd,
    });
  },
  getResourcingHistory: (limit = 50) =>
    request<ResourcingHistoryRecord[]>(`/api/resourcing/history?limit=${limit}`),
  downloadResourcingJsonUrl: (stem: string) =>
    `${getBackendUrl()}/api/resourcing/download/${encodeURIComponent(stem)}.json`,

  // --- Payroll Extractor ---
  processPayrollPdf: (file: File) => {
    const fd = new FormData();
    fd.append("file", file);
    return request<any>("/api/payroll/process-pdf", {
      method: "POST",
      body: fd,
    });
  },

  // --- RPVE ---
  extractRpve: (file: File) => {
    const fd = new FormData();
    fd.append("file", file);
    return request<any>("/api/rpve/api/extract", {
      method: "POST",
      body: fd,
    });
  },
  processRpveFlow: (files: File[]) => {
    const fd = new FormData();
    files.forEach((f) => fd.append("files", f));
    return request<any>("/api/rpve/api/process-flow", {
      method: "POST",
      body: fd,
    });
  },

  // ─── Auth & Admin Access Management ───────────────────────────────────────
  /** Login with email & optional password (checked against app_permissions DB). Returns JWT + user. */
  authLogin: (email: string, password?: string) =>
    request<{ status: string; token: string; user: { email: string; name: string; role: string; allowed_modules?: any; can_manage_tenants?: boolean; can_manage_users?: boolean } }>(
      "/api/auth/login",
      { method: "POST", body: JSON.stringify({ email, password }) }
    ),

  /** Forgot / Reset password */
  forgotPassword: (email: string, new_password: string) =>
    request<{ status: string; message: string }>(
      "/api/auth/forgot-password",
      { method: "POST", body: JSON.stringify({ email, new_password }) }
    ),

  /** SSO Callback exchange (code from Microsoft or direct email) */
  ssoCallback: (code?: string, email?: string) =>
    request<{ status: string; token: string; user: { email: string; name: string; role: string; allowed_modules?: any; can_manage_tenants?: boolean; can_manage_users?: boolean } }>(
      "/api/auth/sso/callback",
      { method: "POST", body: JSON.stringify({ code, email }) }
    ),

  /** Fetch current user from token */
  authMe: (token: string) =>
    request<{ status: string; user: { email: string; name: string; role: string } }>(
      "/api/auth/me",
      { headers: { Authorization: `Bearer ${token}` } }
    ),

  /** Admin: list all permissions + employee directory */
  getAdminUsers: (token: string) =>
    request<{
      status: string;
      current_admin: { email: string; name: string; role: string };
      permissions: any[];
      employee_directory: any[];
    }>("/api/admin/users", { headers: { Authorization: `Bearer ${token}` } }),

  /** Admin: grant access to a user */
  grantAccess: (
    token: string,
    body: { email: string; full_name?: string; role?: string; source?: string; allowed_modules?: string[] | string }
  ) =>
    request<{ status: string; message: string }>("/api/admin/grant-access", {
      method: "POST",
      body: JSON.stringify(body),
      headers: { Authorization: `Bearer ${token}` },
    }),

  /** Admin: revoke access */
  revokeAccess: (token: string, email: string) =>
    request<{ status: string; message: string }>("/api/admin/revoke-access", {
      method: "POST",
      body: JSON.stringify({ email }),
      headers: { Authorization: `Bearer ${token}` },
    }),

  /** Admin: permanently delete access record */
  deleteAccess: (token: string, email: string) =>
    request<{ status: string; message: string }>("/api/admin/delete-access", {
      method: "POST",
      body: JSON.stringify({ email }),
      headers: { Authorization: `Bearer ${token}` },
    }),

  /** SharePoint Automation APIs */
  getSharePointStatus: () =>
    request<{ status: string; agent: any }>("/api/sharepoint/status"),

  startSharePointAutomation: (body: { input_folder: string; output_folder: string; poc_engine: string; processed_by?: string }) =>
    request<{ status: string; message: string; agent: any }>("/api/sharepoint/start", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  stopSharePointAutomation: () =>
    request<{ status: string; message: string; agent: any }>("/api/sharepoint/stop", {
      method: "POST",
    }),

  getSharePointFolders: (path: string = "", folder_id?: string) =>
    request<{
      status: string;
      current_path: string;
      folders: Array<{ name: string; path: string; id: string; childCount: number }>;
      breadcrumbs?: Array<{ path: string; name: string; id?: string }>;
    }>(
      `/api/sharepoint/browse-folders?path=${encodeURIComponent(path)}${folder_id ? `&folder_id=${encodeURIComponent(folder_id)}` : ""}`
    ),
};

export interface ConversionHistoryRecord {
  id: number;
  source_format: string;
  target_format: string;
  original_file_name: string;
  converted_file_name: string | null;
  status: string;
  error_message: string | null;
  created_by: number | null;
  created_date: string | null;
}

export interface ResourcingHistoryRecord {
  id: number;
  pdf_filename: string;
  status: string;
  plan_names: string | null;
  output_json: string | null;
  error_message: string | null;
  created_date: string | null;
}
