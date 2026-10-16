"""Write supplementary/EXPECTED_RESULTS.md from the replica's result files, so every script in the repository
can be checked against what it should return in Neo4j Desktop."""
import json, sys, os
from collections import Counter
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from variants import build

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, '..', 'EXPECTED_RESULTS.md')
X = json.load(open(f'{HERE}/results_experiment.json'))
REC = json.load(open(f'{HERE}/results_reconciliation.json'))
CEN = json.load(open(f'{HERE}/gds/results_centrality.json'))
SIM = json.load(open(f'{HERE}/gds/results_similarity.json'))
PLA = json.load(open(f'{HERE}/gds/results_placement_recommendations.json'))
g = build()

L = []
w = L.append


def table(cols, rows):
    w('| ' + ' | '.join(cols) + ' |')
    w('|' + '|'.join('---' for _ in cols) + '|')
    for r in rows:
        w('| ' + ' | '.join('' if v is None else str(v) for v in r) + ' |')
    w('')


def f(x, n=3):
    return f'{x:.{n}f}'


w('# Expected results')
w('')
w('Produced by the independent in-memory replica of the graph (`analysis/`), which loads the same 26 CSV files '
  'with the same rules as `import.txt`. Use it to check each script after running it in Neo4j Desktop. '
  'All queries use the fixed reporting date **2026-09-14**.')
w('')
w('Tolerances: counts, keys, names and query rows must match exactly. GDS scores may differ in the last decimal '
  'places; eigenvector scores differ more because GDS stops after 20 iterations without converging (compare '
  'rankings, not values). `PROFILE` database hits will not equal the replica\'s logical accesses - compare the '
  'ratio Model B / Model A, not the absolute numbers.')
w('')

# ------------------------------------------------------------------ import
w('## 1. import.txt')
w('')
sz = X['sizes']['B (optimised)']
w(f"After a clean run: **{sz['nodes']} nodes, {sz['rels']} relationships, {sz['labels']} labels, "
  f"{sz['types']} relationship types, {sz['props']} stored property values** (Model B). "
  f"`SHOW CONSTRAINTS` lists 28 uniqueness constraints; `SHOW INDEXES` lists 35 indexes: the 5 query-driven "
  f"indexes, one backing index per constraint and the two built-in token-lookup indexes.")
w('')
w('Validation (section 8):')
w('')
table(['Statement', 'Expected'],
      [['8.1 nodes per label', f"see table below ({sz['nodes']} nodes in total)"],
       ['8.2 relationships per type', f"see table below ({sz['rels']} relationships in total)"],
       ['8.3 rows accounted for', 'subject_enrolments 95, results 71'],
       ['8.4 billing-account category check', 'no rows (every account has exactly one holder of an allowed type)'],
       ['8.5 SUBJECT disjoint and total', 'overlapping_subjects 0, unspecialised_subjects 0'],
       ['8.6 PERSON total', 'roleless_people 0, multi_role_people 2 (Priya Raman, Meena Chandra)'],
       ['8.7 structural integrity (NOT NULL, cardinality)', 'violations = 0'],
       ['8.8 second holder for ACC-1001 (commented demo)', 'fails with Neo.ClientError.Schema.ConstraintValidationFailed '
        '(shown as GQLSTATUS 22N79, property uniqueness constraint violated, on Neo4j 2025+)']])
lc = sorted(g.label_counts().items())
tc = sorted(Counter(r['type'] for r in g.rels.values()).items())
w('Nodes per label (a node can carry several labels, so the column does not add up to the node total):')
w('')
table(['Label', 'Nodes'], lc)
w('Relationships per type:')
w('')
table(['Type', 'Relationships'], tc)
w(f"Reconciliation against the relational source (`analysis/reconcile.py`): {len(REC['tables'])} tables, "
  f"{REC['rows']} rows, {REC['checks']:,} cell-level checks, {REC['mismatches']} mismatches.")
w('')
table(['Source table', 'Rows', 'Checks', 'Mismatches', 'Stored in the graph as'],
      [[t['table'], t['rows'], t['checks'], t['mismatches'], t['target']] for t in REC['tables']])

# ------------------------------------------------------------------ queries
w('## 2. queries.txt')
w('')
R = X['results']
w('### Q1 - assessment conflict of interest')
w('')
table(['staff_member', 'dependant', 'finding', 'subject', 'campus', 'term', 'action', 'eligible_assessors'],
      [[r['staff_member'], r['dependant'], r['finding'], (r['subject'] or '').split(' ')[0] or None, r['campus'],
        r['term'], r['action'], ', '.join(r['eligible_assessors']) or '[]'] for r in R['Q1']])
w('### Q2 - blue card compliance sweep (next term 2026T4)')
w('')
table(['staff_member', 'blue_card_expiry', 'days_remaining', 'risk', 'rostered', 'students_affected', 'escalation',
       'contact'],
      [[r['staff_member'], r['blue_card_expiry'], r['days_remaining'], r['risk'],
        ', '.join(r['offerings_next_term']) or '[]', r['students_affected'], r['escalation_chain'],
        r['manager_contact']] for r in R['Q2']])
w('### Q3 - campus debt against the school-wide average')
w('')
avg = R['Q3'][0]['school_average']
table(['campus', 'open_invoices', 'debtors', 'balance_owing', 'variance_vs_average', 'pct_over_90_days', 'flag'],
      [[r['campus'], r['open_invoices'], r['debtor_students'], f"{r['balance_owing']:.2f}",
        f"{r['variance_vs_average']:+.2f}", r['pct_over_90_days'], r['flag']] for r in R['Q3']])
w(f'School-wide average: **{avg:.2f}** over all five campuses. The same figure comes from the corrected SQL query '
  f'in `a2_feedback_fixes.sql` (FIX 1).')
w('')
w('### Q4 - prerequisite breaches and their root cause')
w('')
table(['student_no', 'program', 'subject', 'term', 'unmet_prerequisite', 'prereq_history', 'root_cause'],
      [[r['student_no'], r['program'], r['subject'], r['term'], r['unmet_prerequisite'],
        r['prerequisite_history'], r['root_cause']] for r in R['Q4']])
rc = Counter(r['root_cause'] for r in R['Q4'])
w(f"{len(R['Q4'])} rows for {len({r['student_no'] for r in R['Q4']})} students: "
  + ', '.join(f'{v} x {k}' for k, v in rc.items()) + '.')
w('')

# ------------------------------------------------------------------ experiment
w('## 3. Modelling experiment (supplementary/experiment_profile.txt)')
w('')
w('Logical accesses (label-scan nodes + index seeks + relationship expansions + property reads) per query; '
  'W1 and W2 are averaged over all 24 students and 22 accounts.')
w('')
qs = ['Q1', 'Q2', 'Q3', 'Q4', 'W1', 'W2']
rows = []
for k, v in X['costs'].items():
    tot = sum(v[q]['accesses'] for q in qs)
    rows.append([k] + [f"{v[q]['accesses']:.0f}" for q in qs] + [f'{tot:.0f}'])
table(['Variant'] + qs + ['Workload'], rows)
w('Every variant returns identical rows for all six queries.')
w('')

# ------------------------------------------------------------------ centrality
w('## 4. gds_centrality.txt')
w('')
w(f"C1 projection: nodeCount **{CEN['nodes']}**, relationshipCount **{2 * CEN['edges']}** "
  f"({CEN['edges']} undirected relationships stored in both directions).")
w('')
w(f"C3 iterations: PageRank ranIterations {CEN['eigen_iters']}, didConverge false; ArticleRank 19, true; "
  f"eigenvector {CEN['eigen_iters']}, false. C4: GDS converges after 227 iterations (Neo4j run, 14 October 2026); "
  f"the replica's stricter per-node tolerance needs about {CEN['eigen_converged_iters']}.")
w('')
algs = ['Degree', 'PageRank', 'ArticleRank', 'Eigenvector', 'Betweenness', 'Closeness', 'Harmonic']
st = sorted(CEN['staff'].items(), key=lambda kv: -kv[1]['Betweenness'])
table(['Staff member'] + algs + ['G1 efficiency loss', 'G2 students taught'],
      [[n] + [f(v[a], 1 if a in ('Degree', 'Betweenness') else 3) for a in algs] + [f(v['G1'], 4), f"{v['G2']:.0f}"]
       for n, v in st])
w('Evaluation against the ground truth (Section 6 of the report):')
w('')
table(['Algorithm', 'rho all nodes (G1)', '95% CI', 'rho staff (G1)', 'precision@3 staff (G1)', 'rho staff (G2)',
       'Kendall tau, 10% TOOK removed (mean +/- SD)'],
      [[e['algorithm'], f(e['all_spearman'], 2), f"{e['all_ci'][0]:.2f}-{e['all_ci'][1]:.2f}", f(e['G1_spearman'], 2),
        f(e['G1_p@3'], 2), f(e['G2_spearman'], 2),
        f"{CEN['robustness'][e['algorithm']][0]:.3f} +/- {CEN['robustness'][e['algorithm']][1]:.3f}"]
       for e in CEN['evaluation']])

# ------------------------------------------------------------------ similarity
w('## 5. gds_similarity.txt')
w('')
w(f"Placed students (leave-one-out cases): {len(SIM['placed'])}; unplaced students: {len(SIM['unplaced'])}. "
  "S0 profiles 24 students; S2 projects 32 nodes and 94 relationships; S3 55 nodes and 94 relationships; S4 24 nodes.")
w('')
w('S5 and S6 list three peers per student. Scores must match; the peers themselves can differ where scores tie '
  '(GDS breaks ties its own way, which is the instability measured below), and GDS KNN is approximate, so a top-3 '
  'list can miss a near neighbour (in the Neo4j run, Priya Raman was given Malik Traore 0.183 instead of Samuel Otieno '
  '0.187). S9 asks KNN for all 23 neighbours, so its recommendations are exact.')
w('')
table(['Variant', 'same program in top 3', 'same campus in top 3', 'students with a tied 3rd/4th peer'],
      [[k, f"{v['program_purity']:.2f}", f"{v['campus_purity']:.2f}", f"{v['tie_rate']:.2f}"]
       for k, v in SIM['intrinsic'].items()]
      + [['Random baseline', f"{SIM['baseline_purity']['program']:.2f}", f"{SIM['baseline_purity']['campus']:.2f}",
          '-']])
rows = []
for k, v in SIM['extrinsic'].items():
    name, mode, kk = k.split('|')
    if kk == '3':
        rows.append([name, 'similarity only' if mode == 'pure' else 'within program', f"{v['hit1']:.2f}",
                     f"{v['hit3']:.2f}", f"{v['mrr']:.2f}"])
for k, v in SIM['baselines'].items():
    rows.append([k, 'baseline', f"{v['hit1']:.2f}", f"{v['hit3']:.2f}", f"{v['mrr']:.2f}"])
w('Leave-one-out placement matching (k = 3 peers):')
w('')
table(['Variant', 'Mode', 'Hit@1', 'Hit@3', 'MRR'], rows)
w('S9 recommendations for the unplaced students (program filter, KNN Euclidean on the performance profile; '
  'S10 lists the cold-start students):')
w('')
table(['Student', 'Program', 'Campus', 'Recommended host', 'Score', 'Most similar placed peers'],
      [[r['student'], r['program'], r['campus'], r['recommendation'],
        '' if r['score'] is None else f"{r['score']:.3f}", ', '.join(r['peers'])] for r in PLA])
open(OUT, 'w').write('\n'.join(L))
print('wrote', OUT, len(L), 'lines')
