"""
Task 4 - centrality use case: key-person risk in the teaching-delivery network.

Projection (identical to gds_centrality.txt):
  nodes          Staff, CourseOffering, Student            (Model B labels)
  relationships  LEADS, TOOK, SUPERVISES, all UNDIRECTED
Seven GDS centrality algorithms are compared against two independent measures
of what losing a staff member would actually cost the school:
  G1  network vulnerability  = relative loss of global efficiency when the node
                               is removed (Latora & Marchiori, 2001)
  G2  students affected      = distinct students taught in offerings the
                               person leads
Evaluation: Spearman rho, Kendall tau-b, precision@3 against G1 and G2 on the
10 staff; inter-algorithm agreement (Kendall tau-b, all 65 nodes); robustness
to missing data (Borgatti, Carley & Krackhardt, 2006): 10 % of TOOK
relationships deleted at random, 500 replicates.
"""
import sys, json, random
import os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from scipy.stats import spearmanr, kendalltau
import numpy as np
from variants import build
from algos import ALGORITHMS, global_efficiency, eigenvector

g = build()
LAB = ('Staff', 'CourseOffering', 'Student')
nodes = [n for n, v in g.nodes.items() if any(l in v['labels'] for l in LAB)]
edges = [(r['start'], r['end'], r['type']) for r in g.rels.values()
         if r['type'] in ('LEADS', 'TOOK', 'SUPERVISES')]


def adjacency(edge_list):
    adj = {n: [] for n in nodes}
    for a, b, _ in edge_list:
        adj[a].append(b)
        adj[b].append(a)
    return adj


adj = adjacency(edges)
staff = [n for n in nodes if 'Staff' in g.nodes[n]['labels']]


def label(n):
    p = g.nodes[n]['props']
    if 'Staff' in g.nodes[n]['labels'] or 'Student' in g.nodes[n]['labels']:
        return f"{p['preferred_name']} {p['family_name']}"
    return f"{p['subject_code']}@{p['campus_code']} {p['term_code']}"


# ---- connectivity ------------------------------------------------------------------
seen, stack = {nodes[0]}, [nodes[0]]
while stack:
    v = stack.pop()
    for w in adj[v]:
        if w not in seen:
            seen.add(w)
            stack.append(w)
assert len(seen) == len(nodes), 'projection is not connected'

# ---- scores ----------------------------------------------------------------------------
scores = {name: fn(adj) for name, fn in ALGORITHMS.items()}
ev, ev_iters = eigenvector(adj, return_iterations=True)
# eigenvector convergence diagnostics (does 20 iterations suffice?)
ev200, ev200_iters = eigenvector(adj, max_iter=1000, return_iterations=True)

# ---- ground truth ----------------------------------------------------------------------
E0 = global_efficiency(adj)
G1 = {s: (E0 - global_efficiency(adj, {s})) / E0 for s in staff}
G2 = {}
for s in staff:
    studs = set()
    for rid in g.out[s]['LEADS']:
        o = g.rels[rid]['end']
        for r2 in g.inn[o]['TOOK']:
            studs.add(g.rels[r2]['start'])
    G2[s] = float(len(studs))


def top_k(d, keys, k=3):
    return set(sorted(keys, key=lambda x: -d[x])[:k])


G1_all = {v: (E0 - global_efficiency(adj, {v})) / E0 for v in nodes}
brng = np.random.default_rng(563)


def boot_ci(x, y, n_boot=2000):
    x, y = np.asarray(x), np.asarray(y)
    vals = []
    for _ in range(n_boot):
        idx = brng.integers(0, len(x), len(x))
        if len(set(x[idx])) > 1 and len(set(y[idx])) > 1:
            vals.append(spearmanr(x[idx], y[idx]).statistic)
    return float(np.percentile(vals, 2.5)), float(np.percentile(vals, 97.5))


rows = []
for name, sc in scores.items():
    x = [sc[s] for s in staff]
    r = {'algorithm': name}
    for gname, gt in (('G1', G1), ('G2', G2)):
        y = [gt[s] for s in staff]
        r[f'{gname}_spearman'] = spearmanr(x, y).statistic
        r[f'{gname}_kendall'] = kendalltau(x, y).statistic
        r[f'{gname}_p@3'] = len(top_k(sc, staff) & top_k(gt, staff)) / 3
    xa = [sc[v] for v in nodes]
    ya = [G1_all[v] for v in nodes]
    r['all_spearman'] = spearmanr(xa, ya).statistic
    r['all_kendall'] = kendalltau(xa, ya).statistic
    r['all_ci'] = boot_ci(xa, ya)
    r['G1_ci'] = boot_ci(x, [G1[s] for s in staff])
    r['distinct_staff_scores'] = len({round(v, 9) for v in x})
    rows.append(r)

# ---- inter-algorithm agreement (all nodes) ------------------------------------------------
names = list(scores)
agree = np.zeros((len(names), len(names)))
for i, a in enumerate(names):
    for j, b in enumerate(names):
        agree[i, j] = kendalltau([scores[a][n] for n in nodes], [scores[b][n] for n in nodes]).statistic

# ---- robustness to missing TOOK relationships -----------------------------------------------
rng = random.Random(563)
took = [e for e in edges if e[2] == 'TOOK']
other = [e for e in edges if e[2] != 'TOOK']
REPS, FRAC = 500, 0.10
robust = {name: [] for name in names}
for _ in range(REPS):
    kept = rng.sample(took, int(round(len(took) * (1 - FRAC))))
    a2 = adjacency(other + kept)
    for name, fn in ALGORITHMS.items():
        s2 = fn(a2)
        robust[name].append(kendalltau([scores[name][s] for s in staff], [s2[s] for s in staff]).statistic)
rob = {n: (float(np.mean(v)), float(np.std(v))) for n, v in robust.items()}

# ---- output -------------------------------------------------------------------------------
print(f'Projection: {len(nodes)} nodes, {len(edges)} relationships, connected; E0 = {E0:.4f}')
print(f'Eigenvector: stopped after {ev_iters} iterations (default 20); converges after {ev200_iters}')
print('max |ev20 - ev_converged| =', max(abs(ev[n] - ev200[n]) for n in nodes))
print()
hdr = f"{'staff':22}{'G1 eff.loss':>12}{'G2 studs':>9}" + ''.join(f'{n[:9]:>11}' for n in names)
print(hdr)
for s in sorted(staff, key=lambda x: -G1[x]):
    print(f'{label(s):22}{G1[s]:12.4f}{G2[s]:9.0f}' + ''.join(f'{scores[n][s]:11.4f}' for n in names))
print()
print(f"{'algorithm':12}{'G1 rho':>8}{'G1 tau':>8}{'G1 P@3':>8}{'G2 rho':>8}{'G2 tau':>8}{'G2 P@3':>8}{'robust tau':>12}")
for r in rows:
    print(f"{r['algorithm']:12}{r['G1_spearman']:8.3f}{r['G1_kendall']:8.3f}{r['G1_p@3']:8.2f}"
          f"{r['G2_spearman']:8.3f}{r['G2_kendall']:8.3f}{r['G2_p@3']:8.2f}"
          f"{rob[r['algorithm']][0]:8.3f}±{rob[r['algorithm']][1]:.3f}")
print()
print(f"{'algorithm':12}{'all65 rho':>10}{'95% CI':>18}{'all tau':>9}{'staff rho CI':>20}{'distinct':>9}")
for r in rows:
    print(f"{r['algorithm']:12}{r['all_spearman']:10.3f}  [{r['all_ci'][0]:.3f}, {r['all_ci'][1]:.3f}]"
          f"{r['all_kendall']:9.3f}   [{r['G1_ci'][0]:.3f}, {r['G1_ci'][1]:.3f}]{r['distinct_staff_scores']:9}")
print('eigenvector@20 vs converged: tau =', kendalltau([ev[n] for n in nodes], [ev200[n] for n in nodes]).statistic,
      ' staff tau =', kendalltau([ev[n] for n in staff], [ev200[n] for n in staff]).statistic)
print('converged eigenvector vs G1 all: rho =', spearmanr([ev200[n] for n in nodes], [G1_all[n] for n in nodes]).statistic)
top_all = sorted(nodes, key=lambda v: -G1_all[v])[:8]
print('G1 top nodes overall:', [(label(v), round(G1_all[v], 4)) for v in top_all])
print()
print('agreement (Kendall tau, 65 nodes)')
for i, a in enumerate(names):
    print(f'{a:12}' + ''.join(f'{agree[i, j]:7.2f}' for j in range(len(names))))
# top nodes overall per algorithm
print()
for n_ in names:
    top = sorted(nodes, key=lambda x: -scores[n_][x])[:5]
    print(f'{n_:12}', ' | '.join(f'{label(t)} ({scores[n_][t]:.3f})' for t in top))

json.dump({'nodes': len(nodes), 'edges': len(edges), 'E0': E0, 'eigen_iters': ev_iters,
           'eigen_converged_iters': ev200_iters,
           'staff': {label(s): dict(G1=G1[s], G2=G2[s], **{n: scores[n][s] for n in names}) for s in staff},
           'evaluation': rows, 'agreement': {'names': names, 'matrix': agree.tolist()},
           'robustness': rob, 'G1_all_top': [(label(v), G1_all[v]) for v in top_all],
           'top5': {n_: [(label(t), scores[n_][t]) for t in sorted(nodes, key=lambda x: -scores[n_][x])[:5]]
                    for n_ in names}},
          open('results_centrality.json', 'w'), indent=1)
