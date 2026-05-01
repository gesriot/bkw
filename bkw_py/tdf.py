#!/usr/bin/env python3
"""
TDF - Thermodynamic Functions of Ideal Gases and Solids
Fixed-format implementation for TDF data files.
"""

from __future__ import annotations

import math
import threading
from pathlib import Path
from typing import Callable

from bkw_py._cancel import CancelledError

try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
except Exception:
    plt = None


def parse_reference_float(s: str) -> float:
    s = s.strip()
    if not s:
        return 0.0
    try:
        return float(s)
    except ValueError:
        pass

    parts = s.split()
    if len(parts) == 2:
        return float(parts[0]) * (10.0 ** int(parts[1]))

    raise ValueError(f"Cannot parse reference float: '{s}'")


def read_e18(line: str, count: int):
    vals = []
    for i in range(count):
        start = i * 18
        end = start + 18
        field = line[start:end] if start < len(line) else ""
        vals.append(parse_reference_float(field))
    return vals


def read_i5(line: str, count: int):
    vals = []
    for i in range(count):
        start = i * 5
        end = start + 5
        field = line[start:end] if start < len(line) else ""
        field = field.strip()
        vals.append(int(field) if field else 0)
    return vals


def fmt_1pe(width: int, prec: int, val: float) -> str:
    return f"{val:{width}.{prec}E}"


def fmt_e18_11(val: float) -> str:
    if val == 0.0:
        return f"{' 0.00000000000E+00':>18s}"

    sign = "-" if val < 0 else " "
    aval = abs(val)
    exp = int(math.floor(math.log10(aval))) + 1
    mant = aval / (10.0 ** exp)
    return f"{sign}{mant:.11f}E{'+' if exp >= 0 else '-'}{abs(exp):02d}"


def write_poly_line(fout, label: str, c):
    line = f"0   {label}"
    line += fmt_1pe(19, 11, c[0])
    line += fmt_1pe(19, 11, c[1]) + "T"
    line += fmt_1pe(19, 11, c[2]) + "T*2"
    line += fmt_1pe(19, 11, c[3]) + "T*3"
    line += fmt_1pe(19, 11, c[4]) + "T*4"
    fout.write(line + "\n")


def poly(x, n, a):
    y = a[n]
    for i in range(2, n + 1):
        j = n - i + 1
        y = a[j] + y * x
    return y


def pfts(m, km, iw, x_in, f2_in, w_in=None):
    # 1-based work arrays preserve the established operation order.
    x = [0.0] + list(x_in)
    f2 = [0.0] + list(f2_in)

    s = [0.0] * 6
    st = [0.0] * 6
    sb = [0.0] * 6
    f = [0.0] * (m + 1)
    pm = [0.0] * (m + 1)
    p = [0.0] * (m + 1)
    b = [0.0] * 6
    dely = [0.0] * (m + 1)
    w = [0.0] * (m + 1)
    a = [[0.0] * 6 for _ in range(6)]
    t = [0.0] * 6
    y = [0.0] * (m + 1)

    fm = 0.0
    a[1][1] = 1.0
    a[2][2] = 1.0
    fbar = 0.0
    xbar = 0.0

    for i in range(1, m + 1):
        if iw == 0:
            w2 = 1.0
            w[i] = 1.0
        else:
            w[i] = w_in[i - 1]
            w2 = math.sqrt(w[i])
        fm += w[i]
        f[i] = w2 * f2[i]
        pm[i] = w2
        fbar += f[i] * pm[i]
        xbar += x[i] * (pm[i] ** 2)

    xbar /= fm
    t[1] = fbar / fm
    a[2][1] = -xbar
    pxf = 0.0
    pxp = 0.0

    for i in range(1, m + 1):
        p[i] = (x[i] - xbar) * pm[i]
        pxf += p[i] * f[i]
        pxp += p[i] * p[i]

    t[2] = pxf / pxp
    pmxpm = fm
    s[1] = pmxpm
    km1 = km + 1

    b[1] = t[1] * a[1][1] + t[2] * a[2][1]
    b[2] = t[2] * a[2][2]

    sigma = 0.0
    for k in range(2, km1 + 1):
        if k > 2:
            xpxp = 0.0
            xpxpm = 0.0
            b[k] = 0.0
            for j in range(1, m + 1):
                xp = x[j] * p[j]
                xpxp += xp * p[j]
                xpxpm += xp * pm[j]

            alpha = xpxp / pxp
            beta = xpxpm / pmxpm
            ppxf = 0.0
            ppxpp = 0.0

            for i in range(1, m + 1):
                pt = p[i]
                p[i] = x[i] * pt - alpha * pt - beta * pm[i]
                ppxf += p[i] * f[i]
                ppxpp += p[i] * p[i]
                pm[i] = pt

            t[k] = ppxf / ppxpp
            pmxpm = pxp
            pxp = ppxpp
            a[k][1] = -alpha * a[k - 1][1] - beta * a[k - 2][1]
            a[k][k - 1] = a[k - 1][k - 2] - a[k - 1][k - 1] * alpha
            a[k][k] = 1.0

            if k > 3:
                k1 = k - 2
                for i in range(2, k1 + 1):
                    a[k][i] = a[k - 1][i - 1] - alpha * a[k - 1][i] - beta * a[k - 2][i]

            for i in range(1, k + 1):
                b[i] += t[k] * a[k][i]

        sig2 = 0.0
        for i in range(1, m + 1):
            y[i] = poly(x[i], k, b)
            dely[i] = y[i] - f2[i]
            sig2 += (dely[i] ** 2) * w[i]

        sig2 /= float(m - k)
        sigma = math.sqrt(sig2)
        s[k] = pxp

        for i in range(1, k + 1):
            st[i] = sigma / math.sqrt(s[i])

        for i in range(1, k + 1):
            sb[i] = 0.0
            for j in range(i, k + 1):
                sb[i] += (a[j][i] * st[j]) ** 2
            sb[i] = math.sqrt(sb[i])

    return sigma, [b[i] for i in range(1, km + 2)], [y[i] for i in range(1, m + 1)], [dely[i] for i in range(1, m + 1)]


def sanitize_label(label: str) -> str:
    keep = []
    for ch in label.strip():
        if ch.isalnum() or ch in ("-", "_"):
            keep.append(ch)
        elif ch.isspace():
            keep.append("_")
    out = "".join(keep).strip("_")
    return out if out else "material"


def save_plot(out_dir: Path, name: str, x, y, xlabel: str, ylabel: str, title: str, indg: int):
    if plt is None:
        return

    figsize = (8.0, 6.0) if indg == 0 else (13.7, 10.0)
    fig, ax = plt.subplots(figsize=figsize)
    ax.plot(x, y, marker="o", markersize=2.5, linewidth=1.0)
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    ax.set_title(title)
    ax.grid(True, linestyle=":", linewidth=0.5)
    fig.tight_layout()
    fig.savefig(out_dir / f"{name}.png", dpi=150)
    plt.close(fig)


def write_common_output(fout, fscoef, label72, itp, temp, fo, soft, so, sic, xa, fa, ha, sigma, stt, cv=None, da=None):
    write_poly_line(fout, "Fo-Ho/T =", fa)
    write_poly_line(fout, "H-Ho =", ha)
    write_poly_line(fout, "So =", xa)

    if itp >= 4:
        write_poly_line(fout, "Cv =", da)
        fout.write("0    Temp (deg k)      Fo-Ho/T (c/m/d)       Ho (kc/m)         So (c/m/d)          Cv (c/m/d)           ic\n")
        for i in range(len(temp)):
            line = ""
            line += fmt_1pe(19, 8, temp[i])
            line += fmt_1pe(19, 8, fo[i])
            line += fmt_1pe(19, 8, soft[i])
            line += fmt_1pe(19, 8, so[i])
            line += fmt_1pe(19, 8, cv[i])
            line += fmt_1pe(19, 8, sic[i])
            fout.write(line + "\n")
    else:
        fout.write("0    Temp (deg k)      Fo-Ho/t (c/m/d)       Ho (kc/m)         So (c/m/d)             ic\n")
        for i in range(len(temp)):
            line = ""
            line += fmt_1pe(19, 8, temp[i])
            line += fmt_1pe(19, 8, fo[i])
            line += fmt_1pe(19, 8, soft[i])
            line += fmt_1pe(19, 8, so[i])
            line += fmt_1pe(19, 8, sic[i])
            fout.write(line + "\n")

    fscoef.write("   " + label72 + "\n")
    fscoef.write("".join(fmt_e18_11(xa[i]) for i in range(4)) + "\n")
    fscoef.write(fmt_e18_11(xa[4]) + "\n")

    fout.write("1" + (" " * 40) + "Entropy Fit\n")
    fout.write("0\n")
    fout.write(" " + (" " * 21) + "Variance\n")
    variance = sigma * sigma
    fout.write((" " * 18) + fmt_1pe(18, 11, variance) + "\n")
    fout.write("0\n")
    fout.write(" " + (" " * 18) + "Temp (deg k)" + (" " * 15) + "So" + (" " * 13) + "So from fit\n")
    for i in range(len(temp)):
        line = (" " * 12)
        line += fmt_1pe(21, 8, temp[i])
        line += fmt_1pe(21, 8, so[i])
        line += fmt_1pe(21, 8, stt[i])
        fout.write(line + "\n")


def run(
    working_dir: str | Path,
    *,
    on_log: Callable[[str], None] | None = None,
    cancel_event: threading.Event | None = None,
) -> int:
    # Data files (tdfdata, tdf.out, scoef, plots/) live inside working_dir.
    wd = Path(working_dir)
    plots_dir = wd / "plots"
    plots_dir.mkdir(exist_ok=True)

    with open(wd / "tdfdata", "r") as fin, open(wd / "tdf.out", "w") as fout, open(wd / "scoef", "w") as fscoef:
        problem_idx = 0

        while True:
            if cancel_event is not None and cancel_event.is_set():
                raise CancelledError("tdf run cancelled")
            while True:
                label_line = fin.readline()
                if not label_line:
                    break
                if label_line.strip():
                    break
            if not label_line:
                break

            label_text = label_line.rstrip("\r\n")
            label72 = label_text[:72].ljust(72)
            glabel = label72.rstrip()

            line = fin.readline()
            if not line:
                break
            itp, indg = read_i5(line, 2)

            if itp > 10:
                break

            problem_idx += 1
            basename = f"{problem_idx:03d}_{sanitize_label(glabel)}"

            temp = []
            fo = []
            ho = []
            so = []
            soft = []
            cv = None

            if itp == 1:
                emw = read_e18(fin.readline(), 1)[0]
                tmpi, dltmp, tmpf = read_e18(fin.readline(), 3)
                line = fin.readline()
                goe = read_e18(line, 1)[0]
                n2 = read_i5(line[18:], 1)[0]

                tmel = []
                stwel = []
                for _ in range(n2):
                    v = read_e18(fin.readline(), 2)
                    tmel.append(v[0])
                    stwel.append(v[1])

                fout.write("1   " + label72 + "\n")
                fout.write("0\n")
                fout.write("         Molecular Wt               go e               Monoatomic\n")
                fout.write(fmt_1pe(23, 11, emw) + fmt_1pe(23, 11, goe) + "\n")
                fout.write("0\n")
                fout.write("         Term Value 1/cm           Stat Wt\n")
                for i in range(n2):
                    fout.write(fmt_1pe(23, 11, tmel[i]) + fmt_1pe(23, 11, stwel[i]) + "\n")

                nt = int((tmpf - tmpi) / dltmp) + 1
                for i in range(nt):
                    tval = tmpi + dltmp * i
                    qe = 0.0
                    het = 0.0
                    for n in range(n2):
                        y = 1.4388 * tmel[n] / tval
                        qi = math.exp(-y) * stwel[n]
                        qe += qi
                        het += qi * y

                    qe += goe
                    fet = math.log(qe) * (-1.98719)
                    het = het * 1.98719 / qe
                    ftt = 7.28295 - 4.9679 * math.log(tval) - 2.98078 * math.log(emw)
                    foval = ftt + fet
                    hoval = 4.9679 + het

                    temp.append(tval)
                    fo.append(foval)
                    ho.append(hoval)
                    so.append(hoval - foval)
                    soft.append(hoval * tval / 1000.0)

            elif itp == 2:
                emw, sigm = read_e18(fin.readline(), 2)
                tmpi, dltmp, tmpf = read_e18(fin.readline(), 3)
                we, wexe, be, ae = read_e18(fin.readline(), 4)
                line = fin.readline()
                goe = read_e18(line, 1)[0]
                n2 = read_i5(line[18:], 1)[0]

                tmel = []
                stwel = []
                for _ in range(n2):
                    v = read_e18(fin.readline(), 2)
                    tmel.append(v[0])
                    stwel.append(v[1])

                fout.write("1   " + label72 + "\n")
                fout.write("0\n")
                fout.write("         Molecular Wt             Symmetry No.              Diatomic\n")
                fout.write(fmt_1pe(23, 11, emw) + fmt_1pe(23, 11, sigm) + "\n")
                fout.write("0\n")
                fout.write("              w e                    we xe                    b e                    a e\n")
                fout.write("".join(fmt_1pe(23, 11, x) for x in (we, wexe, be, ae)) + "\n")
                fout.write("0\n")
                fout.write("            go e\n")
                fout.write(fmt_1pe(23, 11, goe) + "\n")
                fout.write("0\n")
                fout.write("         Term Value 1/cm           Stat Wt\n")
                for i in range(n2):
                    fout.write(fmt_1pe(23, 11, tmel[i]) + fmt_1pe(23, 11, stwel[i]) + "\n")

                wo = we - 2.0 * wexe
                dow = 4.0 * be * be * be / (we * we)
                xval = wexe / we
                bo = be - ae * 0.5
                sval = (1.39017 * dow) / (bo * bo)
                rval = ae / be
                rval = rval * (1.0 + rval)
                fro = (2.98078 * math.log(emw)) - (1.98719 * math.log(1.4388 * bo))
                fro = fro - (1.98719 * math.log(sigm)) - 7.28295

                nt = int((tmpf - tmpi) / dltmp) + 1
                for i in range(nt):
                    tval = tmpi + dltmp * i
                    qe = 0.0
                    het = 0.0
                    uo = 1.4388 * wo / tval
                    exu = math.exp(uo)
                    exm = exu - 1.0
                    fv = -1.98719 * math.log(1.0 - (1.0 / exu))
                    hv = (1.98719 * uo) / exm

                    for n in range(n2):
                        y = 1.4388 * tmel[n] / tval
                        qi = math.exp(-y) * stwel[n]
                        qe += qi
                        het += qi * y

                    qe += goe
                    fet = math.log(qe) * 1.98719
                    het = het * (1.98719) / qe
                    th1 = 1.0 / exm
                    ysq = exm * exm
                    th2 = uo * exu / ysq
                    th4 = 2.0 * uo / ysq
                    th5 = ((2.0 * uo) * (2.0 * uo * exu - exu + 1.0)) / (ysq * exm)
                    fc = 1.98719 * (sval * tval + rval * th1 + xval * th4)
                    hc = 1.98719 * (sval * tval + rval * th2 + xval * th5)

                    foval = -6.955165 * math.log(tval) - fc - fro - fet - fv
                    hoval = hv + 6.955165 + hc + het

                    temp.append(tval)
                    fo.append(foval)
                    ho.append(hoval)
                    so.append(hoval - foval)
                    soft.append(hoval * tval / 1000.0)

            elif itp == 3:
                emw, sigm = read_e18(fin.readline(), 2)
                tmpi, dltmp, tmpf = read_e18(fin.readline(), 3)
                lflag, na, num = read_i5(fin.readline(), 3)

                eig = [0.0, 0.0, 0.0]
                if na == 0:
                    eig = read_e18(fin.readline(), 3)
                else:
                    em = []
                    ex = []
                    ey = []
                    ez = []
                    for _ in range(na):
                        v = read_e18(fin.readline(), 4)
                        em.append(v[0])
                        ex.append(v[1])
                        ey.append(v[2])
                        ez.append(v[3])

                    sm = 0.0
                    smy = 0.0
                    smx = 0.0
                    smz = 0.0
                    sma = 0.0
                    smb = 0.0
                    smc = 0.0
                    smd = 0.0
                    sme = 0.0
                    smf = 0.0

                    for i in range(na):
                        sm += em[i]
                        smy += em[i] * ey[i]
                        smx += em[i] * ex[i]
                        smz += em[i] * ez[i]
                        xs = ex[i] * ex[i]
                        ys = ey[i] * ey[i]
                        zs = ez[i] * ez[i]
                        sma += em[i] * (ys + zs)
                        smb += em[i] * (xs + zs)
                        smc += em[i] * (xs + ys)
                        smd += em[i] * ex[i] * ey[i]
                        sme += em[i] * ex[i] * ez[i]
                        smf += em[i] * ey[i] * ez[i]

                    sm = 1.0 / sm
                    smxs = smx * smx
                    smys = smy * smy
                    smzs = smz * smz

                    aig = [0.0] * 6
                    aig[0] = sma - sm * (smys + smzs)
                    aig[1] = -smd + sm * smx * smy
                    aig[2] = -sme + sm * smx * smz
                    aig[3] = smb - sm * (smxs + smzs)
                    aig[4] = -smf + sm * smy * smz
                    aig[5] = smc - sm * (smxs + smys)

                    eigp = -aig[0] - aig[3] - aig[5]
                    eigq = aig[0] * aig[3] + aig[0] * aig[5] + aig[3] * aig[5] - aig[1] * aig[1] - aig[2] * aig[2] - aig[4] * aig[4]
                    eigr = aig[0] * aig[4] * aig[4] + aig[3] * aig[2] * aig[2] + aig[5] * aig[1] * aig[1] - 2.0 * aig[1] * aig[2] * aig[4] - aig[0] * aig[3] * aig[5]
                    eiga = eigq - (eigp * eigp) / 3.0
                    eigb = 2.0 / 27.0 * (eigp ** 3) - eigp * eigq / 3.0 + eigr
                    eigt = math.acos(-0.5 * eigb / (math.sqrt(-eiga ** 3 / 27.0))) / 3.0
                    tsra = 2.0 * math.sqrt(-eiga / 3.0)
                    eig[0] = tsra * math.cos(eigt + 2.09439510239319) - eigp / 3.0
                    eig[1] = tsra * math.cos(eigt + 4.18879020478639) - eigp / 3.0
                    eig[2] = tsra * math.cos(eigt) - eigp / 3.0
                    eig[0] *= 0.166035
                    eig[1] *= 0.166035
                    eig[2] *= 0.166035

                goe = read_e18(fin.readline(), 1)[0]

                ef = []
                ed = []
                for _ in range(num):
                    v = read_e18(fin.readline(), 2)
                    ef.append(v[0])
                    ed.append(v[1])

                nt = int((tmpf - tmpi) / dltmp) + 1
                for i in range(nt):
                    tval = tmpi + dltmp * i
                    foval = -1.98719 * math.log(goe)
                    hoval = 0.0

                    for n in range(num):
                        uo = 1.4388 * ef[n] / tval
                        exu = math.exp(-uo)
                        exm = 1.0 - exu
                        foval += ed[n] * math.log(exm) * 1.98719
                        hoval += ed[n] * uo * exu * 1.98719 / exm

                    foval = foval - 4.9679 * math.log(tval) - 2.98078 * math.log(emw) + 7.28295
                    foval = foval + 1.98719 * math.log(sigm)
                    hoval = hoval + 4.9679

                    if lflag != 0:
                        hoval = hoval + 2.98078
                        sm = eig[0] * eig[1] * eig[2]
                        foval = foval - 2.98078 * math.log(tval) - 0.99359118 * math.log(sm) + 3.01407
                    else:
                        hoval = hoval + 1.98719
                        foval = foval - 1.98719 * (math.log(tval) + math.log(eig[0])) + 2.76764

                    temp.append(tval)
                    fo.append(foval)
                    ho.append(hoval)
                    so.append(hoval - foval)
                    soft.append(hoval * tval / 1000.0)

                fout.write("1   " + label72 + "\n")
                fout.write("0\n")
                fout.write("         Molecular Wt             Symmetry No.              Polyatomic\n")
                fout.write(fmt_1pe(23, 11, emw) + fmt_1pe(23, 11, sigm) + "\n")
                fout.write("0\n")
                fout.write("".join(fmt_1pe(23, 11, x) for x in eig) + "\n")
                fout.write("0\n")
                fout.write("            go e\n")
                fout.write(fmt_1pe(23, 11, goe) + "\n")
                fout.write("0\n")
                fout.write("          Vib Freq 1/cm           Degeneracy\n")
                for n in range(num):
                    fout.write(fmt_1pe(23, 11, ef[n]) + fmt_1pe(23, 11, ed[n]) + "\n")

            elif itp == 4:
                dths = read_e18(fin.readline(), 1)[0]
                sa, emw = read_e18(fin.readline(), 2)
                tmpi, dltmp, tmpf = read_e18(fin.readline(), 3)

                nt = int((tmpf - tmpi) / dltmp) + 1
                cv = []
                for i in range(nt):
                    tval = tmpi + dltmp * i
                    x = dths / tval
                    exm = math.exp(x)
                    xh = x / 1000.0
                    it = -2
                    sm = 0.0
                    for n in range(1, 1000):
                        l = 2 - it
                        xc = xh * n
                        y = (xc ** emw) / (math.exp(xc) - 1.0)
                        sm += y * l
                        it = -it - 2

                    sm += (x ** emw) / (exm - 1.0)
                    sm = sm * xh / 3.0
                    de = sm * emw / (x ** emw)
                    y = 1.0 - 1.0 / exm
                    z = 1.98719 * sa
                    foval = z * (emw * math.log(y) + (2.0 - emw) * de)
                    hoval = z * 3.0 * de
                    cvval = 3.0 * z * ((emw + 1.0) * de - (emw * x) / (exm - 1.0))

                    temp.append(tval)
                    fo.append(foval)
                    ho.append(hoval)
                    so.append(hoval - foval)
                    soft.append(hoval * tval / 1000.0)
                    cv.append(cvval)

                fout.write("1   " + label72 + "\n")
                fout.write("0\n")
                fout.write("0          Debye Temp             Dimension         Number of Atoms/cell\n")
                fout.write("".join(fmt_1pe(23, 11, x) for x in (dths, emw, sa)) + "\n")
                fout.write("0\n")

            elif itp == 5:
                dtt, dtl = read_e18(fin.readline(), 2)
                sa = read_e18(fin.readline(), 1)[0]
                tmpi, dltmp, tmpf = read_e18(fin.readline(), 3)

                nt = int((tmpf - tmpi) / dltmp) + 1
                cv = []
                for i in range(nt):
                    tval = tmpi + dltmp * i
                    xt = dtt / tval
                    xl = dtl / tval
                    ext = math.exp(xt)
                    exl = math.exp(xl)
                    xh = xt / 1000.0
                    xhl = xl / 1000.0
                    it = -2
                    smt = 0.0
                    sml = 0.0

                    for n in range(1, 1000):
                        l = 2 - it
                        xc = xh * n
                        y = (xc * xc) / (math.exp(xc) - 1.0)
                        smt += y * l
                        xc = xhl * n
                        y = (xc * xc) / (math.exp(xc) - 1.0)
                        sml += y * l
                        it = -it - 2

                    smt += (xt * xt) / (ext - 1.0)
                    smt = smt * xh / 3.0
                    dt = smt * 2.0 / (xt * xt)
                    sml += (xl * xl) / (exl - 1.0)
                    sml = sml * xhl / 3.0
                    dl = sml * 2.0 / (xl * xl)
                    z = 1.98719 * sa
                    y = 1.0 - 1.0 / ext
                    yl = 1.0 - 1.0 / exl
                    foval = z * (-0.5 * dt + math.log(y) - dl + 2.0 * math.log(yl))
                    hoval = 2.0 * z * (0.5 * dt + dl)
                    y = 2.0 * xt / (ext - 1.0)
                    yl = 2.0 * xl / (exl - 1.0)
                    cvval = 2.0 * z * (1.5 * dt - 0.5 * y + 3.0 * dl - yl)

                    temp.append(tval)
                    fo.append(foval)
                    ho.append(hoval)
                    so.append(hoval - foval)
                    soft.append(hoval * tval / 1000.0)
                    cv.append(cvval)

                fout.write("1   " + label72 + "\n")
                fout.write("0\n")
                fout.write("0     Debye Temp (tran)      Debye Temp (long)          Dimension         Number of Atoms/cell\n")
                fout.write("".join(fmt_1pe(23, 11, x) for x in (dtt, dtl, 2.0, sa)) + "\n")
                fout.write("0\n")

            else:
                continue

            sigma_s, xa, stt, _ = pfts(len(temp), 4, 0, temp, so)
            sic = []
            for i in range(len(temp)):
                ts = temp[i] * temp[i]
                tss = ts * ts
                z = (xa[1] * ts / 2.0) + (2.0 * xa[2] * temp[i] * ts / 3.0) + xa[3] * 0.75 * tss
                z1 = soft[i] * 1000.0
                sic.append(z1 - (z + xa[4] * 0.8 * tss * temp[i]))

            _, fa, _, _ = pfts(len(temp), 4, 0, temp, fo)
            _, ha, _, _ = pfts(len(temp), 4, 0, temp, soft)

            da = None
            if itp >= 4:
                _, da, _, _ = pfts(len(temp), 4, 0, temp, cv)

            write_common_output(fout, fscoef, label72, itp, temp, fo, soft, so, sic, xa, fa, ha, sigma_s, stt, cv=cv, da=da)

            save_plot(plots_dir, f"{basename}_enthalpy", temp, soft, "TEMPERATURE", "ENTHALPY", glabel, indg)
            save_plot(plots_dir, f"{basename}_free_energy", temp, fo, "TEMPERATURE", "FREE ENERGY", glabel, indg)
            if itp == 4:
                save_plot(plots_dir, f"{basename}_entropy", temp, so, "TEMPERATURE", "ENTROPY", glabel, indg)
                save_plot(plots_dir, f"{basename}_heat_capacity", temp, cv, "TEMPERATURE", "HEAT CAPACITY", glabel, indg)

    msg = (
        "TDF complete. Matplotlib unavailable; png plots were not generated."
        if plt is None
        else "TDF complete. Output written to tdf.out, scoef, and plots/*.png"
    )
    if on_log is not None:
        on_log(msg)
    else:
        print(msg)
    return 0


def main() -> int:
    # CLI: read inputs and write outputs relative to current working directory.
    return run(Path.cwd())


if __name__ == "__main__":
    raise SystemExit(main())
