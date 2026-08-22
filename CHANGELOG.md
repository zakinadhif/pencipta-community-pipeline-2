# Changelog



Branch `dev/denisetiya` menangani retrieval, prescore, dan orkestrasi matching.

### 1. Precomputed embedding index

- **Sebelum:** Setiap pencarian meng-embed semua profil kandidat secara live —
  `search_people` memanggil `embedder.embed(3 + 3 × N)` teks per query. Dengan
  100 profil hal ini masih terjangkau; dengan ribuan profil, biaya API dan
  latensi per pencarian membengkak seiring ukuran korpus.
- **Sesudah:** Tabel `profile_vectors` yang persisten di `data/runs.duckdb`
  (3 vektor per profil: offers / interests / needs), dibangun sekali lewat
  `EmbeddingIndex.rebuild(...)`. Pencarian hanya meng-embed 3 teks query dan
  memuat vektor dari index. Index kosong → fallback leksikal (notebook offline
  tetap jalan tanpa API key).
- **Mengapa:** Handoff menspesifikasikan embedding sebagai `profile_embeddings`
  yang di-precompute; meng-embed semua profil per pencarian tidak skalabel dan
  bertentangan dengan invarian "retrieval terjadi sebelum penalaran yang mahal".

### 2. Restrukturisasi `search_people`

- **Sebelum:** Satu daftar datar semua kandidat, masing-masing dengan 3 nilai
  cosine similarity, dipotong mentah oleh `limit` sebelum di-rank.
- **Sesudah:** Top-N per dimensi → weighted union + dedup → hard filter →
  buang requester → prescore → shortlist terurut. `limit` menjadi batas keras
  hasil akhir. Parameter baru: `per_dimension_count`, `min_prescore`.
- **Mengapa:** Handoff 10 menspesifikasikan retrieval terarah top-N per dimensi
  embedding sebelum union; daftar datar saat ini kehilangan recall per-dimensi
  dan mencampur requester sebelum shortlist.

### 3. Prescore + orkestrasi pipeline

- **Sebelum:** Interaction score bersifat biner (uji overlap 0/1) dan logika
  prescore diduplikasi antara `pipeline._retrieve` dan `03_retrieval.py`.
- **Sesudah:** Interaction score menjadi 0 / 0.5 / 1 (overlap 2+ tipe interaksi
  = 1, tepat 1 = 0.5, tidak ada = 0). Prescore tinggal di satu tempat di
  `src/retrieval/prescore.py`, hasil jumlah tertimbang di-clamp ke rentang
  [0, 1]. `pipeline._retrieve` mendelegasikan ke `search_people`.
- **Mengapa:** Satu sumber kebenaran mencegah pipeline dan notebook melenceng;
  interaction fit non-biner memberi imbalan pada kandidat yang benar-benar
  menyambut tipe interaksi yang diminta.

### 4. Matching — threshold judge

- **Sebelum:** Setiap match dari judge, sekecil apa pun skornya, tetap mendapat
  panggilan introduction dan ditampilkan sebagai hasil.
- **Sesudah:** `min_judge_score` baru di `PipelineConfig` (default 0.0 =
  perilaku lama). Match di bawah threshold tetap dicatat dengan `shown=false`
  (transparan untuk evaluasi) tetapi dilewati untuk introduction dan
  disembunyikan dari hasil yang ditampilkan.
- **Mengapa:** Match lemah memakan biaya per pencarian (panggilan introduction)
  dan mengotori hasil. Mencatatnya sebagai tersembunyi menjaga recall tetap
  terukur sambil menurunkan biaya.

### 5. Laporan konsumsi token AI

- **Sebelum:** Tidak ada laporan token per pencarian maupun per user.
- **Sesudah:** `src/evaluation/reporting.py` menyediakan `per_run_tokens(store)`
  dan `per_requester_tokens(store)` dari tabel `llm_calls` + `runs` di DuckDB.
  Ditampilkan di `06_evals.py` sebagai tabel "Per-run token & cost detail" dan
  "Token consumption per requester".
- **Mengapa:** Kamu ingin tahu konsumsi token AI secara per-run dan agregat per
  user.

### 6. Seed data 2.000 profil

- **Sebelum:** Dataset sintetis 100 profil.
- **Sesudah:** `data/generate_synthetic_profiles.py` memperluas ke 2.000 profil
  deterministik (id unik `synthetic-XXXX`), diuji di `test_profiles.py`.
- **Mengapa:** Arena uji skala "kualitas + performa": membuktikan biaya
  embedding per pencarian konstan saat index dipakai.

### 7. Provider OpenAI-compatible kustom via `.env`

- **Sebelum:** Hanya OpenAI resmi: client dibuat dengan `OpenAI(api_key=...)`,
  model default `gpt-5.6-*` dan `text-embedding-3-large`.
- **Sesudah:** `src/config.py` menyediakan `provider_config()` dan
  `make_client()`; `OPENAI_BASE_URL` (misal `https://.../v1`) di `.env` membuat
  client memakai base URL tersebut. Model per tahap bisa di-set lewat
  `NEED_MODEL` / `JUDGE_MODEL` / `INTRODUCTION_MODEL` / `EMBEDDING_MODEL`, dan
  harga per model kustom via `MODEL_PRICE_<NAMA>=<input>,<output>`.
  `pricing_for` mengembalikan harga 0 (tidak crash) untuk model tanpa harga.
  URL asli hanya ada di `.env` (ter-ignore); tidak pernah di test/repo.
- **Mengapa:** Kamu ingin memakai provider kustom yang OpenAI-API-compatible
  dengan API key, base URL, dan model khusus, yang dikonfigurasi di `.env`.

### 8. Normalisasi adaptif untuk provider non-OpenAI

- **Sebelum:** Pipeline mengandalkan Structured Outputs (`text.format`) dari
  Responses API; provider kustom (mis. gateway di belakang Cloudflare) menolak
  streaming SDK, mengabaikan schema, dan mengembalikan JSON dengan key/tipe
  berbeda (mis. `candidateId` bukan `userId`, `interactionType` string).
- **Sesudah:**
  - Fallback **stream → non-stream** (HTTP langsung dengan User-Agent curl)
    bila SDK streaming diblokir provider.
  - Untuk base_url non-OpenAI, `text.format` tidak dikirim; instruksi JSON
    ditambahkan ke prompt (`_json_only_instruction`).
  - Parsing toleran (`_parse_json_tolerant`) menangkap JSON dari markdown/prose.
  - `_coerce_need` menormalisasi tipe need (target/hardFilters/retrievalQueries),
    memetakan sinonim interaksi ("mentorship"→"mentoring") ke set kanonik.
  - `_coerce_matches` menerima `userId`/`candidateId`/`id` dan nilai skor
    alternatif (`score`/`matchScore`).
  - `search_people` auto-fallback ke `lexical_similarity` saat embedding gagal.
  - `PipelineConfig` default model dari `.env` (bukan hardcode `gpt-5.6-*`).
  - Prompt `need_interpreter` v2 menetapkan kontrak output (interactionType
    kanonik, bentuk target/hardFilters/retrievalQueries).
- **Mengapa:** Agar pipeline tetap berjalan dan menghasilkan match yang bagus
  di provider kustom yang tidak mendukung Structured Outputs. Hasil live:
  query "student organization" → sarah (0.95) + intro benar; "senior dev
  teaching beginners" → raka (0.85) + intro benar.

## Status implementasi

Keempat bagian desain (precomputed index, restrukturisasi `search_people`,
prescore terpusat, threshold judge) **sudah diimplementasikan**, ditambah
laporan token per-run/per-user, seed 2.000 profil, provider kustom via `.env`,
normalisasi adaptif untuk provider non-OpenAI, dan perbaikan retrieval deterministik
bab 9 (Jaccard, adaptive normalize, soft/avoid, MMR, judge isolasi, rerank 0.7/0.3,
intro paralel). Verifikasi akhir: 38 test pass, keenam notebook lolos `marimo check`,
`git diff --check` bersih, pipeline live end-to-end berhasil di provider kustom
(results sesuai harapan), dan tuning offline `hits@10 6/7` stabil.

### 9. Retrieval deterministik: prescore kontinu, normalisasi adaptif, soft/avoid & MMR

- **Sebelum:**
  - `interaction_score` diskrit 0/0.5/1.0 (overlap 1 dari 3 sama dengan 1 dari 2).
  - Similarity 3 dimensi dicampur tanpa normalisasi — dimensi dengan scale cosine tinggi mendominasi.
  - `softPreferences` dan `avoidMatchingOn` dari need interpreter di-coerce tapi tidak pernah dipakai di ranking.
  - Filter hard relax diam-diam (drop interaction type jika 0 kandidat) tanpa sinyal ke caller.
  - `per_dimension_count == retrieval_count == 30` — tuning recall vs limit terkunci.
  - Shortlist homogen — top offers similarity bisa isi seluruh top-N dengan profil mirip.
  - `prescore` dibocorkan ke judge (`_compact(...) | {"prescore": ...}`) → anchoring LLM.
  - Intro sequential per match — latensi linear dengan jumlah match.
  - Ranking akhir murni `judge_score`.
- **Sesudah:**
  - `interaction_score` Jaccard kontinu `|req∩cand|/|req∪cand|` di `src/retrieval/prescore.py:15` — backward-compat 2/2=1.0, 1/2=0.5.
  - `normalize_dimensions` min-max per dimensi hanya untuk jalur embedding (`_source=="embedding"`); jalur lexical skip normalisasi agar noise sparse tidak terinflasi — `src/retrieval/search.py:119`.
  - `soft_preference_score` (boost aditif cap +0.12) + `avoidance_penalty` (dampener multiplikatif 0.8, Jaccard + substring + stemmer jamak) wired ke `weighted_prescore` — `prescore.py:35,58,107`.
  - `_filtered_with_meta` return `(candidates, flag)` eksplisit `none|interaction_relaxed|location_relaxed` — `search.py:133`.
  - `PipelineConfig` split `retrieval_per_dimension=50` vs `retrieval_count=30`, `min_prescore=None` (non-filtering default setelah tuning — lexical top `0.13` akan kill recall bila `0.15`), `normalize_similarities`, `diversify_retrieval`, `mmr_lambda=0.7` — `pipeline.py:25`.
  - `_mmr_rerank` MMR `λ*prescore − (1−λ)*max_jaccard` opt-in `diversify=True` — `search.py:190`.
  - Judge isolasi: `Pipeline.run` tidak kirim `prescore` bila `isolate_prescore_from_judge=True` (default); `run_judge_experiment` hormati `include_prescore` — `pipeline.py:440`.
  - `_rerank_with_prescore` combined `0.7*judge + 0.3*prescore`, sort sebelum intro, `combined_score` persist di `match_results` — `pipeline.py:378,452`.
  - Intro paralel `ThreadPoolExecutor(max 4)` bila `parallel_intro=True` dan `len>1`, preserve rerank order — `pipeline.py:462`.
- **Mengapa:** Menutup semua lubang audit retrieval→prescore→orkestrasi: prescore kontinu & scale-invariant, preferensi/avoid benar-benar memengaruhi ranking, recall per-dimensi terpisah dari limit, diversity terkontrol, judge tidak ter-anchoring, ranking final gabungkan sinyal deterministik + LLM, latensi intro turun. Hasil tuning offline (lexical fallback, provider embedding `403`): `hits@10 6/7` stabil; `min_prescore 0.15` kill recall → default `None`; embedding path tetap normalize adaptif.
- **Verifikasi:** `38 passed`, `normalize=True` adaptif vs `False` sama `6/7`; `avoid ranked expert 0.92 vs beginner 0.03` benar; MMR tidak crash; `PipelineConfig` import ok.

## Belum rilis / direncanakan

