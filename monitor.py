"""Monitor de salud V1 para Biblioteca Inteligente.

Corre un corpus sintetico de 25 libros x 300 paginas-generador con marcadores
unicos por libro, sin traduccion real, sin tocar la base ni el corpus reales.
Devuelve dos veredictos:

  - CORRECTITUD: 6 consultas con resultado esperado -> define el exit code
  - RENDIMIENTO: arranque, busqueda (min/med/max), memoria -> informativo

Exit code: 0 = correctitud OK, 1 = correctitud FALLA, 2 = argumentos invalidos.

Uso:
    python monitor.py
    python monitor.py --libros 25 --paginas 12 --repeticiones 3
    python monitor.py --json reporte.json
    python servidor.py --monitor
"""

import argparse
import json
import os
import platform
import random
import shutil
import statistics
import sys
import tempfile
import time
import traceback

import database
from buscador_service import BuscadorLocal, _coleccion_de
from indexador_service import procesar_un_archivo

# --- Vocabulario y conectores (sin tildes) ----------------------------------
VOCABULARIO = {
    "programacion": [
        "algoritmo",
        "variable",
        "bucle",
        "codigo",
        "compilar",
        "depurar",
        "memoria",
        "programa",
        "ejecutar",
        "datos",
        "logica",
        "modulo",
        "clase",
        "objeto",
        "metodo",
        "funcion",
        "cadena",
        "entero",
        "puntero",
        "arreglo",
        "recursion",
        "iteracion",
        "compilador",
        "interprete",
        "sentencia",
        "operador",
        "asignacion",
        "condicion",
    ],
    "cocina": [
        "harina",
        "huevos",
        "azucar",
        "manteca",
        "leche",
        "sal",
        "mezclar",
        "batir",
        "hornear",
        "cocinar",
        "sarten",
        "horno",
        "receta",
        "sabor",
        "ingrediente",
        "plato",
        "cuchara",
        "olla",
        "hervir",
        "freir",
        "picar",
        "revolver",
        "amasar",
        "estirar",
        "servir",
        "porcion",
        "condimento",
        "salsa",
    ],
}

CONECTORES = [
    "y",
    "con",
    "para",
    "de",
    "en",
    "que",
    "el",
    "la",
    "los",
    "las",
    "un",
    "una",
    "del",
    "al",
    "sobre",
    "entre",
    "sin",
    "por",
]

# Reparto del corpus. La proporcion 13/12 mantiene ambas colecciones parejas.
PROP_COLECCIONES = {"programacion": 13, "cocina": 12}
PALABRAS_POR_PAGINA = 80
LINEAS_POR_PAGINA_DB = 30  # leer_texto_plano corta cada 30 lineas
SEMILLA = 20251014


# --- Clasificaciones (V1: umbrales mas laxos que V2, es TF-IDF puro) --------
NIVELES = ["EXCELENTE", "BUENO", "ACEPTABLE", "LENTO"]


def _clas_lat(ms):
    if ms < 50:
        return "EXCELENTE", 0
    if ms < 200:
        return "BUENO", 1
    if ms < 600:
        return "ACEPTABLE", 2
    return "LENTO", 3


def _clas_mem(mb):
    if mb < 300:
        return "EXCELENTE", 0
    if mb < 600:
        return "BUENO", 1
    if mb < 1200:
        return "ACEPTABLE", 2
    return "ALTO", 3


def _clas_arr(s):
    if s < 5:
        return "EXCELENTE", 0
    if s < 15:
        return "BUENO", 1
    if s < 45:
        return "ACEPTABLE", 2
    return "LENTO", 3


GLOBAL = ["EXCELENTE", "BUENO", "ACEPTABLE", "MEJORABLE"]


def _peor(niveles):
    return max(niveles) if niveles else 0


def _ram_rec(mem_mb):
    """Recomendacion redondeada a multiplos de 256 MB, minimo 256 MB."""
    if not mem_mb:
        return None
    mb = mem_mb * 1.5 + 128
    return int(((mb + 255) // 256) * 256)


# --- Sistema ----------------------------------------------------------------
def _nucleos():
    try:
        return os.cpu_count() or 0
    except Exception:
        return 0


def _ram_total_bytes():
    try:
        with open("/proc/meminfo", "r") as fh:
            for linea in fh:
                if linea.startswith("MemTotal:"):
                    return int(linea.split()[1]) * 1024
    except Exception:
        pass
    return None


def _rss_bytes():
    """RSS del proceso actual. /proc en Linux, rusage como fallback."""
    try:
        with open("/proc/self/status", "r") as fh:
            for linea in fh:
                if linea.startswith("VmRSS:"):
                    return int(linea.split()[1]) * 1024
    except Exception:
        pass
    try:
        import resource

        return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024
    except Exception:
        return None


# --- Marcadores unicos por libro --------------------------------------------
def _asignar_marcadores(libros_por_coleccion):
    mapa = {}
    n = 0
    for coleccion, cantidad in libros_por_coleccion.items():
        for i in range(cantidad):
            n += 1
            ruta = "%s/libro_%03d.txt" % (coleccion, i + 1)
            mapa[ruta] = ["marcadorA%02d" % n, "marcadorB%02d" % n]
    return mapa


def _repartir_libros(total, prop):
    """Reparte `total` libros segun las proporciones, ajustando el resto."""
    if total < len(prop):
        # Si piden menos libros que colecciones, dar uno a cada una en orden.
        return {c: (1 if i < total else 0) for i, c in enumerate(prop)}
    base = {c: max(1, int(total * p / sum(prop.values()))) for c, p in prop.items()}
    resto = total - sum(base.values())
    i = 0
    nombres = list(prop.keys())
    while resto > 0:
        base[nombres[i % len(nombres)]] += 1
        i += 1
        resto -= 1
    return base


# --- Generador de corpus ----------------------------------------------------
def _generar_libro(rng, vocabulario, marcadores, paginas, palabras_por_pagina):
    salida = []
    for _ in range(paginas):
        palabras = []
        for _ in range(palabras_por_pagina):
            if marcadores and rng.random() < 0.15:
                palabras.append(rng.choice(marcadores))
            else:
                palabras.append(rng.choice(vocabulario))
            if rng.random() < 0.4:
                palabras.append(rng.choice(CONECTORES))
        texto = " ".join(palabras)
        salida.append(texto[0].upper() + texto[1:] + ".")
    return salida


def _generar_corpus(libros_por_coleccion, paginas_por_libro, mapa_marcadores, semilla=SEMILLA):
    rng = random.Random(semilla)
    corpus = {}
    for coleccion, cantidad in libros_por_coleccion.items():
        for i in range(cantidad):
            ruta = "%s/libro_%03d.txt" % (coleccion, i + 1)
            marcadores = mapa_marcadores[ruta]
            corpus[ruta] = _generar_libro(
                rng,
                VOCABULARIO[coleccion],
                marcadores,
                paginas_por_libro,
                PALABRAS_POR_PAGINA,
            )
    return corpus


def _escribir_corpus(carpeta_pdfs, corpus):
    if os.path.isdir(carpeta_pdfs):
        shutil.rmtree(carpeta_pdfs)
    os.makedirs(carpeta_pdfs)
    for ruta_rel, lineas in corpus.items():
        ruta_abs = os.path.join(carpeta_pdfs, *ruta_rel.split("/"))
        carpeta = os.path.dirname(ruta_abs)
        if carpeta and not os.path.isdir(carpeta):
            os.makedirs(carpeta)
        with open(ruta_abs, "w", encoding="utf-8") as fh:
            fh.write("\n".join(lineas))


# --- Silenciar traduccion real ---------------------------------------------
def _silenciar_traduccion():
    def _identidad(self, consulta):
        return consulta

    BuscadorLocal._traducir_consulta = _identidad


# --- Casos de correctitud ---------------------------------------------------
def _casos_correctitud(mapa_marcadores):
    """Se generan a partir del mapa real, para no depender de nombres fijos."""
    prog = sorted(r for r in mapa_marcadores if r.startswith("programacion/"))
    coc = sorted(r for r in mapa_marcadores if r.startswith("cocina/"))
    return [
        {
            "query": mapa_marcadores[prog[0]][0],
            "coleccion": None,
            "debe_estar": {prog[0]},
            "colecciones_ok": {"programacion", "cocina"},
            "espera_vacio": False,
            "descripcion": "marcador unico: top-1 primer libro de programacion",
        },
        {
            "query": " ".join(mapa_marcadores[prog[1]]),
            "coleccion": None,
            "debe_estar": {prog[1]},
            "colecciones_ok": {"programacion", "cocina"},
            "espera_vacio": False,
            "descripcion": "dos marcadores del mismo libro: top-1 estable",
        },
        {
            "query": mapa_marcadores[coc[0]][0],
            "coleccion": "cocina",
            "debe_estar": {coc[0]},
            "colecciones_ok": {"cocina"},
            "espera_vacio": False,
            "descripcion": "marcador unico con filtro de coleccion",
        },
        {
            "query": "algoritmo",
            "coleccion": "programacion",
            "debe_estar": set(),
            "colecciones_ok": {"programacion"},
            "espera_vacio": False,
            "descripcion": "vocabulario compartido: solo programacion",
        },
        {
            "query": "harina huevos",
            "coleccion": None,
            "debe_estar": set(),
            "colecciones_ok": {"cocina"},
            "espera_vacio": False,
            "descripcion": "vocabulario compartido de cocina",
        },
        {
            "query": "ensalada",
            "coleccion": "programacion",
            "debe_estar": set(),
            "colecciones_ok": {"programacion"},
            "espera_vacio": True,
            "descripcion": "sin resultados: cocina excluida por filtro",
        },
    ]


def _evaluar_correctitud(buscador, caso):
    query = caso["query"]
    coleccion = caso["coleccion"]
    debe_estar = caso["debe_estar"]
    colecciones_ok = caso["colecciones_ok"]
    espera_vacio = caso["espera_vacio"]

    error = None
    resultados = []
    try:
        resultados = buscador.buscar(query, coleccion=coleccion)
    except Exception:
        error = traceback.format_exc(limit=3).strip()

    obtenidos = [r.get("archivo") for r in resultados if r.get("archivo")]
    distintos = set(obtenidos)

    faltan, fuera, top1_msg = [], [], None
    ok_estructura = True

    if espera_vacio:
        if obtenidos:
            ok_estructura = False
            top1_msg = "se esperaba vacio; obtenidos: %s" % (sorted(distintos),)
    else:
        faltan = sorted(debe_estar - distintos)
        fuera = sorted(a for a in distintos if _coleccion_de(a) not in colecciones_ok)
        if debe_estar:
            if not obtenidos or obtenidos[0] not in debe_estar:
                ok_estructura = False
                top1_msg = "top-1 inesperado; obtenidos: %s" % (obtenidos[:3],)
        elif not obtenidos:
            ok_estructura = False
            top1_msg = "se esperaba al menos 1 resultado"
        if faltan or fuera:
            ok_estructura = False

    ok = (error is None) and ok_estructura
    return {
        "query": query,
        "coleccion": coleccion,
        "descripcion": caso["descripcion"],
        "ok": ok,
        "error": error,
        "faltan": faltan,
        "fuera": fuera,
        "top1_msg": top1_msg,
        "n": len(obtenidos),
    }


# --- Medicion de rendimiento ------------------------------------------------
def _medir_tiempos(buscador, casos, repeticiones):
    """Corre cada consulta `repeticiones` veces y devuelve min/med/max en ms."""
    filas = []
    for caso in casos:
        tiempos = []
        for _ in range(repeticiones):
            t0 = time.perf_counter()
            try:
                buscador.buscar(caso["query"], coleccion=caso["coleccion"])
            except Exception:
                pass
            tiempos.append((time.perf_counter() - t0) * 1000.0)
        tiempos.sort()
        filas.append(
            {
                "query": caso["query"],
                "min": tiempos[0],
                "med": statistics.median(tiempos),
                "max": tiempos[-1],
            }
        )
    return filas


# --- Reporte ----------------------------------------------------------------
def _fmt_mb(b):
    if not b:
        return "-"
    return "%.1f MB" % (b / (1024.0 * 1024.0))


def _fmt_gb(b):
    if not b:
        return "-"
    return "%.1f GB" % (b / (1024.0 * 1024.0 * 1024.0))


def _imprimir_reporte(rep):
    print("=" * 78)
    print("MONITOR BIBLIOTECA INTELIGENTE - V1")
    print("=" * 78)
    sis = rep["sistema"]
    print(
        "Sistema:   %s | %s | Python %s | %d nucleos | %s RAM"
        % (
            sis["so"],
            sis["arquitectura"],
            sis["python"],
            sis["nucleos"],
            _fmt_gb(sis["ram_total_bytes"]),
        )
    )
    c = rep["corpus"]
    print(
        "Corpus:    %d libros x %d paginas-generador (%d paginas DB) | %d caracteres"
        % (
            c["libros"],
            c["paginas_por_libro"],
            c["paginas_db"],
            c["caracteres"],
        )
    )
    print("Semilla:   %d | Repeticiones: %d" % (c["semilla"], rep["_reps"]))
    print("-" * 78)
    print("CORRECTITUD")
    print("-" * 78)
    print("{:<32} {:<11} {:<6} {}".format("consulta", "coleccion", "estado", "n"))
    print("-" * 78)
    for f in rep["correctitud"]["filas"]:
        print(
            "{:<32} {:<11} {:<6} {}".format(
                f["query"][:32],
                (f["coleccion"] or "-")[:11],
                "OK" if f["ok"] else "FALLA",
                f["n"],
            )
        )
        if not f["ok"]:
            print("    caso:   {}".format(f["descripcion"]))
            if f["error"]:
                print("    error:  {}".format(f["error"].splitlines()[-1]))
            if f["top1_msg"]:
                print("    top-1:  {}".format(f["top1_msg"]))
            if f["faltan"]:
                print("    faltan: {}".format(f["faltan"]))
            if f["fuera"]:
                print("    fuera:  {}".format(f["fuera"]))
    cc = rep["correctitud"]
    print("-" * 78)
    print(
        "VEREDICTO CORRECTITUD: {} ({} de {} consultas)".format(
            "OK" if cc["ok"] else "FALLA",
            cc["pasadas"],
            cc["total"],
        )
    )
    print("-" * 78)

    print("RENDIMIENTO")
    print("-" * 78)
    arr = rep["arranque"]
    print(
        "Arranque:  carga_db=%.3fs  tfidf=%.3fs  total=%.3fs"
        % (
            arr["carga_db_s"],
            arr["tfidf_s"],
            arr["total_s"],
        )
    )
    print("Busqueda (ms, %d reps/consulta):" % rep["_reps"])
    print("  {:<32} {:>8} {:>8} {:>8}".format("consulta", "min", "med", "max"))
    for f in rep["busqueda"]["filas"]:
        print(
            "  {:<32} {:>8.1f} {:>8.1f} {:>8.1f}".format(
                f["query"][:32],
                f["min"],
                f["med"],
                f["max"],
            )
        )
    print(
        "  {:<32} {:>8.1f} {:>8.1f} {:>8.1f}".format(
            "AGREGADO",
            rep["busqueda"]["min"],
            rep["busqueda"]["med"],
            rep["busqueda"]["max"],
        )
    )
    mem = rep["memoria"]
    print(
        "Memoria:   RSS tras entrenar=%s | pico=%s"
        % (
            _fmt_mb(mem["rss_tras_entrenar_bytes"]),
            _fmt_mb(mem["rss_pico_bytes"]),
        )
    )
    print("-" * 78)
    v = rep["veredicto"]
    print("Veredicto latencia:   {}".format(v["latencia"]))
    print("Veredicto memoria:    {}".format(v["memoria"]))
    print("Veredicto arranque:   {}".format(v["arranque"]))
    print("VEREDICTO GLOBAL:     {}".format(v["global"]))
    print(
        "RAM recomendada:      {}".format(
            "{} MB".format(v["ram_recomendada_mb"]) if v["ram_recomendada_mb"] else "-"
        )
    )
    print("=" * 78)


# --- main -------------------------------------------------------------------
def main(argv=None):
    p = argparse.ArgumentParser(prog="monitor.py")
    p.add_argument("--libros", type=int, default=25)
    p.add_argument(
        "--paginas",
        type=int,
        default=300,
        help="paginas-generador por libro (se dividen cada %d lineas)" % LINEAS_POR_PAGINA_DB,
    )
    p.add_argument("--repeticiones", type=int, default=3)
    p.add_argument("--json", metavar="ARCHIVO")
    args, _ = p.parse_known_args(argv)

    if args.libros < 1 or args.paginas < 1 or args.repeticiones < 1:
        print("ERROR: valores deben ser >= 1", file=sys.stderr)
        return 2

    sistema = {
        "so": platform.platform(),
        "arquitectura": platform.machine(),
        "python": platform.python_version(),
        "nucleos": _nucleos(),
        "ram_total_bytes": _ram_total_bytes(),
    }

    tmp = tempfile.mkdtemp(prefix="bib_monitor_")
    db_path = os.path.join(tmp, "monitor.db")
    carpeta_pdfs = os.path.join(tmp, "mis_pdfs")
    db_path_original = database.DB_PATH

    try:
        # 1. Aislar base y corpus.
        database.DB_PATH = db_path
        database.inicializar_db()

        libros_por_coleccion = _repartir_libros(args.libros, PROP_COLECCIONES)
        mapa_marcadores = _asignar_marcadores(libros_por_coleccion)
        corpus = _generar_corpus(libros_por_coleccion, args.paginas, mapa_marcadores, SEMILLA)
        caracteres = sum(len(pg) for pgs in corpus.values() for pg in pgs)
        _escribir_corpus(carpeta_pdfs, corpus)

        # 2. Indexar.
        for ruta_rel in corpus:
            ruta_abs = os.path.join(carpeta_pdfs, *ruta_rel.split("/"))
            exito, detalle = procesar_un_archivo(ruta_abs, ruta_rel)
            if not exito:
                raise RuntimeError("No se pudo indexar {}: {}".format(ruta_rel, detalle))
        paginas_db = len(database.obtener_todas_las_paginas())

        # 3. Arranque: carga de DB + fit del TF-IDF.
        _silenciar_traduccion()
        buscador = BuscadorLocal()

        t0 = time.perf_counter()
        # filas = database.obtener_todas_las_paginas()
        t_carga = time.perf_counter() - t0

        # fit_transform se hace dentro de entrenar_modelo; medimos el bloque entero.
        t0 = time.perf_counter()
        if not buscador.entrenar_modelo():
            raise RuntimeError("entrenar_modelo() devolvio False: base temporal vacia.")
        t_tfidf = time.perf_counter() - t0
        t_total_arr = t_carga + t_tfidf

        rss_tras_ent = _rss_bytes()

        # 4. Correctitud.
        casos = _casos_correctitud(mapa_marcadores)
        filas_corr = [_evaluar_correctitud(buscador, c) for c in casos]
        pasadas = sum(1 for f in filas_corr if f["ok"])
        correctitud_ok = pasadas == len(filas_corr)

        # 5. Rendimiento (repeticiones, min/med/max).
        filas_med = _medir_tiempos(buscador, casos, args.repeticiones)
        todos = [f["med"] for f in filas_med]
        b_min = min(f["min"] for f in filas_med)
        b_med = statistics.median(todos)
        b_max = max(f["max"] for f in filas_med)

        rss_pico = max(_rss_bytes() or 0, rss_tras_ent or 0) or None
        mem_mb = rss_pico / (1024.0 * 1024.0) if rss_pico else 0.0
        mem_txt, mem_niv = _clas_mem(mem_mb)
        lat_txt, lat_niv = _clas_lat(b_med)
        arr_txt, arr_niv = _clas_arr(t_total_arr)
        peor = _peor([lat_niv, mem_niv, arr_niv])

        resultado = {
            "fecha": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "sistema": sistema,
            "corpus": {
                "libros": args.libros,
                "paginas_por_libro": args.paginas,
                "paginas_db": paginas_db,
                "caracteres": caracteres,
                "semilla": SEMILLA,
                "reparto_colecciones": libros_por_coleccion,
            },
            "arranque": {
                "carga_db_s": round(t_carga, 4),
                "tfidf_s": round(t_tfidf, 4),
                "total_s": round(t_total_arr, 4),
            },
            "correctitud": {
                "filas": filas_corr,
                "pasadas": pasadas,
                "total": len(filas_corr),
                "ok": correctitud_ok,
            },
            "busqueda": {
                "filas": filas_med,
                "min": round(b_min, 2),
                "med": round(b_med, 2),
                "max": round(b_max, 2),
            },
            "memoria": {
                "rss_tras_entrenar_bytes": rss_tras_ent,
                "rss_pico_bytes": rss_pico,
            },
            "veredicto": {
                "latencia": lat_txt,
                "memoria": mem_txt,
                "arranque": arr_txt,
                "global": GLOBAL[peor],
                "ram_recomendada_mb": _ram_rec(mem_mb),
            },
            "_reps": args.repeticiones,
        }

        _imprimir_reporte(resultado)
        if args.json:
            with open(args.json, "w", encoding="utf-8") as fh:
                json.dump(resultado, fh, indent=2, ensure_ascii=False)
            print("JSON guardado en: %s" % args.json)

        return 0 if correctitud_ok else 1

    except Exception as exc:
        print("Excepcion inesperada durante el monitor:")
        traceback.print_exc()
        print("VEREDICTO: FALLA ({})".format(exc))
        return 1
    finally:
        database.DB_PATH = db_path_original
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
