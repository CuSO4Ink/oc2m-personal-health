import { env } from 'cloudflare:workers';
export const actors = [{ id: 'patient-lin', name: 'Lin Chen', label: 'Lin Chen', role: 'patient' }, { id: 'doctor-wang', name: 'Dr. Wang', label: 'Dr. Wang', role: 'doctor' }, { id: 'doctor-li', name: 'Dr. Li', label: 'Dr. Li', role: 'doctor' }, { id: 'patient-zhou', name: 'Zhou Ning', label: 'Zhou Ning', role: 'patient' }] as const;
export type RecordRow = {
    id: string;
    tenant: string;
    owner: string;
    title: string;
    kind: string;
    date: string;
    source: string;
    summary: string;
    version: number;
    created: string;
    updated: string;
    file_key: string | null;
    file_name: string | null;
    file_type: string | null;
    file_size: number | null;
};
export class ApiError extends Error {
    constructor(public status: number, message: string) { super(message); }
}
export function db() { const d = (env as unknown as {
    DB: D1Database;
}).DB; if (!d)
    throw new ApiError(503, 'The data service is unavailable. Please try again.'); return d; }
export function bucket() { const b = (env as unknown as {
    BUCKET: R2Bucket;
}).BUCKET; if (!b)
    throw new ApiError(503, 'File storage is unavailable. Please try again.'); return b; }
export function stmt(sql: string, ...args: unknown[]) { return db().prepare(sql).bind(...args); }
export function now() { return new Date().toISOString(); }
export function safeRecord(r: RecordRow) { const { file_key, tenant, ...rest } = r; void file_key; void tenant; return rest; }
export async function tenant(req: Request) { const id = req.headers.get('oai-authenticated-user-id'); if (id)
    return id; if (['127.0.0.1', 'localhost', '[::1]'].includes(new URL(req.url).hostname))
    return 'local-classroom'; throw new ApiError(401, 'Please sign in with ChatGPT to continue.'); }
export async function context(req: Request) { const t = await tenant(req); const sid = (req.headers.get('cookie') || '').split(';').map(x => x.trim()).find(x => x.startsWith('health_session='))?.slice(15); if (!sid)
    throw new ApiError(401, 'Please select a demo role first.'); const row = await stmt('SELECT actor FROM sessions WHERE id=? AND tenant=? AND expires>?', sid, t, now()).first<{
    actor: string;
}>(); const actor = actors.find(x => x.id === row?.actor); if (!actor)
    throw new ApiError(401, 'Your demo session has expired. Please select your role again.'); return { tenant: t, actor }; }
export type Context = Awaited<ReturnType<typeof context>>;
export function patient(c: Context) { if (c.actor.role !== 'patient')
    throw new ApiError(403, 'Only patients can perform this action.'); }
export function logStmt(c: Context, r: {
    owner: string;
    id: string;
    title: string;
}, action: string, result = 'success') { return stmt('INSERT INTO logs(id,tenant,owner,actor,record_id,title,action,result,created) VALUES(?,?,?,?,?,?,?,?,?)', crypto.randomUUID(), c.tenant, r.owner, c.actor.id, r.id, r.title, action, result, now()); }
export async function getRecord(c: Context, id: string) { const r = await stmt('SELECT * FROM records WHERE id=? AND tenant=?', id, c.tenant).first<RecordRow>(); if (!r)
    throw new ApiError(404, 'Report not found.'); return r; }
export async function access(c: Context, r: RecordRow, action: string) { const g = c.actor.role === 'doctor' ? await stmt('SELECT id FROM grants WHERE tenant=? AND doctor=? AND record_id=? AND revoked IS NULL AND expires>? LIMIT 1', c.tenant, c.actor.id, r.id, now()).first() : null; if (r.owner !== c.actor.id && !g) {
    await logStmt(c, r, action, 'denied').run();
    throw new ApiError(403, 'Access denied: permission is missing, revoked or expired.');
} }
export async function seed(t: string) { const time = now(); const rows = [['sample-blood', 'patient-lin', 'Blood test report', 'Lab report', '2026-09-08', 'Demo Hospital · Laboratory', 'A blood test report prepared for a follow-up visit.\nSample record for classroom demonstration. No real test results.'], ['sample-checkup', 'patient-lin', 'Annual health check-up', 'Check-up', '2026-09-02', 'Demo Health Centre', 'An annual check-up record for demonstrating organisation and time-limited sharing.'], ['sample-medication', 'patient-lin', 'Recent medication record', 'Medication', '2026-09-10', 'Self-reported', 'A sample medication record. Edit the content and review earlier versions in the change history.'], ['sample-other', 'patient-zhou', 'Another patient’s report', 'Lab report', '2026-09-09', 'Demo Hospital', 'A sample record used to check that patients cannot access each other’s information.']]; await db().batch(rows.map(([id, owner, title, kind, date, source, summary]) => stmt('INSERT OR IGNORE INTO records(id,tenant,owner,title,kind,date,source,summary,version,created,updated) VALUES(?,?,?,?,?,?,?,?,1,?,?)', `${t}:${id}`, t, owner, title, kind, date, source, summary, time, time))); await stmt("INSERT OR IGNORE INTO versions(id,record_id,tenant,version,title,summary,actor,created) SELECT id || ':v1',id,tenant,1,title,summary,owner,created FROM records WHERE tenant=? AND version=1", t).run(); }
export async function body(req: Request) { if (Number(req.headers.get('content-length') || 0) > 50000)
    throw new ApiError(413, 'The input is too long.'); try {
    const data = await req.json();
    if (!data || typeof data !== 'object' || Array.isArray(data))
        throw new Error();
    return data as Record<string, unknown>;
}
catch {
    throw new ApiError(400, 'Invalid request format.');
} }
export function field(v: unknown, name: string, max = 150) { if (typeof v !== 'string' || !v.trim() || v.trim().length > max)
    throw new ApiError(400, `${name} is required and must be at most ${max} characters.`); return v.trim(); }
export async function route(req: Request, fn: () => Promise<Response>) { try {
    if (!['GET', 'HEAD'].includes(req.method)) {
        const o = req.headers.get('origin');
        if (o && o !== new URL(req.url).origin)
            throw new ApiError(403, 'Cross-site requests are not allowed.');
    }
    const res = await fn();
    res.headers.set('Cache-Control', 'no-store');
    res.headers.set('X-Content-Type-Options', 'nosniff');
    return res;
}
catch (e) {
    if (!(e instanceof ApiError))
        console.error('Health API error', e);
    return Response.json({ error: e instanceof ApiError ? e.message : 'The service is temporarily unavailable. Your input is preserved; please try again.' }, { status: e instanceof ApiError ? e.status : 503, headers: { 'Cache-Control': 'no-store' } });
} }
