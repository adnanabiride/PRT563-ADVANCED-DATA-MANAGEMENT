"""
Task 5 - similarity use case: work-placement matching for unplaced students.

Similarity notions compared (GDS definitions; see gds_similarity.txt):
  NodeSimilarity  JACCARD | OVERLAP | COSINE  on Student->Subject   (what they study)
  NodeSimilarity  JACCARD | OVERLAP | COSINE  on Student->CourseOffering (who they study with)
  KNN             COSINE | PEARSON | EUCLIDEAN on subject_profile   (how well they do)
GDS rescaling is reproduced: KNN cosine/pearson -> (x + 1) / 2, euclidean -> 1 / (1 + d).
Recommendation rule: similarity-weighted vote of the k most similar PLACED
students ('pure'), or of the k most similar placed students in the SAME
PROGRAM ('hybrid'). Evaluation:
  intrinsic  program purity@3 and campus purity@3 of each student's 3 nearest
             neighbours (n = 24), top-3 tie rate
  extrinsic  leave-one-out over the 11 placed students: Hit@1, Hit@3, MRR,
             against random, popularity and program-rule baselines
  agreement  mean Jaccard overlap of top-3 neighbour sets between algorithms
"""
import sys, math, json
import os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from collections import Counter, defaultdict
import numpy as np
from variants import build

g = build()
P = lambda n: g.nodes[n]['props']
students = sorted([n for n, v in g.nodes.items() if 'Student' in v['labels']], key=lambda n: P(n)['person_id'])
pid = {n: P(n)['person_id'] for n in students}
name = {n: f"{P(n)['preferred_name']} {P(n)['family_name']}" for n in students}
SUBJ = sorted(P(n)['subject_code'] for n, v in g.nodes.items() if 'Subject' in v['labels'])
GP = {'A': 5.0, 'B': 4.0, 'C': 3.0, 'D': 2.0, 'E': 1.0}
VET = {'C': 4.0, 'NYC': 1.0}

subjects, classes, profile = defaultdict(set), defaultdict(set), {}
for s in students:
    vec = {j: 0.0 for j in SUBJ}
    for rid in g.out[s]['TOOK']:
        r = g.rels[rid]
        if r['props']['status'] == 'WITHDRAWN':
            continue
        o = r['end']
        j = P(o)['subject_code']
        subjects[s].add(j)
        classes[s].add(o)
        gl, co = r['props'].get('grade_letter'), r['props'].get('competency_outcome')
        vec[j] = GP[gl] if gl else VET[co] if co else 3.0      # enrolled, not yet graded -> 3
    profile[s] = [vec[j] for j in SUBJ]

program, campus = {}, {}
for s in students:
    for rid in g.out[s]['HAS_ENROLMENT']:
        e = g.rels[rid]['end']
        if P(e)['enrolment_status'] in ('ACTIVE', 'COMPLETED'):
            program[s] = P(e)['program_code']
            campus[s] = P(g.rels[g.out[e]['AT_CAMPUS'][0]]['end'])['campus_code']
placement = {}
for s in students:
    for rid in g.out[s]['UNDERTAKES']:
        pl = g.rels[rid]['end']
        placement[s] = P(g.rels[g.out[pl]['HOSTED_BY'][0]]['end'])['employer_name']
employers = sorted(P(n)['employer_name'] for n, v in g.nodes.items() if 'HostEmployer' in v['labels'])
placed = [s for s in students if s in placement]
unplaced = [s for s in students if s not in placement]


# ---- similarity functions (GDS semantics) -----------------------------------------------
def jaccard(a, b):
    return len(a & b) / len(a | b) if a | b else 0.0


def overlap(a, b):
    return len(a & b) / min(len(a), len(b)) if a and b else 0.0


def cosine_set(a, b):
    return len(a & b) / math.sqrt(len(a) * len(b)) if a and b else 0.0


def knn_cosine(x, y):
    nx_, ny_ = math.sqrt(sum(v * v for v in x)), math.sqrt(sum(v * v for v in y))
    c = sum(a * b for a, b in zip(x, y)) / (nx_ * ny_) if nx_ and ny_ else 0.0
    return (c + 1) / 2


def knn_pearson(x, y):
    mx, my = sum(x) / len(x), sum(y) / len(y)
    num = sum((a - mx) * (b - my) for a, b in zip(x, y))
    den = math.sqrt(sum((a - mx) ** 2 for a in x) * sum((b - my) ** 2 for b in y))
    return ((num / den if den else 0.0) + 1) / 2


def knn_euclid(x, y):
    return 1 / (1 + math.sqrt(sum((a - b) ** 2 for a, b in zip(x, y))))


ALG = {
    'NS Jaccard (subject)': lambda a, b: jaccard(subjects[a], subjects[b]),
    'NS Overlap (subject)': lambda a, b: overlap(subjects[a], subjects[b]),
    'NS Cosine (subject)': lambda a, b: cosine_set(subjects[a], subjects[b]),
    'NS Jaccard (class)': lambda a, b: jaccard(classes[a], classes[b]),
    'NS Overlap (class)': lambda a, b: overlap(classes[a], classes[b]),
    'NS Cosine (class)': lambda a, b: cosine_set(classes[a], classes[b]),
    'KNN Cosine (profile)': lambda a, b: knn_cosine(profile[a], profile[b]),
    'KNN Pearson (profile)': lambda a, b: knn_pearson(profile[a], profile[b]),
    'KNN Euclidean (profile)': lambda a, b: knn_euclid(profile[a], profile[b]),
}
SIM = {n: {(a, b): f(a, b) for a in students for b in students if a != b} for n, f in ALG.items()}


def neighbours(alg, s, pool, k):
    """top-k by similarity (> 0, the GDS similarityCutoff), ties broken by person_id."""
    c = [(SIM[alg][(s, u)], u) for u in pool if u != s and SIM[alg][(s, u)] > 0]
    c.sort(key=lambda x: (-x[0], pid[x[1]]))
    return c[:k]


# ---- intrinsic evaluation ------------------------------------------------------------------
intrinsic = {}
for alg in ALG:
    pur_p, pur_c, ties = [], [], 0
    for s in students:
        nb = neighbours(alg, s, students, 3)
        pur_p.append(sum(program[u] == program[s] for _, u in nb) / 3)
        pur_c.append(sum(campus[u] == campus[s] for _, u in nb) / 3)
        allnb = neighbours(alg, s, students, 24)
        if len(allnb) > 3 and abs(allnb[2][0] - allnb[3][0]) < 1e-12:
            ties += 1
    intrinsic[alg] = dict(program_purity=float(np.mean(pur_p)), campus_purity=float(np.mean(pur_c)),
                          tie_rate=ties / len(students))
base_prog = sum(sum(program[u] == program[s] for u in students if u != s) / 23 for s in students) / 24
base_camp = sum(sum(campus[u] == campus[s] for u in students if u != s) / 23 for s in students) / 24


# ---- extrinsic evaluation: leave-one-out placement matching ------------------------------------
def rank_employers(alg, t, k, hybrid, pool):
    cand = [u for u in pool if u != t and (not hybrid or program[u] == program[t])]
    votes = Counter()
    for sc, u in neighbours(alg, t, cand, k):
        votes[placement[u]] += sc
    ranked = [e for e, _ in sorted(votes.items(), key=lambda x: (-x[1], x[0]))]
    if hybrid:   # back-fill: programme popularity, then overall popularity (every employer gets a rank)
        ppop = Counter(placement[u] for u in pool if u != t and program[u] == program[t])
        ranked += [e for e, _ in sorted(ppop.items(), key=lambda x: (-x[1], x[0])) if e not in ranked]
        pop = Counter(placement[u] for u in pool if u != t)
        ranked += [e for e, _ in sorted(pop.items(), key=lambda x: (-x[1], x[0])) if e not in ranked]
    return ranked


def metrics(rank_fn):
    h1 = h3 = mrr = 0.0
    per = []
    for t in placed:
        ranked = rank_fn(t)
        r = ranked.index(placement[t]) + 1 if placement[t] in ranked else None
        per.append(r)
        if r:
            h1 += r == 1
            h3 += r <= 3
            mrr += 1 / r
    n = len(placed)
    return dict(hit1=h1 / n, hit3=h3 / n, mrr=mrr / n, ranks=per)


extrinsic = {}
for alg in ALG:
    for mode in ('pure', 'hybrid'):
        for k in (1, 3, 5):
            extrinsic[(alg, mode, k)] = metrics(lambda t: rank_employers(alg, t, k, mode == 'hybrid', placed))
pop_rank = lambda t: [e for e, _ in sorted(Counter(placement[u] for u in placed if u != t).items(),
                                           key=lambda x: (-x[1], x[0]))]


def prog_rank(t):
    c = Counter(placement[u] for u in placed if u != t and program[u] == program[t])
    ranked = [e for e, _ in sorted(c.items(), key=lambda x: (-x[1], x[0]))]
    return ranked + [e for e in pop_rank(t) if e not in ranked]


baselines = {'Random (expected)': dict(hit1=1 / 6, hit3=3 / 6, mrr=sum(1 / r for r in range(1, 7)) / 6),
             'Popularity': metrics(pop_rank), 'Program rule': metrics(prog_rank)}

# ---- algorithm agreement: top-3 neighbour sets ---------------------------------------------------
names = list(ALG)
agree = np.zeros((len(names), len(names)))
for i, a in enumerate(names):
    for j, b in enumerate(names):
        vals = []
        for s in students:
            A = {u for _, u in neighbours(a, s, students, 3)}
            B = {u for _, u in neighbours(b, s, students, 3)}
            vals.append(len(A & B) / len(A | B) if A | B else 1.0)
        agree[i, j] = np.mean(vals)

# ---- report -------------------------------------------------------------------------------------
print(f'{len(students)} students, {len(placed)} placed, {len(unplaced)} unplaced, {len(employers)} employers')
print(f'baseline purity (random neighbour): program {base_prog:.3f}, campus {base_camp:.3f}\n')
print(f"{'algorithm':26}{'prog@3':>8}{'camp@3':>8}{'ties':>7} | {'pure k=3: H@1 H@3 MRR':>24} | {'hybrid k=3: H@1 H@3 MRR':>25} | hybrid MRR k=1/5")
for alg in ALG:
    i_, p3, h3 = intrinsic[alg], extrinsic[(alg, 'pure', 3)], extrinsic[(alg, 'hybrid', 3)]
    print(f"{alg:26}{i_['program_purity']:8.3f}{i_['campus_purity']:8.3f}{i_['tie_rate']:7.2f} | "
          f"{p3['hit1']:8.3f}{p3['hit3']:6.3f}{p3['mrr']:6.3f}   | {h3['hit1']:9.3f}{h3['hit3']:6.3f}{h3['mrr']:6.3f}   | "
          f"{extrinsic[(alg, 'hybrid', 1)]['mrr']:.3f}/{extrinsic[(alg, 'hybrid', 5)]['mrr']:.3f}")
for b, m in baselines.items():
    print(f"{b:26}{'':23} | {m['hit1']:8.3f}{m['hit3']:6.3f}{m['mrr']:6.3f}")
print('\nagreement (mean Jaccard of top-3 neighbour sets)')
for i, a in enumerate(names):
    print(f'{a:26}' + ''.join(f'{agree[i, j]:6.2f}' for j in range(len(names))))

json.dump({'intrinsic': intrinsic, 'baseline_purity': dict(program=base_prog, campus=base_camp),
           'extrinsic': {f'{a}|{m}|{k}': v for (a, m, k), v in extrinsic.items()},
           'baselines': baselines, 'agreement': {'names': names, 'matrix': agree.tolist()},
           'placed': [pid[s] for s in placed], 'unplaced': [pid[s] for s in unplaced]},
          open('results_similarity.json', 'w'), indent=1)

# ---- application: recommendations for the unplaced students (hybrid, KNN Euclidean, k = 3) ---------
from scipy.stats import fisher_exact
from statsmodels.stats.proportion import proportion_confint
CHOSEN = 'KNN Euclidean (profile)'
recs = []
for s in unplaced:
    same = [u for u in placed if program[u] == program[s]]
    nb = neighbours(CHOSEN, s, same, 3)
    votes = Counter()
    for sc, u in nb:
        votes[placement[u]] += sc
    ranked = sorted(votes.items(), key=lambda x: (-x[1], x[0]))
    recs.append(dict(student=name[s], person_id=pid[s], program=program[s], campus=campus[s],
                     recommendation=ranked[0][0] if ranked else 'NO PEER IN PROGRAM - cold start',
                     score=round(ranked[0][1], 3) if ranked else None,
                     peers=[f'{name[u]} ({sc:.3f})' for sc, u in nb]))
print()
for r in recs:
    print(r)
never = [e for e in employers if e not in set(placement.values())]
print('employers never placed (cold start):', never)
# uncertainty of the headline comparison
p = extrinsic[(CHOSEN, 'pure', 3)]
h = extrinsic[(CHOSEN, 'hybrid', 3)]
n = len(placed)
for lab, m in (('pure', p), ('hybrid', h), ('program rule', baselines['Program rule'])):
    k_ = round(m['hit3'] * n)
    lo, hi = proportion_confint(k_, n, method='wilson')
    print(f'{lab:13} Hit@3 {k_}/{n}  Wilson 95% CI [{lo:.2f}, {hi:.2f}]')
print('Fisher exact pure vs hybrid Hit@3: p =',
      fisher_exact([[round(p['hit3'] * n), n - round(p['hit3'] * n)], [round(h['hit3'] * n), n - round(h['hit3'] * n)]]).pvalue)
json.dump(recs, open('results_placement_recommendations.json', 'w'), indent=1)
