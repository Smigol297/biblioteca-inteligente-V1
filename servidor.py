import os
import socket
import threading
import webbrowser
from flask import Flask, request, jsonify, send_from_directory
import config
import database
from indexador_service import procesar_un_archivo
from buscador_service import BuscadorLocal

app = Flask(__name__)

# Inicializar Base de datos al arrancar
database.inicializar_db()

# Inicializar y entrenar el buscador al levantar el servidor
buscador = BuscadorLocal()
print("Entrenando motor de busqueda local...")
buscador.entrenar_modelo()

@app.route('/')
def inicio():
    return '''
    <!DOCTYPE html>
    <html lang="es">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Mi Biblioteca Inteligente G3</title>
        <style>
            /* DISEÑO DE CÓDIGO LIMPIO CON SOPORTE AUTOMÁTICO DE MODO OSCURO */
            .opciones { margin-top: 10px; color: var(--texto-secundario); }
            #paginador { display: flex; justify-content: center; align-items: center; gap: 12px; margin-top: 15px; }
            #paginador button { padding: 8px 16px; }
            #paginador button:disabled { opacity: 0.4; cursor: default; }
            :root {
                --bg-principal: #f4f4f9;
                --bg-seccion: #ffffff;
                --texto: #333333;
                --texto-secundario: #555555;
                --borde: #dddddd;
                --primario: #2C3E50;
                --exito: #2ECC71;
            }

            @media (prefers-color-scheme: dark) {
                :root {
                    --bg-principal: #121212;
                    --bg-seccion: #1e1e1e;
                    --texto: #e0e0e0;
                    --texto-secundario: #aaaaaa;
                    --borde: #333333;
                    --primario: #34495E;
                    --exito: #27AE60;
                }
            }

            body { font-family: sans-serif; max-width: 800px; margin: 40px auto; padding: 0 20px; background: var(--bg-principal); color: var(--texto); transition: background 0.3s; }
            h1 { text-align: center; color: var(--texto); }
            .section { background: var(--bg-seccion); padding: 20px; margin-bottom: 20px; border-radius: 6px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); border: 1px solid var(--borde); }
            .search-box, .upload-box { display: flex; gap: 10px; margin-top: 10px; }
            input[type="text"] { flex: 1; padding: 12px; border: 1px solid var(--borde); border-radius: 4px; font-size: 16px; background: var(--bg-principal); color: var(--texto); }
            input[type="file"] { padding: 10px; color: var(--texto); }
            button { padding: 12px 24px; background: var(--primario); color: white; border: none; border-radius: 4px; cursor: pointer; font-size: 16px; font-weight: bold; }
            button:hover { opacity: 0.9; }
            .card { background: var(--bg-principal); padding: 15px; margin-top: 15px; border-radius: 4px; border-left: 4px solid var(--primario); border: 1px solid var(--borde); border-left: 4px solid var(--primario); }
            .meta { font-weight: bold; color: var(--texto-secundario); margin-bottom: 5px; }
            .snippet { font-style: italic; color: var(--texto-secundario); }
            .snippet mark { background: #f1c40f; color: #000; padding: 0 2px; border-radius: 2px; font-style: normal; font-weight: bold; }
            .btn-download { display: inline-block; margin-top: 10px; padding: 6px 12px; background: var(--exito); color: white; text-decoration: none; border-radius: 4px; font-size: 14px; font-weight: bold; }
            #status-upload { margin-top: 10px; font-weight: bold; color: var(--exito); }
            .acciones { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 10px; }
            .acciones .btn-download { margin-top: 0; }
            .btn-sec { display: inline-block; padding: 6px 12px; background: var(--primario); color: white; text-decoration: none; border: none; border-radius: 4px; font-size: 14px; font-weight: bold; cursor: pointer; }
            #visor { display: none; position: fixed; top: 0; left: 0; right: 0; bottom: 0; background: rgba(0,0,0,0.6); align-items: center; justify-content: center; padding: 20px; z-index: 10; }
            .visor-caja { background: var(--bg-seccion); border: 1px solid var(--borde); border-radius: 6px; width: 100%; max-width: 760px; max-height: 90vh; display: flex; flex-direction: column; padding: 16px; }
            .visor-head { display: flex; justify-content: space-between; align-items: center; gap: 10px; margin-bottom: 10px; }
            .visor-head button { padding: 6px 12px; }
            #visor-texto { overflow-y: auto; line-height: 1.6; padding: 4px 2px; flex: 1; }
            .visor-nav { display: flex; justify-content: space-between; align-items: center; gap: 10px; margin-top: 12px; }
            .visor-nav button { padding: 8px 16px; }
            .visor-nav button:disabled { opacity: 0.4; cursor: default; }
        </style>
    </head>
    <body>
        <h1>📚 Biblioteca Inteligente Hogareña</h1>
        
        <!-- PANEL DE INDEXACIÓN (SUBIR ARCHIVOS) -->
        <div class="section">
            <h3>📥 Agregar nuevo libro (PDF)</h3>
            <div class="upload-box">
                <input type="file" id="archivo-pdf" accept=".pdf,.docx,.txt,.md">
                <button onclick="subirPDF()">Subir e Indexar</button>
            </div>
            <div id="status-upload"></div>
        </div>

        <!-- PANEL DE BÚSQUEDA -->
        <div class="section">
            <h3>🔍 Buscar en la Biblioteca</h3>
            <div class="search-box">
                <input type="text" id="pregunta" placeholder="¿Qué querés buscar en tus libros?">
                <button onclick="buscar()">Buscar</button>
            </div>
            <div class="opciones">
                <label><input type="checkbox" id="agrupar"> Un resultado por libro</label>
            </div>
            <div id="resultados"></div>
            <div id="paginador"></div>
        </div>
        <div id="visor" onclick="if (event.target === this) cerrarVisor()">
            <div class="visor-caja">
                <div class="visor-head">
                    <strong id="visor-titulo"></strong>
                    <button onclick="cerrarVisor()">✕</button>
                </div>
                <div id="visor-texto"></div>
                <div class="visor-nav">
                    <button id="visor-ant">← Anterior</button>
                    <span id="visor-pos"></span>
                    <button id="visor-sig">Siguiente →</button>
                </div>
                <div class="acciones">
                    <a id="visor-pdf" class="btn-sec" target="_blank" style="display:none;">🔗 Abrir PDF en esta página</a>
                </div>
            </div>
        </div>
        <script>
            async function subirPDF() {
                const fileInput = document.getElementById('archivo-pdf');
                const statusDiv = document.getElementById('status-upload');
                
                if (fileInput.files.length === 0) {
                    alert("Por favor, seleccioná un archivo PDF primero.");
                    return;
                }
                
                const formData = new FormData();
                // SOLUCIÓN AL ERROR: Especificamos explícitamente el archivo [0]
                formData.append("file", fileInput.files[0]);
                
                statusDiv.style.color = "#E67E22";
                statusDiv.innerText = "Enviando e indexando en la netbook... (puede demorar unos segundos)";
                
                try {
                    const response = await fetch('/subir', { method: 'POST', body: formData });
                    const resultado = await response.json();
                    
                    if (resultado.exito) {
                        statusDiv.style.color = "#2ECC71";
                        statusDiv.innerText = `✅ ${resultado.mensaje}`;
                        fileInput.value = ""; 
                    } else {
                        statusDiv.style.color = "#E74C3C";
                        statusDiv.innerText = `❌ Error: ${resultado.mensaje}`;
                    }
                } catch (err) {
                    statusDiv.style.color = "#E74C3C";
                    statusDiv.innerText = "❌ Error de conexión con el servidor.";
                }
            }

            const POR_PAGINA = 10;
            let todos = [];

            function esc(s) {
                return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
            }
            
            function resaltar(trozos) {
                return trozos.map(t => t[1] ? `<mark>${esc(t[0])}</mark>` : esc(t[0])).join("");
            }

            async function buscar() {
                const query = document.getElementById('pregunta').value;
                if(!query) return;
                const agrupar = document.getElementById('agrupar').checked ? 1 : 0;
                const resDiv = document.getElementById('resultados');
                document.getElementById('paginador').innerHTML = "";
                resDiv.innerHTML = "<p style='text-align:center;'>Buscando localmente...</p>";

                const response = await fetch(`/buscar?q=${encodeURIComponent(query)}&agrupar=${agrupar}`);
                todos = await response.json();
                mostrarPagina(1);
            }

            function mostrarPagina(p) {
                const resDiv = document.getElementById('resultados');
                const pag = document.getElementById('paginador');

                if (todos.length === 0) {
                    resDiv.innerHTML = "<p>No encontré resultados.</p>";
                    pag.innerHTML = "";
                    return;
                }

                const paginas = Math.ceil(todos.length / POR_PAGINA);
                const ini = (p - 1) * POR_PAGINA;
                let html = "";
                todos.slice(ini, ini + POR_PAGINA).forEach((res, i) => {
                    const esPDF = res.archivo.toLowerCase().endsWith('.pdf');
                    html += `
                        <div class="card">
                            <div class="meta">📄 ${esc(res.archivo)} (Pág. ${res.pagina})</div>
                            <div class="snippet">${resaltar(res.fragmento)}</div>
                            <div class="acciones">
                                <button class="btn-sec" onclick="verPagina(${ini + i})">📖 Ver página completa</button>
                                ${esPDF ? `<a class="btn-sec" href="/ver/${encodeURIComponent(res.archivo)}#page=${res.pagina}" target="_blank">🔗 Abrir PDF en pág. ${res.pagina}</a>` : ""}
                                <a class="btn-download" href="/descargar/${encodeURIComponent(res.archivo)}" target="_blank">📥 Descargar Libro</a>
                            </div>
                        </div>`;
                });
                resDiv.innerHTML = html;

                pag.innerHTML = `
                    <button ${p <= 1 ? "disabled" : ""} onclick="mostrarPagina(${p - 1})">←</button>
                    <span>Página ${p} de ${paginas} (${todos.length} resultados)</span>
                    <button ${p >= paginas ? "disabled" : ""} onclick="mostrarPagina(${p + 1})">→</button>`;
                window.scrollTo({ top: resDiv.offsetTop - 20 });
            }

            document.getElementById('agrupar').addEventListener('change', buscar);
            let visorActual = null;

            function verPagina(idx) {
                const r = todos[idx];
                cargarPagina(r.archivo, r.pagina);
            }

            async function cargarPagina(archivo, n) {
                const visor = document.getElementById('visor');
                const texto = document.getElementById('visor-texto');
                visor.style.display = 'flex';
                texto.innerText = 'Cargando...';
                try {
                    const resp = await fetch(`/pagina?archivo=${encodeURIComponent(archivo)}&n=${n}`);
                    const d = await resp.json();
                    if (!resp.ok) { texto.innerText = d.error || 'Error'; return; }
                    visorActual = d;

                    const esPDF = d.archivo.toLowerCase().endsWith('.pdf');
                    const unidad = esPDF ? 'Pág.' : 'Bloque';
                    document.getElementById('visor-titulo').innerText = d.archivo;
                    texto.innerText = d.texto;   // innerText: no interpreta HTML
                    texto.scrollTop = 0;
                    document.getElementById('visor-pos').innerText = `${unidad} ${d.pagina} de ${d.ultima}`;

                    const ant = document.getElementById('visor-ant');
                    const sig = document.getElementById('visor-sig');
                    ant.disabled = d.anterior === null;
                    sig.disabled = d.siguiente === null;
                    ant.onclick = () => cargarPagina(d.archivo, d.anterior);
                    sig.onclick = () => cargarPagina(d.archivo, d.siguiente);

                    const lnk = document.getElementById('visor-pdf');
                    if (esPDF) {
                        lnk.href = `/ver/${encodeURIComponent(d.archivo)}#page=${d.pagina}`;
                        lnk.style.display = 'inline-block';
                    } else {
                        lnk.style.display = 'none';
                    }
                } catch (err) {
                    texto.innerText = 'Error de conexión con el servidor.';
                }
            }

            function cerrarVisor() {
                document.getElementById('visor').style.display = 'none';
            }

            document.addEventListener('keydown', e => {
                if (document.getElementById('visor').style.display !== 'flex' || !visorActual) return;
                if (e.key === 'Escape') cerrarVisor();
                else if (e.key === 'ArrowLeft' && visorActual.anterior !== null) cargarPagina(visorActual.archivo, visorActual.anterior);
                else if (e.key === 'ArrowRight' && visorActual.siguiente !== null) cargarPagina(visorActual.archivo, visorActual.siguiente);
            });
        </script>
    </body>
    </html>
    '''

@app.route('/buscar')
def api_buscar():
    query = request.args.get('q', '').strip()
    if not query: return jsonify([])
    agrupar = request.args.get('agrupar') == '1'
    try:
        n = int(request.args.get('n', 100))
    except ValueError:
        n = 100
    n = max(1, min(n, 200))
    resultados = buscador.buscar(query, top_k=n, agrupar=agrupar)
    return jsonify(resultados)

@app.route('/subir', methods=['POST'])
def api_subir():
    if 'file' not in request.files:
        return jsonify({"exito": False, "mensaje": "No se envió ningún archivo"})
        
    archivo = request.files['file']
    if archivo.filename == '':
        return jsonify({"exito": False, "mensaje": "Nombre de archivo vacío"})
        
    # Agregamos las nuevas extensiones permitidas
    extensiones_validas = ('.pdf', '.docx', '.txt', '.md')
    nombre_archivo = archivo.filename
    
    if archivo and nombre_archivo.lower().endswith(extensiones_validas):
        ruta_destino = os.path.join(config.CARPETA_PDFS, nombre_archivo)
        
        # Guardar físicamente en el disco rígido de la netbook
        archivo.save(ruta_destino)
        
        # Llamamos al servicio actualizado (que ahora procesa cualquier formato)
        exito, resultado = procesar_un_archivo(ruta_destino, nombre_archivo)
        
        if exito:
            buscador.entrenar_modelo() # Re-entrenar el buscador con los nuevos textos
            return jsonify({"exito": True, "mensaje": f"¡{nombre_archivo} indexado! ({resultado} bloques añadidos)"})
        else:
            return jsonify({"exito": False, "mensaje": f"Guardado pero falló la lectura: {resultado}"})
            
    return jsonify({"exito": False, "mensaje": "Formato no permitido. Solo se aceptan: .pdf, .docx, .txt, .md"})

@app.route('/descargar/<path:nombre_archivo>')
def descargar_archivo(nombre_archivo):
    return send_from_directory(config.CARPETA_PDFS, nombre_archivo, as_attachment=True)

@app.route('/ver/<path:nombre_archivo>')
def ver_archivo(nombre_archivo):
    # Sin as_attachment: el navegador lo muestra en pestaña (PDF) en vez de descargarlo
    return send_from_directory(config.CARPETA_PDFS, nombre_archivo, as_attachment=False)

@app.route('/pagina')
def api_pagina():
    archivo = request.args.get('archivo', '')
    try:
        n = int(request.args.get('n', 1))
    except ValueError:
        return jsonify({"error": "Página inválida"}), 400
    datos = database.obtener_pagina(archivo, n)
    if datos is None:
        return jsonify({"error": "Página no encontrada"}), 404
    return jsonify(datos)

def obtener_ip_local():
    """Devuelve la IP de la PC en la red local (ej: 192.168.0.25)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))  # no envía datos, solo elige la interfaz
        return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"  # sin red: vuelve a localhost
    finally:
        s.close()
        
if __name__ == '__main__':
    host_env = os.environ.get("FLASK_HOST", "0.0.0.0")
    port_env = int(os.environ.get("FLASK_PORT", 5000))
    url = f"http://{obtener_ip_local()}:{port_env}"
    print(f"\n Biblioteca lista en {url}  (cerra esta ventana para apagarla)\n")
    threading.Timer(2.0, lambda: webbrowser.open(url)).start()
    app.run(host=host_env, port=port_env, debug=False)
