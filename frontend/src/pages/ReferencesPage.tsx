import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import type { Reference } from "../types";

export function ReferencesPage() {
  const [refs, setRefs] = useState<Reference[]>([]);
  const [err, setErr] = useState("");
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);
  const [open, setOpen] = useState(false);

  const [id, setId] = useState("");
  const [name, setName] = useState("");
  const [kind, setKind] = useState("PCB");
  const [mode, setMode] = useState<"regions" | "surface">("regions");
  const [regions, setRegions] = useState("[]");
  const [mmPerPx, setMmPerPx] = useState("");
  const [activate, setActivate] = useState(true);
  const fileRef = useRef<HTMLInputElement>(null);

  const [capOpen, setCapOpen] = useState(false);
  const [capId, setCapId] = useState("MY_OBJECT");
  const [capName, setCapName] = useState("My object");
  const [capSource, setCapSource] = useState("0");
  const [capKind, setCapKind] = useState("GENERIC");
  const [capMode, setCapMode] = useState<"surface" | "regions">("surface");

  const capture = async () => {
    setErr("");
    setMsg("");
    setBusy(true);
    try {
      const r = await api.captureReference({
        id: capId,
        name: capName,
        source: capSource.trim(),
        kind: capKind,
        inspection_mode: capMode,
        activate: true,
      });
      setMsg(
        capMode === "surface"
          ? `Captured ${r.id} and set active. Point the camera at the same object — a ` +
            `clean one reads GOOD, a damaged / scribbled / wrong one reads DEFECTIVE.`
          : `Captured ${r.id} and set active. Now add component regions (Regions JSON below).`,
      );
      setCapOpen(false);
      load();
    } catch (e) {
      setErr(String((e as Error).message ?? e));
    } finally {
      setBusy(false);
    }
  };

  const load = () =>
    api.listReferences().then(setRefs).catch((e) => setErr(String(e.message ?? e)));

  useEffect(() => {
    load();
  }, []);

  const submit = async () => {
    setErr("");
    setMsg("");
    const f = fileRef.current?.files?.[0];
    if (!f) return setErr("Choose a known-good image file.");
    try {
      JSON.parse(regions || "[]");
    } catch {
      return setErr("Regions must be valid JSON (an array).");
    }
    const form = new FormData();
    form.append("file", f);
    form.append("id", id);
    form.append("name", name);
    form.append("kind", kind);
    form.append("inspection_mode", mode);
    form.append("regions", regions || "[]");
    if (mmPerPx) form.append("mm_per_px", mmPerPx);
    form.append("activate", String(activate));

    setBusy(true);
    try {
      const r = await api.createReference(form);
      setMsg(`Created ${r.id}${r.active ? " (active)" : ""}.`);
      setOpen(false);
      setId("");
      setName("");
      setRegions("[]");
      setMmPerPx("");
      load();
    } catch (e) {
      setErr(String((e as Error).message ?? e));
    } finally {
      setBusy(false);
    }
  };

  const activateRef = async (rid: string) => {
    await api.activateReference(rid);
    load();
  };
  const remove = async (rid: string) => {
    if (!confirm(`Delete reference ${rid}? This cannot be undone.`)) return;
    await api.deleteReference(rid);
    load();
  };

  return (
    <>
      <h1 className="page-title">References</h1>
      <p className="page-sub">
        Known-good boards. One reference is <em>active</em> and used by default for
        inspection. Region &amp; tolerance definitions live in each reference's{" "}
        <code>regions.json</code>.
      </p>

      <div className="row" style={{ marginBottom: 16 }}>
        <button className="btn" onClick={() => setOpen((v) => !v)}>
          {open ? "Cancel" : "Add reference (upload)"}
        </button>
        <button className="btn secondary" onClick={() => setCapOpen((v) => !v)}>
          {capOpen ? "Cancel" : "Capture from camera"}
        </button>
      </div>

      {msg && <div className="notice info" style={{ marginBottom: 12 }}>{msg}</div>}
      {err && <div className="notice err" style={{ marginBottom: 12 }}>{err}</div>}

      {capOpen && (
        <div className="panel stack" style={{ marginBottom: 18 }}>
          <p className="muted" style={{ fontSize: 12, margin: 0 }}>
            Point the camera at a <strong>known-good</strong> object — steady, in
            focus, even lighting, roughly centred. This snapshot becomes the
            reference; inspect through the same camera so you compare like with like.
          </p>
          <div className="row">
            <label className="field">
              Identifier
              <input type="text" value={capId} onChange={(e) => setCapId(e.target.value)} />
            </label>
            <label className="field">
              Name
              <input type="text" value={capName} onChange={(e) => setCapName(e.target.value)} />
            </label>
            <label className="field">
              Mode
              <select value={capMode} onChange={(e) => setCapMode(e.target.value as "surface" | "regions")}>
                <option value="surface">Whole surface (clean vs damaged)</option>
                <option value="regions">Component regions</option>
              </select>
            </label>
            <label className="field">
              Kind
              <select value={capKind} onChange={(e) => setCapKind(e.target.value)}>
                <option>GENERIC</option>
                <option>PCB</option>
                <option>BOX</option>
              </select>
            </label>
            <label className="field" style={{ minWidth: 200 }}>
              Camera (index or stream URL)
              <input type="text" value={capSource} onChange={(e) => setCapSource(e.target.value)} />
            </label>
          </div>
          {capSource.trim() && (
            <div className="image-frame" style={{ maxWidth: 420 }}>
              <img src={api.cameraPreviewUrl(capSource.trim())} alt="camera" />
            </div>
          )}
          <div>
            <button className="btn" disabled={busy || !capId || !capName} onClick={capture}>
              {busy ? <span className="spinner" /> : "Capture reference"}
            </button>
          </div>
        </div>
      )}

      {open && (
        <div className="panel stack" style={{ marginBottom: 18 }}>
          <div className="row">
            <label className="field">
              Identifier
              <input
                type="text"
                value={id}
                placeholder="PCB_MODEL_002"
                onChange={(e) => setId(e.target.value)}
              />
            </label>
            <label className="field">
              Name
              <input
                type="text"
                value={name}
                placeholder="Demo PCB Model 002"
                onChange={(e) => setName(e.target.value)}
              />
            </label>
            <label className="field">
              Mode
              <select value={mode} onChange={(e) => setMode(e.target.value as "regions" | "surface")}>
                <option value="regions">Component regions</option>
                <option value="surface">Whole surface (clean vs damaged)</option>
              </select>
            </label>
            <label className="field">
              Kind
              <select value={kind} onChange={(e) => setKind(e.target.value)}>
                <option>PCB</option>
                <option>BOX</option>
                <option>GENERIC</option>
              </select>
            </label>
            <label className="field">
              mm / px (optional)
              <input
                type="number"
                step="0.001"
                value={mmPerPx}
                onChange={(e) => setMmPerPx(e.target.value)}
              />
            </label>
          </div>
          <label className="field">
            Known-good image
            <input ref={fileRef} type="file" accept="image/*" />
          </label>
          {mode === "surface" && (
            <p className="muted" style={{ fontSize: 12, margin: 0 }}>
              Whole-surface mode: no regions needed. A clean object reads GOOD; a
              damaged / scribbled / wrong / dirty one reads DEFECTIVE. Inspect the
              same object type through the same camera.
            </p>
          )}
          <label className="field" hidden={mode === "surface"}>
            Regions JSON (optional — array of{" "}
            <code>{'{ name, bbox:[x,y,w,h], tolerances }'}</code>)
            <textarea
              value={regions}
              onChange={(e) => setRegions(e.target.value)}
              rows={5}
              style={{
                background: "var(--panel-2)",
                color: "var(--text)",
                border: "1px solid var(--border)",
                borderRadius: 7,
                fontFamily: "var(--mono)",
                fontSize: 12,
                padding: 10,
              }}
            />
          </label>
          <label className="row" style={{ gap: 8 }}>
            <input
              type="checkbox"
              checked={activate}
              onChange={(e) => setActivate(e.target.checked)}
            />
            Mark as active reference
          </label>
          <div>
            <button className="btn" disabled={busy || !id || !name} onClick={submit}>
              {busy ? <span className="spinner" /> : "Create reference"}
            </button>
          </div>
        </div>
      )}

      <div className="panel table-wrap" style={{ padding: 0 }}>
        <table>
          <thead>
            <tr>
              <th className="mono">ID</th>
              <th>Name</th>
              <th>Kind</th>
              <th>Mode</th>
              <th>Regions</th>
              <th>Created</th>
              <th>Active</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {refs.map((r) => (
              <tr key={r.id} style={{ cursor: "default" }}>
                <td className="mono">{r.id}</td>
                <td>{r.name}</td>
                <td><span className={"pill " + r.kind}>{r.kind}</span></td>
                <td>{r.inspection_mode === "surface" ? "surface" : "regions"}</td>
                <td>{r.inspection_mode === "surface" ? "—" : r.regions.length}</td>
                <td>{new Date(r.created_at).toLocaleDateString()}</td>
                <td>{r.active ? <span className="badge GOOD">ACTIVE</span> : ""}</td>
                <td style={{ textAlign: "right" }}>
                  {!r.active && (
                    <button
                      className="btn secondary"
                      onClick={() => activateRef(r.id)}
                      style={{ marginRight: 8 }}
                    >
                      Activate
                    </button>
                  )}
                  <button className="btn danger" onClick={() => remove(r.id)}>
                    Delete
                  </button>
                </td>
              </tr>
            ))}
            {refs.length === 0 && (
              <tr>
                <td colSpan={8} className="muted" style={{ padding: 20 }}>
                  No references yet. Run{" "}
                  <code>py scripts/make_synthetic_pcb.py</code> or add one above.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </>
  );
}
