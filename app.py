from flask import Flask, render_template, request, send_file
from io import BytesIO
import exifread
import pandas as pd
import re
import os

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'static/uploads'
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024  # 100MB

def fracao_para_float(fracao_str):
    if '/' in fracao_str:
        numerador, denominador = map(float, fracao_str.split('/'))
        return numerador / denominador
    return float(fracao_str)

def parse_gps_string(gps_str):
    partes = gps_str.split(',')
    graus = int(partes[0].strip())
    minutos = int(partes[1].strip())
    segundos = fracao_para_float(partes[2].strip())
    return graus, minutos, segundos

def formatar_gms(graus, minutos, segundos, direcao_pos, direcao_neg, negativo=False):
    direcao = direcao_neg if negativo else direcao_pos
    return f"{direcao}{graus}°{minutos}'{segundos:.2f}\""

def converter_coordenada_para_gms(coord_str, direcao_pos, direcao_neg):
    try:
        graus, minutos, segundos = parse_gps_string(coord_str)
        negativo = graus < 0
        return formatar_gms(abs(graus), minutos, segundos, direcao_pos, direcao_neg, negativo)
    except Exception:
        return pd.NA

def extrair_valores_gps(ifd_obj):
    try:
        return [str(x) for x in ifd_obj.values]
    except Exception:
        return [pd.NA, pd.NA, pd.NA]

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/processar', methods=['POST'])
def processar():
    if 'fotos' not in request.files:
        return "Erro: Nenhum arquivo enviado"
    arquivos = request.files.getlist('fotos')
    if not arquivos or arquivos[0].filename == '':
        return "Erro: Arquivos inválidos"

    lista_tags = []
    for arquivo in arquivos:
        try:
            tags = exifread.process_file(arquivo.stream, details=False)
            lista_tags.append(tags)
        except Exception as e:
            print(f"Erro ao processar arquivo {arquivo.filename}: {e}")
            lista_tags.append({})  # Inserir entrada vazia se erro

    df_fotos = pd.DataFrame([{k: v for k, v in tags.items()} for tags in lista_tags])

    colunas_para_manter = [
        "Image ImageDescription",
        "Image DateTime",
        "GPS GPSLatitude",
        "GPS GPSLongitude"
    ]
    for coluna in colunas_para_manter:
        if coluna not in df_fotos.columns:
            df_fotos[coluna] = pd.NA

    df_fotos = df_fotos[colunas_para_manter]

    df_fotos_renamed = df_fotos.rename(columns={
        'Image ImageDescription': 'N° do Indivíduo',
        'Image DateTime': 'Data e Hora',
        'GPS GPSLatitude': 'Latitude',
        'GPS GPSLongitude': 'Longitude'
    })

    df_fotos_renamed['Data e Hora'] = df_fotos_renamed['Data e Hora'].astype(str).replace('nan', pd.NA)
    partes = df_fotos_renamed['Data e Hora'].str.split(' ', n=1, expand=True)
    df_fotos_renamed['Hora'] = partes[1].str.strip() if partes.shape[1] > 1 else pd.NA

    df_fotos_renamed['Data Formatada'] = partes[0].str.replace(':', '-', n=2)
    df_fotos_renamed['Data Formatada'] = pd.to_datetime(df_fotos_renamed['Data Formatada'], format='%Y-%m-%d', errors='coerce')
    df_fotos_renamed['Data Formatada'] = df_fotos_renamed['Data Formatada'].dt.strftime('%d-%m-%Y')

    df_fotos_renamed['Latitude'] = df_fotos_renamed['Latitude'].apply(extrair_valores_gps)
    df_fotos_renamed['Longitude'] = df_fotos_renamed['Longitude'].apply(extrair_valores_gps)
    df_fotos_renamed['Latitude'] = df_fotos_renamed['Latitude'].apply(lambda x: ', '.join(x) if isinstance(x, list) else pd.NA)
    df_fotos_renamed['Longitude'] = df_fotos_renamed['Longitude'].apply(lambda x: ', '.join(x) if isinstance(x, list) else pd.NA)
    df_fotos_renamed['Latitude GMS'] = df_fotos_renamed['Latitude'].apply(lambda x: converter_coordenada_para_gms(x, 'S', 'N'))
    df_fotos_renamed['Longitude GMS'] = df_fotos_renamed['Longitude'].apply(lambda x: converter_coordenada_para_gms(x, 'W', 'E'))
    df_fotos_renamed['Coord. Geográficas U.A'] = df_fotos_renamed['Latitude GMS'] + "; " + df_fotos_renamed['Longitude GMS']

    df_fotos_final = df_fotos_renamed.drop(columns=[
        'Latitude', 'Longitude', 'Latitude GMS', 'Longitude GMS', 'Data e Hora'
    ])

    df_fotos_final['N° do Indivíduo'] = (
        df_fotos_final['N° do Indivíduo']
        .fillna('')
        .astype(str)
        .str.replace(r'\D', '', regex=True)
    )

    def ordenar_natural(valor):
        try:
            return int(valor)
        except:
            return float('inf')

    df_fotos_final_sorted = df_fotos_final.sort_values(
        by='N° do Indivíduo',
        key=lambda x: x.map(ordenar_natural)
    )

    df_fotos_final_sorted['DH ISO 8601'] = (
        pd.to_datetime(
            df_fotos_final_sorted['Data Formatada'] + ' ' + df_fotos_final_sorted['Hora'],
            format='%d-%m-%Y %H:%M:%S',
            errors='coerce'
        ).dt.strftime('%Y-%m-%dT%H:%M:%S')
    )

    df_fotos_final_sorted = df_fotos_final_sorted.reset_index(drop=True)
    df_fotos_final_sorted['N° do Indivíduo'] = pd.to_numeric(df_fotos_final_sorted['N° do Indivíduo'], errors='coerce').fillna(0).astype(int)

    nova_ordem_colunas = ['N° do Indivíduo', 'Coord. Geográficas U.A', 'Data Formatada', 'Hora', 'DH ISO 8601']
    df_timestamp = df_fotos_final_sorted[nova_ordem_colunas]

    output = BytesIO()
    df_timestamp.to_excel(output, index=False)
    output.seek(0)
    return send_file(
        output,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        download_name="inventario_florestal.xlsx",
        as_attachment=True
    )

if __name__ == '__main__':
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    app.run(debug=True)
