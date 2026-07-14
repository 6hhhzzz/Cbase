#!/usr/bin/env python3
"""Comprehensive audit of knowledge_chunks table."""

import asyncio
import asyncpg
from datetime import datetime

DB_DSN = "postgresql://kes:kes123@localhost:5432/kes"


async def main():
    conn = await asyncpg.connect(DB_DSN)
    print("=" * 100)
    print("AUDIT REPORT: knowledge_chunks table")
    print(f"Timestamp: {datetime.now().isoformat()}")
    print("=" * 100)

    # ── 1. Basic table info ──
    total = await conn.fetchval("SELECT COUNT(*) FROM knowledge_chunks")
    total_docs = await conn.fetchval("SELECT COUNT(DISTINCT doc_id) FROM knowledge_chunks")
    total_src = await conn.fetchval("SELECT COUNT(DISTINCT source_file) FROM knowledge_chunks")
    print(f"\nTotal chunks:   {total}")
    print(f"Total documents: {total_docs}")
    print(f"Total source files: {total_src}")

    # per-document stats
    doc_stats = await conn.fetch("""
        SELECT doc_id, source_file, COUNT(*) AS cnt,
               MIN(chunk_index) AS min_idx, MAX(chunk_index) AS max_idx,
               MIN(LENGTH(chunk_text)) AS min_len,
               MAX(LENGTH(chunk_text)) AS max_len,
               ROUND(AVG(LENGTH(chunk_text)))::int AS avg_len
        FROM knowledge_chunks
        GROUP BY doc_id, source_file
        ORDER BY COUNT(*) DESC
    """)

    # ── 2. Document Inventory ──
    print("\n" + "=" * 100)
    print("PART 1: DOCUMENT INVENTORY")
    print("=" * 100)

    header = f"{'#':>3} {'Chunks':>7} {'AvgLen':>6} {'Min':>5} {'Max':>5}  {'Source File':<55} {'Classification'}"
    print(header)
    print("-" * len(header))

    # Known real/fake patterns
    real_phrases = ['员工手册', 'employee handbook', 'handbook', 'chapter',
                    '手册', '制度', '规范', '项目', 'introduction', 'overview',
                    'policy', '公司', '组织', '架构', '职责', '岗位', '招聘',
                    '培训', '薪酬', '绩效', '考核', '数据', 'platform', '系统',
                    '安全', '技术', '设计', '合规', '流程', '管理办法', '实施方案']
    fake_phrases = ['test', '测试', 'demo', '示例', 'sample', 'mock', '模拟',
                    'dummy', '假', 'temp', 'temporary', 'lorem', 'ipsum',
                    '随机', '测试数据', '占位']

    for idx, r in enumerate(doc_stats):
        # Get first 500 chars of chunk_text for classification
        sample = await conn.fetchval("""
            SELECT chunk_text FROM knowledge_chunks
            WHERE source_file = $1 AND doc_id = $2
            ORDER BY chunk_index LIMIT 1
        """, r['source_file'], r['doc_id'])
        sample_lower = (sample or "").lower()[:500]

        real_score = sum(2 for p in real_phrases if p in sample_lower or p.lower() in r['source_file'].lower())
        fake_score = sum(2 for p in fake_phrases if p in sample_lower or p.lower() in r['source_file'].lower())

        if fake_score >= 2 and real_score == 0:
            classification = "FAKE (test data)"
        elif fake_score >= 4:
            classification = "FAKE (strong indicators)"
        elif real_score >= 4 and fake_score == 0:
            classification = "REAL document"
        elif real_score >= 2 and real_score > fake_score:
            classification = "LIKELY REAL"
        elif fake_score > 0:
            classification = "LIKELY FAKE"
        else:
            classification = "UNCERTAIN"

        src = r['source_file'][:53]
        print(f"{idx:>3} {r['cnt']:>7} {r['avg_len']:>6} {r['min_len']:>5} {r['max_len']:>5}  {src:<55} {classification}")

    # ── 3. Chunk Quality Check ──
    print("\n" + "=" * 100)
    print("PART 2: CHUNK QUALITY CHECK")
    print("=" * 100)

    stats = await conn.fetchrow("""
        SELECT
            COUNT(*) AS total,
            ROUND(AVG(LENGTH(chunk_text)))::int AS avg_len,
            MIN(LENGTH(chunk_text)) AS min_len,
            MAX(LENGTH(chunk_text)) AS max_len,
            ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY LENGTH(chunk_text)))::int AS median_len,
            ROUND(STDDEV(LENGTH(chunk_text)))::int AS stddev_len,
            ROUND(PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY LENGTH(chunk_text)))::int AS p25,
            ROUND(PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY LENGTH(chunk_text)))::int AS p75
        FROM knowledge_chunks
    """)
    print(f"  Total chunks:          {stats['total']}")
    print(f"  Average chunk length:  {stats['avg_len']} chars")
    print(f"  Median chunk length:   {stats['median_len']} chars")
    print(f"  P25 / P75:             {stats['p25']} / {stats['p75']}")
    print(f"  StdDev chunk length:   {stats['stddev_len']} chars")
    print(f"  Min chunk length:      {stats['min_len']} chars")
    print(f"  Max chunk length:      {stats['max_len']} chars")

    # Short chunks
    short = await conn.fetch("""
        SELECT chunk_text, chunk_index, source_file, LENGTH(chunk_text) AS len
        FROM knowledge_chunks
        WHERE LENGTH(chunk_text) < 50
        ORDER BY len, source_file
        LIMIT 30
    """)
    short_total = await conn.fetchval("SELECT COUNT(*) FROM knowledge_chunks WHERE LENGTH(chunk_text) < 50")
    print(f"\n  Chunks < 50 chars: {short_total} total (showing up to 30)")
    for c in short:
        txt = c['chunk_text'][:80].replace('\n', '\\n')
        print(f"    [{c['source_file']} idx={c['chunk_index']}] ({c['len']}c): \"{txt}\"")

    vshort = await conn.fetchval("SELECT COUNT(*) FROM knowledge_chunks WHERE LENGTH(chunk_text) < 20")
    if vshort:
        print(f"    (of which < 20 chars: {vshort})")

    # Long chunks
    long_total = await conn.fetchval("SELECT COUNT(*) FROM knowledge_chunks WHERE LENGTH(chunk_text) > 2000")
    long_chunks = await conn.fetch("""
        SELECT chunk_text, chunk_index, source_file, LENGTH(chunk_text) AS len
        FROM knowledge_chunks
        WHERE LENGTH(chunk_text) > 2000
        ORDER BY len DESC
        LIMIT 20
    """)
    print(f"\n  Chunks > 2000 chars: {long_total} total (showing up to 20)")
    for c in long_chunks:
        txt = c['chunk_text'][:120].replace('\n', '\\n')
        print(f"    [{c['source_file']} idx={c['chunk_index']}] ({c['len']}c): \"{txt}...\"")

    # Length distribution
    dist = await conn.fetch("""
        SELECT
            CASE
                WHEN LENGTH(chunk_text) < 50 THEN '<50'
                WHEN LENGTH(chunk_text) < 100 THEN '50-100'
                WHEN LENGTH(chunk_text) < 200 THEN '100-200'
                WHEN LENGTH(chunk_text) < 300 THEN '200-300'
                WHEN LENGTH(chunk_text) < 400 THEN '300-400'
                WHEN LENGTH(chunk_text) < 600 THEN '400-600'
                WHEN LENGTH(chunk_text) < 800 THEN '600-800'
                WHEN LENGTH(chunk_text) < 1000 THEN '800-1000'
                WHEN LENGTH(chunk_text) < 1500 THEN '1000-1500'
                WHEN LENGTH(chunk_text) < 2000 THEN '1500-2000'
                ELSE '2000+'
            END AS bucket,
            COUNT(*) AS cnt,
            ROUND(AVG(LENGTH(chunk_text)))::int AS avg_len
        FROM knowledge_chunks
        GROUP BY bucket
        ORDER BY MIN(LENGTH(chunk_text))
    """)
    print(f"\n  Length Distribution:")
    print(f"    {'Bucket':>12} | {'Count':>7} | {'AvgLen':>6}")
    print(f"    {'-'*12}-+-{'-'*7}-+-{'-'*6}")
    for d in dist:
        print(f"    {d['bucket']:>12} | {d['cnt']:>7} | {d['avg_len']:>6}")

    # ── 4. Chunk Boundary Quality — Employee Handbook ──
    print("\n" + "=" * 100)
    print("PART 3: CHUNK BOUNDARY QUALITY — Employee Handbook (8f89b3e6)")
    print("=" * 100)

    handbook_id = "8f89b3e6-fb56-4f5a-b899-4bcfc5b16a8d"
    handbook_chunks = await conn.fetch("""
        SELECT chunk_index, chunk_text
        FROM knowledge_chunks
        WHERE doc_id = $1
        ORDER BY chunk_index
        LIMIT 10
    """, handbook_id)
    total_hb = await conn.fetchval("SELECT COUNT(*) FROM knowledge_chunks WHERE doc_id = $1", handbook_id)

    print(f"  Document: {handbook_id}")
    print(f"  Total chunks: {total_hb}")
    print(f"  Showing first {len(handbook_chunks)} of {total_hb} chunks:\n")

    for c in handbook_chunks:
        print(f"  ── Chunk #{c['chunk_index']} ({len(c['chunk_text'])} chars) ──")
        print(f"  {c['chunk_text']}")
        print()

    # Boundary quality analysis
    print("  --- Boundary Quality Assessment ---")
    bad_starts = 0
    bad_ends = 0
    for c in handbook_chunks:
        text = c['chunk_text'].strip()
        if not text:
            continue
        issues = []
        first = text[0]
        last = text[-1]
        if first.islower() and first.isalpha():
            issues.append("starts mid-sentence (lowercase)")
            bad_starts += 1
        if last not in '.。!！?？\n）》"\'"' and c != handbook_chunks[-1]:
            issues.append("ends mid-sentence (no terminal punctuation)")
            bad_ends += 1
        if issues:
            print(f"    Chunk #{c['chunk_index']}: " + "; ".join(issues))
        else:
            print(f"    Chunk #{c['chunk_index']}: OK - natural boundary")

    print(f"\n    Summary: {bad_starts}/{len(handbook_chunks)} start mid-sentence, {bad_ends}/{len(handbook_chunks)} end mid-sentence")

    # Cross-chunk sentence fragment detection
    print(f"\n    --- Cross-chunk transition check ---")
    fragments = 0
    for i in range(len(handbook_chunks) - 1):
        curr = handbook_chunks[i]['chunk_text'].strip()
        nxt = handbook_chunks[i+1]['chunk_text'].strip()
        if curr and nxt:
            if curr[-1] not in '.。!！?？\n）》"\'"' and (nxt[0].islower() or nxt[0] == ' '):
                fragments += 1
                print(f"    CHUNKS {handbook_chunks[i]['chunk_index']}→{handbook_chunks[i+1]['chunk_index']}: likely sentence fragment cut")
                print(f"      ...'{curr[-60:]}' | '{nxt[:60]}'...")
    if fragments == 0:
        print("    No obvious cross-chunk sentence fragments detected.")
    print(f"    Fragment transitions: {fragments}/{len(handbook_chunks)-1}")

    # Topic coherence
    print(f"\n    --- Topic Coherence ---")
    if len(handbook_chunks) >= 4:
        c0_topic = handbook_chunks[0]['chunk_text'][:150].replace('\n', ' ')
        c3_topic = handbook_chunks[3]['chunk_text'][:150].replace('\n', ' ')
        c6_topic = handbook_chunks[6]['chunk_text'][:150].replace('\n', ' ') if len(handbook_chunks) > 6 else ""
        c9_topic = handbook_chunks[9]['chunk_text'][:150].replace('\n', ' ') if len(handbook_chunks) > 9 else ""
        print(f"    Chunk #0  start: {c0_topic}...")
        print(f"    Chunk #3  start: {c3_topic}...")
        if c6_topic:
            print(f"    Chunk #6  start: {c6_topic}...")
        if c9_topic:
            print(f"    Chunk #9  start: {c9_topic}...")

    # ── 5. Content Overlap / Duplication ──
    print("\n" + "=" * 100)
    print("PART 4: CONTENT OVERLAP / DUPLICATION CHECK")
    print("=" * 100)

    # Exact duplicates
    exact_dupes = await conn.fetch("""
        SELECT chunk_text, COUNT(*) as cnt,
               ARRAY_AGG(DISTINCT source_file) as sources,
               ARRAY_AGG(DISTINCT doc_id::text) as doc_ids
        FROM knowledge_chunks
        GROUP BY chunk_text
        HAVING COUNT(*) > 1
        ORDER BY COUNT(*) DESC
        LIMIT 30
    """)
    print(f"\n  Exact duplicate chunk_text (same text, different rows): {len(exact_dupes)} groups")
    if exact_dupes:
        for d in exact_dupes:
            txt = d['chunk_text'][:100].replace('\n', '\\n')
            print(f"    [{d['cnt']}x] sources={d['sources']}: \"{txt}\"")
            print(f"         doc_ids={d['doc_ids']}")

    # Near-duplicates across documents using pg_trgm similarity
    print(f"\n  Near-duplicate chunks across different documents (pg_trgm similarity > 0.6)...")
    try:
        near_dupes = await conn.fetch("""
            SELECT a.source_file AS src_a, a.doc_id::text AS doc_a, a.chunk_index AS idx_a,
                   b.source_file AS src_b, b.doc_id::text AS doc_b, b.chunk_index AS idx_b,
                   similarity(a.chunk_text, b.chunk_text) AS sim
            FROM knowledge_chunks a
            JOIN knowledge_chunks b ON a.doc_id < b.doc_id
                AND similarity(a.chunk_text, b.chunk_text) > 0.6
            ORDER BY sim DESC
            LIMIT 20
        """)
        print(f"    Found: {len(near_dupes)} pairs")
        for d in near_dupes:
            print(f"    sim={d['sim']:.3f} | DocA={d['doc_a'][:8]} idx={d['idx_a']} ({d['src_a']}) | "
                  f"DocB={d['doc_b'][:8]} idx={d['idx_b']} ({d['src_b']})")
    except Exception as e:
        print(f"    pg_trgm similarity join failed (may need CREATE EXTENSION pg_trgm): {e}")
        print("    Falling back to simple prefix/suffix overlap check...")
        near_dupes = await conn.fetch("""
            SELECT a.source_file AS src_a, a.doc_id::text AS doc_a, a.chunk_index AS idx_a,
                   b.source_file AS src_b, b.doc_id::text AS doc_b, b.chunk_index AS idx_b,
                   LENGTH(a.chunk_text) AS len_a, LENGTH(b.chunk_text) AS len_b
            FROM knowledge_chunks a
            JOIN knowledge_chunks b ON a.doc_id < b.doc_id
                AND a.chunk_text LIKE '%' || LEFT(b.chunk_text, 80) || '%'
            WHERE LENGTH(b.chunk_text) >= 100
            ORDER BY a.source_file, b.source_file
            LIMIT 20
        """)
        print(f"    Found (prefix overlap): {len(near_dupes)} pairs")
        for d in near_dupes:
            print(f"    DocA={d['doc_a'][:8]} idx={d['idx_a']} ({d['src_a']}) | "
                  f"DocB={d['doc_b'][:8]} idx={d['idx_b']} ({d['src_b']})")

    # Chunk index gaps
    print(f"\n  Chunk index gaps per document...")
    gap_rows = await conn.fetch("""
        SELECT doc_id::text, source_file,
               chunk_index AS gap_start,
               LEAD(chunk_index) OVER (PARTITION BY doc_id ORDER BY chunk_index) AS gap_end
        FROM knowledge_chunks
        ORDER BY doc_id, chunk_index
    """)
    gaps_found = []
    for r in gap_rows:
        if r['gap_end'] is not None and r['gap_end'] - r['gap_start'] > 1:
            gaps_found.append((r['doc_id'][:8], r['source_file'], r['gap_start'], r['gap_end'],
                               r['gap_end'] - r['gap_start'] - 1))
    print(f"    Total gaps: {len(gaps_found)}")
    for g in gaps_found[:15]:
        print(f"    doc={g[0]} src={g[1]} index {g[2]} -> {g[3]} ({g[4]} missing indices)")
    if not gaps_found:
        print("    No gaps found — contiguous indices within each document.")

    # ── 6. Per-Document Summary Table ──
    print("\n" + "=" * 100)
    print("APPENDIX: FULL DOCUMENT INVENTORY TABLE")
    print("=" * 100)
    print(f"{'DocID':<10} {'Source File':<50} {'Chunks':>7} {'AvgLen':>7} {'MinLen':>6} {'MaxLen':>6} {'Classification'}")
    print("-" * 98)
    for idx, r in enumerate(doc_stats):
        sample = await conn.fetchval("""
            SELECT chunk_text FROM knowledge_chunks
            WHERE source_file = $1 AND doc_id = $2
            ORDER BY chunk_index LIMIT 1
        """, r['source_file'], r['doc_id'])
        sample_lower = (sample or "").lower()[:500]
        src = r['source_file']
        real_score = sum(2 for p in real_phrases if p.lower() in sample_lower or p.lower() in src.lower())
        fake_score = sum(2 for p in fake_phrases if p.lower() in sample_lower or p.lower() in src.lower())
        if fake_score >= 2 and real_score == 0:
            classification = "FAKE"
        elif fake_score >= 4:
            classification = "FAKE"
        elif real_score >= 4 and fake_score == 0:
            classification = "REAL"
        elif real_score >= 2 and real_score > fake_score:
            classification = "LIKELY_REAL"
        elif fake_score > 0:
            classification = "LIKELY_FAKE"
        else:
            classification = "UNCERTAIN"
        did = str(r['doc_id'])[:8]
        print(f"{did:<10} {src:<50} {r['cnt']:>7} {r['avg_len']:>7} {r['min_len']:>6} {r['max_len']:>6} {classification}")

    await conn.close()
    print("\nDone.")

asyncio.run(main())
