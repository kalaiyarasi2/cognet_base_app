import { createFileRoute } from "@tanstack/react-router";
import { useState, useEffect } from "react";
import {
  Coins, Activity, RefreshCw, Loader2, Search, Cpu,
  DollarSign, Hash, Layers, FileText, Filter, ChevronDown, ChevronRight
} from "lucide-react";
import { PageHeader } from "@/components/PageHeader";
import { Panel, StatCard } from "@/components/Panel";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { Label } from "@/components/ui/label";
import { api, type TokenCallRecord, type TokenFileSummaryRecord } from "@/lib/api";
import { toast } from "sonner";

export const Route = createFileRoute("/token-utilization")({
  component: TokenUtilizationPage,
});

export function TokenUtilizationPage() {
  const [loading, setLoading] = useState(true);
  const [autoRefresh, setAutoRefresh] = useState(true);

  // Filters & View Mode
  const [selectedPoc, setSelectedPoc] = useState<string>("ALL");
  const [searchTerm, setSearchTerm] = useState<string>("");
  const [viewMode, setViewMode] = useState<"FILE_SUMMARY" | "ALL_CALLS">("FILE_SUMMARY");

  // Expanded file rows state
  const [expandedFiles, setExpandedFiles] = useState<Record<string, boolean>>({});

  // Data states
  const [grandTotals, setGrandTotals] = useState<any>({
    grand_tokens: 0,
    grand_cost: 0,
    grand_calls: 0,
    total_pocs: 0,
    total_files: 0,
  });
  const [pocRows, setPocRows] = useState<any[]>([]);
  const [recentCalls, setRecentCalls] = useState<TokenCallRecord[]>([]);
  const [fileSummaries, setFileSummaries] = useState<TokenFileSummaryRecord[]>([]);

  async function loadData() {
    setLoading(true);
    try {
      // 1. Fetch grand summary & per-POC breakdown
      const summaryRes = await api.getTokenUsage();
      if (summaryRes.status === "ok" && summaryRes.data) {
        const grand = summaryRes.data.grand_totals || {};
        setGrandTotals({
          grand_tokens: grand.grand_tokens || 0,
          grand_cost: grand.grand_cost || 0,
          grand_calls: grand.grand_calls || 0,
          total_pocs: grand.total_pocs || 0,
          total_files: grand.total_files || 0,
        });
        setPocRows(summaryRes.data.per_poc || []);
      }

      // 2. Fetch recent call records & grouped file summaries
      const callsRes = await api.getTokenUsage(undefined, undefined, 100);
      if (callsRes.status === "ok") {
        if (callsRes.recent_calls) setRecentCalls(callsRes.recent_calls);
        if (callsRes.file_summaries) setFileSummaries(callsRes.file_summaries);
      }
    } catch (e: any) {
      toast.error(e?.message || "Failed to load token usage statistics.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadData();
    if (!autoRefresh) return;
    const timer = setInterval(loadData, 10000);
    return () => clearInterval(timer);
  }, [autoRefresh]);

  function toggleExpandFile(fileKey: string) {
    setExpandedFiles((prev) => ({ ...prev, [fileKey]: !prev[fileKey] }));
  }

  // Helper to format POC name nicely
  function formatPocTag(raw: string) {
    if (!raw) return "SYSTEM";
    const tag = raw.toUpperCase();
    if (tag.startsWith("GPU-")) return tag.replace("GPU-", "GPU: ");
    return tag;
  }

  // Unique POC list for filter dropdown
  const uniquePocs = Array.from(new Set([
    ...pocRows.map((r) => r.poc_name),
    ...fileSummaries.map((f) => f.poc_name),
    ...recentCalls.map((c) => c.poc_name),
  ])).sort();

  // Filtered File Summaries (1 row per file process)
  const filteredFileSummaries = fileSummaries.filter((f) => {
    const matchPoc = selectedPoc === "ALL" || f.poc_name === selectedPoc;
    const matchSearch =
      !searchTerm ||
      (f.file_name && f.file_name.toLowerCase().includes(searchTerm.toLowerCase())) ||
      (f.poc_name && f.poc_name.toLowerCase().includes(searchTerm.toLowerCase())) ||
      (f.models && f.models.some((m) => m.toLowerCase().includes(searchTerm.toLowerCase())));
    return matchPoc && matchSearch;
  });

  // Filtered Individual Calls
  const filteredCalls = recentCalls.filter((c) => {
    const matchPoc = selectedPoc === "ALL" || c.poc_name === selectedPoc;
    const matchSearch =
      !searchTerm ||
      (c.file_name && c.file_name.toLowerCase().includes(searchTerm.toLowerCase())) ||
      (c.poc_name && c.poc_name.toLowerCase().includes(searchTerm.toLowerCase())) ||
      (c.step_name && c.step_name.toLowerCase().includes(searchTerm.toLowerCase())) ||
      (c.model && c.model.toLowerCase().includes(searchTerm.toLowerCase()));
    return matchPoc && matchSearch;
  });

  return (
    <div className="space-y-6 max-w-full">
      {/* Page Header */}
      <PageHeader
        title="Token Utilization & Cost Analytics"
        subtitle="Real-time monitoring of OpenAI token consumption and USD costs across all POC engines"
        icon={Coins}
        actions={
          <div className="flex items-center gap-4">
            <div className="flex items-center gap-2 bg-sidebar px-3 py-1.5 rounded-lg border border-border">
              <Switch
                id="auto-refresh-token"
                checked={autoRefresh}
                onCheckedChange={setAutoRefresh}
              />
              <Label htmlFor="auto-refresh-token" className="text-xs cursor-pointer select-none">
                Auto Refresh (10s)
              </Label>
            </div>

            <Button
              variant="outline"
              size="sm"
              onClick={loadData}
              disabled={loading}
              className="gap-2"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} />
              Refresh
            </Button>
          </div>
        }
      />

      {/* KPI Cards Grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard
          label="Total Estimated Cost"
          value={`$${(grandTotals.grand_cost || 0).toFixed(6)}`}
          hint={`${grandTotals.total_pocs || 0} active POC(s)`}
          icon={DollarSign}
          accent="success"
        />
        <StatCard
          label="Total Tokens Consumed"
          value={(grandTotals.grand_tokens || 0).toLocaleString()}
          hint="Prompt + Completion tokens"
          icon={Hash}
          accent="primary"
        />
        <StatCard
          label="Total Files Processed"
          value={(grandTotals.total_files || 0).toLocaleString()}
          hint="Unique documents handled"
          icon={FileText}
          accent="warning"
        />
        <StatCard
          label="Total LLM API Calls"
          value={(grandTotals.grand_calls || 0).toLocaleString()}
          hint="API requests executed"
          icon={Cpu}
          accent="primary"
        />
      </div>

      {/* Section 1: Per-POC Breakdown Summary */}
      <Panel
        title="POC Cost & Token Usage Breakdown"
        subtitle="Aggregated usage and estimated expenses grouped by individual POC engine"
        icon={Layers}
      >
        {pocRows.length === 0 ? (
          <div className="text-center py-8 text-muted-foreground text-sm">
            {loading ? "Loading usage metrics..." : "No token usage recorded yet across any POC."}
          </div>
        ) : (
          <div className="overflow-x-auto w-full">
            <table className="w-full text-left border-collapse text-xs">
              <thead>
                <tr className="border-b border-border bg-muted/40 text-muted-foreground font-semibold">
                  <th className="py-2.5 px-4">POC Name</th>
                  <th className="py-2.5 px-4 text-center">Processed Files</th>
                  <th className="py-2.5 px-4 text-center">LLM Calls</th>
                  <th className="py-2.5 px-4 text-right">Total Tokens</th>
                  <th className="py-2.5 px-4 text-right">Estimated Cost ($)</th>
                  <th className="py-2.5 px-4 text-center">Share of Total Cost</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {pocRows.map((row) => {
                  const sharePct = grandTotals.grand_cost > 0
                    ? ((row.total_cost_usd / grandTotals.grand_cost) * 100).toFixed(1)
                    : "0.0";

                  return (
                    <tr key={row.poc_name} className="hover:bg-muted/20 transition-colors">
                      <td className="py-3 px-4 font-semibold text-foreground flex items-center gap-2">
                        <span className="w-2 h-2 rounded-full bg-primary inline-block shrink-0" />
                        <span className="tracking-wider">{formatPocTag(row.poc_name)}</span>
                      </td>
                      <td className="py-3 px-4 text-center font-mono">{row.total_files || 0}</td>
                      <td className="py-3 px-4 text-center font-mono">{row.total_calls || 0}</td>
                      <td className="py-3 px-4 text-right font-mono font-medium">
                        {(row.total_tokens || 0).toLocaleString()}
                      </td>
                      <td className="py-3 px-4 text-right font-mono font-semibold text-emerald-600 dark:text-emerald-400">
                        ${(row.total_cost_usd || 0).toFixed(6)}
                      </td>
                      <td className="py-3 px-4 text-center">
                        <div className="flex items-center justify-center gap-2">
                          <div className="w-16 bg-muted rounded-full h-1.5 overflow-hidden">
                            <div
                              className="bg-primary h-full rounded-full"
                              style={{ width: `${Math.min(100, parseFloat(sharePct))}%` }}
                            />
                          </div>
                          <span className="text-[11px] font-mono text-muted-foreground w-10 text-right">
                            {sharePct}%
                          </span>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </Panel>

      {/* Section 2: Detailed File & Call Activity Logs */}
      <Panel
        title="LLM Processing Activity & Call Logs"
        subtitle="Grouped file summaries (1 row per file) and step-by-step transaction details"
        icon={Activity}
        actions={
          <div className="flex items-center gap-3">
            {/* View Mode Toggle */}
            <div className="flex items-center bg-muted/60 p-0.5 rounded-lg border border-border">
              <button
                onClick={() => setViewMode("FILE_SUMMARY")}
                className={`px-3 py-1 text-xs font-semibold rounded-md transition-colors ${
                  viewMode === "FILE_SUMMARY"
                    ? "bg-background text-foreground shadow-sm"
                    : "text-muted-foreground hover:text-foreground"
                }`}
              >
                📁 Grouped by File
              </button>
              <button
                onClick={() => setViewMode("ALL_CALLS")}
                className={`px-3 py-1 text-xs font-semibold rounded-md transition-colors ${
                  viewMode === "ALL_CALLS"
                    ? "bg-background text-foreground shadow-sm"
                    : "text-muted-foreground hover:text-foreground"
                }`}
              >
                📜 All Individual Calls
              </button>
            </div>

            {/* POC Filter */}
            <div className="flex items-center gap-1.5 bg-background border border-input rounded-md px-2.5 py-1">
              <Filter className="w-3.5 h-3.5 text-muted-foreground" />
              <select
                value={selectedPoc}
                onChange={(e) => setSelectedPoc(e.target.value)}
                className="bg-transparent text-xs font-medium focus:outline-none cursor-pointer"
              >
                <option value="ALL">All POCs</option>
                {uniquePocs.map((poc) => (
                  <option key={poc} value={poc}>
                    {formatPocTag(poc)}
                  </option>
                ))}
              </select>
            </div>

            {/* Search Input */}
            <div className="relative w-52">
              <Search className="w-3.5 h-3.5 absolute left-2.5 top-2.5 text-muted-foreground" />
              <Input
                placeholder="Filter files..."
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                className="pl-8 h-8 text-xs"
              />
            </div>
          </div>
        }
      >
        {/* MODE 1: Grouped 1-Row Per File View */}
        {viewMode === "FILE_SUMMARY" && (
          filteredFileSummaries.length === 0 ? (
            <div className="text-center py-12 text-muted-foreground text-sm">
              {loading ? (
                <div className="flex items-center justify-center gap-2">
                  <Loader2 className="w-4 h-4 animate-spin text-primary" />
                  <span>Loading file summaries...</span>
                </div>
              ) : (
                "No file summaries match the selected filter."
              )}
            </div>
          ) : (
            <div className="overflow-x-auto w-full">
              <table className="w-full text-left border-collapse text-xs">
                <thead>
                  <tr className="border-b border-border bg-muted/40 text-muted-foreground font-semibold">
                    <th className="w-10 py-3 px-3 text-center"></th>
                    <th className="py-3 px-3 min-w-[150px]">Last Updated (UTC)</th>
                    <th className="py-3 px-3 min-w-[140px]">POC Engine</th>
                    <th className="py-3 px-3 min-w-[240px]">File / Document Name</th>
                    <th className="py-3 px-3 text-center min-w-[100px]">LLM Calls</th>
                    <th className="py-3 px-3 text-center min-w-[140px]">Models Used</th>
                    <th className="py-3 px-3 text-right min-w-[160px]">Tokens (Output / Total)</th>
                    <th className="py-3 px-3 text-right min-w-[140px]">Total File Cost ($)</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {filteredFileSummaries.flatMap((fileItem) => {
                    const fileKey = `${fileItem.poc_name}__${fileItem.file_name}`;
                    const isExpanded = !!expandedFiles[fileKey];
                    const callList = fileItem.calls || [];

                    const rows = [
                      /* Main 1-Row File Summary */
                      <tr
                        key={fileKey}
                        onClick={() => toggleExpandFile(fileKey)}
                        className="hover:bg-muted/30 transition-colors cursor-pointer"
                      >
                        <td className="py-3 px-3 text-center text-muted-foreground">
                          {isExpanded ? (
                            <ChevronDown className="w-4 h-4 text-primary inline-block" />
                          ) : (
                            <ChevronRight className="w-4 h-4 text-muted-foreground inline-block" />
                          )}
                        </td>
                        <td className="py-3 px-3 font-mono text-[11px] text-muted-foreground whitespace-nowrap">
                          {fileItem.last_updated}
                        </td>
                        <td className="py-3 px-3">
                          <span className="px-2 py-0.5 rounded text-[10px] font-semibold bg-primary/10 text-primary tracking-wider whitespace-nowrap">
                            {formatPocTag(fileItem.poc_name)}
                          </span>
                        </td>
                        <td className="py-3 px-3 font-medium text-foreground max-w-[300px] truncate" title={fileItem.file_name}>
                          {fileItem.file_name || "N/A"}
                        </td>
                        <td className="py-3 px-3 text-center">
                          <span className="px-2 py-0.5 rounded-full text-[10px] font-semibold bg-blue-500/10 text-blue-600 dark:text-blue-400 whitespace-nowrap">
                            {fileItem.total_llm_calls || 1} call{fileItem.total_llm_calls > 1 ? "s" : ""}
                          </span>
                        </td>
                        <td className="py-3 px-3 text-center">
                          <div className="flex items-center justify-center gap-1 flex-wrap">
                            {(fileItem.models || ["gpt-4o"]).map((m) => (
                              <span key={m} className="px-1.5 py-0.5 rounded text-[9.5px] font-mono bg-muted text-muted-foreground border border-border">
                                {m}
                              </span>
                            ))}
                          </div>
                        </td>
                        <td className="py-3 px-3 text-right font-mono whitespace-nowrap">
                          <span className="text-muted-foreground">{(fileItem.total_completion_tokens || 0).toLocaleString()}</span>
                          <span className="text-muted-foreground mx-1">/</span>
                          <span className="font-semibold text-foreground">
                            {(fileItem.total_tokens || 0).toLocaleString()}
                          </span>
                        </td>
                        <td className="py-3 px-3 text-right font-mono font-bold text-emerald-600 dark:text-emerald-400 whitespace-nowrap">
                          ${(fileItem.total_cost_usd || 0).toFixed(6)}
                        </td>
                      </tr>
                    ];

                    /* Expanded Nested Step Calls Row */
                    if (isExpanded && callList.length > 0) {
                      rows.push(
                        <tr key={`${fileKey}-expanded`} className="bg-muted/20">
                          <td colSpan={8} className="p-3 pl-8 border-t border-b border-primary/20">
                            <div className="bg-background rounded-lg p-3.5 border border-border shadow-sm space-y-2">
                              <div className="text-[11px] font-semibold text-primary uppercase tracking-wider mb-2">
                                Step-by-Step Breakdown for "{fileItem.file_name}" ({callList.length} LLM Call{callList.length > 1 ? "s" : ""}):
                              </div>
                              <table className="w-full text-left text-[11px]">
                                <thead>
                                  <tr className="text-muted-foreground border-b border-border font-semibold bg-muted/30">
                                    <th className="py-2 px-3">Step Name / Operation</th>
                                    <th className="py-2 px-3">AI Model</th>
                                    <th className="py-2 px-3 text-right">Prompt Tokens</th>
                                    <th className="py-2 px-3 text-right">Completion Tokens</th>
                                    <th className="py-2 px-3 text-right">Total Tokens</th>
                                    <th className="py-2 px-3 text-right">Step Cost ($)</th>
                                  </tr>
                                </thead>
                                <tbody className="divide-y divide-border/50">
                                  {callList.map((call, idx) => (
                                    <tr key={call.id || idx} className="hover:bg-muted/40">
                                      <td className="py-2 px-3 font-medium text-foreground">
                                        {call.step_name || `Step ${idx + 1}`}
                                      </td>
                                      <td className="py-2 px-3 font-mono text-muted-foreground">
                                        {call.model}
                                      </td>
                                      <td className="py-2 px-3 text-right font-mono text-muted-foreground">
                                        {call.prompt_tokens?.toLocaleString()}
                                      </td>
                                      <td className="py-2 px-3 text-right font-mono text-muted-foreground">
                                        {call.completion_tokens?.toLocaleString()}
                                      </td>
                                      <td className="py-2 px-3 text-right font-mono font-medium text-foreground">
                                        {call.total_tokens?.toLocaleString()}
                                      </td>
                                      <td className="py-2 px-3 text-right font-mono font-semibold text-emerald-600 dark:text-emerald-400">
                                        ${(call.cost_usd || 0).toFixed(6)}
                                      </td>
                                    </tr>
                                  ))}
                                </tbody>
                              </table>
                            </div>
                          </td>
                        </tr>
                      );
                    }

                    return rows;
                  })}
                </tbody>
              </table>
            </div>
          )
        )}

        {/* MODE 2: All Individual Step Calls Table */}
        {viewMode === "ALL_CALLS" && (
          filteredCalls.length === 0 ? (
            <div className="text-center py-12 text-muted-foreground text-sm">
              {loading ? (
                <div className="flex items-center justify-center gap-2">
                  <Loader2 className="w-4 h-4 animate-spin text-primary" />
                  <span>Loading transaction logs...</span>
                </div>
              ) : (
                "No recent LLM transaction calls match the filter."
              )}
            </div>
          ) : (
            <div className="overflow-x-auto w-full">
              <table className="w-full text-left border-collapse text-xs">
                <thead>
                  <tr className="border-b border-border bg-muted/40 text-muted-foreground font-semibold">
                    <th className="py-3 px-3">Timestamp (UTC)</th>
                    <th className="py-3 px-3">POC Engine</th>
                    <th className="py-3 px-3">File / Document Name</th>
                    <th className="py-3 px-3">Step / Operation</th>
                    <th className="py-3 px-3 text-center">Model</th>
                    <th className="py-3 px-3 text-right">Tokens (Prompt / Output)</th>
                    <th className="py-3 px-3 text-right">Cost ($)</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {filteredCalls.map((call) => (
                    <tr key={call.id} className="hover:bg-muted/20 transition-colors">
                      <td className="py-3 px-3 font-mono text-[11px] text-muted-foreground whitespace-nowrap">
                        {call.timestamp}
                      </td>
                      <td className="py-3 px-3">
                        <span className="px-2 py-0.5 rounded text-[10px] font-semibold bg-primary/10 text-primary tracking-wider whitespace-nowrap">
                          {formatPocTag(call.poc_name)}
                        </span>
                      </td>
                      <td className="py-3 px-3 font-medium text-foreground max-w-[220px] truncate" title={call.file_name}>
                        {call.file_name || "N/A"}
                      </td>
                      <td className="py-3 px-3 text-muted-foreground max-w-[180px] truncate" title={call.step_name}>
                        {call.step_name || "llm_call"}
                      </td>
                      <td className="py-3 px-3 text-center">
                        <span className="px-2 py-0.5 rounded text-[10px] font-mono bg-muted text-muted-foreground border border-border">
                          {call.model || "gpt-4o"}
                        </span>
                      </td>
                      <td className="py-3 px-3 text-right font-mono whitespace-nowrap">
                        <span className="text-muted-foreground">{call.prompt_tokens?.toLocaleString() || 0}</span>
                        <span className="text-muted-foreground mx-1">/</span>
                        <span className="text-muted-foreground">{call.completion_tokens?.toLocaleString() || 0}</span>
                        <span className="font-semibold text-foreground ml-1.5">
                          ({(call.total_tokens || 0).toLocaleString()})
                        </span>
                      </td>
                      <td className="py-3 px-3 text-right font-mono font-semibold text-emerald-600 dark:text-emerald-400 whitespace-nowrap">
                        ${(call.cost_usd || 0).toFixed(6)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )
        )}
      </Panel>
    </div>
  );
}
