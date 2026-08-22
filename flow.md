# Alur Kerja Pipeline Pencocokan Komunitas (flow.md)

Dokumen ini menjelaskan **cara kerja**, **algoritma**, dan **komponen** dari pipeline
pencocokan antar-manusia di komunitas ini, lengkap dengan potongan kode sumber dan
lokasi file di mana masing-masing diterapkan.

Arsitektur memiliki dua alur yang terpisah: **pembentukan profil** dan **pencocokan**.
Profil dibentuk dari percakapan, ditinjau oleh pengguna, lalu baru dapat dipersistenkan
dan di-embed melalui aksi eksplisit. Pipeline pencocokan mengikuti prinsip **funnel
bertahap**: semakin mahal suatu tahap, semakin sedikit orang yang diproses.

```
percakapan ──▶ onboarding transcript ──▶ profile compiler ──▶ edit/validasi ──▶ persist + embed
                                                               (aksi pengguna)

2000 profil ──▶ retrieval (hemat) ──▶ prescore (deterministik) ──▶ judge (LLM) ──▶ intro (LLM)
               30 kandidat            10-15 shortlist             6 match           1 pesan/kandidat
```

---

## 0. Pembentukan Profil — Onboarding dan Profile Compiler

Pembentukan profil sengaja dibagi menjadi dua agen. `OnboardingInterviewer` menjaga
percakapan tetap natural dan menghasilkan **transkrip sumber**; `ProfileCompiler`
mengubah sumber tersebut menjadi **draft terstruktur**. Pemisahan ini mencegah ucapan
pengguna berubah menjadi klaim profil atau data persisten tanpa kesempatan untuk
ditinjau.

```text
jawaban pengguna
      │
      ▼
OnboardingSession ──▶ OnboardingInterviewer ──▶ transkrip selesai
                                                     │
                                                     ▼
                                            ProfileCompiler (LLM)
                                                     │
                                                     ▼
                                          ProfileDraft tervalidasi
                                                     │
                                                     ▼
                                         edit + validasi pengguna
                                                     │
                                                     ▼
                                  persist / rebuild embedding (terpisah)
```

### 0.1 Onboarding interviewer — `src/agents/onboarding.py`

Tujuan onboarding adalah memperoleh informasi yang cukup untuk menjawab dua hal:
kapan orang lain akan mendapat manfaat dari bertemu pengguna, dan kapan pengguna
akan mendapat manfaat dari bertemu orang lain. Agen menggali pengetahuan, pengalaman,
minat, proyek, bantuan yang dapat diberikan/dibutuhkan, orang yang ingin ditemui, dan
jenis interaksi yang terbuka—tanpa memaksa semua kategori terisi.

Aturan percakapan utamanya:

- satu pertanyaan per giliran, singkat, dan mengikuti jawaban aktual;
- meminta contoh konkret alih-alih menerima label generik;
- tidak menyamakan minat dengan keahlian, paparan dengan pengalaman, pengalaman
  dengan kesediaan membantu, atau aspirasi dengan kemampuan saat ini;
- tidak menanyakan hal sensitif hanya demi memperkaya profil;
- menargetkan sekitar 5–8 jawaban bermakna, tetapi boleh lanjut jika masih ada
  ambiguitas penting.

`OnboardingSession` menyimpan urutan `Turn(role, content)` dan flag `finished`.
Jawaban kosong ditolak, sesi yang sudah selesai tidak dapat menerima jawaban baru,
dan sapaan seperti `hello` atau `start my onboarding` tidak dihitung sebagai jawaban
bermakna. `state()` mengekspos bentuk berikut kepada agen:

```json
{
  "meaningfulUserAnswers": 3,
  "finished": false,
  "transcript": [
    {"role": "user", "content": "..."},
    {"role": "assistant", "content": "..."}
  ]
}
```

Setiap `next_turn()` memakai Responses API dengan dua function tool tanpa argumen:

| Tool | Fungsi |
| :-- | :-- |
| `getOnboardingState` | Membaca jumlah jawaban, status selesai, dan seluruh transkrip. Tool ini diwajibkan pada panggilan pertama setiap giliran. |
| `finishOnboarding` | Mengubah `session.finished` menjadi `true` ketika informasi sudah cukup. |

Setelah tool dieksekusi lokal, hasilnya dikirim kembali sebagai
`function_call_output`; model kemudian boleh bertanya lagi atau menyelesaikan sesi.
Loop dibatasi delapan putaran tool agar tool call yang menyimpang tidak berjalan tanpa
batas. Bila model tidak mengeluarkan teks, kode menyediakan pesan fallback sesuai
status sesi. Setiap panggilan model menghasilkan trace stage `onboarding`, termasuk
model, prompt version `onboarding_v1`, token, latensi, biaya estimasi, request, dan
response.

Laboratorium `01_onboarding.py` menambahkan batas jumlah jawaban yang dapat diatur.
Jika batas tercapai, lab menutup sesi tanpa panggilan model tambahan. Lab menyimpan
trace ke DuckDB dan menampilkan transkrip final untuk disalin ke profile compiler.
Interviewer sendiri **tidak membuat atau menyimpan profil**.

### 0.2 Profile compiler — `src/agents/profile_compiler.py`

`ProfileCompiler.compile_with_trace()` menerima transkrip non-kosong, mengirimkannya
sebagai JSON ke Responses API, dan meminta Structured Output strict bernama
`profile_draft`. Default-nya memakai `gpt-5.6-luna`, reasoning `low`, dan maksimum
1.200 output token.

Compiler mempertahankan makna pernyataan dan kategori sumbernya. Contohnya, “ingin
belajar cybersecurity” masuk `interests`/`lookingFor`, bukan otomatis `knowledge`;
“pernah ikut CTF tiga tahun” dapat menjadi `experience`; dan kesediaan mengajar harus
dinyatakan sebelum masuk `canHelpWith`. Compiler tidak mengarang atau memverifikasi
klaim secara independen.

Draft wajib memiliki kontrak berikut (`src/schemas/profile.py`):

| Field | Bentuk dan makna |
| :-- | :-- |
| `headline`, `summary` | String non-kosong yang singkat dan faktual. |
| `knowledge` | Pengetahuan yang memang dinyatakan pengguna. |
| `experience` | Pengalaman hidup/profesional yang konkret. |
| `interests` | Topik atau aktivitas yang diminati. |
| `canHelpWith` | Hal yang secara eksplisit dapat dibantu pengguna. |
| `lookingFor` | Bantuan, orang, atau aktivitas yang dicari. |
| `openTo` | Hanya enum interaksi: `advice`, `being_hired`, `being_mentored`, `cofounding`, `collaboration`, `friendship`, `hiring`, `meeting_people`, `mentoring`, `recommendations`. |
| `projects` | Daftar objek dengan `description` wajib serta `name`/`status` opsional. |
| `location` | String non-kosong bila disebutkan eksplisit, atau `null`. |

Aktivitas seperti *photo walk* bukan nilai `openTo`; aktivitas tetap berada di
`interests` atau `lookingFor`, sementara `openTo` hanya menyatakan bentuk hubungan
sosial yang luas. Setelah Structured Output diterima, `ProfileDraft.from_dict()`
melakukan validasi kedua di aplikasi: field wajib, string non-kosong, enum `openTo`,
struktur proyek, dan lokasi. JSON atau kontrak yang invalid diubah menjadi error dan
tidak menghasilkan draft.

Keluaran `compile_with_trace()` adalah `(draft, raw_response, trace)`. Trace memakai
stage `profile_compiler` dan prompt version `profile_compiler_v1`; error API juga
diberi trace pada exception agar tetap dapat diaudit.

Laboratorium `02_profile_compiler.py` memperlihatkan alur persetujuan eksplisit:

1. pengguna memasukkan transkrip selesai (dan opsional profil lama sebagai konteks
   pembaruan);
2. compiler menghasilkan draft tervalidasi;
3. draft ditampilkan dalam editor JSON dan boleh diubah;
4. tombol accept menjalankan `ProfileDraft.from_dict()` sekali lagi;
5. hasil yang diterima hanya siap untuk langkah persistensi/embedding berikutnya—lab
   ini sendiri **tidak menulis profil atau memperbarui index embedding**.

### 0.3 Handoff ke pipeline pencocokan

Hanya profil yang telah ditinjau dan diterima yang semestinya dipersistenkan lalu
dimasukkan ke `EmbeddingIndex`. Tiga dokumen arah (`offers`, `interests`, `needs`)
kemudian dibentuk oleh `profile_vectors()` seperti dijelaskan di §3.1 dan §5.2.
Pipeline pencocokan di bagian berikut mengasumsikan langkah penerimaan, persistensi,
dan indexing ini sudah selesai; onboarding/compiler bukan bagian dari `Pipeline.run()`.

---

## 1. Gambaran Umum Pipeline

Pipeline pencocokan berjalan end-to-end dari teks query bebas → daftar rekomendasi
yang sudah di-scoring & diberi draft pesan pembuka. Setiap tahap dipisahkan agar tiap bagian bisa
diisolasi (notebook 03/04/07), diuji, dan di-*trace* biaya/latensinya.

| Tahap | Fungsi | Biaya | File |
| :-- | :-- | :-- | :-- |
| 1. Need Interpreter | Query → kebutuhan terstruktur + 3 query arah | LLM (kecil) | `src/agents/need_interpreter.py`, dipanggil di `src/pipeline.py:433` |
| 2. Retrieval | Pilih kandidat relevan dari ribuan | Embedding (murah) | `src/retrieval/search.py` |
| 3. Prescore | Beri skor deterministik | Gratis | `src/retrieval/prescore.py` |
| 4. Match Judge | Ukur mutual value dgn LLM | LLM (mahal) | `src/agents/match_judge.py`, `src/pipeline.py:445` |
| 5. Introduction | Buat draft pesan pembuka | LLM (mahal) | `src/agents/introduction.py`, `src/pipeline.py:458` |

Semua hasil persisten ke DuckDB (`src/tracing/storage.py`) agar bisa dievaluasi offline.

---

## 2. Orkestrasi Pipeline — `src/pipeline.py`

Tahap 1–5 dirangkai dalam `Pipeline.run()` (`src/pipeline.py:429`). Fungsi ini adalah
jantung orkestrasi.

```python
def run(self, requester_id, query, config, on_delta=None):
    requester = next(p for p in self.profiles if p["id"] == requester_id)
    run_id = self.store.new_run(requester, query, asdict(config))
    started = time.perf_counter()
    try:
        # (1) Interpretasi kebutuhan
        need = self._response(run_id, "need_interpreter", config.need_model,
                              NEED_INTERPRETER_PROMPT, NEED_INTERPRETER_VERSION,
                              {"query": query, "requester": _compact(requester)},
                              "need_interpretation", NEED_SCHEMA, config.need_reasoning_effort, config)
        need = _coerce_need(need)                          # -> bentuk baku

        # (2)+(3) Retrieval + prescore
        retrieved = self._retrieve(run_id, requester, need, config)
        self.store.add_retrieval(run_id, retrieved)

        # (4) Judge hanya terhadap shortlist (isolate prescore agar tidak anchor)
        judge_candidates = [_compact(row["candidate"])
                            for row in retrieved[:config.judge_shortlist]]
        judged = self._response(run_id, "match_judge", config.judge_model,
                                MATCH_JUDGE_PROMPT, MATCH_JUDGE_VERSION,
                                {"query": query, "need": need,
                                 "requester": _compact(requester),
                                 "candidates": judge_candidates},
                                "match_results", MATCH_SCHEMA, config.judge_reasoning_effort, config)
        judged_matches = _coerce_matches(judged)

        # (5) Intro paralel untuk match yang lolos threshold
        visible = [m for m in judged_matches if m["score"] >= config.min_judge_score]
        # ... _intro_for dibatasi ThreadPoolExecutor(max_workers=4)
    except Exception as exc:
        status, error = "failed", str(exc)
    latency = round((time.perf_counter() - started) * 1000, 2)
    self.store.finish_run(run_id, need=need, status=status, error=error,
                          latency_ms=latency, estimated_cost=cost)
    return {...}
```

### 2.1 Response LLM terpusat — `Pipeline._response` (`src/pipeline.py:292`)
Semua panggilan LLM lewat satu pintu `_response` supaya tracing, parsing, dan
fallback konsisten:

```python
def _response(self, run_id, stage, model, prompt, prompt_version, payload,
              schema_name, schema, reasoning_effort, config, on_delta=None):
    request = {"model": model, "instructions": prompt,
               "input": json.dumps(payload), "stream": True,
               "max_output_tokens": config.max_output_tokens}
    if _is_official_openai(self.base_url):
        request["text"] = {"format": {"type": "json_schema", "schema": schema, "strict": True}}
    else:
        request["instructions"] = prompt + _json_only_instruction(schema)  # non-OpenAI: minta JSON via prompt
    ...
    # streaming; fallback non-stream via HTTP jika streaming diblokir provider
    # parsing toleran (_parse_json_tolerant) lalu store.add_call tracer
    return parsed
```

### 2.2 Intro paralel — `src/pipeline.py:462`
Karena intro adalah panggilan LLM termahal per kandidat, generation dijalankan paralel
agar latensi tidak linear terhadap jumlah match:

```python
if config.parallel_intro and len(visible_judged) > 1:
    import concurrent.futures as _fut
    with _fut.ThreadPoolExecutor(max_workers=min(4, len(visible_judged))) as ex:
        futs = {ex.submit(_intro_for, m): m for m in visible_judged}
        tmp = {fut.result()["candidate_id"]: fut.result() for fut in _fut.as_completed(futs)}
        for rank, match in enumerate(visible_judged, 1):
            result = tmp[match["userId"]]
            matches.append(result)
            self.store.add_match(run_id, result, rank)
```

---

## 3. Retrieval — `src/retrieval/search.py`

Tujuan retrieval adalah **memilih ~30 kandidat relevan dari 2000 profil dengan biaya
minimal**, sebelum judge (mahal) bekerja. Kunci efisiennya: dengan index, hanya **3
teks query** yang di-embed, vektor kandidat dibaca dari precomputed index.

```python
def search_people(*, profiles, requester, queries, filters, interaction_types,
                  limit, index=None, embedder=None, per_dimension_count=50,
                  min_prescore=None, weights=None, soft_preferences=None,
                  avoid_terms=None, normalize=True, diversify=False, mmr_lambda=0.7):
    candidates, _ = _filtered_with_meta(profiles, requester, filters, interaction_types)
    requester_vectors = profile_vectors(requester)
    # 3 query terarah: offers / interests / needs
    reciprocal_query_text = queries.get("needs", "").strip() or requester_vectors.offers
    query_texts = [queries.get("offers", ""), queries.get("interests", ""), reciprocal_query_text]

    if index is not None:
        vectors = _safe_embed(embedder, query_texts)      # hanya 3 embed
        offer_q, interest_q, reciprocal_q = vectors[:3]
        rows = []
        for candidate in candidates:
            pid = candidate["id"]
            rows.append({
                "candidate": candidate,
                "offers_similarity": _cos(index, pid, "offers", offer_q),      # kandidat dari index
                "interests_similarity": _cos(index, pid, "interests", interest_q),
                "reciprocal_similarity": _cos(index, pid, "needs", reciprocal_q),
            })
        if normalize: normalize_dimensions(rows)          # (lihat prescore)
        return _rank(_union_top_n(rows, per_dimension_count), ...)
    # tanpa index/embedder -> lexical fallback (tidak crash offline)
    return _rank(_union_top_n(_lexical_rows(candidates, query_texts, requester_vectors), ...))
```

> **Kenapa 3 arah?** Karena *mutual matching*. Sisi `offers` menangkap "apa yang
> orang ini bisa tawarkan", `interests` menangkap "topik yang disukai", `needs`
> menangkap "apa yang ia cari". Memisah cara menangkap profil yang *bisa membantu*
> vs profil yang *punya kebutuhan yang saling melengkapi*.

### 3.1 Representasi 3 arah — `profile_vectors` (`src/retrieval/embeddings.py:40`)
Setiap profil dipecah jadi 3 dokumen teks terarah yang di-embed:

```python
def profile_vectors(profile):
    projects = [p.get("description", "") for p in profile.get("projects", []) if isinstance(p, dict)]
    return ProfileVectors(
        offers=_joined(profile.get("knowledge", []) + profile.get("experience", []) + profile.get("canHelpWith", [])),
        interests=_joined(profile.get("interests", []) + projects),
        needs=_joined(profile.get("lookingFor", []) + profile.get("openTo", [])),
    )
```

### 3.2 Union Top-N per dimensi — `_union_top_n` (`src/retrieval/search.py:164`)
Ambil top-N per arah lalu union agar kandidat yang kuat di satu arah pun tidak
terbuang oleh kandidat yang rata-rata bagus:

```python
def _union_top_n(rows, per_dimension_count):
    keep = set()
    for dim in ("offers_similarity", "interests_similarity", "reciprocal_similarity"):
        for row in sorted(rows, key=lambda r: r[dim], reverse=True)[:per_dimension_count]:
            keep.add(row["candidate"]["id"])
    return [row for row in rows if row["candidate"]["id"] in keep]
```

### 3.3 Diversifikasi MMR (opsional) — `_mmr_rerank` (`src/retrieval/search.py:190`)
Saat `diversify=True`, rerank memakai **Maximal Marginal Relevance** agar shortlist
tidak monoton (semua kandidat terlalu mirip):

```
next = argmax  λ * prescore − (1 − λ) * max_jaccard(candidate, selected)
```

```python
def _mmr_rerank(rows, mmr_lambda=0.7):
    remaining = sorted(rows, key=lambda r: r["prescore"], reverse=True)
    selected = []
    while remaining:
        if not selected:
            selected.append(remaining.pop(0)); continue
        best_idx, best_score = 0, float("-inf")
        for i, r in enumerate(remaining):
            max_sim = max(_jaccard(tok[r["candidate"]["id"]], tok[s["candidate"]["id"]])
                          for s in selected)
            mmr = mmr_lambda * r["prescore"] - (1 - mmr_lambda) * max_sim
            if mmr > best_score:
                best_score, best_idx = mmr, i
        selected.append(remaining.pop(best_idx))
    return selected
```

### 3.4 Filter hard + relax eksplisit — `_filtered_with_meta` (`src/retrieval/search.py:133`)
Filter lokasi/interaksi diterapkan dulu. Jika hasil kosong, filter **direlaksasi
sadar** (menghasilkan flag `interaction_relaxed` / `location_relaxed`) alih-alih
diam-diam menghilangkan hasil:

```python
def _filtered_with_meta(profiles, requester, filters, interaction_types):
    base = [p for p in profiles if p["id"] != requester["id"] and _matches_hard_filters(p, filters, interaction_types)]
    if base: return base, "none"
    if filters.get("location"):
        relaxed = [p for p in profiles if p["id"] != requester["id"]
                   and p.get("location", "").casefold() == str(filters["location"]).casefold()]
        if relaxed: return relaxed, "interaction_relaxed"
    return [p for p in profiles if p["id"] != requester["id"]], "location_relaxed"
```

---

## 4. Prescore — `src/retrieval/prescore.py`

Prescore adalah **skor deterministik murah** yang dipakai untuk meranking shortlist
sebelum judge (mahal) melihatnya. Totalnya ter-*clamp* ke [0, 1].

```
prescore = offers*0.45 + interests*0.20 + reciprocity*0.20 + interaction*0.15
           + soft_boost(≤0.12)          # bonus preferensi lunak
           × (1 − 0.8*avoid_penalty)     # penit multiplikatif utk avoid
```

```python
def weighted_prescore(offers, interests, reciprocity, interaction, weights,
                      *, soft_boost=0.0, avoid_penalty=0.0):
    raw = (weights.offers_weight*offers + weights.interests_weight*interests
           + weights.reciprocity_weight*reciprocity + weights.interaction_weight*interaction)
    if soft_boost: raw += min(0.12, soft_boost * 0.15)
    if avoid_penalty: raw *= max(0.0, 1.0 - avoid_penalty * 0.8)
    return max(0.0, min(1.0, raw))
```

### 4.1 Interaction score Jaccard kontinu — `interaction_score` (`prescore.py:15`)
Menggantikan step diskrit 0/0.5/1.0 agar perbedaan overlap 1-dari-3 vs 1-dari-2
terwakili. Backward-compat: 2/2=1.0, 1/2=0.5, 0=0.0 tetap sama.

```python
def interaction_score(requested, candidate_open_to):
    req, cand = set(requested), set(candidate_open_to)
    union = req | cand
    return len(req & cand) / len(union) if union else 0.0
```

### 4.2 Normalisasi per-dimensi — `normalize_dimensions` (`prescore.py:90`)
Min-max tiap arah ke [0,1] supaya skala cosine yang berbeda (mis. `offers` padat,
`needs` jarang) tidak mendominasi hanya karena skalanya. **Hanya untuk jalur
embedding** — lexical skip agar noise sparse tidak terinflasi.

```python
def normalize_dimensions(rows, dims=("offers_similarity", "interests_similarity", "reciprocal_similarity")):
    for dim in dims:
        vals = [float(r.get(dim, 0.0)) for r in rows]
        if not vals: continue
        mn, mx = min(vals), max(vals)
        rng = mx - mn
        if rng < 1e-9: continue
        for r in rows:
            r[dim] = (float(r.get(dim, 0.0)) - mn) / rng
    return rows
```

### 4.3 Preferensi lunak & penghindaran — `soft_preference_score` / `avoidance_penalty`
- `soft_preference_score(candidate, soft_preferences)` → 0–1, seberapa besar frase
  preferensi (mis. "Bandung", "mahasiswa") ada di profil.
- `avoidance_penalty(candidate, avoid_terms)` → 0–1, seberapa besar kandidat mencerminkan
  hal yang ingin dihindari (mis. "mencari senior untuk bayaran" saat requester ingin peer).

```python
def soft_preference_score(candidate, soft_preferences):
    haystack = " ".join(candidate.get("knowledge", []) + candidate.get("experience", [])
                        + candidate.get("interests", []) + candidate.get("canHelpWith", [])
                        + [candidate.get("location", "") or ""]).lower()
    hay_tokens = _tokens(haystack)
    hits = 0
    for phrase in soft_preferences:
        pt = _tokens(phrase)
        if pt and (pt & hay_tokens):
            hits += len(pt & hay_tokens) / len(pt)
    return min(1.0, hits / max(1, len(soft_preferences)))
```

---

## 5. Embedding & Index — `src/retrieval/embeddings.py`, `src/retrieval/index.py`

### 5.1 Embedder & fallback leksikal
- `OpenAIEmbedder` (`embeddings.py:49`) membungkus provider OpenAI-compatible,
  meng-embed batch teks dan mencatat trace biaya/latensi.
- `EMBEDDING_MODEL` di-resolve dari `provider_config()["embedding_model"]` (env
  `EMBEDDING_MODEL`) agar provider kustom bisa memakai model embedding sendiri.
- `lexical_similarity` (`embeddings.py:67`) = fallback offline (overlap token) saat
  tidak ada index/embedder, supaya pipeline tidak crash.

### 5.2 Index persisten + batch rebuild
`EmbeddingIndex` menampung `{kind: {profile_id: vector}}` untuk 3 arah tiap profil,
dipulikan di tabel `profile_vectors` (DuckDB). Rebuild diproses **per batch** agar
tidak melampaui limit input provider (mis. 2048 item):

```python
@classmethod
def rebuild(cls, store, profiles, embedder, *, batch_size=256):
    store.create_vector_table()
    rows, doc_to_key = [], {}
    for profile in profiles:
        v = profile_vectors(profile)
        for kind in ("offers", "interests", "needs"):
            text = getattr(v, kind)
            if text.strip():
                doc_to_key[(profile["id"], kind)] = text
    keys = list(doc_to_key.keys())
    for start in range(0, len(keys), batch_size):
        chunk = keys[start:start+batch_size]
        embeddings = embedder.embed([doc_to_key[k] for k in chunk])
        for key, vector in zip(chunk, embeddings):
            rows.append({"profile_id": key[0], "kind": key[1],
                         "vector": vector, "text": doc_to_key[key]})
    store.upsert_vector_rows(rows)
    return cls.load(store)
```

---

## 6. Agent LLM (Prompt) — `src/agents/`

### 6.1 Need Interpreter — `need_interpreter.py:72`
Mengubah query bebas → rencana terstruktur: goal, target (knowledge/experience/
interests), hardFilters, softPreferences, retrievalQueries (3 arah), avoidMatchingOn.

```text
- retrievalQueries:
  offers:  "senior software developer yang mengajar pemula"
  interests: "software education dan mentoring pemula"
  needs:   "beginner yang antusias + konsisten berlatih"
- hardFilters: {"location": ..., "interactionTypes": [...]}
- avoidMatchingOn: ["sesama beginner yang mencari mentor"]
```

### 6.2 Match Judge — `match_judge.py:30`
Menilai shortlist dgn 4 kriteria: **Relevansi**, **Resiprositas/mutual value**,
**Interaction fit**, **Komplementaritas** (hindari mempertemukan dua pemula yang
butuh skill sama). Keluaran `{matches:[{userId,score,reason}]}`, skor 0–1.

### 6.3 Introduction — `introduction.py:55`
Membuat 3 hal tanpa menciptakan fakta atau membesar-besarkan kecocokan:
`whyThisPerson`, `whyYou`, `possibleOpener` (icebreaker konkret).

---

## 7. Persistensi & Tracing — `src/tracing/storage.py`

Semua observasi disimpan di DuckDB (`data/runs.duckdb`) agar evaluasi offline, audit,
dan perhitungan biaya bisa dilakukan. Tabel utama:

| Tabel | Isi | Ditulis di |
| :-- | :-- | :-- |
| `runs` | 1 baris per eksekusi pipeline + status/biaya | `new_run`/`finish_run` |
| `llm_calls` | tiap panggilan LLM/embedding (token, latency, error) | `add_call` |
| `retrieval_results` | similarity 3 arah + prescore tiap kandidat | `add_retrieval` |
| `match_results` | skor judge + intro + apakah ditampilkan | `add_match` |
| `profile_vectors` | index embedding 3 arah per profil | `upsert_vector_rows` |
| `human_evaluations` | rating manual (good/okay/bad) utk evaluasi | `add_evaluation` |

```python
def add_retrieval(self, run_id, rows):
    for row in rows:
        self._exec("insert into retrieval_results values (?,?,?,?,?,?,?,?,?)",
                   [run_id, row["candidate"]["id"], row["rank"],
                    row["offers_similarity"], row["interests_similarity"],
                    row["reciprocal_similarity"], row["interaction_score"],
                    row["prescore"], _json(row["candidate"])])
```

---

## 8. Ilustrasi Alur pada Satu Query

Contoh query *"aku butuh teman programmer di Bandung"*:

1. **Need Interpreter** → interactionType `[friendship, meeting_people]`,
   hardFilters location `Bandung`, retrievalQueries terarah.
2. **Retrieval** → `_filtered_with_meta` ambil kandidat Bandung yang
   `openTo` friendship/meeting; embed 3 query; union top-N; prescore.
3. **Prescore** → ranking deterministik; kandidat di luar filter premium dikurangi.
4. **Judge** (hanya 6-12 teratas) → skor mutual value + alasannya.
5. **Introduction** (paralel) → draft `whyThisPerson / whyYou / opener`.
6. **Persist** → catat di `runs`, `llm_calls`, `retrieval_results`, `match_results`.

Hasil tampil di notebook `07_live_test.py` (input query bebas) dengan ringkasan
status, retrieval, match, dan konsumsi token.

---

# Lampiran A — Penjelasan lebih sederhana

## A.1 Apa yang dilakukan sistem ini?

Sistem ini adalah **"mesin pencari manusia"**. Kamu mengetik kebutuhan dalam bahasa
biasa, misalnya:

> *"Aku butuh teman programmer di Bandung yang biasa mengajar pemula."*

Sistem lalu melakukan 5 langkah, seperti resepsionis yang sangat teliti:

1. **Memahami permintaanmu** — bukan sekadar kata kunci. Sistem tahu "teman
   programmer di Bandung" berarti *cari seseorang yang*:
   - bisa ngoding (skill),
   - tinggal di Bandung (lokasi),
   - terbuka diajak ngobrol/berteman (jenis interaksi),
   - dan bukan sekedar orang yang *juga butuh diajar* (komplementer, bukan doppleganger).

2. **Menyaring cepat dari ribuan orang** — dari ~2000 profil, hanya orang yang
   memenuhi syarat keras (lokasi, jenis interaksi) yang diteruskan, sekitar 30.

3. **Memberi skor sementara tanpa AI** — menghitung angka kecocokan cepat (0–1)
   berdasarkan: seberapa cocok skillnya, minatnya, saling-melengkapi, dll. Ini
   dilakukan dengan rumus matematika sederhana, bukan AI — jadi murah & cepat.

4. **Menimbang pakai AI (paling teliti)** — 6–12 kandidat terbaik dari langkah 3
   dinilai ulang oleh model AI yang membaca profil mereka dan **memberi alasan**
   kenapa kalian cocok (nilai timbal-balik).

5. **Menulis draft pesan pembuka** — untuk tiap orang yang cocok, AI menyiapkan:
   *kenapa orang ini tepat*, *kenapa kamu menarik buat dia*, dan *contoh chat pertama*
   supaya kamu tidak bingung memulai obrolan.

## A.2 Kenapa tidak langsung pakai AI dari awal?

Karena **biaya dan kecepatan**. AI yang membaca 2000 profil sekaligus akan lambat dan
mahal. Maka sistem memakai trik: *filter murah dulu (matematika), AI hanya untuk yang
paling menjanjikan*. Ini seperti penyisiran: pakai jaring rapat yang cepat, lalu
periksa satu-satu hanya ikan terbaik. Semua biaya & hasil dicatat supaya bisa dilihat
mana yang worth it.

## A.3 "3 arah" itu apa? (offers / interests / needs)

Setiap profil dipecah jadi 3 dokumen, ibarat **3 kartu nama**:
- **offers** — apa yang orang ini bisa berikan (skill, pengalaman, bantuan).
- **interests** — topik yang ia suka/pelajari.
- **needs** — apa yang ia cari (bantuan, rekan, mentor).

Dengan memisahkan 3 kartu ini, sistem bisa membedakan dua orang yang *sama-sama
bisa membantu* dari dua orang yang *saling membutuhkan* — yang pertama mungkin cuma
mirip, yang kedua benar-benar cocok timbal-balik.

## A.4 Apa itu `prescore` dan kenapa penting?

`prescore` = **skor cepat 0–1 buatan rumus, bukan AI**. Fungsinya menyortir supaya
AI (yang mahal) hanya bertemu kandidat terbaik. Kekuatannya:
- **Murah & deterministik** — hasilnya selalu sama untuk input sama.
- **Bisa dilihat/di-*debug*** — kenapa seseorang masuk shortlist, mudah dijelaskan.
- **Menjadi "rem" untuk hal-hal yang tidak diinginkan** — mis. sistem bisa
  menurunkan skor orang yang persis *tipe yang ingin kamu hindari*.

Skor akhir kombinasi: **70% penilaian AI + 30% prescore**, supaya kejelian AI tetap
dominan tapi prescore membantu memutus seri dan menahan kecocokan yang tipis.

---

# Lampiran B — Perhitungan Token & Biaya

## B.1 Apa itu token?

Model bahasa (LLM) tidak membaca huruf, melainkan **token** — potongan kecil teks
(~4 karakter, bisa sebagian kata). Model dikenai biaya per token yang **dibaca**
(input) dan per token yang **dihasilkan** (output). Contoh: kata *"programmer"*
mungkin terdiri dari 2–3 token.

## B.2 Dari mana angka token berasal?

Dua sumber di kode:

1. **Dari response API** — setiap provider mengembalikan objek `usage`:
   `usage_from_response` (`src/costs/calculator.py:22`) membaca:
   `input_tokens`, `cached_input_tokens` (token input yang di-cache sehingga lebih
   murah), `output_tokens`, `reasoning_tokens` (token "berpikir" model).

   ```python
   def usage_from_response(response):
       data = response.model_dump() if hasattr(response, "model_dump") else (response or {})
       usage = data.get("usage", {}) if isinstance(data, dict) else {}
       input_details = usage.get("input_tokens_details", {}) or {}
       output_details = usage.get("output_tokens_details", {}) or {}
       return {
           "input_tokens": int(usage.get("input_tokens", usage.get("prompt_tokens", 0)) or 0),
           "cached_input_tokens": int(input_details.get("cached_tokens", 0) or 0),
           "output_tokens": int(usage.get("output_tokens", 0) or 0),
           "reasoning_tokens": int(output_details.get("reasoning_tokens", 0) or 0),
           "total_tokens": int(usage.get("total_tokens", 0) or 0),
       }
   ```

2. **Perkiraan jika provider kosong** — jika `usage` kosong (beberapa provider
   OpenAI-compatible), `_estimated_usage` (`src/pipeline.py:222`) menghitung kasar:
   `token ≈ panjang karakter / 4`, lalu menandai sebagai estimasi di tracing.

   ```python
   def _estimated_usage(request, output_text):
       input_chars = len(request.get("instructions", "")) + len(str(request.get("input", "")))
       input_tokens = max(1, math.ceil(input_chars / 4))
       output_tokens = max(0, math.ceil(len(output_text or "") / 4))
       return {"input_tokens": input_tokens, "output_tokens": output_tokens, "total_tokens": input_tokens + output_tokens, ...}
   ```

## B.3 Rumus biaya (USD)

`estimate_cost` (`src/costs/calculator.py:37`) — model apa pun harga /1 juta token:

```python
def estimate_cost(usage, rates):
    if isinstance(rates, str):
        rates = pricing_for(rates)          # cari harga model
    return ((usage["input_tokens"] - usage["cached_input_tokens"]) * rates.input_per_million
            + usage["cached_input_tokens"] * rates.cached_input_per_million
            + usage["output_tokens"] * rates.output_per_million) / 1_000_000
```

Artinya:
```
biaya = (input_tokens − cached)*harga_input   +  cached*harga_cached   +  output*harga_output
        ─────────────────────────────── / 1_000_000 (karena harga per sejuta token)
```

### B.4 Harga model — `pricing.py:23`

| Model | Input /M | Cached /M | Output /M |
| :-- | --: | --: | --: |
| `gpt-5.6-terra` (judge) | $2.00 | $0.20 | $12.00 |
| `gpt-5.6-luna` (need/intro) | $0.20 | $0.02 | $1.20 |
| `text-embedding-3-large` | $0.13 | $0.13 | $0.0 |

Model kustom bisa diisikan via env `MODEL_PRICE_<NAMA>=<input>,<output>` (cached
mengikuti harga input). Model tanpa harga → estimasi **$0** (tidak crash).

## B.5 Contoh perhitungan penggalian

Bayangkan satu query → pipeline penuh dengan 6 match (pembulatan):

| Tahap | Panggilan | Input (token) | Output | Model | Perkiraan biaya |
| :-- | :-- | --: | --: | :-- | --: |
| Need Interpreter | 1 | 500 | 180 | luna | ~(500×0.2 + 180×1.2)/1M ≈ **$0.00032** |
| Embedding | 3 query | 90 | 0 | emb-3-large | ~(90×0.13)/1M ≈ **$0.00001** |
| Match Judge | 1 (12 kandidat) | 4000 | 400 | terra | ~(4000×2 + 400×12)/1M ≈ **$0.0128** |
| Introduction ×6 | 6 | 6×800 | 6×120 | luna | ~(4800×0.2 + 720×1.2)/1M ≈ **$0.00182** |
| **Total** | | | | | **≈ $0.015** |

> Rincian biaya per bagian (input/output saja) terlihat real di tabel **per-run
> token & cost** pada notebook `06_evals.py` / `07_live_test.py`, bersumber dari
> `src/evaluation/reporting.py` (`per_run_tokens`, `per_requester_tokens`) yang
> membaca tabel `llm_calls`.

## B.6 Token & biaya per requester

`per_requester_tokens(store)` mengagregasi `llm_calls` per `requester_id` di tabel
`runs` — jadi kita bisa lihat: *siapa paling boros / berapa total biaya per orang*.
Ini penting untuk memantau budget pemakaian dan mengecek apakah konfigurasi
(panjang shortlist, jumlah intro, model) sepadan dengan kualitas hasilnya.

---

# Lampiran C — Daftar Algoritma & Tech Stack

## C.1 Daftar Algoritma

| # | Nama | Fungsi | Lokasi | Rumus / Ide Inti |
| :-- | :-- | :-- | :-- | :-- |
| 1 | **Representasi 3-arah profil** | Memisahkan kemampuan vs kebutuhan tiap profil agar retrieval bisa membedakan *penyedia* vs *pencari* | `src/retrieval/embeddings.py:40` `profile_vectors` | Setiap profil dipecah jadi 3 dokumen: `offers` / `interests` / `needs` |
| 2 | **Cosine similarity** | Mengukur kemiripan semantik dua vektor embedding (0–1) | `embeddings.py:62` `cosine_similarity` | `sim = Σ(a·b) / (‖a‖·‖b‖)` |
| 3 | **Lexical similarity fallback** | Menghitung skor kemiripan murah saat embedding tidak tersedia (offline / provider mati) | `embeddings.py:67` `lexical_similarity` | Overlap token: `|A ∩ B| / √(|A|·|B|)` |
| 4 | **Union Top-N per dimensi** | Menggabungkan kandidat terbaik tiap arah agar yang kuat di satu arah tak terbuang | `src/retrieval/search.py:164` `_union_top_n` | Top-N per offers/interests/needs lalu union + dedup |
| 5 | **MMR — Maximal Marginal Relevance** | Mendiversifikasi shortlist agar tidak monoton (banyak kandidat mirip) | `search.py:190` `_mmr_rerank` | `argmax λ·relevansi − (1−λ)·kemiripan_dg_yg_terpilih` |
| 6 | **Hard filter + relax eksplisit** | Menerapkan syarat wajib (lokasi/interaksi) dan menandai relaksasi agar transparan | `search.py:133` `_filtered_with_meta` | Filter; jika kosong relaksasi dengan flag `interaction_relaxed` / `location_relaxed` |
| 7 | **Jaccard interaction score** | Menilai kesesuaian tipe interaksi requester vs `openTo` kandidat secara kontinu | `src/retrieval/prescore.py:15` `interaction_score` | `|req ∩ openTo| / |req ∪ openTo|` |
| 8 | **Weighted prescore** | Merangkum kecocokan jadi satu skor 0–1 untuk meranking shortlist | `prescore.py:107` `weighted_prescore` | `0.45·offers + 0.20·interests + 0.20·reciprocity + 0.15·interaction + boost − penalty`, clamp [0,1] |
| 9 | **Normalisasi min-max per dimensi** | Menyetarakan skala tiap arah agar dimensi dengan rentang besar tak mendominasi | `prescore.py:90` `normalize_dimensions` | `(x − min) / (max − min)` per arah; hanya untuk embedding |
| 10 | **Soft preference scoring** | Memberi bonus pada kandidat yang memenuhi preferensi lunak (non-wajib) | `prescore.py:35` `soft_preference_score` | Pecahan frase preferensi yang muncul di profil (token overlap) |
| 11 | **Avoidance penalty** | Menurunkan skor kandidat yang mencerminkan hal yang ingin dihindari requester | `prescore.py:58` `avoidance_penalty` | Jaccard/substring maks antara frase avoid vs profil → pengali < 1 |
| 12 | **Stemming ringan** | Menyamakan bentuk kata agar matching token lebih tahan terhadap variasi | `prescore.py:34` `_stem` | Hapus sufiks `ing/s/es/ies/ed`; `beginners≈beginner` |
| 13 | **Rerank gabungan** | Menggabungkan penilaian AI dan prescore jadi urutan akhir | `src/pipeline.py:378` `_rerank_with_prescore` | `combined = 0.7·judge + 0.3·prescore`, sort sebelum intro |
| 14 | **Pembatasan batch embedding** | Membangun index dalam potongan agar tidak melampaui limit input provider | `src/retrieval/index.py:18` `EmbeddingIndex.rebuild` | Embed per `batch_size=256` (&le;2048 item/request) |
| 15 | **Parsing JSON toleran** | Mengambil JSON valid dari output model yang berantakan (markdown/prosa) | `pipeline.py:48` `_parse_json_tolerant` | Ekstrak dari fence / prosa / objek pertama |
| 16 | **Koersi bentuk** (need/matches) | Menormalkan key & tipe output dari provider yang mengabaikan schema | `pipeline.py:77,107,174` `_coerce_need` / `_coerce_matches` | Map sinonim interaksi, ubah tipe string→list, isi default |
| 17 | **Structured Outputs / prompt-only JSON** | Memaksa model menghasilkan JSON sesuai kontrak | `pipeline.py:294` `_response` | OpenAI: `text.format=json_schema`; non-OpenAI: instruksi JSON di prompt |
| 18 | **Fallback stream → non-stream** | Menjaga pipeline tetap jalan saat provider menolak streaming | `pipeline.py:320` `_response` | Bila streaming gagal, POST HTTP tunggal |

## C.2 Tech Stack

| Lapisan | Teknologi | Peran | File kunci |
| :-- | :-- | :-- | :-- |
| Bahasa | **Python 3.12** | Runtime utama | — |
| Notebook | **Marimo 0.24** | Laboratorium interaktif (retrieval/judge/pipeline) | `03_retrieval.py`, `04_matching.py`, `05_end_to_end.py`, `06_evals.py`, `07_live_test.py` |
| Web framework/UI marimo | Marimo CRUD editor | Akses via browser + auth token | `Dockerfile` |
| LLM client | **OpenAI Python SDK** (`openai>=1.0`) | Responses API + embeddings | `src/config.py:make_client` |
| API LLM kustom | **Provider OpenAI-compatible** | LLM + embedding via `OPENAI_BASE_URL` | `.env` (`OPENAI_BASE_URL`) |
| Basis data observasi | **DuckDB** (`duckdb>=1.1`) | Persist runs/calls/retrieval/matches/index | `src/tracing/storage.py` |
| Manipulasi data | **pandas / numpy** | Analisis hasil eval | `src/evaluation/` |
| Env config | **python-dotenv** | Baca `.env` | `.env`, `src/config.py` |
| Testing | **pytest** | Unit/regression | `tests/test_retrieval.py`, `tests/test_pipeline_coercion.py`, dll |
| Kontainer | **Docker + docker compose** | Deploy marimo + cloudflared | `Dockerfile`, `docker-compose.yml` |
| Tunneling | **cloudflared** (Cloudflare Tunnel, token-based) | Ekspos marimo ke publik di belakang CF | `docker-compose.yml` (service `cloudflared`) |
| CI/CD | **GitHub Actions** (`deploy.yml`) | Auto-deploy saat push / manual dispatch | `.github/workflows/deploy.yml` |
| Hosting target | VM Ubuntu (root, Docker aktif) | Server tempat marimo + provider LLM berjalan | `scripts/server_deploy.sh` |

## C.3 Dependensi (requirements.txt)

```
marimo>=0.18.3     # notebook server + UI
openai>=1.0.0      # Responses & Embeddings API
duckdb>=1.1.0      # observability & index
python-dotenv>=1.0.0
pandas>=2.0.0
numpy>=1.26.0
```

## C.4 Lingkungan (`.env`)

| Variabel | Contoh | Fungsi |
| :-- | :-- | :-- |
| `OPENAI_API_KEY` | `sk-...` | Auth ke provider LLM |
| `OPENAI_BASE_URL` | `https://.../v1` | Gateway LLM OpenAI-compatible |
| `NEED_MODEL` / `JUDGE_MODEL` / `INTRODUCTION_MODEL` | `atomix` | Model per tahap |
| `EMBEDDING_MODEL` | `openrouter/openai/text-embedding-3-large` | Model embedding untuk index |
| `MODEL_PRICE_<NAMA>` | `0.2,1.2` | Harga kustom per juta token (input,output) |
| `MARIMO_PASSWORD` | `tecnofest` | Password akses notebook |
| `CF_TUNNEL_TOKEN` | `ey...` | Token Cloudflare Tunnel (dari dashboard Zero Trust) |

## C.5 Peta Modul `src/`

```
src/
├── pipeline.py          # orkestrasi + PipelineConfig + koersi + fallback
├── config.py            # provider_config, make_client, harga kustom
├── agents/
│   ├── need_interpreter.py   # prompt: query → need terstruktur
│   ├── match_judge.py        # prompt: shortlist → skor + alasan
│   └── introduction.py       # prompt: match → draft pesan pembuka
├── retrieval/
│   ├── embeddings.py    # profile_vectors, embedder, cosine/lexical
│   ├── index.py         # EmbeddingIndex (persisten + batch rebuild)
│   ├── search.py        # search_people, filter, union top-N, MMR
│   └── prescore.py      # interaction/Jaccard, normalisasi, soft/avoid
├── tracing/
│   ├── storage.py       # DuckDB: runs, llm_calls, retrieval, matches, index
│   └── trace.py         # make_trace per LLM call
├── costs/
│   ├── calculator.py    # usage_from_response, estimate_cost
│   └── pricing.py       # tabel harga model
└── evaluation/
    └── reporting.py, metrics.py   # token per run/requester + metrik ranking
```
