import { createFileRoute } from "@tanstack/react-router";
import { useState, useMemo, useEffect } from "react";
import { Terminal, RefreshCw, Download, Trash2, Search, Database, Layers, CheckCircle2, XCircle } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { PageHeader } from "@/components/PageHeader";
import { Panel } from "@/components/Panel";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useApp } from "@/lib/store";
import { api } from "@/lib/api";

export const Route = createFileRoute("/logs")({ component: LogsPage });

export function LogsPage() {
  const logs = useApp((s) => s.logs);
  const clear = useApp((s) => s.clearLogs);
  const [search, setSearch] = useState("");
  const [level, setLevel] = useState("");
  const [auto, setAuto] = useState(true);
  const [, force] = useState(0);

  const { data: dbLogsData, refetch: refetchDbLogs, isFetching } = useQuery({
    queryKey: ["universal-logs"],
    queryFn: () => api.getUniversalLogs(100),
    refetchInterval: auto ? 5000 : false,
  });

  useEffect(() => {
    if (!auto) return;
    const t = setInterval(() => force((n) => n + 1), 2000);
    return () => clearInterval(t);
  }, [auto]);

  const filtered = useMemo(
    () =>
      logs
        .filter((l) => !level || l.level === level)
        .filter(
          (l) =>
            !search ||
            l.message.toLowerCase().includes(search.toLowerCase()) ||
            l.source.includes(search)
        ),
    [logs, level, search]
  );

  const dbLogs = dbLogsData?.logs || [];
  const filteredDbLogs = useMemo(() => {
    if (!search) return dbLogs;
    const s = search.toLowerCase();
    return dbLogs.filter(
      (r) =>
        r.module?.toLowerCase().includes(s) ||
        r.action?.toLowerCase().includes(s) ||
        r.file_name?.toLowerCase().includes(s) ||
        r.details?.toLowerCase().includes(s) ||
        r.processed_by?.toLowerCase().includes(s)
    );
  }, [dbLogs, search]);

  function download() {
    const text = filtered
      .map(
        (l) =>
          `[${l.ts}] [${l.level}] ${l.source}: ${l.message}${
            l.meta ? ` ${JSON.stringify(l.meta)}` : ""
          }`
      )
      .join("\n");
    const blob = new Blob([text], { type: "text/plain" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = "logs.txt";
    a.click();
  }

  const levelColor: Record<string, string> = {
    INFO: "text-primary",
    WARN: "text-warning",
    ERROR: "text-destructive",
    DEBUG: "text-muted-foreground",
  };

  const moduleColor: Record<string, string> = {
    PARITY_SETUP: "bg-blue-500/15 text-blue-500 border-blue-500/30",
    RENEWAL_PROCESS: "bg-emerald-500/15 text-emerald-500 border-emerald-500/30",
    RESOURCING_EDGE: "bg-indigo-500/15 text-indigo-500 border-indigo-500/30",
    RPVE: "bg-amber-500/15 text-amber-500 border-amber-500/30",
    CONVERTER: "bg-purple-500/15 text-purple-500 border-purple-500/30",
    GMAIL: "bg-red-500/15 text-red-500 border-red-500/30",
    OUTLOOK: "bg-sky-500/15 text-sky-500 border-sky-500/30",
    DRIVE: "bg-teal-500/15 text-teal-500 border-teal-500/30",
  };

  return (
    <div className="space-y-6">
      <PageHeader
        icon={Terminal}
        title="Logs & Audit History"
        description="Universal activity logs across all 4 POC automation modules and system executions."
        actions={
          <>
            <div className="flex items-center gap-2 mr-2">
              <Switch checked={auto} onCheckedChange={setAuto} id="autorefresh" />
              <Label htmlFor="autorefresh" className="text-[11.5px]">
                Auto refresh
              </Label>
            </div>
            <Button size="sm" variant="outline" onClick={() => refetchDbLogs()} disabled={isFetching}>
              <RefreshCw className={`w-3.5 h-3.5 ${isFetching ? "animate-spin" : ""}`} /> Refresh DB
            </Button>
            <Button size="sm" variant="outline" onClick={download}>
              <Download className="w-3.5 h-3.5" /> Download
            </Button>
          </>
        }
      />

      <Tabs defaultValue="universal" className="w-full">
        <TabsList className="grid grid-cols-2 max-w-md mb-4">
          <TabsTrigger value="universal" className="text-xs gap-1.5">
            <Database className="w-3.5 h-3.5 text-primary" /> UNIVERSAL POC DB LOGS ({dbLogs.length})
          </TabsTrigger>
          <TabsTrigger value="live" className="text-xs gap-1.5">
            <Terminal className="w-3.5 h-3.5" /> LIVE SESSION LOGS ({filtered.length})
          </TabsTrigger>
        </TabsList>

        {/* Tab 1: Universal Database Logs */}
        <TabsContent value="universal">
          <Panel
            title="Universal POC Database Logs (converter.db)"
            description="Combined execution records from Parity Setup, Renewal Process, Resourcing Edge & RPVE"
            actions={
              <div className="relative">
                <Search className="w-3 h-3 absolute left-2 top-1/2 -translate-y-1/2 text-muted-foreground" />
                <Input
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  placeholder="Filter DB logs..."
                  className="h-7 pl-6 text-[12px] w-64"
                />
              </div>
            }
          >
            {filteredDbLogs.length === 0 ? (
              <div className="text-xs text-muted-foreground text-center py-8">
                No database logs recorded.
              </div>
            ) : (
              <div className="overflow-x-auto rounded-lg border">
                <table className="w-full text-xs text-left">
                  <thead className="border-b bg-muted/40 text-muted-foreground uppercase text-[10px]">
                    <tr>
                      <th className="py-2.5 px-3">#</th>
                      <th className="py-2.5 px-3">POC Module</th>
                      <th className="py-2.5 px-3">Action</th>
                      <th className="py-2.5 px-3">Processed By</th>
                      <th className="py-2.5 px-3">File Name</th>
                      <th className="py-2.5 px-3">Status</th>
                      <th className="py-2.5 px-3">Execution Details</th>
                      <th className="py-2.5 px-3">Date / Time</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y font-mono">
                    {filteredDbLogs.map((row) => (
                      <tr key={row.id} className="hover:bg-card/40 transition-colors">
                        <td className="py-2.5 px-3 text-muted-foreground">{row.id}</td>
                        <td className="py-2.5 px-3 font-semibold">
                          <Badge className={moduleColor[row.module] || "bg-muted text-muted-foreground"}>
                            {row.module}
                          </Badge>
                        </td>
                        <td className="py-2.5 px-3 font-medium">{row.action}</td>
                        <td className="py-2.5 px-3 font-medium">
                          <span className="px-2 py-0.5 rounded-full text-[10px] font-semibold bg-indigo-500/10 text-indigo-600 dark:text-indigo-400 border border-indigo-500/20">
                            {row.processed_by || "SYSTEM"}
                          </span>
                        </td>
                        <td className="py-2.5 px-3 max-w-[200px] truncate" title={row.file_name}>
                          {row.file_name || "—"}
                        </td>
                        <td className="py-2.5 px-3">
                          <span className="inline-flex items-center gap-1 text-emerald-500 font-semibold">
                            <CheckCircle2 className="w-3 h-3" /> {row.status}
                          </span>
                        </td>
                        <td className="py-2.5 px-3 text-muted-foreground max-w-[280px] truncate" title={row.details}>
                          {row.details || "—"}
                        </td>
                        <td className="py-2.5 px-3 text-muted-foreground whitespace-nowrap">
                          {row.created_date}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Panel>
        </TabsContent>

        {/* Tab 2: Live Session Terminal Logs */}
        <TabsContent value="live">
          <Panel
            title="Live System Terminal Logs"
            description={`${filtered.length} of ${logs.length} entries in current browser session`}
            actions={
              <div className="flex items-center gap-2">
                <div className="relative">
                  <Search className="w-3 h-3 absolute left-2 top-1/2 -translate-y-1/2 text-muted-foreground" />
                  <Input
                    value={search}
                    onChange={(e) => setSearch(e.target.value)}
                    placeholder="Search logs..."
                    className="h-7 pl-6 text-[12px] w-48"
                  />
                </div>
                <select
                  value={level}
                  onChange={(e) => setLevel(e.target.value)}
                  className="h-7 px-2 rounded-md border border-input bg-background text-[12px]"
                >
                  <option value="">All levels</option>
                  <option value="INFO">INFO</option>
                  <option value="WARN">WARN</option>
                  <option value="ERROR">ERROR</option>
                  <option value="DEBUG">DEBUG</option>
                </select>
                <Button size="sm" variant="outline" onClick={clear} className="text-destructive h-7 text-xs">
                  <Trash2 className="w-3 h-3 mr-1" /> Clear
                </Button>
              </div>
            }
          >
            {filtered.length === 0 ? (
              <div className="text-[12.5px] text-muted-foreground text-center py-8">
                No session log entries.
              </div>
            ) : (
              <div className="font-mono text-[11.5px] bg-muted/40 rounded-md p-3 max-h-[480px] overflow-auto space-y-0.5">
                {filtered.map((l, i) => (
                  <div key={i} className="leading-relaxed">
                    <span className="text-muted-foreground">[{l.ts}]</span>{" "}
                    <span className={`${levelColor[l.level]} font-semibold`}>[{l.level}]</span>{" "}
                    <span>{l.message}</span>
                    {l.meta && (
                      <span className="text-muted-foreground">
                        {" "}
                        - {typeof l.meta === "string" ? l.meta : JSON.stringify(l.meta).slice(0, 120)}
                      </span>
                    )}
                  </div>
                ))}
              </div>
            )}
          </Panel>
        </TabsContent>
      </Tabs>
    </div>
  );
}
