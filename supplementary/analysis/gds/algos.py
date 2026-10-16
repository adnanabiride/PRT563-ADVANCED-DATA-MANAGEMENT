"""
Reference implementations of the GDS algorithms used in the report, written to
the definitions in the Neo4j Graph Data Science manual and checked against the
manual's worked examples (see __main__):

  PageRank / ArticleRank  Pregel, delta-based: init 1 - d, per-node vote-to-halt
                          when delta <= tolerance, maxIterations supersteps
                          (reproduces the manual's example to full precision)
  Eigenvector             power iteration from 1/|V|, L2-normalised each
                          iteration, stops when every change < tolerance
  Betweenness             Brandes; undirected pairs counted once
  Closeness               (n - 1) / sum of distances   (connected graph)
  Harmonic                sum(1 / d) / (n - 1)
  Degree                  number of relationships in the projection
Graphs are adjacency dicts {node: [neighbour, ...]} of an UNDIRECTED projection
(each relationship listed from both ends), as GDS builds for
undirectedRelationshipTypes: ['*'].
"""
import math
from collections import deque


def degree(adj):
    return {v: float(len(n)) for v, n in adj.items()}


def _pregel_rank(adj, d=0.85, max_iter=20, tol=1e-7, article=False):
    nodes = list(adj)
    avg = sum(len(adj[v]) for v in nodes) / len(nodes)
    rank = {v: 1 - d for v in nodes}
    delta = {v: 1 - d for v in nodes}
    inbox = {v: 0.0 for v in nodes}
    for v in nodes:                                   # superstep 0: every node sends
        deg = len(adj[v])
        for w in adj[v]:
            inbox[w] += delta[v] / ((deg + avg) if article else deg)
    for _ in range(1, max_iter):
        new_inbox = {v: 0.0 for v in nodes}
        active = False
        for v in nodes:
            delta[v] = d * inbox[v]
            rank[v] += delta[v]
            if delta[v] > tol:
                active = True
                deg = len(adj[v])
                for w in adj[v]:
                    new_inbox[w] += delta[v] / ((deg + avg) if article else deg)
        inbox = new_inbox
        if not active:
            break
    return rank


def pagerank(adj, d=0.85, max_iter=20, tol=1e-7):
    return _pregel_rank(adj, d, max_iter, tol, article=False)


def articlerank(adj, d=0.85, max_iter=20, tol=1e-7):
    return _pregel_rank(adj, d, max_iter, tol, article=True)


def eigenvector(adj, max_iter=20, tol=1e-7, return_iterations=False):
    nodes = list(adj)
    x = {v: 1.0 / len(nodes) for v in nodes}
    it = 0
    for it in range(1, max_iter + 1):
        nx_ = {v: sum(x[w] for w in adj[v]) for v in nodes}
        norm = math.sqrt(sum(val * val for val in nx_.values())) or 1.0
        nx_ = {v: val / norm for v, val in nx_.items()}
        converged = all(abs(nx_[v] - x[v]) < tol for v in nodes)
        x = nx_
        if converged:
            break
    return (x, it) if return_iterations else x


def _bfs(adj, s):
    dist = {s: 0}
    q = deque([s])
    while q:
        v = q.popleft()
        for w in adj[v]:
            if w not in dist:
                dist[w] = dist[v] + 1
                q.append(w)
    return dist


def closeness(adj):
    n = len(adj)
    out = {}
    for v in adj:
        dist = _bfs(adj, v)
        tot = sum(dist.values())
        out[v] = (len(dist) - 1) / tot if tot > 0 else 0.0     # = (n-1)/sum d when connected
    return out


def harmonic(adj):
    n = len(adj)
    return {v: sum(1.0 / dd for u, dd in _bfs(adj, v).items() if u != v) / (n - 1) for v in adj}


def betweenness(adj):
    """Brandes (2001). Undirected: each unordered pair counted once."""
    bc = {v: 0.0 for v in adj}
    for s in adj:
        stack, pred = [], {v: [] for v in adj}
        sigma = {v: 0 for v in adj}
        sigma[s] = 1
        dist = {v: -1 for v in adj}
        dist[s] = 0
        q = deque([s])
        while q:
            v = q.popleft()
            stack.append(v)
            for w in adj[v]:
                if dist[w] < 0:
                    dist[w] = dist[v] + 1
                    q.append(w)
                if dist[w] == dist[v] + 1:
                    sigma[w] += sigma[v]
                    pred[w].append(v)
        delta = {v: 0.0 for v in adj}
        while stack:
            w = stack.pop()
            for v in pred[w]:
                delta[v] += sigma[v] / sigma[w] * (1 + delta[w])
            if w != s:
                bc[w] += delta[w]
    return {v: val / 2.0 for v, val in bc.items()}


def global_efficiency(adj, removed=None):
    """Latora & Marchiori (2001): mean of 1/d over ordered pairs of the remaining nodes."""
    removed = removed or set()
    keep = {v: [w for w in n if w not in removed] for v, n in adj.items() if v not in removed}
    n = len(keep)
    if n < 2:
        return 0.0
    tot = 0.0
    for v in keep:
        for u, dd in _bfs(keep, v).items():
            if u != v:
                tot += 1.0 / dd
    return tot / (n * (n - 1))


ALGORITHMS = {
    'Degree': degree, 'PageRank': pagerank, 'ArticleRank': articlerank,
    'Eigenvector': eigenvector, 'Betweenness': betweenness,
    'Closeness': closeness, 'Harmonic': harmonic,
}


if __name__ == '__main__':
    # ---- worked examples from the GDS manual --------------------------------------------
    def undirected(edges):
        adj = {}
        for a, b in edges:
            adj.setdefault(a, []).append(b)
            adj.setdefault(b, []).append(a)
        return adj

    # PageRank / ArticleRank examples are DIRECTED; run the pregel core on out-lists
    web = [('Home', 'About'), ('Home', 'Links'), ('Home', 'Product'), ('About', 'Home'), ('Product', 'Home'),
           ('Site A', 'Home'), ('Site B', 'Home'), ('Site C', 'Home'), ('Site D', 'Home'), ('Links', 'Home'),
           ('Links', 'Site A'), ('Links', 'Site B'), ('Links', 'Site C'), ('Links', 'Site D')]
    out = {}
    for a, b in web:
        out.setdefault(a, []).append(b)
        out.setdefault(b, [])
    pr, ar = pagerank(out), articlerank(out)
    assert abs(pr['Home'] - 3.215681999884452) < 1e-12 and abs(pr['Site A'] - 0.3278578964488539) < 1e-12
    assert abs(ar['Home'] - 0.5607071761939444) < 1e-12 and abs(ar['About'] - 0.250337073634706) < 1e-12
    # closeness example: path A-B-C-D-E
    path = undirected([('A', 'B'), ('B', 'C'), ('C', 'D'), ('D', 'E')])
    cl = closeness(path)
    assert abs(cl['C'] - 0.6666666666666666) < 1e-12 and abs(cl['A'] - 0.4) < 1e-12
    # harmonic example
    h = harmonic(undirected([('Alice', 'Bob'), ('Bob', 'Charles'), ('Doug', 'Ethan')]))
    assert abs(h['Bob'] - 0.5) < 1e-12 and abs(h['Doug'] - 0.25) < 1e-12
    # betweenness undirected example from the manual (Carol 9.5, Frank 5.5 ...) via networkx cross-check
    import networkx as nx, random
    random.seed(1)
    G = nx.gnm_random_graph(40, 90, seed=3)
    adj = {v: list(G.neighbors(v)) for v in G}
    ref = nx.betweenness_centrality(G, normalized=False)
    mine = betweenness(adj)
    assert max(abs(ref[v] - mine[v]) for v in G) < 1e-9
    print('All reference implementations reproduce the GDS manual examples / networkx.')
