import { actors, access, ApiError, body, bucket, context, db, field, getRecord, logStmt, now, patient, route, safeRecord, seed, stmt, tenant, type RecordRow } from '@/lib/health-server';
export const dynamic = 'force-dynamic';
async function handle(req: Request) {
    return route(req, async () => {
        const parts = new URL(req.url).pathname.slice(5).split('/').map(decodeURIComponent), [resource, id, sub] = parts, m = req.method;
        if (resource === 'session') {
            if (m === 'GET') {
                try {
                    const c = await context(req);
                    return Response.json({ actor: c.actor, actors });
                }
                catch (e) {
                    if (e instanceof ApiError && e.status === 401)
                        return Response.json({ actor: null, actors });
                    throw e;
                }
            }
            if (m === 'POST') {
                const t = await tenant(req), b = await body(req), actor = actors.find(x => x.id === b.actor);
                if (!actor)
                    throw new ApiError(400, 'Please select a valid demo role.');
                await seed(t);
                const sid = crypto.randomUUID();
                await stmt('DELETE FROM sessions WHERE tenant=? AND expires<?', t, now()).run();
                await stmt('INSERT INTO sessions(id,tenant,actor,expires) VALUES(?,?,?,?)', sid, t, actor.id, new Date(Date.now() + 86400000).toISOString()).run();
                return Response.json({ actor, actors }, { headers: { 'Set-Cookie': `health_session=${sid}; HttpOnly; SameSite=Strict; Path=/; Max-Age=86400${new URL(req.url).protocol === 'https:' ? '; Secure' : ''}` } });
            }
        }
        const c = await context(req);
        if (resource === 'records' && !id) {
            if (m === 'GET') {
                const rows = c.actor.role === 'patient' ? await stmt('SELECT * FROM records WHERE tenant=? AND owner=? ORDER BY date DESC,created DESC', c.tenant, c.actor.id).all<RecordRow>() : await stmt('SELECT r.* FROM records r WHERE r.tenant=? AND EXISTS (SELECT 1 FROM grants g WHERE g.record_id=r.id AND g.tenant=r.tenant AND g.doctor=? AND g.revoked IS NULL AND g.expires>?) ORDER BY r.date DESC', c.tenant, c.actor.id, now()).all<RecordRow>();
                return Response.json({ records: rows.results.map(r => ({ ...safeRecord(r), summary: undefined })) });
            }
            if (m === 'POST') {
                patient(c);
                const b = await body(req);
                const title = field(b.title, 'Title', 100), summary = field(b.summary, 'Record content', 8000), source = field(b.source, 'Source', 120), date = field(b.date, 'Date', 10), kind = field(b.kind, 'Type', 30);
                if (!/^\d{4}-\d{2}-\d{2}$/.test(date) || isNaN(Date.parse(date)))
                    throw new ApiError(400, 'Invalid record date.');
                if (!['Lab report', 'Check-up', 'Medication', 'Other'].includes(kind))
                    throw new ApiError(400, 'Invalid record type.');
                const rid = crypto.randomUUID(), time = now();
                await db().batch([stmt('INSERT INTO records(id,tenant,owner,title,kind,date,source,summary,version,created,updated) VALUES(?,?,?,?,?,?,?,?,1,?,?)', rid, c.tenant, c.actor.id, title, kind, date, source, summary, time, time), stmt('INSERT INTO versions(id,record_id,tenant,version,title,summary,actor,created) VALUES(?,?,?,1,?,?,?,?)', crypto.randomUUID(), rid, c.tenant, title, summary, c.actor.id, time), logStmt(c, { id: rid, owner: c.actor.id, title }, 'Create record')]);
                return Response.json({ id: rid }, { status: 201 });
            }
        }
        if (resource === 'records' && id) {
            const r = await getRecord(c, id);
            if (sub === 'file') {
                if (m === 'GET') {
                    await access(c, r, 'Read attachment');
                    if (!r.file_key)
                        throw new ApiError(404, 'No attachment found.');
                    const file = await bucket().get(r.file_key);
                    if (!file)
                        throw new ApiError(404, 'The attachment is unavailable.');
                    await logStmt(c, r, 'Read attachment').run();
                    return new Response(file.body, { headers: { 'Content-Type': r.file_type || 'application/octet-stream', 'Content-Disposition': `attachment; filename="report"; filename*=UTF-8''${encodeURIComponent(r.file_name || 'report')}`, 'Content-Security-Policy': 'sandbox' } });
                }
                if (m === 'POST') {
                    patient(c);
                    if (r.owner !== c.actor.id)
                        throw new ApiError(403, 'You can only upload to your own records.');
                    if (r.file_key)
                        throw new ApiError(409, 'An attachment already exists. Add another record to save a different file.');
                    if (Number(req.headers.get('content-length') || 0) > 5500000)
                        throw new ApiError(413, 'Attachments must not exceed 5 MB.');
                    const form = await req.formData(), file = form.get('file');
                    if (!(file instanceof File) || !file.size || file.size > 5242880)
                        throw new ApiError(400, 'Choose a PDF, PNG or JPG of up to 5 MB.');
                    const bytes = new Uint8Array(await file.arrayBuffer());
                    let mime = '';
                    if (bytes[0] === 37 && bytes[1] === 80 && bytes[2] === 68 && bytes[3] === 70)
                        mime = 'application/pdf';
                    if (bytes[0] === 137 && bytes[1] === 80 && bytes[2] === 78 && bytes[3] === 71)
                        mime = 'image/png';
                    if (bytes[0] === 255 && bytes[1] === 216 && bytes[2] === 255)
                        mime = 'image/jpeg';
                    if (!mime)
                        throw new ApiError(400, 'Only PDF, PNG and JPG files are supported.');
                    const key = crypto.randomUUID();
                    await bucket().put(key, bytes, { httpMetadata: { contentType: mime } });
                    try {
                        const res = await db().batch([stmt('UPDATE records SET file_key=?,file_name=?,file_type=?,file_size=? WHERE id=? AND tenant=? AND owner=? AND file_key IS NULL', key, file.name.slice(0, 180), mime, file.size, r.id, c.tenant, c.actor.id), logStmt(c, r, 'Upload attachment')]);
                        if (!res[0].meta.changes)
                            throw new ApiError(409, 'An attachment already exists. Please refresh.');
                    }
                    catch (e) {
                        await bucket().delete(key);
                        throw e;
                    }
                    return Response.json({ ok: true });
                }
            }
            if (!sub && m === 'GET') {
                await access(c, r, 'View report');
                await logStmt(c, r, 'View report').run();
                const history = c.actor.id === r.owner ? (await stmt('SELECT version,title,summary,actor,created FROM versions WHERE tenant=? AND record_id=? ORDER BY version DESC', c.tenant, r.id).all()).results : [];
                return Response.json({ record: safeRecord(r), history });
            }
            if (!sub && m === 'PATCH') {
                patient(c);
                if (r.owner !== c.actor.id)
                    throw new ApiError(403, 'You can only edit your own records.');
                const b = await body(req), title = field(b.title, 'Title', 100), summary = field(b.summary, 'Content', 8000);
                if (!Number.isInteger(b.version) || b.version !== r.version)
                    throw new ApiError(409, 'This record has changed. Reopen it before editing.');
                const time = now();
                const res = await db().batch([stmt('UPDATE records SET title=?,summary=?,version=version+1,updated=? WHERE id=? AND tenant=? AND owner=? AND version=?', title, summary, time, r.id, c.tenant, c.actor.id, b.version), stmt('INSERT INTO versions(id,record_id,tenant,version,title,summary,actor,created) SELECT ?,id,tenant,version,title,summary,?,updated FROM records WHERE id=? AND tenant=? AND changes()=1', crypto.randomUUID(), c.actor.id, r.id, c.tenant), stmt('INSERT INTO logs(id,tenant,owner,actor,record_id,title,action,result,created) SELECT ?,tenant,owner,?,id,title,?,?,? FROM records WHERE id=? AND tenant=? AND changes()=1', crypto.randomUUID(), c.actor.id, 'Edit record', 'success', time, r.id, c.tenant)]);
                if (!res[0].meta.changes)
                    throw new ApiError(409, 'This record has changed. Reopen it before editing.');
                return Response.json({ ok: true });
            }
        }
        if (resource === 'grants') {
            if (m === 'GET') {
                const predicate = c.actor.role === 'patient' ? 'g.owner=?' : 'g.doctor=?';
                const rows = await stmt(`SELECT g.*,r.title FROM grants g JOIN records r ON r.id=g.record_id AND r.tenant=g.tenant WHERE g.tenant=? AND ${predicate} ORDER BY g.created DESC`, c.tenant, c.actor.id).all();
                return Response.json({ grants: rows.results.map(({ tenant, ...g }) => { void tenant; return g; }) });
            }
            if (m === 'POST') {
                patient(c);
                const b = await body(req), doctor = actors.find(x => x.id === b.doctor && x.role === 'doctor'), minutes = Number(b.minutes);
                if (!doctor)
                    throw new ApiError(400, 'Please select a doctor.');
                if (![1, 60, 1440, 2880, 10080].includes(minutes))
                    throw new ApiError(400, 'Please choose a valid access duration.');
                if (!Array.isArray(b.records) || !b.records.length || b.records.length > 20 || b.records.some((x: unknown) => typeof x !== 'string'))
                    throw new ApiError(400, 'Choose between 1 and 20 reports.');
                const ids = [...new Set(b.records)] as string[], rs = await Promise.all(ids.map(x => getRecord(c, x)));
                if (rs.some(r => r.owner !== c.actor.id))
                    throw new ApiError(403, 'You can only share your own records.');
                const time = now(), expires = new Date(Date.now() + minutes * 60000).toISOString();
                await db().batch(rs.flatMap(r => [stmt('UPDATE grants SET revoked=? WHERE tenant=? AND owner=? AND doctor=? AND record_id=? AND revoked IS NULL', time, c.tenant, c.actor.id, doctor.id, r.id), stmt('INSERT INTO grants(id,tenant,owner,doctor,record_id,expires,created) VALUES(?,?,?,?,?,?,?)', crypto.randomUUID(), c.tenant, c.actor.id, doctor.id, r.id, expires, time), logStmt(c, r, 'Grant access to ' + doctor.label)]));
                return Response.json({ ok: true }, { status: 201 });
            }
            if (m === 'DELETE') {
                patient(c);
                const b = await body(req), g = await stmt('SELECT g.*,r.title FROM grants g JOIN records r ON r.id=g.record_id WHERE g.id=? AND g.tenant=? AND g.owner=?', String(b.id), c.tenant, c.actor.id).first<{
                    id: string;
                    record_id: string;
                    owner: string;
                    title: string;
                }>();
                if (!g)
                    throw new ApiError(404, 'Permission not found.');
                await db().batch([stmt('UPDATE grants SET revoked=? WHERE id=? AND tenant=? AND owner=? AND revoked IS NULL', now(), g.id, c.tenant, c.actor.id), logStmt(c, { id: g.record_id, owner: g.owner, title: g.title }, 'Revoke access')]);
                return Response.json({ ok: true });
            }
        }
        if (resource === 'logs' && m === 'GET') {
            const predicate = c.actor.role === 'patient' ? 'owner=?' : 'actor=?';
            const rows = await stmt(`SELECT id,actor,record_id,title,action,result,created FROM logs WHERE tenant=? AND ${predicate} ORDER BY created DESC LIMIT 150`, c.tenant, c.actor.id).all();
            return Response.json({ logs: rows.results });
        }
        throw new ApiError(404, 'Endpoint not found.');
    });
}
export const GET = handle, POST = handle, PATCH = handle, DELETE = handle;
