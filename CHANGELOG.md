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

