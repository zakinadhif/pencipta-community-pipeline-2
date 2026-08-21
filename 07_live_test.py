import marimo

__generated_with = "0.24.0"
app = marimo.App(width="full", app_title="Live Pipeline Test")


@app.cell
def _():
    import json
    import os
    import time
    from pathlib import Path

    import marimo as mo
    from dotenv import load_dotenv

    from src.evaluation.reporting import per_requester_tokens, per_run_tokens
    from src.pipeline import Pipeline, PipelineConfig
    from src.tracing.storage import ExperimentStore

    workspace = Path(__file__).parent
    load_dotenv(workspace / ".env")
    profiles = json.loads((workspace / "data" / "synthetic_profiles.json").read_text(encoding="utf-8"))
    eval_queries = json.loads((workspace / "data" / "eval_queries.json").read_text(encoding="utf-8"))
    store = ExperimentStore(workspace / "data" / "runs.duckdb")
    return (
        Pipeline,
        PipelineConfig,
        eval_queries,
        mo,
        os,
        per_requester_tokens,
        per_run_tokens,
        profiles,
        store,
        time,
    )


@app.cell
def _(mo):
    mo.md("""
    # 07 — Live pipeline test

    Jalankan pipeline end-to-end terhadap query yang kamu ketik sendiri, atau
    terhadap semua eval query. Hasil match, retrieval, dan konsumsi token
    per-run + per-requester dibaca dari DuckDB.

    **Alur:** query (input kamu) -> Need Interpreter -> retrieval (lexical jika
    tidak ada embeddings) -> prescore -> match judge -> introduction -> semua
    disimpan ke `data/runs.duckdb`.

    - Tanpa embeddings -> retrieval memakai lexical fallback otomatis.
    - Streaming SDK diblokir -> fallback non-stream (HTTP langsung).
    - Output model yang tidak mengikuti schema -> dinormalisasi adaptif.
    """)
    return


@app.cell
def _(mo):
    db_table_select = mo.ui.dropdown(
        label="Pilih Data / Tabel untuk Ditampilkan",
        options=[
            "Ringkasan Statistik Database",
            "Data Profil Komunitas (2.000 profil)",
            "Riwayat Pipeline Runs (DuckDB)",
            "Riwayat Panggilan LLM (DuckDB)",
            "Riwayat Hasil Match (DuckDB)",
        ],
        value="Ringkasan Statistik Database",
    )
    db_search = mo.ui.text(
        label="Filter / Cari Data",
        placeholder="Ketik kata kunci nama, lokasi, keahlian, atau query...",
    )
    db_refresh = mo.ui.run_button(label="Refresh Tampilan DB")
    clear_confirm = mo.ui.checkbox(label="Konfirmasi bersihkan data runs DuckDB")
    clear_runs_btn = mo.ui.run_button(label="Bersihkan Riwayat Runs", kind="danger")

    mo.accordion({
        "Database Explorer dan Manajemen Data": mo.vstack([
            mo.hstack([db_table_select, db_search, db_refresh], justify="start"),
            mo.hstack([clear_confirm, clear_runs_btn], justify="start"),
        ])
    })
    return clear_confirm, clear_runs_btn, db_refresh, db_search, db_table_select


@app.cell
def _(clear_confirm, clear_runs_btn, db_refresh, db_search, db_table_select, mo, profiles, store):
    _ = db_refresh.value
    msg = None
    if clear_runs_btn.value:
        if clear_confirm.value:
            with store._connection() as con:
                con.execute("delete from runs; delete from llm_calls; delete from retrieval_results; delete from match_results; delete from human_evaluations;")
            msg = mo.callout("Riwayat runs di DuckDB telah berhasil dibersihkan.", kind="success")
        else:
            msg = mo.callout("Centang kotak konfirmasi terlebih dahulu sebelum menekan tombol Bersihkan Riwayat Runs.", kind="warn")

    selected_view = db_table_select.value
    search_keyword = db_search.value.strip().lower()

    if selected_view == "Ringkasan Statistik Database":
        runs_df = store.dataframe("select count(*) as cnt, coalesce(sum(estimated_cost_usd), 0) as total_cost, coalesce(avg(total_latency_ms), 0) as avg_latency from runs")
        calls_df = store.dataframe("select count(*) as cnt, coalesce(sum(total_tokens), 0) as total_tokens from llm_calls")
        matches_df = store.dataframe("select count(*) as cnt from match_results")
        vectors_df = store.dataframe("select count(*) as cnt from profile_vectors")

        vec_cnt = int(vectors_df.iloc[0]['cnt']) if not vectors_df.empty else 0
        r_cnt = int(runs_df.iloc[0]['cnt']) if not runs_df.empty else 0
        r_cost = float(runs_df.iloc[0]['total_cost']) if not runs_df.empty else 0.0
        r_lat = float(runs_df.iloc[0]['avg_latency']) if not runs_df.empty else 0.0
        c_cnt = int(calls_df.iloc[0]['cnt']) if not calls_df.empty else 0
        c_tok = int(calls_df.iloc[0]['total_tokens']) if not calls_df.empty else 0
        m_cnt = int(matches_df.iloc[0]['cnt']) if not matches_df.empty else 0
        emb_mode = "Indexed (Vector)" if vec_cnt > 0 else "Lexical Fallback"

        stats_cards = [
            mo.md(f"""
| Metrik Database | Nilai | Keterangan |
| :--- | :--- | :--- |
| **Total Profil Komunitas** | `{len(profiles):,}` | Profil tersimpan di synthetic_profiles.json |
| **Total Pipeline Runs** | `{r_cnt:,}` | Riwayat run tercatat di DuckDB |
| **Total Panggilan LLM** | `{c_cnt:,}` | Log tahapan LLM (Need, Judge, Intro) |
| **Total Hasil Match** | `{m_cnt:,}` | Kandidat yang pernah dicocokkan |
| **Total Token Terpakai** | `{c_tok:,}` | Konsumsi token input dan output |
| **Total Estimasi Biaya** | `${r_cost:.6f}` | Estimasi biaya panggilan API |
| **Rata-rata Latensi Run** | `{r_lat:.0f} ms` | Rata-rata waktu eksekusi pipeline per run |
| **Status Vector Embeddings** | `{vec_cnt:,}` vektor | Mode: {emb_mode} |
"""),
        ]
        elements = [m for m in [msg, *stats_cards] if m is not None]
        output_view = mo.vstack(elements)

    elif selected_view == "Data Profil Komunitas (2.000 profil)":
        filtered_profiles = []
        for p in profiles:
            p_text = f"{p.get('name', '')} {p.get('headline', '')} {p.get('location', '')} {' '.join(p.get('canHelpWith', []))} {' '.join(p.get('knowledge', []))} {' '.join(p.get('interests', []))}".lower()
            if not search_keyword or search_keyword in p_text:
                filtered_profiles.append({
                    "id": p["id"],
                    "name": p.get("name", ""),
                    "headline": p.get("headline", ""),
                    "location": p.get("location") or "-",
                    "canHelpWith": ", ".join(p.get("canHelpWith", []))[:50],
                    "lookingFor": ", ".join(p.get("lookingFor", []))[:40],
                    "openTo": ", ".join(p.get("openTo", [])),
                })
        elements = [m for m in [msg] if m is not None]
        elements.extend([
            mo.md(f"Menampilkan **{len(filtered_profiles)}** dari {len(profiles)} profil:"),
            mo.ui.table(filtered_profiles, selection=None, page_size=10),
        ])
        output_view = mo.vstack(elements)

    elif selected_view == "Riwayat Pipeline Runs (DuckDB)":
        runs_data = store.dataframe("select id, requester_id, query, status, total_latency_ms, estimated_cost_usd, created_at from runs order by created_at desc limit 100")
        if search_keyword and not runs_data.empty:
            runs_data = runs_data[runs_data.apply(lambda r: search_keyword in str(r).lower(), axis=1)]
        elements = [m for m in [msg] if m is not None]
        elements.extend([
            mo.md(f"Menampilkan **{len(runs_data)}** riwayat runs terbaru:"),
            mo.ui.table(runs_data.to_dict(orient="records"), selection=None, page_size=10),
        ])
        output_view = mo.vstack(elements)

    elif selected_view == "Riwayat Panggilan LLM (DuckDB)":
        calls_data = store.dataframe("select id, run_id, stage, model, input_tokens, output_tokens, total_tokens, latency_ms, estimated_cost_usd, error, created_at from llm_calls order by created_at desc limit 100")
        if search_keyword and not calls_data.empty:
            calls_data = calls_data[calls_data.apply(lambda r: search_keyword in str(r).lower(), axis=1)]
        elements = [m for m in [msg] if m is not None]
        elements.extend([
            mo.md(f"Menampilkan **{len(calls_data)}** panggilan LLM terbaru:"),
            mo.ui.table(calls_data.to_dict(orient="records"), selection=None, page_size=10),
        ])
        output_view = mo.vstack(elements)

    elif selected_view == "Riwayat Hasil Match (DuckDB)":
        matches_data = store.dataframe("select run_id, candidate_id, judge_rank, judge_score, judge_reason from match_results order by run_id desc limit 100")
        if search_keyword and not matches_data.empty:
            matches_data = matches_data[matches_data.apply(lambda r: search_keyword in str(r).lower(), axis=1)]
        elements = [m for m in [msg] if m is not None]
        elements.extend([
            mo.md(f"Menampilkan **{len(matches_data)}** hasil match tersimpan:"),
            mo.ui.table(matches_data.to_dict(orient="records"), selection=None, page_size=10),
        ])
        output_view = mo.vstack(elements)
    else:
        output_view = mo.md("Pilih data untuk ditampilkan.")

    output_view
    return


@app.cell
def _(mo, profiles):
    name_by_id = {p["id"]: p for p in profiles}
    # Tampilkan hanya profil kanonik sebagai requester (biar dropdown ringan & cepat);
    # query tetap dijalankan atas seluruh 2.000 profil kandidat.
    requester_ids = [p["id"] for p in profiles if not p["id"].startswith("synthetic-")]
    profile_options = {f"{name_by_id[i]['name']} — {name_by_id[i]['headline']}": i for i in requester_ids}
    default_label = next(label for label, pid in profile_options.items() if pid == "adi")
    requester = mo.ui.dropdown(label="Requester", options=profile_options, value=default_label)
    custom_query = mo.ui.text_area(
        label="Query kustom (ketik kebutuhan orang yang kamu cari)",
        value="I need a senior developer who genuinely enjoys teaching beginners.",
        full_width=True,
    )
    judge_reasoning = mo.ui.dropdown(label="Judge reasoning", options=["none", "low", "medium"], value="low")
    retrieval_count = mo.ui.number(label="Retrieval count", start=5, stop=50, value=15)
    judge_shortlist = mo.ui.number(label="Judge shortlist", start=3, stop=20, value=6)
    max_output = mo.ui.number(label="Max output tokens", start=200, stop=2000, value=800)
    help_box = mo.accordion({
        "Penjelasan Singkat Parameter Kontrol": mo.md("""
        - **Judge reasoning (`low`)**: Tingkat penalaran/berpikir (*Chain-of-Thought*) model saat mencocokkan profil. `low` seimbang antara akurasi dan kecepatan.
        - **Retrieval count (`15`)**: Jumlah kandidat awal yang disaring dari database 2.000 profil melalui pencarian vektor/leksikal (tahap *funnel filter* ke-1).
        - **Judge shortlist (`6`)**: Jumlah kandidat teratas dari hasil retrieval yang dikirim ke LLM Match Judge untuk dinilai mendalam & dibuatkan intro.
        - **Max output tokens (`800`)**: Batas panjang teks balasan model agar format JSON tidak terpotong dan mencegah pemborosan token/biaya.
        """)
    })
    mo.vstack([
        requester,
        custom_query,
        mo.hstack([judge_reasoning, retrieval_count, judge_shortlist, max_output], justify="start"),
        help_box,
    ])
    return (
        custom_query,
        judge_reasoning,
        judge_shortlist,
        max_output,
        requester,
        retrieval_count,
    )


@app.cell
def _(mo):
    run_single = mo.ui.run_button(label="Run query kustom ini", kind="success")
    run_all = mo.ui.run_button(label="Run all eval queries")
    mo.hstack([run_single, run_all], justify="start")
    return run_all, run_single


@app.cell
def _(
    Pipeline,
    PipelineConfig,
    custom_query,
    eval_queries,
    judge_reasoning,
    judge_shortlist,
    max_output,
    mo,
    os,
    profiles,
    requester,
    retrieval_count,
    run_all,
    run_single,
    store,
    time,
):
    batch_trigger = run_all.value
    single_trigger = (run_single.value or os.getenv("LIVE_TEST") == "1")
    mo.stop(
        not (batch_trigger or single_trigger),
        mo.callout("Silakan pilih **Requester** dan ketik **Query kustom** di atas, lalu klik **Run query kustom ini**.", kind="info"),
    )
    config = PipelineConfig(judge_reasoning_effort=judge_reasoning.value, retrieval_count=int(retrieval_count.value), judge_shortlist=int(judge_shortlist.value), max_output_tokens=int(max_output.value))
    requester_val = requester.value
    requester_id = next((profile["id"] for profile in profiles if profile["id"] == requester_val or f"{profile['name']} — {profile['headline']}" == requester_val), "adi")
    pipeline = Pipeline(store, profiles, os.getenv("OPENAI_API_KEY"))

    queries = eval_queries if batch_trigger else [{"query": custom_query.value.strip(), "known_good_candidate_ids": []}]
    if not queries[0]["query"]:
        queries = [{"query": "I need someone who can help me get started.", "known_good_candidate_ids": []}]

    streamed_logs = []
    def on_delta(stage, delta):
        streamed_logs.append(f"[{stage}] {delta}")
        if len(streamed_logs) % 15 == 0:
            mo.output.replace(mo.callout(f"Sedang memproses tahap: `{stage}` (menerima respon model)...", kind="info"))

    results = []
    spinner_title = f"Menjalankan {len(queries)} query melalui pipeline (Need -> Retrieval -> Judge -> Intro)..."
    with mo.status.spinner(title=spinner_title):
        for idx, item in enumerate(queries, 1):
            query = item["query"]
            start = time.perf_counter()
            mo.output.replace(mo.callout(f"[{idx}/{len(queries)}] Menghubungi LLM untuk query: *\"{query[:80]}\"*...", kind="info"))
            try:
                result = pipeline.run(requester_id, query, config, on_delta=on_delta)
                results.append({
                    "query": query,
                    "known_good": item.get("known_good_candidate_ids", []),
                    "status": result["status"],
                    "error": result["error"],
                    "need": result.get("need") or {},
                    "need_goal": (result.get("need") or {}).get("goal"),
                    "interactionType": (result.get("need") or {}).get("interactionType"),
                    "retrieval": len(result.get("retrieval", [])),
                    "matches_count": len(result.get("matches", [])),
                    "matches": result.get("matches", []),
                    "top_candidates": [m["candidate_id"] for m in result.get("matches", [])[:3]],
                    "latency_ms": round(result.get("total_latency_ms", 0), 0),
                    "cost_usd": round(result.get("estimated_cost_usd", 0), 6),
                    "new_run_id": result.get("run_id"),
                })
            except Exception as exc:
                results.append({"query": query, "known_good": item.get("known_good_candidate_ids", []), "status": "failed", "error": f"{type(exc).__name__}: {exc}", "matches_count": 0, "matches": [], "need": {}, "retrieval": 0, "top_candidates": [], "latency_ms": 0, "cost_usd": 0, "new_run_id": None})

    mo.output.replace(mo.callout(f"Selesai. Berhasil memproses {len(queries)} query. Hasil selengkapnya ditampilkan di bawah.", kind="success"))
    test_output = {"run_time": time.strftime("%Y-%m-%d %H:%M:%S"), "config": config.__dict__, "results": results}
    return (test_output,)


@app.cell
def _(mo, test_output):
    rows = [{"query": r["query"][:60], "status": r["status"], "error": (r.get("error") or "")[:40], "interactionType": r.get("interactionType"), "retrieval": r.get("retrieval"), "matches": r.get("matches_count", 0), "top": ",".join(r.get("top_candidates", [])), "latency_ms": r.get("latency_ms"), "cost_usd": r.get("cost_usd"), "run_id": (r.get("new_run_id") or "")[:8]} for r in test_output["results"]]
    mo.vstack([
        mo.md("## Ringkasan Hasil"),
        mo.ui.table(rows, selection=None),
    ])
    return


@app.cell
def _(mo, profiles, test_output):
    profiles_by_id = {p["id"]: p for p in profiles}
    cards = [
        mo.md("## Rekomendasi Profil dan Alasan Pemilihan (Match Details)"),
        mo.md(f"Run: `{test_output['run_time']}`"),
    ]

    for q_idx, r in enumerate(test_output["results"], 1):
        cards.append(mo.md(f"### Query #{q_idx}: *\"{r['query']}\"* — `{r['status']}`"))
        if r["status"] != "completed":
            cards.append(mo.callout(f"Error: `{r.get('error')}`", kind="danger"))
            continue

        need_data = r.get("need", {})
        if need_data:
            cards.append(mo.md(f"**Target Kebutuhan (Interpreted Need):**\n- **Goal:** {need_data.get('goal')}\n- **Tipe Interaksi:** `{', '.join(need_data.get('interactionType', []))}`"))

        matched_list = r.get("matches", [])
        if not matched_list:
            cards.append(mo.callout("Tidak ada profil yang memenuhi batas minimum skor kecocokan.", kind="warn"))
            continue

        for rank, match in enumerate(matched_list, 1):
            cand_id = match["candidate_id"]
            cand_profile = profiles_by_id.get(cand_id, {})
            cand_name = cand_profile.get("name", cand_id)
            cand_headline = cand_profile.get("headline", "")
            cand_loc = cand_profile.get("location") or "Tidak disebutkan"
            cand_help = ", ".join(cand_profile.get("canHelpWith", [])) or "-"
            cand_looking = ", ".join(cand_profile.get("lookingFor", [])) or "-"
            cand_open = ", ".join(cand_profile.get("openTo", [])) or "-"
            cand_summary = cand_profile.get("summary", "")

            score = match.get("score", 0.0)
            reason = match.get("reason", "")
            intro = match.get("introduction") or {}

            card_content = f"""
---
#### #{rank} **{cand_name}** (`{cand_id}`)
*{cand_headline}*

| **Lokasi** | **Skor Kecocokan** | **Open To** |
| :--- | :--- | :--- |
| {cand_loc} | **`{score:.2f} / 1.0`** | `{cand_open}` |

**Detail Profil User:**
- **Summary:** {cand_summary}
- **Keahlian / Bisa Membantu:** `{cand_help}`
- **Sedang Mencari:** `{cand_looking}`

**Alasan Mengapa AI Memilih Profil Ini (Judge Reason):**
> *"{reason}"*

**Analisis Timbal-Balik dan Draf Pesan Pembuka (Introduction):**
- **Kenapa orang ini tepat untukmu:** {intro.get('why_this_person', '-')}
- **Kenapa kamu bernilai untuk dia (Mutual Value):** {intro.get('why_you', '-')}
- **Saran Pesan Pembuka (Icebreaker Opener):**
  > *"{intro.get('possible_opener', '-')}"*
"""
            cards.append(mo.md(card_content))

    mo.vstack(cards)
    return


@app.cell
def _(mo, per_requester_tokens, per_run_tokens, store):
    _runs = per_run_tokens(store, min_tokens=1)
    mo.vstack([
        mo.md("## Konsumsi token AI (dari DuckDB)"),
        mo.hstack([
            mo.ui.table(_runs, selection=None),
            mo.ui.table(per_requester_tokens(store), selection=None),
        ], justify="start"),
    ])
    return


if __name__ == "__main__":
    app.run()
