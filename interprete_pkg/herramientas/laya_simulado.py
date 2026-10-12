#!/usr/bin/env python3
"""Servidor LAYA SIMULADO (solo para ensayar en casa; NO es LAYA real).

Imita POST /v1/systemone y GET /health, con la cabecera X-Inference-Time-Ms.
Usa el vocabulario y el clasificador de interprete_ordenes.py para fabricar sus respuestas.
Atiende de a UNA petición (como el real), así que bajo carga se forma cola.

  python3 herramientas/laya_simulado.py --port 8000
  python3 herramientas/laya_simulado.py --retraso-extra-ms 3000   # fuerza timeouts
  python3 herramientas/laya_simulado.py --acierto 0.8
"""
import argparse, importlib.util, json, os, random, sys, threading, time, types
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

AQUI = os.path.dirname(os.path.abspath(__file__))
DEF_SCRIPT = os.path.join(AQUI, "..", "interprete_pkg", "scripts", "interprete_ordenes.py")


def cargar_script(ruta):
    """Importa el script del nodo sin necesitar ROS (módulos falsos mínimos)."""
    for n in ("rclpy", "rclpy.node", "rclpy.executors", "rclpy.callback_groups", "interprete_pkg", "interprete_pkg.srv"):
        sys.modules.setdefault(n, types.ModuleType(n))
    sys.modules["rclpy.node"].Node = object
    sys.modules["rclpy.executors"].MultiThreadedExecutor = object
    sys.modules["rclpy.callback_groups"].ReentrantCallbackGroup = object
    sys.modules["interprete_pkg.srv"].InterpretarOrden = object
    sp = importlib.util.spec_from_file_location("nodo_sim", ruta)
    m = importlib.util.module_from_spec(sp)
    sp.loader.exec_module(m)
    return m


ARGS = None
N = None
LOCK = threading.Lock()
RNG = random.Random(7)


def probs(ops, elegido, conf):
    resto = (1 - conf) / max(len(ops) - 1, 1)
    return {o: round(conf if o == elegido else resto, 4) for o in ops}


def responder(frase):
    d = N.clasificar_palabras(frase)
    out = {}
    for campo, vocab in (("accion", N.ACCIONES), ("objeto", N.OBJETOS), ("color", N.COLORES)):
        ops = list(vocab)
        val = d[campo] if RNG.random() <= ARGS.acierto else RNG.choice(ops)
        out[campo] = {"type": "choice", "choice": val, "probabilities": probs(ops, val, 0.8),
                      "confidence": 0.6, "answer_confidence": 0.8}
    prio = d["prioridad"] - 1 + RNG.uniform(-0.3, 0.3)
    if RNG.random() > ARGS.acierto:
        prio = RNG.uniform(0, len(N.NIVELES_PRIORIDAD) - 1)
    out["prioridad"] = {"type": "score", "score": round(max(0, min(len(N.NIVELES_PRIORIDAD) - 1, prio)), 4),
                        "confidence": 0.5, "answer_confidence": 0.6}
    p_si = 0.9 if d["permitido"] else 0.08
    if RNG.random() > ARGS.acierto:
        p_si = 1 - p_si
    out["permitido"] = {"type": "noul", "noul": p_si, "confidence": max(p_si, 1 - p_si)}
    return {"model": "laya-simulado", "answers": out}


class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def _send(self, code, obj, extra=None):
        b = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(b)))
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        self._send(200, {"status": "ok"}) if self.path.startswith("/health") else self._send(404, {"detail": "no existe"})

    def do_POST(self):
        if not self.path.startswith("/v1/systemone"):
            return self._send(404, {"detail": "no existe"})
        n = int(self.headers.get("content-length", 0))
        try:
            body = json.loads(self.rfile.read(n))
            frase = body["state"]
            assert "questions" in body
        except Exception:
            return self._send(400, {"detail": "cuerpo invalido"})
        if RNG.random() < ARGS.error_http:
            return self._send(503, {"detail": "server busy"})
        with LOCK:
            calc = max(1.0, RNG.gauss(ARGS.calculo_ms, ARGS.jitter_ms))
            time.sleep(calc / 1000.0)
            resp = responder(frase)
        if ARGS.retraso_extra_ms:
            time.sleep(ARGS.retraso_extra_ms / 1000.0)
        self._send(200, resp, {"X-Inference-Time-Ms": f"{calc:.2f}"})


def main():
    global ARGS, N
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="0.0.0.0"); ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--calculo-ms", type=float, default=40.0); ap.add_argument("--jitter-ms", type=float, default=8.0)
    ap.add_argument("--retraso-extra-ms", type=float, default=0.0); ap.add_argument("--acierto", type=float, default=0.85)
    ap.add_argument("--error-http", type=float, default=0.0); ap.add_argument("--script", default=DEF_SCRIPT)
    ARGS = ap.parse_args()
    N = cargar_script(ARGS.script)
    print(f"[LAYA simulado] http://{ARGS.host}:{ARGS.port} calculo~{ARGS.calculo_ms} ms (SIMULADO)", flush=True)
    ThreadingHTTPServer((ARGS.host, ARGS.port), H).serve_forever()


if __name__ == "__main__":
    main()
