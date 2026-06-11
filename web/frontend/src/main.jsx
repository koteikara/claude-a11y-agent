import React, { useEffect, useMemo, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import './styles.css';


const stageLabel = (stage) => ({ old: 'old（元ページ）', ai: 'ai（AI下書き）', gold: 'gold（承認済み）' }[stage] || stage);
const typeLabel = (type) => ({ added: '追加', removed: '削除', changed: '変更' }[type] || type);

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
        <h1>Claude A11y 管理画面</h1>
        <nav>
          <button className={view === 'jobs' ? 'active' : ''} onClick={() => setView('jobs')}>ジョブ一覧</button>
          <button className={view === 'metrics' ? 'active' : ''} onClick={() => setView('metrics')}>指標</button>
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
      <label>サイト <input value={site} onChange={(e) => setSite(e.target.value)} placeholder="saga-city" /></label>
      <label>状態 <input value={status} onChange={(e) => setStatus(e.target.value)} placeholder="queued/done" /></label>
      <button onClick={load}>更新</button>
    </section>
    {error && <p className="error">{error}</p>}
    <table className="jobs"><thead><tr><th>ジョブ</th><th>サイト</th><th>ページ</th><th>状態</th><th>レビュー</th><th>操作</th></tr></thead><tbody>
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
  const approve = async () => { const data = await api(`/api/jobs/${jobId}/approve`, { method: 'POST', body: JSON.stringify({}) }); setMessage(`承認しました: ${data.gold_output_link}`); load(); };
  return <main>
    <button onClick={onBack}>← 一覧へ</button>
    <h2>{job?.site}/{job?.page_id}</h2>
    <p><span className={`badge ${job?.status}`}>{job?.status}</span> レビュー: {job?.review_status || '-'}</p>
    <section className="frames">
      {['old', 'ai', 'gold'].map((stage) => <div className="frame-card" key={stage}><h3>{stageLabel(stage)}</h3><iframe title={stage} sandbox="" src={`/api/jobs/${jobId}/html?stage=${stage}`} /></div>)}
    </section>
    <section className="panel"><h3>差分</h3><DiffBlock title="old（元ページ）→ ai（AI下書き）" data={diff?.old_ai} /><DiffBlock title="ai（AI下書き）→ gold（承認済み）" data={diff?.ai_gold} /></section>
    <section className="panel"><h3>要確認</h3>{review.map((item) => <div className="review" key={item.id}><b>{item.rule_id}</b><p>{item.message}</p><small>{item.location}</small><div><button onClick={() => decide(item.id, 'accept')}>受け入れ</button><button onClick={() => decide(item.id, 'edit')}>修正</button><button onClick={() => decide(item.id, 'skip')}>スキップ</button></div></div>)}</section>
    <button className="approve" onClick={approve}>承認（gold確定）</button>{message && <p>{message}</p>}
  </main>;
}

function DiffBlock({ title, data }) {
  return <div><h4>{title}</h4><p>追加 {data?.summary.added ?? 0} / 削除 {data?.summary.removed ?? 0} / 変更 {data?.summary.changed ?? 0}</p><ul>{(data?.items || []).map((item, i) => <li key={i}><b>{typeLabel(item.type)}</b>: {item.excerpt}</li>)}</ul></div>;
}

function Metrics() {
  const [metrics, setMetrics] = useState(null);
  useEffect(() => { api('/api/metrics').then(setMetrics); }, []);
  const chartData = Object.entries(metrics?.jobs_by_status || {}).map(([status, count]) => ({ 状態: status, 件数: count }));
  return <main><h2>指標</h2><section className="panel totals"><div>ジョブ数: {metrics?.totals.jobs ?? 0}</div><div>未対応の要確認: {metrics?.totals.review_open ?? 0}</div><div>通過チェック: {metrics?.totals.checks_passed ?? 0}</div><div>失敗チェック: {metrics?.totals.checks_failed ?? 0}</div><div>助言件数: {metrics?.totals.advisory_hits ?? 0}</div></section><section className="panel chart"><ResponsiveContainer width="100%" height={260}><BarChart data={chartData}><CartesianGrid strokeDasharray="3 3" /><XAxis dataKey="状態" /><YAxis allowDecimals={false} /><Tooltip /><Legend /><Bar dataKey="件数" fill="#2563eb" /></BarChart></ResponsiveContainer></section></main>;
}

createRoot(document.getElementById('root')).render(<App />);
