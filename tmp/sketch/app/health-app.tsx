'use client';
import { useEffect, useState, type FormEvent } from 'react';
import { Activity, FileText, ShieldCheck, History, Plus, Search, RefreshCw, ArrowUpRight, LockKeyhole, CheckCircle2, X, Paperclip, LoaderCircle, ShieldX } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { NativeSelect, NativeSelectOption as Option } from '@/components/ui/native-select';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from '@/components/ui/dialog';
import { Checkbox } from '@/components/ui/checkbox';
import { AlertDialog, AlertDialogContent, AlertDialogHeader, AlertDialogTitle, AlertDialogDescription, AlertDialogFooter, AlertDialogCancel, AlertDialogAction } from '@/components/ui/alert-dialog';
type Actor = {
    id: string;
    name: string;
    label: string;
    role: string;
};
type RecordItem = {
    id: string;
    owner: string;
    title: string;
    summary: string;
    source: string;
    date: string;
    kind: string;
    version: number;
    file_name?: string;
    file_size?: number;
    updated: string;
};
type Grant = {
    id: string;
    record_id: string;
    owner: string;
    doctor: string;
    title: string;
    expires: string;
    revoked: string | null;
    created: string;
};
type Log = {
    id: string;
    actor: string;
    title: string;
    action: string;
    result: string;
    created: string;
};
type Version = {
    version: number;
    title: string;
    summary: string;
    created: string;
};
const fmt = (v: string) => new Date(v).toLocaleString('en-GB', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false });
const url = (id: string) => '/api/records/' + encodeURIComponent(id);
const active = (g: Grant) => !g.revoked && Date.parse(g.expires) > Date.now();
async function api(path: string, method = 'GET', data?: unknown) { const res = await fetch(path, { method, cache: 'no-store', headers: data instanceof FormData ? undefined : data ? { 'Content-Type': 'application/json' } : undefined, body: data instanceof FormData ? data : data ? JSON.stringify(data) : undefined }); const payload = await res.json() as {
    error?: string;
    actor: Actor | null;
    actors: Actor[];
    records: RecordItem[];
    grants: Grant[];
    logs: Log[];
    record: RecordItem;
    history: Version[];
}; if (!res.ok)
    throw new Error(payload.error || 'The action failed. Please try again.'); return payload; }
export default function HealthApp() {
    const [actor, setActor] = useState<Actor | null>(null), [actors, setActors] = useState<Actor[]>([]), [records, setRecords] = useState<RecordItem[]>([]), [grants, setGrants] = useState<Grant[]>([]), [logs, setLogs] = useState<Log[]>([]), [busy, setBusy] = useState(false), [loading, setLoading] = useState(true), [message, setMessage] = useState<{
        text: string;
        error?: boolean;
    } | null>(null), [tab, setTab] = useState('records'), [search, setSearch] = useState(''), [kind, setKind] = useState('All types');
    const [create, setCreate] = useState(false), [share, setShare] = useState(false), [detail, setDetail] = useState<RecordItem | null>(null), [history, setHistory] = useState<Version[]>([]), [editing, setEditing] = useState(false), [revoke, setRevoke] = useState<Grant | null>(null), [selected, setSelected] = useState<string[]>([]), [doctor, setDoctor] = useState('doctor-wang'), [minutes, setMinutes] = useState('2880'), [preview, setPreview] = useState(false);
    const [draft, setDraft] = useState({ title: '', kind: 'Lab report', date: new Date().toISOString().slice(0, 10), source: 'Self-reported', summary: '' }), [editDraft, setEditDraft] = useState({ title: '', summary: '' });
    const isPatient = actor?.role === 'patient';
    const person = (id: string) => actors.find(a => a.id === id)?.label || id;
    async function refresh() { const [r, g, l] = await Promise.all([api('/api/records'), api('/api/grants'), api('/api/logs')]); setRecords(r.records); setGrants(g.grants); setLogs(l.logs); }
    async function switchActor(id: string) { setBusy(true); setMessage(null); setDetail(null); setCreate(false); setShare(false); setRevoke(null); setRecords([]); setGrants([]); setLogs([]); setSelected([]); setSearch(''); setTab('records'); try {
        const s = await api('/api/session', 'POST', { actor: id });
        setActor(s.actor);
        setActors(s.actors);
        await refresh();
    }
    catch (e) {
        setMessage({ text: (e as Error).message, error: true });
    }
    finally {
        setBusy(false);
        setLoading(false);
    } }
    useEffect(() => { let alive = true; (async () => { try {
        const s = await api('/api/session');
        if (!alive)
            return;
        setActors(s.actors);
        if (s.actor) {
            setActor(s.actor);
            await refresh();
            setLoading(false);
        }
        else
            await switchActor('patient-lin');
    }
    catch (e) {
        setMessage({ text: (e as Error).message, error: true });
        setLoading(false);
    } })(); return () => { alive = false; }; }, []);
    async function run(fn: () => Promise<void>) { setBusy(true); setMessage(null); try {
        await fn();
    }
    catch (e) {
        setMessage({ text: (e as Error).message, error: true });
    }
    finally {
        setBusy(false);
    } }
    async function openRecord(id: string) { await run(async () => { setDetail(null); setEditing(false); const d = await api(url(id)); setDetail(d.record); setHistory(d.history); await refresh(); }); }
    async function createRecord(e: FormEvent) { e.preventDefault(); await run(async () => { await api('/api/records', 'POST', draft); setCreate(false); setDraft({ ...draft, title: '', summary: '' }); await refresh(); setMessage({ text: 'Record saved. Open it to attach a PDF or image.' }); }); }
    async function saveEdit(e: FormEvent) { e.preventDefault(); if (!detail)
        return; await run(async () => { await api(url(detail.id), 'PATCH', { ...editDraft, version: detail.version }); const d = await api(url(detail.id)); setDetail(d.record); setHistory(d.history); setEditing(false); await refresh(); setMessage({ text: 'Changes saved. Earlier versions are available in the history.' }); }); }
    function startShare(ids: string[] = []) { setSelected(ids); setPreview(false); setShare(true); }
    async function grantAccess() { await run(async () => { await api('/api/grants', 'POST', { doctor, records: selected, minutes: Number(minutes) }); setShare(false); await refresh(); setTab('grants'); setMessage({ text: 'Access granted. Switch to the selected doctor to check access.' }); }); }
    async function upload(file: File) { if (!detail)
        return; await run(async () => { const f = new FormData(); f.append('file', file); await api(url(detail.id) + '/file', 'POST', f); const d = await api(url(detail.id)); setDetail(d.record); await refresh(); setMessage({ text: 'File uploaded. The same access permissions apply to the attachment.' }); }); }
    async function download() { if (!detail)
        return; await run(async () => { const r = await fetch(url(detail.id) + '/file', { cache: 'no-store' }); if (!r.ok) {
        const x = await r.json() as {
            error: string;
        };
        setDetail(null);
        throw new Error(x.error);
    } const blob = await r.blob(), link = document.createElement('a'), src = URL.createObjectURL(blob); link.href = src; link.download = detail.file_name || 'report'; link.click(); setTimeout(() => URL.revokeObjectURL(src), 1000); await refresh(); }); }
    const filtered = records.filter(r => (kind === 'All types' || r.kind === kind) && `${r.title} ${r.source} ${r.date}`.toLowerCase().includes(search.toLowerCase()));
    return <><header className="topbar"><div className="topinner"><div className="brand"><div className="brandicon"><Activity size={27}/></div><div><strong>Personal Health</strong><small>Personal Health Service System · oc2m</small></div></div><div className="identity"><label htmlFor="actor">Demo role</label><NativeSelect id="actor" aria-label="Switch demo role" value={actor?.id || ''} disabled={busy} onChange={e => switchActor(e.target.value)}>{!actor && <Option value="">Select a role</Option>}{actors.map(a => <Option key={a.id} value={a.id}>{a.label} · {a.role === 'patient' ? 'Patient' : 'Doctor'}</Option>)}</NativeSelect></div></div></header>
 <div className="demo-strip">Classroom demo · Sample records only · Switch roles to try the sharing workflow</div>
 <main className="shell"><div className="heading"><div><p className="eyebrow">{isPatient ? 'MY HEALTH SPACE' : 'DOCTOR WORKSPACE'}</p><h1>{isPatient ? 'My health records' : 'Shared health records'}</h1><p>{isPatient ? 'Organise your records and control who can access them, and for how long.' : 'View only the reports covered by an active patient permission.'}</p></div><div className="actions"><Button variant="outline" disabled={busy || !actor} onClick={() => run(refresh)}><RefreshCw size={16} className={busy ? 'spin' : ''}/>Refresh</Button>{isPatient && <Button disabled={busy} onClick={() => setCreate(true)}><Plus size={18}/>Add record</Button>}</div></div>
 {message && <div role={message.error ? 'alert' : 'status'} className={'notice' + (message.error ? ' error' : '')}>{message.error ? <ShieldX size={20}/> : <CheckCircle2 size={20}/>}<span>{message.text}</span><button aria-label="Dismiss message" onClick={() => setMessage(null)}><X size={18}/></button></div>}
 {loading ? <div className="loading"><LoaderCircle className="spin"/>Loading your records…</div> : <><section className="stats" aria-label="Records overview"><div className="stat"><FileText size={22}/><div><b>{records.length}</b><span>{isPatient ? 'Saved records' : 'Available records'}</span></div></div><div className="stat"><ShieldCheck size={22}/><div><b>{grants.filter(active).length}</b><span>Active permissions</span></div></div><div className="stat"><History size={22}/><div><b>{logs.length}</b><span>Recent activities</span></div></div></section>
 <Tabs className="main-tabs" value={tab} onValueChange={setTab}><TabsList variant="line"><TabsTrigger value="records"><FileText size={17}/>Health records</TabsTrigger><TabsTrigger value="grants"><ShieldCheck size={17}/>Sharing</TabsTrigger><TabsTrigger value="logs"><History size={17}/>Activity</TabsTrigger></TabsList>
 <TabsContent value="records"><div className="workspace"><div><div className="report-toolbar"><div className="searchbox"><Search size={18}/><Input placeholder="Search title, source or date" aria-label="Search records" value={search} onChange={e => setSearch(e.target.value)}/></div><NativeSelect aria-label="Record type" value={kind} onChange={e => setKind(e.target.value)}>{['All types', 'Lab report', 'Check-up', 'Medication', 'Other'].map(k => <Option key={k}>{k}</Option>)}</NativeSelect></div><div className="record-list">{filtered.map(r => <article className="report" key={r.id}><div className="report-icon"><FileText size={23}/></div><div className="report-copy"><span className="tag">{r.kind}</span><h3>{r.title}</h3><div className="meta"><span>{r.date}</span><span>{r.source}</span><span>v{r.version}{r.file_name ? ' · Attachment' : ''}</span></div></div><div className="actions"><Button variant="outline" disabled={busy} onClick={() => openRecord(r.id)}>View<ArrowUpRight size={15}/></Button>{isPatient && <Button variant="ghost" disabled={busy} onClick={() => startShare([r.id])}>Share</Button>}</div></article>)}{!filtered.length && <div className="empty"><LockKeyhole size={34}/><h3>{search ? 'No matching records' : isPatient ? 'No health records yet' : 'No reports available'}</h3><p>{isPatient ? 'Add a record to start organising your health information.' : 'Ask the patient to share a report with this doctor, then refresh.'}</p></div>}</div></div><aside className="side-note"><ShieldCheck color="#72d8c3" size={30}/><h2>Prepare for your visit</h2><ol><li><span className="stepnum">01</span>Gather the reports and files you need</li><li><span className="stepnum">02</span>Choose a doctor and access period</li><li><span className="stepnum">03</span>Review activity and revoke access at any time</li></ol>{isPatient && <Button className="w-full" disabled={busy || !records.length} onClick={() => startShare()}>Choose reports to share</Button>}<small>Record dates and access duration are separate. Further access is blocked after expiry.</small></aside></div></TabsContent>
 <TabsContent value="grants"><div className="heading"><div><h2 className="text-xl font-semibold">{isPatient ? 'Permissions I have granted' : 'Permissions from patients'}</h2><p>Doctors can view reports and read attachments. They cannot edit patient records.</p></div>{isPatient && <Button disabled={busy || !records.length} onClick={() => startShare()}><Plus size={17}/>Grant access</Button>}</div><div className="panel-list">{grants.map(g => <article className="grant-row" key={g.id}><div><span className={'status' + (active(g) ? '' : ' off')}>{g.revoked ? 'Revoked' : active(g) ? 'Active' : 'Expired'}</span><h3>{g.title}</h3><div className="meta"><span>{person(g.owner)} → {person(g.doctor)}</span><span>Expires {fmt(g.expires)}</span><span>View reports and attachments</span></div></div><div className="actions">{isPatient ? active(g) && <Button variant="outline" disabled={busy} onClick={() => setRevoke(g)}>Revoke access</Button> : <Button variant="outline" disabled={busy} onClick={() => openRecord(g.record_id)}>{active(g) ? 'View report' : 'Check blocked access'}</Button>}</div></article>)}{!grants.length && <div className="empty"><ShieldCheck size={34}/><h3>No permissions yet</h3><p>{isPatient ? 'Choose reports and a doctor, then preview and confirm.' : 'Switch to a patient to grant access to this doctor.'}</p></div>}</div></TabsContent>
 <TabsContent value="logs"><p className="mb-4 text-muted-foreground">Track views, edits, permissions and file access. Denied requests are recorded too.</p>{logs.length ? <div className="logwrap"><table><thead><tr><th>Time</th><th>Actor</th><th>Action</th><th>Report</th><th>Result</th></tr></thead><tbody>{logs.map(l => <tr key={l.id}><td>{fmt(l.created)}</td><td>{person(l.actor)}</td><td>{l.action}</td><td>{l.title}</td><td><span className={'status' + (l.result === 'denied' ? ' denied' : '')}>{l.result === 'denied' ? 'Denied' : 'Success'}</span></td></tr>)}</tbody></table></div> : <div className="empty"><History size={34}/><h3>No activity yet</h3><p>View a report or grant access to see activity here.</p></div>}</TabsContent></Tabs></>}
 <footer className="footer"><span>Personal Health · oc2m</span><span>Health records / Time-limited sharing / Access history</span></footer></main>
 <Dialog open={create} onOpenChange={o => !busy && setCreate(o)}><DialogContent className="modal-wide modal-scroll"><DialogHeader><DialogTitle>Add a health record</DialogTitle><DialogDescription>Save the record first, then open it to add an attachment.</DialogDescription></DialogHeader>{message?.error && <p role="alert" className="notice error">{message.text}</p>}<form onSubmit={createRecord} className="grid gap-5"><div className="formgrid"><div className="field full"><label htmlFor="title">Record title</label><Input id="title" required maxLength={100} value={draft.title} onChange={e => setDraft({ ...draft, title: e.target.value })} placeholder="For example: Follow-up test report"/></div><div className="field"><label htmlFor="record-kind">Type</label><NativeSelect id="record-kind" value={draft.kind} onChange={e => setDraft({ ...draft, kind: e.target.value })}>{['Lab report', 'Check-up', 'Medication', 'Other'].map(k => <Option key={k}>{k}</Option>)}</NativeSelect></div><div className="field"><label htmlFor="record-date">Record date</label><Input id="record-date" type="date" required value={draft.date} onChange={e => setDraft({ ...draft, date: e.target.value })}/></div><div className="field full"><label htmlFor="source">Source</label><Input id="source" required maxLength={120} value={draft.source} onChange={e => setDraft({ ...draft, source: e.target.value })}/></div><div className="field full"><label htmlFor="summary">Record content</label><Textarea id="summary" required maxLength={8000} value={draft.summary} onChange={e => setDraft({ ...draft, summary: e.target.value })} placeholder="Enter a summary or notes. Please use sample information only."/></div></div><Button type="submit" disabled={busy}>{busy ? 'Saving…' : 'Save record'}</Button></form></DialogContent></Dialog>
 <Dialog open={!!detail} onOpenChange={o => !o && !busy && setDetail(null)}><DialogContent className="modal-wide modal-scroll"><DialogHeader><DialogTitle>{detail?.title || 'Report details'}</DialogTitle><DialogDescription>{detail?.kind} · {detail?.source}</DialogDescription></DialogHeader>{message?.error && <p role="alert" className="notice error">{message.text}</p>}{detail && <><div className="detail-meta"><span>Record date {detail.date}</span><span>Current version v{detail.version}</span><span>Updated {fmt(detail.updated)}</span></div>{editing ? <form className="grid gap-4" onSubmit={saveEdit}><label htmlFor="edit-title">Title</label><Input id="edit-title" value={editDraft.title} maxLength={100} required onChange={e => setEditDraft({ ...editDraft, title: e.target.value })}/><label htmlFor="edit-summary">Content</label><Textarea id="edit-summary" value={editDraft.summary} maxLength={8000} required onChange={e => setEditDraft({ ...editDraft, summary: e.target.value })}/><div className="actions"><Button disabled={busy} type="submit">Save new version</Button><Button type="button" variant="outline" onClick={() => setEditing(false)}>Cancel</Button></div></form> : <><div className="record-body">{detail.summary}</div><div className="actions">{isPatient && <Button variant="outline" disabled={busy} onClick={() => { setEditDraft({ title: detail.title, summary: detail.summary }); setEditing(true); }}>Edit record</Button>}<Button variant="outline" disabled={busy} onClick={() => openRecord(detail.id)}><RefreshCw size={15}/>Check access again</Button>{detail.file_name && <Button disabled={busy} variant="outline" onClick={download}><Paperclip size={15}/>Read attachment</Button>}</div>{detail.file_name ? <p className="form-hint">Attachment: {detail.file_name} · {Math.ceil((detail.file_size || 0) / 1024)} KB</p> : isPatient && <div className="field"><label htmlFor="upload">Add an attachment</label><Button asChild variant="outline"><label htmlFor="upload">Choose file</label></Button><Input className="sr-only" id="upload" type="file" disabled={busy} accept="application/pdf,image/png,image/jpeg" onChange={e => { const f = e.target.files?.[0]; if (f)
        upload(f); }}/><span className="form-hint">PDF, PNG or JPG, up to 5 MB.</span></div>}</>}{isPatient && <div className="history"><h3>Change history</h3>{history.map(v => <div className="history-entry" key={v.version}><b>v{v.version} · {v.title}</b><br /><small>{fmt(v.created)}</small><p>{v.summary}</p></div>)}</div>}</>}</DialogContent></Dialog>
 <Dialog open={share} onOpenChange={o => !busy && setShare(o)}><DialogContent className="modal-wide modal-scroll"><DialogHeader><DialogTitle>{preview ? 'Review sharing details' : 'Share with a doctor'}</DialogTitle><DialogDescription>Only selected records will be shared. Other records stay private.</DialogDescription></DialogHeader>{message?.error && <p role="alert" className="notice error">{message.text}</p>}{preview ? <><div className="preview-note"><b>{person(doctor)}</b> can view the following {selected.length} report(s) and their attachments. Access period: {minutes === '1' ? '1 minute (demo)' : minutes === '60' ? '1 hour' : minutes === '1440' ? '1 day' : minutes === '2880' ? '2 days' : '7 days'}.<br />Editing is not allowed. You can revoke further access at any time.</div><ul className="list-disc pl-6 space-y-2">{records.filter(r => selected.includes(r.id)).map(r => <li key={r.id}>{r.title} · {r.date}</li>)}</ul><div className="actions"><Button disabled={busy} onClick={grantAccess}>Confirm access</Button><Button disabled={busy} variant="outline" onClick={() => setPreview(false)}>Back to edit</Button></div></> : <><div className="formgrid"><div className="field"><label htmlFor="doctor">Doctor</label><NativeSelect id="doctor" value={doctor} onChange={e => setDoctor(e.target.value)}>{actors.filter(a => a.role === 'doctor').map(a => <Option key={a.id} value={a.id}>{a.name}</Option>)}</NativeSelect></div><div className="field"><label htmlFor="duration">Allow access from now for</label><NativeSelect id="duration" value={minutes} onChange={e => setMinutes(e.target.value)}><Option value="1">1 minute (expiry demo)</Option><Option value="60">1 hour</Option><Option value="1440">1 day</Option><Option value="2880">2 days</Option><Option value="10080">7 days</Option></NativeSelect></div></div><label>Choose reports ({selected.length} selected)</label><div className="selection-list">{records.map(r => <label className="grant-choice" key={r.id}><Checkbox checked={selected.includes(r.id)} onCheckedChange={checked => setSelected(checked ? [...selected, r.id] : selected.filter(id => id !== r.id))}/><span>{r.title}<small className="block text-muted-foreground font-normal">{r.date} · {r.kind}</small></span></label>)}</div><Button disabled={!selected.length || busy} onClick={() => setPreview(true)}>Preview sharing</Button></>}</DialogContent></Dialog>
 <AlertDialog open={!!revoke} onOpenChange={o => !o && !busy && setRevoke(null)}><AlertDialogContent><AlertDialogHeader><AlertDialogTitle>Revoke this permission?</AlertDialogTitle><AlertDialogDescription>After revocation, {revoke && person(revoke.doctor)} will no longer be able to access this report or attachment through the system. Previously downloaded copies cannot be recalled.</AlertDialogDescription></AlertDialogHeader><AlertDialogFooter><AlertDialogCancel disabled={busy}>Keep access</AlertDialogCancel><AlertDialogAction disabled={busy} onClick={e => { e.preventDefault(); if (revoke)
        run(async () => { await api('/api/grants', 'DELETE', { id: revoke.id }); setRevoke(null); await refresh(); setMessage({ text: 'Access revoked. Switch to the doctor to check that access is blocked.' }); }); }}>Revoke access</AlertDialogAction></AlertDialogFooter></AlertDialogContent></AlertDialog>
 </>;
}
