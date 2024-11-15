import streamlit as st
import pandas as pd
from supabase import create_client, Client
import openpyxl
from datetime import datetime, time
from dateutil import parser
import re
import logging

def show_carga():
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)

    st.subheader("REGISTRO DEL DESEMBARQUE DE RECURSOS HIDROBIOLÓGICOS PROCEDENTE DEL ÁMBITO MARÍTIMO")

    @st.cache_resource
    def get_supabase_client() -> Client:
        url = st.secrets["connections"]["supabase"]["SUPABASE_URL"]
        key = st.secrets["connections"]["supabase"]["SUPABASE_KEY"]
        return create_client(url, key)

    supabase = get_supabase_client()

    def es_matricula_formal(matricula):
        if not isinstance(matricula, str):
            return False
        patron = r'^CE-\d{5}-[A-Z]{2}$'
        return bool(re.match(patron, matricula))

    def parsear_fecha(fecha):
        if isinstance(fecha, datetime):
            return fecha.strftime("%Y-%m-%d")
        elif isinstance(fecha, str):
            try:
                fecha_dt = parser.parse(fecha, dayfirst=True, fuzzy=True)
                return fecha_dt.strftime("%Y-%m-%d")
            except parser.ParserError:
                fecha_mod = fecha.replace(" ", "/")
                try:
                    fecha_dt = parser.parse(fecha_mod, dayfirst=True, fuzzy=True)
                    return fecha_dt.strftime("%Y-%m-%d")
                except parser.ParserError:
                    return None
        return None

    def parsear_hora(valor_hora):
        """Convierte diferentes formatos de hora a formato HH:mm"""
        if isinstance(valor_hora, time):
            return valor_hora.strftime("%H:%M")
        elif isinstance(valor_hora, datetime):
            return valor_hora.strftime("%H:%M")
        elif isinstance(valor_hora, str):
            try:
                # Intenta parsear la hora en formato 24 horas
                hora_dt = parser.parse(valor_hora)
                return hora_dt.strftime("%H:%M")
            except:
                try:
                    # Si es un número decimal (ejemplo: 13.30), conviértelo a HH:mm
                    hora_decimal = float(valor_hora)
                    horas = int(hora_decimal)
                    minutos = int((hora_decimal % 1) * 60)
                    return f"{horas:02d}:{minutos:02d}"
                except:
                    return None
        return None

    def get_o_crear_especie(supabase, nombre_comun, nombre_cientifico, tipo):
        try:
            logger.info(f"Buscando especie: {nombre_cientifico}")
            response = supabase.table("especie").select("id").eq("nombre_cientifico", nombre_cientifico).execute()
            if response.data:
                return response.data[0]['id']
            else:
                logger.info(f"Creando nueva especie: {nombre_cientifico}")
                response = supabase.table("especie").insert({
                    "nombre_comun": nombre_comun,
                    "nombre_cientifico": nombre_cientifico,
                    "tipo": tipo,
                    "volumen_total": 0  # Inicializar volumen total
                }).execute()
                return response.data[0]['id']
        except Exception as e:
            logger.error(f"Error al procesar especie: {e}")
            st.error(f"Error al procesar especie: {e}")
            return None

    def actualizar_volumen_especie(supabase, especie_id, volumen_adicional):
        """Actualiza el volumen total de una especie"""
        try:
            # Obtener el volumen actual
            response = supabase.table("especie").select("volumen_total").eq("id", especie_id).execute()
            if response.data:
                volumen_actual = float(response.data[0]['volumen_total'] or 0)
                nuevo_volumen = volumen_actual + float(volumen_adicional or 0)
                
                # Actualizar el volumen total
                supabase.table("especie").update({"volumen_total": nuevo_volumen}).eq("id", especie_id).execute()
                logger.info(f"Volumen actualizado para especie {especie_id}: {nuevo_volumen}")
        except Exception as e:
            logger.error(f"Error al actualizar volumen de especie: {e}")

    def get_o_crear_embarcacion(supabase, matricula, nombre, es_formal):
        try:
            if not matricula:
                return None
                
            logger.info(f"Buscando embarcación: {matricula}")
            response = supabase.table("embarcacion").select("id").eq("matricula", matricula).execute()
            if response.data:
                return response.data[0]['id']
            else:
                logger.info(f"Creando nueva embarcación: {matricula}")
                response = supabase.table("embarcacion").insert({
                    "matricula": matricula,
                    "nombre": nombre,
                    "condicion": "FORMAL" if es_formal else "INFORMAL",
                    "es_formal": es_formal
                }).execute()
                return response.data[0]['id']
        except Exception as e:
            logger.error(f"Error al procesar embarcación: {e}")
            st.error(f"Error al procesar embarcación: {e}")
            return None

    def procesar_y_enviar_archivo(uploaded_file):
        errores = []
        try:
            logger.info(f"Procesando archivo: {uploaded_file.name}")
            wb = openpyxl.load_workbook(uploaded_file, data_only=True)

            for sheet_name in wb.sheetnames:
                sheet = wb[sheet_name]
                logger.info(f"Procesando hoja: {sheet_name}")

                # Datos básicos
                departamento = sheet["E6"].value or ""
                provincia = sheet["L6"].value or ""
                distrito = sheet["Q6"].value or ""
                recopilador = sheet["Q8"].value or sheet["Q9"].value or ""
                fecha_cell = sheet["L8"].value
                fecha = parsear_fecha(fecha_cell)

                # Crear recopilación
                recopilacion_data = {
                    "nombre_recopilador": recopilador.strip() if isinstance(recopilador, str) else "",
                    "zona_operacion": f"{departamento}, {provincia}, {distrito}",
                    "fecha_registro": fecha
                }

                response_recopilacion = supabase.table("recopilacion").insert(recopilacion_data).execute()
                recopilacion_id = response_recopilacion.data[0]['id']

                # Procesar cada fila de datos (13 a 57)
                for row in range(13, 58):
                    nombre_comun = sheet[f"C{row}"].value or ""
                    nombre_cientifico = sheet[f"D{row}"].value or ""
                    tipo = sheet[f"X{row}"].value or ""
                    destino = sheet[f"V{row}"].value or ""
                    hora_descarga = parsear_hora(sheet[f"O{row}"].value)  # Parsear hora de descarga

                    if nombre_cientifico:
                        try:
                            cantidad = sheet[f"E{row}"].value
                            unidad_medida = sheet[f"F{row}"].value or ""
                            volumen = sheet[f"G{row}"].value
                            aparejo = sheet[f"H{row}"].value or ""
                            procedencia = sheet[f"I{row}"].value or ""
                            embarcacion = sheet[f"J{row}"].value or ""
                            matricula = sheet[f"K{row}"].value or ""
                            es_formal = es_matricula_formal(matricula)

                            # Obtener o crear especie
                            especie_id = get_o_crear_especie(
                                supabase,
                                nombre_comun.strip() if isinstance(nombre_comun, str) else "",
                                nombre_cientifico.strip() if isinstance(nombre_cientifico, str) else "",
                                tipo.strip() if isinstance(tipo, str) else ""
                            )

                            # Actualizar volumen total de la especie
                            if especie_id and volumen:
                                actualizar_volumen_especie(supabase, especie_id, volumen)

                            # Obtener o crear embarcación
                            embarcacion_id = get_o_crear_embarcacion(
                                supabase,
                                matricula.strip() if isinstance(matricula, str) else "",
                                embarcacion.strip() if isinstance(embarcacion, str) else "",
                                es_formal
                            )

                            # Preparar datos de descarga
                            descarga_data = {
                                "nombre_comun": nombre_comun.strip() if isinstance(nombre_comun, str) else "",
                                "nombre_cientifico": nombre_cientifico.strip() if isinstance(nombre_cientifico, str) else "",
                                "tipo": tipo.strip() if isinstance(tipo, str) else "",
                                "destino": destino.strip() if isinstance(destino, str) else "",
                                "cantidad": cantidad if isinstance(cantidad, (int, float)) else None,
                                "unidad_medida": unidad_medida.strip() if isinstance(unidad_medida, str) else "",
                                "volumen": float(volumen) if isinstance(volumen, (int, float)) else None,
                                "aparejo": aparejo.strip() if isinstance(aparejo, str) else "",
                                "procedencia": procedencia.strip() if isinstance(procedencia, str) else "",
                                "embarcacion_id": embarcacion_id,
                                "matricula": matricula.strip() if isinstance(matricula, str) else "",
                                "tripulantes": sheet[f"L{row}"].value if isinstance(sheet[f"L{row}"].value, int) else None,
                                "dias_de_faena": sheet[f"M{row}"].value if isinstance(sheet[f"M{row}"].value, int) else None,
                                "horas_de_faena": sheet[f"N{row}"].value if isinstance(sheet[f"N{row}"].value, int) else None,
                                "hora_de_descarga": hora_descarga,  # Usar la hora parseada
                                "es_formal": es_formal,
                                "recopilacion_id": recopilacion_id,
                                "registro": f"{recopilacion_id}-{matricula}-{row}"
                            }

                            # Insertar descarga
                            response_descarga = supabase.table("descarga").insert(descarga_data).execute()
                            descarga_id = response_descarga.data[0]['id']

                            # Crear relaciones
                            if especie_id and descarga_id:
                                descarga_especie_data = {
                                    "descarga_id": descarga_id,
                                    "especie_id": especie_id,
                                    "cantidad": cantidad if isinstance(cantidad, (int, float)) else 0
                                }
                                supabase.table("descarga_especies").insert(descarga_especie_data).execute()

                            if embarcacion_id and especie_id:
                                embarcacion_especie_data = {
                                    "embarcacion_id": embarcacion_id,
                                    "especie_id": especie_id,
                                    "cantidad": cantidad if isinstance(cantidad, (int, float)) else 0,
                                    "es_formal": es_formal
                                }
                                supabase.table("embarcacion_especies").insert(embarcacion_especie_data).execute()

                        except Exception as e:
                            logger.error(f"Error al procesar fila {row}: {e}")
                            errores.append(f"Error en fila {row}: {e}")

        except Exception as e:
            logger.error(f"Error al procesar el archivo {uploaded_file.name}: {e}")
            errores.append(f"Error en archivo {uploaded_file.name}: {e}")

        return errores

    # Interface de carga de archivos
    uploaded_files = st.file_uploader("Sube tus reportes Excel", type=["xlsx"], accept_multiple_files=True)

    if uploaded_files:
        if st.button("Enviar a Supabase"):
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            total_files = len(uploaded_files)
            all_errors = []
            
            for i, uploaded_file in enumerate(uploaded_files):
                status_text.text(f"Procesando archivo {i + 1} de {total_files}: {uploaded_file.name}")
                errores = procesar_y_enviar_archivo(uploaded_file)
                all_errors.extend(errores)
                progress_bar.progress((i + 1) / total_files)

            if all_errors:
                st.error("Se encontraron errores durante el proceso:")
                for error in all_errors:
                    st.error(error)
            else:
                st.success("Todos los archivos fueron procesados y enviados correctamente")
                
            status_text.text("Proceso completado")
            progress_bar.progress(1.0)
