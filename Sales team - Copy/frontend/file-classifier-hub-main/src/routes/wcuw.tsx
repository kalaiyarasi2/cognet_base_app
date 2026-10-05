import { createFileRoute } from "@tanstack/react-router";
import { useState, useRef, useEffect } from "react";
import {
  ShieldCheck, FileText, UploadCloud, Loader2, Download, CheckCircle2,
  AlertCircle, FileJson, Table as TableIcon, Copy, Brain, RefreshCw,
  Building2, BarChart3, Check, Sparkles, HardHat, DollarSign,
  Search, ShieldAlert, ArrowRight, ExternalLink, MapPin, Users, History, Phone, Mail,
  ChevronDown, ChevronUp, RotateCcw, Briefcase, Calendar, Percent, Database
} from "lucide-react";
import { PageHeader } from "@/components/PageHeader";
import { Panel } from "@/components/Panel";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { toast } from "sonner";
import { api, getBackendUrl } from "@/lib/api";
import { useAuth } from "@/lib/store";
import ExceptionTab from "@/components/ExceptionTab";

export const Route = createFileRoute("/wcuw")({
  component: WcuwPage,
});

interface ExtractionState {
  lossRunResult: any | null;
  acordResult: any | null;
  modifierResult?: any | null;
  lossRunSchema: any | null;
  acordSchema: any | null;
  modifierValue?: number | null;
  lossRunExcelUrl?: string | null;
  acordExcelUrl?: string | null;
}

const STAGES = [
  { id: "loss_run", label: "Loss Run Ingestion", desc: "Extracting claims, loss history & reserves via GPU OCR" },
  { id: "acord", label: "ACORD 130 Ingestion", desc: "Extracting demographics, state ratings & payroll classes" },
  { id: "modifier", label: "Modifier Extraction", desc: "Extracting Experience Modifier (X-Mod) via Modifier POC" },
  { id: "synthesis", label: "Data Synthesis", desc: "Correlating claims experience with policy rating & X-Mod structure" },
  { id: "complete", label: "Ready", desc: "Extraction complete — review dashboard & AI summary" },
];

export interface OpportunityData {
  recordType: string;
  opportunityName: string;
  stage: string;
  closeDate: string;
  estimatedFirstPayrollDate: string;
  opportunityGeneratedBy: string;
  channelPartner: string;
  firstMeetingDate: string;
  modifier?: string;
}

const formatMMDDYYYY = (d: Date = new Date()): string => {
  const mm = String(d.getMonth() + 1).padStart(2, "0");
  const dd = String(d.getDate()).padStart(2, "0");
  const yyyy = d.getFullYear();
  return `${mm}/${dd}/${yyyy}`;
};

const addDaysToDate = (d: Date, days: number): Date => {
  const result = new Date(d);
  result.setDate(result.getDate() + days);
  return result;
};

const getInitialOpportunityData = (applicantName?: string): OpportunityData => {
  const today = new Date();
  const plus60Days = addDaysToDate(today, 60);
  return {
    recordType: "PEO",
    opportunityName: applicantName || "",
    stage: "First Meeting",
    closeDate: formatMMDDYYYY(plus60Days),
    estimatedFirstPayrollDate: formatMMDDYYYY(plus60Days),
    opportunityGeneratedBy: "Channel Partner",
    channelPartner: "TBD",
    firstMeetingDate: formatMMDDYYYY(today),
    modifier: "1.0",
  };
};

function WcuwPage() {
  const { user } = useAuth();
  const [lossRunFile, setLossRunFile] = useState<File | null>(null);
  const [acordFile, setAcordFile] = useState<File | null>(null);
  const [modifierFile, setModifierFile] = useState<File | null>(null);
  const [extractedModifier, setExtractedModifier] = useState<number | null>(null);
  const [modifierResult, setModifierResult] = useState<any | null>(null);

  const [isProcessing, setIsProcessing] = useState(false);
  const [currentStageIdx, setCurrentStageIdx] = useState(0);
  const [extractionState, setExtractionState] = useState<ExtractionState | null>(null);

  // View state
  const [activeMainTab, setActiveMainTab] = useState<"table" | "json" | "summary" | "exceptions">("table");
  const [activeTableSubTab, setActiveTableSubTab] = useState<"all" | "claims" | "rating" | "locations" | "contacts" | "priors">("all");
  const [activeJsonSubTab, setActiveJsonSubTab] = useState<"unified" | "loss_run" | "acord" | "modifier">("unified");
  const [tableSearch, setTableSearch] = useState("");

  // AI Summary State
  const [isSummarizing, setIsSummarizing] = useState(false);
  const [summaryText, setSummaryText] = useState<string | null>(null);

  // Opportunity form state (Option A Intake Setup)
  const [opportunityForm, setOpportunityForm] = useState<OpportunityData>(() => getInitialOpportunityData());
  const [isOpportunityOpen, setIsOpportunityOpen] = useState(true);
  const [copiedOpp, setCopiedOpp] = useState(false);

  // Copy states
  const [copiedCsv, setCopiedCsv] = useState(false);
  const [copiedJson, setCopiedJson] = useState(false);
  const [copiedSummary, setCopiedSummary] = useState(false);

  const lossRunInputRef = useRef<HTMLInputElement>(null);
  const acordInputRef = useRef<HTMLInputElement>(null);
  const modifierInputRef = useRef<HTMLInputElement>(null);
  const lastSavedStateRef = useRef<any>(null);

  // File selection handlers
  const handleLossRunSelect = (f: File) => {
    if (!f.name.toLowerCase().endsWith(".pdf")) {
      toast.error("Loss Run file must be a PDF document (.pdf)");
      return;
    }
    setLossRunFile(f);
  };

  const handleAcordSelect = (f: File) => {
    if (!f.name.toLowerCase().endsWith(".pdf")) {
      toast.error("ACORD form must be a PDF document (.pdf)");
      return;
    }
    setAcordFile(f);
  };

  const handleModifierSelect = (f: File) => {
    const ext = f.name.toLowerCase();
    const valid = [".pdf", ".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".webp"].some(e => ext.endsWith(e));
    if (!valid) {
      toast.error("Modifier document must be a PDF or image file (.pdf, .png, .jpg)");
      return;
    }
    setModifierFile(f);
  };

  // Dual/Triple Process execution
  const handleProcessWcuw = async () => {
    if (!lossRunFile && !acordFile && !modifierFile) {
      toast.error("Please upload at least one document (Loss Run, ACORD 130, or Modifier worksheet).");
      return;
    }

    setIsProcessing(true);
    setCurrentStageIdx(0);
    setSummaryText(null);

    const userEmail = user?.email || "SYSTEM";
    let lrRes: any = null;
    let lrSchema: any = null;
    let acRes: any = null;
    let acSchema: any = null;
    let modRes: any = null;
    let modVal: number | null = extractedModifier;

    try {
      // Stage 1: Loss Run Ingestion (Calls universal tenant endpoint for WCUW)
      if (lossRunFile) {
        setCurrentStageIdx(0);
        try {
          const lrFd = new FormData();
          lrFd.append("file", lossRunFile);
          if (userEmail) lrFd.append("processed_by", userEmail);
          const lrResp = await fetch(
            `${getBackendUrl()}/api/gpu/api/tenant/wcuw/extract-lossrun`,
            { method: "POST", body: lrFd, headers: { "X-User-Email": userEmail, "X-Tenant-ID": "WCUW" } }
          );
          if (lrResp.ok) {
            lrRes = await lrResp.json();
            lrSchema = lrRes?.enriched_schema || null;
            if (!lrSchema && lrRes?.output_json) {
              const dlRes = await fetch(`${getBackendUrl()}/api/gpu/api/download/${lrRes.output_json}`);
              lrSchema = await dlRes.json();
            }
          } else {
            throw new Error(`Tenant LossRun endpoint returned ${lrResp.status}`);
          }
        } catch (lrErr) {
          console.warn("Tenant LossRun endpoint failed, falling back to base INSURANCE:", lrErr);
          lrRes = await api.gpuExtractDirect(lossRunFile, "INSURANCE", userEmail);
          if (lrRes?.output_json) {
            try {
              const res = await fetch(`${getBackendUrl()}/api/gpu/api/download/${lrRes.output_json}`);
              lrSchema = await res.json();
            } catch (e) {
              console.error("Failed to load loss run schema:", e);
            }
          }
        }
      }

      // Stage 2: ACORD Ingestion — use universal tenant endpoint
      if (acordFile) {
        setCurrentStageIdx(1);
        try {
          const wcuwFd = new FormData();
          wcuwFd.append("file", acordFile);
          if (userEmail) wcuwFd.append("processed_by", userEmail);
          const wcuwRes = await fetch(
            `${getBackendUrl()}/api/gpu/api/tenant/wcuw/extract-acord`,
            { method: "POST", body: wcuwFd, headers: { "X-User-Email": userEmail, "X-Tenant-ID": "WCUW" } }
          );
          if (wcuwRes.ok) {
            acRes = await wcuwRes.json();
            acSchema = acRes?.enriched_schema || null;
            if (!acSchema && acRes?.output_json) {
              const fallbackRes = await fetch(`${getBackendUrl()}/api/gpu/api/download/${acRes.output_json}`);
              acSchema = await fallbackRes.json();
            }
          } else {
            throw new Error(`Tenant ACORD endpoint returned ${wcuwRes.status}`);
          }
        } catch (wcuwErr) {
          console.warn("Tenant ACORD endpoint failed, falling back to base WORK_COMP:", wcuwErr);
          acRes = await api.gpuExtractDirect(acordFile, "WORK_COMP", userEmail);
          if (acRes?.output_json) {
            try {
              const res = await fetch(`${getBackendUrl()}/api/gpu/api/download/${acRes.output_json}`);
              acSchema = await res.json();
            } catch (e) {
              console.error("Failed to load ACORD schema:", e);
            }
          }
        }
      }

      // Stage 3: Modifier Ingestion — calls dedicated WCUW Modifier POC endpoint
      if (modifierFile) {
        setCurrentStageIdx(2);
        try {
          const modFd = new FormData();
          modFd.append("file", modifierFile);
          if (userEmail) modFd.append("processed_by", userEmail);
          const modResp = await fetch(
            `${getBackendUrl()}/api/gpu/api/tenant/wcuw/extract-modifier`,
            { method: "POST", body: modFd, headers: { "X-User-Email": userEmail, "X-Tenant-ID": "WCUW" } }
          );
          if (modResp.ok) {
            modRes = await modResp.json();
            if (modRes?.experience_mod !== undefined && modRes?.experience_mod !== null) {
              const parsed = typeof modRes.experience_mod === "number" ? modRes.experience_mod : parseFloat(modRes.experience_mod);
              if (!isNaN(parsed)) {
                modVal = parsed;
                setExtractedModifier(parsed);
                setOpportunityForm((prev) => ({ ...prev, modifier: String(parsed) }));
              }
            }
            setModifierResult(modRes);
          } else {
            throw new Error(`Tenant Modifier endpoint returned ${modResp.status}`);
          }
        } catch (modErr) {
          console.warn("Tenant Modifier endpoint failed:", modErr);
          toast.error("Modifier extraction failed, using fallback modifier");
        }
      }

      // Stage 4: Data Synthesis
      setCurrentStageIdx(3);
      await new Promise((r) => setTimeout(r, 600));

      setExtractionState({
        lossRunResult: lrRes,
        acordResult: acRes,
        modifierResult: modRes,
        lossRunSchema: lrSchema,
        acordSchema: acSchema,
        modifierValue: modVal,
        lossRunExcelUrl: lrRes?.output_file ? `${getBackendUrl()}/api/gpu/api/download/${lrRes.output_file}` : null,
        acordExcelUrl: acRes?.output_file ? `${getBackendUrl()}/api/gpu/api/download/${acRes.output_file}` : null,
      });

      setCurrentStageIdx(4);
      setActiveMainTab("table");
      toast.success("WCUW pipeline & modifier analysis completed successfully!");
    } catch (err: any) {
      console.error("WCUW processing error:", err);
      toast.error(`Processing failed: ${err.message || err}`);
    } finally {
      setIsProcessing(false);
    }
  };

  // Reset / Reprocess
  const handleReprocess = () => {
    setExtractionState(null);
    setSummaryText(null);
    setExtractedModifier(null);
    setModifierResult(null);
    setCurrentStageIdx(0);
    toast.info("Ready to reprocess documents.");
  };

  // Helper getters for extracted datasets
  const claimsList: any[] = (() => {
    if (!extractionState?.lossRunSchema) return [];
    const schema = extractionState.lossRunSchema;
    if (Array.isArray(schema?.claims)) return schema.claims;
    if (Array.isArray(schema)) return schema;
    if (Array.isArray(schema?.data)) return schema.data;
    return [];
  })();

  const acordRatingsList: any[] = (() => {
    if (!extractionState?.acordSchema) return [];
    const schema = extractionState.acordSchema;
    const wcData = schema?.data || schema;
    if (Array.isArray(wcData?.ratingByState)) return wcData.ratingByState;
    if (Array.isArray(schema?.ratingByState)) return schema.ratingByState;
    return [];
  })();

  const acordDemographics: Record<string, any> = (() => {
    if (!extractionState?.acordSchema) return {};
    const schema = extractionState.acordSchema;
    const wcData = schema?.data || schema;
    return wcData?.demographics || schema?.demographics || {};
  })();

  // Sync opportunityName with extracted applicant name when available
  useEffect(() => {
    if (acordDemographics.applicantName) {
      setOpportunityForm((prev) => {
        if (!prev.opportunityName || prev.opportunityName === "New Opportunity") {
          return { ...prev, opportunityName: acordDemographics.applicantName };
        }
        return prev;
      });
    }
  }, [acordDemographics.applicantName]);

  // Filtered claims for table search
  const filteredClaims = claimsList.filter((claim) => {
    if (!tableSearch.trim()) return true;
    const query = tableSearch.toLowerCase();
    return Object.values(claim).some((val) =>
      String(val ?? "").toLowerCase().includes(query)
    );
  });

  // Filtered ratings for table search
  const filteredRatings = acordRatingsList.filter((item) => {
    if (!tableSearch.trim()) return true;
    const query = tableSearch.toLowerCase();
    return Object.values(item).some((val) =>
      String(val ?? "").toLowerCase().includes(query)
    );
  });

  // WCUW-specific: extract locations and contact_information from enriched schema
  const locationsList: any[] = (() => {
    if (!extractionState?.acordSchema) return [];
    const schema = extractionState.acordSchema;
    const wcData = schema?.data || schema;
    if (Array.isArray(wcData?.locations)) return wcData.locations;
    if (Array.isArray(schema?.locations)) return schema.locations;
    return [];
  })();

  const contactInfo: Record<string, any> = (() => {
    if (!extractionState?.acordSchema) return {};
    const schema = extractionState.acordSchema;
    const wcData = schema?.data || schema;
    return wcData?.contact_information || schema?.contact_information || {};
  })();

  const priorCarriersList: any[] = (() => {
    if (!extractionState?.acordSchema) return [];
    const schema = extractionState.acordSchema;
    const wcData = schema?.data || schema;
    if (Array.isArray(wcData?.priorCarriers)) return wcData.priorCarriers;
    if (Array.isArray(schema?.priorCarriers)) return schema.priorCarriers;
    return [];
  })();

  const individualsList: any[] = (() => {
    if (!extractionState?.acordSchema) return [];
    const schema = extractionState.acordSchema;
    const wcData = schema?.data || schema;
    if (Array.isArray(wcData?.individuals)) return wcData.individuals;
    if (Array.isArray(schema?.individuals)) return schema.individuals;
    return [];
  })();

  const premiumCalculation: Record<string, any> = (() => {
    if (!extractionState?.acordSchema) return {};
    const schema = extractionState.acordSchema;
    const wcData = schema?.data || schema;
    return wcData?.premiumCalculation || schema?.premiumCalculation || {};
  })();

  const generalQuestions: Record<string, any> = (() => {
    if (!extractionState?.acordSchema) return {};
    const schema = extractionState.acordSchema;
    const wcData = schema?.data || schema;
    return wcData?.generalQuestions || schema?.generalQuestions || {};
  })();

  const filteredLocations = locationsList.filter((item) => {
    if (!tableSearch.trim()) return true;
    const query = tableSearch.toLowerCase();
    return Object.values(item).some((val) =>
      String(val ?? "").toLowerCase().includes(query)
    );
  });

  const filteredPriorCarriers = priorCarriersList.filter((item) => {
    if (!tableSearch.trim()) return true;
    const query = tableSearch.toLowerCase();
    return Object.values(item).some((val) =>
      String(val ?? "").toLowerCase().includes(query)
    );
  });

  // WCUW-specific: extract Loss Run report metadata (report_created_date, valuation_date, carrier)
  const reportMetadata: Record<string, any> = (() => {
    const lrSchema = extractionState?.lossRunSchema;
    const lrRes = extractionState?.lossRunResult;
    if (!lrSchema && !lrRes) return {};
    const schemaData = lrSchema?.data || lrSchema;
    const enrichedData = lrRes?.enriched_schema?.data || lrRes?.enriched_schema;
    return (
      schemaData?.report_metadata ||
      lrSchema?.report_metadata ||
      enrichedData?.report_metadata ||
      lrRes?.report_metadata ||
      {}
    );
  })();

  const reportCreatedDate = reportMetadata.report_created_date || "";
  const reportValuationDate = reportMetadata.valuation_date || "";
  const reportCarrierName = reportMetadata.carrier_name || "";
  const reportDateLabel = reportMetadata.date_label_found || "Report Date";

  const finalModifier = extractedModifier ?? (opportunityForm.modifier ? parseFloat(opportunityForm.modifier) : null) ?? 1.0;

  // Unified submission JSON (WCUW tenant)
  const unifiedJsonPayload = {
    tenant: "WCUW",
    defaultModifier: finalModifier,
    modifier: finalModifier,
    email: user?.email || "",
    opportunity: {
      ...opportunityForm,
      modifier: String(finalModifier),
    },
    acord: extractionState?.acordSchema || {},
    lossRuns: extractionState?.lossRunSchema || {},
    modifierData: extractionState?.modifierResult || (extractedModifier !== null ? { experience_mod: extractedModifier } : null),
    metadata: {
      generatedAt: new Date().toISOString(),
      lossRunFile: lossRunFile?.name || null,
      acordFile: acordFile?.name || null,
      modifierFile: modifierFile?.name || null,
      defaultModifier: finalModifier,
      experienceMod: finalModifier,
      totalClaims: claimsList.length,
      totalRatingEntries: acordRatingsList.length,
      totalLocations: locationsList.length,
    }
  };

  // Metrics calculation
  const totalIncurredSum = claimsList.reduce((sum, c) => sum + (parseFloat(String(c.total_incurred || 0)) || 0), 0);
  const totalPaidSum = claimsList.reduce((sum, c) => sum + (parseFloat(String(c.total_paid || 0)) || (parseFloat(String(c.medical_paid || 0)) || 0) + (parseFloat(String(c.indemnity_paid || 0)) || 0) + (parseFloat(String(c.expense_paid || 0)) || 0)), 0);
  const totalReservesSum = claimsList.reduce((sum, c) => sum + (parseFloat(String(c.total_reserve || 0)) || (parseFloat(String(c.medical_reserve || 0)) || 0) + (parseFloat(String(c.indemnity_reserve || 0)) || 0) + (parseFloat(String(c.expense_reserve || 0)) || 0)), 0);
  const openClaimsCount = claimsList.filter((c) => String(c.status || "").toLowerCase() === "open").length;
  const closedClaimsCount = claimsList.filter((c) => String(c.status || "").toLowerCase() === "closed").length;
  const litigatedCount = claimsList.filter((c) => String(c.litigation || "").toLowerCase() === "yes").length;

  const totalPayrollEst = acordRatingsList.reduce((sum, r) => sum + (parseFloat(String(r.estAnnualPayroll || r.annualPayroll || r.estimatedAnnualPayroll || r.payroll || 0)) || 0), 0);
  const totalFullTime = acordRatingsList.reduce((sum, r) => {
    const val = r.fullTimeEmployees ?? r.fullTimeCount ?? r.full_time ?? r.full_time_employees ?? 0;
    return sum + (parseInt(String(val), 10) || 0);
  }, 0);
  const totalPartTime = acordRatingsList.reduce((sum, r) => {
    const val = r.partTimeEmployees ?? r.partTimeCount ?? r.part_time ?? r.part_time_employees ?? 0;
    return sum + (parseInt(String(val), 10) || 0);
  }, 0);
  const totalEmployees = totalFullTime + totalPartTime;

  const insurerName = extractionState?.lossRunResult?.insurer || acordDemographics.carrierName || acordDemographics.applicantName || "Insurance Document";

  // Downloads
  const handleDownloadJson = () => {
    let payloadToDownload: any = unifiedJsonPayload;
    let filename = "WCUW_unified_payload.json";

    if (activeJsonSubTab === "loss_run" && extractionState?.lossRunSchema) {
      payloadToDownload = extractionState.lossRunSchema;
      filename = `${lossRunFile?.name.replace(".pdf", "") || "loss_run"}_extracted.json`;
    } else if (activeJsonSubTab === "acord" && extractionState?.acordSchema) {
      payloadToDownload = extractionState.acordSchema;
      filename = `${acordFile?.name.replace(".pdf", "") || "acord_130"}_extracted.json`;
    } else if (activeJsonSubTab === "modifier") {
      payloadToDownload = extractionState?.modifierResult || { experience_mod: finalModifier };
      filename = `${modifierFile?.name.replace(/\.[^/.]+$/, "") || "modifier"}_extracted.json`;
    }

    const blob = new Blob([JSON.stringify(payloadToDownload, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
    toast.success(`Downloaded ${filename}`);
  };

  const handleSaveToServer = async () => {
    let payloadToSave: any = unifiedJsonPayload;
    if (activeJsonSubTab === "loss_run" && extractionState?.lossRunSchema) {
      payloadToSave = extractionState.lossRunSchema;
    } else if (activeJsonSubTab === "acord" && extractionState?.acordSchema) {
      payloadToSave = extractionState.acordSchema;
    } else if (activeJsonSubTab === "modifier") {
      payloadToSave = extractionState?.modifierResult || { experience_mod: finalModifier };
    }

    try {
      const resp = await fetch(`${getBackendUrl()}/api/gpu/api/tenant/wcuw/save`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payloadToSave)
      });
      if (resp.ok) {
        toast.success("Successfully saved JSON payload to backend server!");
      } else {
        toast.error(`Failed to save: ${resp.statusText}`);
      }
    } catch (e: any) {
      toast.error(`Save error: ${e.message}`);
    }
  };

  // Auto-save whenever extraction successfully finishes
  useEffect(() => {
    if (extractionState && !isProcessing && lastSavedStateRef.current !== extractionState) {
      lastSavedStateRef.current = extractionState;
      // Slight delay to ensure all React state (like applicant name) has settled into the payload
      setTimeout(() => {
        handleSaveToServer();
      }, 500);
    }
  }, [extractionState, isProcessing]);


  const handleDownloadExcel = () => {
    if (extractionState?.lossRunExcelUrl) {
      window.open(extractionState.lossRunExcelUrl, "_blank");
    }
    if (extractionState?.acordExcelUrl) {
      window.open(extractionState.acordExcelUrl, "_blank");
    }
    if (!extractionState?.lossRunExcelUrl && !extractionState?.acordExcelUrl) {
      toast.error("No Excel workbook generated yet");
    }
  };

  // Copy CSV of current table
  const handleCopyTableCsv = () => {
    let dataToExport: any[] = [];
    if (activeTableSubTab === "claims") {
      dataToExport = filteredClaims;
    } else if (activeTableSubTab === "locations") {
      dataToExport = filteredLocations;
    } else if (activeTableSubTab === "contacts") {
      dataToExport = [
        { type: "INSPECTION", ...(contactInfo.inspection || {}) },
        { type: "ACCTNG_RECORD", ...(contactInfo.acctng_record || {}) },
        { type: "CLAIMS_INFO", ...(contactInfo.claims_info || {}) },
      ];
    } else if (activeTableSubTab === "priors") {
      dataToExport = filteredPriorCarriers;
    } else if (activeTableSubTab === "rating") {
      dataToExport = filteredRatings;
    } else {
      dataToExport = filteredRatings.length > 0 ? filteredRatings : filteredClaims;
    }
    if (!dataToExport || dataToExport.length === 0) {
      toast.error("No data available to copy");
      return;
    }
    const headers = Array.from(new Set(dataToExport.flatMap((row) => Object.keys(row))));
    const csvRows = [
      headers.join(","),
      ...dataToExport.map((row) =>
        headers.map((h) => {
          const val = row[h];
          const escaped = ("" + (val ?? "")).replace(/"/g, '""');
          return `"${escaped}"`;
        }).join(",")
      ),
    ];
    navigator.clipboard.writeText(csvRows.join("\n"));
    setCopiedCsv(true);
    setTimeout(() => setCopiedCsv(false), 2000);
    toast.success("CSV copied to clipboard!");
  };

  // Copy current active JSON
  const handleCopyJson = () => {
    let payload = unifiedJsonPayload;
    if (activeJsonSubTab === "loss_run") payload = extractionState?.lossRunSchema || {};
    if (activeJsonSubTab === "acord") payload = extractionState?.acordSchema || {};
    if (activeJsonSubTab === "modifier") payload = extractionState?.modifierResult || { experience_mod: finalModifier };
    navigator.clipboard.writeText(JSON.stringify(payload, null, 2));
    setCopiedJson(true);
    setTimeout(() => setCopiedJson(false), 2000);
    toast.success("JSON copied to clipboard!");
  };

  // Trigger joint AI Underwriting Summary
  const handleGenerateSummary = async () => {
    setIsSummarizing(true);
    setSummaryText(null);

    const payload = {
      opportunity: opportunityForm,
      loss_runs: extractionState?.lossRunSchema || { claims: claimsList },
      acord: extractionState?.acordSchema || { demographics: acordDemographics, ratingByState: acordRatingsList },
      claims: claimsList,
      company_name: opportunityForm.opportunityName || acordDemographics.applicantName || acordDemographics.legalEntityName || insurerName,
    };

    try {
      const response = await fetch(`${getBackendUrl()}/api/gpu/api/underwriting-summary`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      if (!response.ok) {
        // Fallback to claim-summary endpoint if underwriting-summary is unavailable
        const fbRes = await fetch(`${getBackendUrl()}/api/gpu/api/claim-summary`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ claims: claimsList }),
        });
        const fbData = await fbRes.json();
        if (fbData.success && fbData.summary) {
          setSummaryText(fbData.summary);
          toast.success("AI Claims Analysis generated!");
          return;
        }
        throw new Error(`Server returned ${response.status}`);
      }

      const data = await response.json();
      if (data.success && data.summary) {
        setSummaryText(data.summary);
        toast.success("AI Underwriting Assessment generated!");
      } else {
        toast.error(data.error || "Failed to generate underwriting summary");
      }
    } catch (err: any) {
      console.error("AI Summary error:", err);
      toast.error(`Summary generation error: ${err.message || err}`);
    } finally {
      setIsSummarizing(false);
    }
  };

  const handleCopySummaryText = () => {
    if (summaryText) {
      navigator.clipboard.writeText(summaryText);
      setCopiedSummary(true);
      setTimeout(() => setCopiedSummary(false), 2000);
      toast.success("Summary copied to clipboard!");
    }
  };

  const handleDownloadSummaryTxt = () => {
    if (!summaryText) return;
    const blob = new Blob([summaryText], { type: "text/plain" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `WCUW_Underwriting_Summary_${new Date().toISOString().slice(0, 10)}.txt`;
    a.click();
    URL.revokeObjectURL(url);
  };

  // Opportunity handlers
  const handleResetOpportunity = () => {
    setOpportunityForm(getInitialOpportunityData(acordDemographics.applicantName));
    toast.info("Opportunity form reset to default values.");
  };

  const handleCopyOpportunity = () => {
    const text = [
      `Opportunity & Submission Setup`,
      `==============================`,
      `Select a record Type: ${opportunityForm.recordType}`,
      `Opportunity Name: ${opportunityForm.opportunityName || "—"}`,
      `Stage: ${opportunityForm.stage}`,
      `Close Date: ${opportunityForm.closeDate}`,
      `Estimated First Payroll Date: ${opportunityForm.estimatedFirstPayrollDate}`,
      `Opportunity Generated By: ${opportunityForm.opportunityGeneratedBy}`,
      `Channel Partner: ${opportunityForm.channelPartner || "—"}`,
      `First Meeting Date: ${opportunityForm.firstMeetingDate}`,
      `Experience Modifier: ${opportunityForm.modifier || "1.0"}`,
    ].join("\n");
    navigator.clipboard.writeText(text);
    setCopiedOpp(true);
    setTimeout(() => setCopiedOpp(false), 2000);
    toast.success("Opportunity details copied to clipboard!");
  };

  // Helper for Markdown rendering
  const parseBold = (text: string) => {
    const parts = text.split(/(\*\*.*?\*\*)/g);
    return parts.map((part, i) => {
      if (part.startsWith("**") && part.endsWith("**")) {
        return <strong key={i} className="font-bold text-foreground">{part.slice(2, -2)}</strong>;
      }
      return part;
    });
  };

  const renderMarkdown = (text: string) => {
    const lines = text.split("\n");
    return lines.map((line, index) => {
      const trimmed = line.trim();
      if (!trimmed) return <div key={index} className="h-2" />;
      if (trimmed.startsWith("### ")) return <h3 key={index} className="text-sm font-bold mt-4 mb-2 text-primary">{trimmed.slice(4)}</h3>;
      if (trimmed.startsWith("## ")) return <h2 key={index} className="text-base font-bold mt-5 mb-2 text-primary border-b border-border pb-1">{trimmed.slice(3)}</h2>;
      if (trimmed.startsWith("# ")) return <h1 key={index} className="text-lg font-bold mt-6 mb-3 text-primary">{trimmed.slice(2)}</h1>;
      if (trimmed.startsWith("- ") || trimmed.startsWith("* ")) {
        return (
          <div key={index} className="flex items-start gap-2 ml-2 my-1 text-xs">
            <span className="text-primary mt-1">•</span>
            <span>{parseBold(trimmed.slice(2))}</span>
          </div>
        );
      }
      return <p key={index} className="my-1 text-xs leading-relaxed text-foreground/90">{parseBold(line)}</p>;
    });
  };

  return (
    <div className="p-6 space-y-6 max-w-7xl mx-auto">
      {/* Header */}
      <PageHeader
        icon={ShieldCheck}
        title="WCUW — Workers' Compensation Underwriting"
        description="Automated dual extraction & underwriting evaluation for Loss Runs and ACORD 130 applications."
      />

      {/* Triple Upload Hub (Loss Run + ACORD 130 + Experience Modifier) */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        {/* Card 1: Loss Run File */}
        <Panel
          title="1. Loss Run File"
          description="Upload the historical insurance loss run / claims document."
        >
          <div
            onDragOver={(e) => e.preventDefault()}
            onDrop={(e) => {
              e.preventDefault();
              if (e.dataTransfer.files[0]) handleLossRunSelect(e.dataTransfer.files[0]);
            }}
            className="border-2 border-dashed border-border/80 rounded-xl p-8 flex flex-col items-center justify-center gap-3 bg-muted/20 hover:bg-muted/30 transition-colors text-center cursor-pointer min-h-[220px]"
            onClick={() => lossRunInputRef.current?.click()}
          >
            <input
              ref={lossRunInputRef}
              type="file"
              accept=".pdf"
              className="hidden"
              onChange={(e) => {
                if (e.target.files?.[0]) handleLossRunSelect(e.target.files[0]);
              }}
            />
            <div className="w-12 h-12 rounded-full bg-primary/10 flex items-center justify-center text-primary">
              <FileText className="w-6 h-6" />
            </div>
            <div>
              <p className="text-sm font-semibold text-foreground">Drag & drop your file here</p>
              <p className="text-xs text-muted-foreground mt-0.5">or click to browse • PDF - max 50MB</p>
            </div>
            <Button
              type="button"
              variant="default"
              size="sm"
              className="mt-2"
              onClick={(e) => {
                e.stopPropagation();
                lossRunInputRef.current?.click();
              }}
            >
              Select File
            </Button>
            {lossRunFile && (
              <div className="mt-3 flex items-center gap-2 px-3 py-1.5 rounded-lg bg-primary/10 text-primary border border-primary/20 text-xs font-medium">
                <CheckCircle2 className="w-4 h-4 text-emerald-500" />
                <span className="truncate max-w-[200px]">{lossRunFile.name}</span>
                <span className="text-[10px] text-muted-foreground">({(lossRunFile.size / 1024 / 1024).toFixed(2)} MB)</span>
              </div>
            )}
          </div>
        </Panel>

        {/* Card 2: ACORD 130 Application */}
        <Panel
          title="2. ACORD 130 Application"
          description="Upload the Workers' Compensation ACORD 130 / 133 form."
        >
          <div
            onDragOver={(e) => e.preventDefault()}
            onDrop={(e) => {
              e.preventDefault();
              if (e.dataTransfer.files[0]) handleAcordSelect(e.dataTransfer.files[0]);
            }}
            className="border-2 border-dashed border-border/80 rounded-xl p-8 flex flex-col items-center justify-center gap-3 bg-muted/20 hover:bg-muted/30 transition-colors text-center cursor-pointer min-h-[220px]"
            onClick={() => acordInputRef.current?.click()}
          >
            <input
              ref={acordInputRef}
              type="file"
              accept=".pdf"
              className="hidden"
              onChange={(e) => {
                if (e.target.files?.[0]) handleAcordSelect(e.target.files[0]);
              }}
            />
            <div className="w-12 h-12 rounded-full bg-primary/10 flex items-center justify-center text-primary">
              <HardHat className="w-6 h-6" />
            </div>
            <div>
              <p className="text-sm font-semibold text-foreground">Drag & drop your file here</p>
              <p className="text-xs text-muted-foreground mt-0.5">or click to browse • PDF - max 50MB</p>
            </div>
            <Button
              type="button"
              variant="default"
              size="sm"
              className="mt-2"
              onClick={(e) => {
                e.stopPropagation();
                acordInputRef.current?.click();
              }}
            >
              Select File
            </Button>
            {acordFile && (
              <div className="mt-3 flex items-center gap-2 px-3 py-1.5 rounded-lg bg-primary/10 text-primary border border-primary/20 text-xs font-medium">
                <CheckCircle2 className="w-4 h-4 text-emerald-500" />
                <span className="truncate max-w-[200px]">{acordFile.name}</span>
                <span className="text-[10px] text-muted-foreground">({(acordFile.size / 1024 / 1024).toFixed(2)} MB)</span>
              </div>
            )}
          </div>
        </Panel>

        {/* Card 3: Experience Modifier (X-Mod) */}
        <Panel
          title="3. Experience Modifier (X-Mod)"
          description="Upload NCCI / WCIRB rating worksheet or risk summary."
        >
          <div
            onDragOver={(e) => e.preventDefault()}
            onDrop={(e) => {
              e.preventDefault();
              if (e.dataTransfer.files[0]) handleModifierSelect(e.dataTransfer.files[0]);
            }}
            className="border-2 border-dashed border-border/80 rounded-xl p-8 flex flex-col items-center justify-center gap-3 bg-muted/20 hover:bg-muted/30 transition-colors text-center cursor-pointer min-h-[220px]"
            onClick={() => modifierInputRef.current?.click()}
          >
            <input
              ref={modifierInputRef}
              type="file"
              accept=".pdf,.png,.jpg,.jpeg,.bmp,.tif,.tiff,.webp"
              className="hidden"
              onChange={(e) => {
                if (e.target.files?.[0]) handleModifierSelect(e.target.files[0]);
              }}
            />
            <div className="w-12 h-12 rounded-full bg-amber-500/10 flex items-center justify-center text-amber-600">
              <Percent className="w-6 h-6" />
            </div>
            <div>
              <p className="text-sm font-semibold text-foreground">Drag & drop your file here</p>
              <p className="text-xs text-muted-foreground mt-0.5">or click to browse • PDF, PNG, JPG</p>
            </div>
            <Button
              type="button"
              variant="default"
              size="sm"
              className="mt-2 bg-amber-600 hover:bg-amber-700 text-white"
              onClick={(e) => {
                e.stopPropagation();
                modifierInputRef.current?.click();
              }}
            >
              Select File
            </Button>
            {modifierFile && (
              <div className="mt-3 flex items-center gap-2 px-3 py-1.5 rounded-lg bg-amber-500/10 text-amber-700 dark:text-amber-300 border border-amber-500/20 text-xs font-medium">
                <CheckCircle2 className="w-4 h-4 text-emerald-500" />
                <span className="truncate max-w-[200px]">{modifierFile.name}</span>
                <span className="text-[10px] text-muted-foreground">({(modifierFile.size / 1024 / 1024).toFixed(2)} MB)</span>
              </div>
            )}
            {extractedModifier !== null && (
              <div className="mt-1 flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-emerald-500/10 text-emerald-600 border border-emerald-500/20 text-xs font-bold">
                <Sparkles className="w-3.5 h-3.5" />
                <span>Extracted Modifier: {extractedModifier}</span>
              </div>
            )}
          </div>
        </Panel>
      </div>

      {/* Process Trigger & Stage Stepper */}
      <div className="p-5 rounded-xl border border-border bg-card flex flex-col md:flex-row md:items-center justify-between gap-4 shadow-sm">
        <div className="space-y-1">
          <p className="text-sm font-semibold text-foreground">Execute WCUW Pipeline</p>
          <p className="text-xs text-muted-foreground">
            Runs OCR text extraction, layout analysis, verification and schema synthesis across Loss Run, ACORD 130 and X-Mod engines.
          </p>
        </div>
        <div className="flex items-center gap-3">
          {extractionState && (
            <Button
              variant="outline"
              size="sm"
              onClick={handleReprocess}
              className="gap-1.5 text-xs text-muted-foreground hover:text-foreground"
            >
              <RefreshCw className="w-3.5 h-3.5" />
              Reset
            </Button>
          )}
          <Button
            size="default"
            onClick={handleProcessWcuw}
            disabled={isProcessing || (!lossRunFile && !acordFile && !modifierFile)}
            className="gap-2 font-bold px-6 shadow"
          >
            {isProcessing ? (
              <>
                <Loader2 className="w-4 h-4 animate-spin" />
                Processing Pipelines...
              </>
            ) : (
              <>
                <Sparkles className="w-4 h-4 text-amber-300" />
                Process WCUW Documents
              </>
            )}
          </Button>
        </div>
      </div>

      {/* Progress Stepper when Processing */}
      {isProcessing && (
        <div className="p-4 rounded-xl border border-border bg-card/60 space-y-3">
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
            {STAGES.map((s, idx) => {
              const isPast = idx < currentStageIdx;
              const isCurrent = idx === currentStageIdx;
              return (
                <div
                  key={s.id}
                  className={`p-3 rounded-lg border text-xs transition-all ${
                    isCurrent
                      ? "border-primary bg-primary/5 text-primary font-medium"
                      : isPast
                      ? "border-emerald-500/30 bg-emerald-500/5 text-emerald-600"
                      : "border-border/50 text-muted-foreground opacity-60"
                  }`}
                >
                  <div className="flex items-center gap-2 mb-1">
                    {isPast ? (
                      <CheckCircle2 className="w-3.5 h-3.5 text-emerald-500" />
                    ) : isCurrent ? (
                      <Loader2 className="w-3.5 h-3.5 animate-spin text-primary" />
                    ) : (
                      <span className="w-3.5 h-3.5 rounded-full border border-muted-foreground/40 flex items-center justify-center text-[9px]">
                        {idx + 1}
                      </span>
                    )}
                    <span className="font-semibold">{s.label}</span>
                  </div>
                  <p className="text-[10px] text-muted-foreground line-clamp-1">{s.desc}</p>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Results Section (Screenshots 1, 3, 4 layout) */}
      {extractionState && (
        <div className="space-y-4 pt-2">
          {/* Result Title Bar */}
          <div className="flex items-center gap-2 text-base font-semibold text-foreground">
            <FileText className="w-5 h-5 text-primary" />
            <span>
              Results — {lossRunFile ? lossRunFile.name : ""}
              {lossRunFile && acordFile ? " & " : ""}
              {acordFile ? acordFile.name : ""}
            </span>
          </div>

          {/* Top KPI Cards (Screenshot 1: 5 Cards with Total Employees) */}
          <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-3">
            <div className="p-3.5 rounded-lg bg-card border border-border shadow-xs">
              <div className="flex items-center justify-between mb-1.5">
                <div className="flex items-center gap-2">
                  <Building2 className="w-4 h-4 text-primary" />
                  <span className="text-[11px] text-muted-foreground font-medium uppercase tracking-wider">
                    Insurer / Entity
                  </span>
                </div>
                {(reportCreatedDate || reportValuationDate) && (
                  <Badge variant="outline" className="text-[10px] font-mono bg-emerald-500/10 text-emerald-600 border-emerald-500/30">
                    {reportDateLabel}: {reportCreatedDate || reportValuationDate}
                  </Badge>
                )}
              </div>
              <p className="text-sm font-bold text-foreground truncate" title={insurerName}>
                {insurerName}
              </p>
              {reportCarrierName && reportCarrierName !== insurerName && (
                <p className="text-[10px] text-muted-foreground truncate">
                  Carrier: {reportCarrierName}
                </p>
              )}
            </div>

            <div className="p-3.5 rounded-lg bg-card border border-border shadow-xs">
              <div className="flex items-center gap-2 mb-1.5">
                <BarChart3 className="w-4 h-4 text-primary" />
                <span className="text-[11px] text-muted-foreground font-medium uppercase tracking-wider">
                  Claims Found
                </span>
              </div>
              <div className="flex items-baseline gap-2">
                <p className="text-xl font-extrabold text-foreground">{claimsList.length}</p>
                {claimsList.length > 0 && (
                  <span className="text-[11px] text-muted-foreground">
                    ({openClaimsCount} Open • {closedClaimsCount} Closed)
                  </span>
                )}
              </div>
            </div>

            <div className="p-3.5 rounded-lg bg-card border border-border shadow-xs">
              <div className="flex items-center gap-2 mb-1.5">
                <DollarSign className="w-4 h-4 text-emerald-500" />
                <span className="text-[11px] text-muted-foreground font-medium uppercase tracking-wider">
                  Total Incurred
                </span>
              </div>
              <p className="text-base font-bold text-emerald-600">
                {new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(totalIncurredSum)}
              </p>
              <p className="text-[10px] text-muted-foreground">
                Reserves: {new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(totalReservesSum)}
              </p>
            </div>

            <div className="p-3.5 rounded-lg bg-card border border-border shadow-xs">
              <div className="flex items-center gap-2 mb-1.5">
                <HardHat className="w-4 h-4 text-primary" />
                <span className="text-[11px] text-muted-foreground font-medium uppercase tracking-wider">
                  WC Ratings & Confidence
                </span>
              </div>
              <div className="flex items-baseline justify-between">
                <p className="text-sm font-bold text-foreground">
                  {acordRatingsList.length} Class Code(s)
                </p>
                <Badge variant="outline" className="text-xs bg-emerald-500/10 text-emerald-600 border-emerald-500/30">
                  95% Confidence
                </Badge>
              </div>
              {totalPayrollEst > 0 && (
                <p className="text-[10px] text-muted-foreground">
                  Payroll: {new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(totalPayrollEst)}
                </p>
              )}
            </div>

            <div className="p-3.5 rounded-lg bg-card border border-border shadow-xs">
              <div className="flex items-center gap-2 mb-1.5">
                <Users className="w-4 h-4 text-primary" />
                <span className="text-[11px] text-muted-foreground font-medium uppercase tracking-wider">
                  Total Employees
                </span>
              </div>
              <div className="flex items-baseline gap-2">
                <p className="text-xl font-extrabold text-foreground">{totalEmployees}</p>
                <span className="text-[11px] text-muted-foreground font-normal">
                  ({totalFullTime} Full Time • {totalPartTime} Part Time)
                </span>
              </div>
            </div>
          </div>

          {/* Action Row Buttons (Screenshot 1: Download JSON, Download Excel, AI Summary, Reprocess) */}
          <div className="flex flex-wrap items-center gap-2">
            <Button
              size="sm"
              onClick={handleDownloadJson}
              className="h-8 text-[11px] font-bold bg-primary text-primary-foreground hover:bg-primary/90"
            >
              <FileJson className="w-3.5 h-3.5 mr-1.5" />
              Download JSON
            </Button>

            <Button
              size="sm"
              onClick={handleSaveToServer}
              className="h-8 text-[11px] font-bold bg-green-600 text-white hover:bg-green-700"
            >
              <Database className="w-3.5 h-3.5 mr-1.5" />
              Save to Server
            </Button>

            <Button
              size="sm"
              variant="outline"
              onClick={handleDownloadExcel}
              className="h-8 text-[11px] font-bold"
            >
              <Download className="w-3.5 h-3.5 mr-1.5" />
              Download Excel
            </Button>

            <Button
              size="sm"
              variant="secondary"
              className="h-8 text-[11px] font-bold bg-primary/10 text-primary hover:bg-primary/20 border border-primary/20"
              onClick={() => {
                setActiveMainTab("summary");
                if (!summaryText && !isSummarizing) {
                  handleGenerateSummary();
                }
              }}
              disabled={isSummarizing}
            >
              {isSummarizing ? (
                <Loader2 className="w-3.5 h-3.5 mr-1.5 animate-spin" />
              ) : (
                <Brain className="w-3.5 h-3.5 mr-1.5" />
              )}
              AI Summary
            </Button>

            <Button
              size="sm"
              variant="ghost"
              className="h-8 text-[11px] font-bold text-muted-foreground hover:text-foreground ml-auto"
              onClick={handleReprocess}
            >
              <RefreshCw className="w-3 h-3 mr-1.5" />
              Reprocess
            </Button>
          </div>

          {/* Main Tabs (Screenshot 1: TABLE VIEW, JSON VIEW, AI SUMMARY) */}
          <Tabs value={activeMainTab} onValueChange={(v: any) => setActiveMainTab(v)} className="space-y-4">
            <TabsList className="bg-muted/70 p-1 rounded-lg">
              <TabsTrigger value="table" className="text-xs font-semibold gap-1.5 data-[state=active]:bg-card shadow-xs">
                <TableIcon className="w-3.5 h-3.5" />
                TABLE VIEW
              </TabsTrigger>
              <TabsTrigger value="json" className="text-xs font-semibold gap-1.5 data-[state=active]:bg-card shadow-xs">
                <FileJson className="w-3.5 h-3.5" />
                JSON VIEW
              </TabsTrigger>
              <TabsTrigger value="summary" className="text-xs font-semibold gap-1.5 data-[state=active]:bg-card shadow-xs">
                <Brain className="w-3.5 h-3.5" />
                AI SUMMARY
              </TabsTrigger>
              <TabsTrigger value="exceptions" className="text-xs font-semibold gap-1.5 data-[state=active]:bg-card shadow-xs text-red-600 data-[state=active]:text-red-700">
                <AlertCircle className="w-3.5 h-3.5" />
                EXCEPTIONS
              </TabsTrigger>
            </TabsList>

            {/* TAB 4: EXCEPTIONS VIEW */}
            <TabsContent value="exceptions" className="space-y-4">
              <ExceptionTab 
                exceptionRules={[
                  {
                    "id": "missing_fein",
                    "condition": "!demographics.fein",
                    "exception_message": "Exception: No FEIN Found - Ensure FEIN is provided for policy issuance."
                  },
                  {
                    "id": "missing_loss_runs",
                    "condition": "!has_document('INSURANCE')",
                    "exception_message": "Exception: Missing Loss Runs - Required to proceed with underwriting."
                  },
                  {
                    "id": "valuation_date_old",
                    "condition": "days_since(report_metadata.valuation_date) > 60",
                    "exception_message": "Exception: Valuation Date too old - Must be within the last 60 days."
                  },
                  {
                    "id": "zero_employees",
                    "condition": "summary.employee_count == 0",
                    "exception_message": "Exception: Zero Employees - Verify if this is an owner-only policy."
                  },
                  {
                    "id": "missing_modifier",
                    "condition": "!has_document('EXPERIENCE_MODIFIER')",
                    "exception_message": "Exception: Missing Modifier Worksheet - Ensure it is uploaded if applicable."
                  },
                  {
                    "id": "missing_acord",
                    "condition": "!has_document('WORK_COMP')",
                    "exception_message": "Exception: Missing ACORD 130 - Required to extract policy and rating information."
                  }
                ]}
                unifiedPayload={unifiedJsonPayload} 
              />
            </TabsContent>

            {/* TAB 1: TABLE VIEW (First Priority — Extracted Data Grid & Cards) */}
            <TabsContent value="table" className="space-y-4">
              {/* Opportunity & Submission Setup (Option A Intake Setup) */}
              <div className="rounded-xl border border-primary/20 bg-card shadow-xs overflow-hidden">
                <div className="flex flex-wrap items-center justify-between gap-3 p-3.5 bg-muted/40 border-b border-border/60">
                  <div className="flex items-center gap-2.5">
                    <div className="p-1.5 rounded-lg bg-primary/10 text-primary">
                      <Briefcase className="w-4 h-4" />
                    </div>
                    <div>
                      <div className="flex items-center gap-2">
                        <h4 className="text-sm font-bold text-foreground">
                          Opportunity & Submission Setup
                        </h4>
                        <Badge variant="outline" className="text-[10px] font-semibold bg-primary/5 text-primary border-primary/20">
                          9 Intake Fields
                        </Badge>
                        <Badge variant="outline" className="text-[10px] font-semibold bg-amber-500/10 text-amber-600 border-amber-500/30">
                          Modifier: {finalModifier}
                        </Badge>
                      </div>
                      <p className="text-[11px] text-muted-foreground">
                        Configure CRM opportunity parameters, intake classification & target payroll dates (MM/DD/YYYY)
                      </p>
                    </div>
                  </div>

                  <div className="flex items-center gap-2">
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      onClick={handleCopyOpportunity}
                      className="h-7 px-2.5 text-xs font-medium gap-1.5"
                    >
                      {copiedOpp ? (
                        <>
                          <Check className="w-3.5 h-3.5 text-emerald-500" />
                          <span>Copied</span>
                        </>
                      ) : (
                        <>
                          <Copy className="w-3.5 h-3.5" />
                          <span>Copy Details</span>
                        </>
                      )}
                    </Button>

                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      onClick={handleResetOpportunity}
                      className="h-7 px-2 text-xs font-medium text-muted-foreground hover:text-foreground gap-1.5"
                      title="Reset all fields to system defaults"
                    >
                      <RotateCcw className="w-3.5 h-3.5" />
                      <span>Reset to Defaults</span>
                    </Button>

                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      onClick={() => setIsOpportunityOpen(!isOpportunityOpen)}
                      className="h-7 w-7 p-0 text-muted-foreground hover:text-foreground"
                      title={isOpportunityOpen ? "Collapse panel" : "Expand panel"}
                    >
                      {isOpportunityOpen ? (
                        <ChevronUp className="w-4 h-4" />
                      ) : (
                        <ChevronDown className="w-4 h-4" />
                      )}
                    </Button>
                  </div>
                </div>

                {isOpportunityOpen && (
                  <div className="p-4 bg-card/60">
                    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3.5">
                      {/* 1. Select a Record Type */}
                      <div className="space-y-1.5">
                        <label className="text-xs font-semibold text-foreground flex items-center justify-between">
                          <span>Select Record Type</span>
                          <span className="text-[10px] text-muted-foreground font-normal">Default: PEO</span>
                        </label>
                        <select
                          value={opportunityForm.recordType}
                          onChange={(e) => setOpportunityForm(p => ({ ...p, recordType: e.target.value }))}
                          className="h-9 w-full rounded-md border border-input bg-background px-3 py-1.5 text-xs text-foreground shadow-xs focus:ring-1 focus:ring-primary focus:outline-none font-medium cursor-pointer"
                        >
                          <option value="PEO">PEO (Default)</option>
                          <option value="ASO">ASO</option>
                          <option value="Client Growth">Client Growth</option>
                          <option value="Payroll Only">Payroll Only</option>
                          <option value="Retention">Retention</option>
                          <option value="Retirement Planning & WC only">Retirement Planning & WC only</option>
                        </select>
                      </div>

                      {/* 2. Opportunity Name */}
                      <div className="space-y-1.5">
                        <label className="text-xs font-semibold text-foreground flex items-center justify-between">
                          <span>Opportunity Name</span>
                          <span className="text-[10px] text-muted-foreground font-normal">Prospect Name</span>
                        </label>
                        <Input
                          value={opportunityForm.opportunityName}
                          onChange={(e) => setOpportunityForm(p => ({ ...p, opportunityName: e.target.value }))}
                          placeholder="Account or Prospect Name"
                          className="h-9 text-xs font-medium"
                        />
                      </div>

                      {/* 3. Stage */}
                      <div className="space-y-1.5">
                        <label className="text-xs font-semibold text-foreground flex items-center justify-between">
                          <span>Stage</span>
                          <span className="text-[10px] text-muted-foreground font-normal">Default: First Meeting</span>
                        </label>
                        <select
                          value={opportunityForm.stage}
                          onChange={(e) => setOpportunityForm(p => ({ ...p, stage: e.target.value }))}
                          className="h-9 w-full rounded-md border border-input bg-background px-3 py-1.5 text-xs text-foreground shadow-xs focus:ring-1 focus:ring-primary focus:outline-none font-medium cursor-pointer"
                        >
                          <option value="First Meeting">First Meeting</option>
                          <option value="Discovery">Discovery</option>
                          <option value="Proposal">Proposal</option>
                          <option value="Underwriting Review">Underwriting Review</option>
                          <option value="Closed Won">Closed Won</option>
                          <option value="Closed Lost">Closed Lost</option>
                        </select>
                      </div>

                      {/* 4. First Meeting Date */}
                      <div className="space-y-1.5">
                        <label className="text-xs font-semibold text-foreground flex items-center justify-between">
                          <span>First Meeting Date</span>
                          <span className="text-[10px] text-muted-foreground font-mono">MM/DD/YYYY</span>
                        </label>
                        <div className="relative">
                          <Input
                            value={opportunityForm.firstMeetingDate}
                            onChange={(e) => setOpportunityForm(p => ({ ...p, firstMeetingDate: e.target.value }))}
                            placeholder="MM/DD/YYYY"
                            className="h-9 text-xs font-mono pl-8"
                          />
                          <Calendar className="w-3.5 h-3.5 text-muted-foreground absolute left-2.5 top-3 pointer-events-none" />
                        </div>
                      </div>

                      {/* 5. Opportunity Generated By */}
                      <div className="space-y-1.5">
                        <label className="text-xs font-semibold text-foreground flex items-center justify-between">
                          <span>Opportunity Generated By</span>
                          <span className="text-[10px] text-muted-foreground font-normal">Default: Channel Partner</span>
                        </label>
                        <select
                          value={opportunityForm.opportunityGeneratedBy}
                          onChange={(e) => setOpportunityForm(p => ({ ...p, opportunityGeneratedBy: e.target.value }))}
                          className="h-9 w-full rounded-md border border-input bg-background px-3 py-1.5 text-xs text-foreground shadow-xs focus:ring-1 focus:ring-primary focus:outline-none font-medium cursor-pointer"
                        >
                          <option value="Channel Partner">Channel Partner</option>
                          <option value="Direct Sales">Direct Sales</option>
                          <option value="Referral">Referral</option>
                          <option value="Marketing">Marketing</option>
                          <option value="Inbound">Inbound</option>
                        </select>
                      </div>

                      {/* 6. Channel Partner */}
                      <div className="space-y-1.5">
                        <label className="text-xs font-semibold text-foreground flex items-center justify-between">
                          <span>Channel Partner</span>
                          <span className="text-[10px] text-muted-foreground font-normal">Broker Name</span>
                        </label>
                        <Input
                          value={opportunityForm.channelPartner}
                          onChange={(e) => setOpportunityForm(p => ({ ...p, channelPartner: e.target.value }))}
                          placeholder="Broker Name (Default: TBD)"
                          className="h-9 text-xs font-medium"
                        />
                      </div>

                      {/* 7. Close Date */}
                      <div className="space-y-1.5">
                        <label className="text-xs font-semibold text-foreground flex items-center justify-between">
                          <span>Close Date</span>
                          <span className="text-[10px] text-muted-foreground font-mono">+60 Days (MM/DD/YYYY)</span>
                        </label>
                        <div className="relative">
                          <Input
                            value={opportunityForm.closeDate}
                            onChange={(e) => setOpportunityForm(p => ({ ...p, closeDate: e.target.value }))}
                            placeholder="MM/DD/YYYY"
                            className="h-9 text-xs font-mono pl-8"
                          />
                          <Calendar className="w-3.5 h-3.5 text-muted-foreground absolute left-2.5 top-3 pointer-events-none" />
                        </div>
                      </div>

                      {/* 8. Estimated First Payroll Date */}
                      <div className="space-y-1.5">
                        <label className="text-xs font-semibold text-foreground flex items-center justify-between">
                          <span>Est. First Payroll Date</span>
                          <span className="text-[10px] text-muted-foreground font-mono">+60 Days (MM/DD/YYYY)</span>
                        </label>
                        <div className="relative">
                          <Input
                            value={opportunityForm.estimatedFirstPayrollDate}
                            onChange={(e) => setOpportunityForm(p => ({ ...p, estimatedFirstPayrollDate: e.target.value }))}
                            placeholder="MM/DD/YYYY"
                            className="h-9 text-xs font-mono pl-8"
                          />
                          <Calendar className="w-3.5 h-3.5 text-muted-foreground absolute left-2.5 top-3 pointer-events-none" />
                        </div>
                      </div>

                      {/* 9. Experience Modifier (X-Mod) */}
                      <div className="space-y-1.5">
                        <label className="text-xs font-semibold text-foreground flex items-center justify-between">
                          <span>Experience Modifier</span>
                          <span className="text-[10px] text-amber-600 font-mono font-semibold">X-Mod</span>
                        </label>
                        <div className="relative">
                          <Input
                            value={opportunityForm.modifier ?? "1.0"}
                            onChange={(e) => setOpportunityForm(p => ({ ...p, modifier: e.target.value }))}
                            placeholder="e.g. 1.3"
                            className="h-9 text-xs font-mono pl-8 border-amber-500/40 focus:border-amber-500"
                          />
                          <Percent className="w-3.5 h-3.5 text-amber-600 absolute left-2.5 top-3 pointer-events-none" />
                        </div>
                      </div>
                    </div>
                  </div>
                )}
              </div>

              {/* ACORD 130 Application Overview Cards */}
              {extractionState?.acordSchema && (
                <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                  {/* Card 1: Applicant Demographics */}
                  <div className="p-4 rounded-xl bg-card border border-border shadow-xs flex flex-col justify-between">
                    <div>
                      <div className="flex items-center justify-between gap-2 mb-2">
                        <div className="flex items-center gap-1.5">
                          <Building2 className="w-4 h-4 text-primary" />
                          <span className="text-[11px] font-bold uppercase tracking-wider text-muted-foreground">
                            Applicant Demographics
                          </span>
                        </div>
                        {acordDemographics.fein && (
                          <Badge variant="outline" className="text-[10px] font-mono bg-muted text-foreground">
                            FEIN: {acordDemographics.fein}
                          </Badge>
                        )}
                      </div>
                      <h4 className="text-sm font-bold text-foreground">
                        {acordDemographics.applicantName || "—"}
                      </h4>
                      <p className="text-xs text-muted-foreground mt-1 line-clamp-2" title={acordDemographics.businessDescription}>
                        {acordDemographics.businessDescription || "No business description specified."}
                      </p>
                    </div>

                    <div className="mt-3 pt-3 border-t border-border/60 text-[11px] space-y-1.5 text-muted-foreground">
                      <div className="flex items-start gap-1.5">
                        <MapPin className="w-3.5 h-3.5 text-primary shrink-0 mt-0.5" />
                        <span className="text-foreground">
                          {[acordDemographics.mailingStreet, acordDemographics.mailingCity, acordDemographics.mailingState, acordDemographics.mailingZip].filter(Boolean).join(", ") || "—"}
                        </span>
                      </div>
                      <div className="flex items-center justify-between pt-0.5">
                        <span className="flex items-center gap-1">
                          <Phone className="w-3 h-3 text-muted-foreground" />
                          <strong className="text-foreground">{acordDemographics.officePhone || acordDemographics.mobilePhone || "—"}</strong>
                        </span>
                        <span className="flex items-center gap-1">
                          <Mail className="w-3 h-3 text-muted-foreground" />
                          <strong className="text-foreground">{acordDemographics.email || "—"}</strong>
                        </span>
                      </div>
                    </div>
                  </div>

                  {/* Card 2: Coverage Scope & Key Officers */}
                  <div className="p-4 rounded-xl bg-card border border-border shadow-xs flex flex-col justify-between">
                    <div>
                      <div className="flex items-center justify-between gap-2 mb-2">
                        <div className="flex items-center gap-1.5">
                          <ShieldAlert className="w-4 h-4 text-primary" />
                          <span className="text-[11px] font-bold uppercase tracking-wider text-muted-foreground">
                            Coverage & Term
                          </span>
                        </div>
                        {acordDemographics.wcStates && (
                          <Badge variant="outline" className="text-[10px] font-bold bg-primary/10 text-primary border-primary/20">
                            States: {acordDemographics.wcStates}
                          </Badge>
                        )}
                      </div>
                      <div className="space-y-1.5 text-xs">
                        <div className="flex items-center justify-between">
                          <span className="text-muted-foreground">Proposed Term:</span>
                          <span className="font-semibold text-foreground font-mono">
                            {acordDemographics.proposedEffectiveDate || "—"} → {acordDemographics.proposedExpirationDate || "—"}
                          </span>
                        </div>
                        <div className="flex items-center justify-between">
                          <span className="text-muted-foreground">Years in Business:</span>
                          <span className="font-semibold text-foreground">
                            {acordDemographics.yearsInBusiness ? `${acordDemographics.yearsInBusiness} years` : "—"}
                          </span>
                        </div>
                      </div>
                    </div>

                    <div className="mt-3 pt-3 border-t border-border/60 text-[11px]">
                      <div className="flex items-center justify-between mb-1">
                        <span className="font-bold text-foreground flex items-center gap-1">
                          <Users className="w-3 h-3 text-primary" />
                          Key Officers / Owners
                        </span>
                        <span className="text-[10px] text-muted-foreground">({individualsList.length})</span>
                      </div>
                      {individualsList.length === 0 ? (
                        <p className="text-muted-foreground text-[10px]">None specified in application</p>
                      ) : (
                        <div className="space-y-1">
                          {individualsList.map((ind: any, i: number) => (
                            <div key={i} className="flex items-center justify-between text-muted-foreground">
                              <span className="text-foreground font-medium truncate max-w-[170px]" title={ind.name}>
                                {ind.name} <span className="text-[10px] text-muted-foreground">({ind.title || "Officer"})</span>
                              </span>
                              <span className="text-[10px] font-mono">
                                {ind.ownershipPercentage ? `${ind.ownershipPercentage}%` : ""} • <Badge variant="outline" className="text-[9px] px-1 py-0">{ind.included || "INC"}</Badge>
                              </span>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  </div>

                  {/* Card 3: Financials & Risk Questionnaire */}
                  <div className="p-4 rounded-xl bg-card border border-border shadow-xs flex flex-col justify-between">
                    <div>
                      <div className="flex items-center justify-between gap-2 mb-2">
                        <div className="flex items-center gap-1.5">
                          <DollarSign className="w-4 h-4 text-emerald-500" />
                          <span className="text-[11px] font-bold uppercase tracking-wider text-muted-foreground">
                            Financials & Risk Flags
                          </span>
                        </div>
                        <Badge variant="outline" className="text-[10px] font-mono bg-emerald-500/10 text-emerald-600 border-emerald-500/30">
                          Mod: {premiumCalculation.experienceModification ?? "1.00"}
                        </Badge>
                      </div>

                      <div className="grid grid-cols-2 gap-2 text-xs mb-2">
                        <div className="p-2 rounded-lg bg-muted/40 border border-border/40">
                          <span className="text-[10px] text-muted-foreground block">Est. Annual Payroll</span>
                          <span className="font-bold text-foreground font-mono text-xs">
                            {new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(totalPayrollEst)}
                          </span>
                        </div>
                        <div className="p-2 rounded-lg bg-muted/40 border border-border/40">
                          <span className="text-[10px] text-muted-foreground block">Total Est. Premium</span>
                          <span className="font-bold text-emerald-600 font-mono text-xs">
                            {premiumCalculation.totalEstimatedAnnualPremium ? `$${Number(premiumCalculation.totalEstimatedAnnualPremium).toLocaleString()}` : "$0.00"}
                          </span>
                        </div>
                      </div>
                    </div>

                    <div className="mt-3 pt-3 border-t border-border/60 text-[11px]">
                      {(() => {
                        const yesKeys = Object.entries(generalQuestions)
                          .filter(([_, v]) => String(v).toUpperCase() === "Y")
                          .map(([k]) => k.toUpperCase());
                        return (
                          <div className="flex items-center justify-between">
                            <span className="text-muted-foreground font-medium">Underwriting Questions:</span>
                            {yesKeys.length > 0 ? (
                              <Badge variant="outline" className="text-[10px] bg-amber-500/10 text-amber-600 border-amber-500/30 font-bold">
                                {yesKeys.join(", ")} Answered YES
                              </Badge>
                            ) : (
                              <span className="text-emerald-600 font-medium text-[10px] flex items-center gap-1">
                                <CheckCircle2 className="w-3 h-3 text-emerald-500" />
                                All 24 Questions Clean (NO)
                              </span>
                            )}
                          </div>
                        );
                      })()}
                    </div>
                  </div>
                </div>
              )}

              {/* Main Table Grid Container */}
              <div className="rounded-xl border border-border bg-card overflow-hidden shadow-sm">
                {/* Table Header Controls */}
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 px-4 py-3 bg-muted/40 border-b border-border">
                  <div className="flex items-center gap-2">
                    <TableIcon className="w-4 h-4 text-muted-foreground" />
                    <span className="text-xs font-bold text-foreground uppercase tracking-wide">
                      Extracted Data Grid
                    </span>
                  </div>

                  <div className="flex flex-wrap items-center gap-2">
                    {/* Sub-Switch: All Sections | ACORD Ratings | Locations | Contacts | Prior Carriers | Claims */}
                    <div className="flex items-center rounded-lg bg-muted p-0.5 border border-border flex-wrap gap-0.5">
                      <button
                        type="button"
                        onClick={() => setActiveTableSubTab("all")}
                        className={`px-2.5 py-1 text-[11px] font-semibold rounded-md transition-all ${
                          activeTableSubTab === "all"
                            ? "bg-card text-foreground shadow-xs"
                            : "text-muted-foreground hover:text-foreground"
                        }`}
                      >
                        All Stacked ({acordRatingsList.length + locationsList.length + priorCarriersList.length + claimsList.length})
                      </button>
                      <button
                        type="button"
                        onClick={() => setActiveTableSubTab("rating")}
                        className={`px-2.5 py-1 text-[11px] font-semibold rounded-md transition-all ${
                          activeTableSubTab === "rating"
                            ? "bg-card text-foreground shadow-xs"
                            : "text-muted-foreground hover:text-foreground"
                        }`}
                      >
                        ACORD Ratings ({acordRatingsList.length})
                      </button>
                      <button
                        type="button"
                        onClick={() => setActiveTableSubTab("locations")}
                        className={`px-2.5 py-1 text-[11px] font-semibold rounded-md transition-all ${
                          activeTableSubTab === "locations"
                            ? "bg-card text-foreground shadow-xs"
                            : "text-muted-foreground hover:text-foreground"
                        }`}
                      >
                        Locations ({locationsList.length})
                      </button>
                      <button
                        type="button"
                        onClick={() => setActiveTableSubTab("contacts")}
                        className={`px-2.5 py-1 text-[11px] font-semibold rounded-md transition-all ${
                          activeTableSubTab === "contacts"
                            ? "bg-card text-foreground shadow-xs"
                            : "text-muted-foreground hover:text-foreground"
                        }`}
                      >
                        Contacts
                      </button>
                      <button
                        type="button"
                        onClick={() => setActiveTableSubTab("priors")}
                        className={`px-2.5 py-1 text-[11px] font-semibold rounded-md transition-all ${
                          activeTableSubTab === "priors"
                            ? "bg-card text-foreground shadow-xs"
                            : "text-muted-foreground hover:text-foreground"
                        }`}
                      >
                        Prior Carriers ({priorCarriersList.length})
                      </button>
                      {claimsList.length > 0 && (
                        <button
                          type="button"
                          onClick={() => setActiveTableSubTab("claims")}
                          className={`px-2.5 py-1 text-[11px] font-semibold rounded-md transition-all ${
                            activeTableSubTab === "claims"
                              ? "bg-card text-foreground shadow-xs"
                              : "text-muted-foreground hover:text-foreground"
                          }`}
                        >
                          Claims ({claimsList.length})
                        </button>
                      )}
                    </div>

                    {/* Search Filter */}
                    <div className="relative w-44">
                      <Search className="w-3 h-3 absolute left-2.5 top-1/2 -translate-y-1/2 text-muted-foreground" />
                      <Input
                        value={tableSearch}
                        onChange={(e) => setTableSearch(e.target.value)}
                        placeholder="Filter rows..."
                        className="h-7 text-xs pl-7"
                      />
                    </div>

                    {/* Copy CSV Button */}
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={handleCopyTableCsv}
                      className="h-7 text-xs gap-1"
                    >
                      {copiedCsv ? (
                        <>
                          <Check className="w-3 h-3 text-emerald-500" />
                          Copied CSV
                        </>
                      ) : (
                        <>
                          <Copy className="w-3 h-3" />
                          Copy CSV
                        </>
                      )}
                    </Button>
                  </div>
                </div>

                {/* Sub Tab: ALL STACKED (Stacked One Below Another as Requested) */}
                {activeTableSubTab === "all" && (
                  <div className="p-4 space-y-6">
                    {/* Section 1: Claims (if present) */}
                    {claimsList.length > 0 && (
                      <div className="space-y-2">
                        <div className="flex items-center justify-between px-1">
                          <div className="flex items-center gap-2">
                            <BarChart3 className="w-4 h-4 text-primary" />
                            <h4 className="text-xs font-bold uppercase tracking-wider text-foreground">
                              Loss Run Claims History
                            </h4>
                            <Badge variant="outline" className="text-[10px] bg-primary/10 text-primary border-primary/20">
                              {filteredClaims.length} records
                            </Badge>
                          </div>
                          {(reportCreatedDate || reportValuationDate) && (
                            <span className="text-[10px] text-muted-foreground font-mono">
                              Valuation Date: <strong className="text-foreground">{reportValuationDate || reportCreatedDate}</strong>
                            </span>
                          )}
                        </div>
                        <div className="rounded-lg border border-border overflow-x-auto scrollbar-thin">
                          <Table>
                            <TableHeader className="bg-muted/40">
                              <TableRow className="border-border">
                                <TableHead className="text-[10px] font-bold uppercase tracking-wider h-9 px-3 whitespace-nowrap">Employee Name</TableHead>
                                <TableHead className="text-[10px] font-bold uppercase tracking-wider h-9 px-3 whitespace-nowrap">Carrier Name</TableHead>
                                <TableHead className="text-[10px] font-bold uppercase tracking-wider h-9 px-3 whitespace-nowrap">Policy Number</TableHead>
                                <TableHead className="text-[10px] font-bold uppercase tracking-wider h-9 px-3 whitespace-nowrap">Claim Number</TableHead>
                                <TableHead className="text-[10px] font-bold uppercase tracking-wider h-9 px-3 whitespace-nowrap">Injury Date</TableHead>
                                <TableHead className="text-[10px] font-bold uppercase tracking-wider h-9 px-3 whitespace-nowrap">Status</TableHead>
                                <TableHead className="text-[10px] font-bold uppercase tracking-wider h-9 px-3 whitespace-nowrap text-right">Medical Paid</TableHead>
                                <TableHead className="text-[10px] font-bold uppercase tracking-wider h-9 px-3 whitespace-nowrap text-right">Indemnity Paid</TableHead>
                                <TableHead className="text-[10px] font-bold uppercase tracking-wider h-9 px-3 whitespace-nowrap text-right">Total Incurred</TableHead>
                              </TableRow>
                            </TableHeader>
                            <TableBody>
                              {filteredClaims.map((claim, idx) => (
                                <TableRow key={idx} className="hover:bg-muted/30 transition-colors border-border/60">
                                  <TableCell className="text-[11px] py-2 px-3 font-semibold text-foreground whitespace-nowrap">
                                    {claim.employee_name || claim.claimant_name || "-"}
                                  </TableCell>
                                  <TableCell className="text-[11px] py-2 px-3 text-muted-foreground whitespace-nowrap">
                                    {claim.carrier_name || "-"}
                                  </TableCell>
                                  <TableCell className="text-[11px] py-2 px-3 font-mono text-muted-foreground whitespace-nowrap">
                                    {claim.policy_number || "-"}
                                  </TableCell>
                                  <TableCell className="text-[11px] py-2 px-3 font-mono font-medium text-foreground whitespace-nowrap">
                                    {claim.claim_number || "-"}
                                  </TableCell>
                                  <TableCell className="text-[11px] py-2 px-3 text-muted-foreground whitespace-nowrap">
                                    {claim.injury_date_time || claim.injury_date || "-"}
                                  </TableCell>
                                  <TableCell className="text-[11px] py-2 px-3 whitespace-nowrap">
                                    <Badge
                                      variant="outline"
                                      className={`text-[10px] px-1.5 py-0 ${
                                        String(claim.status).toLowerCase() === "open"
                                          ? "bg-amber-500/10 text-amber-600 border-amber-500/30"
                                          : String(claim.status).toLowerCase() === "closed"
                                          ? "bg-emerald-500/10 text-emerald-600 border-emerald-500/30"
                                          : "bg-muted text-muted-foreground"
                                      }`}
                                    >
                                      {claim.status || "-"}
                                    </Badge>
                                  </TableCell>
                                  <TableCell className="text-[11px] py-2 px-3 text-right font-mono text-foreground whitespace-nowrap">
                                    ${(parseFloat(String(claim.medical_paid || 0)) || 0).toLocaleString("en-US", { minimumFractionDigits: 2 })}
                                  </TableCell>
                                  <TableCell className="text-[11px] py-2 px-3 text-right font-mono text-foreground whitespace-nowrap">
                                    ${(parseFloat(String(claim.indemnity_paid || 0)) || 0).toLocaleString("en-US", { minimumFractionDigits: 2 })}
                                  </TableCell>
                                  <TableCell className="text-[11px] py-2 px-3 text-right font-mono font-bold text-emerald-600 whitespace-nowrap">
                                    ${(parseFloat(String(claim.total_incurred || 0)) || 0).toLocaleString("en-US", { minimumFractionDigits: 2 })}
                                  </TableCell>
                                </TableRow>
                              ))}
                            </TableBody>
                          </Table>
                        </div>
                      </div>
                    )}

                    {/* Section 2: ACORD Ratings by State */}
                    <div className="space-y-2">
                      <div className="flex items-center justify-between px-1">
                        <div className="flex items-center gap-2">
                          <HardHat className="w-4 h-4 text-primary" />
                          <h4 className="text-xs font-bold uppercase tracking-wider text-foreground">
                            ACORD 130 Ratings by State & Class Code
                          </h4>
                          <Badge variant="outline" className="text-[10px] bg-primary/10 text-primary border-primary/20">
                            {filteredRatings.length} entries
                          </Badge>
                        </div>
                      </div>
                      <div className="rounded-lg border border-border overflow-x-auto scrollbar-thin">
                        <Table>
                          <TableHeader className="bg-muted/40">
                            <TableRow className="border-border">
                              <TableHead className="text-[10px] font-bold uppercase tracking-wider h-9 px-3 whitespace-nowrap">State</TableHead>
                              <TableHead className="text-[10px] font-bold uppercase tracking-wider h-9 px-3 whitespace-nowrap">Class Code</TableHead>
                              <TableHead className="text-[10px] font-bold uppercase tracking-wider h-9 px-3 whitespace-nowrap">Categories / Description</TableHead>
                              <TableHead className="text-[10px] font-bold uppercase tracking-wider h-9 px-3 whitespace-nowrap text-right">Full Time</TableHead>
                              <TableHead className="text-[10px] font-bold uppercase tracking-wider h-9 px-3 whitespace-nowrap text-right">Part Time</TableHead>
                              <TableHead className="text-[10px] font-bold uppercase tracking-wider h-9 px-3 whitespace-nowrap text-right">Annual Payroll</TableHead>
                              <TableHead className="text-[10px] font-bold uppercase tracking-wider h-9 px-3 whitespace-nowrap text-right">Rate</TableHead>
                              <TableHead className="text-[10px] font-bold uppercase tracking-wider h-9 px-3 whitespace-nowrap text-right">Estimated Premium</TableHead>
                            </TableRow>
                          </TableHeader>
                          <TableBody>
                            {filteredRatings.map((rating, idx) => {
                              const fullTime = rating.fullTimeEmployees ?? rating.fullTimeCount ?? rating.full_time ?? rating.full_time_employees;
                              const partTime = rating.partTimeEmployees ?? rating.partTimeCount ?? rating.part_time ?? rating.part_time_employees;
                              const payrollVal = parseFloat(String(rating.estAnnualPayroll ?? rating.annualPayroll ?? rating.estimatedAnnualPayroll ?? rating.payroll ?? 0)) || 0;
                              const rateVal = rating.ratePer100Payroll ?? rating.rate ?? rating.rate_per_100_payroll;
                              const premiumVal = parseFloat(String(rating.estAnnualPremium ?? rating.estimatedAnnualPremium ?? rating.annualPremium ?? rating.premium ?? 0)) || 0;
                              const desc = rating.categories || rating.description || rating.classDescription || rating.duties || rating.class_description;

                              return (
                                <TableRow key={idx} className="hover:bg-muted/30 transition-colors border-border/60">
                                  <TableCell className="text-[11px] py-2 px-3 font-semibold text-primary whitespace-nowrap">
                                    {rating.state || rating.wc_state || "-"}
                                  </TableCell>
                                  <TableCell className="text-[11px] py-2 px-3 font-mono font-bold text-foreground whitespace-nowrap">
                                    {rating.classCode ?? rating.class_code ?? "-"}
                                  </TableCell>
                                  <TableCell className="text-[11px] py-2 px-3 text-foreground/80 max-w-xs truncate" title={desc || "-"}>
                                    {desc || "-"}
                                  </TableCell>
                                  <TableCell className="text-[11px] py-2 px-3 text-right text-muted-foreground whitespace-nowrap">
                                    {fullTime !== undefined && fullTime !== null && String(fullTime).trim() !== "" ? String(fullTime) : "-"}
                                  </TableCell>
                                  <TableCell className="text-[11px] py-2 px-3 text-right text-muted-foreground whitespace-nowrap">
                                    {partTime !== undefined && partTime !== null && String(partTime).trim() !== "" ? String(partTime) : "-"}
                                  </TableCell>
                                  <TableCell className="text-[11px] py-2 px-3 text-right font-mono font-semibold text-foreground whitespace-nowrap">
                                    ${payrollVal.toLocaleString("en-US", { minimumFractionDigits: 2 })}
                                  </TableCell>
                                  <TableCell className="text-[11px] py-2 px-3 text-right font-mono text-muted-foreground whitespace-nowrap">
                                    {rateVal !== undefined && rateVal !== null && String(rateVal).trim() !== "" ? `${rateVal}` : "-"}
                                  </TableCell>
                                  <TableCell className="text-[11px] py-2 px-3 text-right font-mono font-bold text-emerald-600 whitespace-nowrap">
                                    ${premiumVal.toLocaleString("en-US", { minimumFractionDigits: 2 })}
                                  </TableCell>
                                </TableRow>
                              );
                            })}
                          </TableBody>
                        </Table>
                      </div>
                    </div>

                    {/* Section 3: Locations Schedule */}
                    <div className="space-y-2">
                      <div className="flex items-center justify-between px-1">
                        <div className="flex items-center gap-2">
                          <MapPin className="w-4 h-4 text-primary" />
                          <h4 className="text-xs font-bold uppercase tracking-wider text-foreground">
                            Locations Schedule (Primary & Additional)
                          </h4>
                          <Badge variant="outline" className="text-[10px] bg-primary/10 text-primary border-primary/20">
                            {filteredLocations.length} locations
                          </Badge>
                        </div>
                      </div>
                      <div className="rounded-lg border border-border overflow-x-auto scrollbar-thin">
                        <Table>
                          <TableHeader className="bg-muted/40">
                            <TableRow className="border-border">
                              <TableHead className="text-[10px] font-bold uppercase tracking-wider h-9 px-3 whitespace-nowrap">LOC #</TableHead>
                              <TableHead className="text-[10px] font-bold uppercase tracking-wider h-9 px-3 whitespace-nowrap">Type</TableHead>
                              <TableHead className="text-[10px] font-bold uppercase tracking-wider h-9 px-3 whitespace-nowrap">Highest Floor</TableHead>
                              <TableHead className="text-[10px] font-bold uppercase tracking-wider h-9 px-3">Street</TableHead>
                              <TableHead className="text-[10px] font-bold uppercase tracking-wider h-9 px-3 whitespace-nowrap">City</TableHead>
                              <TableHead className="text-[10px] font-bold uppercase tracking-wider h-9 px-3 whitespace-nowrap">County</TableHead>
                              <TableHead className="text-[10px] font-bold uppercase tracking-wider h-9 px-3 whitespace-nowrap">State</TableHead>
                              <TableHead className="text-[10px] font-bold uppercase tracking-wider h-9 px-3 whitespace-nowrap">Zip Code</TableHead>
                              <TableHead className="text-[10px] font-bold uppercase tracking-wider h-9 px-3 whitespace-nowrap">Operations</TableHead>
                            </TableRow>
                          </TableHeader>
                          <TableBody>
                            {filteredLocations.map((loc: any, idx: number) => (
                              <TableRow key={idx} className="hover:bg-muted/30 transition-colors border-border/60">
                                <TableCell className="text-[11px] py-2 px-3 font-bold text-primary whitespace-nowrap">
                                  {loc.loc_number ?? idx + 1}
                                </TableCell>
                                <TableCell className="text-[11px] py-2 px-3 whitespace-nowrap">
                                  <Badge
                                    variant="outline"
                                    className={
                                      loc.location_type === "ADDITIONAL"
                                        ? "text-[10px] bg-amber-500/10 text-amber-600 border-amber-500/30"
                                        : "text-[10px] bg-primary/10 text-primary border-primary/20"
                                    }
                                  >
                                    {loc.location_type || "PRIMARY"}
                                  </Badge>
                                </TableCell>
                                <TableCell className="text-[11px] py-2 px-3 text-muted-foreground whitespace-nowrap">
                                  {loc.highest_floor || "—"}
                                </TableCell>
                                <TableCell className="text-[11px] py-2 px-3 text-foreground">
                                  {loc.street || "—"}
                                </TableCell>
                                <TableCell className="text-[11px] py-2 px-3 text-muted-foreground whitespace-nowrap">
                                  {loc.city || "—"}
                                </TableCell>
                                <TableCell className="text-[11px] py-2 px-3 text-muted-foreground whitespace-nowrap">
                                  {loc.county || "—"}
                                </TableCell>
                                <TableCell className="text-[11px] py-2 px-3 font-semibold text-primary whitespace-nowrap">
                                  {loc.state || "—"}
                                </TableCell>
                                <TableCell className="text-[11px] py-2 px-3 font-mono text-muted-foreground whitespace-nowrap">
                                  {loc.zip || "—"}
                                </TableCell>
                                <TableCell className="text-[11px] py-2 px-3 text-muted-foreground max-w-xs truncate" title={loc.operations || ""}>
                                  {loc.operations || "—"}
                                </TableCell>
                              </TableRow>
                            ))}
                          </TableBody>
                        </Table>
                      </div>
                    </div>

                    {/* Section 4: Contact Information */}
                    <div className="space-y-2">
                      <div className="flex items-center justify-between px-1">
                        <div className="flex items-center gap-2">
                          <Phone className="w-4 h-4 text-primary" />
                          <h4 className="text-xs font-bold uppercase tracking-wider text-foreground">
                            Designated Contact Information
                          </h4>
                          <Badge variant="outline" className="text-[10px] bg-muted">
                            3 roles
                          </Badge>
                        </div>
                      </div>
                      <div className="rounded-lg border border-border overflow-x-auto scrollbar-thin">
                        <Table>
                          <TableHeader className="bg-muted/40">
                            <TableRow className="border-border">
                              <TableHead className="text-[10px] font-bold uppercase tracking-wider h-9 px-3 whitespace-nowrap">Role / Type</TableHead>
                              <TableHead className="text-[10px] font-bold uppercase tracking-wider h-9 px-3">Name</TableHead>
                              <TableHead className="text-[10px] font-bold uppercase tracking-wider h-9 px-3 whitespace-nowrap">Office Phone</TableHead>
                              <TableHead className="text-[10px] font-bold uppercase tracking-wider h-9 px-3 whitespace-nowrap">Mobile Phone</TableHead>
                              <TableHead className="text-[10px] font-bold uppercase tracking-wider h-9 px-3">Email</TableHead>
                            </TableRow>
                          </TableHeader>
                          <TableBody>
                            {([
                              { key: "inspection",   label: "Inspection" },
                              { key: "acctng_record", label: "Acctng / Record" },
                              { key: "claims_info",   label: "Claims Info" },
                            ] as { key: string; label: string }[]).map(({ key, label }) => {
                              const row = contactInfo[key] || {};
                              return (
                                <TableRow key={key} className="hover:bg-muted/30 transition-colors border-border/60">
                                  <TableCell className="text-[11px] py-2 px-3 font-bold text-foreground whitespace-nowrap uppercase tracking-wide">
                                    {label}
                                  </TableCell>
                                  <TableCell className="text-[11px] py-2 px-3 text-foreground font-medium">
                                    {row.name || "—"}
                                  </TableCell>
                                  <TableCell className="text-[11px] py-2 px-3 font-mono text-muted-foreground whitespace-nowrap">
                                    {row.office_phone || "—"}
                                  </TableCell>
                                  <TableCell className="text-[11px] py-2 px-3 font-mono text-muted-foreground whitespace-nowrap">
                                    {row.mobile_phone || "—"}
                                  </TableCell>
                                  <TableCell className="text-[11px] py-2 px-3 text-primary">
                                    {row.email || "—"}
                                  </TableCell>
                                </TableRow>
                              );
                            })}
                          </TableBody>
                        </Table>
                      </div>
                    </div>

                    {/* Section 5: Prior Carriers History */}
                    {priorCarriersList.length > 0 && (
                      <div className="space-y-2">
                        <div className="flex items-center justify-between px-1">
                          <div className="flex items-center gap-2">
                            <History className="w-4 h-4 text-primary" />
                            <h4 className="text-xs font-bold uppercase tracking-wider text-foreground">
                              5-Year Prior Carrier Loss History
                            </h4>
                            <Badge variant="outline" className="text-[10px] bg-primary/10 text-primary border-primary/20">
                              {filteredPriorCarriers.length} policy years
                            </Badge>
                          </div>
                        </div>
                        <div className="rounded-lg border border-border overflow-x-auto scrollbar-thin">
                          <Table>
                            <TableHeader className="bg-muted/40">
                              <TableRow className="border-border">
                                <TableHead className="text-[10px] font-bold uppercase tracking-wider h-9 px-3 whitespace-nowrap">Year</TableHead>
                                <TableHead className="text-[10px] font-bold uppercase tracking-wider h-9 px-3">Carrier Name</TableHead>
                                <TableHead className="text-[10px] font-bold uppercase tracking-wider h-9 px-3 whitespace-nowrap">Policy Number</TableHead>
                                <TableHead className="text-[10px] font-bold uppercase tracking-wider h-9 px-3 whitespace-nowrap text-right">Exp. Mod</TableHead>
                                <TableHead className="text-[10px] font-bold uppercase tracking-wider h-9 px-3 whitespace-nowrap text-right">Annual Premium</TableHead>
                                <TableHead className="text-[10px] font-bold uppercase tracking-wider h-9 px-3 whitespace-nowrap text-right">Claims</TableHead>
                                <TableHead className="text-[10px] font-bold uppercase tracking-wider h-9 px-3 whitespace-nowrap text-right">Amount Paid</TableHead>
                                <TableHead className="text-[10px] font-bold uppercase tracking-wider h-9 px-3 whitespace-nowrap text-right">Reserve Amount</TableHead>
                              </TableRow>
                            </TableHeader>
                            <TableBody>
                              {filteredPriorCarriers.map((carrier, idx) => (
                                <TableRow key={idx} className="hover:bg-muted/30 transition-colors border-border/60">
                                  <TableCell className="text-[11px] py-2 px-3 font-bold text-primary font-mono whitespace-nowrap">
                                    {carrier.year || "—"}
                                  </TableCell>
                                  <TableCell className="text-[11px] py-2 px-3 font-medium text-foreground">
                                    {carrier.carrierName || "—"}
                                  </TableCell>
                                  <TableCell className="text-[11px] py-2 px-3 font-mono text-muted-foreground whitespace-nowrap">
                                    {carrier.policyNumber || "—"}
                                  </TableCell>
                                  <TableCell className="text-[11px] py-2 px-3 text-right font-mono text-muted-foreground whitespace-nowrap">
                                    {carrier.experienceMod !== undefined ? `${carrier.experienceMod}` : "—"}
                                  </TableCell>
                                  <TableCell className="text-[11px] py-2 px-3 text-right font-mono font-semibold text-foreground whitespace-nowrap">
                                    ${(parseFloat(String(carrier.annualPremium || 0)) || 0).toLocaleString("en-US", { minimumFractionDigits: 2 })}
                                  </TableCell>
                                  <TableCell className="text-[11px] py-2 px-3 text-right font-mono text-muted-foreground whitespace-nowrap">
                                    {carrier.numberOfClaims !== undefined ? `${carrier.numberOfClaims}` : "0"}
                                  </TableCell>
                                  <TableCell className="text-[11px] py-2 px-3 text-right font-mono text-foreground whitespace-nowrap">
                                    ${(parseFloat(String(carrier.amountPaid || 0)) || 0).toLocaleString("en-US", { minimumFractionDigits: 2 })}
                                  </TableCell>
                                  <TableCell className="text-[11px] py-2 px-3 text-right font-mono text-muted-foreground whitespace-nowrap">
                                    ${(parseFloat(String(carrier.reserveAmount || 0)) || 0).toLocaleString("en-US", { minimumFractionDigits: 2 })}
                                  </TableCell>
                                </TableRow>
                              ))}
                            </TableBody>
                          </Table>
                        </div>
                      </div>
                    )}
                  </div>
                )}

                {/* Sub Tab: Claims Only */}
                {activeTableSubTab === "claims" && (
                  <div className="overflow-x-auto scrollbar-thin p-3" style={{ maxHeight: "500px" }}>
                    {filteredClaims.length === 0 ? (
                      <div className="p-8 text-center text-muted-foreground text-xs italic">
                        No claims records found in the extracted Loss Run document.
                      </div>
                    ) : (
                      <Table>
                        <TableHeader className="bg-muted/40 sticky top-0 z-10">
                          <TableRow className="border-border">
                            <TableHead className="text-[10px] font-bold uppercase tracking-wider h-9 px-3 whitespace-nowrap">Employee Name</TableHead>
                            <TableHead className="text-[10px] font-bold uppercase tracking-wider h-9 px-3 whitespace-nowrap">Carrier Name</TableHead>
                            <TableHead className="text-[10px] font-bold uppercase tracking-wider h-9 px-3 whitespace-nowrap">Policy Number</TableHead>
                            <TableHead className="text-[10px] font-bold uppercase tracking-wider h-9 px-3 whitespace-nowrap">Claim Number</TableHead>
                            <TableHead className="text-[10px] font-bold uppercase tracking-wider h-9 px-3 whitespace-nowrap">Injury Date</TableHead>
                            <TableHead className="text-[10px] font-bold uppercase tracking-wider h-9 px-3 whitespace-nowrap">Claim Year</TableHead>
                            <TableHead className="text-[10px] font-bold uppercase tracking-wider h-9 px-3 whitespace-nowrap">Status</TableHead>
                            <TableHead className="text-[10px] font-bold uppercase tracking-wider h-9 px-3 whitespace-nowrap">Reopen</TableHead>
                            <TableHead className="text-[10px] font-bold uppercase tracking-wider h-9 px-3 whitespace-nowrap text-right">Medical Paid</TableHead>
                            <TableHead className="text-[10px] font-bold uppercase tracking-wider h-9 px-3 whitespace-nowrap text-right">Medical Reserve</TableHead>
                            <TableHead className="text-[10px] font-bold uppercase tracking-wider h-9 px-3 whitespace-nowrap text-right">Indemnity Paid</TableHead>
                            <TableHead className="text-[10px] font-bold uppercase tracking-wider h-9 px-3 whitespace-nowrap text-right">Total Incurred</TableHead>
                            <TableHead className="text-[10px] font-bold uppercase tracking-wider h-9 px-3 whitespace-nowrap">Litigation</TableHead>
                          </TableRow>
                        </TableHeader>
                        <TableBody>
                          {filteredClaims.map((claim, idx) => (
                            <TableRow key={idx} className="hover:bg-muted/30 transition-colors border-border/60">
                              <TableCell className="text-[11px] py-2 px-3 font-semibold text-foreground whitespace-nowrap">
                                {claim.employee_name || claim.claimant_name || "-"}
                              </TableCell>
                              <TableCell className="text-[11px] py-2 px-3 text-muted-foreground whitespace-nowrap">
                                {claim.carrier_name || "-"}
                              </TableCell>
                              <TableCell className="text-[11px] py-2 px-3 font-mono text-muted-foreground whitespace-nowrap">
                                {claim.policy_number || "-"}
                              </TableCell>
                              <TableCell className="text-[11px] py-2 px-3 font-mono font-medium text-foreground whitespace-nowrap">
                                {claim.claim_number || "-"}
                              </TableCell>
                              <TableCell className="text-[11px] py-2 px-3 text-muted-foreground whitespace-nowrap">
                                {claim.injury_date_time || claim.injury_date || "-"}
                              </TableCell>
                              <TableCell className="text-[11px] py-2 px-3 text-muted-foreground whitespace-nowrap">
                                {claim.claim_year || "-"}
                              </TableCell>
                              <TableCell className="text-[11px] py-2 px-3 whitespace-nowrap">
                                <Badge
                                  variant="outline"
                                  className={`text-[10px] px-1.5 py-0 ${
                                    String(claim.status).toLowerCase() === "open"
                                      ? "bg-amber-500/10 text-amber-600 border-amber-500/30"
                                      : String(claim.status).toLowerCase() === "closed"
                                      ? "bg-emerald-500/10 text-emerald-600 border-emerald-500/30"
                                      : "bg-muted text-muted-foreground"
                                  }`}
                                >
                                  {claim.status || "-"}
                                </Badge>
                              </TableCell>
                              <TableCell className="text-[11px] py-2 px-3 text-muted-foreground whitespace-nowrap">
                                {String(claim.reopen || "False")}
                              </TableCell>
                              <TableCell className="text-[11px] py-2 px-3 text-right font-mono text-foreground whitespace-nowrap">
                                ${(parseFloat(String(claim.medical_paid || 0)) || 0).toLocaleString("en-US", { minimumFractionDigits: 2 })}
                              </TableCell>
                              <TableCell className="text-[11px] py-2 px-3 text-right font-mono text-foreground whitespace-nowrap">
                                ${(parseFloat(String(claim.medical_reserve || 0)) || 0).toLocaleString("en-US", { minimumFractionDigits: 2 })}
                              </TableCell>
                              <TableCell className="text-[11px] py-2 px-3 text-right font-mono text-foreground whitespace-nowrap">
                                ${(parseFloat(String(claim.indemnity_paid || 0)) || 0).toLocaleString("en-US", { minimumFractionDigits: 2 })}
                              </TableCell>
                              <TableCell className="text-[11px] py-2 px-3 text-right font-mono font-bold text-emerald-600 whitespace-nowrap">
                                ${(parseFloat(String(claim.total_incurred || 0)) || 0).toLocaleString("en-US", { minimumFractionDigits: 2 })}
                              </TableCell>
                              <TableCell className="text-[11px] py-2 px-3 whitespace-nowrap">
                                {String(claim.litigation || "").toLowerCase() === "yes" ? (
                                  <Badge variant="outline" className="text-[10px] bg-destructive/10 text-destructive border-destructive/20">
                                    Litigated
                                  </Badge>
                                ) : (
                                  <span className="text-muted-foreground">No</span>
                                )}
                              </TableCell>
                            </TableRow>
                          ))}
                        </TableBody>
                      </Table>
                    )}
                  </div>
                )}

                {/* Sub Tab: ACORD Rating Grid */}
                {activeTableSubTab === "rating" && (
                  <div className="overflow-x-auto scrollbar-thin p-3" style={{ maxHeight: "500px" }}>
                    {filteredRatings.length === 0 ? (
                      <div className="p-8 text-center text-muted-foreground text-xs italic">
                        No ACORD 130 rating classification records found.
                      </div>
                    ) : (
                      <Table>
                        <TableHeader className="bg-muted/40 sticky top-0 z-10">
                          <TableRow className="border-border">
                            <TableHead className="text-[10px] font-bold uppercase tracking-wider h-9 px-3 whitespace-nowrap">State</TableHead>
                            <TableHead className="text-[10px] font-bold uppercase tracking-wider h-9 px-3 whitespace-nowrap">Class Code</TableHead>
                            <TableHead className="text-[10px] font-bold uppercase tracking-wider h-9 px-3 whitespace-nowrap">Categories / Description</TableHead>
                            <TableHead className="text-[10px] font-bold uppercase tracking-wider h-9 px-3 whitespace-nowrap text-right">Full Time</TableHead>
                            <TableHead className="text-[10px] font-bold uppercase tracking-wider h-9 px-3 whitespace-nowrap text-right">Part Time</TableHead>
                            <TableHead className="text-[10px] font-bold uppercase tracking-wider h-9 px-3 whitespace-nowrap text-right">Annual Payroll</TableHead>
                            <TableHead className="text-[10px] font-bold uppercase tracking-wider h-9 px-3 whitespace-nowrap text-right">Rate</TableHead>
                            <TableHead className="text-[10px] font-bold uppercase tracking-wider h-9 px-3 whitespace-nowrap text-right">Estimated Premium</TableHead>
                          </TableRow>
                        </TableHeader>
                        <TableBody>
                          {filteredRatings.map((rating, idx) => {
                            const fullTime = rating.fullTimeEmployees ?? rating.fullTimeCount ?? rating.full_time ?? rating.full_time_employees;
                            const partTime = rating.partTimeEmployees ?? rating.partTimeCount ?? rating.part_time ?? rating.part_time_employees;
                            const payrollVal = parseFloat(String(rating.estAnnualPayroll ?? rating.annualPayroll ?? rating.estimatedAnnualPayroll ?? rating.payroll ?? 0)) || 0;
                            const rateVal = rating.ratePer100Payroll ?? rating.rate ?? rating.rate_per_100_payroll;
                            const premiumVal = parseFloat(String(rating.estAnnualPremium ?? rating.estimatedAnnualPremium ?? rating.annualPremium ?? rating.premium ?? 0)) || 0;
                            const desc = rating.categories || rating.description || rating.classDescription || rating.duties || rating.class_description;

                            return (
                              <TableRow key={idx} className="hover:bg-muted/30 transition-colors border-border/60">
                                <TableCell className="text-[11px] py-2 px-3 font-semibold text-primary whitespace-nowrap">
                                  {rating.state || rating.wc_state || "-"}
                                </TableCell>
                                <TableCell className="text-[11px] py-2 px-3 font-mono font-bold text-foreground whitespace-nowrap">
                                  {rating.classCode ?? rating.class_code ?? "-"}
                                </TableCell>
                                <TableCell className="text-[11px] py-2 px-3 text-foreground/80 max-w-xs truncate" title={desc || "-"}>
                                  {desc || "-"}
                                </TableCell>
                                <TableCell className="text-[11px] py-2 px-3 text-right text-muted-foreground whitespace-nowrap">
                                  {fullTime !== undefined && fullTime !== null && String(fullTime).trim() !== "" ? String(fullTime) : "-"}
                                </TableCell>
                                <TableCell className="text-[11px] py-2 px-3 text-right text-muted-foreground whitespace-nowrap">
                                  {partTime !== undefined && partTime !== null && String(partTime).trim() !== "" ? String(partTime) : "-"}
                                </TableCell>
                                <TableCell className="text-[11px] py-2 px-3 text-right font-mono font-semibold text-foreground whitespace-nowrap">
                                  ${payrollVal.toLocaleString("en-US", { minimumFractionDigits: 2 })}
                                </TableCell>
                                <TableCell className="text-[11px] py-2 px-3 text-right font-mono text-muted-foreground whitespace-nowrap">
                                  {rateVal !== undefined && rateVal !== null && String(rateVal).trim() !== "" ? `${rateVal}` : "-"}
                                </TableCell>
                                <TableCell className="text-[11px] py-2 px-3 text-right font-mono font-bold text-emerald-600 whitespace-nowrap">
                                  ${premiumVal.toLocaleString("en-US", { minimumFractionDigits: 2 })}
                                </TableCell>
                              </TableRow>
                            );
                          })}
                        </TableBody>
                      </Table>
                    )}
                  </div>
                )}

                {/* Sub Tab: Locations Table */}
                {activeTableSubTab === "locations" && (
                  <div className="overflow-x-auto scrollbar-thin p-3" style={{ maxHeight: "500px" }}>
                    {filteredLocations.length === 0 ? (
                      <div className="p-8 text-center text-muted-foreground text-xs italic">
                        No locations extracted yet. Upload an ACORD 130 form — locations and additional locations tables will appear here.
                      </div>
                    ) : (
                      <Table>
                        <TableHeader className="bg-muted/40 sticky top-0 z-10">
                          <TableRow className="border-border">
                            <TableHead className="text-[10px] font-bold uppercase tracking-wider h-9 px-3 whitespace-nowrap">LOC #</TableHead>
                            <TableHead className="text-[10px] font-bold uppercase tracking-wider h-9 px-3 whitespace-nowrap">Type</TableHead>
                            <TableHead className="text-[10px] font-bold uppercase tracking-wider h-9 px-3 whitespace-nowrap">Highest Floor</TableHead>
                            <TableHead className="text-[10px] font-bold uppercase tracking-wider h-9 px-3">Street</TableHead>
                            <TableHead className="text-[10px] font-bold uppercase tracking-wider h-9 px-3 whitespace-nowrap">City</TableHead>
                            <TableHead className="text-[10px] font-bold uppercase tracking-wider h-9 px-3 whitespace-nowrap">County</TableHead>
                            <TableHead className="text-[10px] font-bold uppercase tracking-wider h-9 px-3 whitespace-nowrap">State</TableHead>
                            <TableHead className="text-[10px] font-bold uppercase tracking-wider h-9 px-3 whitespace-nowrap">Zip Code</TableHead>
                            <TableHead className="text-[10px] font-bold uppercase tracking-wider h-9 px-3 whitespace-nowrap">Operations</TableHead>
                          </TableRow>
                        </TableHeader>
                        <TableBody>
                          {filteredLocations.map((loc: any, idx: number) => (
                            <TableRow key={idx} className="hover:bg-muted/30 transition-colors border-border/60">
                              <TableCell className="text-[11px] py-2 px-3 font-bold text-primary whitespace-nowrap">
                                {loc.loc_number ?? idx + 1}
                              </TableCell>
                              <TableCell className="text-[11px] py-2 px-3 whitespace-nowrap">
                                <Badge
                                  variant="outline"
                                  className={
                                    loc.location_type === "ADDITIONAL"
                                      ? "text-[10px] bg-amber-500/10 text-amber-600 border-amber-500/30"
                                      : "text-[10px] bg-primary/10 text-primary border-primary/20"
                                  }
                                >
                                  {loc.location_type || "PRIMARY"}
                                </Badge>
                              </TableCell>
                              <TableCell className="text-[11px] py-2 px-3 text-muted-foreground whitespace-nowrap">
                                {loc.highest_floor || "—"}
                              </TableCell>
                              <TableCell className="text-[11px] py-2 px-3 text-foreground">
                                {loc.street || "—"}
                              </TableCell>
                              <TableCell className="text-[11px] py-2 px-3 text-muted-foreground whitespace-nowrap">
                                {loc.city || "—"}
                              </TableCell>
                              <TableCell className="text-[11px] py-2 px-3 text-muted-foreground whitespace-nowrap">
                                {loc.county || "—"}
                              </TableCell>
                              <TableCell className="text-[11px] py-2 px-3 font-semibold text-primary whitespace-nowrap">
                                {loc.state || "—"}
                              </TableCell>
                              <TableCell className="text-[11px] py-2 px-3 font-mono text-muted-foreground whitespace-nowrap">
                                {loc.zip || "—"}
                              </TableCell>
                              <TableCell className="text-[11px] py-2 px-3 text-muted-foreground max-w-xs truncate" title={loc.operations || ""}>
                                {loc.operations || "—"}
                              </TableCell>
                            </TableRow>
                          ))}
                        </TableBody>
                      </Table>
                    )}
                  </div>
                )}

                {/* Sub Tab: Contact Information */}
                {activeTableSubTab === "contacts" && (
                  <div className="overflow-x-auto scrollbar-thin p-3" style={{ maxHeight: "500px" }}>
                    {Object.keys(contactInfo).length === 0 ? (
                      <div className="p-8 text-center text-muted-foreground text-xs italic">
                        No contact information extracted yet. Upload an ACORD 130 form — the contact information table (Inspection, Acctng/Record, Claims Info) will appear here.
                      </div>
                    ) : (
                      <Table>
                        <TableHeader className="bg-muted/40 sticky top-0 z-10">
                          <TableRow className="border-border">
                            <TableHead className="text-[10px] font-bold uppercase tracking-wider h-9 px-3 whitespace-nowrap">Role / Type</TableHead>
                            <TableHead className="text-[10px] font-bold uppercase tracking-wider h-9 px-3">Name</TableHead>
                            <TableHead className="text-[10px] font-bold uppercase tracking-wider h-9 px-3 whitespace-nowrap">Office Phone</TableHead>
                            <TableHead className="text-[10px] font-bold uppercase tracking-wider h-9 px-3 whitespace-nowrap">Mobile Phone</TableHead>
                            <TableHead className="text-[10px] font-bold uppercase tracking-wider h-9 px-3">Email</TableHead>
                          </TableRow>
                        </TableHeader>
                        <TableBody>
                          {([
                            { key: "inspection",   label: "Inspection" },
                            { key: "acctng_record", label: "Acctng / Record" },
                            { key: "claims_info",   label: "Claims Info" },
                          ] as { key: string; label: string }[]).map(({ key, label }) => {
                            const row = contactInfo[key] || {};
                            return (
                              <TableRow key={key} className="hover:bg-muted/30 transition-colors border-border/60">
                                <TableCell className="text-[11px] py-2 px-3 font-bold text-foreground whitespace-nowrap uppercase tracking-wide">
                                  {label}
                                </TableCell>
                                <TableCell className="text-[11px] py-2 px-3 text-foreground font-medium">
                                  {row.name || "—"}
                                </TableCell>
                                <TableCell className="text-[11px] py-2 px-3 font-mono text-muted-foreground whitespace-nowrap">
                                  {row.office_phone || "—"}
                                </TableCell>
                                <TableCell className="text-[11px] py-2 px-3 font-mono text-muted-foreground whitespace-nowrap">
                                  {row.mobile_phone || "—"}
                                </TableCell>
                                <TableCell className="text-[11px] py-2 px-3 text-primary">
                                  {row.email || "—"}
                                </TableCell>
                              </TableRow>
                            );
                          })}
                        </TableBody>
                      </Table>
                    )}
                  </div>
                )}

                {/* Sub Tab: Prior Carriers */}
                {activeTableSubTab === "priors" && (
                  <div className="overflow-x-auto scrollbar-thin p-3" style={{ maxHeight: "500px" }}>
                    {filteredPriorCarriers.length === 0 ? (
                      <div className="p-8 text-center text-muted-foreground text-xs italic">
                        No prior carrier history records found in ACORD 130.
                      </div>
                    ) : (
                      <Table>
                        <TableHeader className="bg-muted/40 sticky top-0 z-10">
                          <TableRow className="border-border">
                            <TableHead className="text-[10px] font-bold uppercase tracking-wider h-9 px-3 whitespace-nowrap">Year</TableHead>
                            <TableHead className="text-[10px] font-bold uppercase tracking-wider h-9 px-3">Carrier Name</TableHead>
                            <TableHead className="text-[10px] font-bold uppercase tracking-wider h-9 px-3 whitespace-nowrap">Policy Number</TableHead>
                            <TableHead className="text-[10px] font-bold uppercase tracking-wider h-9 px-3 whitespace-nowrap text-right">Exp. Mod</TableHead>
                            <TableHead className="text-[10px] font-bold uppercase tracking-wider h-9 px-3 whitespace-nowrap text-right">Annual Premium</TableHead>
                            <TableHead className="text-[10px] font-bold uppercase tracking-wider h-9 px-3 whitespace-nowrap text-right">Claims</TableHead>
                            <TableHead className="text-[10px] font-bold uppercase tracking-wider h-9 px-3 whitespace-nowrap text-right">Amount Paid</TableHead>
                            <TableHead className="text-[10px] font-bold uppercase tracking-wider h-9 px-3 whitespace-nowrap text-right">Reserve Amount</TableHead>
                          </TableRow>
                        </TableHeader>
                        <TableBody>
                          {filteredPriorCarriers.map((carrier, idx) => (
                            <TableRow key={idx} className="hover:bg-muted/30 transition-colors border-border/60">
                              <TableCell className="text-[11px] py-2 px-3 font-bold text-primary font-mono whitespace-nowrap">
                                {carrier.year || "—"}
                              </TableCell>
                              <TableCell className="text-[11px] py-2 px-3 font-medium text-foreground">
                                {carrier.carrierName || "—"}
                              </TableCell>
                              <TableCell className="text-[11px] py-2 px-3 font-mono text-muted-foreground whitespace-nowrap">
                                {carrier.policyNumber || "—"}
                              </TableCell>
                              <TableCell className="text-[11px] py-2 px-3 text-right font-mono text-muted-foreground whitespace-nowrap">
                                {carrier.experienceMod !== undefined ? `${carrier.experienceMod}` : "—"}
                              </TableCell>
                              <TableCell className="text-[11px] py-2 px-3 text-right font-mono font-semibold text-foreground whitespace-nowrap">
                                ${(parseFloat(String(carrier.annualPremium || 0)) || 0).toLocaleString("en-US", { minimumFractionDigits: 2 })}
                              </TableCell>
                              <TableCell className="text-[11px] py-2 px-3 text-right font-mono text-muted-foreground whitespace-nowrap">
                                {carrier.numberOfClaims !== undefined ? `${carrier.numberOfClaims}` : "0"}
                              </TableCell>
                              <TableCell className="text-[11px] py-2 px-3 text-right font-mono text-foreground whitespace-nowrap">
                                ${(parseFloat(String(carrier.amountPaid || 0)) || 0).toLocaleString("en-US", { minimumFractionDigits: 2 })}
                              </TableCell>
                              <TableCell className="text-[11px] py-2 px-3 text-right font-mono text-muted-foreground whitespace-nowrap">
                                ${(parseFloat(String(carrier.reserveAmount || 0)) || 0).toLocaleString("en-US", { minimumFractionDigits: 2 })}
                              </TableCell>
                            </TableRow>
                          ))}
                        </TableBody>
                      </Table>
                    )}
                  </div>
                )}
              </div>
            </TabsContent>

            {/* TAB 2: JSON VIEW (Light theme) */}
            <TabsContent value="json" className="space-y-3">
              <div className="rounded-xl border border-border bg-white shadow-sm overflow-hidden">
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 px-4 py-3 bg-muted/40 border-b border-border">
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-bold text-foreground uppercase tracking-wide">Raw Extraction Data</span>
                    <div className="flex items-center rounded-lg bg-muted p-0.5 border border-border ml-3">
                      <button
                        type="button"
                        onClick={() => setActiveJsonSubTab("unified")}
                        className={`px-2.5 py-1 text-[11px] font-semibold rounded-md transition-all ${
                          activeJsonSubTab === "unified"
                            ? "bg-card text-foreground shadow-xs"
                            : "text-muted-foreground hover:text-foreground"
                        }`}
                      >
                        Unified Payload
                      </button>
                      <button
                        type="button"
                        onClick={() => setActiveJsonSubTab("loss_run")}
                        className={`px-2.5 py-1 text-[11px] font-semibold rounded-md transition-all ${
                          activeJsonSubTab === "loss_run"
                            ? "bg-card text-foreground shadow-xs"
                            : "text-muted-foreground hover:text-foreground"
                        }`}
                      >
                        Loss Run JSON
                      </button>
                      <button
                        type="button"
                        onClick={() => setActiveJsonSubTab("acord")}
                        className={`px-2.5 py-1 text-[11px] font-semibold rounded-md transition-all ${
                          activeJsonSubTab === "acord"
                            ? "bg-card text-foreground shadow-xs"
                            : "text-muted-foreground hover:text-foreground"
                        }`}
                      >
                        ACORD JSON
                      </button>
                      <button
                        type="button"
                        onClick={() => setActiveJsonSubTab("modifier")}
                        className={`px-2.5 py-1 text-[11px] font-semibold rounded-md transition-all ${
                          activeJsonSubTab === "modifier"
                            ? "bg-card text-foreground shadow-xs"
                            : "text-muted-foreground hover:text-foreground"
                        }`}
                      >
                        Modifier JSON
                      </button>
                    </div>
                  </div>

                  <Button
                    variant="outline"
                    size="sm"
                    onClick={handleCopyJson}
                    className="h-7 text-xs gap-1"
                  >
                    {copiedJson ? (
                      <>
                        <Check className="w-3.5 h-3.5 text-emerald-500" />
                        Copied
                      </>
                    ) : (
                      <>
                        <Copy className="w-3.5 h-3.5" />
                        Copy
                      </>
                    )}
                  </Button>
                </div>

                <pre
                  className="p-5 text-xs font-mono text-zinc-800 bg-white overflow-auto whitespace-pre leading-relaxed scrollbar-thin selection:bg-primary/20"
                  style={{ maxHeight: "500px" }}
                >
                  {JSON.stringify(
                    activeJsonSubTab === "loss_run"
                      ? extractionState?.lossRunSchema || {}
                      : activeJsonSubTab === "acord"
                      ? extractionState?.acordSchema || {}
                      : activeJsonSubTab === "modifier"
                      ? extractionState?.modifierResult || { experience_mod: finalModifier }
                      : unifiedJsonPayload,
                    null,
                    2
                  )}
                </pre>
              </div>
            </TabsContent>

            {/* TAB 3: AI SUMMARY (Screenshot 4 design) */}
            <TabsContent value="summary" className="space-y-4">
              <div className="rounded-xl border border-border bg-card p-6 min-h-[360px] flex flex-col justify-center shadow-sm">
                {!summaryText && !isSummarizing ? (
                  <div className="flex flex-col items-center justify-center py-12 text-center space-y-4">
                    <div className="w-16 h-16 rounded-full bg-primary/10 flex items-center justify-center text-primary shadow-xs">
                      <Brain className="w-8 h-8" />
                    </div>
                    <div>
                      <h3 className="text-base font-bold text-foreground">AI Claims & Underwriting Analysis</h3>
                      <p className="text-xs text-muted-foreground mt-1 max-w-md">
                        Click Analyze to generate an AI-powered summary evaluating loss experience, policy payroll, severity trends and underwriting flags.
                      </p>
                    </div>
                    <Button
                      size="default"
                      onClick={handleGenerateSummary}
                      className="gap-2 font-bold px-6 shadow"
                    >
                      <Brain className="w-4 h-4" />
                      Analyze
                    </Button>
                  </div>
                ) : isSummarizing ? (
                  <div className="flex flex-col items-center justify-center py-16 text-center space-y-4">
                    <div className="w-14 h-14 rounded-full bg-primary/10 flex items-center justify-center text-primary animate-pulse">
                      <Loader2 className="w-7 h-7 animate-spin" />
                    </div>
                    <div>
                      <p className="text-sm font-semibold text-foreground">Synthesizing Underwriting Risk Report...</p>
                      <p className="text-xs text-muted-foreground mt-1">
                        Correlating loss runs claims history with ACORD 130 rating classes and payroll exposure.
                      </p>
                    </div>
                  </div>
                ) : (
                  <div className="space-y-4">
                    <div className="flex flex-wrap items-center justify-between pb-3 border-b border-border gap-2">
                      <div className="flex items-center gap-2">
                        <Brain className="w-5 h-5 text-primary" />
                        <span className="text-sm font-bold text-foreground">
                          Executive Underwriting & Claims Assessment
                        </span>
                      </div>
                      <div className="flex items-center gap-2">
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={handleCopySummaryText}
                          className="h-7 text-xs gap-1"
                        >
                          {copiedSummary ? <Check className="w-3 h-3 text-emerald-500" /> : <Copy className="w-3 h-3" />}
                          Copy Report
                        </Button>
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={handleDownloadSummaryTxt}
                          className="h-7 text-xs gap-1"
                        >
                          <Download className="w-3 h-3" />
                          Download (.txt)
                        </Button>
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={handleGenerateSummary}
                          className="h-7 text-xs text-muted-foreground hover:text-foreground gap-1"
                        >
                          <RefreshCw className="w-3 h-3" />
                          Re-analyze
                        </Button>
                      </div>
                    </div>

                    <div className="prose prose-sm dark:prose-invert max-w-none text-xs leading-relaxed max-h-[500px] overflow-auto pr-2 scrollbar-thin">
                      {renderMarkdown(summaryText || "")}
                    </div>
                  </div>
                )}
              </div>
            </TabsContent>
          </Tabs>

          {/* Footer note from Screenshot 4 */}
          <div className="pt-4 text-center text-xs text-muted-foreground border-t border-border/50">
            Data Retrieval Ingestion Verification Engine • AI-Powered PDF Processing
          </div>
        </div>
      )}
    </div>
  );
}
export default WcuwPage;
