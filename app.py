from flask import Flask, render_template, request, send_file
from io import BytesIO
import exifread
import pandas as pd
import re
import os

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'static/uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB

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
    except Exception as e:
        return pd.NA

def extrair_valores_gps(ifd_obj):
    try:
        return [str(x) for x in ifd_obj.values]
    except Exception as e:
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
        tags = exifread.process_file(arquivo)
        lista_tags.append(tags)

    # CORREÇÃO CRÍTICA: Garante estrutura consistente do DataFrame
    colunas_para_manter = [
        "Image ImageDescription",
        "Image DateTime",
        "GPS GPSLatitude", 
        "GPS GPSLongitude"
    ]

    dados = []
    for tags in lista_tags:
        foto_data = {}
        for chave in colunas_para_manter:
            # Garante que todas as colunas existam, mesmo com valores ausentes
            foto_data[chave] = str(tags.get(chave, pd.NA))  
        dados.append(foto_data)

    df_fotos = pd.DataFrame(dados)

    # Renomear colunas
    df_fotos_renamed = df_fotos.rename(columns={
        'Image ImageDescription': 'N° do Indivíduo',
        'Image DateTime': 'Data e Hora',
        'GPS GPSLatitude': 'Latitude',
        'GPS GPSLongitude': 'Longitude'
    })

    # Processamento de datas
    df_fotos_renamed['Data e Hora'] = df_fotos_renamed['Data e Hora'].replace('nan', pd.NA)
    partes = df_fotos_renamed['Data e Hora'].str.split(' ', n=1, expand=True)
    
    df_fotos_renamed['Hora'] = partes[1].str.strip() if partes.shape[1] > 1 else pd.NA
    df_fotos_renamed['Data Formatada'] = partes[0].str.replace(':', '-', n=2)
    
    # ... (mantenha o restante do processamento igual ao seu código original)

    # Geração do Excel
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
