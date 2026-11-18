"""Offline presentation of actual experimental evidence, with escaped diagnostics."""

from html import escape
import json
import os
from pathlib import Path
from urllib.parse import quote

from verified_updates.storage import atomic_write


LABELS = {
    "genuine_release_v1": "Install the first authorized release",
    "artifact_substitution": "Replace the downloadable application",
    "genuine_release_v2_after_rejection": "Recover with the genuine update",
    "metadata_rollback_after_process_restart": "Replay an older repository publication",
    "correctly_signed_expired_metadata": "Serve correctly signed, expired metadata",
    "insufficient_targets_signatures": "Authorize a release with only one signer",
    "inconsistent_snapshot": "Mix inconsistent repository metadata",
    "authorized_release_key_rotation": "Rotate a release key and publish again",
    "interrupted_activation": "Interrupt the updater before activation",
    "recovery_after_interruption": "Resume after the interrupted installation",
    "application_self_test_failure": "Deliver an authorized application that fails its self-test",
    "genuine_release": "Genuine release",
    "file_and_unsigned_checksum_replacement": "Replace the file and its unsigned checksum",
    "replay_previously_signed_release": "Replay a previously signed release",
}

STYLE = """
:root{--paper:#f5f5f0;--surface:#fff;--ink:#1b2b34;--muted:#52636b;--line:#cdd6d8;--blue:#155e7a;--soft:#edf2f3;--green:#1b6245;--green-bg:#e8f2eb;--red:#92382e;--red-bg:#f8eae7}
*{box-sizing:border-box}html{scroll-behavior:smooth;scroll-padding-top:28px}body{margin:0;background:var(--paper);color:var(--ink);font:16px/1.6 'Segoe UI',Arial,sans-serif}::selection{background:#c9e2ed;color:var(--ink)}a{color:var(--blue);text-underline-offset:4px}a:hover{text-decoration-thickness:2px}:focus-visible{outline:3px solid var(--blue);outline-offset:5px}button,summary{cursor:pointer}button{font:inherit}button:disabled{cursor:default;opacity:.55}header{border-bottom:1px solid var(--line);background:var(--surface)}.header-inner{max-width:1232px;margin:auto;min-height:78px;padding:18px 32px;display:flex;align-items:center;justify-content:space-between;gap:24px}.brand{font-size:20px;font-weight:650;letter-spacing:-.5px}.brand span{font-weight:400;color:var(--muted);padding-left:16px;margin-left:16px;border-left:1px solid var(--line)}nav{display:flex;gap:24px;font-size:14px}main{max-width:1232px;margin:auto;padding:54px 32px 70px}.intro{display:flex;gap:36px;align-items:flex-end;justify-content:space-between;margin-bottom:32px}h1{font-size:clamp(32px,4vw,48px);line-height:1.12;letter-spacing:-1.4px;font-weight:650;margin:0 0 18px;text-wrap:balance}h2{font-size:25px;line-height:1.3;letter-spacing:-.5px;margin:0 0 10px}p{margin:0;max-width:73ch}.intro p,.section-copy{color:var(--muted)}.action{white-space:nowrap;display:inline-block;border:1px solid var(--line);border-radius:4px;background:var(--surface);padding:11px 18px;font-size:14px;font-weight:600;text-decoration:none;transition:background .15s}.action:hover{background:var(--soft)}.verdict{display:flex;justify-content:space-between;gap:24px;align-items:center;padding:19px 24px;background:var(--green-bg);color:var(--green);border:1px solid #b9d2c2;border-radius:4px;margin:0 0 48px}.verdict.bad{color:var(--red);background:var(--red-bg);border-color:#dfbbb5}.verdict strong{font-size:18px}.verdict small{font-size:14px}.section-header{display:flex;justify-content:space-between;gap:24px;align-items:flex-end;margin-bottom:22px}.section-copy{font-size:15px}.filters{display:flex;gap:8px;flex-shrink:0}.filters button{border:1px solid var(--line);background:transparent;color:var(--muted);padding:10px 14px;min-height:44px;border-radius:4px;font-size:14px}.filters button[aria-pressed=true]{background:var(--ink);color:#fff;border-color:var(--ink)}.scenario{border-top:1px solid var(--line);background:var(--surface)}.scenario:last-child{border-bottom:1px solid var(--line)}summary{list-style:none;display:grid;grid-template-columns:minmax(0,1fr) 190px 110px 105px;align-items:center;gap:20px;padding:20px 22px;min-height:88px;transition:background .15s}summary::-webkit-details-marker{display:none}summary:hover,.scenario[open] summary{background:var(--soft)}.case-name{font-weight:600;font-size:16px;line-height:1.4}.observed{font-size:14px;color:var(--muted)}.observed strong{display:block;color:var(--ink);font-weight:600}.sequence{font-size:14px;font-variant-numeric:tabular-nums;color:var(--muted)}.inspect{font-size:13px;color:var(--blue);text-decoration:underline;text-underline-offset:3px}.pass-label{display:block;font-size:12px;letter-spacing:.25px;color:var(--green);margin-bottom:5px}.pass-label.bad{color:var(--red)}.evidence{padding:0 22px 24px}.evidence p{font-size:14px;color:var(--muted);margin:5px 0 14px}pre{margin:0;background:#f0f3f3;border:1px solid var(--line);padding:20px;border-radius:3px;color:var(--ink);font:13px/1.65 Consolas,'Courier New',monospace;white-space:pre-wrap;overflow-wrap:anywhere;word-break:break-word}.scenario[hidden]{display:none}section+section{margin-top:52px}.table-wrap{overflow:auto;border:1px solid var(--line);border-radius:4px;background:var(--surface);margin-top:22px}table{border-collapse:collapse;width:100%;font-size:14px;text-align:left}th,td{padding:17px 20px;border-bottom:1px solid var(--line);vertical-align:top}thead th{background:var(--soft);font-weight:600}tbody tr:last-child>*{border-bottom:0}tbody th{font-weight:500;min-width:220px}.decision{font-weight:600;white-space:nowrap}.good{color:var(--green)}.unsafe{color:var(--red)}.table-note{font-size:13px;color:var(--muted);margin-top:12px}.lower{display:grid;grid-template-columns:1fr 1fr;gap:48px;border-top:1px solid var(--line);padding-top:36px}.lower pre{margin-top:20px}.lower ul{margin:18px 0 0;padding-left:20px;font-size:14px;color:var(--muted)}.lower li+li{margin-top:12px}footer{margin-top:48px;border-top:1px solid var(--line);padding-top:20px;color:var(--muted);font-size:13px;overflow-wrap:anywhere}.skip{position:absolute;top:-100px;left:20px}.skip:focus{top:10px;padding:8px;background:white;z-index:2}.empty{padding:24px;background:var(--surface);border:1px solid var(--line)}
@media(max-width:850px){.header-inner{padding:16px 24px}.brand span{display:none}nav{gap:18px}main{padding:36px 24px}.intro{display:block}.intro .action{margin-top:22px}.section-header{display:block}.filters{margin-top:18px}.verdict{align-items:flex-start;flex-direction:column;gap:6px;margin-bottom:36px}summary{grid-template-columns:minmax(0,1fr) 150px;gap:10px 18px}.sequence{grid-column:1}.inspect{grid-column:2}.lower{grid-template-columns:1fr;gap:32px}}
@media(max-width:480px){.header-inner{padding:14px 18px;min-height:68px}.brand{font-size:18px}nav{gap:14px;font-size:13px}nav a:last-child{display:none}main{padding:32px 18px 44px}h1{letter-spacing:-1px}summary{padding:18px 16px;grid-template-columns:minmax(0,1fr) 116px;gap:12px}.case-name{font-size:14px}.observed{font-size:12px}.sequence{font-size:12px}.inspect{font-size:12px}.evidence{padding:0 16px 18px}pre{padding:14px;font-size:12px}.verdict{padding:17px}.verdict strong{font-size:16px}.section-copy{font-size:14px}.filters{flex-wrap:wrap}th,td{padding:14px}tbody th{min-width:180px}}
@media(max-width:600px){table{table-layout:fixed;font-size:12px;line-height:1.5}th,td{padding:13px 7px;overflow-wrap:anywhere}thead th:first-child{width:40%}tbody th{min-width:0}.decision{white-space:normal}}
@media(prefers-reduced-motion:reduce){html{scroll-behavior:auto}*{transition:none!important}}
@media print{header nav,.filters,.action,.inspect{display:none}body{background:#fff}main{padding:20px}.scenario{break-inside:avoid}.evidence{display:block}summary{grid-template-columns:1fr 160px 90px}.lower{display:block}.lower>div+div{margin-top:30px}}
"""


def _text(value) -> str:
    return escape(str(value), quote=True)


def render_report(report: dict, destination: Path, *, source: Path | None = None) -> None:
    source = (source or destination.with_name("report.json")).resolve()
    try:
        evidence_url = quote(Path(os.path.relpath(source, destination.resolve().parent)).as_posix())
    except ValueError:
        evidence_url = source.as_uri()
    cases = report.get("cases", [])
    failures = sum(not case.get("passed", False) for case in cases)
    passed = len(cases) - failures
    comparison = report.get("comparison", [])
    all_passed = bool(cases) and failures == 0 and all(row.get("passed", False) for row in comparison)
    verdict = "All expected outcomes observed" if all_passed else "Some outcomes need investigation"
    rows = []
    for case in cases:
        actual = case.get("actual", {})
        outcome = actual.get("outcome", "interrupted" if case.get("scenario") == "interrupted_activation" else "unknown")
        outcome_label = {"updated": "Update installed", "up_to_date": "Already current", "rejected": "Update rejected", "failed": "Operation failed", "interrupted": "Process interrupted"}.get(outcome, outcome)
        before, after = actual.get("installed_before"), actual.get("installed_after")
        sequence = f"{before if before is not None else 'None'} → {after if after is not None else 'None'}"
        status = "Expected outcome" if case.get("passed") else "Needs investigation"
        css = "" if case.get("passed") else "bad"
        rows.append(f'''<details class="scenario" data-passed="{str(bool(case.get('passed'))).lower()}">
<summary><span class="case-name">{_text(LABELS.get(case.get('scenario'), case.get('scenario', 'Unnamed scenario')))}</span>
<span class="observed"><span class="pass-label {css}">{status}</span><strong>{_text(outcome_label)}</strong></span>
<span class="sequence" aria-label="Installed release sequence before and after">{_text(sequence)}</span><span class="inspect">Inspect evidence</span></summary>
<div class="evidence"><p>The record below contains the observed result and the expected outcome for this experiment.</p><pre>{_text(json.dumps(case, indent=2))}</pre></div></details>''')
    comparisons = []
    for row in comparison:
        decisions = []
        for key in ("unsigned_checksum", "signature_only", "tuf"):
            accepted = row[key]["accepted"]
            desired = row["scenario"] == "genuine_release"
            decisions.append(f'<td><span class="decision {"good" if accepted == desired else "unsafe"}">{"Accepted" if accepted else "Rejected"}</span></td>')
        comparisons.append(f'<tr><th scope="row">{_text(LABELS.get(row["scenario"], row["scenario"]))}</th>{"".join(decisions)}</tr>')
    notes = "".join(f"<li>{_text(note)}</li>" for note in report.get("notes", []))
    body = f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; base-uri 'none'; form-action 'none'">
<title>Verified Updates · Verification report</title><style>{STYLE}</style></head><body>
<a class="skip" href="#experiments">Skip to experiments</a>
<header><div class="header-inner"><div class="brand">Verified Updates<span>Evidence record</span></div><nav aria-label="Report sections"><a href="#experiments">Experiments</a><a href="#comparison">Comparison</a><a href="#boundaries">Boundaries</a></nav></div></header>
<main><div class="intro"><div><h1>Update verification report</h1><p>A recorded experiment in software distribution under repository compromise. Every result comes from the actual updater and a local HTTP repository.</p></div><a class="action" href="{_text(evidence_url)}">Open JSON record</a></div>
<div class="verdict {'' if all_passed else 'bad'}"><strong>{verdict}</strong><small>{passed} of {len(cases)} scenarios matched expectations · {len(comparison)} comparison cases</small></div>
<section id="experiments" aria-labelledby="experiments-title"><div class="section-header"><div><h2 id="experiments-title">What happened at the client</h2><p class="section-copy">Inspect a scenario to see its exact decision, failure reason, and installed release sequence.</p></div><div class="filters" aria-label="Filter experiments"><button id="all" type="button" aria-pressed="true">All experiments</button><button id="attention" type="button" aria-pressed="false" {'disabled' if not failures else ''}>Needs attention ({failures})</button></div></div>
{''.join(rows) if rows else '<p class="empty">No experiment records are available in this report.</p>'}</section>
<section id="comparison" aria-labelledby="comparison-title"><h2 id="comparison-title">Why a signature alone is insufficient</h2><p class="section-copy">Compare artifact acceptance using the same release data and attack classes.</p><div class="table-wrap"><table><thead><tr><th scope="col">Experiment</th><th scope="col">Unsigned checksum</th><th scope="col">Signature only</th><th scope="col">TUF client</th></tr></thead><tbody>{''.join(comparisons)}</tbody></table></div><p class="table-note">The comparison clients evaluate artifact acceptance. The TUF outcomes reference the complete update runs above. An accepted obsolete release exposes a missing freshness policy.</p></section>
<section class="lower"><div><h2>The installed application still runs</h2><p class="section-copy">Output captured from the last working CSV Inspector after the installation failure.</p><pre>{_text(json.dumps(report.get('installed_application_output', {}), indent=2))}</pre></div><div id="boundaries"><h2>Read the evidence within its boundaries</h2><p class="section-copy">These are reproducible local experiments, with the following setup and implementation limits.</p><ul>{notes}</ul></div></section>
<footer>Run directory: {_text(report.get('directory', 'Not recorded'))}<br>Reproduce from the project directory: <code>python -m verified_updates demo</code></footer></main>
<script>const all=document.getElementById('all');const attention=document.getElementById('attention');function filter(onlyAttention){{document.querySelectorAll('.scenario').forEach(row=>{{row.hidden=onlyAttention&&row.dataset.passed==='true';}});all.setAttribute('aria-pressed',String(!onlyAttention));attention.setAttribute('aria-pressed',String(onlyAttention));}}all.addEventListener('click',()=>filter(false));attention.addEventListener('click',()=>filter(true));</script></body></html>'''
    atomic_write(destination, body.encode("utf-8"))

