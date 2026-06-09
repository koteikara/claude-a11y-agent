import React, { useEffect, useMemo, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import './styles.css';

const api = async (path, options = {}) => {
  const response = await fetch(path, {
    ...options,
    headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
  });
  if (!response.ok) throw new Error(`${response.status} ${await response.text()}`);
  return response.headers.get('content-type')?.includes('application/json') ? response.json() : response.text();
};

function App() {
  const [view, setView] = useState('jobs');
  const [selectedJobId, setSelectedJobId] = useState(null);
  return (
    <div className="app">
      <header>
        <h1>Claude A11y Admin</h1>
        <nav>
          <button className={view === 'jobs' ? 'active' : ''} onClick={() => setView('jobs')}>Jobs</button>
          <button className={view === 'metrics' ? 'active' : ''} onClick={() => setView('metrics')}>Metrics</button>
        </nav>
      </header>
      {view === 'jobs' && !selectedJobId && <JobsList onSelect={setSelectedJobId} />}
      {view === 'jobs' && selectedJobId && <JobDetail jobId={selectedJobId} onBack={() => setSelectedJobId(null)} />}
      {view === 'metrics' && <Metrics />}
    </div>
  );
}

function JobsList({ onSelect }) {
  const [jobs, setJobs] = useState([]);
  const [site, setSite] = useState('');
  const [status, setStatus] = useState('');
  const [error, setError] = useState('');
  const query = useMemo(() => new URLSearchParams(Object.fromEntries(Object.entries({ site, status }).filter(([, v]) => v))).toString(), [site, status]);
  const load = () => api(`/api/jobs${query ? `?${query}` : ''}`).then((data) => setJobs(data.jobs)).catch((err) => setError(err.message));
  useEffect(() => { load(); const id = setInterval(load, 5000); return () => clearInterval(id); }, [query]);
  const run = async (jobId) => { await api(`/api/jobs/${jobId}/run`, { method: 'POST' }); load(); };
  return <main>
    <section className="panel filters">
      <label>Site <input value={site} onChange={(e) => setSite(e.target.value)} placeholder="saga-city" /></label>
      <label>Status <input value={status} onChange={(e) => setStatus(e.target.value)} placeholder="queued/done" /></label>
      <button onClick={load}>更新</button>
    </section>
    {error && <p className="error">{error}</p>}
    <table className="jobs"><thead><tr><th>Job</th><th>Site</th><th>Page</th><th>Status</th><th>Review</th><th>Actions</th></tr></thead><tbody>
      {jobs.map((job) => <tr key={job.job_id}>
        <td>{job.job_id}</td><td>{job.site}</td><td>{job.page_id}</td>
        <td><span className={`badge ${job.status || 'unknown'}`}>{job.status || 'unknown'}</span></td>
        <td>{job.review_status || '-'}</td>
        <td><button onClick={() => run(job.job_id)}>実行</button><button onClick={() => onSelect(job.job_id)}>詳細</button></td>
      </tr>)}
    </tbody></table>
  </main>;
}

function JobDetail({ jobId, onBack }) {
  const [job, setJob] = useState(null);
  const [diff, setDiff] = useState(null);
  const [review, setReview] = useState([]);
  const [message, setMessage] = useState('');
  const load = () => Promise.all([
    api(`/api/jobs/${jobId}`), api(`/api/jobs/${jobId}/diff`), api('/api/review?status=open')
  ]).then(([jobData, diffData, reviewData]) => { setJob(jobData.job); setDiff(diffData); setReview(reviewData.review.filter((r) => r.job_id === jobId)); });
  useEffect(() => { load(); const id = setInterval(load, 5000); return () => clearInterval(id); }, [jobId]);
  const decide = async (rowId, decision) => { await api(`/api/review/${rowId}/decision`, { method: 'POST', body: JSON.stringify({ decision }) }); load(); };
  const approve = async () => { const data = await api(`/api/jobs/${jobId}/approve`, { method: 'POST', body: JSON.stringify({}) }); setMessage(`approved: ${data.gold_output_link}`); load(); };
  return <main>
    <button onClick={onBack}>← 一覧へ</button>
    <h2>{job?.site}/{job?.page_id}</h2>
    <p><span className={`badge ${job?.status}`}>{job?.status}</span> review: {job?.review_status || '-'}</p>
    <section className="frames">
      {['old', 'ai', 'gold'].map((stage) => <div className="frame-card" key={stage}><h3>{stage}</h3><iframe title={stage} sandbox="" src={`/api/jobs/${jobId}/html?stage=${stage}`} /></div>)}
    </section>
    <section className="panel"><h3>Diff</h3><DiffBlock title="old → ai" data={diff?.old_ai} /><DiffBlock title="ai → gold" data={diff?.ai_gold} /></section>
    <section className="panel"><h3>Review</h3>{review.map((item) => <div className="review" key={item.id}><b>{item.rule_id}</b><p>{item.message}</p><small>{item.location}</small><div><button onClick={() => decide(item.id, 'accept')}>accept</button><button onClick={() => decide(item.id, 'edit')}>edit</button><button onClick={() => decide(item.id, 'skip')}>skip</button></div></div>)}</section>
    <button className="approve" onClick={approve}>承認（gold確定）</button>{message && <p>{message}</p>}
  </main>;
}

function DiffBlock({ title, data }) {
  return <div><h4>{title}</h4><p>added {data?.summary.added ?? 0} / removed {data?.summary.removed ?? 0} / changed {data?.summary.changed ?? 0}</p><ul>{(data?.items || []).map((item, i) => <li key={i}><b>{item.type}</b>: {item.excerpt}</li>)}</ul></div>;
}

function Metrics() {
  const [metrics, setMetrics] = useState(null);
  useEffect(() => { api('/api/metrics').then(setMetrics); }, []);
  const chartData = Object.entries(metrics?.jobs_by_status || {}).map(([status, count]) => ({ status, count }));
  return <main><h2>Metrics</h2><section className="panel totals"><div>Jobs: {metrics?.totals.jobs ?? 0}</div><div>Open review: {metrics?.totals.review_open ?? 0}</div><div>Checks passed: {metrics?.totals.checks_passed ?? 0}</div><div>Checks failed: {metrics?.totals.checks_failed ?? 0}</div><div>Advisory: {metrics?.totals.advisory_hits ?? 0}</div></section><section className="panel chart"><ResponsiveContainer width="100%" height={260}><BarChart data={chartData}><CartesianGrid strokeDasharray="3 3" /><XAxis dataKey="status" /><YAxis allowDecimals={false} /><Tooltip /><Legend /><Bar dataKey="count" fill="#2563eb" /></BarChart></ResponsiveContainer></section></main>;
}

createRoot(document.getElementById('root')).render(<App />);
