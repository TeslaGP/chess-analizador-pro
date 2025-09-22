import requests
import chess.pgn
import io
from collections import Counter, defaultdict
import datetime
import os
import json
import random

class ChessAnalizadorPro:
    """
    Clase unificada para analizar y generar informes y recomendaciones de partidas
    de un jugador de Chess.com.
    """

    def __init__(self, username: str):
        self.user = username.lower()
        self.base_url = f"https://api.chess.com/pub/player/{self.user}/games/archives"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        }
        self.partidas = []
        self.stats = {}

    def obtener_partidas(self, meses_a_analizar: int = 1) -> bool:
        """
        Obtiene las partidas de los últimos N meses del jugador.
        Retorna True si la operación fue exitosa, False en caso contrario.
        """
        print(f"Obteniendo archivos de partidas para {self.user}...")
        try:
            res_archives = requests.get(self.base_url, headers=self.headers)
            res_archives.raise_for_status()
            archivos = res_archives.json()["archives"]
            
            archivos_a_descargar = archivos[-meses_a_analizar:]
            
            for url_mes in archivos_a_descargar:
                print(f"Descargando partidas de: {url_mes.split('/')[-2]}/{url_mes.split('/')[-1]}", end="...")
                res_games = requests.get(url_mes, headers=self.headers)
                res_games.raise_for_status()
                self.partidas.extend(res_games.json()["games"])
                print("¡listo!")
            
            return True
            
        except requests.exceptions.RequestException as e:
            print(f"Error al conectar con la API: {e}")
            return False

    def analizar_partidas(self, filtro_tc=None, min_rating=0):
        """
        Procesa las partidas obtenidas y calcula estadísticas, aplicando filtros.
        """
        if not self.partidas:
            print("No hay partidas para analizar.")
            return

        print("\nAnalizando partidas...")
        
        self.stats = {
            "ganadas": 0, "perdidas": 0, "tablas": 0,
            "blancas_g": 0, "blancas_partidas": 0,
            "negras_g": 0, "negras_partidas": 0,
            "total_jugadas": 0,
            "rivales": [],
            "ratings_rivales": [],
            "time_controls": Counter(),
            "tablas_por_tipo": Counter(),
            "racha_actual": 0, "racha_max_g": 0, "racha_max_p": 0,
            "partida_corta": ("", 9999),
            "partida_larga": ("", 0),
            "mejor_victoria": ("", 0),
            "peor_derrota": ("", 9999),
            "aperturas": Counter(),
            "aperturas_con_resultados": defaultdict(lambda: {'ganadas': 0, 'total': 0}),
            "partidas_analizadas": 0,
            "juegos_por_dia": defaultdict(int),
            "resultados_dia": defaultdict(Counter),
        }

        for game in self.partidas:
            tc = game.get("time_control", "N/A")
            if filtro_tc and tc != filtro_tc:
                continue

            blanco = game["white"]["username"].lower()
            negro = game["black"]["username"].lower()
            
            if blanco == self.user:
                self.stats["blancas_partidas"] += 1
                rival = negro
                rating_rival = game["black"].get("rating", 0)
                resultado = game["white"]["result"]
            else:
                self.stats["negras_partidas"] += 1
                rival = blanco
                rating_rival = game["white"].get("rating", 0)
                resultado = game["black"]["result"]

            if rating_rival < min_rating:
                continue

            self.stats["rivales"].append(rival)
            self.stats["ratings_rivales"].append(rating_rival)
            self.stats["partidas_analizadas"] += 1

            if resultado == "win":
                self.stats["ganadas"] += 1
                self.stats["racha_actual"] = self.stats["racha_actual"] + 1 if self.stats["racha_actual"] >= 0 else 1
                self.stats["racha_max_g"] = max(self.stats["racha_max_g"], self.stats["racha_actual"])
                if blanco == self.user:
                    self.stats["blancas_g"] += 1
                else:
                    self.stats["negras_g"] += 1
                if rating_rival > self.stats["mejor_victoria"][1]:
                    self.stats["mejor_victoria"] = (rival, rating_rival)
            elif resultado in ("checkmated", "resigned", "timeout", "lose"):
                self.stats["perdidas"] += 1
                self.stats["racha_actual"] = self.stats["racha_actual"] - 1 if self.stats["racha_actual"] <= 0 else -1
                self.stats["racha_max_p"] = min(self.stats["racha_max_p"], self.stats["racha_actual"])
                if rating_rival < self.stats["peor_derrota"][1]:
                    self.stats["peor_derrota"] = (rival, rating_rival)
            else: # Empate
                self.stats["tablas"] += 1
                self.stats["tablas_por_tipo"][resultado] += 1
                self.stats["racha_actual"] = 0

            # Análisis del PGN
            if "pgn" in game:
                try:
                    pgn_io = io.StringIO(game["pgn"])
                    partida_pgn = chess.pgn.read_game(pgn_io)
                    if partida_pgn:
                        jugadas = sum(1 for _ in partida_pgn.mainline_moves())
                        self.stats["total_jugadas"] += jugadas
                        if jugadas < self.stats["partida_corta"][1]:
                            self.stats["partida_corta"] = (game["pgn"], jugadas)
                        if jugadas > self.stats["partida_larga"][1]:
                            self.stats["partida_larga"] = (game["pgn"], jugadas)
                            
                        # Usar los primeros 4 movimientos para identificar la apertura
                        apertura_key = " ".join(str(move) for _, move in zip(range(4), partida_pgn.mainline_moves()))
                        if apertura_key:
                            self.stats["aperturas"][apertura_key] += 1
                            if resultado == "win":
                                self.stats["aperturas_con_resultados"][apertura_key]['ganadas'] += 1
                            self.stats["aperturas_con_resultados"][apertura_key]['total'] += 1

                except Exception as e:
                    print(f"Error al parsear PGN: {e}")
                    continue

            self.stats["time_controls"][tc] += 1
            fecha = datetime.datetime.fromtimestamp(game.get("end_time", 0))
            dia_semana = fecha.strftime("%A")
            self.stats["juegos_por_dia"][dia_semana] += 1

            if resultado == "win":
                self.stats["resultados_dia"][dia_semana]["ganadas"] += 1
            elif resultado in ("checkmated", "resigned", "timeout", "lose"):
                self.stats["resultados_dia"][dia_semana]["perdidas"] += 1
            else:
                self.stats["resultados_dia"][dia_semana]["tablas"] += 1
        
        print("Análisis completado.")
    
    def generar_reporte(self, guardar=False):
        """
        Imprime o guarda un reporte detallado de las estadísticas.
        """
        s = self.stats
        if not s or s["partidas_analizadas"] == 0:
            print("No se generó un reporte.")
            return

        lines = []
        lines.append("\n" + "="*40)
        lines.append("    INFORME DE ANÁLISIS DE PARTIDAS")
        lines.append("="*40)
        lines.append(f"  Usuario: {self.user}")
        lines.append(f"  Partidas analizadas: {s['partidas_analizadas']}")
        lines.append("-"*40)

        lines.append("\n📊 Resumen de Resultados")
        lines.append(f"  Ganadas: {s['ganadas']} | Perdidas: {s['perdidas']} | Tablas: {s['tablas']}")
        
        winrate = s['ganadas'] * 100 // s["partidas_analizadas"] if s["partidas_analizadas"] > 0 else 0
        lines.append(f"  Winrate global: {winrate}%")
        
        if s["blancas_partidas"] > 0:
            winrate_blancas = s['blancas_g'] * 100 // s['blancas_partidas']
            lines.append(f"  Winrate con blancas: {winrate_blancas}%")
        if s["negras_partidas"] > 0:
            winrate_negras = s['negras_g'] * 100 // s['negras_partidas']
            lines.append(f"  Winrate con negras: {winrate_negras}%")

        lines.append("\n📈 Rachas de Partidas")
        lines.append(f"  Racha más larga de victorias: {s['racha_max_g']}")
        lines.append(f"  Racha más larga de derrotas: {abs(s['racha_max_p'])}")

        lines.append("\n🤝 Rendimiento contra Rivales")
        if s['ratings_rivales']:
            avg_rating = sum(s['ratings_rivales']) // len(s['ratings_rivales'])
            lines.append(f"  Rating promedio de rivales: {avg_rating}")
        
        rival_frecuente = Counter(s['rivales']).most_common(1)
        if rival_frecuente:
            lines.append(f"  Rival más frecuente: {rival_frecuente[0][0]} ({rival_frecuente[0][1]} partidas)")
        
        if s['mejor_victoria'][1] > 0:
            lines.append(f"  Mejor victoria: contra {s['mejor_victoria'][0]} (rating {s['mejor_victoria'][1]})")
        if s['peor_derrota'][1] < 9999:
            lines.append(f"  Peor derrota: contra {s['peor_derrota'][0]} (rating {s['peor_derrota'][1]})")
            
        lines.append("\n♟️ Aperturas más jugadas:")
        for apertura, n in s["aperturas"].most_common(5):
            lines.append(f"  - {apertura} ({n} veces)")

        lines.append("\n⏱️ Ritmo de Juego y Longitud de Partidas")
        if s["partidas_analizadas"] > 0:
            lines.append(f"  Promedio de jugadas: {s['total_jugadas'] // s['partidas_analizadas']}")
        lines.append(f"  Partida más corta: {s['partida_corta'][1]} jugadas")
        lines.append(f"  Partida más larga: {s['partida_larga'][1]} jugadas")
        
        if s['time_controls']:
             lines.append("\n  Control de tiempo:")
             for tc, n in s['time_controls'].items():
                 lines.append(f"  - {tc}: {n} partidas")
        
        if s['tablas_por_tipo']:
            lines.append("\n  Tipos de tablas:")
            for t, n in s['tablas_por_tipo'].items():
                lines.append(f"    - {t}: {n}")

        lines.append("="*40)
        reporte = "\n".join(lines)
        print(reporte)

        if guardar:
            nombre = f"reporte_{self.user}_{datetime.date.today()}.txt"
            with open(nombre, "w", encoding="utf-8") as f:
                f.write(reporte)
            print(f"\nReporte guardado en {nombre}")

    def histograma_dias(self):
        """Muestra un histograma de la actividad por día de la semana."""
        print("\n📊 Actividad por día de la semana:")
        nombres = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
        actividad_por_dia = self.stats["juegos_por_dia"]
        # Convertir a un formato ordenado por el día de la semana
        dias_ordenados = {n: actividad_por_dia.get(n, 0) for n in nombres}
        
        max_juegos = max(dias_ordenados.values()) if dias_ordenados else 0
        if max_juegos > 0:
            for nombre, juegos in dias_ordenados.items():
                # Escalar el número de hashes para que el gráfico sea legible
                barras = "#" * int((juegos / max_juegos) * 20) 
                print(f"{nombre.ljust(10)}: {barras} ({juegos} partidas)")
        else:
            print("No hay datos de juegos por día.")
    
    def generar_recomendaciones(self):
        """Genera y muestra recomendaciones personalizadas basadas en las estadísticas."""
        s = self.stats
        if not s or s["partidas_analizadas"] == 0:
            return

        print("\n\n💡 Recomendaciones para Mejorar")
        print("="*40)

        # 1. Recomendación sobre el Winrate General
        winrate_global = s['ganadas'] * 100 // s["partidas_analizadas"] if s["partidas_analizadas"] > 0 else 0
        if winrate_global < 50:
            print("  - Tu porcentaje de victorias es bajo. La maestría comienza en el medio juego. Analiza tus derrotas, no solo las de apertura, y busca los momentos clave donde la posición cambió en tu contra. ¿Qué movimiento perdiste de vista?")
        else:
            print("  - Tu winrate es sólido. Ahora, enfócate en la eficiencia. ¿Puedes ganar más rápido? ¿Convertir ventajas menores en victorias decisivas? Busca la partida perfecta, aquella sin errores.")

        # 2. Recomendación sobre el balance de colores
        if s["blancas_partidas"] > 0 and s["negras_partidas"] > 0:
            winrate_blancas = s['blancas_g'] * 100 // s['blancas_partidas']
            winrate_negras = s['negras_g'] * 100 // s['negras_partidas']

            if abs(winrate_blancas - winrate_negras) > 10:
                color_inferior = "negras" if winrate_blancas > winrate_negras else "blancas"
                print(f"  - Parece que juegas significativamente mejor con {color_inferior}. La diferencia en tu juego con {color_inferior} no es una desventaja, es una oportunidad. Elige una apertura para ese color y estúdiala a fondo: los primeros 10-15 movimientos. El conocimiento en la apertura te dará un campo de batalla favorable.")

        # 3. Recomendación sobre rachas de derrotas
        if s['racha_max_p'] < -3:
            print("  - Las rachas de derrotas son un maestro cruel. No son solo sobre ajedrez; son sobre fatiga mental. Después de dos o tres derrotas consecutivas, ¡detente! Sal de la plataforma, haz algo completamente diferente. Volverás con la mente despejada y con menos probabilidades de cometer errores por frustración.")

        # 4. Recomendación sobre aperturas
        if s["aperturas"]:
            apertura_peor_rendimiento = None
            peor_winrate = 1.0
            for apertura, stats in s["aperturas_con_resultados"].items():
                if stats['total'] > 5:
                    winrate_apertura = stats['ganadas'] / stats['total']
                    if winrate_apertura < peor_winrate:
                        peor_winrate = winrate_apertura
                        apertura_peor_rendimiento = apertura

            if apertura_peor_rendimiento:
                print(f"  - Tu punto débil más claro es la apertura: '{apertura_peor_rendimiento}'. Este es el primer punto de contacto con el rival, y si te sientes incómodo desde el inicio, el final será una lucha. Dedica 15 minutos al día a ver vídeos o partidas de grandes maestros con esta apertura. Conocer las ideas detrás de los movimientos te hará imparable.")
        else:
            print("  - No se pudo analizar tu desempeño en aperturas. Sugerencia: Enfócate en una apertura por color y estúdiala a fondo. La repetición crea familiaridad, y la familiaridad reduce los errores.")

        # 5. Recomendación sobre la longitud de las partidas
        if s["partidas_analizadas"] > 0:
            promedio_jugadas = s['total_jugadas'] // s["partidas_analizadas"]
            if promedio_jugadas < 25:
                print(f"  - Tus partidas tienden a ser cortas, con un promedio de {promedio_jugadas} jugadas. Las partidas cortas a menudo terminan en errores tácticos tempranos. Tu tarea es simple pero profunda: después de cada movimiento del oponente, pregúntate, '¿A dónde quiere ir mi oponente con esta jugada?'. Esta simple pregunta te abrirá la mente a sus amenazas y a las tuyas.")
            elif promedio_jugadas > 40:
                print(f"  - Tus partidas son largas, un promedio de {promedio_jugadas} jugadas. Esto demuestra paciencia, pero ¿estás aprovechando la ventaja? Revisa tus finales. La fase final es donde las pequeñas ventajas se convierten en victorias. Domina las técnicas de finales de peones y torres, son la clave para sellar la victoria.")
        
        # 6. Recomendación de actividad por día (nueva)
        dias_semana_esp = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
        peor_dia_winrate = None
        min_winrate = 101 # Más de 100%
        
        for dia, resultados in s['resultados_dia'].items():
            total_dia = sum(resultados.values())
            if total_dia > 5:
                winrate_dia = resultados['ganadas'] * 100 / total_dia
                if winrate_dia < min_winrate:
                    min_winrate = winrate_dia
                    peor_dia_winrate = dia
        
        if peor_dia_winrate and min_winrate < 40:
             print(f"  - Tu winrate es notablemente más bajo los {peor_dia_winrate}s. A menudo, el rendimiento en el ajedrez se ve afectado por la rutina de la vida. ¿Estás jugando después de un día de trabajo estresante o cuando deberías estar descansando? Intenta tomarte un descanso ese día o jugar en otro momento para ver si tu rendimiento mejora.")


    def guardar_json(self):
        """Guarda las estadísticas en un archivo JSON."""
        if self.stats:
            nombre = f"stats_{self.user}_{datetime.date.today()}.json"
            with open(nombre, "w", encoding="utf-8") as f:
                stats_json = {k: dict(v) if isinstance(v, (Counter, defaultdict)) else v for k, v in self.stats.items()}
                stats_json['partida_corta'] = list(stats_json['partida_corta'])
                stats_json['partida_larga'] = list(stats_json['partida_larga'])
                json.dump(stats_json, f, indent=4)
            print(f"Estadísticas guardadas en {nombre}")

    def seleccionar_partida(self):
        """
        Permite al usuario seleccionar una partida para ver su PGN.
        """
        if not self.partidas:
            return

        print("\nPartidas disponibles (más recientes primero):")
        for i, game in enumerate(reversed(self.partidas), start=1):
            blanco = game["white"]["username"]
            negro = game["black"]["username"]
            resultado = game["white"]["result"] if blanco.lower() == self.user else game["black"]["result"]
            print(f"  {i}. {blanco} vs {negro} → {resultado}")
        
        try:
            opcion = input("\nElige número de partida para ver detalles (o ENTER para omitir): ")
            if opcion.isdigit():
                idx = len(self.partidas) - int(opcion)
                if 0 <= idx < len(self.partidas):
                    seleccionada = self.partidas[idx]
                    print("\nDetalles de la partida elegida:")
                    print(f"  Evento: {seleccionada.get('event', 'N/A')}")
                    print(f"  Fecha: {datetime.datetime.fromtimestamp(seleccionada.get('end_time', 0))}")
                    print(f"  Blancas: {seleccionada['white']['username']} ({seleccionada['white'].get('rating', 'N/A')})")
                    print(f"  Negras: {seleccionada['black']['username']} ({seleccionada['black'].get('rating', 'N/A')})")
                    print(f"  Resultado: {seleccionada['white']['result'] if seleccionada['white']['username'].lower() == self.user else seleccionada['black']['result']}")
                    print(f"\n  PGN completo:\n{seleccionada['pgn']}")
                else:
                    print("Número de partida inválido.")
            else:
                print("Operación omitida.")
        except (ValueError, IndexError):
            print("Entrada inválida. Operación omitida.")

# --- Ejecución del script ---
if __name__ == "__main__":
    nombre_usuario = input("Por favor, ingresa el nombre de usuario de Chess.com: ")
    analizador = ChessAnalizadorPro(nombre_usuario)

    if analizador.obtener_partidas(meses_a_analizar=1):
        analizador.analizar_partidas()
        analizador.generar_reporte(guardar=True)
        analizador.guardar_json()
        analizador.histograma_dias()
        analizador.generar_recomendaciones()
        analizador.seleccionar_partida()