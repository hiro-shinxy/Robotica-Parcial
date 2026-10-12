#!/usr/bin/env python3
"""Nodo interprete_ordenes: servicio /interpretar_orden.

frase en español -> decisión tipada (accion, objeto, color, prioridad 1-5, permitido).

 * LAYA recibe 5 preguntas TIPADAS (choice / score / noul) en UNA petición HTTP.
   Nunca se le pide texto, y NO se rellenan campos con el clasificador local en silencio:
   si LAYA falla o responde algo inesperado, TODA la decisión pasa al respaldo y se marca
   degradado=True con el motivo.
 * El tiempo límite (parámetro timeout_laya) es DURO: el callback no espera más que eso.
 * El campo `modo` de la petición permite medir cada método por separado.

Edita los diccionarios ACCIONES / OBJETOS / COLORES para que los nombres coincidan con los
del docente. De ellos salen tanto las opciones que ve LAYA como las palabras clave.
"""
import json
import math
import time
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturoTimeout

import requests
import rclpy
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node

from interprete_pkg.srv import InterpretarOrden

NO_DISP = -1.0

# --------------------------------------------------------------------------- #
# VOCABULARIO (nombre: (descripción que lee LAYA, palabras clave del respaldo))
#   "raiz"  = cualquier palabra que EMPIECE con raiz      "ya$" = palabra exacta
# --------------------------------------------------------------------------- #
ACCIONES = {
    "detener": ("detenerse, parar el movimiento o cancelar la tarea",
                ["deten", "alto$", "stop$", "frena", "cancela"]),
    "inicio": ("volver a la posicion inicial o de reposo",
               ["inicio", "home$", "reposo", "regresa", "vuelve"]),
    "agarrar": ("tomar, agarrar, recoger o llevar un objeto de un lugar a otro",
                ["coge", "agarr", "toma", "recog", "levant", "sujet", "mueve", "lleva",
                 "traslad", "pon", "coloc", "deposit"]),
    "soltar": ("soltar el objeto que sostiene la pinza", ["suelt", "dej", "libera"]),
    "desconocida": ("no es una orden para el brazo o no se entiende", []),
}
OBJETOS = {
    "cubo": ("un cubo o bloque", ["cubo", "bloque", "dado"]),
    "cilindro": ("un cilindro o lata", ["cilindr", "lata", "tubo"]),
    "esfera": ("una esfera, bola o pelota", ["esfera", "bola", "pelota"]),
    "caja": ("una caja o prisma", ["caja", "prisma"]),
    "desconocido": ("no se menciona ningun objeto", []),
}
COLORES = {
    "rojo": ("color rojo", ["roj", "colorad"]),
    "azul": ("color azul", ["azul", "celeste"]),
    "verde": ("color verde", ["verd"]),
    "amarillo": ("color amarillo", ["amarill"]),
    "desconocido": ("no se menciona ningun color", []),
}
DEFECTO = {"accion": "desconocida", "objeto": "desconocido", "color": "desconocido"}

# Prioridad 1..5 (de menor a mayor urgencia). Palabras para el respaldo, de mayor a menor.
NIVELES_PRIORIDAD = [
    "sin urgencia, puede esperar",
    "poca urgencia, puede hacerse pronto",
    "prioritaria, hacerla cuanto antes",
    "urgente, hacerla rapido",
    "emergencia, hacerla de inmediato",
]
PALABRAS_PRIORIDAD = [
    (5, ["emergencia", "inmediat", "ya$", "ahora mismo"]),
    (4, ["urgente", "rapido"]),
    (3, ["prioritari", "cuanto antes"]),
    (2, ["pronto$"]),
]
PROHIBIDAS = ["lanz", "tira$", "tires$", "arroj", "avient", "golpe", "rompe", "rompa", "destru",
              "aplast", "choca", "apaga", "desactiva", "persona", "mi mano", "con fuerza"]


def normalizar(texto):
    t = unicodedata.normalize("NFD", str(texto).lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    t = "".join(c if c.isalnum() else " " for c in t)
    return " ".join(t.split())


def coincide(texto, tokens, patron):
    if patron.endswith("$"):
        return normalizar(patron[:-1]) in tokens
    p = normalizar(patron)
    if not p:
        return False
    if " " in p:
        return f" {p}" in f" {texto}"
    return any(t.startswith(p) for t in tokens)


def _mejor(vocab, campo, texto, tokens):
    mejor, n_mejor = DEFECTO[campo], 0
    for nombre, (_desc, palabras) in vocab.items():  # el orden desempata
        n = sum(1 for p in palabras if coincide(texto, tokens, p))
        if n > n_mejor:
            mejor, n_mejor = nombre, n
    return mejor, n_mejor


def clasificar_palabras(frase):
    """Respaldo sin red. Devuelve dict con la decisión."""
    texto = normalizar(frase)
    tokens = texto.split()
    accion, na = _mejor(ACCIONES, "accion", texto, tokens)
    objeto, no = _mejor(OBJETOS, "objeto", texto, tokens)
    color, nc = _mejor(COLORES, "color", texto, tokens)
    prioridad = 1
    for nivel, palabras in PALABRAS_PRIORIDAD:
        if any(coincide(texto, tokens, p) for p in palabras):
            prioridad = nivel
            break
    prohibidas = [p for p in PROHIBIDAS if coincide(texto, tokens, p)]
    permitido, causa = True, ""
    if prohibidas:
        permitido, causa = False, f"contiene termino prohibido: '{prohibidas[0].rstrip('$')}'"
    elif accion == "desconocida":
        permitido, causa = False, "orden no entendida"
    conf = round(sum(1 for n in (na, no, nc) if n > 0) / 3.0, 3)
    return dict(accion=accion, objeto=objeto, color=color, prioridad=prioridad,
                permitido=permitido, causa_rechazo=causa, confianza=conf)


# --------------------------------------------------------------------------- #
# Cliente LAYA
# --------------------------------------------------------------------------- #
class ErrorLaya(Exception):
    def __init__(self, motivo, detalle=""):
        super().__init__(f"{motivo}: {detalle}" if detalle else motivo)
        self.motivo, self.detalle = motivo, detalle


def preguntas_tipadas():
    def choice(vocab, texto):
        return {"type": "choice", "instructions": texto,
                "criteria": {k: v[0] for k, v in vocab.items()}}
    return {
        "accion": choice(ACCIONES, "Que accion le pide el operador al brazo robotico?"),
        "objeto": choice(OBJETOS, "Sobre que tipo de objeto actua la orden?"),
        "color": choice(COLORES, "De que color es el objeto mencionado?"),
        "prioridad": {"type": "score", "instructions": "Que tan urgente es esta orden?",
                      "criteria": NIVELES_PRIORIDAD},
        "permitido": {"type": "noul", "instructions":
                      "Es una orden segura y permitida para el brazo, sin lanzar, golpear, "
                      "romper ni danar personas u objetos?"},
    }


def calculo_ms(r):
    v = r.headers.get("X-Inference-Time-Ms")
    if v:
        try:
            return float(v)
        except ValueError:
            pass
    for parte in r.headers.get("Server-Timing", "").split(","):
        parte = parte.strip()
        if parte.startswith("inference") and "dur=" in parte:
            try:
                return float(parte.split("dur=")[1].split(";")[0])
            except ValueError:
                pass
    return NO_DISP


def a_decision(datos, umbral):
    resp = datos.get("answers") if isinstance(datos, dict) else None
    if not isinstance(resp, dict):
        raise ErrorLaya("respuesta_invalida", "sin 'answers': " + json.dumps(datos)[:200])
    try:
        d, confs = {}, []
        for campo, vocab in (("accion", ACCIONES), ("objeto", OBJETOS), ("color", COLORES)):
            a = resp[campo]
            valor = a["choice"]
            if valor not in vocab:
                raise ErrorLaya("respuesta_invalida", f"{campo}='{valor}' fuera del vocabulario")
            d[campo] = valor
            confs.append(float(a.get("answer_confidence", a.get("confidence", 0.0))))
        score = float(resp["prioridad"]["score"])
        p_si = float(resp["permitido"]["noul"])
    except (KeyError, TypeError, ValueError, AttributeError) as e:
        raise ErrorLaya("respuesta_invalida", f"falta o mal tipado {e}: " + json.dumps(datos)[:200])
    n = len(NIVELES_PRIORIDAD)
    d["prioridad"] = max(1, min(n, int(math.floor(score + 0.5)) + 1))
    d["permitido"], d["causa_rechazo"] = p_si >= umbral, ""
    if not d["permitido"]:
        d["causa_rechazo"] = f"LAYA estima P(permitida)={p_si:.2f} < umbral {umbral:.2f}"
    elif d["accion"] == "desconocida":
        d["permitido"], d["causa_rechazo"] = False, "orden no entendida"
    confs.append(max(p_si, 1.0 - p_si))
    d["confianza"] = round(min(confs), 3)
    return d


class Motor:
    """Lógica sin ROS. `cfg()` devuelve un dict con los parámetros vigentes."""

    def __init__(self, cfg):
        self.cfg = cfg
        self.preguntas = preguntas_tipadas()
        self.ejecutor = ThreadPoolExecutor(max_workers=8, thread_name_prefix="laya")

    def _post(self, frase, c):
        body = {"state": frase, "questions": self.preguntas}
        if c["lang"]:
            body["lang"] = c["lang"]
        body.update(c["extra"])
        headers = {"content-type": "application/json"}
        if c["api_key"]:
            headers["Authorization"] = f"Bearer {c['api_key']}"
        t0 = time.perf_counter()
        try:
            r = requests.post(c["url"], json=body, headers=headers,
                              timeout=(c["timeout"] * 1.5, c["timeout"] * 1.5))
        except requests.Timeout:
            raise ErrorLaya("timeout")
        except requests.ConnectionError as e:
            raise ErrorLaya("sin_conexion", str(e)[:100])
        except requests.RequestException as e:
            raise ErrorLaya("error_http", str(e)[:100])
        t_http = (time.perf_counter() - t0) * 1000.0
        if r.status_code == 503:
            raise ErrorLaya("servidor_ocupado")
        if r.status_code == 401:
            raise ErrorLaya("no_autorizado")
        if r.status_code >= 400:
            raise ErrorLaya("error_http", f"{r.status_code} {r.text[:150]}")
        try:
            datos = r.json()
        except ValueError:
            raise ErrorLaya("respuesta_invalida", "no es JSON: " + r.text[:100])
        return datos, t_http, calculo_ms(r)

    def interpretar(self, frase, modo=""):
        t0 = time.perf_counter()
        c = self.cfg()
        modo = (modo or "auto").strip().lower()
        out = dict(accion="", objeto="", color="", prioridad=0, permitido=False, degradado=False,
                   causa_rechazo="", fuente="", motivo="", exito=False, confianza=0.0,
                   latencia_total_ms=NO_DISP, latencia_http_ms=NO_DISP,
                   latencia_calculo_ms=NO_DISP, latencia_red_ms=NO_DISP)

        def fin():
            out["latencia_total_ms"] = (time.perf_counter() - t0) * 1000.0
            return out

        if modo not in ("auto", "laya", "palabras_clave"):
            out["motivo"], out["causa_rechazo"] = f"modo_invalido:{modo}", "modo desconocido"
            return fin()
        if not (frase or "").strip():
            out["motivo"], out["causa_rechazo"] = "frase_vacia", "la frase esta vacia"
            return fin()
        if modo == "palabras_clave":
            out.update(clasificar_palabras(frase))
            out.update(exito=True, fuente="palabras_clave")
            return fin()

        fut = self.ejecutor.submit(self._post, frase, c)
        try:
            try:
                datos, t_http, calc = fut.result(timeout=c["timeout"])
            except FuturoTimeout:
                fut.cancel()
                raise ErrorLaya("timeout")
            out.update(a_decision(datos, c["umbral"]))
            out.update(exito=True, fuente="laya", latencia_http_ms=t_http, latencia_calculo_ms=calc)
            if calc >= 0:
                out["latencia_red_ms"] = max(0.0, t_http - calc)
            return fin()
        except ErrorLaya as e:
            out["motivo"] = e.motivo
            out["detalle"] = e.detalle
            if modo == "laya":
                out.update(fuente="laya", causa_rechazo=f"LAYA no respondio ({e})")
                return fin()
        # RESPALDO: el sistema nunca se queda esperando
        out.update(clasificar_palabras(frase))
        out.update(exito=True, fuente="palabras_clave", degradado=True)
        return fin()


# --------------------------------------------------------------------------- #
# Nodo ROS 2
# --------------------------------------------------------------------------- #
class InterpreteOrdenes(Node):
    def __init__(self):
        super().__init__("interprete_ordenes")
        self.declare_parameter("timeout_laya", 2.0)               # TIEMPO LIMITE (s)
        self.declare_parameter("laya_url", "http://172.51.1.14:8000")  # <- la da el docente
        self.declare_parameter("laya_endpoint", "/v1/systemone")
        self.declare_parameter("lang", "es")
        self.declare_parameter("laya_extra_json", '{"preset": "multilingual"}')
        self.declare_parameter("umbral_permitido", 0.5)
        self.declare_parameter("laya_api_key_env", "LAYA_API_KEY")
        self.motor = Motor(self._cfg)
        self.cb = ReentrantCallbackGroup()
        self.srv = self.create_service(InterpretarOrden, "/interpretar_orden",
                                       self.interpretar_callback, callback_group=self.cb)
        c = self._cfg()
        self.get_logger().info(f"Servicio /interpretar_orden listo (Prioridad 1 a 5). "
                               f"LAYA={c['url']} timeout={c['timeout']}s")

    def _cfg(self):
        import os
        g = lambda n: self.get_parameter(n).value  # noqa: E731
        try:
            extra = json.loads(g("laya_extra_json") or "{}")
        except ValueError:
            extra = {}
        return dict(timeout=float(g("timeout_laya")),
                    url=g("laya_url").rstrip("/") + g("laya_endpoint"),
                    lang=g("lang"), extra=extra, umbral=float(g("umbral_permitido")),
                    api_key=os.environ.get(g("laya_api_key_env"), "") or None)

    def interpretar_callback(self, request, response):
        r = self.motor.interpretar(request.frase, request.modo)
        for campo in ("accion", "objeto", "color", "causa_rechazo", "fuente", "motivo"):
            setattr(response, campo, str(r[campo]))
        response.prioridad = int(r["prioridad"])
        response.permitido = bool(r["permitido"])
        response.degradado = bool(r["degradado"])
        response.exito = bool(r["exito"])
        response.confianza = float(r["confianza"])
        for campo in ("latencia_total_ms", "latencia_http_ms", "latencia_calculo_ms", "latencia_red_ms"):
            setattr(response, campo, float(r[campo]))
        msg = (f'"{request.frase}" -> {r["accion"]}/{r["objeto"]}/{r["color"]} p={r["prioridad"]} '
               f'permitido={r["permitido"]} [{r["fuente"]}] {r["latencia_total_ms"]:.0f} ms')
        if r["degradado"]:
            self.get_logger().warn(f'{msg} DEGRADADO ({r["motivo"]}) {r.get("detalle", "")}')
        else:
            self.get_logger().info(msg)
        return response


def main(args=None):
    rclpy.init(args=args)
    nodo = InterpreteOrdenes()
    ex = MultiThreadedExecutor(num_threads=4)
    ex.add_node(nodo)
    try:
        ex.spin()
    except KeyboardInterrupt:
        pass
    finally:
        nodo.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
