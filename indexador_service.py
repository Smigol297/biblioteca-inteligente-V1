import os
from pypdf import PdfReader
from docx import Document
import database

def leer_pdf(ruta):
    """Extrae el texto de un archivo PDF por páginas."""
    paginas = []
    reader = PdfReader(ruta)
    for num_pagina, pagina in enumerate(reader.pages, start=1):
        texto = pagina.extract_text()
        if texto:
            paginas.append((num_pagina, texto))
    return paginas

def leer_docx(ruta):
    """Extrae el texto de un archivo Word (.docx). Simula páginas dividiendo por párrafos."""
    doc = Document(ruta)
    paginas = []
    texto_acumulado = []
    num_pagina = 1
    
    for i, parrafo in enumerate(doc.paragraphs):
        if parrafo.text.strip():
            texto_acumulado.append(parrafo.text.strip())
        
        # Cada 15 párrafos simulamos un cambio de página para no tener un bloque gigante
        if (i + 1) % 15 == 0 and texto_acumulado:
            paginas.append((num_pagina, " ".join(texto_acumulado)))
            texto_acumulado = []
            num_pagina += 1
            
    if texto_acumulado:
        paginas.append((num_pagina, " ".join(texto_acumulado)))
        
    return paginas

def leer_texto_plano(ruta):
    """Extrae el texto de archivos .txt y .md. Divide el contenido en bloques/páginas."""
    paginas = []
    # Usamos errors='ignore' por si hay caracteres raros o tildes rotas en Python 3.6
    with open(ruta, "r", encoding="utf-8", errors="ignore") as f:
        lineas = f.readlines()
        
    texto_acumulado = []
    num_pagina = 1
    
    for i, linea in enumerate(lineas):
        if linea.strip():
            texto_acumulado.append(linea.strip())
            
        # Cada 30 líneas de texto simulamos una página
        if (i + 1) % 30 == 0 and texto_acumulado:
            paginas.append((num_pagina, " ".join(texto_acumulado)))
            texto_acumulado = []
            num_pagina += 1
            
    if texto_acumulado:
        paginas.append((num_pagina, " ".join(texto_acumulado)))
        
    return paginas

def procesar_un_archivo(ruta_completa, nombre_archivo):
    """Detecta la extensión del archivo, extrae su texto y lo guarda en la DB."""
    extension = nombre_archivo.lower().split('.')[-1]
    
    try:
        # 1. Enrutar según el formato del archivo
        if extension == 'pdf':
            paginas = leer_pdf(ruta_completa)
        elif extension == 'docx':
            paginas = leer_docx(ruta_completa)
        elif extension in ['txt', 'md']:
            paginas = leer_texto_plano(ruta_completa)
        else:
            return False, f"Formato .{extension} no soportado."
            
        # 2. Guardar las páginas procesadas en la base de datos
        paginas_guardadas = 0
        for num_pagina, texto in paginas:
            if len(texto.strip()) > 30:
                texto_limpio = " ".join(texto.strip().split())
                database.guardar_pagina(nombre_archivo, num_pagina, texto_limpio)
                paginas_guardadas += 1
                
        return True, paginas_guardadas
        
    except Exception as e:
        return False, str(e)
