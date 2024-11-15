import os
import requests
import numpy as np
import pandas as pd
import streamlit as st
import folium
from streamlit_folium import folium_static
from sklearn.metrics import mean_squared_error, mean_absolute_error, r2_score
from sklearn.ensemble import RandomForestRegressor
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import MinMaxScaler
import plotly.express as px
import plotly.graph_objects as go
from supabase import create_client, Client

def show_modelo():

    def get_supabase_client() -> Client:
        url = st.secrets["connections"]["supabase"]["SUPABASE_URL"]
        key = st.secrets["connections"]["supabase"]["SUPABASE_KEY"]
        return create_client(url, key)

    def guardar_prediccion_supabase(datos_prediccion):
        try:
            client = get_supabase_client()
            
            # Insertar datos en Supabase
            response = client.table('prediccion').insert(datos_prediccion).execute()
            
            if response.data:
                st.success("¡Datos guardados exitosamente en Supabase!")
                return True
            else:
                st.error("Error al guardar los datos en Supabase")
                return False
        except Exception as e:
            st.error(f"Error al conectar con Supabase: {str(e)}")
            return False

    # Título y descripción de la aplicación
    st.title('Modelo de Random Forest para Pesca Artesanal en Coishco')
    st.write("""
    Esta aplicación permite visualizar la importancia de las características en un modelo de Random Forest para la predicción del volumen de captura.
    """)

    # Cargar los datos
    df = pd.read_excel('data/data.xlsx')

    # Función para categorizar horas en intervalos de 2 horas
    def categorize_hour(hour):
        period = "A.M." if hour < 12 else "P.M."
        hour_12 = hour % 12
        hour_12 = 12 if hour_12 == 0 else hour_12
        start_hour = hour_12
        end_hour = (hour_12 + 2) % 12
        end_hour = 12 if end_hour == 0 else end_hour
        return f"{start_hour:02d} - {end_hour:02d} {period}"

    # Aplicar la función para categorizar horas en 'Hora_Faena'
    df['Hora_Faena'] = df['Inicio_Faena'].dt.hour.apply(categorize_hour)

    # Crear la columna 'Mes_Faena' y mapear los meses a abreviaturas
    meses = {1: 'ENE', 2: 'FEB', 3: 'MAR', 4: 'ABR', 5: 'MAY', 6: 'JUN', 
             7: 'JUL', 8: 'AGO', 9: 'SEP', 10: 'OCT', 11: 'NOV', 12: 'DIC'}
    df['Mes_Faena'] = df['Inicio_Faena'].dt.month.map(meses)

    # Crear rangos para 'Precio_Kg' y 'Talla_cm'
    bins_precio = [0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55]
    labels_precio = ["S/ (0 - 5)", "S/ (5 - 10)", "S/ (10 - 15)", "S/ (15 - 20)", 
                     "S/ (20 - 25)", "S/ (25 - 30)", "S/ (30 - 35)", "S/ (35 - 40)", 
                     "S/ (40 - 45)", "S/ (45 - 50)", "S/ (50 - 55)"]
    df['Precio_Float'] = pd.cut(df['Precio_Kg'], bins=bins_precio, labels=labels_precio, right=False)

    bins_talla = [10, 20, 30, 40, 50, 60, 70, 80, 90, 100, 110, 120, 130, 140, 150]
    labels_talla = ["(10 - 20) cm", "(20 - 30) cm", "(30 - 40) cm", "(40 - 50) cm", 
                   "(50 - 60) cm", "(60 - 70) cm", "(70 - 80) cm", "(80 - 90) cm", 
                   "(90 - 100) cm", "(100 - 110) cm", "(110 - 120) cm", "(120 - 130) cm", 
                   "(130 - 140) cm", "(140 - 150) cm"]
    df['Talla_Float'] = pd.cut(df['Talla_cm'], bins=bins_talla, labels=labels_talla, right=False)

    # Selección del enfoque para las predicciones
    opcion = st.selectbox("Seleccionar el enfoque", ["Embarcación", "Especie"], key="enfoque_selectbox")

    # Filtrar según la opción seleccionada
    if opcion == "Embarcación":
        seleccion = st.selectbox("Seleccionar la embarcación", df['Embarcacion'].unique(), key="embarcacion_selectbox")
        df_seleccion = df[df['Embarcacion'] == seleccion]
    else:
        seleccion = st.selectbox("Seleccionar la especie", df['Especie'].unique(), key="especie_selectbox")
        df_seleccion = df[df['Especie'] == seleccion]

    # Mostrar la imagen si la opción es "Especie"
    if opcion == "Especie":
        especie_seleccionada = seleccion
        ruta_imagen = f"resources/{especie_seleccionada}.png"
        
        try:
            st.image(ruta_imagen, caption=f"Especie: {especie_seleccionada}", use_column_width=True)
        except FileNotFoundError:
            st.error(f"No se encontró la imagen para la especie: {especie_seleccionada}")

    # Mostrar el mapa centrado en la ubicación de las capturas
    st.subheader(f"Mapa de capturas para la selección: {seleccion}")
    if not df_seleccion.empty:
        mapa = folium.Map(location=[df_seleccion['Origen_Latitud'].mean(), df_seleccion['Origen_Longitud'].mean()], zoom_start=6)
        for idx, row in df_seleccion.iterrows():
            folium.Marker(
                location=[row['Origen_Latitud'], row['Origen_Longitud']],
                popup=row['Especie'] if opcion == "Especie" else row['Embarcacion']
            ).add_to(mapa)
        folium_static(mapa)
    else:
        st.warning("No hay datos disponibles para la selección realizada.")

    # Definir las características y la variable objetivo
    selected_columns = ['Caballos_Motor', 'Millas_Recorridas', 'Precio_Kg', 'Talla_cm', 
                       'Costo_Combustible', 'Ganancia', 'Temperatura_Agua_°C', 
                       'Profundidad_m', 'Salinidad_PSU', 'Velocidad_Viento_m_s',
                       'Corriente_Marina_m_s', 'CPUE']

    # Verificar si las columnas existen en el DataFrame
    missing_columns = [col for col in selected_columns + ['Volumen_Kg'] if col not in df.columns]
    if missing_columns:
        st.error(f"Faltan las siguientes columnas en los datos: {missing_columns}")
        return

    # Normalizar los datos
    scaler = MinMaxScaler()
    df_normalized = df.copy()
    df_normalized[selected_columns] = scaler.fit_transform(df[selected_columns])

    X = df_normalized[selected_columns]
    y = df_normalized['Volumen_Kg']

    # Entrenar modelo de Random Forest
    X_train, X_val, y_train, y_val = train_test_split(X, y, test_size=0.2, random_state=42)
    modelo_rf = RandomForestRegressor(n_estimators=100, random_state=42)
    modelo_rf.fit(X_train, y_train)

    # Función generar_prediccion
    def generar_prediccion(caballos_motor, millas_recorridas, precio_kg, talla_cm, 
                       costo_combustible, ganancia, temperatura_agua, profundidad, 
                       salinidad, velocidad_viento, corriente_marina, cpue):
        # Crear un nuevo conjunto de datos con los valores ingresados
        nuevos_datos = np.array([[caballos_motor, millas_recorridas, precio_kg, talla_cm, 
                                costo_combustible, ganancia, temperatura_agua, profundidad, 
                                salinidad, velocidad_viento, corriente_marina, cpue]])

        # Normalizar los nuevos datos usando el scaler
        nuevos_datos_normalizados = scaler.transform(nuevos_datos)

        # Predicción del modelo con los datos ingresados
        prediccion = modelo_rf.predict(nuevos_datos_normalizados)
        
        return prediccion[0]

    # Gráfico Interactivo: Curvas de Entrenamiento y Validación
    st.write("### Evaluación del Modelo")

    # Predicción en el conjunto de validación
    y_pred = modelo_rf.predict(X_val)

    # Cálculo de las métricas
    mse = mean_squared_error(y_val, y_pred)
    mae = mean_absolute_error(y_val, y_pred)
    r2 = r2_score(y_val, y_pred)

    # Mostrar las métricas
    st.markdown("**Métricas de Evaluación del Modelo:**")
    st.write(f"**Error Cuadrático Medio (MSE):** {mse:.4f}")
    st.write(f"**Error Absoluto Medio (MAE):** {mae:.4f}")
    st.write(f"**Coeficiente de Determinación (R²):** {r2:.4f}")

    # Explicación de las métricas
    st.markdown("""
    - **Error Cuadrático Medio (MSE):** Mide el promedio de los errores al cuadrado entre los valores reales y los predichos. Un valor menor indica un mejor desempeño del modelo.
    - **Error Absoluto Medio (MAE):** Representa el promedio de los errores absolutos entre los valores reales y los predichos. Es útil para entender el error promedio en las predicciones.
    - **Coeficiente de Determinación (R²):** Indica la proporción de la variabilidad de la variable dependiente que es explicada por el modelo. Un valor cercano a 1 sugiere un buen ajuste.
    """)

    st.subheader(f'Valores Reales vs Predichos - {seleccion} ({opcion})')
    st.markdown("""
    Este gráfico compara nuestras predicciones con los valores reales observados. Si los puntos se alinean bien con la línea diagonal, significa que nuestro modelo está haciendo un buen trabajo prediciendo el volumen de captura.
    """)
    # Gráfico de Valores Reales vs Predichos
    fig_real_vs_pred = px.scatter(x=y_val, y=y_pred, labels={'x': 'Valores Reales', 'y': 'Valores Predichos'},
                                  title='Valores Reales vs Predichos')
    fig_real_vs_pred.add_shape(type="line",
                               x0=y_val.min(), y0=y_val.min(),
                               x1=y_val.max(), y1=y_val.max(),
                               line=dict(color="Red", dash="dash"))
    st.plotly_chart(fig_real_vs_pred, use_container_width=True)

    # Gráfico de Curvas de Aprendizaje
    st.write("#### Curvas de Aprendizaje")
    st.markdown("Selecciona el número de árboles para visualizar cómo afecta al desempeño del modelo.")

    # Selección del rango de n_estimators
    n_estimators_range = st.slider("Selecciona el rango de n_estimators", 10, 200, (10, 100), step=10)

    # Preparar los rangos
    n_estimators_list = list(range(n_estimators_range[0], n_estimators_range[1]+1, 10))
    train_scores = []
    val_scores = []

    for n in n_estimators_list:
        modelo = RandomForestRegressor(n_estimators=n, random_state=42)
        modelo.fit(X_train, y_train)
        train_score = modelo.score(X_train, y_train)
        val_score = modelo.score(X_val, y_val)
        train_scores.append(train_score)
        val_scores.append(val_score)

    # Crear el gráfico de curvas de aprendizaje
    fig_learning = go.Figure()
    fig_learning.add_trace(go.Scatter(x=n_estimators_list, y=train_scores, mode='lines+markers', name='Entrenamiento'))
    fig_learning.add_trace(go.Scatter(x=n_estimators_list, y=val_scores, mode='lines+markers', name='Validación'))
    fig_learning.update_layout(title='Curvas de Aprendizaje',
                               xaxis_title='Número de Árboles (n_estimators)',
                               yaxis_title='Puntuación R²',
                               yaxis=dict(range=[0,1]))
    st.plotly_chart(fig_learning, use_container_width=True)
    
    # Cargar la clave de RapidAPI desde los secretos de Streamlit
    rapidapi_key = st.secrets["RAPIDAPI"]["key"]

    # Función para generar la predicción basada en la entrada del usuario
    def generar_respuesta_rapidapi(prediccion, user_inputs):
        url = "https://cheapest-gpt-4-turbo-gpt-4-vision-chatgpt-openai-ai-api.p.rapidapi.com/v1/chat/completions"
        
        prompt = f"""
        El modelo predice un volumen capturado de {prediccion:.2f} kg basado en los siguientes datos:
        - Caballos de Motor: {user_inputs['caballos_motor']}
        - Millas Recorridas: {user_inputs['millas_recorridas']}
        - Precio por Kg: {user_inputs['precio_kg']}
        - Talla del Pescado: {user_inputs['talla_cm']}
        - Costo de Combustible: {user_inputs['costo_combustible']}
        - Ganancia: {user_inputs['ganancia']}
        - Temperatura del Agua: {user_inputs['temperatura_agua']} °C
        - Profundidad del Mar: {user_inputs['profundidad']} metros
        - Salinidad: {user_inputs['salinidad']} PSU
        - Velocidad del Viento: {user_inputs['velocidad_viento']} m/s
        - Corriente Marina: {user_inputs['corriente_marina']} m/s
        - Índice CPUE: {user_inputs['cpue']}

        Explica en lenguaje simple cómo estos factores pueden influir en el volumen de captura predicho.
        """

        payload = {
            "messages": [
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            "model": "gpt-4o",
            "max_tokens": 1000,
            "temperature": 0.7
        }
        headers = {
            "x-rapidapi-key": rapidapi_key,
            "x-rapidapi-host": "cheapest-gpt-4-turbo-gpt-4-vision-chatgpt-openai-ai-api.p.rapidapi.com",
            "Content-Type": "application/json"
        }

        try:
            response = requests.post(url, json=payload, headers=headers)
            response.raise_for_status()  # Raise an exception for bad status codes
            result = response.json()
            return result['choices'][0]['message']['content'].strip()
        except requests.RequestException as e:
            st.error(f"Error al comunicarse con la API de RapidAPI: {e}")
            return ""
        except Exception as e:
            st.error(f"Error inesperado: {e}")
            return ""

    # Interfaz del GPT en Streamlit
    st.header("Formulario para Predicción de Volumen Capturado con Explicación")

    # Campos de entrada para el usuario
    caballos_motor = st.slider("Caballos de Motor", 10, 50, 20)
    millas_recorridas = st.slider("Millas Recorridas", 1, 100, 10)
    precio_kg = st.slider("Precio por Kg", 1.0, 55.0, 15.0)  # Ajustado para coincidir con bins_precio
    talla_cm = st.slider("Talla del Pescado (cm)", 10, 150, 30)  # Ajustado para coincidir con bins_talla
    costo_combustible = st.slider("Costo de Combustible (S/.)", 10.0, 1000.0, 100.0)
    ganancia = st.slider("Ganancia (S/.)", 50.0, 5000.0, 500.0)
    temperatura_agua = st.slider("Temperatura del Agua (°C)", 15.0, 30.0, 25.0)
    profundidad = st.slider("Profundidad del Mar (m)", 10.0, 100.0, 50.0)
    salinidad = st.slider("Salinidad del Agua (PSU)", 30.0, 40.0, 35.0)
    velocidad_viento = st.slider("Velocidad del Viento (m/s)", 1.0, 20.0, 5.0)
    corriente_marina = st.slider("Corriente Marina (m/s)", 0.1, 2.0, 0.5)
    cpue = st.slider("Índice CPUE", 0.1, 5.0, 1.0)

    # Variable de control para mostrar el gráfico
    mostrar_grafico = False

    # Cuando el usuario envía los datos
    col1, col2 = st.columns(2)
    with col1:
        if st.button("Generar Predicción y Explicación"):
            # Almacenar las entradas del usuario en un diccionario
            user_inputs = {
                'caballos_motor': caballos_motor,
                'millas_recorridas': millas_recorridas,
                'precio_kg': precio_kg,
                'talla_cm': talla_cm,
                'costo_combustible': costo_combustible,
                'ganancia': ganancia,
                'temperatura_agua': temperatura_agua,
                'profundidad': profundidad,
                'salinidad': salinidad,
                'velocidad_viento': velocidad_viento,
                'corriente_marina': corriente_marina,
                'cpue': cpue
            }
            
            # Generar la predicción usando el modelo
            prediccion = generar_prediccion(caballos_motor, millas_recorridas, precio_kg, talla_cm, 
                                            costo_combustible, ganancia, temperatura_agua, profundidad, 
                                            salinidad, velocidad_viento, corriente_marina, cpue)

            # Almacenar las entradas del usuario, la predicción y las selecciones
            datos_prediccion = {
                # Datos de selección del usuario
                'enfoque': opcion,
                'seleccion_nombre': seleccion,
                'n_estimators': n_estimators_range[1],  # Usamos el valor máximo del rango
                
                # Datos del formulario
                'caballos_motor': caballos_motor,
                'millas_recorridas': millas_recorridas,
                'precio_kg': precio_kg,
                'talla_cm': talla_cm,
                'costo_combustible': costo_combustible,
                'ganancia': ganancia,
                'temperatura_agua': temperatura_agua,
                'profundidad': profundidad,
                'salinidad': salinidad,
                'velocidad_viento': velocidad_viento,
                'corriente_marina': corriente_marina,
                'cpue': cpue,
                'volumen_predicho': float(prediccion)
            }
            
            # Guardar en variable de sesión para usar con el botón de Supabase
            st.session_state['ultima_prediccion'] = datos_prediccion

            # Mostrar predicción de forma más llamativa
            st.markdown(f"""
                <div style="text-align: center; padding: 20px; 
                            background-color: rgba(0, 0, 0, 0); 
                            border-radius: 10px; 
                            border: 2px solid #eb5952;">
                    <h3 style="color: #93c7fa;">📈 Predicción del Volumen Capturado (Kg):</h3>
                    <p style="font-size: 28px; font-weight: bold; 
                            color: #ec5a53;">{prediccion:.2f} Kg</p>
                </div>
            """, unsafe_allow_html=True)
            
            # Usar API para generar una respuesta explicativa
            explicacion = generar_respuesta_rapidapi(prediccion, user_inputs)
            
            if explicacion:
                with st.container():
                    st.markdown("### Explicación")
                    st.markdown(f"{explicacion}")
            
            mostrar_grafico = True

    with col2:
        if st.button("Guardar en Supabase"):
            if 'ultima_prediccion' in st.session_state:
                if guardar_prediccion_supabase(st.session_state['ultima_prediccion']):
                    # Mostrar datos guardados en una tabla
                    st.write("Datos guardados:")
                    df_guardado = pd.DataFrame([st.session_state['ultima_prediccion']])
                    st.dataframe(df_guardado)
            else:
                st.warning("Primero debe generar una predicción antes de guardar")

    # Mostrar el gráfico solo si se ha generado la predicción y la explicación
    if mostrar_grafico:
        # Gráfico de importancia de características
        importances = modelo_rf.feature_importances_
        indices = X.columns
        feature_importances = pd.Series(importances, index=indices).sort_values(ascending=False)

        st.subheader('Importancia de Características')
        st.markdown("""
        La importancia de características nos ayuda a entender cuáles variables son más influyentes en la predicción del volumen de captura.
        """)
        fig = px.bar(feature_importances, x=feature_importances.index, y=feature_importances.values,
                    title="Importancia de las Características para Predicción",
                    labels={'x': 'Características', 'y': 'Importancia'})
        st.plotly_chart(fig, use_container_width=True)

        # Mostrar la característica más influyente
        caracteristica_principal = feature_importances.idxmax()
        st.markdown(f"**La característica más influyente es:** `{caracteristica_principal}`, lo que indica que esta variable tiene el mayor impacto en la predicción del volumen de captura.")

# Ejecutar la función display si el script es el principal
if __name__ == "__main__":
    display()
