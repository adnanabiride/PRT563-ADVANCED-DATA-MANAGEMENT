"""Modelling experiment: Model A (baseline) vs Model B (optimised) and a
leave-one-out ablation of each optimisation O1-O5 on the six-query workload."""
import json
from variants import build, BASELINE, OPTIMISATIONS
from qeval import run_workload

def norm(x):
    return json.dumps(x, sort_keys=True, default=str)

variants = {'A (baseline)': build(name='A', **BASELINE), 'B (optimised)': build(name='B')}
for o in OPTIMISATIONS:
    variants[f'B - {o}'] = build(name=f'B-{o}', **{o: False})
# typed values ablation (strings but otherwise B)
variants['B - typed'] = build(name='B-typed', typed=False)

runs = {k: run_workload(g) for k, g in variants.items()}
ref = runs['B (optimised)']
queries = ['Q1', 'Q2', 'Q3', 'Q4', 'W1', 'W2']
for k, r in runs.items():
    for q in queries:
        assert norm(r[q][0]) == norm(ref[q][0]), f'{k} {q} result differs'
print('All', len(runs), 'variants return identical results for all six queries.\n')

sizes = {k: dict(nodes=len(g.nodes), rels=len(g.rels), props=g.prop_count(),
                 labels=len(g.label_counts()), types=len(g.type_counts())) for k, g in variants.items()}
metric = 'accesses'
print(f"{'variant':16}" + ''.join(f'{q:>9}' for q in queries) + f"{'total':>9}{'nodes':>7}{'rels':>6}{'props':>7}")
out = {}
for k, r in runs.items():
    vals = [r[q][1][metric] for q in queries]
    out[k] = {q: r[q][1] for q in queries}
    print(f'{k:16}' + ''.join(f'{v:9.1f}' for v in vals) + f'{sum(vals):9.1f}' +
          f"{sizes[k]['nodes']:7}{sizes[k]['rels']:6}{sizes[k]['props']:7}")
print()
for mname in ('expansions', 'reads', 'conversions', 'touched'):
    print(mname)
    for k in ('A (baseline)', 'B (optimised)'):
        print(f'  {k:16}' + ''.join(f'{runs[k][q][1][mname]:9.1f}' for q in queries))
json.dump({'sizes': sizes, 'costs': out,
           'results': {q: ref[q][0] for q in ['Q1', 'Q2', 'Q3', 'Q4']}},
          open('results_experiment.json', 'w'), indent=1, default=str)
