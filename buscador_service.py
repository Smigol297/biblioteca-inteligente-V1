import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from translate import Translator
import database

class BuscadorLocal:
    def __init__(self):
        self.vectorizer = TfidfVectorizer(lowercase=True)
        self.matrix_tfidf = None
        self.paginas_data = []

    def entrenar_modelo(self):
        """Carga los datos desde el disco y entrena el motor matemático local."""
        filas = database.obtener_todas_las_paginas()
        if not filas:
            return False
            
        self.paginas_data = filas
        textos = [r[3] for r in filas]
        
        self.matrix_tfidf = self.vectorizer.fit_transform(textos)
        return True

    def _traducir_consulta(self, query):
        """Intenta traducir la consulta del español al inglés de forma segura."""
        try:
            translator = Translator(from_lang="es", to_lang="en")
            traduccion = translator.translate(query)
            if traduccion and traduccion.lower() != query.lower():
                return f"{query} {traduccion}"
        except Exception as e:
            print(f"⚠️ Error en traducción: {e}")
        return query

    def buscar(self, query, top_k=100, umbral_abs=0.03, umbral_rel=0.3, agrupar=False):
        """Búsqueda bilingüe: devuelve solo coincidencias fuertes.
        agrupar=True deja solo la mejor página de cada libro."""
        if self.matrix_tfidf is None:
            return []

        query_expandida = self._traducir_consulta(query)
        print(f"🔍 Buscando: {query_expandida}")

        vector_pregunta = self.vectorizer.transform([query_expandida])
        similitudes = cosine_similarity(self.matrix_tfidf, vector_pregunta).flatten()

        mejor = similitudes.max()
        if mejor <= 0:
            return []
        minimo = max(umbral_abs, mejor * umbral_rel)

        resultados = []
        vistos = set()
        for idx in np.argsort(similitudes)[::-1]:
            if similitudes[idx] < minimo:
                break  # están ordenados: los siguientes son todavía peores
            id_db, archivo, pagina, texto = self.paginas_data[idx]
            if agrupar:
                if archivo in vistos:
                    continue  # ya tenemos la mejor página de este libro
                vistos.add(archivo)
            resultados.append({
                "archivo": archivo,
                "pagina": int(pagina),
                "texto": texto[:300],
                "score": round(float(similitudes[idx]), 3),
            })
            if len(resultados) >= top_k:
                break
        return resultados

