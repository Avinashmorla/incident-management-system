import React, { useEffect, useMemo, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { Activity, AlertTriangle, CheckCircle2, ClipboardList, RefreshCw, Send } from 'lucide-react';
import './styles.css';

const API_BASE = import.meta.env.VITE_API_BASE ?? 'http://localhost:8000';

async function api(path, options) {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail ?? `Request failed with ${response.status}`);
  }
  return response.json();
}

function fmt(value) {
  return new Intl.DateTimeFormat(undefined, {
    month: 'short',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).format(new Date(value));
}

function App() {
  const [dashboard, setDashboard] = useState({ active: [], totals_by_severity: {}, signals_per_second: 0 });
  const [selectedId, setSelectedId] = useState(null);
  const [detail, setDetail] = useState(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const selected = detail?.work_item;

  async function loadDashboard() {
    const next = await api('/dashboard');
    setDashboard(next);
    if (!selectedId && next.active.length) {
      setSelectedId(next.active[0].id);
    }
  }

  async function loadDetail(id) {
    if (!id) return;
    setDetail(await api(`/work-items/${id}`));
  }

  useEffect(() => {
    loadDashboard().catch((err) => setError(err.message));
    const timer = setInterval(() => loadDashboard().catch((err) => setError(err.message)), 3000);
    return () => clearInterval(timer);
  }, []);

  useEffect(() => {
    loadDetail(selectedId).catch((err) => setError(err.message));
  }, [selectedId]);

  async function transition(status) {
    if (!selectedId) return;
    setLoading(true);
    setError('');
    try {
      await api(`/work-items/${selectedId}/status`, {
        method: 'PATCH',
        body: JSON.stringify({ status }),
      });
      await Promise.all([loadDashboard(), loadDetail(selectedId)]);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  const totals = useMemo(() => ['P0', 'P1', 'P2', 'P3'].map((sev) => [sev, dashboard.totals_by_severity[sev] ?? 0]), [dashboard]);

  return (
    <main>
      <header className="topbar">
        <div>
          <p className="eyebrow">Mission Critical IMS</p>
          <h1>Incident Command</h1>
        </div>
        <button className="iconButton" onClick={() => loadDashboard()} title="Refresh incidents">
          <RefreshCw size={18} />
        </button>
      </header>

      <section className="metrics">
        {totals.map(([severity, count]) => (
          <div className={`metric ${severity.toLowerCase()}`} key={severity}>
            <span>{severity}</span>
            <strong>{count}</strong>
          </div>
        ))}
        <div className="metric throughput">
          <span>Signals/sec</span>
          <strong>{dashboard.signals_per_second.toFixed(1)}</strong>
        </div>
      </section>

      {error && <div className="banner">{error}</div>}

      <div className="layout">
        <IncidentFeed incidents={dashboard.active} selectedId={selectedId} onSelect={setSelectedId} />
        <section className="detail">
          {!selected ? (
            <EmptyState />
          ) : (
            <>
              <div className="detailHeader">
                <div>
                  <p className={`severity ${selected.severity.toLowerCase()}`}>{selected.severity}</p>
                  <h2>{selected.component_id}</h2>
                  <p>{selected.component_type} · {selected.alert_channel}</p>
                </div>
                <StatusActions item={selected} disabled={loading} onTransition={transition} />
              </div>

              <div className="statusStrip">
                <span>{selected.status}</span>
                <span>{selected.signal_count} linked signals</span>
                <span>First seen {fmt(selected.first_signal_at)}</span>
              </div>

              <RcaForm selected={selected} onSaved={() => Promise.all([loadDashboard(), loadDetail(selectedId)])} setError={setError} />
              <RawSignals signals={detail.signals} />
            </>
          )}
        </section>
      </div>
    </main>
  );
}

function IncidentFeed({ incidents, selectedId, onSelect }) {
  return (
    <aside className="feed">
      <div className="panelTitle">
        <Activity size={18} />
        <span>Live Feed</span>
      </div>
      {incidents.length === 0 && <p className="muted">No active incidents.</p>}
      {incidents.map((incident) => (
        <button
          className={`feedItem ${incident.id === selectedId ? 'selected' : ''}`}
          key={incident.id}
          onClick={() => onSelect(incident.id)}
        >
          <span className={`dot ${incident.severity.toLowerCase()}`} />
          <span>
            <strong>{incident.component_id}</strong>
            <small>{incident.status} · {incident.signal_count} signals</small>
          </span>
        </button>
      ))}
    </aside>
  );
}

function StatusActions({ item, disabled, onTransition }) {
  const actions = {
    OPEN: ['INVESTIGATING'],
    INVESTIGATING: ['RESOLVED'],
    RESOLVED: ['CLOSED', 'INVESTIGATING'],
    CLOSED: [],
  }[item.status];

  return (
    <div className="actions">
      {actions.map((status) => (
        <button key={status} disabled={disabled} onClick={() => onTransition(status)}>
          {status === 'CLOSED' ? <CheckCircle2 size={16} /> : <Send size={16} />}
          {status}
        </button>
      ))}
    </div>
  );
}

function RcaForm({ selected, onSaved, setError }) {
  const [form, setForm] = useState({
    incident_start: '',
    incident_end: '',
    root_cause_category: 'CAPACITY',
    fix_applied: '',
    prevention_steps: '',
  });

  useEffect(() => {
    setForm((current) => ({
      ...current,
      incident_start: selected.first_signal_at.slice(0, 16),
      incident_end: new Date().toISOString().slice(0, 16),
    }));
  }, [selected.id]);

  function update(field, value) {
    setForm((current) => ({ ...current, [field]: value }));
  }

  async function submit(event) {
    event.preventDefault();
    setError('');
    try {
      await api(`/work-items/${selected.id}/rca`, {
        method: 'POST',
        body: JSON.stringify({
          ...form,
          incident_start: new Date(form.incident_start).toISOString(),
          incident_end: new Date(form.incident_end).toISOString(),
        }),
      });
      await onSaved();
    } catch (err) {
      setError(err.message);
    }
  }

  return (
    <form className="rca" onSubmit={submit}>
      <div className="panelTitle">
        <ClipboardList size={18} />
        <span>RCA</span>
      </div>
      <div className="formGrid">
        <label>
          Start
          <input type="datetime-local" value={form.incident_start} onChange={(event) => update('incident_start', event.target.value)} />
        </label>
        <label>
          End
          <input type="datetime-local" value={form.incident_end} onChange={(event) => update('incident_end', event.target.value)} />
        </label>
        <label>
          Category
          <select value={form.root_cause_category} onChange={(event) => update('root_cause_category', event.target.value)}>
            {['CODE_DEPLOY', 'INFRASTRUCTURE', 'DATA_CORRUPTION', 'CAPACITY', 'THIRD_PARTY', 'UNKNOWN'].map((item) => (
              <option key={item}>{item}</option>
            ))}
          </select>
        </label>
      </div>
      <label>
        Fix Applied
        <textarea value={form.fix_applied} onChange={(event) => update('fix_applied', event.target.value)} />
      </label>
      <label>
        Prevention Steps
        <textarea value={form.prevention_steps} onChange={(event) => update('prevention_steps', event.target.value)} />
      </label>
      <button className="primary" type="submit">
        <CheckCircle2 size={16} />
        Save RCA
      </button>
      {selected.rca && <p className="mttr">MTTR: {(selected.rca.mttr_seconds / 60).toFixed(1)} minutes</p>}
    </form>
  );
}

function RawSignals({ signals }) {
  return (
    <section className="signals">
      <div className="panelTitle">
        <AlertTriangle size={18} />
        <span>Raw Signals</span>
      </div>
      {signals.map((signal) => (
        <article key={signal.id}>
          <strong>{signal.message}</strong>
          <small>{fmt(signal.observed_at)} · {signal.error_code ?? 'NO_CODE'}</small>
          <pre>{JSON.stringify(signal.payload, null, 2)}</pre>
        </article>
      ))}
    </section>
  );
}

function EmptyState() {
  return (
    <div className="empty">
      <AlertTriangle size={28} />
      <p>Select an incident from the live feed.</p>
    </div>
  );
}

createRoot(document.getElementById('root')).render(<App />);
