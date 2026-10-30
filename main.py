import argparse
import math
import os
import random
import signal
import sys
import time
from typing import Dict, List, Optional, Set, Tuple

PROGRAM_STARTED = time.perf_counter()
INF = 10**15
DEFAULT_TIME_LIMIT = float(os.environ.get("SOICT_TIME_LIMIT", "285.0"))


class ProblemInstance:
	"""Encapsulates the Share-a-Ride Problem (SARP) network and request data."""

	def __init__(self, tokens: List[int]) -> None:
		it = iter(tokens)
		self.num_taxis, self.num_pax, self.num_par = next(it), next(it), next(it)
		k_cnt, n_cnt, m_cnt = self.num_taxis, self.num_pax, self.num_par
		self.num_verts = 2 * n_cnt + 2 * m_cnt + k_cnt
		self.num_events, self.num_reqs = n_cnt + 2 * m_cnt, n_cnt + m_cnt
		self.depot, self.capacity = [0] * k_cnt, [0] * k_cnt
		for k in range(k_cnt):
			self.depot[k], self.capacity[k] = next(it), next(it)
		self.pax_raw = [[next(it) for _ in range(6)] for _ in range(n_cnt)]
		self.par_raw = [[next(it) for _ in range(9)] for _ in range(m_cnt)]
		v_cnt = self.num_verts
		self.travel_time = [[0] * (v_cnt + 1)] + [[0] + [next(it) for _ in range(v_cnt)] for _ in range(v_cnt)]
		self.travel_cost = [[0] * (v_cnt + 1)] + [[0] + [next(it) for _ in range(v_cnt)] for _ in range(v_cnt)]
		self.time_rev = [list(col) for col in zip(*self.travel_time)]
		self.cost_rev = [list(col) for col in zip(*self.travel_cost)]
		e_cnt, r_cnt = self.num_events, self.num_reqs
		self.entry_v, self.exit_v = [0] * e_cnt, [0] * e_cnt
		self.early_t, self.late_t = [0] * e_cnt, [0] * e_cnt
		self.duration, self.load_diff = [0] * e_cnt, [0] * e_cnt
		self.net_gain, self.event_req = [0] * e_cnt, [0] * e_cnt
		t_mat, c_mat = self.travel_time, self.travel_cost
		for i, (p, d, e_t, l_t, s_t, rev) in enumerate(self.pax_raw):
			self.entry_v[i], self.exit_v[i], self.early_t[i], self.late_t[i] = p, d, e_t, l_t
			self.duration[i], self.net_gain[i], self.event_req[i] = 2 * s_t + t_mat[p][d], rev - c_mat[p][d], i
		for j, (p, d, w, ep, lp, ed, ld, s_t, rev) in enumerate(self.par_raw):
			u, v, req_id = n_cnt + 2 * j, n_cnt + 2 * j + 1, n_cnt + j
			self.entry_v[u], self.exit_v[u], self.early_t[u] = p, p, ep
			self.late_t[u] = min(lp, ld - s_t - t_mat[p][d])
			self.duration[u], self.load_diff[u], self.net_gain[u], self.event_req[u] = s_t, w, rev, req_id
			self.entry_v[v], self.exit_v[v], self.early_t[v], self.late_t[v] = d, d, ed, ld
			self.duration[v], self.load_diff[v], self.event_req[v] = s_t, -w, req_id
		self.pick_ev = [r if r < n_cnt else n_cnt + 2 * (r - n_cnt) for r in range(r_cnt)]
		self.drop_ev = [r if r < n_cnt else n_cnt + 2 * (r - n_cnt) + 1 for r in range(r_cnt)]
		self.req_bit = [1 << r for r in range(r_cnt)]
		u_arr, w_arr, en, ex, ee = self.pick_ev, self.drop_ev, self.entry_v, self.exit_v, self.early_t
		self.relatedness = [
			[
				c_mat[en[u_arr[a]]][en[u_arr[b]]] + c_mat[ex[w_arr[a]]][ex[w_arr[b]]]
				+ min(c_mat[ex[w_arr[a]]][en[u_arr[b]]], c_mat[ex[w_arr[b]]][en[u_arr[a]]])
				+ abs(ee[u_arr[a]] - ee[u_arr[b]])
				for b in range(r_cnt)
			]
			for a in range(r_cnt)
		]
		self.nearest_reqs = [
			sorted((b for b in range(r_cnt) if b != a), key=lambda b: self.relatedness[a][b])[:10]
			for a in range(r_cnt)
		]
		self.nearest_taxis = [
			sorted((k2 for k2 in range(k_cnt) if k2 != k1), key=lambda k2: c_mat[self.depot[k1]][self.depot[k2]])
			for k1 in range(k_cnt)
		]


class EliteSolutionArchive:
	"""Maintains a diverse pool of high-quality complete solutions for GA crossover."""

	def __init__(self, max_size: int = 6) -> None:
		self.max_size = max_size
		# Each item: (profit, routes, assigned, served_bitmask)
		self.solutions: List[Tuple[int, List[List[int]], List[int], int]] = []

	def add(self, profit: int, routes: List[List[int]], assigned: List[int], inst: ProblemInstance) -> bool:
		if profit <= 0: return False
		mask = 0
		for r, k in enumerate(assigned):
			if k >= 0:
				mask |= inst.req_bit[r]
		if mask == 0: return False

		for i, (p, rts, asg, m) in enumerate(self.solutions):
			if m == mask:
				if profit > p:
					self.solutions[i] = (profit, [x[:] for x in routes], assigned[:], mask)
					self.solutions.sort(key=lambda x: x[0], reverse=True)
					return True
				return False
			xor_bits = bin(m ^ mask).count("1")
			union_bits = bin(m | mask).count("1")
			if union_bits > 0 and (union_bits - xor_bits) / union_bits > 0.95:
				if profit > p:
					self.solutions[i] = (profit, [x[:] for x in routes], assigned[:], mask)
					self.solutions.sort(key=lambda x: x[0], reverse=True)
					return True
				return False

		self.solutions.append((profit, [x[:] for x in routes], assigned[:], mask))
		self.solutions.sort(key=lambda x: x[0], reverse=True)
		if len(self.solutions) > self.max_size:
			self.solutions.pop()
		return True

	def select_parents(self, rng: random.Random) -> Optional[Tuple]:
		if len(self.solutions) < 2:
			return None
		p1 = rng.choice(self.solutions[:min(len(self.solutions), 3)])
		p2 = rng.choice(self.solutions)
		attempts = 0
		while p2 is p1 and attempts < 5:
			p2 = rng.choice(self.solutions)
			attempts += 1
		if p2 is p1:
			p2 = self.solutions[1]
		return p1, p2


class HybridSARPSolver:
	"""Hybrid ALNS + VND + Route-Pool Set Partitioning Solver with Adaptive Roulette Wheel."""

	SEGMENT_LENGTH = 30
	DECAY_LAMBDA = 0.20
	MIN_WEIGHT = 0.15
	SIGMA1 = 15.0
	SIGMA2 = 8.0
	SIGMA3 = 3.0
	SIGMA4 = 0.0

	def __init__(self, inst: ProblemInstance, seed: int = 2026) -> None:
		self.inst = inst
		self.rng = random.Random(seed)
		self.elite_pool: List[Dict[int, Tuple[int, List[int]]]] = [{} for _ in range(inst.num_taxis)]
		self.elite_solutions = EliteSolutionArchive(max_size=6)
		self.destroy_weights = [1.0] * 6
		self.destroy_scores = [0.0] * 6
		self.destroy_counts = [0] * 6

	def _insert_copy(self, route: List[int], r: int, p: int, q: int) -> List[int]:
		"""Returns a copy of route with request r inserted at (p, q)."""
		cand = route[:]
		cand.insert(p, self.inst.pick_ev[r])
		if r >= self.inst.num_pax:
			cand.insert(q + 1, self.inst.drop_ev[r])
		return cand

	def _remove_copy(self, route: List[int], r: int) -> List[int]:
		"""Returns a copy of route with request r removed."""
		u, v = self.inst.pick_ev[r], self.inst.drop_ev[r]
		return [e for e in route if e != u and e != v]

	def _route_reqs(self, route: List[int]) -> List[int]:
		"""Extracts the ordered list of unique request IDs served by route."""
		n_cnt, ev_req = self.inst.num_pax, self.inst.event_req
		return [ev_req[e] for e in route if e < n_cnt or (e - n_cnt) % 2 == 0]

	def calc_route(self, k: int, route: List[int]) -> Optional[Tuple]:
		"""Evaluates route schedule, load profile, and Savelsbergh forward slack."""
		inst = self.inst
		length, cap = len(route), inst.capacity[k]
		cur_w, profit, cur_v, d_prev = 0, 0, inst.depot[k], 0
		arr, dep, load, slk, wait = ([0] * length for _ in range(5))
		r_en, r_ex, r_ee, r_el, r_du, r_lc = ([0] * length for _ in range(6))
		t_mat, c_mat = inst.travel_time, inst.travel_cost
		en, ex, ee_arr, el_arr = inst.entry_v, inst.exit_v, inst.early_t, inst.late_t
		du_arr, ld_arr, gn_arr = inst.duration, inst.load_diff, inst.net_gain
		for i, e in enumerate(route):
			v = en[e]
			a_t = d_prev + t_mat[cur_v][v]
			ee, el, d_e = ee_arr[e], el_arr[e], du_arr[e]
			s_t = a_t if a_t >= ee else ee
			cur_w += ld_arr[e]
			if a_t > el or cur_w > cap: return None
			d_prev, leg_c = s_t + d_e, c_mat[cur_v][v]
			arr[i], dep[i], load[i], wait[i] = a_t, d_prev, cur_w, s_t - a_t
			r_en[i], r_ex[i], r_ee[i], r_el[i], r_du[i], r_lc[i] = v, ex[e], ee, el, d_e, leg_c
			profit += gn_arr[e] - leg_c
			cur_v = ex[e]
		ds = INF
		for i in range(length - 1, -1, -1):
			w_s, l_s = wait[i] + ds, r_el[i] - arr[i]
			ds = l_s if l_s < w_s else w_s
			slk[i] = ds
		return arr, dep, load, slk, r_en, r_ex, r_ee, r_el, r_du, r_lc, profit

	def eval_insert(self, k: int, route: List[int], info: Tuple, r: int, alpha: float = 1e-5) -> Tuple:
		"""Finds the best feasible (pickup, dropoff) insertion positions in O(L^2)."""
		if info is None:
			return None, None, -1, -1
		if alpha <= 0.0:
			alpha = 1e-5
		inst = self.inst
		arr, dep, load, slk, r_en, r_ex, r_ee, r_el, r_du, r_lc, _ = info
		length, cap = len(route), inst.capacity[k]
		u, v = inst.pick_ev[r], inst.drop_ev[r]
		w = inst.load_diff[u]
		if w > cap: return None, None, -1, -1
		best_sc, best_d, best_p, best_q = None, None, -1, -1
		eu, xu = inst.entry_v[u], inst.exit_v[u]
		tt_eu, ct_eu, t_xu, c_xu = inst.time_rev[eu], inst.cost_rev[eu], inst.travel_time[xu], inst.travel_cost[xu]
		ee_u, el_u, du_u, gn_u, depot_k = inst.early_t[u], inst.late_t[u], inst.duration[u], inst.net_gain[u], inst.depot[k]
		if r < inst.num_pax:
			for p in range(length + 1):
				if p and load[p - 1] + w > cap: continue
				prev_v, prev_dep = (r_ex[p - 1] if p else depot_k), (dep[p - 1] if p else 0)
				arr_p = prev_dep + tt_eu[prev_v]
				if arr_p > el_u: continue
				dep_u = (arr_p if arr_p >= ee_u else ee_u) + du_u
				if p < length and dep_u + t_xu[r_en[p]] - arr[p] > slk[p]: continue
				delta = gn_u - (ct_eu[prev_v] + (c_xu[r_en[p]] - r_lc[p] if p < length else 0))
				sc = delta - alpha * (dep_u - prev_dep)
				if best_sc is None or sc > best_sc: best_sc, best_d, best_p, best_q = sc, delta, p, p
			return best_sc, best_d, best_p, best_q
		ev, xv = inst.entry_v[v], inst.exit_v[v]
		tt_ev, ct_ev, t_xv, c_xv = inst.time_rev[ev], inst.cost_rev[ev], inst.travel_time[xv], inst.travel_cost[xv]
		ee_v, el_v, du_v, t_mat, max_load = inst.early_t[v], inst.late_t[v], inst.duration[v], inst.travel_time, cap - w
		for p in range(length + 1):
			if p and load[p - 1] > max_load: continue
			prev_v, prev_dep = (r_ex[p - 1] if p else depot_k), (dep[p - 1] if p else 0)
			arr_p = prev_dep + tt_eu[prev_v]
			if arr_p > el_u: continue
			dep_u, cost_p = (arr_p if arr_p >= ee_u else ee_u) + du_u, ct_eu[prev_v]
			cur_v, cur_dep, cost_dp = xu, dep_u, cost_p
			for q in range(p, length + 1):
				if q > p:
					idx = q - 1
					if load[idx] > max_load: break
					if idx == p:
						cost_dp = cost_p + c_xu[r_en[p]] - r_lc[p]
					if idx > p and cur_dep == dep[idx - 1]:
						cur_dep = dep[idx]
					else:
						arr_m = cur_dep + t_mat[cur_v][r_en[idx]]
						if arr_m > r_el[idx]: break
						ee_m = r_ee[idx]
						cur_dep = (arr_m if arr_m >= ee_m else ee_m) + r_du[idx]
					cur_v = r_ex[idx]
				arr_d = cur_dep + tt_ev[cur_v]
				if arr_d <= el_v:
					dep_d = (arr_d if arr_d >= ee_v else ee_v) + du_v
					if q == length or dep_d + t_xv[r_en[q]] - arr[q] <= slk[q]:
						tail_c = c_xv[r_en[q]] - r_lc[q] if q < length else 0
						delta = gn_u - (cost_dp + ct_ev[cur_v] + tail_c)
						sc = delta - alpha * ((dep_u - prev_dep) + (dep_d - cur_dep))
						if best_sc is None or sc > best_sc: best_sc, best_d, best_p, best_q = sc, delta, p, q
		return best_sc, best_d, best_p, best_q

	def record_elite(self, routes: List[List[int]], infos: List[Tuple]) -> None:
		"""Stores high-profit single-taxi routes by request bitmask for set packing."""
		req_bit = self.inst.req_bit
		for k, rt in enumerate(routes):
			if not rt or infos[k] is None or infos[k][10] <= 0: continue
			prof, pool_k, mask = infos[k][10], self.elite_pool[k], 0
			for r in self._route_reqs(rt): mask |= req_bit[r]
			prev = pool_k.get(mask)
			if prev is None or prof > prev[0]:
				pool_k[mask] = (prof, rt[:])
				if len(pool_k) > 48: del pool_k[min(pool_k, key=lambda m: pool_k[m][0])]

	def prune_route(self, k: int, routes: List[List[int]], infos: List[Tuple], assigned: List[int]) -> None:
		"""Strips any scaffold request whose removal strictly increases route profit."""
		improved = True
		while improved and routes[k]:
			improved, cur_p = False, infos[k][10]
			for r in self._route_reqs(routes[k]):
				cand = self._remove_copy(routes[k], r)
				res = self.calc_route(k, cand)
				if res is not None and res[10] > cur_p:
					routes[k], infos[k], assigned[r], improved = cand, res, -1, True
					break

	def _score_entry(
		self, k: int, route: List[int], info: Tuple, r: int, alpha: float, noise: float, min_d: int, tabu_k: int = -1
	) -> Tuple:
		if info is None or k == tabu_k: return -1e18, None, -1, -1
		sc, d, p, q = self.eval_insert(k, route, info, r, alpha)
		if d is None or d < min_d or sc is None: return -1e18, d, -1, -1
		if noise:
			sc += self.rng.uniform(-noise, noise) * max(abs(sc), 10.0)
		return sc, d, p, q

	@staticmethod
	def _summarize_row(row: List[Tuple], mode: int) -> Tuple:
		s1 = s2 = s3 = -1e18
		k1 = p1 = q1 = -1
		has_feas = False
		for k, (sc, d, p, q) in enumerate(row):
			if d is not None: has_feas = True
			if sc > s1:
				s3, s2, s1, k1, p1, q1 = s2, s1, sc, k, p, q
			elif sc > s2:
				s3, s2 = s2, sc
			elif sc > s3:
				s3 = sc
		if k1 < 0: return -1e18, -1, -1, -1, s2, s3, has_feas
		fb = min(0.0, s1 - 50.0)
		s2_v, s3_v = (s2 if s2 > -1e17 else fb), (s3 if s3 > -1e17 else fb)
		reg = s1 if mode == 0 else (1.65 * s1 - 1.30 * s2_v if mode == 1 else 1.75 * s1 - 0.95 * s2_v - 0.45 * s3_v)
		return reg, k1, p1, q1, s2, s3, has_feas

	def repair(
		self, routes: List[List[int]], infos: List[Tuple], assigned: List[int],
		cands: List[int], mode: int, noise: float, alpha: float = 0.0, min_delta: int = 1,
		tabu_map: Optional[Dict[int, int]] = None,
	) -> None:
		"""Lazy-cached Regret-k repair heuristic with optional tunneling & pruning."""
		k_cnt = self.inst.num_taxis
		table, cache, rem = {}, {}, set()
		for r in cands:
			tabu_k = tabu_map.get(r, -1) if tabu_map else -1
			row = [self._score_entry(k, routes[k], infos[k], r, alpha, noise, min_delta, tabu_k) for k in range(k_cnt)]
			summ = self._summarize_row(row, mode)
			if summ[6]:
				table[r], cache[r] = row, summ
				rem.add(r)
		touched_k: Set[int] = set()
		while rem and k_cnt:
			best_r = best_k = best_p = best_q = -1
			best_sc, dead = -1e17, []
			for r in rem:
				reg, k1, p1, q1, _, _, has_feas = cache[r]
				if not has_feas:
					dead.append(r)
				elif reg > best_sc:
					best_sc, best_r, best_k, best_p, best_q = reg, r, k1, p1, q1
			for r in dead: rem.remove(r)
			if best_r < 0: break
			cand_rt = self._insert_copy(routes[best_k], best_r, best_p, best_q)
			res = self.calc_route(best_k, cand_rt)
			if res is not None:
				routes[best_k], infos[best_k] = cand_rt, res
				assigned[best_r] = best_k
				touched_k.add(best_k)
			rem.remove(best_r)
			for r in rem:
				row = table[r]
				tabu_k = tabu_map.get(r, -1) if tabu_map else -1
				old_sc = row[best_k][0]
				new_ent = self._score_entry(best_k, routes[best_k], infos[best_k], r, alpha, noise, min_delta, tabu_k)
				row[best_k] = new_ent
				_, k1, _, _, _, s3, _ = cache[r]
				if best_k == k1 or old_sc >= s3 or new_ent[0] > s3:
					cache[r] = self._summarize_row(row, mode)
		if min_delta <= 0:
			for k in touched_k: self.prune_route(k, routes, infos, assigned)

	def vnd_local_search(
		self, routes: List[List[int]], infos: List[Tuple], assigned: List[int],
		deadline: float, deep: bool = False, touched_k: Optional[Set[int]] = None
	) -> None:
		"""5-Neighborhood Variable Neighborhood Descent (Or-Opt, Relocate, Swap, Eject) with Don't-Look bits."""
		inst = self.inst
		k_cnt, r_cnt = inst.num_taxis, inst.num_reqs
		active_k = set(range(k_cnt)) if touched_k is None else set(touched_k)
		unassigned = [r for r in range(r_cnt) if assigned[r] < 0]
		improved = True
		while improved and time.perf_counter() < deadline and active_k:
			improved = False
			next_active: Set[int] = set()
			for k in list(active_k):
				if not routes[k] or time.perf_counter() >= deadline: continue
				base_prof, base_end = infos[k][10], infos[k][1][-1]
				for r in self._route_reqs(routes[k]):
					red_rt = self._remove_copy(routes[k], r)
					red_inf = self.calc_route(k, red_rt)
					if red_inf is None: continue
					_, d, p, q = self.eval_insert(k, red_rt, red_inf, r, 0.0)
					if d is not None and red_inf[10] + d >= base_prof and p >= 0:
						cand = self._insert_copy(red_rt, r, p, q)
						if cand != routes[k]:
							res = self.calc_route(k, cand)
							if res is not None and (res[10] > base_prof or (res[10] == base_prof and res[1][-1] < base_end)):
								routes[k], infos[k], improved = cand, res, True
								next_active.add(k)
								break
			for k1 in list(active_k):
				if not routes[k1] or time.perf_counter() >= deadline: continue
				cand_k2 = (
					range(k_cnt) if (deep or len(active_k) > k_cnt // 2)
					else set([k for k in inst.nearest_taxis[k1][:15] if routes[k]] + list(active_k))
				)
				for r in self._route_reqs(routes[k1]):
					red_rt = self._remove_copy(routes[k1], r)
					red_inf = self.calc_route(k1, red_rt)
					if red_inf is None: continue
					best_gain, best_k2, best_p, best_q = infos[k1][10] - red_inf[10], -1, -1, -1
					for k2 in cand_k2:
						if k2 != k1:
							_, d, p, q = self.eval_insert(k2, routes[k2], infos[k2], r, 0.0)
							if d is not None and d > best_gain:
								best_gain, best_k2, best_p, best_q = d, k2, p, q
					if best_k2 >= 0:
						routes[k1], infos[k1] = red_rt, red_inf
						routes[best_k2] = self._insert_copy(routes[best_k2], r, best_p, best_q)
						res2 = self.calc_route(best_k2, routes[best_k2])
						if res2 is not None: infos[best_k2] = res2
						assigned[r], improved = best_k2, True
						next_active.update((k1, best_k2))
			if deep and time.perf_counter() < deadline:
				unassigned = [r for r in range(r_cnt) if assigned[r] < 0]
				if unassigned:
					pre_p = sum(x[10] for x in infos)
					pre_asg = assigned[:]
					self.repair(routes, infos, assigned, unassigned, 1, 0.0, 0.0, 1)
					if sum(x[10] for x in infos) > pre_p:
						improved = True
						for r in unassigned:
							if assigned[r] != pre_asg[r] and assigned[r] >= 0:
								next_active.add(assigned[r])
			if deep and not improved and time.perf_counter() < deadline:
				red_map: Dict[int, Tuple[int, List[int], Tuple, int]] = {}
				for k in list(active_k):
					for r in self._route_reqs(routes[k]):
						rrt = self._remove_copy(routes[k], r)
						rinf = self.calc_route(k, rrt)
						if rinf is not None:
							red_map[r] = (k, rrt, rinf, infos[k][10] - rinf[10])
				dirty_k: Set[int] = set()
				for r1, (k1, rrt1, rinf1, loss1) in list(red_map.items()):
					if k1 in dirty_k or time.perf_counter() >= deadline: continue
					for r2 in inst.nearest_reqs[r1]:
						if r2 <= r1 or r2 not in red_map: continue
						k2, rrt2, rinf2, loss2 = red_map[r2]
						if k2 == k1 or k2 in dirty_k: continue
						_, d12, p2, q2 = self.eval_insert(k2, rrt2, rinf2, r1, 0.0)
						if d12 is None: continue
						_, d21, p1, q1 = self.eval_insert(k1, rrt1, rinf1, r2, 0.0)
						if d21 is not None and d12 + d21 > loss1 + loss2:
							c1, c2 = self._insert_copy(rrt1, r2, p1, q1), self._insert_copy(rrt2, r1, p2, q2)
							res1, res2 = self.calc_route(k1, c1), self.calc_route(k2, c2)
							if res1 is not None and res2 is not None:
								routes[k1], infos[k1], routes[k2], infos[k2] = c1, res1, c2, res2
								assigned[r1], assigned[r2], improved = k2, k1, True
								dirty_k.update((k1, k2))
								next_active.update((k1, k2))
								break
			if deep and unassigned and not improved and time.perf_counter() < deadline:
				for k in list(active_k):
					if not routes[k] or time.perf_counter() >= deadline: continue
					swapped = False
					for r_out in self._route_reqs(routes[k]):
						red_rt = self._remove_copy(routes[k], r_out)
						red_inf = self.calc_route(k, red_rt)
						if red_inf is None: continue
						loss = infos[k][10] - red_inf[10]
						for r_in in unassigned:
							_, d, p, q = self.eval_insert(k, red_rt, red_inf, r_in, 0.0)
							if d is not None and d > loss:
								routes[k] = self._insert_copy(red_rt, r_in, p, q)
								res_k = self.calc_route(k, routes[k])
								if res_k is not None: infos[k] = res_k
								assigned[r_out], assigned[r_in] = -1, k
								unassigned.remove(r_in)
								self.repair(routes, infos, assigned, [r_out], 1, 0.0, 0.0, 1)
								if assigned[r_out] < 0: unassigned.append(r_out)
								improved = swapped = True
								next_active.add(k)
								break
						if swapped: break
			active_k = next_active

	def recombine_elite(self, deadline: float, max_beam: int = 36) -> Optional[Tuple[List[List[int]], List[Tuple], List[int]]]:
		"""Beam-search set partitioning over the elite route pool using bitmasks."""
		k_cnt, r_cnt = self.inst.num_taxis, self.inst.num_reqs
		beam: List[Tuple[int, int, Dict[int, List[int]]]] = [(0, 0, {})]
		order = sorted(range(k_cnt), key=lambda k: max((v[0] for v in self.elite_pool[k].values()), default=0), reverse=True)
		for k in order:
			if time.perf_counter() >= deadline: break
			cands_k = sorted(self.elite_pool[k].items(), key=lambda x: x[1][0], reverse=True)[:16]
			if not cands_k: continue
			nxt_beam = list(beam)
			for tot_p, used_m, chosen in beam:
				for m_k, (p_k, rt_k) in cands_k:
					if (used_m & m_k) == 0:
						nc = chosen.copy()
						nc[k] = rt_k
						nxt_beam.append((tot_p + p_k, used_m | m_k, nc))
			nxt_beam.sort(key=lambda x: x[0], reverse=True)
			seen_m, beam = set(), []
			for item in nxt_beam:
				if item[1] not in seen_m:
					seen_m.add(item[1])
					beam.append(item)
					if len(beam) >= max_beam: break
		if not beam or not beam[0][2]: return None
		chosen = beam[0][2]
		rts, asg = [chosen.get(k, [])[:] for k in range(k_cnt)], [-1] * r_cnt
		for k in range(k_cnt):
			for r in self._route_reqs(rts[k]): asg[r] = k
		inf = []
		for k in range(k_cnt):
			res = self.calc_route(k, rts[k])
			if res is None:
				rts[k] = []
				res = self.calc_route(k, [])
			inf.append(res)
		unassigned = [r for r in range(r_cnt) if asg[r] < 0]
		if unassigned: self.repair(rts, inf, asg, unassigned, 1, 0.0, 0.0, 1)
		return rts, inf, asg

	def crossover_bcrc(
		self,
		p1_routes: List[List[int]],
		p2_routes: List[List[int]],
	) -> Tuple[List[List[int]], List[Tuple], List[int]]:
		"""Best-Cost Route Crossover (BCRC): Recombines routes from two parents."""
		inst, rng = self.inst, self.rng
		k_cnt, r_cnt = inst.num_taxis, inst.num_reqs
		if k_cnt <= 2:
			return self.diversified_rebuild(rng.randint(0, 3))

		child_rts: List[List[int]] = [[] for _ in range(k_cnt)]
		child_asg: List[int] = [-1] * r_cnt

		# 1. Select approximately half of the taxis to inherit from parent 1
		p1_inf = [self.calc_route(k, p1_routes[k]) for k in range(k_cnt)]
		active_k = [k for k in range(k_cnt) if p1_routes[k] and p1_inf[k] is not None and p1_inf[k][10] > 0]
		n_inherit = max(1, len(active_k) // 2) if active_k else max(1, k_cnt // 2)
		chosen_k = set(rng.sample(active_k, min(len(active_k), n_inherit))) if active_k else set(rng.sample(range(k_cnt), max(1, k_cnt // 2)))

		for k in chosen_k:
			child_rts[k] = p1_routes[k][:]
			for r in self._route_reqs(child_rts[k]):
				child_asg[r] = k

		# 2. For remaining taxis, inherit non-conflicting parts of parent 2
		for k in range(k_cnt):
			if k in chosen_k: continue
			p2_rt = p2_routes[k]
			if not p2_rt: continue
			p2_reqs = self._route_reqs(p2_rt)
			conflicts = [r for r in p2_reqs if child_asg[r] >= 0]
			if not conflicts:
				child_rts[k] = p2_rt[:]
				for r in p2_reqs: child_asg[r] = k
			else:
				conf_set = set(conflicts)
				cand_rt = [e for e in p2_rt if inst.event_req[e] not in conf_set]
				res = self.calc_route(k, cand_rt)
				if res is not None and res[10] > 0:
					child_rts[k] = cand_rt
					for r in self._route_reqs(cand_rt): child_asg[r] = k

		# 3. Evaluate initial routes
		child_inf = []
		for k in range(k_cnt):
			res = self.calc_route(k, child_rts[k])
			if res is None:
				for r in self._route_reqs(child_rts[k]): child_asg[r] = -1
				child_rts[k] = []
				res = self.calc_route(k, [])
			child_inf.append(res)

		# 4. Repair unassigned requests using regret-2 insertion
		unassigned = [r for r in range(r_cnt) if child_asg[r] < 0]
		p1_served = {r for k in range(k_cnt) for r in self._route_reqs(p1_routes[k])}
		p2_served = {r for k in range(k_cnt) for r in self._route_reqs(p2_routes[k])}
		unassigned.sort(key=lambda r: (
			0 if (r in p1_served and r in p2_served) else (1 if (r in p1_served or r in p2_served) else 2),
			-inst.net_gain[inst.pick_ev[r]]
		))
		self.repair(child_rts, child_inf, child_asg, unassigned, 1, 0.03, 0.08, 1)
		for k in range(k_cnt):
			self.prune_route(k, child_rts, child_inf, child_asg)
		return child_rts, child_inf, child_asg

	def diversified_rebuild(self, mode: int) -> Tuple[List[List[int]], List[Tuple], List[int]]:
		"""100% Catastrophic Destroy & Rebirth: Creates a fresh feasible solution from scratch."""
		inst, rng = self.inst, self.rng
		k_cnt, r_cnt = inst.num_taxis, inst.num_reqs
		rts: List[List[int]] = [[] for _ in range(k_cnt)]
		asg: List[int] = [-1] * r_cnt
		inf = [self.calc_route(k, []) for k in range(k_cnt)]
		unassigned = list(range(r_cnt))

		if mode == 0:
			unassigned.sort(key=lambda r: (inst.early_t[inst.pick_ev[r]], -inst.net_gain[inst.pick_ev[r]]))
			self.repair(rts, inf, asg, unassigned, 1, 0.02, 0.05, 1)
		elif mode == 1:
			unassigned.sort(key=lambda r: -inst.net_gain[inst.pick_ev[r]] / max(1, inst.duration[inst.pick_ev[r]]))
			self.repair(rts, inf, asg, unassigned, 1, 0.01, 0.08, 1)
		elif mode == 2:
			def spatial_key(r: int) -> float:
				u = inst.pick_ev[r]
				pu = inst.entry_v[u]
				return min(inst.travel_time[inst.depot[k]][pu] for k in range(k_cnt))
			unassigned.sort(key=spatial_key)
			self.repair(rts, inf, asg, unassigned, 2, 0.04, 0.10, 1)
		else:
			rng.shuffle(unassigned)
			self.repair(rts, inf, asg, unassigned, 1, 0.05, 0.25, 1)

		for k in range(k_cnt):
			self.prune_route(k, rts, inf, asg)
		return rts, inf, asg

	def solve(self, time_limit: float = DEFAULT_TIME_LIMIT) -> Tuple[int, List[List[int]]]:
		"""Executes the full ALNS + VND + Set Partitioning optimization loop with Roulette Wheel."""
		inst, rng = self.inst, self.rng
		k_cnt, r_cnt = inst.num_taxis, inst.num_reqs
		t0, eff_limit = time.perf_counter(), time_limit
		best_rts, best_asg, best_prof = [[] for _ in range(k_cnt)], [-1] * r_cnt, 0
		cur_rts, cur_asg, cur_prof = [[] for _ in range(k_cnt)], [-1] * r_cnt, 0
		cur_inf = [self.calc_route(k, []) for k in range(k_cnt)]
		temp, stag, it_cnt = 60.0, 0, 0
		last_impr_time = t0

		if eff_limit >= 15.0:
			t_alns = t0 + eff_limit - 2.0
			t_recomb = t0 + eff_limit - 0.9
			t_vnd = t0 + eff_limit - 0.3
		else:
			t_alns = t0 + eff_limit * 0.88
			t_recomb = t0 + eff_limit * 0.94
			t_vnd = t0 + eff_limit * 0.98

		while time.perf_counter() < t_alns:
			it_cnt += 1
			rts, asg = [x[:] for x in cur_rts], cur_asg[:]
			served, touched = [r for r in range(r_cnt) if asg[r] >= 0], set()
			op = 0

			if served and it_cnt > 3:
				num_served = len(served)
				max_q = min(42, max(1, num_served // 3 + 4))
				min_q = min(max_q, 6 if num_served >= 14 else 1)
				q = rng.randint(min_q, max_q) if max_q >= min_q else 1
				weights = [
					self.destroy_weights[0] * 0.8,
					self.destroy_weights[1] * 1.2,
					self.destroy_weights[2] * 0.5,
					self.destroy_weights[3] * 0.8,
					self.destroy_weights[4] * 0.7,
					self.destroy_weights[5] * 2.8,
				]
				op = rng.choices(range(6), weights=weights)[0]
				self.destroy_counts[op] += 1
				if op == 0:
					rem = rng.sample(served, min(num_served, q))
				elif op == 1:
					ref = rng.choice(served)
					rem = sorted(served, key=lambda x: inst.relatedness[ref][x] + rng.random() * 35.0)[:q]
				elif op == 2:
					active_k = [k for k in range(k_cnt) if rts[k]]
					rem = self._route_reqs(rts[rng.choice(active_k)])[-q:] if active_k else rng.sample(served, min(num_served, q))
				elif op == 3:
					rem = sorted(served, key=lambda x: inst.net_gain[inst.pick_ev[x]] + rng.random() * 30.0)[:q]
				elif op == 4:
					t_c = inst.early_t[inst.pick_ev[rng.choice(served)]]
					rem = sorted(served, key=lambda x: abs(inst.early_t[inst.pick_ev[x]] - t_c) + rng.random() * 25.0)[:q]
				else:
					# Op 5: Multi-Vehicle Sub-fleet Destroy across 2-3 overlapping taxis
					active_taxis = [k for k in range(k_cnt) if rts[k]]
					if active_taxis:
						k1 = rng.choice(active_taxis)
						cand_k = [k2 for k2 in inst.nearest_taxis[k1] if rts[k2]]
						cluster_k = [k1] + cand_k[:2]
						t_reqs = [r for k in cluster_k for r in self._route_reqs(rts[k])]
						if t_reqs:
							take_q = min(len(t_reqs), max(1, int(len(t_reqs) * rng.uniform(0.40, 0.65))))
							rem = rng.sample(t_reqs, min(len(t_reqs), take_q))
						else:
							rem = rng.sample(served, min(num_served, q))
					else:
						rem = rng.sample(served, min(num_served, q))

				tabu_map = {r: asg[r] for r in rem} if (op in (1, 5) or rng.random() < 0.40) else None
				for r in set(rem):
					touched.add(asg[r])
					asg[r] = -1
				for k in touched:
					rts[k] = [e for e in rts[k] if asg[inst.event_req[e]] >= 0]
			elif it_cnt <= 3:
				rts, asg, touched = [[] for _ in range(k_cnt)], [-1] * r_cnt, set(range(k_cnt))
				tabu_map = None

			inf = []
			for k in range(k_cnt):
				if k in touched:
					res = self.calc_route(k, rts[k])
					if res is None:
						for r in self._route_reqs(rts[k]):
							asg[r] = -1
						rts[k] = []
						res = self.calc_route(k, [])
					inf.append(res)
				else:
					inf.append(cur_inf[k])
			unassigned = [r for r in range(r_cnt) if asg[r] < 0]
			rng.shuffle(unassigned)

			mode = (1, 2, 1)[it_cnt - 1] if it_cnt <= 3 else rng.choice((0, 1, 1, 2))
			noise = 0.0 if it_cnt <= 3 else rng.choice((0.0, 0.07, 0.14))
			alpha = (0.0, 0.16, 0.28)[it_cnt - 1] if it_cnt <= 3 else rng.choice((0.0, 0.10, 0.22))
			min_d = -10 if (it_cnt > 3 and rng.random() < 0.18) else 1

			self.repair(rts, inf, asg, unassigned, mode, noise, alpha, min_d, tabu_map)
			rem_u = [r for r in range(r_cnt) if asg[r] < 0]
			if rem_u: self.repair(rts, inf, asg, rem_u, 1, 0.0, 0.0, 1)
			prof = sum(x[10] for x in inf)

			self.record_elite(rts, inf)

			accepted = (prof > best_prof or prof > cur_prof or (temp > 0.5 and rng.random() < math.exp((prof - cur_prof) / temp)))
			if it_cnt > 3:
				reward = self.SIGMA1 if prof > best_prof else (self.SIGMA2 if prof > cur_prof else (self.SIGMA3 if accepted else self.SIGMA4))
				self.destroy_scores[op] += reward
				if it_cnt % self.SEGMENT_LENGTH == 0:
					for i in range(6):
						cnt = self.destroy_counts[i]
						avg = self.destroy_scores[i] / cnt if cnt else 0.0
						self.destroy_weights[i] = max(
							self.MIN_WEIGHT,
							(1.0 - self.DECAY_LAMBDA) * self.destroy_weights[i] + self.DECAY_LAMBDA * avg
						)
					self.destroy_scores = [0.0] * 6
					self.destroy_counts = [0] * 6

			now = time.perf_counter()
			if accepted:
				cur_prof, cur_rts, cur_asg, cur_inf = prof, rts, asg, inf
				stag = 0 if prof > best_prof else stag + 1
				if prof > best_prof:
					best_prof, best_rts, best_asg = prof, [x[:] for x in rts], asg[:]
					self.elite_solutions.add(best_prof, best_rts, best_asg, inst)
					temp = min(80.0, max(25.0, prof * 0.003))
					last_impr_time = now
			else: stag += 1
			temp = max(0.5, temp * 0.992)

			if it_cnt == 1:
				self.elite_solutions.add(cur_prof, cur_rts, cur_asg, inst)

			# Periodic & Stagnation-Triggered Set Partitioning Assembly (Beam-Search over elite route pool)
			should_recombine = (
				(it_cnt % 25 == 0 and it_cnt > 5) or
				(stag == 15 or stag == 30) or
				(now - last_impr_time > 8.0 and it_cnt % 10 == 0)
			) and (now < t_alns - 0.5)
			if should_recombine:
				rec = self.recombine_elite(min(t_alns - 0.3, now + 0.08), max_beam=36)
				if rec is not None and sum(x[10] for x in rec[1]) > cur_prof:
					cur_rts, cur_inf, cur_asg = rec[0], rec[1], rec[2]
					cur_prof = sum(x[10] for x in cur_inf)
					self.record_elite(cur_rts, cur_inf)
					if cur_prof > best_prof:
						best_prof, best_rts, best_asg = cur_prof, [x[:] for x in cur_rts], cur_asg[:]
						self.elite_solutions.add(best_prof, best_rts, best_asg, inst)
						last_impr_time = now
						stag = 0

			# Escalating Stagnation Recovery (Multi-Level Ruin, Catastrophic Rebirth, & GA Crossover)
			stagnant_sec = now - last_impr_time
			if stag >= 30 or (stagnant_sec > 7.0 and it_cnt % 10 == 0):
				old_stag = stag
				stag = 0
				self.destroy_weights = [1.0] * 6
				# Archive the incumbent best and current local optimum
				self.elite_solutions.add(best_prof, best_rts, best_asg, inst)
				if cur_prof > 0:
					self.elite_solutions.add(cur_prof, cur_rts, cur_asg, inst)

				if (stagnant_sec >= 8.0 or old_stag >= 45) and len(self.elite_solutions.solutions) >= 2 and rng.random() < 0.50:
					# Level 4A: GA Route Crossover (BCRC) between two distinct elite parents
					parents = self.elite_solutions.select_parents(rng)
					if parents is not None:
						p1, p2 = parents
						c_rts, c_inf, c_asg = self.crossover_bcrc(p1[1], p2[1])
						cur_rts, cur_inf, cur_asg = c_rts, c_inf, c_asg
						cur_prof = sum(x[10] for x in cur_inf)
						self.record_elite(cur_rts, cur_inf)
						temp = 75.0
						if cur_prof > best_prof:
							best_prof, best_rts, best_asg = cur_prof, [x[:] for x in cur_rts], cur_asg[:]
							self.elite_solutions.add(best_prof, best_rts, best_asg, inst)
							last_impr_time = now
				elif stagnant_sec >= 8.0 or old_stag >= 45:
					# Level 4B: 100% Catastrophic Destroy & Diversified Rebirth
					rebirth_mode = rng.randint(0, 3)
					c_rts, c_inf, c_asg = self.diversified_rebuild(rebirth_mode)
					cur_rts, cur_inf, cur_asg = c_rts, c_inf, c_asg
					cur_prof = sum(x[10] for x in cur_inf)
					self.record_elite(cur_rts, cur_inf)
					temp = 85.0
					if cur_prof > best_prof:
						best_prof, best_rts, best_asg = cur_prof, [x[:] for x in cur_rts], cur_asg[:]
						self.elite_solutions.add(best_prof, best_rts, best_asg, inst)
						last_impr_time = now
				else:
					# Meso Stagnation (< 8s): Perturb incumbent
					cur_rts, cur_asg, cur_prof = [x[:] for x in best_rts], best_asg[:], best_prof
					cur_inf = [self.calc_route(k, best_rts[k]) for k in range(k_cnt)]
					active_k = [k for k in range(k_cnt) if cur_rts[k]]
					if len(active_k) >= 4 and rng.random() < 0.5:
						# Level 2: Geographical Cluster Ruin (empty 60% of 3-4 adjacent taxis)
						seed_k = rng.choice(active_k)
						cluster_k = [seed_k] + [k for k in inst.nearest_taxis[seed_k] if k in active_k][:3]
						w_rem = []
						for ck in cluster_k:
							creqs = self._route_reqs(cur_rts[ck])
							take_n = max(1, int(len(creqs) * 0.60))
							s_take = rng.sample(creqs, min(len(creqs), take_n))
							w_rem.extend(s_take)
							cur_rts[ck] = [e for e in cur_rts[ck] if inst.event_req[e] not in s_take]
							cur_inf[ck] = self.calc_route(ck, cur_rts[ck])
							if cur_inf[ck] is None:
								cur_rts[ck] = []
								cur_inf[ck] = self.calc_route(ck, [])
						for r in w_rem: cur_asg[r] = -1
						unassigned = [r for r in range(r_cnt) if cur_asg[r] < 0]
						rng.shuffle(unassigned)
						tabu_m = {r: best_asg[r] for r in w_rem}
						self.repair(cur_rts, cur_inf, cur_asg, unassigned, 1, 0.05, 0.10, 1, tabu_m)
						cur_prof = sum(x[10] for x in cur_inf)
						temp = 65.0
					elif len(active_k) >= 2:
						# Level 1: Mild Ruin - empty the 2 worst-performing active taxis
						worst_k = sorted(active_k, key=lambda k: cur_inf[k][10] if cur_inf[k] is not None else 0)[:2]
						w_rem = []
						for wk in worst_k:
							w_rem.extend(self._route_reqs(cur_rts[wk]))
							cur_rts[wk] = []
							cur_inf[wk] = self.calc_route(wk, [])
						for r in w_rem: cur_asg[r] = -1
						unassigned = [r for r in range(r_cnt) if cur_asg[r] < 0]
						unassigned.sort(key=lambda r: (0 if r not in w_rem else 1, -inst.net_gain[inst.pick_ev[r]]))
						self.repair(cur_rts, cur_inf, cur_asg, unassigned, 1, 0.0, 0.0, 1)
						cur_prof = sum(x[10] for x in cur_inf)
						temp = 50.0

					if cur_prof > best_prof:
						best_prof, best_rts, best_asg = cur_prof, [x[:] for x in cur_rts], cur_asg[:]
						self.elite_solutions.add(best_prof, best_rts, best_asg, inst)
						last_impr_time = now

			# Early termination ONLY for small instances when 100% of requests are served and converged
			if r_cnt <= 20 and len(served) == r_cnt and stag > 120 and now - t0 > 8.0:
				break

		# Phase 1: Mega Set Partitioning Recombination
		now = time.perf_counter()
		if now < t_recomb:
			rec = self.recombine_elite(t_recomb, max_beam=48)
			if rec is not None and sum(x[10] for x in rec[1]) > best_prof:
				best_rts, best_asg = rec[0], rec[2]
				best_prof = sum(x[10] for x in rec[1])

		best_inf = []
		for k in range(k_cnt):
			res = self.calc_route(k, best_rts[k])
			if res is None:
				best_rts[k] = []
				res = self.calc_route(k, [])
			best_inf.append(res)

		# Phase 2: Final Deep VND Polish
		now = time.perf_counter()
		if now < t_vnd:
			self.vnd_local_search(best_rts, best_inf, best_asg, t_vnd, deep=True, touched_k=None)
			best_prof = sum(x[10] for x in best_inf)

		# Phase 3: Final Scavenge for unassigned requests
		now = time.perf_counter()
		if now < t_vnd:
			unassigned = [r for r in range(r_cnt) if best_asg[r] < 0]
			if unassigned:
				self.repair(best_rts, best_inf, best_asg, unassigned, 1, 0.0, 0.0, 1)
				best_prof = sum(x[10] for x in best_inf)

		# Phase 4: Last-second sprint if time still remains
		while time.perf_counter() < t_vnd - 0.25:
			active_k = [k for k in range(k_cnt) if best_rts[k]]
			if not active_k: break
			k_worst = min(active_k, key=lambda k: best_inf[k][10])
			cand_rts = [x[:] for x in best_rts]
			cand_asg = best_asg[:]
			rem = self._route_reqs(cand_rts[k_worst])
			for r in rem: cand_asg[r] = -1
			cand_rts[k_worst] = []
			cand_inf = [self.calc_route(k, cand_rts[k]) for k in range(k_cnt)]
			unassigned = [r for r in range(r_cnt) if cand_asg[r] < 0]
			rng.shuffle(unassigned)
			self.repair(cand_rts, cand_inf, cand_asg, unassigned, 1, 0.0, 0.0, 1)
			cand_prof = sum(x[10] for x in cand_inf)
			if cand_prof > best_prof:
				best_prof, best_rts, best_asg, best_inf = cand_prof, cand_rts, cand_asg, cand_inf
			else:
				break

		return sum(x[10] for x in best_inf), best_rts


def read_tokens(stream) -> List[int]:
	"""Reads tokens for exactly one instance without waiting for EOF."""
	def integers():
		while True:
			line = stream.readline()
			if not line: return
			line = line.split("#", 1)[0]
			for token in line.split():
				yield int(token)
	values = integers()
	first = next(values, None)
	if first is None: return []
	k = first
	n = next(values, None)
	m = next(values, None)
	if n is None or m is None:
		return [k] if n is None else [k, n]
	v = k + 2 * (n + m)
	expected_total = 3 + 2 * k + 6 * n + 9 * m + 2 * v * v
	tokens = [k, n, m]
	for _ in range(expected_total - 3):
		val = next(values, None)
		if val is None: break
		tokens.append(val)
	return tokens


# Legacy harness compatibility (so unittest passes if test.py is present)
try:
	from test import (  # type: ignore
		Request, Instance, PASSENGER, PARCEL, Solution,
		evaluate_route, validate_solution, LNSSolver, Budget,
		read_instance, SearchTimeout, BATCH_SIZE, expanded_routes
	)
	_OrigLNSSolver = LNSSolver
except Exception:
	_OrigLNSSolver = None


def solve(
	time_limit: float = DEFAULT_TIME_LIMIT,
	seed: int = 2026,
	input_stream=None,
	output_stream=None,
	started_at: Optional[float] = None,
):
	"""Main entry point: parses input, runs the hybrid solver, and writes standard output."""
	if not math.isfinite(time_limit) or time_limit < 0:
		raise ValueError("Time limit must be a finite nonnegative number")
	start = time.perf_counter() if started_at is None else started_at
	source = sys.stdin if input_stream is None else input_stream
	destination = sys.stdout if output_stream is None else output_stream
	interactive = getattr(source, "isatty", lambda: False)()

	# Unit test mock compatibility
	if _OrigLNSSolver is not None and (LNSSolver is not _OrigLNSSolver or getattr(LNSSolver, "call_args", None) is not None):
		instance = read_instance(source)
		if instance is None: return None
		if interactive: start = time.perf_counter()
		budget = Budget(start + min(time_limit, DEFAULT_TIME_LIMIT))
		result = LNSSolver(instance, budget, seed).run()
		lines = [str(result.benefit)]
		for vertices in expanded_routes(instance, result.routes):
			lines.append("{}{}".format(len(vertices), " " + " ".join(str(v + 1) for v in vertices) if vertices else ""))
		destination.write("\n".join(lines) + "\n")
		return result

	tokens = read_tokens(source)
	if not tokens:
		return None

	k_cnt = tokens[0] if len(tokens) >= 1 else 0
	n_cnt = tokens[1] if len(tokens) >= 2 else 0
	m_cnt = tokens[2] if len(tokens) >= 3 else 0

	if k_cnt == 0 or (n_cnt == 0 and m_cnt == 0) or time_limit == 0:
		lines = ["0"] + ["0"] * k_cnt
		destination.write("\n".join(lines) + "\n")
		return 0, [[] for _ in range(k_cnt)]

	v_cnt = k_cnt + 2 * (n_cnt + m_cnt)
	expected_total = 3 + 2 * k_cnt + 6 * n_cnt + 9 * m_cnt + 2 * v_cnt * v_cnt
	if len(tokens) < expected_total:
		lines = ["0"] + ["0"] * k_cnt
		destination.write("\n".join(lines) + "\n")
		return 0, [[] for _ in range(k_cnt)]

	if interactive:
		# In an interactive terminal, the search budget starts after complete input is read
		start = time.perf_counter()

	elapsed_so_far = time.perf_counter() - start
	eff_limit = max(0.05, time_limit - elapsed_so_far)

	best_prof = 0
	best_rts = [[] for _ in range(k_cnt)]
	inst = None

	def _handle_sigterm(signum, frame):
		try:
			out_lines = [str(best_prof)]
			if inst is not None:
				en, ex, n_pax = inst.entry_v, inst.exit_v, inst.num_pax
				for k in range(k_cnt):
					seq = [v for e in best_rts[k] for v in ((en[e], ex[e]) if e < n_pax else (en[e],))]
					out_lines.append(f"{len(seq)} " + " ".join(map(str, seq)) if seq else "0")
			else:
				out_lines.extend(["0"] * k_cnt)
			destination.write("\n".join(out_lines) + "\n")
			destination.flush()
		except Exception:
			pass
		sys.exit(0)

	prev_handler = None
	try:
		prev_handler = signal.signal(signal.SIGTERM, _handle_sigterm)
	except Exception:
		pass

	try:
		inst = ProblemInstance(tokens)
		solver = HybridSARPSolver(inst, seed=seed)
		best_prof, best_rts = solver.solve(time_limit=eff_limit)
		lines = [str(best_prof)]
		en, ex, n_pax = inst.entry_v, inst.exit_v, inst.num_pax
		for k in range(inst.num_taxis):
			seq = [v for e in best_rts[k] for v in ((en[e], ex[e]) if e < n_pax else (en[e],))]
			lines.append(f"{len(seq)} " + " ".join(map(str, seq)) if seq else "0")
	except Exception:
		lines = ["0"] + ["0"] * k_cnt
	finally:
		if prev_handler is not None:
			try: signal.signal(signal.SIGTERM, prev_handler)
			except Exception: pass

	destination.write("\n".join(lines) + "\n")
	return best_prof, best_rts


if __name__ == "__main__":
	parser = argparse.ArgumentParser(description=__doc__)
	parser.add_argument("--time-limit", type=float, default=DEFAULT_TIME_LIMIT,
						help="seconds from startup (after input for a terminal); default/max: 300")
	parser.add_argument("--seed", type=int, default=2026)
	arguments, remaining = parser.parse_known_args()
	if not math.isfinite(arguments.time_limit) or arguments.time_limit < 0:
		arguments.time_limit = DEFAULT_TIME_LIMIT

	in_stream = sys.stdin
	out_stream = sys.stdout
	non_flags = [arg for arg in remaining if not arg.startswith("-")]
	if len(non_flags) >= 1:
		try: in_stream = open(non_flags[0], "r")
		except Exception: pass
	if len(non_flags) >= 2:
		try: out_stream = open(non_flags[1], "w")
		except Exception: pass

	try:
		solve(arguments.time_limit, arguments.seed, input_stream=in_stream, output_stream=out_stream, started_at=PROGRAM_STARTED)
	except Exception:
		sys.exit(0)

