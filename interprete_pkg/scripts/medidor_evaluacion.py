#!/usr/bin/env python3
"""Evalúa las 50 frases oficiales, genera CSV y calcula latencia/exactitud.

CSV de entrada: datos/frases_50.csv. Las columnas de verdad de referencia
pueden quedar vacías durante una prueba técnica, pero sin etiquetas reales no
se puede reportar exactitud.
"""
import csv
import math
import os
import time
from statistics import median

import rclpy
from rclpy.node import Node
from interprete_pkg.srv import InterpretarOrden

FIELDS = [
    "id", "frase", "esperado_accion", "esperado_objeto", "esperado_color",
    "esperado_prioridad", "esperado_permitido"
]
OUTPUT_FIELDS = [
    "id", "frase", "esperado_accion", "esperado_objeto", "esperado_color",
    "esperado_prioridad", "esperado_permitido", "laya_accion", "laya_objeto",
    "laya_color", "laya_prioridad", "laya_permitido", "degradado", "metodo",
    "local_accion", "local_objeto", "local_color", "local_prioridad", "local_permitido",
    "latencia_servicio_ms", "latencia_laya_ms", "latencia_red_ms", "detalle_error",
    "correcto_laya", "correcto_local"
]


def bool_csv(value):
    value = str(value).strip().lower()
    if value in ("true", "1", "si", "sí", "yes"):
        return True
    if value in ("false", "0", "no"):
        return False
    return None


def p95(values):
    """Percentil 95 por método nearest-rank: posición ceil(0.95*n)."""
    if not values:
        return float("nan")
    s = sorted(values)
    return s[max(0, math.ceil(0.95 * len(s)) - 1)]


def exactitud(fila, prefijo):
    esperados = [
        str(fila.get("esperado_accion", "")).strip().lower(),
        str(fila.get("esperado_objeto", "")).strip().lower(),
        str(fila.get("esperado_color", "")).strip().lower(),
        str(fila.get("esperado_prioridad", "")).strip(),
        bool_csv(fila.get("esperado_permitido", "")),
    ]
    if any(x == "" or x is None for x in esperados):
        return ""
    obtenidos = [
        str(fila.get(f"{prefijo}_accion", "")).strip().lower(),
        str(fila.get(f"{prefijo}_objeto", "")).strip().lower(),
        str(fila.get(f"{prefijo}_color", "")).strip().lower(),
        str(fila.get(f"{prefijo}_prioridad", "")).strip(),
        bool_csv(fila.get(f"{prefijo}_permitido", "")),
    ]
    return all(a == b for a, b in zip(esperados, obtenidos))


class MedidorEvaluacion(Node):
    def __init__(self):
        super().__init__("medidor_evaluacion")
        self.declare_parameter("archivo_entrada", "datos/frases_50.csv")
        self.declare_parameter("archivo_salida", "resultados_50_frases.csv")
        self.declare_parameter("modo", "calma")
        self.declare_parameter("timeout_servicio", 10.0)
        self.cliente = self.create_client(InterpretarOrden, "/interpretar_orden")

    def cargar_frases(self):
        path = self.get_parameter("archivo_entrada").value
        if not os.path.isabs(path):
            path = os.path.abspath(path)
        if not os.path.exists(path):
            raise FileNotFoundError(f"No existe CSV de entrada: {path}")
        with open(path, newline="", encoding="utf-8-sig") as f:
            rows = list(csv.DictReader(f))
        if len(rows) != 50:
            raise ValueError(f"Se requieren exactamente 50 frases oficiales; el archivo tiene {len(rows)}")
        if not rows or not all("frase" in row and row["frase"].strip() for row in rows):
            raise ValueError("Cada fila debe contener una frase no vacía en la columna 'frase'")
        return rows

    def ejecutar(self):
        while not self.cliente.wait_for_service(timeout_sec=1.0):
            self.get_logger().info("Esperando /interpretar_orden...")
        entradas = self.cargar_frases()
        salida = []
        latencias = []
        for i, row in enumerate(entradas, 1):
            req = InterpretarOrden.Request()
            req.frase = row["frase"].strip()
            inicio = time.perf_counter()
            future = self.cliente.call_async(req)
            deadline = time.monotonic() + float(self.get_parameter("timeout_servicio").value)
            while rclpy.ok() and not future.done() and time.monotonic() < deadline:
                rclpy.spin_once(self, timeout_sec=0.05)
            elapsed_ms = (time.perf_counter() - inicio) * 1000.0
            if not future.done():
                raise TimeoutError(f"El servicio ROS 2 no respondió para la frase {i}; no se registra como medición válida")
            result = future.result()
            if result is None:
                raise RuntimeError(f"El servicio devolvió un resultado vacío para la frase {i}")
            latencias.append(elapsed_ms)
            item = {
                "id": row.get("id", str(i)), "frase": row["frase"].strip(),
                "esperado_accion": row.get("esperado_accion", ""),
                "esperado_objeto": row.get("esperado_objeto", ""),
                "esperado_color": row.get("esperado_color", ""),
                "esperado_prioridad": row.get("esperado_prioridad", ""),
                "esperado_permitido": row.get("esperado_permitido", ""),
                "laya_accion": result.accion, "laya_objeto": result.objeto,
                "laya_color": result.color, "laya_prioridad": result.prioridad,
                "laya_permitido": result.permitido, "degradado": result.degradado,
                "metodo": result.metodo, "local_accion": result.accion_local,
                "local_objeto": result.objeto_local, "local_color": result.color_local,
                "local_prioridad": result.prioridad_local, "local_permitido": result.permitido_local,
                "latencia_servicio_ms": round(elapsed_ms, 3),
                "latencia_laya_ms": round(result.latencia_laya_ms, 3),
                "latencia_red_ms": round(result.latencia_red_ms, 3),
                "detalle_error": result.detalle_error,
            }
            item["correcto_laya"] = exactitud({**item, "laya_accion": item["laya_accion"],
                "laya_objeto": item["laya_objeto"], "laya_color": item["laya_color"],
                "laya_prioridad": item["laya_prioridad"], "laya_permitido": item["laya_permitido"]}, "laya")
            item["correcto_local"] = exactitud({**item, "local_accion": item["local_accion"],
                "local_objeto": item["local_objeto"], "local_color": item["local_color"],
                "local_prioridad": item["local_prioridad"], "local_permitido": item["local_permitido"]}, "local")
            salida.append(item)
            self.get_logger().info(f"[{i}/50] {elapsed_ms:.1f} ms; método={result.metodo}")

        output_path = self.get_parameter("archivo_salida").value
        with open(output_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=OUTPUT_FIELDS)
            writer.writeheader()
            writer.writerows(salida)

        print("\n=== RESULTADOS PREGUNTA 1 ===")
        print(f"Modo declarado: {self.get_parameter('modo').value}")
        print(f"Frases medidas: {len(latencias)}")
        print(f"Mediana servicio ROS 2: {median(latencias):.3f} ms")
        print(f"P95 servicio ROS 2: {p95(latencias):.3f} ms")
        print(f"Promedio cálculo LAYA (solo respuestas LAYA): {self._promedio(salida, 'latencia_laya_ms'):.3f} ms")
        print(f"Promedio estimado red/HTTP (solo respuestas LAYA): {self._promedio(salida, 'latencia_red_ms'):.3f} ms")
        self._imprimir_exactitud(salida, "correcto_laya", "LAYA")
        self._imprimir_exactitud(salida, "correcto_local", "Clasificador local")
        print(f"CSV generado: {os.path.abspath(output_path)}")
        if any(x["correcto_laya"] == "" for x in salida):
            print("AVISO: exactitud no calculable para todas las frases: completa las columnas esperado_* con etiquetas de referencia.")

    @staticmethod
    def _promedio(rows, key):
        vals = [float(r[key]) for r in rows if r[key] not in ("", None) and float(r[key]) > 0]
        return sum(vals) / len(vals) if vals else 0.0

    @staticmethod
    def _imprimir_exactitud(rows, key, label):
        vals = [r[key] for r in rows if r[key] != ""]
        if not vals:
            print(f"Exactitud {label}: NO CALCULABLE (faltan etiquetas correctas)")
        else:
            correctos = sum(v is True or str(v).lower() == "true" for v in vals)
            print(f"Exactitud {label}: {100.0 * correctos / len(vals):.2f}% ({correctos}/{len(vals)})")


def main(args=None):
    rclpy.init(args=args)
    node = MedidorEvaluacion()
    try:
        node.ejecutar()
    except Exception as exc:
        node.get_logger().error(str(exc))
        raise
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
