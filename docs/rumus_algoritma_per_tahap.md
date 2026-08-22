# Dokumentasi Rumus & Algoritma per Tahap Pipeline

Dokumen ini menjabarkan **setiap rumus/algoritma** yang dipakai di tiap tahap
pipeline matching. Setiap rumus diberi:

- **Rumus** — bentuk matematis / kode
- **Contoh angka** — agar gampang dibayangkan
- **Kenapa ini?** — alasan pemilihan
- **Lokasi kode** — tempat diterapkan

---

## Daftar Isi per Tahap

| Tahap | Rumus / algoritma |
| :-- | :-- |
| T0. Fondasi | Representasi profil 3-arah |
| T1. Embedding | Batch embedding, cosine similarity, fallback lexical |
| T2. Retrieval | Hard filter+relax, union top-N, MMR |
| T3. Prescore | Interaction score (Jaccard), normalisasi min-max, soft/avoid, weighted prescore |
| T4. Match Judge | Isolasi prescore, rerank gabungan |
| T5. Introduction | Intro paralel, parsing output |
| T6. Persist | Skema tabel, perhitungan cost |

---

# T0. Fondasi — Representasi Profil 3-Arah

**Lokasi:** `src/retrieval/embeddings.py:40` — `profile_vectors`

Setiap profil dipecah jadi 3 dokumen yang di-embed terpisah:

```
offers    = knowledge + experience + canHelpWith      # apa yang bisa ia berikan
interests = interests + deskripsi_proyek              # topik yang ia sukai
needs     = lookingFor + openTo                        # apa yang ia cari/terbuka
```

**Contoh** — profil "Maya: founder marketplace kampus":
- `offers` → *"campus distribution; early user acquisition; launcher marketplace; ..."*
- `interests` → *"student entrepreneurship; marketplaces; ..."*
- `needs` → *"design feedback; advice; mentoring"*

**Kenapa harus ini?** Karena tujuannya *mutual matching*. Memisahkan
"sumbu pemberi" (offers) dan "sumbu pencari" (needs) membuat sistem bisa
menemukan pasangan yang **saling melengkapi**, bukan dua orang yang sama-sama
butuh. (Lihat juga bahasan "kenapa tidak 1 arah" di dokumen alur).

---

# T1. Embedding

## T1.1 Batch Embedding

**Lokasi:** `src/retrieval/index.py:18` — `EmbeddingIndex.rebuild`

```
untuk tiap chunk 256 dokumen:
    embed(chunk) → vektor
simpan semua ke tabel profile_vectors
```

**Contoh:** 6000 dokumen (2000 profil × 3 arah) → 24 panggilan embedding,
tiap panggilan 256 teks. Hasil: 6000 vektor tersimpan sekali untuk dipakai
semua query berikutnya.

**Kenapa harus ini?** Provider embedding membatasi ukuran satu request
(mis. ≤ 2048 item). Pecah per 256 berada di bawah limit dan tetap cepat.

---

## T1.2 Cosine Similarity

**Lokasi:** `src/retrieval/embeddings.py:62`

```
cosine(A, B) = Σ(Aᵢ·Bᵢ) / ( ‖A‖ · ‖B‖ ),  dengan ‖X‖ = √Σ Xᵢ²
```

Hasil **0–1**: 1 = sangat mirip, 0 = tak berkaitan.

**Contoh:** dua vektor kecil `A=[1,2,3]`, `B=[2,4,6]` (arah sama, panjang beda)
→ cosine **1.0**, karena hanya memakai arah, bukan panjang.

**Kenapa harus ini?** Dokumen bisa beda panjang (teks pendek vs panjang) tapi
makna sama. Cosine mengabaikan besaran — hanya sudut. Euclidean (jarak) akan
menganggap yang lebih panjang "jauh", padahal maknanya sama.

---

## T1.3 Fallback Lexical

**Lokasi:** `src/retrieval/embeddings.py:67`

```
lexical(A, B) = |token(A) ∩ token(B)| / √( |token(A)| · |token(B)| )
```

**Contoh:** A="python mentoring", B="python untuk pemula"
→ token A={python,mentoring}, B={python,pemula} → iris{python}=1
→ `1 / √(2·2) = 0.5`.

**Kenapa harus ini?** Digunakan hanya bila embedding tak tersedia/mati, agar
pipeline **tidak crash** dan tetap memberi peringkat yang masuk akal. Kasar tapi
lebih baik daripada error.

---

# T2. Retrieval

## T2.1 Hard Filter + Relaksasi Eksplisit

**Lokasi:** `src/retrieval/search.py:133` — `_filtered_with_meta`

```
kandidat = { p ∉ requester  dan  p.match(lokasi)  dan  p.match(interactionTypes) }
if kandidat kosong dan ada filter lokasi:
    kandidat = p.pada(lokasi)         # relaksasi interaksi, flag = interaction_relaxed
if masih kosong:
    kandidat = semua kecuali requester # flag = location_relaxed
```

**Contoh:** filter "Bandung + mentoring" → 0 hasil → relaksasi ke "semua Bandung"
dan tandai `interaction_relaxed`, supaya user tahu kualitas waktu itu diturunkan.

**Kenapa harus ini?** Syarat wajib tidak boleh dilanggar diam-diam, tapi hasil
kosong juga tidak bermanfaat. Relaksasi **sadar + flag** = transparan,
mudah di-*audit*.

---

## T2.2 Union Top-N per Dimensi

**Lokasi:** `src/retrieval/search.py:165` — `_union_top_n`

```
untuk tiap dim di {offers, interests, reciprocal}:
    ambil top-N kandidat (urut similarity turun)
id_keep = gabungan (union) semua id itu
hasil   = semua baris yang id-nya ada di id_keep, lalu dedup
```

**Contoh:** per_dimension=50 → tiap arah ambil 50 terbaik → union → biasanya
~86 kandidat unik (bukan 150, karena banyak yang muncul di >1 arah).

**Kenapa harus ini?** Kalau hanya "rata-rata", orang yang sangat kuat di
**satu** arah (mis. offers tinggi) bisa kalah oleh orang yang sedang-sedang di
semua arah. Union memastikan bakat menonjol di satu dimensi tetap masuk.

---

## T2.3 MMR — Diversifikasi (opsional)

**Lokasi:** `src/retrieval/search.py:191` — `_mmr_rerank`

```
skor_seleksi = λ · prescore − (1−λ) · max(jaccard(candidate, tiap yg sudah dipilih))
pilih satu per satu yang skornya tertinggi
```

dengan `λ` default `0.7` (relevansi 70%, keberagaman 30%).

**Contoh:** 12 teratas awalnya 10 "backend Python". MMR menukar beberapa dengan
"mobile" / "infra" yang masih relevan tapi berbeda — hasil akhir campuran.

**Kenapa harus ini?** Ranking murni skor cenderung penuh orang kembar. MMR
memaksa keberagaman agar user dapat **pilihan**, tanpa mengorbankan relevansi
terlalu jauh.

---

# T3. Prescore

## T3.1 Interaction Score (Jaccard kontinu)

**Lokasi:** `src/retrieval/prescore.py:15`

```
interaction = |request ∩ openTo| / |request ∪ openTo|
```

**Contoh:** request `{advice, mentoring}`, openTo `{advice}`:
- iris = {advice} → 1
- gabung = {advice, mentoring} → 2
- skor = **0.5**

Versi kontinu (bukan 0/0.5/1) supaya "overlap 1 dari 2" (0.5) ≠
"overlap 1 dari 3" (0.33).

**Kenapa harus ini?** Tipe interaksi adalah **himpunan kecil diskret**; Jaccard
adalah ukuran standar kemiripan himpunan — cocok dipakai langsung sebagai
komponen skor.

---

## T3.2 Normalisasi Min-Max per Dimensi

**Lokasi:** `src/retrieval/prescore.py:90`

```
nilai' = (x − min) / (max − min)      # per arah
```

**Contoh:** offers di kandidat berkisar 0.7–0.9, needs 0.0–0.3. Tanpa
normalisasi, needs yang "kecil" tak akan pernah memengaruhi; setelah
normalisasi keduanya di skala 0–1 setara.

**Kenapa harus ini?** Tiap dimensi cosine rentangnya beda. Tanpa penyetaraan,
dimensi bernilai bes-ar mendominasi bobot **hanya karena skalanya**, bukan karena
penting. (Khusus jalur embedding; lexical di-skip agar noise tidak ter-inflasi.)

---

## T3.3 Soft Preference & Avoidance

**Lokasi:** `src/retrieval/prescore.py:35` & `:58`

```
soft_boost  = fraksi frase preferensi yg cocok (0-1)       # mis. "Bandung"
avoid_penalty = jaccard maks frase avoid vs profil (0-1)    # mis. "cari bayaran"
```

Keduanya dipakai sebagai penyesuaian prescore: `+min(0.12, soft_boost·0.15)`
dan `× (1 − 0.8·avoid_penalty)`.

**Contoh:** preferensi "Bandung" cocok → boost +0.05; kandidat punya frasa
yang ingin dihindari → × 0.8 → skor turun ~20%.

**Kenapa harus ini?** Kondisi lunak boleh tidak dipenuhi tapi **tetap harus
memiringkan** hasil; kondisi larangan harus menurunkan, agar pola buruk
(mempertemukan dua orang yang sama-sama butuh) tidak terulang.

---

## T3.4 Weighted Prescore (rumus utama)

**Lokasi:** `src/retrieval/prescore.py:107`

```
prescore = 0.45·offers + 0.20·interests + 0.20·reciprocal + 0.15·interaction
           + min(0.12, soft_boost·0.15)
           × (1 − 0.8·avoid_penalty)
           → clamp [0,1]
```

**Contoh lengkap:**

| Komponen | Skor | Bobot | Kontribusi |
| :-- | :-- | :-- | :-- |
| offers | 0.90 | 0.45 | 0.405 |
| interests | 0.70 | 0.20 | 0.140 |
| reciprocal | 0.50 | 0.20 | 0.100 |
| interaction | 1.00 | 0.15 | 0.150 |
| **jumlah** | | | **0.795** |
| + soft_boost | 0.05 | | 0.050 |
| − avoidance(0) | 0 | | 0.000 |
| **prescore** | | | **0.845** |

**Kenapa bobot ini?** offers paling menentukan (45% — bisakah dia membantu),
interest 20% (kesamaan minat), reciprocal 20% (saling melengkapi), interaction
15% (mau diajak dengan gaya itu). Bobot bisa diubah di `.env` tanpa kode → A/B
mudah.

---

# T4. Match Judge

## T4.1 Isolasi Prescore dari Judgele (anti-anchoring)

**Lokasi:** `src/pipeline.py:440`

**Rumus:** (bukan perhitungan — desain payload)

```
payload_kandidat = pakai PROFIL saja, TANPA prescore    # bila isolate=True
```

**Contoh:** shortlist 12 orang dikirim ke AI cuma dengan profil (name, headline,
knowledge, ...), bukan `0.45·offers+...`. AI menilainya sendiri, tidak tahu skor
rumus.

**Kenapa harus ini?** AI yang tahu "orang ini skor 0.9" cenderung **ikut-ikutan**
(anchoring). Menghapus skor memaksa AI menilai murni dari profil → penilaian
independen, tidak bias rangking rumus.

---

## T4.2 Rerank Gabungan

**Lokasi:** `src/pipeline.py:378` — `_rerank_with_prescore`

```
final = 0.7 · judge_score + 0.3 · prescore
```

**Contoh:** AI beri skor 0.8, prescore 0.845 → `0.7·0.8 + 0.3·0.845 = 0.815`.

Urutan akhir diurutkan berdasarkan `final`, sebelum intro dibuat.

**Kenapa harus ini?** AI peka nuansa tapi kadang tak konsisten; rumus konsisten
tapi kasar. 0.7/0.3 membuat kualitas AI dominan, 30% rumus memutus seri &
menahan lonjakan skor AI yang ekstrem.

---

# T5. Introduction

## T5.1 Intro Paralel

**Lokasi:** `src/pipeline.py:462`

**Rumus latensi:**

```
latensi_total ≈ waktu_satu_call · ⌈N / 4⌉      (paralel, maks 4 thread)
vs sekuensial ≈ waktu_satu_call · N
```

**Contoh:** 6 match, tiap intro 2 detik → sekuensial 12 detik; paralel ≈
`2 · ⌈6/4⌉ = 4 detik`.

**Kenapa harus ini?** Panggilan intro = N kali (pengali volume). Paralel menekan
latensi tanpa biaya ekstra — hanya memakai thread yang menganggur menunggu
respon.

---

## T5.2 Parsing & Koersi Output

**Lokasi:** `src/pipeline.py:48` & `:174`

**Proses:** ambil JSON dari output model (meski dibungkus markdown/prosa),
normalisasi key/tipe (`whyThisPerson`, `whyYou`, `possibleOpener` konsisten).

**Kenapa harus ini?** Output model sering tidak rapi; normalisasi menjamin hasil
yang disimpan & ditampilkan selalu punya bentuk sama, tidak crash saat render.

---

# T6. Persist

## T6.1 Skema Tabel Observasi

**Lokasi:** `src/tracing/storage.py`

| Tabel | Granularitas | Menjawab pertanyaan |
| :-- | :-- | :-- |
| `runs` | 1 baris / eksekusi | "berapa biaya/latensi total per query?" |
| `llm_calls` | 1 baris / panggilan | "berapa token/biaya per call?" |
| `retrieval_results` | 1 baris / kandidat | "berapa recall retrieval?" |
| `match_results` | 1 baris / match | "match + intro apa saja?" |

**Kenapa harus ini?** Granularitas terpisah → query analitik presisi per dimensi;
mencampur semuanya membuat tab el tidak bisa menjawab satu jenis pertanyaan.

## T6.2 Perhitungan Token & Biaya

**Lokasi:** `src/costs/calculator.py`

```
biaya = (input − cached)·h_input + cached·h_cached + output·h_output
        ────────────────────────────────────────────────────────  (per 1 juta token)
```

**Contoh:** model dgn h_input $2/1jt, h_output $12/1jt; call input 4000, output 400
→ `(4000·2 + 400·12)/1_000_000 = $0.0128`.

**Kenapa harus ini?** Provider memberi jumlah token bukan rupiah. Rumus ini
mengubah token → biaya dengan harga per model yang bisa diset di `.env`
(`MODEL_PRICE_<NAMA>`). Tanpa cache/input/output bisa di-*cost*-per-call.

---

# Lampiran — Peta Singkat Rumus → Tahap

| Rumus | Tahap | Sifat |
| :-- | :-- | :-- |
| Representasi 3-arah | fondasi | data |
| Batch embedding | T1 | I/O |
| Cosine similarity | T1/T2 | hitung |
| Fallback lexical | T1 | hitung |
| Hard filter + relax | T2 | logika |
| Union top-N | T2 | logika |
| MMR | T2 (opsional) | hitung |
| Jaccard interaction | T3 | hitung |
| Min-max normalization | T3 | hitung |
| Soft/avoid | T3 | hitung |
| Weighted prescore | T3 | hitung |
| Isolasi prescore | T4 | desain |
| Rerank 0.7/0.3 | T4 | hitung |
| Intro paralel | T5 | I/O |
| Parsing/koersi | T5 | logika |
| Skema tabel | T6 | data |
| Hitung cost | T6 | hitung |