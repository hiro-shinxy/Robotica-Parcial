#!/usr/bin/env python3
"""Medidor de la Pregunta 1.

Para CADA frase del archivo del docente llama al servicio /interpretar_orden dos veces
(modo 'laya' y modo 'palabras_clave'), ESPERANDO cada respuesta antes de seguir.
Guarda un CSV y imprime/guarda las tablas de latencia (mediana y P95) y de exactitud.

Uso:
  ros2 run interprete_pkg medidor_evaluacion.py --frases ~/frases.csv --escenario calma \
      --salida ~/resultados_calma.csv --laya-url http://IP:PUERTO
"""
import argparse
import csv
import json
import os
import statistics
import sys
import time
import unicodedata

import rclpy
from rclpy.utilities import remove_ros_args

from interprete_pkg.srv import InterpretarOrden

CAMPOS = ["accion", "objeto", "color", "prioridad", "permitido"]


def norm(x):
    t = unicodedata.normalize("NFD", str(x).strip().lower())
    return "".join(c for c in t if unicodedata.category(c) != "Mn")


def es_true(x):
    return norm(x) in ("true", "1", "si", "yes", "verdadero", "v", "s")


def igual(campo, esperado, obtenido):
    if campo == "permitido":
        return es_true(esperado) == es_true(obtenido)
    if campo == "prioridad":
        try:
            return int(float(esperado)) == int(float(obtenido))
        except (ValueError, TypeError):
            return False
    return norm(esperado) == norm(obtenido)


def percentil(v, p):
    """Percentil con interpolación lineal (igual que numpy.percentile)."""
    s = sorted(v)
    if not s:
        return float("nan")
    k = (len(s) - 1) * p / 100.0
    i = int(k)
    j = min(i + 1, len(s) - 1)
    return s[i] + (s[j] - s[i]) * (k - i)


def resumen(v):
    v = [x for x in v if x >= 0]
    if not v:
        return None
    return dict(n=len(v), mediana=statistics.median(v), p95=percentil(v, 95),
                media=statistics.fmean(v), minimo=min(v), maximo=max(v))


def leer_frases(ruta):
    with open(ruta, encoding="utf-8-sig", newline="") as f:
        muestra = f.read(4096)
        f.seek(0)
        try:
            dialecto = csv.Sniffer().sniff(muestra, delimiters=",;\t")
        except csv.Error:
            dialecto = csv.excel
        filas = list(csv.DictReader(f, dialect=dialecto))
    if not filas:
        sys.exit("El archivo de frases esta vacio")
    col = "frase" if "frase" in filas[0] else list(filas[0].keys())[0]
    for i, fila in enumerate(filas, 1):
        fila["_frase"] = (fila[col] or "").strip()
        if not fila.get("id"):
            fila["id"] = str(i)
    return [f for f in filas if f["_frase"]]


def col_esperada(fila, campo):
    for k in (f"{campo}_esperada", f"{campo}_esperado"):
        if k in fila:
            return k
    return None


def num(fila, k):
    try:
        return float(fila[k])
    except (KeyError, ValueError, TypeError):
        return -1.0


def tablas(filas, escenario):
    ok = [r for r in filas if es_true(r.get("laya_exito", ""))]
    md = [f"## Latencia - {escenario}", "",
          f"Peticiones: {len(filas)} - LAYA respondio: {len(ok)} - "
          f"sin respuesta o degradadas: {len(filas) - len(ok)}", "",
          "| Componente (ms) | n | Mediana | P95 | Media | Min | Max |", "|---|---|---|---|---|---|---|"]
    for nombre, clave, fuente in (
            ("Ida y vuelta HTTP a LAYA", "laya_http_ms", ok),
            ("Calculo informado por el servidor", "laya_calculo_ms", ok),
            ("Red + cola del servidor (HTTP - calculo)", "laya_red_ms", ok),
            ("Red pura (GET /health)", "rtt_health_ms", filas),
            ("Total visto por el cliente ROS (LAYA)", "cliente_laya_ms", filas),
            ("Palabras clave (total en el nodo)", "kw_total_ms", filas)):
        s = resumen([num(r, clave) for r in fuente])
        md.append(f"| {nombre} | " + (" | ".join([str(s["n"])] + [f"{s[k]:.1f}" for k in
                  ("mediana", "p95", "media", "minimo", "maximo")]) if s else "- | - | - | - | - | -") + " |")
    md.append("")
    if filas and any(col_esperada(filas[0], c) for c in CAMPOS):
        campos = [c for c in CAMPOS if col_esperada(filas[0], c)]
        md += ["## Exactitud (mismas frases)", "", "| Campo | LAYA | Palabras clave |", "|---|---|---|"]
        res = {}
        for pref in ("laya", "kw"):
            r_ = {}
            for c in campos:
                r_[c] = sum(1 for f in filas if es_true(f.get(f"{pref}_exito", "")) and
                            igual(c, f[col_esperada(f, c)], f.get(f"{pref}_{c}", ""))) / len(filas)
            r_["COMPLETA"] = sum(1 for f in filas if es_true(f.get(f"{pref}_exito", "")) and all(
                igual(c, f[col_esperada(f, c)], f.get(f"{pref}_{c}", "")) for c in campos)) / len(filas)
            res[pref] = r_
        for c in campos + ["COMPLETA"]:
            md.append(f"| {c if c != 'COMPLETA' else 'DECISION COMPLETA'} | "
                      f"{100 * res['laya'][c]:.1f} % | {100 * res['kw'][c]:.1f} % |")
        md.append("")
    else:
        md += ["_Sin columnas *_esperada/*_esperado: no se calcula la exactitud._", ""]
    return md


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--frases", required=True)
    ap.add_argument("--escenario", default="calma")
    ap.add_argument("--salida", default="resultados.csv")
    ap.add_argument("--rondas", type=int, default=1)
    ap.add_argument("--laya-url", default="", help="solo para medir /health (red pura)")
    ap.add_argument("--espera-max-s", type=float, default=15.0)
    ap.add_argument("--esperar-enter", action="store_true")
    ap.add_argument("--prediccion-mediana-ms", type=float)
    ap.add_argument("--prediccion-p95-ms", type=float)
    a = ap.parse_args(remove_ros_args(args=sys.argv)[1:])
    a.frases, a.salida = os.path.expanduser(a.frases), os.path.expanduser(a.salida)

    frases = leer_frases(a.frases)
    rclpy.init()
    nodo = rclpy.create_node("medidor_evaluacion")
    cli = nodo.create_client(InterpretarOrden, "/interpretar_orden")
    if not cli.wait_for_service(timeout_sec=10.0):
        sys.exit("No aparece /interpretar_orden: nodo apagado o ROS_DOMAIN_ID distinto.")

    def llamar(frase, modo):
        req = InterpretarOrden.Request()
        req.frase, req.modo = frase, modo
        t0 = time.perf_counter()
        fut = cli.call_async(req)
        rclpy.spin_until_future_complete(nodo, fut, timeout_sec=a.espera_max_s)  # ESPERA la respuesta
        ms = (time.perf_counter() - t0) * 1000.0
        return (fut.result() if fut.done() else None), ms

    def health():
        if not a.laya_url:
            return -1.0
        import requests
        t0 = time.perf_counter()
        try:
            requests.get(a.laya_url.rstrip("/") + "/health", timeout=3)
        except requests.RequestException:
            return -1.0
        return (time.perf_counter() - t0) * 1000.0

    esperadas = [k for k in frases[0] if k.endswith(("_esperada", "_esperado"))]
    cab = (["escenario", "ronda", "id", "frase"] + esperadas +
           [f"laya_{c}" for c in CAMPOS] + ["laya_exito", "laya_degradado", "laya_motivo", "laya_confianza",
                                            "laya_causa", "laya_http_ms", "laya_calculo_ms", "laya_red_ms",
                                            "laya_total_ms", "cliente_laya_ms", "rtt_health_ms"] +
           [f"kw_{c}" for c in CAMPOS] + ["kw_exito", "kw_causa", "kw_total_ms", "cliente_kw_ms"])
    if a.esperar_enter:
        input("Presione ENTER cuando el docente de la senal de INICIO... ")
    filas_out = []
    with open(a.salida, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cab, extrasaction="ignore")
        w.writeheader()
        for ronda in range(1, a.rondas + 1):
            for fila in frases:
                o = {"escenario": a.escenario, "ronda": ronda, "id": fila["id"], "frase": fila["_frase"]}
                for k in esperadas:
                    o[k] = fila[k]
                o["rtt_health_ms"] = round(health(), 2)
                rl, ml = llamar(fila["_frase"], "laya")
                rk, mk = llamar(fila["_frase"], "palabras_clave")
                o["cliente_laya_ms"], o["cliente_kw_ms"] = round(ml, 2), round(mk, 2)
                if rl is None:
                    o["laya_exito"], o["laya_motivo"] = False, "sin_respuesta_del_servicio"
                else:
                    for c in CAMPOS:
                        o[f"laya_{c}"] = getattr(rl, c)
                    o.update(laya_exito=rl.exito, laya_degradado=rl.degradado, laya_motivo=rl.motivo,
                             laya_confianza=round(rl.confianza, 3), laya_causa=rl.causa_rechazo,
                             laya_http_ms=round(rl.latencia_http_ms, 2),
                             laya_calculo_ms=round(rl.latencia_calculo_ms, 2),
                             laya_red_ms=round(rl.latencia_red_ms, 2),
                             laya_total_ms=round(rl.latencia_total_ms, 2))
                if rk is None:
                    o["kw_exito"] = False
                else:
                    for c in CAMPOS:
                        o[f"kw_{c}"] = getattr(rk, c)
                    o.update(kw_exito=rk.exito, kw_causa=rk.causa_rechazo,
                             kw_total_ms=round(rk.latencia_total_ms, 4))
                w.writerow(o)
                f.flush()
                filas_out.append({k: str(v) for k, v in o.items()})
                print(f"[{ronda}/{a.rondas}] #{fila['id']:>3} {fila['_frase'][:45]:<45} "
                      f"laya={'ok' if (rl and rl.exito) else (rl.motivo if rl else 'sin_resp')} {ml:7.1f} ms")
    md = tablas(filas_out, a.escenario)
    p = {k: v for k, v in (("mediana_ms", a.prediccion_mediana_ms), ("p95_ms", a.prediccion_p95_ms)) if v is not None}
    if p:
        s = resumen([num(r, "laya_http_ms") for r in filas_out if es_true(r.get("laya_exito", ""))])
        if s:
            md += ["## Predicho vs medido (HTTP LAYA)", "", "| Metrica | Predicho | Medido |", "|---|---|---|"]
            if "mediana_ms" in p:
                md.append(f"| Mediana | {p['mediana_ms']:.1f} | {s['mediana']:.1f} |")
            if "p95_ms" in p:
                md.append(f"| P95 | {p['p95_ms']:.1f} | {s['p95']:.1f} |")
            md.append("")
    ruta_md = os.path.splitext(a.salida)[0] + "_tablas.md"
    with open(ruta_md, "w", encoding="utf-8") as g:
        g.write("\n".join(md))
    with open(a.salida + ".meta.json", "w", encoding="utf-8") as g:
        json.dump({"escenario": a.escenario, "rondas": a.rondas, "n_frases": len(frases),
                   "prediccion": p, "fin_epoch": time.time()}, g, indent=2)
    print("\n" + "\n".join(md))
    print(f"CSV: {a.salida}\nTablas: {ruta_md}")
    nodo.destroy_node()
    rclpy.shutdown()


if __name__ == "__main__":
    main()
