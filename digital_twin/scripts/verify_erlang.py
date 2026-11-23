import sys, pathlib, time, math
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import numpy as np
from evdt import charging as chg


def erlang_b_recursive(c, a):
    inv = 1.0
    for i in range(1, int(c) + 1):
        inv = 1.0 + inv * i / a
    return 1.0 / inv


print("closed form vs recursion (crossing the c=256 threshold):")
for c in (1, 5, 50, 200, 256, 257, 300, 1000, 5000):
    for rho in (0.3, 0.7, 0.95):
        a = rho * c
        ref = erlang_b_recursive(c, a)
        got = chg.erlang_b(c, a)
        err = abs(got - ref) / max(ref, 1e-300)
        print(f"  c={c:5d} rho={rho:4.2f}  ref={ref:.6e}  got={got:.6e}  rel.err={err:.2e}")

print("\nErlang-C timing at large c:")
for c in (10_000, 500_000, 4_000_000):
    t0 = time.perf_counter()
    v = chg.erlang_c(c, 0.6 * c)
    print(f"  c={c:9d}  P_wait={v:.4e}  {(time.perf_counter()-t0)*1e3:.3f} ms")

print("\nwaiting_time sanity:")
for c, rho in ((4, 0.55), (12, 0.80), (100000, 0.5)):
    w, r = chg.waiting_time(c, rho * c / 0.6, 0.6)
    print(f"  c={c:8d} rho={rho:.2f} -> wait={w*60:.4f} min, sat={r:.3f}")
