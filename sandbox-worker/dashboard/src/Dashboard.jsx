import { useState, useEffect, useCallback } from "react";
import { Activity, Cpu, Server, Layers, Zap, Box, Monitor, GitBranch, CheckCircle, XCircle, Clock, RefreshCw, Wifi, WifiOff, Database, HardDrive, BarChart2, ChevronRight } from "lucide-react";

// ── Mock data (replace fetch URL with real /v1/dashboard in production) ──────
const generateMock = () => {
  const rand = (min, max) => Math.random() * (max - min) + min;
  const randInt = (min, max) => Math.floor(rand(min, max));
  const nodes = ["node-1", "node-2"].map((id, i) => ({
    id,
    address: `10.0.0.${10 + i}:50051`,
    status: Math.random() > 0.1 ? "active" : "offline",
    load: rand(0.05, 0.75),
    last_seen: new Date(Date.now() - randInt(1000, 8000)).toISOString(),
    registered_at: new Date(Date.now() - 3600000).toISOString(),
    queue_depth: randInt(0, 15),
    runtimes: {
      wasm:    { active: randInt(0, 500),  capacity: 10000, pool_size: 0  },
      microvm: { active: randInt(0, 40),   capacity: 100,   pool_size: 10 },
      gui:     { active: randInt(0, 5),    capacity: 20,    pool_size: 3  },
    },
  }));

  return {
    timestamp: new Date().toISOString(),
    cluster: {
      total_nodes: nodes.length,
      active_nodes: nodes.filter(n => n.status === "active").length,
      offline_nodes: nodes.filter(n => n.status === "offline").length,
      avg_load: nodes.reduce((s, n) => s + n.load, 0) / nodes.length,
    },
    nodes,
    pools: {
      wasm:    { tier: "wasm",    pool_size: 0,  active: randInt(0, 800), available: randInt(800, 10000), utilization: rand(0.01, 0.25) },
      microvm: { tier: "microvm", pool_size: 10, active: randInt(0, 80),  available: randInt(80, 200),   utilization: rand(0.05, 0.55) },
      gui:     { tier: "gui",     pool_size: 3,  active: randInt(0, 10),  available: randInt(10, 40),    utilization: rand(0.02, 0.40) },
    },
    queue: {
      global_depth: randInt(0, 30),
      per_node: { "node-1": randInt(0, 15), "node-2": randInt(0, 15) },
    },
    jobs: {
      total_completed: randInt(1200, 2000),
      total_failed:    randInt(10, 80),
      total_pending:   randInt(0, 25),
    },
    tools: [
      { name: "html_parse",        tier: "wasm",    timeout: 10,  entrypoint: "html_parse.wasm"       },
      { name: "json_parse",        tier: "wasm",    timeout: 10,  entrypoint: "json_parse.wasm"       },
      { name: "markdown_convert",  tier: "wasm",    timeout: 10,  entrypoint: "markdown_convert.wasm" },
      { name: "docx_generate",     tier: "wasm",    timeout: 30,  entrypoint: "docx_generate.wasm"    },
      { name: "python_run",        tier: "microvm", timeout: 60,  entrypoint: "main.py"               },
      { name: "bash_run",          tier: "microvm", timeout: 60,  entrypoint: "run.py"                },
      { name: "git_clone",         tier: "microvm", timeout: 120, entrypoint: "clone.py"              },
      { name: "file_ops",          tier: "microvm", timeout: 30,  entrypoint: "file_ops.py"           },
      { name: "browser_open",      tier: "gui",     timeout: 120, entrypoint: "browser.py"            },
      { name: "web_scrape",        tier: "gui",     timeout: 120, entrypoint: "scrape.py"             },
      { name: "excel_edit",        tier: "gui",     timeout: 60,  entrypoint: "excel.py"              },
      { name: "office_automation", tier: "gui",     timeout: 300, entrypoint: "office.py"             },
    ],
  };
};

// ── Helpers ───────────────────────────────────────────────────────────────────
const pct = (v) => `${(v * 100).toFixed(1)}%`;
const ago = (iso) => {
  const s = Math.floor((Date.now() - new Date(iso)) / 1000);
  if (s < 60) return `${s}s ago`;
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  return `${Math.floor(s / 3600)}h ago`;
};
const tierColor = {
  wasm:    { bg: "bg-violet-500/15", text: "text-violet-300", border: "border-violet-500/30", dot: "bg-violet-400" },
  microvm: { bg: "bg-blue-500/15",   text: "text-blue-300",   border: "border-blue-500/30",   dot: "bg-blue-400"   },
  gui:     { bg: "bg-emerald-500/15",text: "text-emerald-300",border: "border-emerald-500/30",dot: "bg-emerald-400"},
};
const tierIcon = { wasm: Zap, microvm: Cpu, gui: Monitor };

const loadColor = (v) =>
  v < 0.4 ? "text-emerald-400" : v < 0.7 ? "text-amber-400" : "text-red-400";
const loadBarColor = (v) =>
  v < 0.4 ? "bg-emerald-500" : v < 0.7 ? "bg-amber-500" : "bg-red-500";

// ── Sub-components ────────────────────────────────────────────────────────────

function Badge({ tier }) {
  const c = tierColor[tier] || tierColor.wasm;
  const Icon = tierIcon[tier] || Zap;
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-xs font-medium border ${c.bg} ${c.text} ${c.border}`}>
      <Icon size={10} />{tier}
    </span>
  );
}

function Card({ children, className = "" }) {
  return (
    <div className={`bg-zinc-900 border border-zinc-800 rounded-xl p-5 ${className}`}>
      {children}
    </div>
  );
}

function StatCard({ icon: Icon, label, value, sub, color = "text-white" }) {
  return (
    <Card>
      <div className="flex items-start justify-between">
        <div>
          <p className="text-xs text-zinc-500 font-medium uppercase tracking-wider mb-1">{label}</p>
          <p className={`text-3xl font-bold ${color}`}>{value}</p>
          {sub && <p className="text-xs text-zinc-500 mt-1">{sub}</p>}
        </div>
        <div className="p-2 rounded-lg bg-zinc-800">
          <Icon size={18} className="text-zinc-400" />
        </div>
      </div>
    </Card>
  );
}

function LoadBar({ value, height = "h-1.5" }) {
  return (
    <div className={`w-full bg-zinc-800 rounded-full ${height}`}>
      <div
        className={`${height} rounded-full transition-all duration-700 ${loadBarColor(value)}`}
        style={{ width: pct(Math.min(value, 1)) }}
      />
    </div>
  );
}

function SectionHeader({ icon: Icon, title, count }) {
  return (
    <div className="flex items-center gap-2 mb-4">
      <Icon size={16} className="text-zinc-400" />
      <h2 className="text-sm font-semibold text-zinc-300 uppercase tracking-wider">{title}</h2>
      {count !== undefined && (
        <span className="ml-auto text-xs text-zinc-500 bg-zinc-800 px-2 py-0.5 rounded-full">{count}</span>
      )}
    </div>
  );
}

// ── Panels ────────────────────────────────────────────────────────────────────

function NodePanel({ node }) {
  const isActive = node.status === "active";
  return (
    <Card>
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <div className={`w-2 h-2 rounded-full ${isActive ? "bg-emerald-400 animate-pulse" : "bg-red-500"}`} />
          <span className="text-sm font-semibold text-white">{node.id}</span>
        </div>
        <div className="flex items-center gap-2">
          {isActive ? <Wifi size={14} className="text-emerald-400" /> : <WifiOff size={14} className="text-red-400" />}
          <span className={`text-xs font-medium ${isActive ? "text-emerald-400" : "text-red-400"}`}>
            {node.status}
          </span>
        </div>
      </div>

      <p className="text-xs text-zinc-500 font-mono mb-4">{node.address}</p>

      {/* Load */}
      <div className="mb-4">
        <div className="flex justify-between mb-1.5">
          <span className="text-xs text-zinc-500">Load</span>
          <span className={`text-xs font-medium ${loadColor(node.load)}`}>{pct(node.load)}</span>
        </div>
        <LoadBar value={node.load} height="h-2" />
      </div>

      {/* Runtime capacity */}
      <div className="space-y-2">
        {Object.entries(node.runtimes).map(([tier, rt]) => {
          const c = tierColor[tier];
          const util = rt.capacity > 0 ? rt.active / rt.capacity : 0;
          return (
            <div key={tier} className="flex items-center gap-2">
              <span className={`text-xs w-14 ${c.text}`}>{tier}</span>
              <div className="flex-1 bg-zinc-800 rounded-full h-1.5">
                <div className={`h-1.5 rounded-full ${c.dot}`} style={{ width: pct(Math.min(util, 1)) }} />
              </div>
              <span className="text-xs text-zinc-500 w-20 text-right">
                {rt.active.toLocaleString()}/{rt.capacity.toLocaleString()}
              </span>
            </div>
          );
        })}
      </div>

      <div className="flex justify-between mt-4 pt-3 border-t border-zinc-800">
        <span className="text-xs text-zinc-600">Queue</span>
        <span className="text-xs text-zinc-400 font-medium">{node.queue_depth} jobs</span>
        <span className="text-xs text-zinc-600">Last seen</span>
        <span className="text-xs text-zinc-400">{ago(node.last_seen)}</span>
      </div>
    </Card>
  );
}

function PoolPanel({ pool }) {
  const c = tierColor[pool.tier];
  const Icon = tierIcon[pool.tier] || Zap;
  return (
    <Card>
      <div className="flex items-center gap-2 mb-4">
        <div className={`p-1.5 rounded-lg ${c.bg} border ${c.border}`}>
          <Icon size={14} className={c.text} />
        </div>
        <span className={`text-sm font-semibold ${c.text} capitalize`}>{pool.tier}</span>
        <span className="ml-auto text-xs text-zinc-500">{pool.pool_size > 0 ? `pool: ${pool.pool_size}` : "stateless"}</span>
      </div>

      <div className="mb-3">
        <div className="flex justify-between text-xs mb-1.5">
          <span className="text-zinc-500">Utilization</span>
          <span className={loadColor(pool.utilization)}>{pct(pool.utilization)}</span>
        </div>
        <LoadBar value={pool.utilization} height="h-2" />
      </div>

      <div className="grid grid-cols-2 gap-2 mt-4">
        <div className={`rounded-lg p-3 ${c.bg} border ${c.border} text-center`}>
          <p className={`text-xl font-bold ${c.text}`}>{pool.active}</p>
          <p className="text-xs text-zinc-500 mt-0.5">active</p>
        </div>
        <div className="rounded-lg p-3 bg-zinc-800 border border-zinc-700 text-center">
          <p className="text-xl font-bold text-zinc-300">{pool.available}</p>
          <p className="text-xs text-zinc-500 mt-0.5">available</p>
        </div>
      </div>
    </Card>
  );
}

function ToolsTable({ tools }) {
  const [filter, setFilter] = useState("all");
  const tiers = ["all", "wasm", "microvm", "gui"];
  const filtered = filter === "all" ? tools : tools.filter(t => t.tier === filter);

  return (
    <Card>
      <SectionHeader icon={Box} title="Tools Registry" count={tools.length} />
      <div className="flex gap-1 mb-4">
        {tiers.map(t => (
          <button
            key={t}
            onClick={() => setFilter(t)}
            className={`px-3 py-1 rounded-lg text-xs font-medium transition-all ${
              filter === t
                ? "bg-zinc-700 text-white"
                : "text-zinc-500 hover:text-zinc-300"
            }`}
          >
            {t}
          </button>
        ))}
      </div>

      <div className="space-y-1">
        {filtered.map(tool => (
          <div key={tool.name} className="flex items-center gap-3 px-3 py-2.5 rounded-lg hover:bg-zinc-800 transition-colors group">
            <Badge tier={tool.tier} />
            <span className="text-sm text-zinc-200 font-medium flex-1">{tool.name}</span>
            <span className="text-xs text-zinc-600 font-mono hidden group-hover:block">{tool.entrypoint}</span>
            <span className="text-xs text-zinc-500">{tool.timeout}s</span>
            <ChevronRight size={12} className="text-zinc-700" />
          </div>
        ))}
      </div>
    </Card>
  );
}

function JobsPanel({ jobs, queue }) {
  const total = jobs.total_completed + jobs.total_failed;
  const successRate = total > 0 ? jobs.total_completed / total : 1;

  return (
    <Card>
      <SectionHeader icon={BarChart2} title="Jobs Summary" />
      <div className="grid grid-cols-3 gap-3 mb-4">
        {[
          { label: "Completed", value: jobs.total_completed, color: "text-emerald-400", icon: CheckCircle },
          { label: "Failed",    value: jobs.total_failed,    color: "text-red-400",     icon: XCircle    },
          { label: "Pending",   value: jobs.total_pending,   color: "text-amber-400",   icon: Clock      },
        ].map(({ label, value, color, icon: Icon }) => (
          <div key={label} className="bg-zinc-800 rounded-lg p-3 text-center">
            <Icon size={14} className={`${color} mx-auto mb-1.5`} />
            <p className={`text-xl font-bold ${color}`}>{value.toLocaleString()}</p>
            <p className="text-xs text-zinc-500 mt-0.5">{label}</p>
          </div>
        ))}
      </div>

      <div className="mb-2">
        <div className="flex justify-between text-xs mb-1.5">
          <span className="text-zinc-500">Success rate</span>
          <span className={loadColor(1 - successRate + 0.1)}>{pct(successRate)}</span>
        </div>
        <div className="h-2 w-full bg-zinc-800 rounded-full">
          <div className="h-2 rounded-full bg-emerald-500 transition-all duration-700"
            style={{ width: pct(successRate) }} />
        </div>
      </div>

      <div className="mt-4 pt-3 border-t border-zinc-800 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Database size={13} className="text-zinc-500" />
          <span className="text-xs text-zinc-500">Global queue</span>
        </div>
        <span className="text-sm font-semibold text-white">{queue.global_depth} waiting</span>
      </div>
    </Card>
  );
}

// ── Main Dashboard ────────────────────────────────────────────────────────────
export default function Dashboard() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [lastRefresh, setLastRefresh] = useState(null);
  const [autoRefresh, setAutoRefresh] = useState(true);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      // In production: const res = await fetch("/v1/dashboard"); const d = await res.json();
      // Demo: use mock data with simulated latency
      await new Promise(r => setTimeout(r, 350));
      setData(generateMock());
      setLastRefresh(new Date());
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, []);

  useEffect(() => {
    if (!autoRefresh) return;
    const id = setInterval(refresh, 5000);
    return () => clearInterval(id);
  }, [autoRefresh, refresh]);

  if (!data) {
    return (
      <div className="min-h-screen bg-zinc-950 flex items-center justify-center">
        <div className="flex flex-col items-center gap-3">
          <div className="w-8 h-8 border-2 border-violet-500 border-t-transparent rounded-full animate-spin" />
          <p className="text-zinc-500 text-sm">Loading platform state…</p>
        </div>
      </div>
    );
  }

  const { cluster, nodes, pools, queue, jobs, tools } = data;

  return (
    <div className="min-h-screen bg-zinc-950 text-white font-sans">
      {/* Top nav */}
      <header className="sticky top-0 z-50 bg-zinc-950/90 backdrop-blur border-b border-zinc-800">
        <div className="max-w-7xl mx-auto px-6 h-14 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="flex items-center gap-1.5">
              <div className="w-2 h-2 rounded-full bg-violet-500" />
              <div className="w-2 h-2 rounded-full bg-blue-500" />
              <div className="w-2 h-2 rounded-full bg-emerald-500" />
            </div>
            <span className="font-semibold text-sm text-white">sandbox-platform</span>
            <span className="text-zinc-700">·</span>
            <span className="text-xs text-zinc-500">control plane</span>
          </div>

          <div className="flex items-center gap-3">
            {lastRefresh && (
              <span className="text-xs text-zinc-600 hidden sm:block">
                Updated {ago(lastRefresh.toISOString())}
              </span>
            )}
            <button
              onClick={() => setAutoRefresh(v => !v)}
              className={`text-xs px-2.5 py-1.5 rounded-lg border transition-all ${
                autoRefresh
                  ? "bg-emerald-500/10 border-emerald-500/30 text-emerald-400"
                  : "bg-zinc-800 border-zinc-700 text-zinc-500"
              }`}
            >
              {autoRefresh ? "● Live" : "Paused"}
            </button>
            <button
              onClick={refresh}
              className="p-1.5 rounded-lg bg-zinc-800 hover:bg-zinc-700 transition-colors"
            >
              <RefreshCw size={14} className={`text-zinc-400 ${loading ? "animate-spin" : ""}`} />
            </button>
          </div>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-6 py-6 space-y-6">

        {/* Cluster KPIs */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
          <StatCard
            icon={Server}
            label="Active Nodes"
            value={cluster.active_nodes}
            sub={`${cluster.offline_nodes} offline`}
            color={cluster.offline_nodes > 0 ? "text-amber-400" : "text-white"}
          />
          <StatCard
            icon={Activity}
            label="Avg Load"
            value={pct(cluster.avg_load)}
            sub="across active nodes"
            color={loadColor(cluster.avg_load)}
          />
          <StatCard
            icon={Layers}
            label="Queue Depth"
            value={queue.global_depth}
            sub="jobs waiting"
            color={queue.global_depth > 20 ? "text-amber-400" : "text-white"}
          />
          <StatCard
            icon={GitBranch}
            label="Tools"
            value={tools.length}
            sub="registered"
          />
        </div>

        {/* Nodes */}
        <section>
          <SectionHeader icon={Server} title="Nodes" count={nodes.length} />
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            {nodes.map(n => <NodePanel key={n.id} node={n} />)}
          </div>
        </section>

        {/* Runtime Pools */}
        <section>
          <SectionHeader icon={HardDrive} title="Runtime Pools" />
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            <PoolPanel pool={pools.wasm}    />
            <PoolPanel pool={pools.microvm} />
            <PoolPanel pool={pools.gui}     />
          </div>
        </section>

        {/* Jobs + Tools */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <JobsPanel jobs={jobs} queue={queue} />
          <ToolsTable tools={tools} />
        </div>

        {/* Footer */}
        <div className="text-center pt-2 pb-4">
          <p className="text-xs text-zinc-700">
            sandbox-platform v1.1 · data from <code className="text-zinc-600">GET /v1/dashboard</code>
          </p>
        </div>
      </main>
    </div>
  );
}
